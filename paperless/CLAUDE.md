# Paperless — CLAUDE.md

Ce fichier complète le `CLAUDE.md` racine. Il ne redéfinit aucune règle transverse, il précise les spécificités de ce service.

## Rôle du service

DMS (Document Management System) personnel, local-first, pour l'archivage, l'indexation et l'enrichissement sémantique de documents dont l'original vit dans Google Drive.

## Principe d'architecture du service

Trois couches, jamais mélangées :

1. **Google Drive** — source documentaire pure et immuable. Le service ne modifie jamais un fichier original dans Drive.
2. **Paperless-ngx** — moteur documentaire : stockage, OCR, recherche plein texte, tags, types de document, correspondants, custom fields, workflows. On ne réimplémente pas ce que Paperless sait déjà faire.
3. **Service RAD/LAD (à développer)** — couche d'orchestration et d'intelligence, écrite en Python, qui consomme le texte OCR de Paperless, produit une classification/extraction plus riche que celle de Paperless, et réinjecte le résultat dans Paperless via son API REST (`document_type`, `tags`, `custom_fields`).

Le service RAD/LAD ne remplace jamais le moteur documentaire de Paperless. Il l'enrichit.

Détails complets : voir `_plan/architecture.md`.

## Stack technique retenue

- **Paperless-ngx** (Docker) : moteur documentaire.
- **PostgreSQL** : base interne de Paperless (pas de base partagée avec un autre service).
- **rclone** : synchronisation unidirectionnelle Google Drive → dossier local (`consume` de Paperless), via `sidecar-gdrive-sync` dans `compose.yaml` (`rclone copy`, jamais `sync` — voir `_plan/plan.md` phase 1 pour pourquoi). Accès en lecture seule (`scope = drive.readonly`), jamais un accès complet — voir `scripts/authorize-gdrive.sh`.
- **Service RAD/LAD** : Python (FastAPI), déclenché par un workflow/webhook Paperless. Squelette implémenté (`rad-lad/`) — reçoit le webhook, relit le document et son OCR via l'API Paperless, ne classe encore rien (voir `_plan/plan.md` phase 3). Le workflow Paperless qui l'appelle est déclaré dans `provisioning/seed.json` (pas créé à la main), avec un piège à connaître si on le modifie : `as_json: true` ne doit être combiné qu'avec `params` (dict), jamais avec `body` (string) — sinon Paperless envoie une chaîne JSON-encodée plutôt qu'un objet JSON.
- **Conteneurisation obligatoire** : le service est packagé entièrement via **Docker Compose** — un unique `compose.yaml` orchestrant `postgres`, `paperless`, `rad-lad-service`, éventuellement `frontend`. Aucun composant installé nativement sur l'hôte (hors Docker). Pas de Kubernetes au démarrage.

## Exposition Internet

Ce service ne gère **jamais** lui-même de nom de domaine, de certificat TLS, ni de sidecar DuckDNS/ACME/DDNS. Si Paperless (ou le futur service RAD/LAD) doit être accessible depuis Internet, il se contente de publier un port HTTP sur l'hôte (ex. `127.0.0.1:8081:8000`) ; c'est le service `/edge/` qui le route et termine le TLS, sur un sous-domaine DuckDNS dédié (ex. `paperless.<base>.duckdns.org`). Voir `edge/CLAUDE.md` et `edge/_plan/architecture.md` pour le contrat d'intégration exact, et `_plan/plan.md` phase 8 pour le détail côté paperless.

## Persistance et mise à jour des données

- La taxonomie (types de documents, tags) est déclarée dans `provisioning/seed.json` et appliquée de façon idempotente par `provisioning/apply.py` — la base Postgres n'est qu'un état dérivé. Pour ajouter/modifier un type ou un tag : éditer le seed puis relancer `apply.py`, jamais uniquement via l'UI Paperless (sinon le seed devient obsolète silencieusement). Voir `../protocole-donnees.md` et `README.md`.
- Les documents réels (`media`) et leurs métadonnées (`pgdata`) sont des données utilisateur non déclarables. `_plan/plan-sauvegarde.md` documente le mécanisme envisagé (restic+rclone), mais la décision actuelle (2026-08-12) est de **ne pas l'implémenter** : la source brute vit déjà sur Google Drive (immuable, cf. `_plan/architecture.md`), donc `media`/`pgdata` restent reconstructibles en réingérant depuis Drive. Le plan reste écrit pour référence si cette analyse change (ex. si le volume enrichi par le RAD/LAD devient coûteux à reconstruire).

## Contraintes non négociables

- **Synchronisation unidirectionnelle** : `GDrive → local`. Jamais `local metadata → GDrive`, sauf action explicite de l'utilisateur.
- **Immutabilité de la source** : le fichier original dans Drive n'est jamais altéré par le service.
- **Reconstructibilité** : la base locale (Paperless + RAD/LAD) doit pouvoir être reconstruite entièrement à partir de Google Drive en cas de perte.
- **Décision par confiance, pas classification aveugle** : toute sortie du RAD/LAD passe par une politique de seuils de confiance avant application automatique (voir `_plan/rad-lad-contract.md`). Une confiance faible implique une validation humaine, jamais une écriture automatique silencieuse.
- **Séparation classification / tags / collections** : `document_type` = ce qu'est le document (facture, contrat...) ; `tags` = attributs associés (EDF, maison, 2026...) ; `collections` = regroupements temporaires (Impôts 2026, Déménagement...). Ne pas transformer les tags en système de dossiers déguisé.
- **Progressivité** : démarrer sans IA (règles Paperless + algorithme Auto natif), puis n'ajouter du code custom (regex/heuristiques → ML → LLM/VLM → modèle spécialisé) que si les documents en échec le justifient.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases.
- `_plan/architecture.md` — architecture détaillée et flux de synchronisation/événements.
- `_plan/data-model.md` — modèle conceptuel du Document et sa correspondance avec les objets Paperless.
- `_plan/rad-lad-contract.md` — contrat d'échange entre le service RAD/LAD et Paperless (format JSON, seuils de confiance, mapping API).
- `_plan/plan-sauvegarde.md` — ce qui est critique, outils, procédure de restauration envisagée (décision actuelle : non implémentée, cf. §Persistance ci-dessus).
- `provisioning/seed.json` + `provisioning/apply.py` — état déclaré et script idempotent pour la taxonomie (types de documents, tags).
