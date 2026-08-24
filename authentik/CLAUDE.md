# Service authentik — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge [Authentik](https://goauthentik.io/), un fournisseur SSO / forward-auth : il ajoute un écran de connexion unique devant potentiellement tous les autres services exposés par `edge`, **sauf bitwarden** (décision explicite de l'utilisateur, cf. `_plan/plan.md`).

Voir `_plan/plan.md` avant toute implémentation — rien n'est encore codé, ce dossier ne contient pour l'instant que le plan.

## Rôle du service

- Héberger le serveur Authentik (`server` + `worker`), sa base Postgres et son cache Redis — un `compose.yaml` autonome, comme tout autre service de ce dépôt (pas de base/réseau partagé avec qui que ce soit).
- Exposer deux choses en HTTP, toutes deux publiées comme un port hôte standard (contrat d'intégration `edge`, rien de plus) :
  1. L'interface web Authentik elle-même (login, admin), routée par `edge` sous un sous-domaine dédié (`auth`).
  2. Un point de vérification HTTP (« outpost » embarqué, pas de conteneur outpost séparé) que `edge` interroge en sous-requête (`auth_request` nginx) avant de laisser passer une requête vers un service protégé.
- Ne connaît rien d'`edge`, comme tout backend : `edge` l'appelle en HTTP, dans les deux sens d'usage ci-dessus, exactement comme il appellerait n'importe quel autre service.

## Ce que ce service NE fait PAS

- **bitwarden reste exclu explicitement** : aucun `auth_request` ajouté à `nginx/conf.d/bitwarden.conf`. Raison : Vaultwarden a déjà son propre mécanisme d'authentification (mot de passe maître, 2FA), consommé aussi par des apps mobiles/extensions qui n'attendent pas une redirection SSO — ajouter Authentik devant casserait ces clients.
- **Ne protège pas le port de jeu Minecraft (TCP 25565)** : forward-auth est un mécanisme HTTP (`auth_request`), inapplicable à un flux TCP brut de protocole de jeu. Seul le panel web de gestion Minecraft (HTTP) peut être protégé par ce service — le port de jeu reste ouvert comme avant, limite technique et non un oubli.

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire**, comme tout service de ce dépôt : `compose.yaml` propre (`server`, `worker`, `postgres`, `redis`), aucune ressource partagée avec un autre service.
- **Provisioning déclaratif** : les objets structurels créés dans Authentik (applications, providers proxy, groupes, policies) doivent être déclarés via les **Blueprints** natifs d'Authentik (fichiers YAML), commités dans `provisioning/`, appliqués par le mécanisme de discovery d'Authentik lui-même — pas de clic-ouvrage non reproductible en cas de perte de la base. Conforme à la règle du `CLAUDE.md` racine sur `provisioning/`.
- **Données utilisateur critiques non déclarables** : les comptes utilisateurs (identifiants, mots de passe hashés) et les sessions actives vivent dans Postgres et ne sont pas capturés par les blueprints — nécessite un `_plan/plan-sauvegarde.md` testé (règle racine `protocole-donnees.md`) avant tout usage réel prolongé.
- **Risque de verrouillage (lockout)** : ce service devient un point de passage obligé pour tous les services protégés. Une panne, une mauvaise config, ou une perte de la base Authentik peut couper l'accès à tout ce qui est derrière — voir la question ouverte dans `_plan/plan.md` sur un mécanisme de secours.
- **Hébergé sur le second serveur physique (`192.168.1.109`)**, comme paperless/actual-budget/minecraft/music_manager (décidé le 2026-08-23) — ce serveur reste désormais **allumé en permanence** (changement de décision concomitant, cf. `_plan/plan.md`), précisément pour ne pas rendre les services protégés (dont `task`/vikunja, qui tourne sur le Pi toujours allumé) indisponibles chaque fois que ce serveur aurait été éteint.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases, y compris les questions ouvertes à trancher avec l'utilisateur avant implémentation.
- `edge/CLAUDE.md` et `edge/_plan/architecture.md` — contrat d'intégration edge (ce service s'y conforme comme tout autre backend).
- `edge/_plan/plan.md` phase 15 — migration dynv6 en cours, dont dépend l'introduction de ce service (sous-domaines `auth` + services protégés doivent exister côté dynv6 avant/pendant ce travail).
