# minecraft

Serveur Minecraft (édition Java, Paper via `itzg/minecraft-server`) accessible depuis l'extérieur du réseau domestique, plus un panel web pour le démarrer/arrêter et changer de map. Voir `CLAUDE.md` et `_plan/plan.md` pour le contexte complet et l'état d'avancement.

Hébergé sur le second serveur physique (`192.168.1.109`, 64 Go de RAM).

## Démarrage sur le second serveur

```bash
cp .env.example .env
# éditer .env : HOST_PROJECT_DIR (chemin absolu de ce dossier sur CETTE machine),
# PANEL_SECRET_KEY (openssl rand -hex 32)

docker compose up -d docker-socket-proxy panel

# créer les comptes du panel (aucune auto-inscription) :
docker compose exec panel python manage.py add alice
docker compose exec panel python manage.py add bob
# ... un par personne autorisée (~10)
```

Le conteneur du serveur Minecraft lui-même (`minecraft-mc`) n'est jamais démarré par `docker compose` — c'est le panel qui le crée/démarre/arrête via l'API Docker (voir `panel/app.py` et `CLAUDE.md`, section "changement de map"). Rien à faire de plus ici : se connecter au panel et cliquer sur « Démarrer le serveur ».

Vérifier en local avant intégration edge :

```bash
curl http://192.168.1.109:8086/login
```

## Ajouter une nouvelle map

```bash
mkdir maps/<nom>
```

Un dossier vide suffit : le serveur Paper y génère un monde neuf au premier démarrage sur cette map. Pour importer un monde existant, copier son contenu (dossier `world/` + `server.properties` etc.) directement dans `maps/<nom>/` avant de sélectionner cette map dans le panel.

## Intégration edge (à faire une fois, sur la machine qui héberge edge)

Voir `edge/_plan/plan.md` phase 12 pour le détail complet :

1. `nginx.conf` personnalisé + `stream.d/minecraft.conf` (routage du port de jeu 25565, TCP brut) et `conf.d/minecraft-panel.conf` (panel HTTPS) — déjà écrits dans ce dépôt, restent à déployer sur la machine cible (`rsync`/`git pull`, `nginx -t`, `nginx -s reload`).
2. Sous-domaine `minecraft-jvince.duckdns.org` ajouté à `DUCKDNS_SUBDOMAINS` — émettre le certificat Let's Encrypt (staging puis production, même procédure que les autres services, voir `edge/README.md`).
3. Étape manuelle hors dépôt : ouvrir le port TCP 25565 dans le pare-feu IPv6 de la box, en plus des 80/443 déjà ouverts.

## Se connecter en jeu

Une fois tout déployé : ajouter un serveur dans le client Minecraft avec l'adresse `minecraft-jvince.duckdns.org` (port par défaut 25565, pas besoin de le préciser). Le panel de gestion est sur `https://minecraft-jvince.duckdns.org/` (port 443, implicite).
