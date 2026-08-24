# Plan de réalisation — service vikunja

## Phase 0 — Choix de la stack

- Image officielle `vikunja/vikunja` (mono-conteneur depuis la v0.22 : API Go + frontend statique servis par le même binaire — pas la variante historique `vikunja/api` + `vikunja/frontend` séparée, obsolète et plus lourde pour rien sur un Pi 3).
- Stockage **SQLite par défaut** (fichier `.db` sous `/app/vikunja/`), pas de Postgres/MySQL séparé — cohérent avec l'usage familial visé (quelques comptes, faible volume) et avec le choix déjà fait pour `actual-budget`. Documentation officielle confirmée : SQLite est adapté à un utilisateur unique ou une petite équipe ; Postgres/MySQL n'apporte rien tant que ce n'est pas le cas.
- Port interne du conteneur : `3456` (défaut de l'image).
- Prochain port local disponible sur l'hôte, en suivant la numérotation déjà utilisée (`8081` bitwarden, `8082` paperless, `8083` actual-budget) : **`8084`**.

## Phase 1 — `compose.yaml` minimal (le service)

- Un seul service `vikunja`, réseau `internal` dédié — pas de partage avec un autre service (principe d'autonomie racine).
- Port publié uniquement en local : `127.0.0.1:8084:3456` — pas d'exposition Internet à ce stade (voir Phase 3).
- Volume **nommé** `data` (pas anonyme), monté sur `/app/vikunja/` — contient la base SQLite et les fichiers joints aux tâches (pièces jointes). Nommé dès le départ pour rester adressable par un futur mécanisme de sauvegarde, même logique que `actual-budget` (voir Phase 5).
- Variables à fixer dès ce stade dans `.env` (jamais committé) :
  - `VIKUNJA_SERVICE_JWTSECRET` : généré une fois (`openssl rand -hex 32` par exemple) et figé. Sans elle, Vikunja tire un secret aléatoire à chaque démarrage et invalide toutes les sessions ouvertes au moindre redémarrage/mise à jour du conteneur — inacceptable même pour un usage familial.
  - `VIKUNJA_SERVICE_PUBLICURL` : URL publique/locale exacte par laquelle les utilisateurs atteignent le service (utilisée dans les emails et pour la vérification d'origine) — valeur dépendante du mode d'exposition choisi en Phase 3, à revoir si ce mode change.
  - `VIKUNJA_SERVICE_TIMEZONE` : `Europe/Paris` (défaut `GMT`, à corriger pour que les échéances/rappels s'affichent à l'heure locale).

## Phase 2 — SMTP (mailer)

Vikunja utilise le SMTP pour deux choses seulement : les rappels de tâches (échéances) et la réinitialisation de mot de passe. **Sans mailer actif, ces deux fonctions ne marchent pas du tout** — pas de mode dégradé comme chez Vaultwarden (qui accepte automatiquement une invitation si l'email correspond déjà à un compte local, cf. `bitwarden/README.md`). Vikunja est donc le premier service de ce dépôt où le SMTP est réellement nécessaire dès la mise en service, pas une amélioration différée.

Variables d'environnement (`VIKUNJA_MAILER_*`, doc officielle [vikunja.io/docs/config-options](https://vikunja.io/docs/config-options/)) :

| Variable | Rôle | Valeur retenue |
|---|---|---|
| `VIKUNJA_MAILER_ENABLED` | active l'envoi d'emails | `true` |
| `VIKUNJA_MAILER_HOST` | serveur SMTP | à choisir — voir ci-dessous |
| `VIKUNJA_MAILER_PORT` | port SMTP | `587` (STARTTLS) par défaut ; `465` si le fournisseur exige SSL direct (`FORCESSL: true` dans ce cas) |
| `VIKUNJA_MAILER_AUTHTYPE` | `plain`, `login` ou `cram-md5` | dépend du fournisseur, `login` le plus courant |
| `VIKUNJA_MAILER_USERNAME` / `VIKUNJA_MAILER_PASSWORD` | identifiants SMTP | secret, dans `.env` non committé |
| `VIKUNJA_MAILER_FROMEMAIL` | adresse d'expéditeur affichée | ex. `vikunja@<domaine choisi>` |
| `VIKUNJA_MAILER_FORCESSL` | force SSL direct au lieu de STARTTLS | `false` sauf si le fournisseur l'exige |
| `VIKUNJA_MAILER_SKIPTLSVERIFY` | ignore la vérification du certificat TLS du serveur SMTP | `false` — ne jamais mettre à `true` hors debug ponctuel |

**Décision à prendre (question ouverte)** : quel fournisseur SMTP ? Aucun service de ce dépôt n'a pour l'instant de SMTP réellement configuré (bitwarden fonctionne sans, cf. `bitwarden/README.md`). Options usuelles pour un usage familial à faible volume :
- Compte Gmail existant + mot de passe d'application dédié (simple, gratuit, limite ~500 emails/jour très largement suffisante ici) ;
- Un service transactionnel gratuit (Brevo, Mailjet...) si l'utilisateur préfère ne pas exposer un compte personnel.

Dans tous les cas, conformément au principe d'autonomie racine, les identifiants SMTP de `vikunja` restent **propres à ce service** (pas de réutilisation d'un secret déjà utilisé ailleurs dans ce dépôt, même si le compte email sous-jacent est le même) — un `.env` distinct, non partagé.

**Piège documenté par la communauté Vikunja, à vérifier au premier test** : certains relais SMTP minimalistes ne supportent pas la commande `NOOP` que Vikunja envoie pour vérifier la connexion — préférer un vrai serveur SMTP/relais complet (Gmail, Brevo... conviennent) plutôt qu'un relais maison minimal.

## Phase 3 — Certificats et adaptation à `edge`

Suit le contrat d'intégration standard (`edge/_plan/architecture.md`) : `vikunja` publie un port HTTP local (`127.0.0.1:8084`, Phase 1), ne possède aucun token DuckDNS, aucun certificat, aucun sidecar DDNS/ACME propre.

Deux modes possibles, comme documenté pour `actual-budget` (`edge/_plan/architecture.md`, « second mode ») — à choisir explicitement avant l'implémentation :

- **Mode local uniquement** (`vikunja.home.test`, certificat auto-signé généré par `cert-init` côté edge, pas d'entrée `DUCKDNS_SUBDOMAINS`) : suffisant si l'usage reste dans le réseau domestique. Vikunja étant une PWA avec un service worker (mode hors-ligne), il est probable qu'elle exige elle aussi un **contexte sécurisé navigateur** (HTTPS ou `localhost`) — même piège que celui découvert avec `actual-budget` (`SharedArrayBuffer`) : **à vérifier explicitement au premier test réel dans un navigateur** (pas seulement `curl`, qui ne fait aucune vérification de contexte sécurisé), avant de considérer un simple `listen 80` suffisant.
- **Mode public** (sous-domaine DuckDNS dédié, ex. `taches.<base>.duckdns.org`, certificat Let's Encrypt via `sidecar-acme`) : nécessaire seulement si un accès depuis l'extérieur du réseau domestique est voulu dès le départ (contrairement à `actual-budget`, où ce besoin a été explicitement écarté au démarrage) — pertinent ici si l'usage visé est un gestionnaire de tâches consulté aussi en mobilité, pas seulement à la maison.

**Recommandation** : commencer en mode local (`vikunja.home.test`), comme `actual-budget`, pour valider le service sans consommer de budget Let's Encrypt ni ouvrir de nouvelle entrée publique — basculer en mode public plus tard (Phase 3b) si un accès hors domicile s'avère utile, sans rien changer côté `vikunja` au-delà du contrat de la Phase 1.

Concrètement, ajouter côté `edge` uniquement (jamais côté `vikunja`) :
- `edge/nginx/conf.d/vikunja.conf` — `server_name vikunja.home.test`, `listen 443 ssl` avec le certificat auto-signé `cert-init`, `proxy_pass http://127.0.0.1:8084`, redirection 301 du port 80.
- Mettre à jour la table de routage dans `edge/_plan/architecture.md`.

### Phase 3b — Bascule en exposition Internet — **implémentée et testée en conditions réelles (2026-08-14, le jour même de la mise en service locale)**

Sous-domaine créé par l'utilisateur : **`task-jvince.duckdns.org`** (même compte DuckDNS que bitwarden/paperless). Contrat standard complet suivi (voir `edge/_plan/plan.md` phase 11 pour le détail exécuté côté edge) — remplace le certificat auto-signé, ne change rien côté `vikunja` au-delà de `VIKUNJA_SERVICE_PUBLICURL` (aucun token, certificat, ou sidecar propre à ce service, conformément au principe d'autonomie racine).

- **`VIKUNJA_SERVICE_PUBLICURL` mis à jour** vers `https://task-jvince.duckdns.org/` dans `compose.yaml` — vérifié dans les logs (`CORS enabled with origins: ... https://task-jvince.duckdns.org`).
- **Piège rencontré, sans lien avec `vikunja` lui-même** : le premier test SMTP direct avait déjà révélé le blocage IP Brevo (voir Phase 2 ci-dessus) — sans rapport avec cette bascule, mais découvert dans la même session.
- **Testé réellement, progressivement** (staging puis production, jamais l'inverse — préserve le rate limit Let's Encrypt) : certificat staging émis et vérifié (`HTTP 200`, issuer `(STAGING)`), puis certificat production émis, installé, et vérifié en accès public réel depuis une machine hors du réseau domestique (`curl https://task-jvince.duckdns.org/` sans forcer la résolution DNS) → `HTTP 200`, `issuer: Let's Encrypt` sans `STAGING`.
- **Nettoyage fait** : certificat auto-signé `vikunja.home.test` (devenu orphelin) supprimé du volume `certs` d'edge, ligne correspondante retirée de `cert-init`.
- **Conséquence documentaire** : la note de `edge/_plan/architecture.md` sur la coexistence de deux services local-only (ajoutée lors de la mise en service locale quelques heures plus tôt) redevient un historique — `budget.home.test` est de nouveau l'unique service en mode local.
- **Fait (2026-08-14)** : deux comptes du foyer créés via `https://task-jvince.duckdns.org` dans un vrai navigateur — valide au passage le contexte sécurisé HTTPS (PWA/service worker) sans réserve. Inscription libre désactivée juste après (`VIKUNJA_SERVICE_ENABLEREGISTRATION: "false"`, voir Phase 1) puisque les comptes nécessaires existent déjà et que le service est exposé publiquement — `PUT /api/v1/register` vérifié en `405` (route non montée).

## Phase 4 — Analyse de capacité : ajouter vikunja sur le Raspberry Pi 3, en plus de bitwarden et actual-budget

Contexte (`deploiement-raspberry.md`) : Raspberry Pi 3 Model B+, **1 Go de RAM total**, ~600-700 Mo réellement disponibles pour Docker après désactivation de la session graphique (Partie 3bis). `edge`, `bitwarden` (vaultwarden) et `actual-budget` tournent déjà sur cette même machine.

**Empreinte mémoire attendue de Vikunja** (mono-binaire Go + SQLite, sans Postgres) : de l'ordre de **50 Mo en fonctionnement idle/léger**, d'après la documentation et les retours de la communauté — le service le plus léger des quatre après vaultwarden (Rust, empreinte comparable), nettement sous `actual-budget` (Node.js, historiquement le plus gourmand des services déjà présents). Cette estimation reste indicative : **ne pas se fier uniquement à ce chiffre pour décider** — mesurer réellement avec `docker stats` sur le Pi avant et après l'ajout (voir ci-dessous), dans le même esprit que les validations déjà faites pour bitwarden/actual-budget (« testé, pas supposé »).

Démarche recommandée avant bascule en production sur le Pi :
1. **Mesurer l'état actuel** sur le Pi avec `docker stats --no-stream` (edge + bitwarden + actual-budget qui tournent déjà) et `free -h`, pour connaître la marge réelle disponible plutôt que de partir d'une estimation théorique — aucune mesure de ce type n'a encore été documentée pour les trois services déjà en place.
2. **Valider vikunja en local sur le PC de dev d'abord** (comme pour chaque service précédent), puis mesurer son empreinte réelle avec `docker stats` dans les mêmes conditions.
3. **Recouper les deux mesures** avant de décider d'un déploiement sur le Pi : si la marge mesurée à l'étape 1 est nettement supérieure à l'empreinte mesurée à l'étape 2, poursuivre ; sinon, ne pas déployer sans réduire la charge existante ou reconsidérer le matériel.
4. **Fixer une limite mémoire par conteneur** (`deploy.resources.limits.memory` ou `mem_limit` dans `compose.yaml`) pour `vikunja` — aucun des services déjà en place n'en a, mais avec quatre conteneurs sur 1 Go de RAM totale, un service qui dérive (fuite mémoire, pic d'usage) ne doit pas pouvoir déclencher l'OOM-killer du noyau et faire tomber un autre service au hasard (ex. bitwarden) à sa place. Point à réévaluer aussi pour les services déjà en place si ce mécanisme est jugé utile.
5. **Vérifier l'existence d'un swap** sur le Pi (`swapon --show`) : `deploiement-raspberry.md` ne mentionne aucune configuration de swap à ce jour. Sur une machine à 1 Go de RAM qui accueille un quatrième conteneur, un petit fichier de swap (ex. 512 Mo, sur la carte SD — lent mais un filet de sécurité contre un OOM plutôt qu'un accélérateur de performance) est une précaution raisonnable à considérer, pas une obligation si les mesures des étapes 1-3 montrent une marge confortable.

**CPU** : non identifié comme un risque — les quatre services visent un usage familial à faible trafic, largement dans les capacités du quad-core Cortex-A53 du Pi 3 même en cumulé ; le facteur limitant sur cette machine est la RAM, pas le CPU.

**Conclusion provisoire** : l'ajout de vikunja semble raisonnable au vu de son empreinte annoncée très faible, mais **cette phase reste à valider par la mesure réelle** (étapes 1-3) avant toute bascule en production sur le Pi — pas de déploiement direct sur la machine cible sans ce passage, en cohérence avec la démarche déjà suivie pour bitwarden/actual-budget (validation progressive : local → local sur le Pi → production).

**Devenue moins critique (2026-08-14)** : `actual-budget` (le service le plus gourmand du Pi) a été délocalisé vers le second serveur physique entre-temps (voir `actual-budget/_plan/plan.md` phase 5), justement pour faire de la place à `vikunja` — la marge disponible avant l'ajout de `vikunja` était donc déjà meilleure que ce que cette phase anticipait à l'origine (calculée avec 4 services sur le Pi, en réalité seulement `edge` + `bitwarden` + `vikunja` au moment du déploiement).

**Mesuré réellement sur le Pi (2026-08-14)** : `free -h` juste après la délocalisation d'`actual-budget` (avant `vikunja`) → 561 Mio disponibles ; après déploiement de `vikunja` (conteneur démarré, migrations SQLite exécutées) → 545 Mio disponibles. Delta réel ≈ 16 Mio, très en dessous de l'estimation de 50 Mo — confirme l'estimation « le plus léger des services de ce dépôt » sans ambiguïté. Étapes 4-5 (limite mémoire par conteneur, swap) restées non traitées ici, la marge mesurée étant large ; à reconsidérer seulement si un futur service supplémentaire venait combler cette marge à son tour.

## Phase 5 (future, non déclenchée) — Sauvegarde

Non traitée dans le détail par cette demande initiale, mais à ne pas oublier : les tâches créées dans Vikunja sont des données utilisateur réelles, non régénérables (comme `actual-budget`, à la différence de `paperless` dont la source vit sur Google Drive). Une fois le volume `data` (Phase 1) en usage réel, écrire un `_plan/plan-sauvegarde.md` dédié (mécanisme à définir, potentiellement calqué sur `bitwarden`/`actual-budget` : restic + rclone, sans jamais réutiliser leur dépôt/remote — principe d'autonomie racine) et mettre à jour le tableau de `protocole-donnees.md`. Peut rester non implémenté un temps, par décision explicite documentée, comme cela a été fait pour `actual-budget`.

## Exécutée et testée en conditions réelles (2026-08-14)

Service implémenté et déployé sur le Raspberry Pi (mode local uniquement, Phase 3), avec plusieurs corrections par rapport à ce plan initial, découvertes en vérifiant la documentation officielle avant d'écrire la config (plutôt que de committer les hypothèses de la Phase 1 telles quelles) :

- **Variable JWT corrigée** : `VIKUNJA_SERVICE_JWTSECRET` (Phase 1) est dépréciée — la variable actuelle recommandée est `VIKUNJA_SERVICE_SECRET` (fonctionnellement équivalente, `JWTSECRET` continue de fonctionner mais n'est plus la forme documentée pour un déploiement neuf). `compose.yaml`/`.env.example` utilisent `VIKUNJA_SERVICE_SECRET`.
- **Deux volumes nommés, pas un seul** : contrairement à l'hypothèse de la Phase 1 (« volume nommé `data` monté sur `/app/vikunja/` »), l'image officielle préconfigure `VIKUNJA_DATABASE_PATH=/db/vikunja.db` et `VIKUNJA_SERVICE_ROOTPATH=/app/vikunja/` (fichiers sous `/app/vikunja/files`) — deux chemins distincts, pas un seul. `compose.yaml` suit ces défauts tels quels (volumes nommés `data` → `/db` et `files` → `/app/vikunja/files`) plutôt que de les réécrire vers un point de montage unique, pour rester au plus près du comportement documenté/testé par l'éditeur.
- **Chown obligatoire avant le premier démarrage** : l'image tourne en uid 1000 non-root et ne chown jamais elle-même ses volumes — sans cette étape, l'écriture dans `/db` et `/app/vikunja/files` échoue au premier lancement. Ajouté comme service `vikunja-init` derrière un profil Compose `init` (même schéma que `cert-init` côté `edge`) : `docker compose --profile init run --rm vikunja-init`, à exécuter une seule fois avant le premier `up`.
- **SMTP (Phase 2) — validé de bout en bout (2026-08-14)** : fournisseur retenu **Brevo** (transactionnel, 300 emails/jour gratuits, n'expose pas de compte email personnel), tranchant la question ouverte de cette phase. `VIKUNJA_MAILER_HOST`/`PORT`/`AUTHTYPE` fixés en clair dans `compose.yaml` (non secrets) ; `VIKUNJA_MAILER_USERNAME`/`PASSWORD`/`FROMEMAIL` dans `.env` sur le Pi (non committé), `FROMEMAIL` = adresse perso vérifiée par code à 6 chiffres dans Brevo (Senders).
  - **Piège rencontré et corrigé** : premier test SMTP direct (`curl smtp://...`, hors Vikunja) → `525 5.7.1 Unauthorized IP address`. Brevo bloque par défaut les clés SMTP depuis une IP non reconnue (protection anti-abus). Corrigé en désactivant ce blocage (`Settings > Security > Authorized IPs > SMTP keys > Deactivate blocking`) plutôt qu'en autorisant une IP précise — l'IPv4 sortante du foyer est probablement CGNAT (cf. `bitwarden/_plan/analyse-besoin-fonctionnel.md`), donc potentiellement instable ; une clé SMTP secrète reste une protection suffisante pour ce volume/usage. Décision explicite de l'utilisateur.
  - **Testé réellement** : connexion `smtp-relay.brevo.com:587`, `AUTH CRAM-MD5` → `235 Authentication succeeded`, email accepté (`250 OK: queued`) — test fait en dehors de Vikunja (aucun compte Vikunja encore créé pour déclencher un vrai reset de mot de passe), donc la couche transport SMTP est validée mais pas encore un envoi déclenché par Vikunja lui-même. À confirmer à la création du premier compte (email de bienvenue/confirmation, si activé) ou au premier reset de mot de passe réel.
- **HTTPS choisi directement, sans passer par un essai HTTP simple** : contrairement à la découverte a posteriori sur `actual-budget` (Phase 4a/8 de son propre plan), le bloc `edge/nginx/conf.d/vikunja.conf` est allé directement en `listen 443 ssl` avec certificat auto-signé (`cert-init` étendu avec `generate "vikunja.home.test" "vikunja"`), sur l'hypothèse que la PWA/service worker de Vikunja a la même exigence de contexte sécurisé qu'Actual (`SharedArrayBuffer`). **Pas encore confirmé par un vrai navigateur** (seulement `curl -k`, qui ne vérifie aucun contexte sécurisé) — à faire au premier usage réel.
- **Conséquence architecturale sur `edge`** : avec `vikunja.home.test` ET `budget.home.test` désormais tous deux en mode local uniquement, l'accès par IP LAN nue ne peut plus servir que le premier bloc chargé par nginx — une entrée `/etc/hosts` par service devient nécessaire pour les appareils du foyer, pas seulement pratique. Documenté dans `edge/_plan/architecture.md`.
- **Testé réellement de bout en bout** : `docker logs` confirme `Using SQLite database at: /db/vikunja.db`, migrations exécutées sans erreur, CORS aligné sur `https://vikunja.home.test` (repris de `VIKUNJA_SERVICE_PUBLICURL`) ; `curl http://127.0.0.1:8084/` → `HTTP 200` ; via `edge`, `curl -k https://vikunja.home.test/ --resolve ...` → `HTTP 200`, page HTML servie. Aucune régression constatée sur `budget.home.test` ni `jvince.duckdns.org` (bitwarden) après le reload nginx.
- **Déployé par `rsync`** (pas de `git pull` — le dossier `vikunja/` n'existait pas encore sur le Pi), `.env` réel transféré avec le secret déjà généré (`openssl rand -hex 32`).
- **Fait (2026-08-14)** : deux comptes créés dans un vrai navigateur via `https://task-jvince.duckdns.org` — contexte sécurisé HTTPS validé sans réserve pour la PWA/service worker. Inscription libre désactivée juste après (voir Phase 3b et Phase 1).
- **Pas encore fait** : entrées `/etc/hosts` sur les appareils du foyer devenues sans objet (service désormais public, plus besoin de résolution locale) ; décision sur le commit de ces changements.
