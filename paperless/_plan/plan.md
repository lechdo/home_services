# Plan de réalisation — Paperless (DMS personnel)

> Synthèse de conception issue de `../conversation.md`. Ce plan découpe le projet en phases progressives : on commence sans code custom, et on n'ajoute de l'intelligence propre que là où Paperless-ngx ne suffit plus.

## Vision

Un DMS personnel local-first où :
- **Google Drive** est l'archive immuable ("source pure").
- **Paperless-ngx** est le moteur documentaire (OCR, stockage, recherche, tags, types, custom fields).
- **Un service RAD/LAD custom** est la couche d'intelligence qui enrichit progressivement Paperless (classification et extraction plus riches, relations sémantiques, actions), sans jamais le remplacer.

Objectif final : passer de "j'ai des fichiers" à "j'ai des documents avec une représentation sémantique exploitable".

## Décisions d'architecture déjà prises (issues de la conversation)

- Solution DMS retenue : **Paperless-ngx** (plutôt que Mayan EDMS, Teedy, Nextcloud+apps) — meilleur rapport OCR/tags/recherche/API/déploiement pour un usage personnel.
- Synchronisation GDrive : via **rclone**, en mode unidirectionnel (`GDrive → local`), jamais l'inverse automatiquement.
- Stockage/recherche : la base PostgreSQL interne de Paperless suffit au départ ; pas d'OpenSearch/Elasticsearch tant que le volume ne le justifie pas.
- Le pipeline de traitement est pensé comme **événementiel** (`document.created → ocr.required → ocr.completed → classification.required → ... → index.updated`), pour pouvoir remplacer un composant (OCR, classifieur) sans réécrire le reste.
- Question ouverte tranchée : les documents restent physiquement "appartenant" à Drive comme source de vérité ; Paperless n'en garde qu'une copie/cache locale, jamais l'inverse.

## Phase 0 — Socle Paperless (zéro code custom) — **partiellement faite**

- **Fait (2026-08-12)** : Paperless-ngx déployé en Docker Compose. Trois services, pas deux : `db` (postgres) + `broker` (redis) + `paperless` (webserver) — **`broker` n'était pas anticipé dans `architecture.md`/`data-model.md`** (conception centrée sur PostgreSQL) : Paperless-ngx nécessite une file de tâches (OCR, indexation, matching Auto) même en usage mono-utilisateur, découvert à l'implémentation.
- **Fait** : `ghcr.io/paperless-ngx/paperless-ngx` (image "canonique" de la doc officielle) refuse le pull dans l'environnement de test (`denied`) — `docker.io/paperlessngx/paperless-ngx` utilisé à la place (même projet, mirroir Docker Hub). À revérifier sur la machine cible finale (peut-être spécifique à cet environnement de test).
- **Fait** : `PAPERLESS_URL` réglé sur `https://paperless-jvince.duckdns.org` (règle `ALLOWED_HOSTS`/`CORS_ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` en une variable) — nécessaire car Paperless-ngx est servi derrière `edge` sur un nom de domaine externe, jamais en direct.
- **Validé réellement** : webserver démarre (`healthy`), migrations Django appliquées, page de connexion accessible en local (`127.0.0.1:8082`) et via `edge` (`https://paperless-jvince.duckdns.org`, certificat staging) — voir `edge/_plan/plan.md` phase 6.
- **Fait (2026-08-12), via l'API REST** : les 7 types de documents décidés à la conception créés (`Facture`, `Contrat`, `Relevé bancaire`, `Courrier administratif`, `Bulletin de salaire`, `Impôt`, `Assurance`), ainsi que les 5 tags de base issus des exemples concrets de `data-model.md` (`EDF`, `maison`, `à vérifier`, `important`, `comptabilité`). Tous créés avec `matching_algorithm: 6` (Auto) — cohérent avec l'approche documentée ("commencer sans IA, laisser l'algorithme Auto apprendre des classifications confirmées"), aucune règle de matching par mots-clés définie (`match` vide) puisqu'aucun document réel n'a encore été vu.
- **Ajouté ensuite, sur demande explicite** : 3 types de documents supplémentaires par personne (`Lucas`, `Virginie`, `Julien`) et le tag `mdph`. **Écart volontaire par rapport à `data-model.md`** ("Distinction Classification / Tags / Collections" : `document_type` répond à "qu'est-ce que ce document ?", pas "à qui appartient-il ?") — un type de document par personne mélange les deux axes. Noté ici pour que ce ne soit pas pris pour un oubli ; pas remis en question sans demande explicite, `data-model.md` non modifié en conséquence pour l'instant.
- **Pas encore fait** : les correspondants, les règles de matching explicites (`match` + `algorithm: Any`) pour les cas évidents — reportées à après l'ingestion d'un premier lot de documents réels (voir Phase 1). Aucun document ingéré à ce stade.
- Objectif de sortie de phase : le classement fonctionne "à la main + règles" sur un premier lot de documents, sans aucun service custom — **catégories prêtes, classement réel pas encore testé** (pas de document).
- Voir `README.md` pour reproduire ces étapes.

