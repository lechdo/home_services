# Service actual-budget — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge [Actual Budget](https://actualbudget.org/), une application de budgétisation personnelle (enveloppes budgétaires), en local-first.

## Rôle du service

Application de suivi budgétaire personnel, self-hosted. Un seul conteneur (image officielle `actualbudget/actual-server`) qui embarque son propre stockage SQLite — pas de base de données séparée à gérer, contrairement à paperless ou bitwarden.

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : packagé entièrement via **Docker Compose** — un unique `compose.yaml` avec un seul service `actual-budget`. Aucun composant installé nativement sur l'hôte (hors Docker).
- **Mono-conteneur, pas de dépendance externe** : l'image officielle gère elle-même son stockage (SQLite) sous `/data`. Ne pas ajouter de Postgres/MySQL — ce n'est pas ce que l'image attend, et ça casserait la simplicité du service pour rien.
- **Aucune gestion TLS/DNS propre** : le conteneur écoute en HTTP simple, publié uniquement sur `127.0.0.1:8083` (loopback de l'hôte). Pas encore branché derrière `edge` (voir `_plan/plan.md`) — à faire le jour où un accès depuis l'extérieur du réseau local est nécessaire, en suivant le contrat d'intégration standard (`edge/_plan/architecture.md`), sans jamais donner à ce service son propre certificat ou sous-domaine.
- **Mot de passe applicatif** : pas de variable d'environnement pour un admin — le mot de passe se définit dans l'interface web au premier lancement. Rien à mettre dans `.env` pour ça.

## Persistance et gestion des volumes

- **Un seul volume nommé `data`** (monté sur `/data`), délibérément nommé — pas anonyme — pour rester adressable par un futur mécanisme de sauvegarde, conformément à la demande explicite de préparer ce point avant même d'implémenter le backup. Il contient :
  - `server-files/account.sqlite` : comptes, sessions, registre des budgets créés sur ce serveur ;
  - `user-files/<id>.sqlite` : les fichiers de budget réels (transactions, catégories, comptes bancaires suivis) — c'est **la** donnée critique de ce service.
- **Rien n'est régénérable ici** : à la différence de paperless (source brute sur Google Drive) ou de bitwarden (items chiffrés mais structure similaire), il n'existe aucune source externe de secours pour les transactions saisies dans Actual — la perte du volume `data` est une perte définitive.
- **Sauvegarde : pas encore implémentée, volontairement** (décision explicite du 2026-08-12, cf. `_plan/plan-sauvegarde.md`) — seule la structuration du volume (nommage, contenu documenté) a été faite maintenant. Le mécanisme (calqué sur `bitwarden/_plan/plan-sauvegarde.md` : restic + rclone, sidecar dédié derrière un profil Compose) est à activer dès que demandé, sans réutiliser le dépôt/remote d'un autre service (principe d'autonomie racine).
- **Pas de `provisioning/`** : Actual Budget n'a pas de notion de taxonomie/config structurelle créée via API à déclarer séparément — catégories et comptes budgétaires font partie des données utilisateur elles-mêmes (dans `user-files/*.sqlite`), pas d'une config d'infrastructure.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases.
- `_plan/plan-sauvegarde.md` — ce qui est critique dans le volume `data`, mécanisme envisagé, statut (non implémenté).
