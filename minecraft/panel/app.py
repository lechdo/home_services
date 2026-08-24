import json
import os
import random
import re
import secrets
import shutil
import socket
import struct
import threading
import time
from functools import wraps

import bcrypt
import docker
import requests
import requests.exceptions
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

MAPS_DIR = "/app/maps"
DATA_DIR = "/app/data"
PLUGIN_CACHE_DIR = os.path.join(DATA_DIR, "plugin-cache")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
GIFS_DIR = os.path.join(os.path.dirname(__file__), "static", "gifs")

CONTAINER_NAME = "minecraft-mc"
IMAGE = "itzg/minecraft-server:latest"
GAME_PORT = 25565
# Réseau Docker dédié (nommé explicitement dans compose.yaml) auquel "panel"
# rattache le conteneur du serveur à sa création — permet de lui parler en
# RCON par nom de conteneur (résolution DNS Docker sur un réseau nommé),
# sans jamais publier le port RCON sur l'hôte/LAN.
NETWORK_NAME = "minecraft_net"
RCON_PORT = 25575
DIFFICULTIES = ["peaceful", "easy", "normal", "hard"]
MAP_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
# Pseudo Minecraft (Java) : 3 à 16 caractères, lettres/chiffres/underscore.
MC_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")

# Minuteur de session : le serveur s'arrête tout seul 2h après un démarrage,
# avec des messages in-game (RCON) aux trois seuils ci-dessous avant l'arrêt
# automatique — besoin exprimé par l'utilisateur. Le renouvellement, lui,
# permet de choisir la durée de la prolongation (2h, 3h ou 5h).
SESSION_DURATION = 2 * 60 * 60
RENEWAL_HOURS = (2, 3, 5)
WARNING_THRESHOLDS = (15 * 60, 10 * 60, 5 * 60)

# Plugins proposés depuis le panel — catalogue volontairement restreint (pas
# de marketplace générique) aux deux besoins exprimés : autorisations en jeu
# (LuckPerms) et récupération de son inventaire à la mort (GravesX, le
# successeur activement maintenu du plugin "Graves" original de Ranull).
# Récupérés via l'API Modrinth (toujours la dernière version compatible
# Paper, pas d'URL de jar figée à maintenir à la main).
PLUGINS = {
    "luckperms": {
        "label": "LuckPerms (autorisations / permissions en jeu)",
        "modrinth_slug": "luckperms",
        "cache_filename": "panel-luckperms.jar",
    },
    "gravesx": {
        "label": "GravesX (tombe récupérable à la mort)",
        "modrinth_slug": "gravesx",
        "cache_filename": "panel-gravesx.jar",
    },
    "treefeller": {
        "label": "Thizzy'z Tree Feller (couper un arbre entier d'un coup)",
        "modrinth_slug": "thizzyz-tree-feller",
        "cache_filename": "panel-treefeller.jar",
    },
    "veinminer": {
        "label": "VeinMiner (miner un filon de minerai entier d'un coup)",
        "modrinth_slug": "veinminer",
        "cache_filename": "panel-veinminer.jar",
    },
    "essentialsx": {
        "label": "EssentialsX (/home, /tpa, /kit, /warp — confort multijoueur)",
        "modrinth_slug": "essentialsx",
        "cache_filename": "panel-essentialsx.jar",
    },
    "sleeper": {
        "label": "Sleeper (% de joueurs endormis pour passer la nuit, vote, messages)",
        "modrinth_slug": "sleeper",
        "cache_filename": "panel-sleeper.jar",
    },
}

HOST_PROJECT_DIR = os.environ["HOST_PROJECT_DIR"]
MC_MEMORY = os.environ.get("MC_MEMORY", "6G")
MC_LAN_IP = os.environ.get("MC_LAN_IP", "192.168.1.109")

