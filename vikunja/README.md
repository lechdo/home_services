# vikunja

Service Docker Compose auto-hébergeant [Vikunja](https://vikunja.io/), un gestionnaire de tâches/to-do, en complément de `bitwarden` et `actual-budget` sur le même Raspberry Pi 3.

## Démarrage (première fois)

```bash
cp .env.example .env
openssl rand -hex 32   # coller le résultat dans VIKUNJA_SERVICE_SECRET
# Compléter VIKUNJA_MAILER_USERNAME/PASSWORD/FROMEMAIL (Brevo, voir .env.example)

docker compose --profile init run --rm vikunja-init   # chown 1000:1000 des volumes — une seule fois
docker compose up -d
```

Ouvrir `http://127.0.0.1:8084` (ou `https://vikunja.home.test` une fois routé par `edge`, voir `_plan/plan.md` phase 3). Le premier compte créé dans l'interface devient administrateur — pas de compte pré-configuré via variable d'environnement.

## Volumes et sauvegarde

Deux volumes nommés : `data` (base SQLite, `/db`) et `files` (pièces jointes, `/app/vikunja/files`) — chemins imposés par les défauts de l'image officielle, voir `compose.yaml`. Rien n'est régénérable en cas de perte (comme `actual-budget`, à la différence de `paperless`) — voir `_plan/plan.md` phase 5 (sauvegarde, future) pour le mécanisme envisagé.

## Exposition

Exposé publiquement via `https://task-jvince.duckdns.org` (sous-domaine DuckDNS dédié, certificat Let's Encrypt géré par `edge`). Voir `_plan/plan.md` phases 3/3b pour le détail (passage bref par un mode local avant la création de ce sous-domaine).
