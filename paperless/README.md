# paperless

Voir `conversation.md` (échange de conception d'origine) et `_plan/` (plan de réalisation, architecture, modèle de données, contrat RAD/LAD) pour le contexte complet.

## Où on en est

**Dernier état (2026-08-14)** : socle Docker Compose implémenté et validé (Phase 0 partielle), exposition Internet via `edge` faite (Phase 8), synchronisation Google Drive préparée mais pas activée (Phase 1), modélisation Custom Fields faite et validée (Phase 2), squelette RAD/LAD + webhook Paperless implémentés et validés de bout en bout (Phase 3) — la classification/extraction elle-même (Phase 4+) n'est pas encore développée, et aucun document réel (hors tests) n'a encore été traité. Migration vers un second serveur dédié en cours (Phase 9) : socle re-déployé et validé sur ce second serveur (instance neuve, pas encore reliée à `edge`) — voir `_plan/plan.md` phase 9 pour le détail et ce qui reste à faire (migration des données réelles, câblage edge, IP LAN).

- Services : `db` (postgres), `broker` (redis — non anticipé à la conception, nécessaire pour la file de tâches de Paperless-ngx), `paperless` (webserver, image `paperlessngx/paperless-ngx` — le mirroir Docker Hub, `ghcr.io/paperless-ngx/paperless-ngx` étant refusé dans l'environnement de test utilisé), `gotenberg` + `tika` (conversion/extraction, nécessaires pour consommer les fichiers `.eml`, jamais exposés sur l'hôte).
- Webserver publié sur `127.0.0.1:8082`, `PAPERLESS_URL=https://paperless-jvince.duckdns.org` (le sous-domaine réel, possédé et routé par `/edge/` — rien de DNS/TLS ici).
- **Validé réellement** : démarrage propre (migrations Django appliquées, `healthy`), page de connexion accessible en local et via `edge` (`https://paperless-jvince.duckdns.org`, certificat staging).
- **Fait** : 10 types de documents créés (`Facture`, `Contrat`, `Relevé bancaire`, `Courrier administratif`, `Bulletin de salaire`, `Impôt`, `Assurance`, puis `Lucas`, `Virginie`, `Julien` sur demande explicite — écart volontaire par rapport à la distinction type/tag documentée dans `_plan/data-model.md`, voir `_plan/plan.md` phase 0) et 6 tags de base (`EDF`, `maison`, `à vérifier`, `important`, `comptabilité`, `mdph`), via l'API REST, avec `matching_algorithm: 6` (Auto).
- **Fait (2026-08-12)** : synchronisation Google Drive → `consume` (Phase 1) implémentée (`sidecar-gdrive-sync` dans `compose.yaml`, dossier Drive dédié `controlled_chaos`, accès en lecture seule) — voir section "Synchronisation Google Drive" ci-dessous. **Pas encore activée** : bloquée sur l'autorisation OAuth (geste manuel, comme pour bitwarden).
- **Fait (2026-08-12)** : 5 Custom Fields créés (Phase 2) via le même mécanisme `provisioning/` que les types/tags — `fournisseur`, `montant`, `date_document`, `date_echeance`, `numero_piece` (génériques, pas un jeu par type de document — Paperless-ngx ne le permet pas nativement). Validé réellement : apply + second passage idempotent + vérification API.
- **Fait (2026-08-12)** : squelette du service `rad-lad-service` (Phase 3) + workflow Paperless déclaratif appelant son webhook — voir section "Service RAD/LAD" ci-dessous. **Validé de bout en bout** avec un document réel (upload → webhook → relecture OCR par `rad-lad-service`).
- **Pas encore fait** : correspondants, règles de matching explicites par mots-clés, aucun document réel ingéré, classification/extraction RAD/LAD (Phase 4+, le squelette actuel ne fait que lire l'OCR, il ne classe rien).
- Tous les conteneurs actuellement **arrêtés** (`docker compose down`, sans `-v`) — volumes conservés (`data`, `media`, `pgdata`, `redisdata`).

## Prérequis

- Docker + Docker Compose (`docker compose version`).

## Démarrage

```bash
cd /ws/personal/home_services/paperless
cp .env.example .env
# éditer .env : POSTGRES_PASSWORD, PAPERLESS_SECRET_KEY, PAPERLESS_ADMIN_PASSWORD
# (valeurs fortes, ex. openssl rand -base64 32) et PUBLIC_HOSTNAME
mkdir -p export consume
docker compose up -d
docker compose logs -f paperless   # attendre "Booting worker" / le healthcheck "healthy"
```

## Tests à réaliser

- En local (sans edge) : `curl http://127.0.0.1:8082/` doit rediriger vers `/accounts/login/?next=/` (HTTP 302), puis `curl http://127.0.0.1:8082/accounts/login/` doit répondre 200.
- Se connecter avec `PAPERLESS_ADMIN_USER`/`PAPERLESS_ADMIN_PASSWORD`.
- Via `edge` (une fois celui-ci démarré et `paperless.conf` en place, voir `../edge/README.md`) : `https://paperless-jvince.duckdns.org` doit servir la même page (certificat staging, avertissement navigateur attendu).

## Types de documents, tags et custom fields (déclaratif, rejouable)

Types de documents, tags et Custom Fields déclarés dans `provisioning/seed.json` — pas créés à la main ni par une suite de commandes à rejouer de mémoire. `provisioning/apply.py` réconcilie l'état réel de Paperless avec ce fichier : crée ce qui manque, corrige ce qui a dérivé, ne touche jamais à ce qui est déjà conforme, ne supprime jamais rien (voir `../protocole-donnees.md`).

```bash
set -a && source .env && set +a
python3 provisioning/apply.py            # applique pour de vrai
python3 provisioning/apply.py --dry-run  # affiche ce qui serait fait, sans écrire
```

Pour ajouter/modifier un type, un tag ou un custom field : éditer `provisioning/seed.json`, puis relancer `apply.py` — c'est la seule façon d'y toucher, plutôt que via l'UI Paperless directement (sinon le fichier de seed devient obsolète sans qu'on s'en rende compte).

`matching_algorithm: 6` = Auto (Paperless apprend des classifications confirmées manuellement, cf. `_plan/plan.md` phase 0). Aucune règle de matching par mots-clés définie pour l'instant — à ajouter dans le seed une fois un premier lot de documents réels observé.

Custom Fields (Phase 2, cf. `_plan/plan.md`) : 5 champs génériques — `fournisseur` (string), `montant` (monetary), `date_document` (date), `date_echeance` (date), `numero_piece` (string) — pas un jeu par type de document (Paperless-ngx ne le permet pas nativement). Pas encore remplis automatiquement (nécessite le RAD/LAD, phases 3+), et aucun document réel pour l'instant.

**Validé réellement (2026-08-12)** : exécution à vide sur l'état déjà en base (16 déjà conformes, 0 changement) ; suppression manuelle du tag `mdph` puis `apply.py` le recrée ; changement manuel de l'algorithme de matching d'`EDF` puis `apply.py` le corrige ; ajout des 5 custom fields (5 créés) puis second passage confirmant l'idempotence (21 déjà conformes, 0 changement) et vérification via l'API que les `data_type` sont corrects. Les trois chemins (créer / mettre à jour / ne rien faire) fonctionnent, y compris pour les custom fields.

## Service RAD/LAD (squelette, Phase 3)

Voir `_plan/plan.md` phase 3 pour le détail des choix et du piège rencontré (encodage JSON du webhook). Code dans `rad-lad/` (FastAPI, `app/main.py`). Démarre avec le reste de la stack :

```bash
docker compose up -d   # construit rad-lad-service au besoin, puis le démarre avec le reste
python3 provisioning/apply.py   # crée/maintient le workflow "RAD/LAD - notification document"
```

Ce service n'est **jamais** exposé sur l'hôte : il n'est appelé que par Paperless, sur le réseau Docker interne (`http://rad-lad-service:8000/webhook/paperless`). Pour l'instant il ne fait que recevoir la notification et relire le document + son OCR — aucune classification, aucune écriture dans Paperless (ça viendra en Phase 4-5).

### Test de bout en bout

```bash
set -a && source .env && set +a
TOKEN=$(curl -s -X POST http://127.0.0.1:8082/api/token/ -d "username=$PAPERLESS_ADMIN_USER&password=$PAPERLESS_ADMIN_PASSWORD" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "Document de test" > /tmp/test.txt
curl -s -X POST -H "Authorization: Token $TOKEN" -F "document=@/tmp/test.txt" -F "title=Test webhook" \
  http://127.0.0.1:8082/api/documents/post_document/
docker compose logs -f rad-lad-service   # doit afficher "document N reçu : ..." après quelques secondes
```

**Validé réellement (2026-08-12)** : document réel envoyé, webhook reçu par `rad-lad-service`, document et texte OCR relus via l'API Paperless (journalisé dans les logs du conteneur), documents de test purgés après coup (`DELETE` + vidage de la corbeille).

## Synchronisation Google Drive (Phase 1)

Voir `_plan/plan.md` phase 1 pour le détail des choix d'architecture. Statut (2026-08-12) : `sidecar-gdrive-sync` implémenté dans `compose.yaml`, dossier Drive dédié `controlled_chaos` — **bloqué sur l'autorisation OAuth Google Drive** (geste manuel dans un navigateur, même nature que pour bitwarden, mais scope en **lecture seule** ici).

### 1. Autoriser rclone à lire ton Google Drive (à faire toi-même)

Sur une machine qui a un navigateur (pas forcément celle qui héberge paperless en prod) :

```bash
./scripts/authorize-gdrive.sh
```

Suis le lien affiché, connecte-toi/autorise l'accès **en lecture** à ton Google Drive. Le script récupère lui-même le token et génère `rclone.conf` (scope `drive.readonly` — ce service ne peut pas écrire sur ton Drive).

Si cette machine n'est pas celle qui héberge paperless en prod, copie le `rclone.conf` généré vers le dossier `paperless/` de la machine cible avant l'étape suivante.

### 2. Activer la synchronisation

```bash
./scripts/setup-gdrive-sync.sh
```

Le script vérifie que `GDRIVE_REMOTE_PATH` (dossier `controlled_chaos` par défaut, cf. `.env`) est bien lisible, active `COMPOSE_PROFILES=gdrive-sync`, puis démarre `sidecar-gdrive-sync`. Suivre la première synchronisation avec `docker compose logs -f sidecar-gdrive-sync`, puis vérifier dans l'UI Paperless qu'un document déposé dans `controlled_chaos` apparaît automatiquement, OCR fait.

## Consommation des fichiers .eml (courriers électroniques)

Paperless-ngx ne sait pas nativement extraire le contenu d'un `.eml` : il délègue à **Tika** (extraction du message) et **Gotenberg** (rendu HTML → PDF). Sans ces deux services, un `.eml` déposé dans `consume/` échoue avec `Unsupported mime type message/rfc822`.

- Deux services ajoutés à `compose.yaml` : `gotenberg` (`gotenberg/gotenberg:8.34`) et `tika` (`apache/tika:latest`), tous deux internes uniquement (jamais publiés sur l'hôte).
- Côté `paperless` : `PAPERLESS_TIKA_ENABLED=true`, `PAPERLESS_TIKA_ENDPOINT=http://tika:9998`, `PAPERLESS_TIKA_GOTENBERG_ENDPOINT=http://gotenberg:3000`.
- Pas de configuration supplémentaire côté `.env` : ces endpoints pointent sur les noms de service Docker Compose, internes au réseau `internal`.
- Test : déposer un fichier `.eml` dans `consume/` (ou l'envoyer via `POST /api/documents/post_document/`) et vérifier qu'il apparaît comme document dans Paperless (converti en PDF, OCR fait) plutôt que de rester en échec dans `docker compose logs paperless`.

## Arrêt / nettoyage

```bash
docker compose down          # arrête les conteneurs, conserve les volumes (documents, base, secrets de session)
docker compose down -v       # arrête et supprime aussi les volumes (perte des données)
```

## Notes

- `PAPERLESS_URL` doit correspondre exactement au nom de domaine externe utilisé pour accéder au service (via `edge`) — sinon Paperless-ngx refuse les requêtes (`ALLOWED_HOSTS`) ou les soumissions de formulaire (`CSRF_TRUSTED_ORIGINS`).
- Ce service ne gère jamais lui-même de nom de domaine ni de certificat TLS — voir `CLAUDE.md`, section "Exposition Internet", et `../edge/`.
- Prochaine étape naturelle : activer la synchronisation Google Drive (phase 1, geste manuel OAuth restant) pour obtenir un premier lot de documents réels, puis commencer la classification/extraction RAD/LAD elle-même (phase 4) sur ce lot.