# SSO via authentik (authentik/_plan/plan.md phase 6) : ce panel n'a pas de
# support OIDC natif (application maison), donc pas d'intégration comme
# vikunja/paperless/actual-budget — on fait confiance à l'en-tête transmis
# par edge (X-authentik-username, edge/nginx/snippets/authentik-headers.conf)
# pour auto-connecter une session, à condition que :
#   1. la requête vienne bien d'edge (TRUSTED_PROXY_IP) — sans cette
#      vérification, n'importe quel appareil du LAN capable d'atteindre ce
#      port directement pourrait usurper n'importe quel utilisateur en
#      forgeant l'en-tête lui-même (même risque que ND_EXTAUTH_TRUSTEDSOURCES
#      côté navidrome) ;
#   2. le nom d'utilisateur authentik corresponde à un compte DÉJÀ EXISTANT
#      dans users.json — pas de création automatique façon navidrome, un
#      panel qui contrôle un serveur de jeu n'a pas vocation à s'ouvrir à
#      n'importe quel compte authentik d'un coup (ex. un compte créé plus
#      tard pour un autre service). Un utilisateur du panel sans compte
#      authentik (cas réel : "jean_aurelien") garde son login local
#      classique — rien ne change pour lui.
TRUSTED_PROXY_IP = os.environ.get("TRUSTED_PROXY_IP", "192.168.1.99")
TRUSTED_AUTH_HEADER = "X-Authentik-Username"

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    # true par défaut (accès prévu via https://minecraft-jvince.duckdns.org
    # une fois edge branché) — mettre COOKIE_SECURE=false en attendant, pour
    # tester en direct en HTTP simple (http://<IP>:8086) : un cookie Secure
    # n'est jamais renvoyé par le navigateur sur une connexion non-HTTPS,
    # ce qui fait échouer silencieusement la connexion (retour à /login sans
    # message d'erreur). Constaté à l'usage (2026-08-17).
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
)


@app.before_request
def try_trusted_header_login():
    if session.get("user"):
        return
    if request.remote_addr != TRUSTED_PROXY_IP:
        return
    username = request.headers.get(TRUSTED_AUTH_HEADER)
    if not username:
        return
    if username in load_users():
        session["user"] = username

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


# --- Actions Docker en arrière-plan (start/stop) ---

# container.stop() attend jusqu'à 60s (arrêt propre, sauvegarde du monde) et
# bloquait toute la requête HTTP pendant ce temps — aucun retour visuel côté
# page pendant l'arrêt. Exécuté dans un thread à part : la route répond tout
# de suite, et la page (via /status, interrogé périodiquement) reflète l'état
# "en cours" pendant que ça tourne. Un seul verrou global : ce panel ne gère
# qu'un seul conteneur Minecraft, pas besoin de plus fin.
_action_lock = threading.Lock()
_pending_action = None  # None | "starting" | "stopping"


def run_in_background(action, fn):
    global _pending_action
    with _action_lock:
        if _pending_action is not None:
            return False
        _pending_action = action

    def wrapper():
        global _pending_action
        try:
            fn()
        finally:
            with _action_lock:
                _pending_action = None

    threading.Thread(target=wrapper, daemon=True).start()
    return True


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


# --- Maps disponibles + état persistant (sélection, difficulté par map) ---

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


def update_state(**changes):
    # Fusionne plutôt qu'écrase : plusieurs réglages indépendants (map
    # sélectionnée, difficulté par map) partagent ce même fichier.
    state = load_state()
    state.update(changes)
    save_state(state)


def selected_map():
    maps = available_maps()
    if not maps:
        return None
    wanted = load_state().get("selected_map")
    return wanted if wanted in maps else maps[0]


def map_difficulty(map_name):
    return load_state().get("difficulty", {}).get(map_name, "normal")


def set_map_difficulty(map_name, difficulty):
    state = load_state()
    state.setdefault("difficulty", {})[map_name] = difficulty
    save_state(state)


def create_map(name):
    os.makedirs(os.path.join(MAPS_DIR, name))


# --- Whitelist (contrôle d'accès au serveur de jeu, pas au panel) ---

# Liste canonique commune à toutes les maps (ce n'est pas un réglage par
# map comme la difficulté : c'est "qui a le droit de rejoindre CE service"),
# gérée depuis le panel plutôt qu'à la main dans un fichier (décision du
# 2026-08-18). Combinée à ONLINE_MODE=true (déjà la valeur par défaut de
# l'image, fixée explicitement ici) : Minecraft vérifie auprès des serveurs
# Mojang/Microsoft que le client possède réellement le compte correspondant
# au pseudo annoncé avant même de regarder la whitelist — ça empêche qu'un
# pseudo déjà utilisé par quelqu'un d'autre serve à se faire passer pour lui
# (contrairement à un filtrage par pseudo/IP déclarés, qui ne vérifie rien).
def whitelist():
    return load_state().get("whitelist", [])


