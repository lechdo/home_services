# Plan de sauvegarde — service actual-budget

Statut : **non implémenté (2026-08-12)**. Ce fichier documente ce qui est critique et le mécanisme envisagé, pour pouvoir l'activer rapidement plus tard — conformément à la demande explicite de préparer les volumes maintenant sans encore brancher la sauvegarde.

## 1. Qu'est-ce qui est critique ?

Le volume nommé `data` (monté sur `/data`) dans son intégralité :

| Donnée | Fichier/dossier | À sauvegarder ? |
|---|---|---|
| Comptes, sessions, registre des budgets du serveur | `data/server-files/account.sqlite` | **Oui** — critique |
| Fichiers de budget réels (transactions, comptes bancaires suivis, catégories) | `data/user-files/<id>.sqlite` | **Oui** — critique, et unique : c'est la seule copie des données saisies |

Différence importante avec les autres services de ce dépôt : **rien n'est régénérable ici**. Paperless a sa source brute sur Google Drive (immuable) ; bitwarden n'a "que" des items chiffrés mais reste dans le même cas de figure de données non régénérables — donc même besoin, pas de particularité. Pour Actual Budget, il n'existe aucune source externe : perdre `data` = perdre l'historique budgétaire sans recours.

## 2. Mécanisme envisagé (à implémenter, pas encore fait)

Même schéma que `bitwarden/_plan/plan-sauvegarde.md`, adapté à ce service :

1. Snapshot cohérent de chaque fichier SQLite via l'API de backup SQLite (`sqlite3 <fichier> ".backup ..."`) plutôt qu'une copie brute, pour éviter une sauvegarde corrompue en cas d'écriture concurrente — il peut y avoir plusieurs fichiers `user-files/*.sqlite` (un par budget).
2. `restic backup` du snapshot vers un dépôt restic dédié à ce service (`RESTIC_REPOSITORY`, ex. `rclone:gdrive:actual-budget-backups` — jamais le même dépôt qu'un autre service, principe d'autonomie racine), avec `rclone` comme backend de stockage.
3. `restic forget --prune` avec une politique de rétention (proposition identique à bitwarden : 14 quotidiennes + 8 hebdomadaires + 6 mensuelles, ajustable).
4. Packaging : nouveau service `sidecar-backup` dans `compose.yaml`, derrière un profil Compose `backup` (ne démarre pas par défaut, comme chez bitwarden) — sa propre config rclone (`rclone.conf`, non committée), son propre `RESTIC_PASSWORD`.

## 3. Point de vigilance (identique à bitwarden)

`RESTIC_PASSWORD` sera **le** secret critique une fois le mécanisme activé : sans lui, les sauvegardes chiffrées sont définitivement irrécupérables. À conserver hors du Raspberry Pi et hors du service lui-même dès sa génération.

## 4. Pourquoi ce n'est pas fait maintenant

Décision explicite de l'utilisateur (2026-08-12) : préparer les volumes (nommage, contenu documenté) pour pouvoir sauvegarder *plus tard*, sans implémenter le mécanisme immédiatement. Ce fichier sert de plan prêt à exécuter — reprendre à la section 2 le jour venu, en suivant `_plan/plan.md` Phase 3.

## 5. Restauration — à tester dès l'implémentation

Comme pour bitwarden : un test de restauration complet dans un volume de test, avant de considérer le dispositif fiable. À documenter ici (mise à jour de ce fichier avec le résultat réel) une fois fait.