## Phase 1 — Synchronisation Google Drive → Paperless — **implémentée (2026-08-12), pas encore activée**

- **Fait** : sidecar `sidecar-gdrive-sync` ajouté à `compose.yaml` (image Alpine + rclone, `rclone copy` — jamais `sync` — depuis `GDRIVE_REMOTE_PATH` vers le dossier `consume` de Paperless, toutes les 5 minutes). Dossier Drive dédié retenu : `controlled_chaos`.
- **Décision d'architecture** : `copy` plutôt que `sync`, délibérément — Paperless retire les fichiers du dossier `consume` une fois ingérés ; un `sync` (qui recrée l'état miroir exact) les recopierait indéfiniment depuis Drive. Pas de tracking custom d'ID Drive à ce stade : un fichier déjà ingéré et recopié par erreur est rejeté par la détection de doublon par hash déjà native à Paperless-ngx — cohérent avec la progressivité voulue (`CLAUDE.md`, "ne pas réimplémenter ce que Paperless sait déjà faire"). La traçabilité `drive_file_id` en tant que donnée de premier niveau reste hors périmètre de cette phase (renvoyée à un vrai modèle de données si le besoin apparaît, cf. `data-model.md`).
- **Fait** : accès en **lecture seule** (`scope = drive.readonly` côté rclone) plutôt qu'accès complet — ce service ne peut structurellement pas écrire sur le Drive, cohérent avec la contrainte d'immutabilité de la source. Scripts `scripts/authorize-gdrive.sh` (OAuth, indépendant de celui de bitwarden) et `scripts/setup-gdrive-sync.sh` (vérification d'accès + activation, idempotent) préparés — voir `README.md`.
- **Pas encore fait / en attente d'un geste manuel** : l'autorisation OAuth elle-même (navigateur), puis l'activation réelle du sidecar et la vérification qu'un fichier déposé dans `controlled_chaos` apparaît bien dans Paperless (OCR fait, sans intervention manuelle) — objectif de sortie de phase non encore validé en conditions réelles.

## Phase 2 — Modélisation Paperless (types, tags, custom fields) — **implémentée et validée (2026-08-12)**

- **Fait** : 5 Custom Fields créés via `provisioning/seed.json` + `apply.py` (même mécanisme que les types/tags de la Phase 0, pas de nouvelle machinerie) : `fournisseur` (string), `montant` (monetary), `date_document` (date), `date_echeance` (date), `numero_piece` (string).
- **Décision d'architecture** : un jeu de champs **générique**, pas un jeu par type de document — Paperless-ngx ne permet pas nativement de restreindre un Custom Field à un `document_type` précis (contrairement à ce que "chaque type a son jeu de custom fields" dans la version initiale de ce plan pouvait suggérer) ; ces 5 champs couvrent de façon générique la plupart des types (facture, contrat, impôt, assurance, relevé, bulletin de salaire), sans sur-construire un modèle par type qui n'apporterait rien tant qu'aucun document réel n'a été traité (cf. "Progressivité", `CLAUDE.md`).
- **Validé réellement** : dry-run puis apply réels sur l'instance locale (5 créés, 0 mis à jour, 16 déjà conformes) ; second passage confirmant l'idempotence (21 déjà conformes, 0 changement) ; vérification via l'API que les 5 champs ont bien les `data_type` attendus.
- Objectif de sortie de phase atteint : les Custom Fields existent et sont prêts à être remplis, manuellement ou par le futur RAD/LAD (Phase 3+) — pas encore de règle automatique les remplissant, normal à ce stade (aucun document réel).

## Phase 3 — Webhook Paperless → service RAD/LAD — **implémentée et validée de bout en bout (2026-08-12)**

- **Fait** : workflow Paperless `RAD/LAD - notification document` déclaré dans `provisioning/seed.json` (déclenché sur `Document Added` et `Document Updated`, toutes sources) — même mécanisme `provisioning/apply.py` que le reste, pas d'exception "workflow créé à la main" à documenter séparément (cohérent avec `protocole-donnees.md`, qui cite justement les workflows comme exemple de config structurelle à déclarer).
- **Fait** : squelette du service `rad-lad-service` (FastAPI, `paperless/rad-lad/`) — reçoit le webhook, récupère le document et son texte OCR via l'API Paperless (`GET /api/documents/{id}/`), journalise, ne classe/n'extrait rien (Phase 4+). Conteneur ajouté à `compose.yaml`, jamais exposé sur l'hôte (appelé uniquement par Paperless sur le réseau `internal`).
- **Piège découvert et corrigé** : la combinaison `as_json: true` + `body` (string) fait que Paperless envoie une **chaîne JSON-encodée** comme corps de requête (`json.dumps(str)`), pas un objet JSON — `rad-lad-service` recevait un `str` au lieu d'un `dict`. Corrigé en utilisant `params` (dict de templates Jinja2, un par clé) plutôt que `body` : `as_json: true` + `params` produit un vrai objet JSON. Variable de template correcte : `doc_id` (pas `doc.id` comme dans l'exemple informel de la conversation d'origine — voir le code source de `documents/templating/workflows.py` dans l'image `paperlessngx/paperless-ngx` pour la liste exacte des placeholders disponibles).
- **Validé réellement** : dry-run/apply/second-passage idempotent (0 changement) sur le workflow ; détection de dérive testée (désactivation manuelle du workflow puis correction par `apply.py`) ; test de bout en bout complet — document réel envoyé via `POST /api/documents/post_document/`, webhook reçu par `rad-lad-service`, document et texte OCR relus via l'API Paperless (journalisé), documents de test purgés après coup (trash vidée).
- Objectif de sortie de phase atteint : le service RAD/LAD est notifié à chaque nouveau document (ajout ou modification) et peut lire son contenu OCR.