def add_to_whitelist(name):
    state = load_state()
    entries = state.setdefault("whitelist", [])
    if name not in entries:
        entries.append(name)
        save_state(state)
    if server_status()["state"] == "running":
        try:
            rcon_command(f"whitelist add {name}")
        except Exception:
            pass  # appliqué au prochain démarrage via WHITELIST/ENFORCE_WHITELIST


def remove_from_whitelist(name):
    state = load_state()
    entries = state.get("whitelist", [])
    if name in entries:
        entries.remove(name)
        save_state(state)
    if server_status()["state"] == "running":
        try:
            rcon_command(f"whitelist remove {name}")
        except Exception:
            pass


# --- Illustration (gif) affichée pendant que le serveur tourne ---

def available_gifs():
    if not os.path.isdir(GIFS_DIR):
        return []
    return sorted(name for name in os.listdir(GIFS_DIR) if name.lower().endswith(".gif"))


def roll_random_gif():
    # Nouveau tirage aléatoire — appelé à chaque chargement complet de la
    # page et à chaque démarrage du serveur (besoin exprimé par l'utilisateur),
    # pas à chaque poll de /status (sinon le gif changerait toutes les 3s).
    gifs = available_gifs()
    if not gifs:
        return None
    chosen = random.choice(gifs)
    update_state(current_gif=chosen)
    return chosen


def current_gif():
    gifs = available_gifs()
    if not gifs:
        return None
    chosen = load_state().get("current_gif")
    return chosen if chosen in gifs else roll_random_gif()


# --- Plugins (catalogue restreint, récupérés à la demande depuis Modrinth) ---

def plugin_jar_path(map_name, key):
    return os.path.join(MAPS_DIR, map_name, "plugins", PLUGINS[key]["cache_filename"])


def is_plugin_enabled(map_name, key):
    return os.path.exists(plugin_jar_path(map_name, key))


def fetch_plugin_jar(key):
    # Mis en cache une seule fois (/app/data/plugin-cache), réutilisé pour
    # toutes les maps ensuite — pas retéléchargé à chaque activation.
    plugin = PLUGINS[key]
    cache_path = os.path.join(PLUGIN_CACHE_DIR, plugin["cache_filename"])
    if os.path.exists(cache_path):
        return cache_path

    versions = requests.get(
        f"https://api.modrinth.com/v2/project/{plugin['modrinth_slug']}/version",
        params={"loaders": '["paper"]'},
        timeout=15,
    )
    versions.raise_for_status()
    files = versions.json()[0]["files"]
    file_info = next(f for f in files if f["primary"])

    os.makedirs(PLUGIN_CACHE_DIR, exist_ok=True)
    tmp_path = cache_path + ".part"
    with requests.get(file_info["url"], timeout=60, stream=True) as download:
        download.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in download.iter_content(chunk_size=65536):
                f.write(chunk)
    os.replace(tmp_path, cache_path)
    return cache_path


def set_plugin_enabled(map_name, key, enabled):
    target = plugin_jar_path(map_name, key)
    if enabled:
        cache_path = fetch_plugin_jar(key)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(cache_path, target)
    elif os.path.exists(target):
        os.remove(target)


# --- Version en cours (lue depuis les logs, pas depuis Docker) ---

# Format confirmé en testant réellement itzg/minecraft-server (TYPE=PAPER) :
# "Starting minecraft server version <mc>" et "This server is running Paper
# version <paper> (Implementing API version <api>)", toutes deux écrites dans
# <map>/logs/latest.log par Paper lui-même dès le tout début du démarrage.
# Lire ce fichier directement (déjà accessible via le montage maps/) évite
# d'élargir les droits de docker-socket-proxy (pas besoin de LOGS/EXEC) et
# fonctionne même serveur arrêté, tant qu'il a démarré au moins une fois.
MC_VERSION_RE = re.compile(r"Starting minecraft server version (\S+)")
PAPER_VERSION_RE = re.compile(r"This server is running Paper version (.+?) \(Implementing API version")


