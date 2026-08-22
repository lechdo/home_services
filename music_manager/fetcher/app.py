import json
import os
import queue
import secrets
import threading
import time
from functools import wraps

import bcrypt
import yt_dlp
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

MUSIC_DIR = "/music"
DOWNLOAD_DIR = os.path.join(MUSIC_DIR, "YouTube")
# Fichier d'archive yt-dlp (une ligne par vidéo déjà téléchargée, identifiée
# par "extracteur id") — vit dans le volume "music" (pas dans /app/data) pour
# rester rattaché à la bibliothèque elle-même, voir _plan/plan.md phase 3.
ARCHIVE_FILE = os.path.join(MUSIC_DIR, ".yt-dlp-archive.txt")

DATA_DIR = "/app/data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# Nombre de lots (soumissions) gardés en mémoire pour l'affichage — pas de
# persistance entre redémarrages du conteneur, voir _plan/plan.md phase 3
# (un redémarrage pendant un téléchargement en cours est un cas rare et sans
# conséquence grave, il suffit de resoumettre l'URL).
MAX_JOBS_KEPT = 20

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    # true par défaut (accès prévu via https://music-jvince.duckdns.org/fetcher
    # une fois edge branché) — mettre COOKIE_SECURE=false pour tester en HTTP
    # direct avant l'intégration edge, même piège que minecraft/panel/app.py
    # (un cookie Secure n'est jamais renvoyé par le navigateur en HTTP simple).
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
)

# Fait comprendre à Flask que ce service est servi sous /fetcher (en-tête
# X-Forwarded-Prefix envoyé par edge, voir edge/nginx/conf.d/music.conf) —
# sans ça, url_for() générerait des liens à la racine du sous-domaine
# (/login, /status...) au lieu de /fetcher/login, /fetcher/status, cassant
# les redirections et les appels JS. Voir _plan/plan.md phase 3.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# --- Comptes utilisateurs (créés à la main via manage.py, pas d'auto-inscription) ---

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def check_login(username, password):
    users = load_users()
    stored_hash = users.get(username)
    if stored_hash is None:
        return False
    return bcrypt.checkpw(password.encode(), stored_hash.encode())


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# --- File de téléchargement (un seul worker, séquentiel) ---

# Un seul thread de fond traite les lignes une par une plutôt qu'en parallèle
# : plus simple, et évite de solliciter YouTube avec plusieurs téléchargements
# simultanés (risque de limitation) pour un usage familial qui n'en a pas
# besoin. Chaque "lot" (_jobs[job_id]) correspond à une soumission du
# formulaire, avec une ligne par URL collée par l'utilisateur.
_jobs = {}
_jobs_lock = threading.Lock()
_queue = queue.Queue()


def _prune_jobs():
    if len(_jobs) <= MAX_JOBS_KEPT:
        return
    oldest = sorted(_jobs, key=lambda job_id: _jobs[job_id]["created"])
    for job_id in oldest[: len(_jobs) - MAX_JOBS_KEPT]:
        del _jobs[job_id]


def archive_line_count():
    if not os.path.exists(ARCHIVE_FILE):
        return 0
    with open(ARCHIVE_FILE) as f:
        return sum(1 for line in f if line.strip())


def download_one(url):
    """Télécharge une URL (vidéo unique ou playlist) en MP3 dans la
    bibliothèque partagée. Retourne (état, message). yt-dlp gère lui-même
    l'expansion d'une playlist en ses vidéos, et le fichier d'archive
    (ARCHIVE_FILE) fait sauter les vidéos déjà téléchargées (individuellement
    ou via une playlist qui les recontient) sans repasser par le réseau —
    voir _plan/plan.md phase 3, "Détection des doublons".

    Le compte de lignes de l'archive avant/après sert à déterminer combien de
    pistes ont réellement été ajoutées, plutôt que de tenter de parser les
    messages internes de yt-dlp (fragile, non garanti stable entre versions).
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    before = archive_line_count()

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "download_archive": ARCHIVE_FILE,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
            # Écrit les tags ID3 (titre/artiste/album...) à partir des
            # métadonnées YouTube directement dans le MP3 final, en place —
            # aucune étape de copie séparée pour l'étiquetage (voir
            # _plan/plan.md, "un seul exemplaire du fichier audio").
            {"key": "FFmpegMetadata"},
            # Pochette (voir conversation.md) embarquée dans le MP3 lui-même.
            {"key": "EmbedThumbnail"},
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return "error", str(e)

    new = archive_line_count() - before
    if new == 0:
        return "skipped", "déjà présent dans la bibliothèque"
    if new == 1:
        return "done", "1 piste téléchargée"
    return "done", f"{new} pistes téléchargées"


def worker():
    while True:
        job_id, idx = _queue.get()
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                continue  # lot expiré (voir _prune_jobs) avant traitement
            job["lines"][idx]["state"] = "running"
            url = job["lines"][idx]["url"]

        state, message = download_one(url)

        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["lines"][idx]["state"] = state
                job["lines"][idx]["message"] = message


# --- Routes ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if check_login(username, password):
            session["user"] = username
            return redirect(url_for("index"))
        flash("Identifiants incorrects.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def jobs_context():
    with _jobs_lock:
        jobs = [
            {"id": job_id, **job}
            for job_id, job in sorted(_jobs.items(), key=lambda kv: kv[1]["created"], reverse=True)
        ]
    return jobs


@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session["user"])


@app.route("/status")
@login_required
def status_json():
    return jsonify(jobs_context())


@app.route("/submit", methods=["POST"])
@login_required
def submit():
    raw = request.form.get("urls", "")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        flash("Aucune URL fournie.")
        return redirect(url_for("index"))

    job_id = secrets.token_hex(4)
    with _jobs_lock:
        _jobs[job_id] = {
            "created": time.time(),
            "submitted_by": session["user"],
            "lines": [{"url": url, "state": "queued", "message": None} for url in lines],
        }
        _prune_jobs()

    for idx in range(len(lines)):
        _queue.put((job_id, idx))

    flash(f"{len(lines)} URL(s) mise(s) en file d'attente.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    from waitress import serve

    threading.Thread(target=worker, daemon=True).start()
    serve(app, host="0.0.0.0", port=5000)
