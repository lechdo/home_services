# Protocole — persistance et mise à jour des données de service

Complète le `CLAUDE.md` racine : règle commune à tous les services, indépendante de leur stack technique.

## Le problème

Une fois un service démarré, deux types de données apparaissent, qu'il faut traiter différemment :

1. **Configuration structurelle** créée via l'API/l'UI du service (types de documents, tags, règles...) — ce n'est pas du contenu utilisateur, c'est de la config, mais elle n'existe *que* dans la base du service tant qu'elle n'est pas déclarée ailleurs. Exemple concret : les types de documents et tags Paperless créés à la main via l'API le 2026-08-12 n'existaient qu'en base — perdus si le volume disparaît, irreproductibles sur une nouvelle machine sans relire l'historique de conversation.
2. **Données utilisateur réelles**, non déclarables (contenu de mots de passe chiffrés, documents scannés, base complète accumulée dans le temps). Celles-ci ne peuvent pas être "codifiées" — elles doivent être sauvegardées/restaurées.

Confondre les deux mène soit à tout traiter comme sauvegarde opaque (on perd la capacité de rejouer/faire évoluer la config proprement), soit à tout traiter comme code (impossible pour du contenu utilisateur réel).

## Principe

- **Configuration structurelle → déclarée en fichiers versionnés + script idempotent.** Un service qui a ce besoin maintient un dossier `provisioning/` avec un fichier de seed (état désiré) et un script `apply` qui le réconcilie avec l'état réel du service via son API : crée ce qui manque, met à jour ce qui a changé, ne touche jamais à ce qui est déjà conforme. La base du service (Postgres, sqlite...) devient un **état dérivé**, reconstructible en rejouant `apply` — pas la source de vérité.
- **Données utilisateur réelles → sauvegarde/restauration documentée.** Un service qui a des données critiques non déclarables maintient un `_plan/plan-sauvegarde.md` : quoi sauvegarder, avec quel outil, quelle fréquence, et une procédure de restauration **testée** au moins une fois.
- **Aucune destruction implicite.** `apply` ne supprime jamais une entrée absente du fichier de seed mais présente en base (pas de purge automatique) — une suppression volontaire est un geste explicite, pas un effet de bord d'un `apply` de routine.
- **Ce protocole ne remplace pas Docker Compose**, qui reste la source de vérité pour l'infrastructure (conteneurs, réseaux, volumes). Il couvre ce que Compose ne capture pas : l'état applicatif créé après coup via une API/UI.

## Indépendance entre services (rappel du principe racine)

Chaque script `provisioning/apply.*` et chaque procédure de sauvegarde ne parle **qu'à l'API et aux volumes de son propre service** (typiquement `127.0.0.1:<port>`), jamais à un autre service, jamais à une ressource partagée. Un service doit pouvoir être installé, mis à jour, sauvegardé et restauré sur une machine où aucun autre service du dossier racine ne tourne. Rien n'est mutualisé entre `provisioning/apply.*` de deux services différents, même s'ils se ressemblent — chaque service a sa propre copie, indépendante.

## Convention de structure par service

```
<service>/
  provisioning/            # SI le service a une config structurelle créée via API/UI
    seed.json              # état désiré, versionné
    apply.py               # idempotent : crée / met à jour, ne supprime jamais
  _plan/
    plan-sauvegarde.md     # SI le service a des données utilisateur critiques non déclarables
```

Les deux dossiers sont indépendants l'un de l'autre : un service peut n'avoir besoin que de l'un, des deux, ou d'aucun (rien à déclarer, rien de critique à sauvegarder).

## Statut par service (à tenir à jour à chaque changement)

| Service | `provisioning/` | `_plan/plan-sauvegarde.md` |
|---|---|---|
| **paperless** | Types de documents + tags — **implémenté** (`provisioning/seed.json` + `apply.py`) | Écrit puis **décision explicite de ne pas implémenter (2026-08-12)** : la source brute des documents vit déjà sur Google Drive, `media`/`pgdata` sont reconstructibles depuis Drive — dupliquer une sauvegarde ici serait redondant |
| **bitwarden** | Non applicable — pas de taxonomie structurelle, uniquement des données utilisateur opaques (items chiffrés) | **Implémenté (2026-08-12)**, restic + rclone vers Google Drive — `sidecar-backup` dans `compose.yaml`, `RESTIC_PASSWORD` généré, **bloqué sur l'autorisation OAuth Google Drive** (geste manuel de l'utilisateur, voir `bitwarden/README.md`) |
| **edge** | Non applicable — le routage (nginx `conf.d/*.conf`) et les sous-domaines (`.env`) sont déjà des fichiers versionnés, pas de config créée via API/UI à déclarer séparément | Non applicable — rien d'irremplaçable (certificats et état acme.sh régénérables à volonté) |
| **actual-budget** | Non applicable — catégories/comptes budgétaires font partie des données utilisateur elles-mêmes (`user-files/*.sqlite`), pas d'une config d'infrastructure créée via API à déclarer séparément | Écrit (`_plan/plan-sauvegarde.md`), **non implémenté (2026-08-12)** par décision explicite : volume `data` nommé et documenté pour permettre une sauvegarde plus tard, mécanisme (restic+rclone, calqué sur bitwarden) à activer quand demandé — rien n'est régénérable ici, à la différence de paperless |

## Quand créer un nouveau `provisioning/`

Dès qu'un service expose une notion de catégorie/taxonomie/règle configurée via son API ou son UI plutôt que par un fichier de `compose.yaml` (types de documents, workflows, custom fields, organisations, permissions...). Si la seule "donnée" est du contenu utilisateur opaque (mots de passe, documents), `provisioning/` n'a pas de sens — seul `plan-sauvegarde.md` s'applique.