def read_server_version(map_name):
    log_path = os.path.join(MAPS_DIR, map_name, "logs", "latest.log")
    if not os.path.exists(log_path):
        return None

    mc_version = paper_version = None
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if mc_version is None and (m := MC_VERSION_RE.search(line)):
                mc_version = m.group(1)
            if paper_version is None and (m := PAPER_VERSION_RE.search(line)):
                paper_version = m.group(1)
            if mc_version and paper_version:
                break

    if mc_version is None and paper_version is None:
        return None
    return {"minecraft": mc_version, "paper": paper_version}


def server_ready(map_name):
    # "]: Done (12.3s)! For help, type "help"" — dernière ligne du démarrage
    # de Paper, confirmée en testant réellement. latest.log étant réécrit
    # depuis zéro à chaque démarrage (rotation par log4j), sa seule présence
    # suffit à savoir que CE démarrage est terminé, pas un précédent.
    log_path = os.path.join(MAPS_DIR, map_name, "logs", "latest.log")
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            return any("]: Done (" in line for line in f)
    except OSError:
        return False


# --- Minuteur de session + notifications in-game (RCON) ---

def rcon_password():
    # Générée une fois puis persistée (panel-data/state.json) — seulement
    # joignable depuis "panel" via le réseau Docker interne (minecraft_net,
    # jamais publié sur l'hôte), pas besoin de la faire tourner.
    state = load_state()
    password = state.get("rcon_password")
    if password is None:
        password = secrets.token_hex(16)
        update_state(rcon_password=password)
    return password


# Client RCON minimal (protocole Source RCON, celui utilisé par Minecraft) —
# écrit à la main plutôt que d'utiliser une librairie tierce (ex. mcrcon) :
# constaté à l'usage que mcrcon appelle signal.signal(SIGALRM, ...) dans son
# constructeur, ce qui lève ValueError ("signal only works in main thread")
# dès qu'on l'instancie hors du thread principal — or c'est exactement le
# contexte de `session_watchdog` (thread de fond du minuteur). Le protocole
# lui-même est trivial (quelques paquets binaires), pas besoin d'une
# dépendance externe pour ça.
def _rcon_recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("RCON : connexion fermée par le serveur")
        data += chunk
    return data


def _rcon_send(sock, request_id, packet_type, payload):
    body = struct.pack("<ii", request_id, packet_type) + payload.encode("utf-8") + b"\x00\x00"
    sock.sendall(struct.pack("<i", len(body)) + body)


def _rcon_read_packet(sock):
    (length,) = struct.unpack("<i", _rcon_recv_exact(sock, 4))
    body = _rcon_recv_exact(sock, length)
    request_id, packet_type = struct.unpack("<ii", body[:8])
    return request_id, packet_type, body[8:-2].decode("utf-8", errors="replace")


def rcon_command(command, timeout=5):
    with socket.create_connection((CONTAINER_NAME, RCON_PORT), timeout=timeout) as sock:
        _rcon_send(sock, 1, 3, rcon_password())  # SERVERDATA_AUTH
        request_id, _, _ = _rcon_read_packet(sock)
        if request_id == -1:
            raise ConnectionError("RCON : authentification refusée")
        _rcon_send(sock, 2, 2, command)  # SERVERDATA_EXECCOMMAND
        return _rcon_read_packet(sock)[2]


def broadcast(message):
    # Best-effort : une notification manquée (RCON pas encore prêt juste
    # après le démarrage, conteneur qui s'arrête entre-temps...) ne doit
    # jamais interrompre le minuteur ni faire planter le thread de fond.
    try:
        rcon_command(f"say {message}")
    except Exception:
        pass


LIST_RE = re.compile(r"There are (\d+) of a max(?: of| imum)? (\d+) players online")


def player_count():
    # Best-effort comme broadcast() : un échec RCON (serveur pas encore prêt,
    # commande localisée différemment) ne doit jamais faire planter /status,
    # simplement ne rien afficher.
    try:
        response = rcon_command("list")
    except Exception:
        return None
    match = LIST_RE.search(response)
    if not match:
        return None
    return {"online": int(match.group(1)), "max": int(match.group(2))}


