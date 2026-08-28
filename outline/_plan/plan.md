# Plan de réalisation — outline

> Décision de l'utilisateur (2026-08-28) : ajouter un wiki personnel auto-hébergé (Outline), sur le second serveur physique (`192.168.1.109`), derrière SSO Authentik, exposé sous `doc.jvince.dynv6.net`. Les deux comptes Authentik existants (`julien`, `virginie`) doivent pouvoir s'y connecter.

## Décisions déjà actées

1. **Machine hôte** : le second serveur physique (`192.168.1.109`), qui héberge déjà paperless/actual-budget/minecraft/music_manager/authentik — même raisonnement que ces services (`authentik/CLAUDE.md`), machine allumée en permanence.
2. **Sous-domaine** : `doc.jvince.dynv6.net`, routé par `edge` selon le contrat d'intégration standard (un service = un sous-domaine dédié, `edge/_plan/architecture.md`).
3. **Authentification** : SSO applicatif réel via OIDC (comme vikunja/paperless/actual-budget), pas juste le portail générique forward-auth — Outline supporte l'OIDC générique nativement (`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET`/`OIDC_AUTH_URI`/`OIDC_TOKEN_URI`/`OIDC_USERINFO_URI`/`OIDC_USERNAME_CLAIM`/`OIDC_DISPLAY_NAME`/`OIDC_SCOPES`), à vérifier précisément sur la version d'image réellement déployée (comme pour vikunja/paperless, où le chemin de callback réel différait de l'hypothèse initiale).
4. **Comptes autorisés** : `julien` et `virginie`, les deux seuls comptes Authentik existants aujourd'hui. Comme une Application Authentik sans `policybinding` est déjà ouverte à tous les comptes existants (pattern `paperless`/`vikunja`), aucune restriction supplémentaire n'est nécessaire pour satisfaire cette exigence en l'état actuel des comptes — à revoir uniquement si un compte Authentik supplémentaire (autre que julien/virginie) est créé un jour pour un autre usage et ne doit pas accéder à Outline.
5. **Port publié** : provisoirement `8090` sur `192.168.1.109` (premier port libre après `authentik` sur `8089`) — à confirmer/ajuster au moment de l'implémentation si un autre service prend ce port entre-temps.

## Questions ouvertes — tranchées le 2026-08-28 (recommandations retenues, pas encore vérifiées en conditions réelles)

1. **Stockage des fichiers/pièces jointes** : **local** (`FILE_STORAGE=local`), pas de MinIO. Confirmé par recherche que c'est aussi la valeur par défaut d'Outline désormais — cohérent avec la philosophie du dépôt (pas de composant supplémentaire si évitable). Volume Docker dédié (`storage`).
2. **Emails transactionnels (SMTP)** : pas configuré dans un premier temps (`SMTP_HOST` vide) — accès déjà limité aux deux comptes SSO existants, pas d'auto-inscription par e-mail à couvrir.
3. **Sauvegarde** (`protocole-donnees.md`) : reste à écrire, voir Phase 4 ci-dessous — pas bloquant pour un premier déploiement de test.
4. **Version d'image** : `docker.getoutline.com/outlinewiki/outline:1.9.2`, dernière stable constatée par recherche le 2026-08-28 (registre officiel recommandé par la doc outline, pas Docker Hub) — à revérifier avant le déploiement réel si du temps s'est écoulé depuis (jamais `latest`).

## Phase 0 — Squelette du service — **implémentée et déployée (2026-08-28)**

- `outline/compose.yaml` créé et déployé : `outline` (image épinglée `docker.getoutline.com/outlinewiki/outline:1.9.2`), `postgres`, `redis` — réseau Docker interne dédié (`outline_net`), aucune ressource partagée avec un autre service du dépôt.
- Volumes nommés dédiés : `postgres`, `redis`, `storage` (stockage local des fichiers, question ouverte n°1 résolue).
- **Bug réel trouvé et corrigé au premier déploiement** : `DATABASE_SSL: "false"` (variable inventée, n'existe pas côté outline) ne suffit pas — outline exige `PGSSLMODE=disable` explicitement, sinon il tente du SSL contre un `postgres:16-alpine` qui n'en a pas (boucle de redémarrage, `SequelizeConnectionError: The server does not support SSL connections`). Corrigé dans `compose.yaml`.
- `.env` réel créé directement sur `192.168.1.109` (secrets `OUTLINE_SECRET_KEY`/`OUTLINE_UTILS_SECRET`/`OUTLINE_PG_PASSWORD`/`OIDC_OUTLINE_CLIENT_SECRET` générés sur place via `openssl rand`, jamais transmis ailleurs).
- Port HTTP publié sur l'IP LAN du second serveur : `192.168.1.109:8090` (confirmé libre, pas de conflit).

## Phase 1 — Déploiement core, validation locale — **implémentée et validée (2026-08-28)**

- `docker compose up -d` exécuté réellement sur `192.168.1.109` : les 3 conteneurs (`outline`, `postgres`, `redis`) démarrent et passent `healthy`.
- Validation réelle en accès direct (`http://192.168.1.109:8090`) : `HTTP 301` (redirection forcée vers `https://doc.jvince.dynv6.net`, comportement normal d'outline avec `URL` en `https://`), logs confirmant `OIDC plugin registered` et `Listening on ... https://doc.jvince.dynv6.net`.

## Phase 2 — Sous-domaine `doc` côté edge — **implémentée et validée en production (2026-08-28)**

- `edge/nginx/conf.d/outline.conf` créé et déployé (`server_name doc.jvince.dynv6.net`, `proxy_pass http://192.168.1.109:8090`, en-têtes `Upgrade`/`Connection` inclus d'emblée pour la collaboration temps réel d'outline).
- **Écart réel constaté avec le plan initial** : le CNAME public `doc` ne pointe pas vers un enregistrement dynamique nommé `outline` mais vers un enregistrement nommé **`documentation`** (créé par l'utilisateur sous ce nom) — `DYNV6_HOSTNAMES` corrigé en conséquence (`edge/.env`, local et déployé).
- **Bug réel trouvé et corrigé** : l'utilisateur avait créé à la fois le CNAME `doc → documentation` **et** des enregistrements A/AAAA directs sur `doc` lui-même (invalide en DNS : un nom ne peut pas porter un CNAME et un autre type d'enregistrement) — l'enregistrement dynamique `documentation` proprement dit n'existait pas. Corrigé via l'API dynv6 (autorisation explicite de l'utilisateur) : création de `documentation` (A+AAAA), suppression des A/AAAA en trop sur `doc`. `sidecar-ddns-dynv6` maintient `documentation` depuis, résolution publique confirmée (`dig @1.1.1.1`).
- Certificat DNS-01 dynv6 émis (staging puis production, `openssl`/`curl -v` confirmé `O=Let's Encrypt` sans `STAGING`), `nginx -t` + `nginx -s reload` sans coupure (`reverse-proxy` resté `Up`, pas de redémarrage).
- **Validé en accès public réel** : `curl https://doc.jvince.dynv6.net/` → `HTTP 200`.

## Phase 3 — Intégration OIDC Authentik — **implémentée et validée jusqu'à la redirection (2026-08-28)**

- `authentik/provisioning/oidc-outline.yaml` déployé (Provider OAuth2/OIDC dédié + Application, pas de `policybinding` restrictif — décision n°4 ci-dessus), même pattern que `oidc-vikunja.yaml`/`oidc-paperless.yaml`/`oidc-actual.yaml`. Blueprint appliqué avec succès (`apply_blueprint` → `SUCCESS` dans les logs du `worker`).
- `authentik/compose.yaml` et `authentik/.env.example` mis à jour avec `OIDC_OUTLINE_CLIENT_SECRET` (au passage, `OIDC_VIKUNJA_CLIENT_SECRET`/`OIDC_PAPERLESS_CLIENT_SECRET`/`OIDC_ACTUAL_CLIENT_SECRET` — absents de `.env.example` jusqu'ici bien que déjà utilisés par `compose.yaml` — ont été ajoutés aussi, pour combler cet oubli documentaire pré-existant). Secret généré une fois sur `192.168.1.109`, reporté des deux côtés (`outline/.env` et `authentik/.env`), jamais affiché en clair.
- **Hypothèse confirmée par le test réel** : le callback outline est bien `/auth/oidc.callback` (`redirect_uris` du blueprint correct du premier coup, à la différence de vikunja).
- **Chaîne validée de bout en bout par curl** (pas encore par un login navigateur réel) : `https://doc.jvince.dynv6.net/auth/oidc` → `302` vers `https://auth.jvince.dynv6.net/application/o/authorize/?...&client_id=outline&redirect_uri=https://doc.jvince.dynv6.net/auth/oidc.callback` → authentik répond `302` (accepte la requête, redirige vers son flow de login). Le document de découverte `https://auth.jvince.dynv6.net/application/o/outline/.well-known/openid-configuration` confirme des endpoints identiques à ceux configurés côté outline (`OIDC_AUTH_URI`/`OIDC_TOKEN_URI`/`OIDC_USERINFO_URI`).
- **Pas testé par l'agent** : la connexion réelle (identifiants) avec les comptes `julien` et `virginie`, et le retour effectif sur Outline après login — étape interactive, à faire par l'utilisateur.
- **Reste à faire une fois la connexion validée** : retirer un éventuel forward-auth générique du bloc `doc.jvince.dynv6.net` si jamais ajouté entretemps (non fait ici, ce plan n'en a jamais ajouté — l'OIDC applicatif a été la seule couche mise en place, comme pour vikunja).

## Phase 4 — Sauvegarde — à faire

- Écrire `_plan/plan-sauvegarde.md` (quoi sauvegarder — dump Postgres + volume de stockage local si retenu —, avec quel outil, quelle fréquence) et tester une restauration au moins une fois, avant tout usage réel prolongé (`protocole-donnees.md`).

## À lire avant de travailler sur ce service

- `edge/CLAUDE.md` et `edge/_plan/architecture.md` — contrat d'intégration edge.
- `edge/_plan/plan.md` phase 15 — mécanique dynv6 (enregistrement dynamique + CNAME, `DYNV6_HOSTNAMES`).
- `authentik/_plan/plan.md` phase 6 et les blueprints `oidc-vikunja.yaml`/`oidc-paperless.yaml`/`oidc-actual.yaml` — pattern d'intégration OIDC applicatif à répliquer.
- `protocole-donnees.md` — règle sur `provisioning/` et `_plan/plan-sauvegarde.md`.
