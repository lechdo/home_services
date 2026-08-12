# Plan de sauvegarde — service paperless

Périmètre : données stateful critiques uniquement (voir `../../protocole-donnees.md`). La configuration structurelle (types de documents, tags) est hors périmètre ici — elle est déclarative et reconstructible via `provisioning/apply.py`, pas besoin de la sauvegarder en tant que blob.

## 1. Qu'est-ce qui est vraiment critique ?

| Donnée | Volume | À sauvegarder ? |
|---|---|---|
| Documents originaux + archivés (PDF/images) | `media` | **Oui — critique, irremplaçable** (c'est le contenu réel des documents) |
| Métadonnées, texte OCR indexé, tags/types associés à chaque document, custom fields | `pgdata` (Postgres) | **Oui — critique** (sans ça, `media` n'est qu'un tas de fichiers non retrouvables) |
| Types de documents / tags "définis" (la taxonomie elle-même, pas leur usage) | — | Non par ce mécanisme — déclarée dans `provisioning/seed.json`, reconstructible par `apply.py` (voir `README.md`) |
| Modèle de classification "Auto" entraîné, index de recherche, miniatures | `data` | Non critique — régénérable à partir de `pgdata`/`media` (réindexation, réentraînement), mais long à reconstruire sur un gros volume de documents : sauvegarder si simple, sans en faire une priorité |
| File de tâches en cours | `redisdata` (broker) | Non — purement transitoire, aucune perte réelle si vidé |
| Secrets d'infra (`.env` : mots de passe DB, `PAPERLESS_SECRET_KEY`, admin) | hors volume Docker | Hors périmètre de ce mécanisme (voir §6) |

## 2. Outils retenus

- **`document_exporter`** (commande de gestion intégrée à Paperless-ngx) plutôt qu'un dump brut de `pgdata` : produit un export portable (fichiers + manifeste JSON décrivant métadonnées/tags/types/relations), indépendant du moteur de base de données, et c'est la méthode de sauvegarde officiellement recommandée par le projet — un `pg_dump` seul ne suffit pas à restaurer proprement sans rejouer aussi les fichiers de `media`.
- **restic** + **rclone** (vers Google Drive) pour transporter/chiffrer/versionner cet export — même choix que `bitwarden/_plan/plan-sauvegarde.md`, pour rester cohérent, mais implémenté indépendamment ici (aucun script ni config partagée entre les deux services, cf. `protocole-donnees.md`).
- Packaging cohérent avec l'existant : un service `sidecar-backup` dédié dans `compose.yaml` (même esprit que les sidecars déjà utilisés dans `bitwarden`/`edge`), pas encore ajouté.

## 3. Déroulé d'une sauvegarde (quotidienne)

1. `docker compose exec paperless document_exporter ../export` — régénère l'export complet (fichiers + manifeste) dans le dossier `export/` déjà monté (bind mount, voir `compose.yaml`).
2. `restic backup export/` vers le dépôt restic (Google Drive via rclone).
3. `restic forget --prune` avec une politique de rétention (proposition : 14 quotidiennes + 8 hebdomadaires + 6 mensuelles — à ajuster selon le volume réel de documents).
4. Journalisation du succès/échec dans les logs du conteneur.
5. Fréquence : une fois par jour suffit (les documents s'accumulent, ils ne changent pas plusieurs fois par jour une fois archivés).

## 4. Secrets et point de vigilance

- Le mot de passe du dépôt restic (`RESTIC_PASSWORD`) est **le** secret critique : sans lui, la sauvegarde chiffrée est définitivement irrécupérable. À conserver hors de la machine qui héberge paperless, hors du dépôt lui-même (même logique que pour bitwarden).
- Le remote Google Drive rclone peut être **partagé** avec celui déjà configuré pour bitwarden (même compte Drive, dossier différent) — ce n'est pas une ressource inter-services au sens du `CLAUDE.md` racine (c'est une destination de stockage externe, pas une ressource applicative partagée entre les deux services), mais chaque service garde son propre dépôt restic (mot de passe différent, contenu différent), pour ne pas coupler leur cycle de vie.
- Contrairement à bitwarden (contenu chiffré côté client), le contenu des documents Paperless n'est **pas chiffré avant stockage** — la sauvegarde chiffrée par restic est donc la seule protection du contenu réel des documents (potentiellement sensibles : bulletins de salaire, MDPH...) une fois hors de la machine locale.

## 5. Restauration — à tester au moins une fois avant de faire confiance au dispositif

1. `restic restore latest --target /chemin/restauration` (depuis le dépôt Google Drive).
2. Démarrer une instance paperless neuve (nouveau volume `pgdata`/`media` vides) via `docker compose up -d`.
3. `docker compose exec paperless document_importer ../restauration` — réimporte les documents et toutes leurs métadonnées/tags/types depuis l'export restauré.
4. Rejouer `provisioning/apply.py` pour s'assurer que la taxonomie déclarée est bien en place (normalement déjà réimportée par l'étape 3, `apply.py` sert de garde-fou).
5. Vérifier l'accès aux documents et la recherche plein texte.
6. Ce test complet doit être fait une première fois en conditions contrôlées (pas sur le volume de production) avant de considérer le dispositif fiable.

## 6. Hors périmètre (assumé)

- `.env` (secrets d'infra) n'est pas sauvegardé par ce mécanisme, pour ne pas dupliquer un secret sensible dans le dépôt de sauvegarde lui-même — à gérer séparément.
- Pas d'alerting temps réel en cas d'échec pour l'instant (log uniquement).

## 7. Roadmap d'implémentation

1. Créer/réutiliser le remote Google Drive dans rclone (manuel, une fois — dossier dédié à paperless, distinct de celui de bitwarden).
2. `restic init` sur un dépôt dédié (`rclone:gdrive:paperless-backups`).
3. Ajouter le service `sidecar-backup` à `compose.yaml` (image Alpine + `restic` + `rclone`, boucle quotidienne appelant `document_exporter` puis `restic backup`).
4. Premier backup réel + test de restauration complet dans un environnement de test (§5).
5. Documenter la procédure de restauration testée dans ce fichier (mise à jour de ce plan avec le résultat réel, comme fait pour bitwarden).

**Statut (2026-08-12) : décision explicite de ne pas implémenter ce mécanisme.** La source brute des documents est déjà sur Google Drive (l'archive immuable, cf. `_plan/architecture.md`) — `media`/`pgdata` ne sont qu'une couche d'indexation/enrichissement reconstructible en réingérant depuis Drive (moyennant un nouveau passage d'OCR/classification, cf. `_plan/plan.md` phases 1+). Contrairement à bitwarden (`_plan/plan-migration-edge.md` — le vault n'a pas de copie ailleurs), sauvegarder `media`/`pgdata` ici dupliquerait une protection qui existe déjà côté Drive, pour un gain marginal (éviter de réingérer/reclasser). Ce plan reste écrit pour référence si cette analyse change (ex. si le volume de RAD/LAD enrichi devient coûteux à reconstruire), mais n'est plus la prochaine étape.
