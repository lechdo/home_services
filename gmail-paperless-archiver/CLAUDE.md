# gmail-paperless-archiver — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service est un **Google Apps Script** (add-on Gmail), pas un service auto-hébergé : il n'a ni `compose.yaml`, ni port HTTP, ni intégration `edge` — il tourne entièrement dans l'infrastructure Google, sur le compte Gmail personnel de l'utilisateur.

## Rôle du service

Ajoute un bouton **« Archiver dans Paperless »** dans le panneau latéral de Gmail quand un email est ouvert. Au clic, l'email complet (avec pièces jointes) est exporté au format `.eml` (RFC 822 brut) et déposé dans le dossier Google Drive `controlled_chaos`.

Ce dossier Drive est le **même** que celui déjà synchronisé vers `paperless/` (voir `paperless/.env` → `GDRIVE_REMOTE_PATH=gdrive:controlled_chaos`, et `paperless/_plan/architecture.md`). Le sidecar `rclone` de `paperless/` récupère ensuite le fichier automatiquement (poll ~5 min) et Paperless l'ingère (OCR, indexation).

## Pourquoi ne pas appeler l'API Paperless directement

L'architecture de `paperless/` pose Google Drive comme **source documentaire pure et immuable**, avec un flux strictement unidirectionnel `Drive → Paperless` (voir `paperless/_plan/architecture.md`, section « Synchronisation Google Drive »). Écrire directement dans Paperless via son API REST créerait un document qui n'existe nulle part sur Drive, cassant la propriété de reconstructibilité (« toute la base Paperless doit pouvoir être reconstruite à partir de Drive seul »).

Ce service dépose donc le `.eml` dans `controlled_chaos` exactement comme le ferait l'utilisateur en glissant un fichier dans Drive à la main — c'est le geste normal d'entrée dans le pipeline documentaire, pas une exception.

## Ce service reste autonome

- Aucun code, aucune config, aucun secret partagé avec `paperless/` : ce script ne connaît ni l'API Paperless, ni son URL, ni ses identifiants.
- Le seul point de contact avec `paperless/` est le dossier Google Drive `controlled_chaos` — une ressource **externe** au dépôt (ni base de données, ni fichier, ni variable d'environnement d'un autre service au sens du principe d'architecture racine). C'est l'équivalent d'un client externe déposant un fichier au même endroit que `rclone` va le lire, pas un couplage entre services.
- L'ID du dossier Drive cible est configuré localement dans les propriétés du script Apps Script (`PAPERLESS_DRIVE_FOLDER_ID`), jamais codé en dur ni committé.

## Caractéristiques spécifiques à ce service

- **Un seul email à la fois.** Les Gmail Add-ons ne supportent pas (vérifié sur la doc officielle, 2026-08) de déclencheur personnalisé sur une multi-sélection de mails dans la liste — seulement un `contextualTrigger` par message ouvert individuellement. Traiter plusieurs mails d'un coup nécessiterait un mécanisme différent (label Gmail + trigger Apps Script périodique) — non retenu pour l'instant, voir `_plan/plan.md` phase 3 si le besoin revient.
- **Scopes Gmail restreints** : `gmail.addons.execute` (scope de base obligatoire pour l'exécution de tout add-on Gmail) + `gmail.addons.current.message.readonly` (accès temporaire au message ouvert uniquement, jamais à toute la boîte mail) — pas de `https://mail.google.com/`.
- **Scope Drive large (`.../auth/drive`), assumé** : le scope restreint `drive.file` ne permet pas d'écrire dans un dossier préexistant que le script n'a pas créé lui-même (vérifié — comportement documenté de `drive.file`). Comme ce script n'est ni publié ni soumis à vérification Google (usage personnel, un seul utilisateur, écran de consentement « application non validée » accepté manuellement une fois), le scope large est un compromis accepté plutôt qu'une négligence. Ne pas le restreindre à `drive.file` sans revoir ce point.
- **Pas de conteneurisation, pas d'exposition Internet, pas d'`edge`** : le code s'exécute côté Google (V8 runtime d'Apps Script), pas sur l'infra du dépôt.
- **Pas de `provisioning/`** : aucune donnée structurelle créée via API à déclarer — le seul état est la propriété de script `PAPERLESS_DRIVE_FOLDER_ID` (config, pas donnée).
- **Pas de plan de sauvegarde** : ce service ne stocke rien lui-même ; le `.eml` déposé sur Drive suit le cycle de vie déjà couvert par `paperless/_plan/plan-sauvegarde.md`.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases et procédure de déploiement manuelle (clasp ou éditeur en ligne).
- `paperless/_plan/architecture.md` — pourquoi Drive est la source pure et pourquoi ce service n'écrit jamais directement dans Paperless.