## Phase 4 — Classification/extraction RAD/LAD (progressif)

Monter en sophistication uniquement quand le niveau précédent échoue trop souvent :

1. Règles Paperless natives.
2. Algorithme **Auto** de Paperless.
3. Regex / heuristiques Python côté RAD/LAD.
4. Modèle ML classique.
5. LLM / VLM.
6. Modèle spécialisé (si le volume/besoin le justifie).

- Le format de sortie du RAD/LAD (type, champs, confiance, evidence) est figé par le contrat défini dans `rad-lad-contract.md`.
- Objectif de sortie de phase : mesurer, sur un échantillon réel, la répartition règles/Auto/RAD-LAD (cf. exemple conversation : 900 règles / 70 Auto / 30 RAD-LAD sur 1000 documents) et ne complexifier que si nécessaire.

## Phase 5 — Politique de confiance et écriture dans Paperless

- Implémenter la couche de décision par seuils de confiance (voir `rad-lad-contract.md`) : automatique / automatique + "à vérifier" / validation humaine.
- Le service RAD/LAD écrit dans Paperless via son API REST (`document_type`, `tags`, `custom_fields`) uniquement selon cette politique.
- Objectif de sortie de phase : aucune classification de confiance faible n'est appliquée sans passer par une validation humaine visible.

## Phase 6 — Historisation et robustesse

- Garder une trace des versions du document source (hash, date de téléchargement) pour distinguer "métadonnées modifiées" de "nouvelle version du fichier", et ne jamais perdre un résultat RAD/LAD précédent.
- Vérifier la propriété de **reconstructibilité** : la base locale peut être régénérée entièrement à partir de Google Drive.

## Phase 7 (ultérieure, hors périmètre immédiat)

- Relations sémantiques entre documents (`replaces`, `related_to`, `attachment_of`, `duplicate_of`).
- Entités, dates, montants extraits comme objets de premier niveau, actions dérivées (ex. "paiement à effectuer", échéance).
- Interfaces Web / CLI / TUI au-dessus de l'API Paperless + service RAD/LAD.

## Phase 8 — Exposition Internet via `edge` — **implémentée et validée (2026-08-12)**

