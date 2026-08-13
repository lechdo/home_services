# Plan de réalisation — service actual-budget

## Phase 0 — Choix de la stack

- Image officielle `actualbudget/actual-server` (variante `latest-alpine`, plus légère). Mono-conteneur : le serveur embarque son propre stockage SQLite sous `/data` (`server-files/account.sqlite` + `user-files/*.sqlite`) — pas de Postgres/MySQL séparé à orchestrer, contrairement à paperless.
- Port interne du conteneur : `5006` (défaut de l'image).

## Phase 1 — `compose.yaml` minimal (fait, 2026-08-12)

- Un seul service `actual-budget`, réseau `internal` dédié (pas de partage avec un autre service, conformément au principe d'autonomie racine).
- Port publié uniquement en local : `127.0.0.1:8083:5006` — pas d'exposition Internet pour l'instant (voir Phase 3).
- `ACTUAL_TRUSTED_PROXIES: "127.0.0.1"` positionné dès maintenant : sans effet tant que rien ne proxifie ce service en local, mais évite un oubli le jour où `edge` (Phase 3) ou un accès local via un reverse-proxy de test s'ajoute.

## Phase 2 — Volumes gérés pour un backup ultérieur (fait, 2026-08-12)

Demande explicite : préparer les volumes pour pouvoir les sauvegarder plus tard, sans implémenter le mécanisme de sauvegarde maintenant.

- Volume **nommé** `data` (pas anonyme) monté sur `/data` — un volume nommé est adressable par son nom dans un futur `sidecar-backup`, alors qu'un volume anonyme obligerait à retrouver son identifiant généré.
- Contenu documenté dans `plan-sauvegarde.md` : ce que contient `/data`, pourquoi tout est critique (rien n'est régénérable depuis une source externe, à la différence de paperless).
- Aucun autre volume/bind-mount créé pour l'instant : pas de sur-ingénierie avant d'avoir un besoin réel.

## Phase 3 (future, non déclenchée) — Implémentation effective de la sauvegarde

À faire quand demandé explicitement, en suivant `_plan/plan-sauvegarde.md` :
- Ajouter un `sidecar-backup` à `compose.yaml`, derrière un profil Compose dédié (même schéma que `bitwarden/compose.yaml`), avec sa propre config rclone/restic — jamais partagée avec un autre service.
- Tester une restauration complète avant de considérer le dispositif fiable (cf. protocole-donnees.md, principe racine).

## Phase 4 (future, optionnelle) — Exposition via `edge`

Non nécessaire tant que l'usage reste local (réseau domestique). Si un accès depuis l'extérieur devient utile :
- Publier le port `127.0.0.1:8083` dans la table de routage d'`edge` (nouveau sous-domaine DuckDNS dédié, ex. `budget.<base>.duckdns.org`), en suivant le contrat d'intégration standard (`edge/_plan/architecture.md`).
- Ne rien ajouter côté `actual-budget` au-delà du port déjà publié : ni certificat, ni token DuckDNS, ni sidecar DDNS/ACME propre (interdit par le principe d'autonomie racine — voir `edge/CLAUDE.md`).
