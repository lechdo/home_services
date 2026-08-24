# edge

Point d'entrée Internet unique pour tous les services du dossier racine. Voir `CLAUDE.md` et `_plan/architecture.md` pour le contrat d'intégration, `_plan/plan.md` pour le déroulé complet (17 phases à ce jour).

## Où on en est

**DNS/TLS** : DuckDNS entièrement retiré (`_plan/plan.md` phase 15, terminé le 2026-08-24) — **dynv6** est désormais l'unique mécanisme DNS/certificat de ce dépôt, sur une zone unique (`jvince.dynv6.net`). 8 sous-domaines actifs, tous avec certificat Let's Encrypt réel : `vault` (bitwarden), `paperless`, `task` (vikunja), `budget` (actual-budget), `minecraft` (panel), `navi`/`music` (navidrome/fetcher, music_manager), `auth` (authentik).

**Authentification** : `authentik` (service séparé, voir `authentik/CLAUDE.md`) protège tous ces services sauf `vault` — soit via un vrai SSO applicatif (OIDC pour vikunja/paperless/actual-budget, en-tête de confiance natif pour navidrome), soit via le portail générique de secours (minecraft-panel, fetcher). Voir `authentik/_plan/plan.md`.

**Pour reprendre** :
```bash
cd /ws/personal/home_services/edge && docker compose up -d
./scripts/deploy.sh   # déploiement + vérification de bout en bout sur le Pi
```

<details>
<summary>Historique — Phases 0-14 (DuckDNS, 2026-08-12 à 2026-08-22)</summary>

Voir `_plan/plan.md` pour le détail complet : squelette du service, premiers sous-domaines DuckDNS (bitwarden, paperless), généralisation à vikunja/actual-budget/minecraft/music_manager, découverte du besoin de `network_mode: host`, correction du timeout Minecraft Java (A factice + Happy Eyeballs), etc. Cette section n'est plus reproductible telle quelle : DuckDNS a été retiré (Phase 15).

</details>

## Déploiement en production (Raspberry Pi)

```bash
./scripts/deploy.sh
```

rsync ce dossier vers la machine cible (`REMOTE_USER`/`REMOTE_HOST`/`REMOTE_PATH`, par défaut `julien@raspi-home.local:~/home_services/edge` — voir `../deploiement-raspberry.md`), applique les changements Docker Compose (`COMPOSE_PROFILES` du `.env` distant fait foi, jamais de `--profile` explicite sur la ligne de commande — voir commentaire dans le script), recharge nginx, puis vérifie chaque sous-domaine `*.jvince.dynv6.net` trouvé dans `nginx/conf.d/*.conf` avec un `curl` local sur la machine cible. Idempotent, à relancer après toute modification locale (`compose.yaml`, `nginx/conf.d/*.conf`, `.env`).

## Prérequis