- Fait : port HTTP de Paperless-ngx publié sur `127.0.0.1:8082`, sans aucune logique TLS/DNS côté paperless.
- Fait : sous-domaine `paperless-jvince.duckdns.org` (créé dès la Phase 1 du plan `edge`, avant même que ce service existe) enregistré dans la table de routage d'`edge` (`edge/nginx/conf.d/paperless.conf`).
- **Test de bout en bout réussi** : `https://paperless-jvince.duckdns.org` (via edge, certificat staging) sert la page de connexion Paperless-ngx (`<title>Paperless-ngx sign in</title>`).
- Cette phase est indépendante des phases 0-6 : elle ne conditionne pas le fonctionnement local de Paperless, seulement son accès distant — cohérent avec le fait qu'elle a été implémentée avant que les phases 1-6 (config métier, RAD/LAD) ne soient commencées.
- **Pas encore fait** : passage en production (toujours staging), test sur la machine cible finale.

## Phase 9 — Migration vers un second serveur dédié — **planifiée, pas encore faite**

- **Contexte** : `paperless` (et son sidecar rclone, futur RAD/LAD) va quitter la machine qui héberge `edge` pour un second serveur physique, sur le **même réseau local domestique**, avec une IP LAN déjà réservée (DHCP). Ce serveur ne sera **pas allumé en permanence** — accepté explicitement comme un choix, pas un incident à corriger.
- **Ce qui ne change pas** : toujours conteneurisé via `compose.yaml`, toujours aucune connaissance d'`edge` (le service ignore qui le route et comment — cf. `CLAUDE.md`), toujours aucun token DuckDNS/certificat/sidecar DDNS-ACME propre. `PAPERLESS_URL` reste `https://paperless-jvince.duckdns.org` (donnée applicative pour `ALLOWED_HOSTS`/CORS/CSRF, pas une adresse réseau) — inchangé par ce déménagement.
- **Ce qui change** :
  1. **Binding du port publié** (`compose.yaml`, actuellement `127.0.0.1:8082:8000`) : ne peut plus être borné à la loopback, puisque la requête vient désormais du réseau local (edge, sur une autre machine) et non de l'hôte lui-même. À remplacer par l'IP LAN de ce second serveur : `<IP_LAN_PAPERLESS>:8082:8000` — jamais `0.0.0.0` (pas d'exposition sur toutes les interfaces de la machine).
  2. **Pare-feu côté second serveur** : autoriser le port `8082/tcp` uniquement depuis l'IP LAN de la machine qui héberge `edge` — jamais tout le LAN, jamais Internet. Le trafic edge↔paperless reste du HTTP non chiffré (cf. contrat `edge/_plan/architecture.md`) ; ce n'est défendable que restreint à une source précise sur un réseau de confiance.
  3. **Migration des volumes** (`pgdata`, `media`, `redisdata`) et de `.env`/`rclone.conf` vers le second serveur : une copie manuelle (export/`rsync` des volumes Docker) suffit, pas de script de migration dédié à écrire — ces données sont de toute façon reconstructibles depuis Google Drive si besoin (cf. `plan-sauvegarde.md`), donc pas de procédure filet de sécurité particulière au-delà de la copie elle-même.
  4. `sidecar-gdrive-sync` (rclone) suit paperless sur le second serveur — aucune dépendance à la machine d'`edge`, aucun changement de logique de synchronisation.
- **Disponibilité intermittente — porté entièrement côté edge, pas ici** : la dégradation propre du service quand le second serveur est éteint (page d'indisponibilité au lieu d'une erreur brute, timeouts courts) est une responsabilité d'`edge` (voir `edge/_plan/plan.md` phase 7), pas de paperless — cohérent avec le principe d'autonomie : paperless n'a rien à coder ni à configurer pour ce cas, il ne sait même pas qu'`edge` existe.
- **Pas encore fait** : bascule physique effective, mise à jour de l'IP dans `edge/nginx/conf.d/paperless.conf`, test réel serveur éteint/rallumé.

## Documents associés

- `architecture.md` — schémas d'architecture et flux détaillés.
- `data-model.md` — modèle conceptuel du Document et correspondance avec les objets Paperless.
- `rad-lad-contract.md` — contrat JSON RAD/LAD ↔ Paperless et politique de seuils de confiance.
- `../../edge/_plan/architecture.md` — contrat d'intégration pour l'exposition Internet (phase 8).
