#!/usr/bin/env bash
# Déploie ce service (edge) sur la machine de production (le Raspberry Pi,
# voir ../../deploiement-raspberry.md) : rsync des fichiers, application des
# changements côté Docker Compose, reload nginx, et vérification de bout en
# bout via curl sur chaque sous-domaine configuré.
#
# Idempotent : peut être relancé sans risque (rsync ne fait que synchroniser,
# `docker compose up -d` ne recrée que ce qui a changé, `nginx -s reload` est
# sans coupure).
#
# Usage : ./deploy.sh
# Variables surchargeables : REMOTE_USER, REMOTE_HOST, REMOTE_PATH

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(dirname "$script_dir")"
cd "$service_dir"

fail() { echo "Erreur : $1" >&2; exit 1; }

REMOTE_USER="${REMOTE_USER:-julien}"
REMOTE_HOST="${REMOTE_HOST:-raspi-home.local}"
REMOTE_PATH="${REMOTE_PATH:-~/home_services/edge}"
REMOTE="$REMOTE_USER@$REMOTE_HOST"

[[ -f .env ]] || fail ".env introuvable — copier .env.example en .env et le compléter d'abord."

echo "== rsync vers $REMOTE:$REMOTE_PATH =="
rsync -avz --exclude '.git' ./ "$REMOTE:$REMOTE_PATH/"

echo "== application des changements Docker Compose =="
# shellcheck disable=SC1091
source .env
# Pas de "--profile" explicite ici : ça écraserait COMPOSE_PROFILES du .env
# distant au lieu de le compléter (bug réel constaté le 2026-08-23 — la
# valeur "duckdns,dynv6" du .env était ignorée dès qu'un "--profile duckdns"
# était passé sur la ligne de commande, empêchant sidecar-ddns-dynv6 de
# démarrer). `docker compose up -d`, sans argument, lit COMPOSE_PROFILES
# depuis .env tout seul — c'est la source de vérité unique désormais.
ssh "$REMOTE" "cd $REMOTE_PATH && docker compose up -d"

echo "== reload nginx (prend en compte un nginx/conf.d/*.conf modifié) =="
ssh "$REMOTE" "cd $REMOTE_PATH && docker compose exec reverse-proxy nginx -t && docker compose exec reverse-proxy nginx -s reload"

echo "== vérification de bout en bout =="
# Domaines lus directement dans nginx/conf.d/*.conf (source de vérité,
# depuis le retrait de DuckDNS — plus de liste à part type DUCKDNS_SUBDOMAINS
# à maintenir en double, edge/_plan/plan.md phase 15) plutôt qu'une liste
# figée ici, qui aurait pu se désynchroniser en silence à chaque nouveau
# service ajouté/retiré.
mapfile -t domains < <(grep -hoE 'server_name +[a-zA-Z0-9.-]+\.jvince\.dynv6\.net' nginx/conf.d/*.conf | awk '{print $2}' | sort -u)
if [[ ${#domains[@]} -eq 0 ]]; then
  echo "Aucun server_name *.jvince.dynv6.net trouvé dans nginx/conf.d/, rien à vérifier." >&2
else
  for domain in "${domains[@]}"; do
    ssh "$REMOTE" "curl -sSk --resolve $domain:443:127.0.0.1 https://$domain/ -o /dev/null -w '$domain: %{http_code}\n'"
  done
fi

echo "Déploiement terminé."
