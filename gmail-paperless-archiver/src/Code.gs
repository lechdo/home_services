/**
 * Gmail Add-on : ajoute un bouton "Archiver dans Paperless" quand un email
 * est ouvert. Au clic, exporte le mail en .eml (RFC 822 brut, pièces jointes
 * incluses) et le dépose dans le dossier Google Drive "controlled_chaos",
 * déjà synchronisé vers Paperless par le service `paperless/` (rclone).
 *
 * Voir CLAUDE.md et _plan/plan.md de ce dossier pour le contexte
 * d'architecture (pourquoi Drive et pas l'API Paperless directement).
 */

var PAPERLESS_FOLDER_PROPERTY = 'PAPERLESS_DRIVE_FOLDER_ID';

/**
 * Contextual trigger : appelé par Gmail à chaque ouverture d'un message.
 */
function onGmailMessageOpen(e) {
  GmailApp.setCurrentMessageAccessToken(e.gmail.accessToken);
  var message = GmailApp.getMessageById(e.gmail.messageId);

  var section = CardService.newCardSection()
    .addWidget(
      CardService.newDecoratedText()
        .setTopLabel('Sujet')
        .setText(message.getSubject() || '(sans sujet)')
        .setWrapText(true)
    )
    .addWidget(
      CardService.newTextButton()
        .setText('Archiver dans Paperless')
        .setOnClickAction(CardService.newAction().setFunctionName('archiveToPaperless'))
    );

  var card = CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('Paperless Archiver'))
    .addSection(section)
    .build();

  return [card];
}

/**
 * Handler du clic sur le bouton : exporte le message ouvert en .eml et le
 * dépose dans le dossier Drive "controlled_chaos".
 */
function archiveToPaperless(e) {
  GmailApp.setCurrentMessageAccessToken(e.gmail.accessToken);
  var message = GmailApp.getMessageById(e.gmail.messageId);

  var folder = getPaperlessFolder_();
  var blob = Utilities.newBlob(message.getRawContent(), 'message/rfc822', buildFileName_(message));
  folder.createFile(blob);

  return CardService.newActionResponseBuilder()
    .setNotification(
      CardService.newNotification().setText('Archivé dans Paperless (controlled_chaos).')
    )
    .build();
}

/**
 * Résout le dossier Drive cible depuis les propriétés du script.
 * L'ID doit être configuré manuellement une fois (Project Settings > Script
 * Properties) — jamais codé en dur, voir _plan/plan.md phase 0.
 */
function getPaperlessFolder_() {
  var folderId = PropertiesService.getScriptProperties().getProperty(PAPERLESS_FOLDER_PROPERTY);
  if (!folderId) {
    throw new Error(
      'Propriété de script "' + PAPERLESS_FOLDER_PROPERTY + '" manquante. ' +
      'Configure-la avec l\'ID du dossier Drive "controlled_chaos" ' +
      '(Project Settings > Script Properties dans l\'éditeur Apps Script).'
    );
  }
  return DriveApp.getFolderById(folderId);
}

/**
 * Nom de fichier lisible et unique : date, sujet slugifié, ID du message
 * (garantit l'unicité même en cas de sujets identiques).
 */
function buildFileName_(message) {
  var stamp = Utilities.formatDate(message.getDate(), Session.getScriptTimeZone(), 'yyyy-MM-dd_HHmmss');
  var subjectSlug = (message.getSubject() || 'sans-sujet')
    .replace(/[\\/:*?"<>|]/g, ' ')
    .trim()
    .slice(0, 80);
  return stamp + ' - ' + subjectSlug + ' - ' + message.getId() + '.eml';
}
