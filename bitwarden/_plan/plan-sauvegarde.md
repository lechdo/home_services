# Plan de sauvegarde — service bitwarden

Répond à BF-8 (« permettre la sauvegarde et la restauration des données du vault indépendamment du reste de l'infrastructure »). Périmètre : données stateful critiques uniquement, avec Google Drive comme seule destination disponible actuellement.

## 1. Qu'est-ce qui est vraiment critique ?

| Donnée | Volume/fichier | À sauvegarder ? |
|---|---|---|
| Base des comptes/items (chiffrés côté client) | `vaultwarden_data/db.sqlite3` | **Oui** — critique |
| Pièces jointes, Sends | `vaultwarden_data/attachments/`, `vaultwarden_data/sends/` | **Oui** — critique |
| Config, clés de signature de session | `vaultwarden_data/config.json`, `vaultwarden_data/rsa_key*.pem` | **Oui** — critique |
| Cache d'icônes | `vaultwarden_data/icon_cache/` | Non — régénérable, pas une donnée utilisateur |
| Certificat TLS + état acme.sh | `bitwarden_certs`, `bitwarden_acme_state` | Non — régénéré automatiquement par `sidecar-acme`, aucune perte réelle |
| Secrets d'infra (`.env`) | hors volume Docker | Hors périmètre de ce mécanisme (voir §6) |

Rappel rassurant : Bitwarden chiffre les items de vault côté client (architecture "zero-knowledge") avant envoi au serveur — une fuite du contenu de la sauvegarde n'exposerait pas les mots de passe en clair. Le point réellement sensible est `rsa_key.pem` (signature des sessions) et les métadonnées (emails, structure) : la sauvegarde doit donc rester chiffrée malgré tout.

## 2. Outils retenus

- **restic** : sauvegarde chiffrée, dédupliquée (n'envoie que ce qui a changé), versionnée, avec politique de rétention native — plus robuste qu'un tar+chiffrement manuel.
- **rclone** comme backend de stockage pour restic (restic n'a pas de backend Google Drive natif, mais sait déléguer à rclone, qui lui en a un).
- Packaging cohérent avec l'existant : nouveau service `sidecar-backup` dans `compose.yaml`, même esprit que `sidecar-ddns`/`sidecar-acme` (image Alpine légère, boucle interne, aucune dépendance host hors Docker — CT-6).

## 3. Déroulé d'une sauvegarde (quotidienne)

1. Snapshot cohérent de la base sqlite via l'API de backup SQLite (`sqlite3 db.sqlite3 ".backup /staging/db.sqlite3"`), plutôt qu'une copie brute du fichier — évite une sauvegarde corrompue si une écriture est en cours au moment de la copie.
2. `restic backup` du snapshot + `attachments/` + `sends/` + `config.json` + `rsa_key*.pem`, vers le dépôt restic (Google Drive via rclone).
3. `restic forget --prune` avec une politique de rétention (proposition : 14 quotidiennes + 8 hebdomadaires + 6 mensuelles — ajustable).
4. Journalisation du succès/échec dans les logs du conteneur (alerte email en option ultérieure, si un SMTP est configuré pour les invitations multi-utilisateurs).
5. Fréquence : une fois par jour — les mots de passe changent rarement plusieurs fois par jour, pas besoin de temps réel.

## 4. Secrets et point de vigilance n°1

- Le mot de passe du dépôt restic (`RESTIC_PASSWORD`) est **le** secret critique : sans lui, les sauvegardes chiffrées sont définitivement irrécupérables, y compris pour toi.
- Il ne doit **jamais** exister uniquement sur le Raspberry Pi : si le Pi est perdu/détruit, il ne faut pas perdre en même temps la seule copie du mot de passe permettant de restaurer depuis Google Drive. À conserver aussi ailleurs, hors du Pi et hors du vault lui-même (risque de "l'œuf et la poule" si le mot de passe n'existe que dans le vault qu'il protège) — par exemple noté physiquement, ou dans un gestionnaire de secrets déjà utilisé par ailleurs.
- Configuration Google Drive côté rclone : nécessite une autorisation OAuth interactive une seule fois (`rclone config`) — étape manuelle à faire par toi (navigateur), du même type que la création du compte DuckDNS.

## 5. Restauration — à tester au moins une fois avant de faire confiance au dispositif

1. `restic restore latest --target /chemin/restauration` (depuis le dépôt Google Drive).
2. Recopier le snapshot sqlite restauré en tant que `db.sqlite3` dans un nouveau volume `vaultwarden_data`, avec `attachments/`, `sends/`, `config.json`, `rsa_key*.pem`.
3. Démarrer vaultwarden sur ce volume restauré et vérifier l'accès aux comptes/items.
4. Ce test de restauration complet doit être fait une première fois en conditions contrôlées (volume de test, pas le volume de production) avant de considérer le dispositif fiable.

## 6. Hors périmètre (assumé)

- Le fichier `.env` (secrets d'infra : `ADMIN_TOKEN`, `DUCKDNS_TOKEN`, `RESTIC_PASSWORD` lui-même) n'est pas sauvegardé par ce mécanisme — ce n'est pas une "donnée utilisateur" au sens de BF-8, et l'inclure créerait un risque de fuite supplémentaire dans le dépôt de sauvegarde lui-même. À gérer séparément (ex: noté à part, comme le mot de passe restic).
- Pas d'alerting temps réel en cas d'échec pour l'instant (log uniquement) — amélioration possible plus tard.

## 7. Roadmap d'implémentation

1. **Bloqué sur une action manuelle de l'utilisateur** : créer le remote Google Drive dans rclone. Nécessite une autorisation OAuth interactive dans un vrai navigateur — ne peut pas être fait par Claude (pas d'accès navigateur, et l'octroi d'un accès OAuth à un compte Google reste un geste que l'utilisateur doit faire lui-même). **Fait (2026-08-12)** : `scripts/authorize-gdrive.sh` prépare ce geste au strict minimum irréductible (suivre le lien, se connecter) — le script récupère lui-même le token et écrit `rclone.conf`, sans copier-coller manuel. Voir `README.md`, section "Sauvegarde".
2. **Fait (2026-08-12)** : `RESTIC_PASSWORD` généré et placé dans `.env` — **à copier ailleurs par l'utilisateur avant le premier backup réel** (perdu = sauvegardes définitivement irrécupérables, cf. §4).
3. **Fait (2026-08-12)** : service `sidecar-backup` ajouté à `compose.yaml` (image Alpine + `restic`/`rclone`/`sqlite` installés au démarrage, boucle quotidienne : snapshot sqlite cohérent, `restic backup`, `restic forget --prune`). Derrière le profil Compose `backup`, ne démarre pas tant que `rclone.conf` n'existe pas.
4. **Fait (2026-08-12)** : `scripts/setup-backup.sh` automatise et rend idempotent le reste de la mise en place (activation du profil `backup`, `restic init` uniquement si le dépôt n'est pas déjà initialisé, démarrage de `sidecar-backup`) — prêt à être relancé tel quel sur la machine cible finale (Raspberry Pi) une fois l'étape 1 faite là-bas.
5. `restic init` sur le dépôt (`rclone:gdrive:vaultwarden-backups`) — **en attente de l'étape 1**, mais désormais automatisé par `setup-backup.sh` (plus de commande manuelle à retenir).
6. Premier backup réel + test de restauration complet dans un volume de test (§5) — **en attente de l'étape 1**.
7. Documenter le résultat du test de restauration dans ce fichier (mise à jour de ce plan avec le résultat réel).