def format_duration(seconds):
    if seconds is None:
        return None
    if seconds < 60:
        return "< 1 min"
    minutes, _ = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}min" if hours else f"{minutes}min"


def session_expires_at():
    return load_state().get("session_expires_at")


def start_session_timer(duration=SESSION_DURATION):
    # Reset complet : un nouveau démarrage comme un renouvellement repartent
    # sur une fenêtre pleine (2h au démarrage, durée choisie au renouvellement),
    # avec les trois seuils à re-notifier.
    update_state(session_expires_at=time.time() + duration, session_notified=[])


def session_remaining():
    if server_status()["state"] not in ("running", "starting"):
        return None
    expires_at = session_expires_at()
    if expires_at is None:
        return SESSION_DURATION
    return max(0, int(expires_at - time.time()))


def session_watchdog():
    # Thread de fond unique, démarré au lancement du panel (même logique que
    # run_in_background pour start/stop) : vérifie le temps restant toutes
    # les 10s, tant que le serveur est réellement "running" (pas "starting" —
    # pas de compte à rebours tant que Paper charge encore le monde).
    while True:
        time.sleep(10)
        try:
            if server_status()["state"] != "running":
                continue
            expires_at = session_expires_at()
            if expires_at is None:
                # Serveur démarré avant l'ajout de ce minuteur (ou état
                # perdu) : repart sur une fenêtre pleine plutôt que de
                # laisser tourner indéfiniment sans limite.
                start_session_timer()
                continue

            remaining = expires_at - time.time()
            if remaining <= 0:
                broadcast("Temps ecoule, arret du serveur.")
                run_in_background("stopping", stop_server)
                continue

            notified = load_state().get("session_notified", [])
            for threshold in WARNING_THRESHOLDS:
                if remaining <= threshold and threshold not in notified:
                    broadcast(f"Arret automatique du serveur dans {threshold // 60} minutes.")
                    notified.append(threshold)
                    update_state(session_notified=notified)
        except Exception:
            continue


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


def container_env(container, key):
    for entry in container.attrs.get("Config", {}).get("Env", []):
        if entry.startswith(f"{key}="):
            return entry.split("=", 1)[1]
    return None


def server_status():
    # Ne laisse jamais une erreur Docker remonter jusqu'à la route "/" :
    # sinon le gestionnaire d'erreur générique (qui redirige vers "/" quand
    # l'utilisateur est connecté) boucle indéfiniment sur cette même route.
    # Constaté à l'usage en testant docker-socket-proxy indisponible.
    try:
        container = get_container()
        if container is None:
            state, map_name = "absent", None
        else:
            container.reload()
            map_name = container_map(container)
            if container.status == "running":
                # Docker considère le conteneur "running" dès le lancement du
                # process — Paper, lui, met encore ~30-90s à charger le monde
                # avant d'accepter des connexions. "starting" reflète cette
                # réalité plutôt que l'état brut du conteneur.
                state = "running" if server_ready(map_name) else "starting"
            else:
                state = "stopped"
    except requests.exceptions.RequestException:
        state, map_name = "unknown", None

    # L'action en arrière-plan a priorité sur l'état Docker brut : pendant un
    # arrêt (jusqu'à 60s), Docker rapporte encore "running" un moment.
    if _pending_action == "stopping":
        state = "stopping"
    elif _pending_action == "starting" and state != "running":
        state = "starting"

    return {"state": state, "map": map_name}


def ensure_image():
    try:
        docker_client().images.get(IMAGE)
    except docker.errors.ImageNotFound:
        docker_client().images.pull(IMAGE)


