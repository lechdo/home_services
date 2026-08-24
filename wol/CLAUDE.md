# Service wol — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service expose un unique endpoint HTTP qui envoie un paquet magique Wake-on-LAN sur le réseau local, pour pouvoir réveiller l'Optiplex depuis un smartphone Android, y compris depuis l'extérieur du réseau domestique (4G/wifi externe).

Voir `_plan/plan.md` avant toute implémentation.

## Rôle du service

Un magic packet WoL cible normalement l'adresse de broadcast du LAN (ex. `255.255.255.255`). Depuis l'extérieur, la box ne peut pas transférer un port vers une adresse de broadcast (elle NAT vers une IP précise) — d'où ce petit relais applicatif : il tourne en permanence **sur le réseau local de l'Optiplex** (même hôte que le service `edge`, le Raspberry Pi — cf. `deploiement-raspberry.md`), reçoit un déclenchement HTTPS authentifié via `edge`, et émet lui-même le broadcast UDP en local.

Ce service ne fait qu'une seule chose : `POST /wake` (authentifié) → émission d'un magic packet vers l'adresse MAC configurée. Pas de base de données, pas d'état, pas de données utilisateur.

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : packagé via **Docker Compose**, un unique `compose.yaml`. Aucun composant installé nativement sur l'hôte (hors Docker).
- **`network_mode: host` obligatoire** : un conteneur en réseau bridge Docker par défaut ne peut pas émettre de broadcast UDP sur le vrai réseau local (seulement sur son propre réseau bridge interne) — même contrainte déjà rencontrée et documentée pour `sidecar-ddns` dans `edge` (besoin de voir/joindre le réseau réel de l'hôte, pas une interface virtuelle Docker). Sans ce mode, le magic packet ne sortirait jamais de la machine.
- **Aucune dépendance externe** : l'application est un unique script Python (`app/app.py`), stdlib uniquement (`http.server`, `socket`, `hmac`) — pas de framework, pas de `requirements.txt`, pour minimiser la surface (ce service a un accès broadcast au réseau local et doit rester trivial à auditer).
- **Authentification obligatoire par jeton** (`WOL_AUTH_TOKEN`, comparaison à temps constant via `hmac.compare_digest`) : ce endpoint agit sur du matériel physique et sera exposé publiquement (voir plus bas) — jamais d'accès anonyme, même en HTTPS.
- **Exposition Internet réelle, pas seulement locale** : contrairement à `actual-budget`/`vikunja` (mode local uniquement, `*.home.test` + certificat auto-signé), ce service a besoin d'être atteint depuis l'extérieur du réseau domestique par construction (déclenchement depuis un smartphone hors wifi maison) — il suit donc le contrat d'intégration standard d'`edge` avec un vrai sous-domaine DuckDNS + certificat Let's Encrypt (comme `bitwarden`/`paperless`), pas le mode local (`edge/_plan/architecture.md`).
- **Aucun secret dans ce dossier versionné** : l'adresse MAC de l'Optiplex et le jeton d'authentification ne vivent que dans `wol/.env` (jamais committé, voir `.env.example`).
- **Pas de `provisioning/` ni de plan de sauvegarde** : aucune donnée utilisateur ni configuration structurelle créée via API — action ponctuelle sans état, hors du périmètre de `protocole-donnees.md`.
- **Ne gère ni TLS ni DNS** : le conteneur écoute en HTTP simple sur `127.0.0.1:8085` (contrat d'intégration standard, `edge` termine le TLS).

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases, y compris les étapes manuelles (BIOS/OS de l'Optiplex, intégration edge, configuration du smartphone).
- `edge/_plan/architecture.md` — contrat d'intégration service backend ↔ edge.
