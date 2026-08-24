# Service vikunja — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge [Vikunja](https://vikunja.io/), un gestionnaire de tâches/to-do self-hosted, en complément de `bitwarden` et `actual-budget`, déjà hébergés sur le même Raspberry Pi 3.

Voir `_plan/plan.md` avant toute implémentation.

## Rôle du service

Gestion de tâches personnelles/familiales (listes, échéances, rappels). Depuis Vikunja v0.22, un seul conteneur (image officielle `vikunja/vikunja`) embarque à la fois l'API (Go) et le frontend (assets statiques servis par le même binaire) — pas de conteneur frontend séparé comme dans les anciennes versions. Stockage SQLite par défaut, comme `actual-budget` — pas de Postgres/MySQL séparé.

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : packagé entièrement via **Docker Compose** — un unique `compose.yaml`. Aucun composant installé nativement sur l'hôte (hors Docker).
- **Mono-conteneur, SQLite par défaut** : pas de base de données séparée à orchestrer, sauf besoin réel constaté (usage familial visé — quelques comptes). Ne pas ajouter Postgres sans raison concrète.
- **SMTP à configurer dès la mise en service, pas après coup** : sans mailer (`VIKUNJA_MAILER_*`), les rappels de tâches et la réinitialisation de mot de passe ne fonctionnent pas du tout (pas de dégradation silencieuse comme chez Vaultwarden qui bascule sur l'auto-acceptation locale — voir `bitwarden/README.md`). Ajouter le SMTP après coup impose un redémarrage du conteneur ; le committer dans le `compose.yaml`/`.env` dès la Phase 1 évite un oubli. Voir `_plan/plan.md` Phase 2.
- **Aucune gestion TLS/DNS propre** : le conteneur écoute en HTTP simple, publié uniquement sur un port loopback de l'hôte — c'est `edge` qui termine le TLS, jamais ce service (contrat d'intégration standard, voir `edge/_plan/architecture.md`). **Exposé publiquement depuis le 2026-08-14** via `https://task-jvince.duckdns.org` (sous-domaine DuckDNS dédié, certificat Let's Encrypt) — passé par un bref mode local (`vikunja.home.test`, auto-signé) le même jour avant la création de ce sous-domaine, voir `_plan/plan.md` phase 3b.
- **`VIKUNJA_SERVICE_PUBLICURL`** doit correspondre exactement au nom d'hôte (+ port si non standard) réellement utilisé par les navigateurs/clients mobiles — cette valeur est réutilisée dans les emails envoyés et dans la vérification d'origine. À mettre à jour si le mode d'exposition change (local → public, voir `_plan/plan.md` Phase 3).
- **`VIKUNJA_SERVICE_SECRET` doit être fixe**, généré une fois (`openssl rand -hex 32`) et stocké dans `.env` (jamais committé) — sans cette variable, Vikunja génère un secret aléatoire à chaque démarrage du conteneur et invalide toutes les sessions ouvertes à chaque redémarrage/mise à jour. Nom de variable corrigé le 2026-08-14 : `VIKUNJA_SERVICE_JWTSECRET` (mentionné dans une version antérieure de ce fichier) est dépréciée — toujours fonctionnelle mais plus la forme recommandée.
- **Deux volumes nommés, pas un seul** : `data` monté sur `/db` (base SQLite) et `files` monté sur `/app/vikunja/files` (pièces jointes) — chemins imposés par les défauts de l'image officielle (`VIKUNJA_DATABASE_PATH=/db/vikunja.db`, `VIKUNJA_SERVICE_ROOTPATH=/app/vikunja/`), suivis tels quels plutôt que réécrits vers un point de montage unique. Le conteneur tourne en uid 1000 non-root et ne chown jamais lui-même ces volumes : un chown initial (`docker compose --profile init run --rm vikunja-init`) est obligatoire avant le tout premier démarrage.
- **SMTP : Brevo retenu** (2026-08-14) — service transactionnel, gratuit jusqu'à 300 emails/jour, n'expose pas de compte email personnel. Host/port non secrets dans `compose.yaml` ; `VIKUNJA_MAILER_USERNAME`/`PASSWORD`/`FROMEMAIL` dans `.env`.
- **Hébergé sur le Raspberry Pi 3** (pas délocalisé, à la différence d'`actual-budget`) : empreinte mesurée réellement très faible (~16 Mio), la RAM libérée par la délocalisation d'`actual-budget` suffit largement (voir `_plan/plan.md` phase 4).
- **Secrets** (mot de passe SMTP, `VIKUNJA_SERVICE_SECRET`) ne doivent jamais être committés en clair — variables d'environnement/`.env` non versionné.
- **Inscription libre désactivée** (`VIKUNJA_SERVICE_ENABLEREGISTRATION: "false"`, 2026-08-14) : les deux comptes du foyer existent déjà, le service est exposé publiquement — pas de raison de laisser n'importe qui créer un compte avec l'URL. Vérifié : `PUT /api/v1/register` répond `405` (route non montée). Un admin peut toujours créer un compte en CLI (`docker compose exec vikunja ./vikunja user create ...`) si besoin d'en ajouter un plus tard.
- **Pas de `provisioning/`** envisagé pour l'instant : Vikunja n'a pas de notion de taxonomie/config structurelle créée via API à déclarer séparément pour un usage familial simple (listes/projets/tâches sont des données utilisateur, pas de l'infra) — à réévaluer si des labels/vues partagées complexes sont créés en masse via l'API un jour.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases (service, SMTP, edge/certificats, analyse de capacité sur le Raspberry Pi 3).