def start_server(map_name):
    difficulty = map_difficulty(map_name)
    whitelist_value = ",".join(whitelist())
    host_map_dir = f"{HOST_PROJECT_DIR}/maps/{map_name}"
    container = get_container()

    # Recrée le conteneur si la map, la difficulté OU la whitelist configurée
    # ne correspond plus à ce qui est demandé (les plugins, eux, n'ont pas
    # besoin de ce contrôle : leur présence sur disque dans maps/<nom>/plugins
    # est lue par Paper à chaque démarrage, un redémarrage normal suffit).
    if container is not None and (
        container_map(container) != map_name
        or container_env(container, "DIFFICULTY") != difficulty
        or container_env(container, "WHITELIST") != whitelist_value
    ):
        container.remove(force=True)
        container = None

    if container is None:
        ensure_image()
        docker_client().containers.run(
            IMAGE,
            name=CONTAINER_NAME,
            detach=True,
            environment={
                "EULA": "TRUE",
                "TYPE": "PAPER",
                "MEMORY": MC_MEMORY,
                "DIFFICULTY": difficulty,
                "ENABLE_RCON": "true",
                "RCON_PASSWORD": rcon_password(),
                "RCON_PORT": str(RCON_PORT),
                # Authentification réelle (vérifiée auprès de Mojang/Microsoft,
                # empêche qu'un pseudo déjà pris par quelqu'un d'autre serve à
                # se faire passer pour lui) + accès restreint aux ~10 comptes
                # déclarés depuis le panel — voir la section whitelist ci-dessus.
                "ONLINE_MODE": "true",
                "ENFORCE_WHITELIST": "true",
                "WHITELIST": whitelist_value,
            },
            volumes={host_map_dir: {"bind": "/data", "mode": "rw"}},
            ports={f"{GAME_PORT}/tcp": (MC_LAN_IP, GAME_PORT)},
            network=NETWORK_NAME,
            restart_policy={"Name": "unless-stopped"},
        )
    else:
        container.start()

    start_session_timer()
    roll_random_gif()


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
app.register_error_handler(requests.exceptions.ConnectionError, handle_docker_error)
app.register_error_handler(requests.exceptions.Timeout, handle_docker_error)


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


def dashboard_context():
    current_map = selected_map()
    status = server_status()
    return {
        "status": status,
        "maps": available_maps(),
        "current_selection": current_map,
        "server_version": read_server_version(current_map) if current_map else None,
        "difficulties": DIFFICULTIES,
        "current_difficulty": map_difficulty(current_map) if current_map else None,
        "session_remaining": session_remaining(),
        "session_remaining_label": format_duration(session_remaining()),
        # Uniquement quand "running" (pas "starting") : le serveur n'accepte
        # pas encore RCON pendant le chargement du monde, même logique que
        # server_ready() pour l'état affiché.
        "player_count": player_count() if status["state"] == "running" else None,
        "renewal_hours": RENEWAL_HOURS,
        "current_gif": current_gif(),
        "plugins": PLUGINS,
        "plugin_enabled": (
            {key: is_plugin_enabled(current_map, key) for key in PLUGINS}
            if current_map else {}
        ),
        "whitelist": whitelist(),
        # Les formulaires (map/difficulté/plugins) ne sont modifiables que
        # serveur arrêté — utilisé côté template ET côté /status (pour que
        # le JS puisse resynchroniser les champs sans recharger la page).
        "locked": status["state"] not in ("stopped", "absent"),
    }


@app.route("/")
@login_required
def dashboard():
    roll_random_gif()  # nouveau tirage à chaque chargement complet de la page
    return render_template(
        "dashboard.html",
        username=session["user"],
        **dashboard_context(),
    )


@app.route("/status")
@login_required
def status_json():
    context = dashboard_context()
    context.pop("plugins")  # catalogue statique, pas besoin de le repousser à chaque poll
    context.pop("renewal_hours")  # idem : liste statique de choix
    return jsonify(context)


@app.route("/create-map", methods=["POST"])
@login_required
def create_map_route():
    name = request.form.get("name", "").strip()
    if not MAP_NAME_RE.match(name):
        flash("Nom de map invalide (lettres, chiffres, - et _ uniquement).")
    elif name in available_maps():
        flash(f"Une map « {name} » existe déjà.")
    else:
        create_map(name)
        update_state(selected_map=name)
        flash(f"Map « {name} » créée et sélectionnée.")
    return redirect(url_for("dashboard"))


