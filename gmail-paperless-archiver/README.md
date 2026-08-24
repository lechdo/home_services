# gmail-paperless-archiver

Gmail Add-on personnel : bouton « Archiver dans Paperless » dans le panneau latéral d'un email ouvert. Voir `CLAUDE.md` pour l'architecture et `_plan/plan.md` pour le détail des phases.

## Déploiement (usage personnel, non publié)

### 1. Créer le projet Apps Script

- Aller sur [script.google.com](https://script.google.com) → **Nouveau projet**.
- Renommer le projet (ex. `Paperless Archiver`).
- Dans l'éditeur, ouvrir **Project Settings** (roue crantée) → cocher *Show "appsscript.json" manifest file in editor*.
- Remplacer le contenu de `appsscript.json` par celui de `src/appsscript.json` de ce dossier.
- Remplacer le contenu de `Code.gs` par celui de `src/Code.gs` de ce dossier (ou créer un fichier du même nom).

*(Alternative : utiliser [`clasp`](https://github.com/google/clasp) pour pousser `src/` directement — `clasp create --type standalone`, puis `clasp push`. Non fait ici car nécessite une authentification interactive dans un navigateur.)*

### 2. Configurer l'ID du dossier Drive cible

- Ouvrir le dossier Drive `controlled_chaos` (celui déjà utilisé par `paperless/`, cf. `paperless/.env` → `GDRIVE_REMOTE_PATH=gdrive:controlled_chaos`).
- Copier son ID depuis l'URL : `https://drive.google.com/drive/folders/<ID>`.
- Dans l'éditeur Apps Script : **Project Settings** → **Script Properties** → **Add script property** → clé `PAPERLESS_DRIVE_FOLDER_ID`, valeur = l'ID copié.

### 3. Installer l'add-on sur son propre compte Gmail

- Dans l'éditeur : **Deploy** → **Test deployments** → **Install add-on**.
- Autoriser l'application quand Google le demande (l'écran « Google n'a pas vérifié cette application » est normal pour un script personnel non publié — cliquer *Avancé* → *Accéder à [nom du projet] (non sécurisé)*).
- Ouvrir Gmail, ouvrir un email : l'icône de l'add-on doit apparaître dans le panneau latéral droit, avec le bouton « Archiver dans Paperless ».

### 4. Vérifier le pipeline complet

1. Ouvrir un mail de test, cliquer « Archiver dans Paperless ».
2. Vérifier que le `.eml` apparaît dans le dossier Drive `controlled_chaos`.
3. Attendre le prochain cycle du sidecar `rclone` de `paperless/` (~5 min, voir `paperless/README.md`).
4. Vérifier que le document apparaît dans l'UI Paperless, OCR fait.

## Limites connues

- Un seul mail à la fois (pas de multi-sélection — limitation de la plateforme Gmail Add-ons, voir `_plan/plan.md`).
- Pas de déduplication : archiver deux fois le même mail crée deux fichiers `.eml` distincts dans Drive (l'ID du message est dans le nom de fichier, donc traçable).
