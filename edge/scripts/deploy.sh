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
compose_profile_args=()
if [[ "${COMPOSE_PROFILES:-}" == *duckdns* ]]; then
  compose_profile_args=(--profile duckdns)
fi
ssh "$REMOTE" "cd $REMOTE_PATH && docker compose ${compose_profile_args[*]} up -d"

echo "== reload nginx (prend en compte un nginx/conf.d/*.conf modifié) =="
ssh "$REMOTE" "cd $REMOTE_PATH && docker compose exec reverse-proxy nginx -t && docker compose exec reverse-proxy nginx -s reload"

echo "== vérification de bout en bout =="
if [[ -z "${DUCKDNS_SUBDOMAINS:-}" ]]; then
  echo "DUCKDNS_SUBDOMAINS est vide dans .env, rien à vérifier." >&2
else
  IFS=',' read -ra subdomains <<< "$DUCKDNS_SUBDOMAINS"
  for label in "${subdomains[@]}"; do
    domain="${label}.duckdns.org"
    ssh "$REMOTE" "curl -sSk --resolve $domain:443:127.0.0.1 https://$domain/ -o /dev/null -w '$domain: %{http_code}\n'"
  done
fi

echo "Déploiement terminé."
