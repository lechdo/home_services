# Plan — service wol

## Contexte / décision

Besoin : réveiller l'Optiplex (Wake-on-LAN) depuis un smartphone Android, y compris depuis l'extérieur du réseau domestique. Un simple port-forward UDP 9 vers l'IP de l'Optiplex ne suffit pas de façon fiable : un magic packet cible l'adresse de broadcast du LAN, pas une IP précise, et la box NAT vers une IP précise, pas vers du broadcast.

Solution retenue : un petit relais HTTP (`wol`), toujours allumé, **sur le même réseau local que l'Optiplex** — le Raspberry Pi qui héberge déjà `edge` (cf. `deploiement-raspberry.md`). Le smartphone appelle ce relais en HTTPS via `edge` (authentifié par jeton) ; le relais, lui, émet le broadcast UDP en local — donc jamais de problème de routage de broadcast à travers Internet/NAT.

Outil côté smartphone (Android) : app **HTTP Shortcuts** (gratuite, F-Droid/Play Store) — une icône sur l'écran d'accueil qui déclenche une requête `POST` avec le header d'authentification. Voir `README.md`.

## Phase 1 — squelette applicatif (fait)

- `app/app.py` : script Python stdlib unique, endpoint `POST /wake` (authentifié par jeton, comparaison à temps constant) qui envoie le magic packet, `GET /health` pour un check de vie basique.
- `.env.example` : `WOL_TARGET_MAC`, `WOL_BROADCAST_ADDR`, `WOL_AUTH_TOKEN`.

## Phase 2 — Docker Compose (fait)

- `compose.yaml` : un seul service, image `python:3.12-alpine` + script monté en volume, `network_mode: host` (obligatoire pour le broadcast UDP, cf. `CLAUDE.md`), écoute directe sur `127.0.0.1:8085`.

## Phase 3 — configuration de l'Optiplex (à faire par l'utilisateur)

Accès BIOS/OS hors de portée de Claude — étapes à réaliser manuellement :

1. BIOS/UEFI : activer "Wake on LAN" / "Wake on PCI-E", désactiver tout "Deep Sleep Control" qui couperait l'alimentation de la carte réseau en veille.
2. OS (Windows : Gestionnaire de périphériques → carte réseau → Gestion de l'alimentation → "Autoriser ce périphérique à sortir l'ordinateur du mode veille" ; Linux : `ethtool -s <iface> wol g`, à rendre persistant au boot).
3. Noter l'adresse MAC de l'interface réseau concernée (celle qui reste alimentée en veille) → à mettre dans `wol/.env` (`WOL_TARGET_MAC`).
4. Vérifier que l'Optiplex a une IP stable (réservation DHCP sur la box) — pas strictement nécessaire pour le WoL lui-même (qui cible une MAC, pas une IP), mais utile pour vérifier ensuite que la machine a bien démarré.

## Phase 4 — intégration edge (à faire une fois les secrets réels connus)

Contrairement à `actual-budget`/`vikunja` (mode local uniquement), ce service a besoin d'un vrai sous-domaine public — suivre le contrat d'intégration standard d'edge (`edge/_plan/architecture.md`), comme `bitwarden`/`paperless` :

1. Ajouter le label `wol-jvince` à `DUCKDNS_SUBDOMAINS` dans `edge/.env` (fichier non versionné, à éditer manuellement).
2. Émettre le certificat Let's Encrypt (`edge/README.md`, Phase 3 : staging d'abord, puis production avec `--server letsencrypt`, obligatoire sinon acme.sh part sur ZeroSSL par défaut).
3. Copier `edge/nginx/conf.d/_example-service.conf.template` vers `edge/nginx/conf.d/wol.conf`, avec `server_name wol-jvince.duckdns.org` et `proxy_pass http://127.0.0.1:8085`.
4. `docker compose exec reverse-proxy nginx -t` puis `nginx -s reload`.

Volontairement non fait automatiquement lors du scaffolding initial : ajouter `wol.conf` avant l'émission du certificat ferait échouer le prochain reload nginx (fichier de certificat introuvable) — ce qui casserait le routage de **tous** les autres services déjà en production (`bitwarden`, `paperless`, `actual-budget`). À faire dans cet ordre précis, pas en parallèle.

## Phase 5 — déploiement sur le Raspberry Pi

- Copier le dossier `wol/` sur le Raspberry Pi (même machine que `edge`), remplir `wol/.env` avec la vraie MAC de l'Optiplex et un jeton généré (`openssl rand -hex 32`).
- `docker compose up -d`.
- Vérifier `curl http://127.0.0.1:8085/health` en local sur le Pi.

## Phase 6 — test bout en bout + configuration Android

- Depuis un réseau externe (4G) : `curl -X POST https://wol-jvince.duckdns.org/wake -H "Authorization: Bearer <token>"` doit répondre `magic packet envoye`, et l'Optiplex doit démarrer.
- Sur le smartphone Android : installer **HTTP Shortcuts**, créer une requête `POST` vers `https://wol-jvince.duckdns.org/wake` avec le header `Authorization: Bearer <token>`, l'ajouter à l'écran d'accueil. Voir `README.md`.
