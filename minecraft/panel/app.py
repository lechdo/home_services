import json
import os
from functools import wraps

import bcrypt
import docker
import requests.exceptions
from flask import Flask, flash, redirect, render_template, request, session, url_for

MAPS_DIR = "/app/maps"
DATA_DIR = "/app/data"
STATE_FILE = os.path.join(DATA_DIR, "state.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

CONTAINER_NAME = "minecraft-mc"
IMAGE = "itzg/minecraft-server:latest"
GAME_PORT = 25565

HOST_PROJECT_DIR = os.environ["HOST_PROJECT_DIR"]
MC_MEMORY = os.environ.get("MC_MEMORY", "6G")
MC_LAN_IP = os.environ.get("MC_LAN_IP", "192.168.1.109")

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=True)

_docker_client = None


def docker_client():
    # Initialisation paresseuse : DockerClient(...) se connecte immédiatement
    # pour négocier la version de l'API (constaté à l'usage) — si on
    # l'appelait au chargement du module, le panel entier plante au
    # démarrage tant que docker-socket-proxy n'est pas encore prêt (course
    # normale au démarrage de `docker compose up`), y compris pour la page
    # de login qui n'a pourtant rien à voir avec Docker. `version` fixé
    # explicitement pour éviter cette négociation à chaque (re)connexion.
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.DockerClient(
            base_url=os.environ["DOCKER_HOST"], version="1.44"
        )
    return _docker_client


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


# --- Maps disponibles + map sélectionnée (persistée entre redémarrages du panel) ---

def available_maps():
    if not os.path.isdir(MAPS_DIR):
        return []
    return sorted(
        name for name in os.listdir(MAPS_DIR)
        if os.path.isdir(os.path.join(MAPS_DIR, name))
    )


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def selected_map():
    maps = available_maps()
    if not maps:
        return None
    wanted = load_state().get("selected_map")
    return wanted if wanted in maps else maps[0]


# --- Conteneur du serveur Minecraft (géré directement via le SDK Docker, pas via compose) ---

def get_container():
    try:
        return docker_client().containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        return None


def container_map(container):
    for mount in container.attrs.get("Mounts", []):
        if mount.get("Destination") == "/data":
            source = mount.get("Source", "")
            return os.path.basename(source.rstrip("/"))
    return None


def server_status():
    # Ne laisse jamais une erreur Docker remonter jusqu'à la route "/" :
    # sinon le gestionnaire d'erreur générique (qui redirige vers "/" quand
    # l'utilisateur est connecté) boucle indéfiniment sur cette même route.
    # Constaté à l'usage en testant docker-socket-proxy indisponible.
    try:
        container = get_container()
        if container is None:
            return {"state": "absent", "map": None}
        container.reload()
        return {"state": container.status, "map": container_map(container)}
    except requests.exceptions.RequestException:
        return {"state": "unknown", "map": None}


def ensure_image():
    try:
        docker_client().images.get(IMAGE)
    except docker.errors.ImageNotFound:
        docker_client().images.pull(IMAGE)


def start_server(map_name):
    host_map_dir = f"{HOST_PROJECT_DIR}/maps/{map_name}"
    container = get_container()

    if container is not None and container_map(container) != map_name:
        container.remove(force=True)
        container = None

    if container is None:
        ensure_image()
        docker_client().containers.run(
            IMAGE,
            name=CONTAINER_NAME,
            detach=True,
            environment={"EULA": "TRUE", "TYPE": "PAPER", "MEMORY": MC_MEMORY},
            volumes={host_map_dir: {"bind": "/data", "mode": "rw"}},
            ports={f"{GAME_PORT}/tcp": (MC_LAN_IP, GAME_PORT)},
            restart_policy={"Name": "unless-stopped"},
        )
    else:
        container.start()


def stop_server():
    container = get_container()
    if container is not None:
        container.stop(timeout=60)


# --- Routes ---

def handle_docker_error(_error):
    # docker-socket-proxy peut être temporairement inaccessible (redémarrage,
    # course au démarrage de `docker compose up`) — mieux vaut un message
    # clair qu'une page d'erreur 500 brute. Un socket inatteignable remonte
    # en `requests.exceptions.ConnectionError` (pas encapsulé par docker-py
    # en dehors de l'initialisation du client), d'où les deux handlers —
    # constaté à l'usage, pas anticipé.
    flash("Impossible de contacter Docker en ce moment — réessayez dans quelques instants.")
    return redirect(url_for("dashboard") if session.get("user") else url_for("login"))


app.register_error_handler(docker.errors.DockerException, handle_docker_error)
app.register_error_handler(requests.exceptions.RequestException, handle_docker_error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if check_login(username, password):
            session["user"] = username
            return redirect(url_for("dashboard"))
        flash("Identifiants incorrects.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    status = server_status()
    return render_template(
        "dashboard.html",
        status=status,
        maps=available_maps(),
        current_selection=selected_map(),
        username=session["user"],
    )


@app.route("/select-map", methods=["POST"])
@login_required
def select_map():
    status = server_status()
    if status["state"] == "running":
        flash("Arrêtez le serveur avant de changer de map.")
        return redirect(url_for("dashboard"))

    wanted = request.form.get("map", "")
    if wanted not in available_maps():
        flash("Map inconnue.")
        return redirect(url_for("dashboard"))

    save_state({"selected_map": wanted})
    flash(f"Map active réglée sur « {wanted} ».")
    return redirect(url_for("dashboard"))


@app.route("/start", methods=["POST"])
@login_required
def start():
    map_name = selected_map()
    if map_name is None:
        flash("Aucune map disponible sous maps/.")
        return redirect(url_for("dashboard"))
    start_server(map_name)
    flash(f"Démarrage du serveur sur la map « {map_name} »…")
    return redirect(url_for("dashboard"))


@app.route("/stop", methods=["POST"])
@login_required
def stop():
    stop_server()
    flash("Arrêt du serveur…")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    from waitress import serve

    serve(app, host="0.0.0.0", port=8086)
