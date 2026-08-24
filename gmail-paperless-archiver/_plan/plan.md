# Plan — gmail-paperless-archiver

## Décision de conception (2026-08-21)

Demande initiale : un bouton « Archiver dans Paperless » qui apparaît quand on sélectionne **un ou plusieurs** mails dans Gmail.

Vérification faite sur la documentation officielle Google Workspace Add-ons (2026-08) : les `contextualTriggers` d'un Gmail Add-on ne se déclenchent que sur un **message ouvert individuellement** (`unconditional` trigger dans `gmail.contextualTriggers`). Il n'existe pas d'API publique documentée permettant d'ajouter une action personnalisée sur une multi-sélection de mails dans la liste Gmail.

Deux options réalistes ont été présentées à l'utilisateur :
1. Bouton add-on, un mail à la fois (contextual trigger classique).
2. Label Gmail + trigger Apps Script périodique, pour traiter un lot de mails sélectionnés en une fois.
3. Les deux combinés.

**Choix retenu : option 1** (bouton add-on, un mail à la fois). Le traitement par lot (option 2/3) reste documenté en phase 3 ci-dessous si le besoin redevient prioritaire, mais n'est pas implémenté.

## Phase 0 — Création du projet Apps Script

- Créer un projet Apps Script **standalone** (script.google.com → Nouveau projet), pas lié à un Sheet/Doc — un Gmail Add-on n'a pas besoin d'être bound à un fichier.
- Copier `src/appsscript.json` (manifeste) et `src/Code.gs` (logique) dans l'éditeur, ou déployer via `clasp` (voir README à la racine de ce service pour la procédure détaillée).
- Repérer l'ID du dossier Drive `controlled_chaos` (celui déjà utilisé par `paperless/`, cf. `paperless/.env` → `GDRIVE_REMOTE_PATH=gdrive:controlled_chaos`) : ouvrir le dossier dans Drive, copier l'ID dans l'URL (`https://drive.google.com/drive/folders/<ID>`).
- Dans l'éditeur Apps Script : Project Settings → Script Properties → ajouter `PAPERLESS_DRIVE_FOLDER_ID` = cet ID. Ne jamais coder cet ID en dur dans `Code.gs`.

**Statut** : à faire manuellement par l'utilisateur (geste unique, comme l'autorisation OAuth Drive pour `paperless/`).

## Phase 1 — Implémentation du bouton (fait, code dans `src/`)

- `onGmailMessageOpen(e)` : contextual trigger, affiche une carte avec le sujet du mail et un bouton « Archiver dans Paperless ».
- `archiveToPaperless(e)` : au clic, récupère le contenu brut du message (`GmailMessage.getRawContent()` — RFC 822 complet, pièces jointes incluses), crée un blob `message/rfc822`, et le dépose dans le dossier Drive `controlled_chaos` (`DriveApp.getFolderById(...).createFile(blob)`).
- Nom de fichier : `<date>_<heure>_<sujet-slugifié>_<messageId>.eml` — l'ID du message garantit l'unicité même si deux mails ont un sujet identique.
- Notification de confirmation (`CardService.newNotification`) après dépôt réussi.

## Phase 2 — Déploiement personnel (test) et validation

- Déployer le projet en mode **Test deployments** (Apps Script → Deploy → Test deployments → Install add-on), pas de publication au Google Workspace Marketplace (usage strictement personnel, un seul utilisateur).
- Accepter l'écran de consentement OAuth (« Google n'a pas vérifié cette application ») — normal pour un script personnel non publié, même geste que pour les autres autorisations manuelles du dépôt (Drive `paperless/`, Bitwarden).
- Test de bout en bout : ouvrir un mail réel dans Gmail, cliquer « Archiver dans Paperless », vérifier que le `.eml` apparaît dans `controlled_chaos` sur Drive, puis (après le prochain cycle `sidecar-gdrive-sync`, ~5 min) qu'il apparaît dans Paperless avec l'OCR fait.
- **Objectif de sortie de phase** : un mail archivé via le bouton apparaît dans Paperless sans intervention manuelle après le clic initial.

**Statut** : à faire par l'utilisateur après la phase 0.

## Phase 3 — (Non retenue pour l'instant) Traitement par lot

Si le besoin de traiter plusieurs mails sélectionnés d'un coup redevient prioritaire :
- Ajouter un label Gmail dédié (ex. `Paperless/À archiver`), applicable en masse via la sélection multiple native de Gmail (case à cocher + menu labels).
- Ajouter un trigger Apps Script `time-driven` (toutes les 5-10 min) qui liste les threads portant ce label (`GmailApp.search('label:paperless-a-archiver')`), exporte chaque message en `.eml`, le dépose dans `controlled_chaos`, puis retire le label (et en ajoute un `Paperless/Archivé` pour trace).
- Point de vigilance à traiter si implémenté : idempotence (ne pas réarchiver un mail déjà traité si le trigger tourne pendant qu'un lot est en cours) et gestion des erreurs partielles (un mail qui échoue ne doit pas bloquer les suivants).

Non implémenté : pas de code correspondant dans `src/` tant que cette phase n'est pas activée.
