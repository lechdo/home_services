# edge

Point d'entrée Internet unique pour tous les services du dossier racine. Voir `CLAUDE.md` et `_plan/architecture.md` pour le contrat d'intégration, `_plan/plan.md` pour le déroulé complet.

## Où on en est

**Dernier état (2026-08-12)** : Phases 0 à 6 toutes avancées, deux services backend réels enregistrés et fonctionnels :
- Sous-domaines gérés : **`jvince.duckdns.org`** (bitwarden) et **`paperless-jvince.duckdns.org`** (paperless), tous les deux avec un backend réel derrière. `DUCKDNS_SUBDOMAINS=paperless-jvince,jvince` — format de réponse DuckDNS multi-domaines validé (réponse `OK` unique).
- Certificats **staging** Let's Encrypt émis et installés pour les deux sous-domaines.
- `reverse-proxy` tourne en `network_mode: host` (correction découverte à l'usage — `host.docker.internal:host-gateway` ne peut pas atteindre un port publié en `127.0.0.1:PORT`). Tous les `nginx/conf.d/*.conf` utilisent `proxy_pass http://127.0.0.1:PORT`.
- `nginx/conf.d/bitwarden.conf` et `nginx/conf.d/paperless.conf` **testés de bout en bout avec succès** : `https://jvince.duckdns.org` sert Vaultwarden, `https://paperless-jvince.duckdns.org` sert la page de connexion Paperless-ngx.
- Bug pré-existant du websocket bitwarden (`/notifications/hub` → port 3012 supprimé depuis Vaultwarden 1.31) **corrigé** — voir `bitwarden/_plan/plan-migration-edge.md`.
- Tous les conteneurs de ce PC (`edge`, `bitwarden`, `paperless`) actuellement **arrêtés** (`docker compose down`, sans `-v`) — volumes et `.env` conservés.
- **Machine cible finale (Raspberry Pi 3 Model B+, pas le Pi 4 initialement prévu — voir `../deploiement-raspberry.md`) : `edge` + `bitwarden` déployés et validés en staging (2026-08-12)**. `https://jvince.duckdns.org` répond `200` via edge sur le Pi, avec l'IPv6 réelle de la maison publiée par DDNS. `paperless` n'a pas été copié sur cette machine (hors périmètre) — sa route dans `nginx/conf.d/paperless.conf` répond donc `502`, attendu.
- **Reste à faire** : passage en production pour `jvince` (toujours staging, rate limit à préserver), ouverture du pare-feu IPv6 de la box SFR vers le Pi, configuration métier de Paperless (types de documents, tags, RAD/LAD — `paperless/_plan/plan.md` phases 1-6, sur la machine qui l'héberge).

**Pour reprendre** :
```bash
cd /ws/personal/home_services/edge && docker compose up -d
cd /ws/personal/home_services/bitwarden && docker compose up -d
cd /ws/personal/home_services/paperless && docker compose up -d
curl -sSk --resolve jvince.duckdns.org:443:127.0.0.1 https://jvince.duckdns.org/ -o /dev/null -w "bitwarden: %{http_code}\n"
curl -sSk --resolve paperless-jvince.duckdns.org:443:127.0.0.1 https://paperless-jvince.duckdns.org/ -o /dev/null -w "paperless: %{http_code}\n"
```

<details>
<summary>Historique — Phase 0 (reverse-proxy seul, certificat auto-signé)</summary>

Validée réellement le 2026-08-12 : `cert-init` génère le certificat, `reverse-proxy` démarre, `curl -k https://localhost` répond correctement, `nginx -t` valide la config. Tout avait alors été nettoyé (`docker compose down -v`, `.env` supprimé) — l'environnement a été recréé depuis pour les phases suivantes.

</details>

## Prérequis

- Docker + Docker Compose (`docker compose version`).

## Phase 0 — reverse-proxy seul, certificat de test auto-signé

Aucune dépendance internet, aucun sous-domaine DuckDNS requis. Objectif : valider que le `reverse-proxy` démarre et sert du TLS avant d'introduire DNS/ACME.

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

## Phase 1 — créer un sous-domaine DuckDNS

- Se connecter sur https://www.duckdns.org (login via un compte existant, ex. GitHub/Google) — **réutiliser le compte déjà utilisé pour bitwarden** si applicable, ne pas en créer un second.
- Créer un sous-domaine par service prévu (ex. `jvince` déjà existant pour bitwarden, `paperless-jvince` pour paperless — adapter les noms).
- Noter le **token** DuckDNS (unique pour tout le compte, valable pour tous les sous-domaines).

Dans `.env` :
```bash
DUCKDNS_TOKEN=<le token DuckDNS>
DUCKDNS_SUBDOMAINS=jvince   # liste séparée par des virgules, sans le suffixe .duckdns.org
```

## Phase 2 — DDNS centralisé

```bash
docker compose --profile duckdns up -d sidecar-ddns
docker compose logs -f sidecar-ddns
```

Vérifier la ligne `DuckDNS AAAA mis à jour` (pas d'erreur réseau/token). Si plusieurs sous-domaines sont listés dans `DUCKDNS_SUBDOMAINS`, vérifier via une résolution DNS publique tierce que chacun pointe bien vers l'IPv6 courante — le format exact de la réponse DuckDNS pour une mise à jour multi-domaines n'a pas encore été validé en conditions réelles (seul le cas mono-domaine l'a été, sur bitwarden), c'est le premier test à faire ici.

## Phase 3 — émission d'un certificat par sous-domaine (DNS-01, staging d'abord)

Répéter cette séquence pour **chaque** sous-domaine listé dans `DUCKDNS_SUBDOMAINS` (remplacer `SUBDOMAIN` par le label, ex. `jvince`) :

```bash
docker compose --profile duckdns up -d sidecar-acme   # démarre le conteneur (mode daemon, sans effet immédiat)

# 1) émission en environnement STAGING (obligatoire pour les tests, préserve le rate limit prod)
docker compose run --rm sidecar-acme --issue --staging \
  --dns dns_duckdns \
  -d "SUBDOMAIN.duckdns.org"

# 2) créer le dossier de destination dans le volume certs — acme.sh --install-cert
#    ne crée PAS les dossiers manquants (découvert à l'usage, voir plan.md phase 3)
docker compose run --rm --entrypoint sh sidecar-acme -c "mkdir -p /certs/SUBDOMAIN"

# 3) installation dans le volume partagé avec nginx, dans un dossier dédié au sous-domaine
docker compose run --rm sidecar-acme --install-cert -d "SUBDOMAIN.duckdns.org" \
  --fullchain-file /certs/SUBDOMAIN/fullchain.pem \
  --key-file /certs/SUBDOMAIN/privkey.pem
```

`--install-cert` est mémorisé par acme.sh pour ce domaine : les renouvellements automatiques ultérieurs (cron interne, `command: daemon`) réinstalleront seuls le certificat renouvelé au même emplacement, sans action manuelle.

Passage en production, uniquement une fois le DNS et le routage validés en staging pour ce sous-domaine (voir Phase 4 et note plus bas) :

```bash
docker compose run --rm sidecar-acme --issue --server letsencrypt --dns dns_duckdns -d "SUBDOMAIN.duckdns.org" --force
docker compose run --rm sidecar-acme --install-cert -d "SUBDOMAIN.duckdns.org" \
  --fullchain-file /certs/SUBDOMAIN/fullchain.pem \
  --key-file /certs/SUBDOMAIN/privkey.pem
docker compose exec reverse-proxy nginx -s reload   # pour ne pas attendre le cycle de 6h
```

**Correction découverte à l'usage (2026-08-12)** : `--server letsencrypt` est **obligatoire** ici, sans quoi acme.sh (version récente) part sur ZeroSSL par défaut, échoue faute de compte/email enregistré (« Please update your account with an email address first »), et `--install-cert` réinstalle alors silencieusement l'ancien certificat déjà présent (staging) sans erreur visible — piège découvert lors de la bascule en production de `jvince.duckdns.org`, où le premier essai sans `--server letsencrypt` a semblé réussir (`Installing full chain to...`) alors qu'aucun nouveau certificat n'avait été émis. Toujours vérifier l'issuer après coup : `curl -v --resolve SUBDOMAIN.duckdns.org:443:127.0.0.1 https://SUBDOMAIN.duckdns.org -o /dev/null 2>&1 | grep issuer` doit afficher `O=Let's Encrypt` **sans** `(STAGING)`.

## Phase 4 — enregistrer un service backend dans le routage

Pré-requis côté service backend (contrat d'intégration, `_plan/architecture.md`) : il publie déjà un port HTTP sur l'hôte, sans TLS.

```bash
cd nginx/conf.d
cp _example-service.conf.template <nom-service>.conf
# éditer <nom-service>.conf : remplacer SUBDOMAIN (2 fois) et UPSTREAM_PORT
cd ../..
docker compose exec reverse-proxy nginx -t          # valider la config
docker compose exec reverse-proxy nginx -s reload
```

Test : `curl -k https://SUBDOMAIN.duckdns.org` (ou depuis un vrai navigateur) doit atteindre le service backend, pas la page par défaut d'edge.

**Aucun service réel n'est encore enregistré dans ce dépôt** : la migration de bitwarden (`bitwarden/_plan/plan-migration-edge.md`) et l'intégration de paperless (`paperless/_plan/plan.md`, phase 8) sont des étapes séparées, à faire une fois cette Phase 4 validée avec au moins un service de test.

## Arrêt / nettoyage

```bash
docker compose down          # arrête les conteneurs, conserve les volumes (certificats, état acme.sh)
docker compose down -v       # arrête et supprime aussi les volumes (perte des certificats)
```

## Notes

- `DUCKDNS_TOKEN` est le secret le plus sensible de ce service : il donne la capacité de modifier le DNS et d'émettre des certificats pour **tous** les sous-domaines du compte. Ne jamais le committer, ne jamais le dupliquer dans un autre service (cf. `bitwarden/_plan/plan-migration-edge.md`).
- `sidecar-ddns` tourne en `network_mode: host` volontairement (pas sur le réseau par défaut du projet) — le réseau bridge Docker ne fournit pas de sortie IPv6 aux conteneurs. Voir le commentaire dans `compose.yaml`.
- Le reload nginx automatique se fait au plus toutes les 6h (voir commentaire dans `compose.yaml`) — après une émission/renouvellement de certificat, forcer un reload immédiat pour test : `docker compose exec reverse-proxy nginx -s reload`.
- La machine cible finale de bitwarden est aussi celle d'edge : un Raspberry Pi 3 Model B+ (voir `bitwarden/README.md` et `../deploiement-raspberry.md`). Les phases 0-4 y ont été reproduites et validées en staging (2026-08-12).