- Docker + Docker Compose (`docker compose version`).
- Un compte [dynv6](https://dynv6.com/) avec une zone créée, et le token HTTP de cette zone (page de la zone, section "HTTP Tokens").

## Phase 0 — reverse-proxy seul, certificat de test auto-signé

Aucune dépendance internet, aucun sous-domaine requis. Objectif : valider que le `reverse-proxy` démarre et sert du TLS avant d'introduire DNS/ACME.

```bash
cd /ws/personal/home_services/edge
cp .env.example .env
docker compose run --rm cert-init   # génère le certificat auto-signé, une seule fois
docker compose up -d reverse-proxy
docker compose logs -f reverse-proxy
```

Test (avertissement de certificat non fiable attendu, c'est un auto-signé) :

```bash
curl -k https://localhost
# → "edge: reverse-proxy operationnel, aucun service backend ne correspond a ce nom d'hote."
```

## Phase 1 — créer les enregistrements dynv6

Dans l'UI dynv6 (zone `jvince.dynv6.net`) — schéma "un enregistrement par service", voir `_plan/plan.md` phase 15 pour le pourquoi :

1. Pour chaque service prévu, créer un enregistrement **A + AAAA** nommé d'après le vrai nom du logiciel (ex. `vaultwarden`, `vikunja`) — valeur initiale sans importance, le sidecar l'écrasera. Pour un service consommé par un client sans bascule IPv4/IPv6 (ex. Minecraft Java) : **AAAA seul**, aucun A du tout.
2. Créer un **CNAME court** par service (ex. `vault` → `vaultwarden`) — c'est ce nom court qui devient le sous-domaine public.
3. Noter le **token HTTP** de la zone (page de la zone, section "HTTP Tokens") — un seul token pour toute la zone, valable aussi pour le DNS-01 d'acme.sh.

Dans `.env` :
```bash
DYNV6_TOKEN=<le token de la zone>
DYNV6_HOSTNAMES=vaultwarden,vikunja        # noms COURTS créés à l'étape 1, A+AAAA
DYNV6_HOSTNAMES_V6ONLY=paper                # AAAA seul (si besoin)
```

## Phase 2 — DDNS centralisé

```bash
docker compose --profile dynv6 up -d sidecar-ddns-dynv6
docker compose logs -f sidecar-ddns-dynv6
```

Vérifier la ligne `dynv6 mis à jour` pour chaque nom (pas d'erreur réseau/token), puis une résolution DNS publique tierce (`dig @1.1.1.1 A/AAAA <nom>.jvince.dynv6.net`) pour confirmer que chaque enregistrement pointe bien vers l'IP courante.

## Phase 3 — émission d'un certificat par sous-domaine (DNS-01, staging d'abord)

Répéter cette séquence pour **chaque** sous-domaine (remplacer `SUBDOMAIN` par le nom court public, ex. `vault`) :

```bash
docker compose --profile dynv6 up -d sidecar-acme   # démarre le conteneur (mode daemon, sans effet immédiat)

# 1) émission en environnement STAGING (obligatoire pour les tests, préserve le rate limit prod)
#    ATTENTION : ne JAMAIS combiner --staging avec --server letsencrypt (--server
#    prend le dessus silencieusement et émet un vrai certificat de production —
#    piège réel rencontré, cf. _plan/plan.md phase 15).
docker compose run --rm sidecar-acme --issue --staging \
  --dns dns_dynv6 \
  -d "SUBDOMAIN.jvince.dynv6.net"

# 2) créer le dossier de destination dans le volume certs — acme.sh --install-cert
#    ne crée PAS les dossiers manquants
docker compose run --rm --entrypoint sh sidecar-acme -c "mkdir -p /certs/SUBDOMAIN"

# 3) installation dans le volume partagé avec nginx, dans un dossier dédié au sous-domaine
docker compose run --rm sidecar-acme --install-cert -d "SUBDOMAIN.jvince.dynv6.net" \
  --fullchain-file /certs/SUBDOMAIN/fullchain.pem \
  --key-file /certs/SUBDOMAIN/privkey.pem
```

`--install-cert` est mémorisé par acme.sh pour ce domaine : les renouvellements automatiques ultérieurs (cron interne, `command: daemon`) réinstalleront seuls le certificat renouvelé au même emplacement, sans action manuelle.

Passage en production, uniquement une fois le DNS et le routage validés en staging pour ce sous-domaine (voir Phase 4) :

```bash
docker compose run --rm sidecar-acme --issue --server letsencrypt --dns dns_dynv6 -d "SUBDOMAIN.jvince.dynv6.net" --force
docker compose run --rm sidecar-acme --install-cert -d "SUBDOMAIN.jvince.dynv6.net" \
  --fullchain-file /certs/SUBDOMAIN/fullchain.pem \
  --key-file /certs/SUBDOMAIN/privkey.pem
docker compose exec reverse-proxy nginx -s reload   # pour ne pas attendre le cycle de 6h
```

**`--server letsencrypt` est obligatoire** en production, sans quoi acme.sh (version récente) part sur ZeroSSL par défaut et échoue faute de compte/email enregistré. Toujours vérifier l'issuer après coup : `curl -v --resolve SUBDOMAIN.jvince.dynv6.net:443:127.0.0.1 https://SUBDOMAIN.jvince.dynv6.net -o /dev/null 2>&1 | grep issuer` doit afficher `O=Let's Encrypt` **sans** `(STAGING)`.

## Phase 4 — enregistrer un service backend dans le routage

Pré-requis côté service backend (contrat d'intégration, `_plan/architecture.md`) : il publie déjà un port HTTP sur l'hôte, sans TLS. Pré-requis côté DNS/certificat : Phases 1-3 déjà faites pour ce sous-domaine — **jamais l'inverse**, un `server{}` référençant un certificat pas encore émis fait planter `reverse-proxy` (crash-loop réel rencontré, cf. `_plan/plan.md` phase 14).

```bash
cd nginx/conf.d
cp _example-service.conf.template <nom-service>.conf
# éditer <nom-service>.conf : remplacer SUBDOMAIN (2 fois) et UPSTREAM_PORT
cd ../..
docker compose exec reverse-proxy nginx -t          # valider la config
docker compose exec reverse-proxy nginx -s reload
```

Test : `curl -k https://SUBDOMAIN.jvince.dynv6.net` (ou depuis un vrai navigateur) doit atteindre le service backend, pas la page par défaut d'edge.

Une fois le routage validé, voir `authentik/_plan/plan.md` pour l'ajouter derrière le portail d'authentification (sauf `bitwarden`, exclu définitivement).

## Arrêt / nettoyage

```bash
docker compose down          # arrête les conteneurs, conserve les volumes (certificats, état acme.sh)
docker compose down -v       # arrête et supprime aussi les volumes (perte des certificats)
```

## Notes

- `DYNV6_TOKEN` est le secret le plus sensible de ce service : il donne la capacité de modifier le DNS et d'émettre des certificats pour **toute la zone**. Ne jamais le committer, ne jamais le dupliquer dans un autre service.
- `sidecar-ddns-dynv6` tourne en `network_mode: host` volontairement (pas sur le réseau par défaut du projet) — le réseau bridge Docker ne fournit pas de sortie IPv6 aux conteneurs.
- Le reload nginx automatique se fait au plus toutes les 6h (voir commentaire dans `compose.yaml`) — après une émission/renouvellement de certificat, forcer un reload immédiat pour test : `docker compose exec reverse-proxy nginx -s reload`.
- Tout conteneur backend sur un réseau bridge Docker (sans IPv6 sortant) qui a besoin de joindre `auth.jvince.dynv6.net` (OIDC, ExtAuth...) doit résoudre ce nom directement vers l'IP LAN du Pi (`extra_hosts` dans son propre `compose.yaml`) — la résolution publique lui est injoignable (A factice + AAAA sans route). Voir `authentik/_plan/plan.md` phase 6 pour le détail et le piège de `host-gateway` (ne fonctionne pas de façon fiable).