@app.route("/select-map", methods=["POST"])
@login_required
def select_map():
    if server_status()["state"] not in ("stopped", "absent"):
        flash("Arrêtez le serveur avant de changer de map.")
        return redirect(url_for("dashboard"))

    wanted = request.form.get("map", "")
    if wanted not in available_maps():
        flash("Map inconnue.")
        return redirect(url_for("dashboard"))

    update_state(selected_map=wanted)
    flash(f"Map active réglée sur « {wanted} ».")
    return redirect(url_for("dashboard"))


@app.route("/set-difficulty", methods=["POST"])
@login_required
def set_difficulty():
    if server_status()["state"] not in ("stopped", "absent"):
        flash("Arrêtez le serveur avant de changer la difficulté.")
        return redirect(url_for("dashboard"))

    map_name = selected_map()
    difficulty = request.form.get("difficulty", "")
    if map_name is None or difficulty not in DIFFICULTIES:
        flash("Difficulté invalide.")
    else:
        set_map_difficulty(map_name, difficulty)
        flash(f"Difficulté de « {map_name} » réglée sur « {difficulty} ».")
    return redirect(url_for("dashboard"))


@app.route("/toggle-plugin", methods=["POST"])
@login_required
def toggle_plugin():
    if server_status()["state"] not in ("stopped", "absent"):
        flash("Arrêtez le serveur avant de changer les plugins.")
        return redirect(url_for("dashboard"))

    map_name = selected_map()
    key = request.form.get("plugin", "")
    if map_name is None or key not in PLUGINS:
        flash("Plugin inconnu.")
        return redirect(url_for("dashboard"))

    enabled = not is_plugin_enabled(map_name, key)
    try:
        set_plugin_enabled(map_name, key, enabled)
    except requests.exceptions.RequestException:
        flash("Impossible de télécharger le plugin depuis Modrinth — réessayez plus tard.")
        return redirect(url_for("dashboard"))

    verb = "activé" if enabled else "désactivé"
    flash(f"{PLUGINS[key]['label']} {verb} pour « {map_name} ».")
    return redirect(url_for("dashboard"))


@app.route("/add-whitelist", methods=["POST"])
@login_required
def add_whitelist_route():
    name = request.form.get("username", "").strip()
    if not MC_USERNAME_RE.match(name):
        flash("Pseudo invalide (3 à 16 caractères, lettres/chiffres/underscore).")
    elif name in whitelist():
        flash(f"« {name} » est déjà autorisé.")
    else:
        add_to_whitelist(name)
        flash(f"« {name} » ajouté à la whitelist.")
    return redirect(url_for("dashboard"))


@app.route("/remove-whitelist", methods=["POST"])
@login_required
def remove_whitelist_route():
    name = request.form.get("username", "")
    if name in whitelist():
        remove_from_whitelist(name)
        flash(f"« {name} » retiré de la whitelist.")
    return redirect(url_for("dashboard"))


@app.route("/start", methods=["POST"])
@login_required
def start():
    map_name = selected_map()
    if map_name is None:
        flash("Aucune map disponible sous maps/.")
        return redirect(url_for("dashboard"))
    if run_in_background("starting", lambda: start_server(map_name)):
        flash(f"Démarrage du serveur sur la map « {map_name} »…")
    else:
        flash("Une action est déjà en cours.")
    return redirect(url_for("dashboard"))


@app.route("/stop", methods=["POST"])
@login_required
def stop():
    if run_in_background("stopping", stop_server):
        flash("Arrêt du serveur…")
    else:
        flash("Une action est déjà en cours.")
    return redirect(url_for("dashboard"))


@app.route("/renew-session", methods=["POST"])
@login_required
def renew_session():
    try:
        hours = int(request.form.get("hours", ""))
    except ValueError:
        hours = None

    if server_status()["state"] not in ("running", "starting"):
        flash("Le serveur n'est pas en cours d'exécution.")
    elif hours not in RENEWAL_HOURS:
        flash("Durée de renouvellement invalide.")
    else:
        start_session_timer(hours * 60 * 60)
        broadcast(f"Minuteur du serveur remis a {hours}h.")
        flash(f"Minuteur remis à {hours}h.")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    from waitress import serve

    threading.Thread(target=session_watchdog, daemon=True).start()
    serve(app, host="0.0.0.0", port=8086)
