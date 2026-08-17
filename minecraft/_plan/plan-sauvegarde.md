# Plan de sauvegarde — minecraft

Cf. `protocole-donnees.md` (racine) : les mondes Minecraft (`maps/<nom>/`) sont des données utilisateur réelles, non déclarables — ce n'est pas de la config d'infrastructure reproductible, donc pas de `provisioning/` ici, uniquement ce plan.

**Statut : écrit, pas encore implémenté.** À faire une fois le service en place (phase 5 de `plan.md`).

## Quoi sauvegarder

- Tous les dossiers sous `maps/` (pas seulement la map actuellement active — les maps inactives contiennent aussi des mondes réels, pas juste des fichiers de config).

## Avec quel outil

À définir à l'implémentation, mais dans le même esprit que bitwarden (`restic` + `rclone`) sans partager sa config — ce service doit avoir ses propres identifiants/destination, indépendants (cf. principe d'indépendance entre services, `protocole-donnees.md`). Alternative plus simple si le volume de données le permet : `tar` + rotation locale sur un disque distinct, sans dépendance à un compte cloud.

## Fréquence

À définir selon la fréquence de jeu réelle — proposition de départ : sauvegarde quotidienne si le serveur a tourné dans la journée (pas de sauvegarde d'un monde inchangé), rétention à définir (ex. 14 jours).

## Procédure de restauration

À écrire et **tester au moins une fois** avant de considérer cette phase faite (exigence du protocole racine) — restaurer un dossier de map depuis la sauvegarde et vérifier que le serveur démarre correctement dessus.
