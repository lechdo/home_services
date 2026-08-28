# Service outline — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge [Outline](https://www.getoutline.com/), un wiki/base de connaissances personnel(le) auto-hébergé(e).

Voir `_plan/plan.md` avant toute implémentation — rien n'est encore codé, ce dossier ne contient pour l'instant que le plan.

## Rôle du service

- Héberger le serveur Outline, sa base Postgres et son cache Redis — un `compose.yaml` autonome, comme tout autre service de ce dépôt (pas de base/réseau partagé avec qui que ce soit).
- Exposer un unique port HTTP sur l'hôte, routé par `edge` sous `doc.jvince.dynv6.net` (contrat d'intégration standard, `edge/CLAUDE.md` + `edge/_plan/architecture.md`). Ne connaît rien d'`edge`.
- Déléguer l'authentification à Authentik en SSO applicatif réel (OIDC), pas seulement en forward-auth devant — même principe que `vikunja`/`paperless`/`actual-budget` (`authentik/_plan/plan.md` phase 6).

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : `compose.yaml` propre (serveur Outline, Postgres, Redis), aucune ressource partagée avec un autre service.
- **Hébergé sur le second serveur physique (`192.168.1.109`)**, comme paperless/actual-budget/minecraft/music_manager/authentik — ce serveur reste allumé en permanence (décision déjà actée pour authentik, `authentik/CLAUDE.md`). Port publié sur l'IP LAN de cette machine, pas `127.0.0.1` (même schéma que les autres services de ce serveur, `edge` y accède via le réseau local).
- **Comptes SSO** : les deux seuls comptes Authentik existants à ce jour, `julien` et `virginie`, doivent pouvoir se connecter à Outline via OIDC. Comme ce sont aujourd'hui les deux seuls comptes de tout l'Authentik, aucune restriction (`policybinding`) supplémentaire n'est a priori nécessaire — l'accès par défaut à une Application Authentik sans binding est déjà limité à ces deux comptes (même pattern que `paperless`/`vikunja`, à la différence d'`actual-budget` qui restreint volontairement à un seul compte). Voir `_plan/plan.md` pour le détail.
- **Données utilisateur critiques non déclarables** : le contenu réel du wiki (documents, pièces jointes) vit dans Postgres (et dans le stockage de fichiers choisi, cf. `_plan/plan.md`) — nécessite un `_plan/plan-sauvegarde.md` testé avant tout usage réel prolongé (règle racine `protocole-donnees.md`), pas de source externe reconstructible comme pour `paperless` (Google Drive).
- **Pas de `provisioning/` envisagé pour l'instant** : les collections/groupes créés dans Outline sont du contenu utilisateur réel, pas une taxonomie structurelle générique à rejouer sur une nouvelle instance (même raisonnement que les comptes Navidrome de `music_manager`) — à réévaluer si ça change.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases, y compris les questions ouvertes à trancher avec l'utilisateur avant implémentation.
- `edge/CLAUDE.md` et `edge/_plan/architecture.md` — contrat d'intégration edge (ce service s'y conforme comme tout autre backend).
- `authentik/CLAUDE.md` et `authentik/_plan/plan.md` phase 6 — pattern d'intégration OIDC applicatif déjà suivi pour vikunja/paperless/actual-budget, à répliquer ici.
