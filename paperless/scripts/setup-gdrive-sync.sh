#!/usr/bin/env bash
# Finalise la mise en place de la synchronisation Google Drive -> consume
# (Phase 1), une fois rclone.conf généré (voir authorize-gdrive.sh).
#
# Idempotent : peut être relancé sans risque. Vérifie que le dossier Drive
# ciblé est bien lisible (lecture seule, aucune écriture) avant de démarrer le
# sidecar. Voir _plan/plan.md phase 1 et README.md pour le détail.
#
# Usage : ./setup-gdrive-sync.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(dirname "$script_dir")"
cd "$service_dir"

fail() { echo "Erreur : $1" >&2; exit 1; }

[[ -f .env ]] || fail ".env introuvable — copier .env.example en .env et le compléter d'abord."
[[ -f rclone.conf ]] || fail "rclone.conf introuvable — lancer d'abord ./scripts/authorize-gdrive.sh (ou le copier depuis la machine où il a été généré)."

if grep -q 'token = {"access_token":"\.\.\.' rclone.conf 2>/dev/null; then
  fail "rclone.conf contient encore le token d'exemple — lancer ./scripts/authorize-gdrive.sh."
fi

# shellcheck disable=SC1091
source .env

[[ -n "${GDRIVE_REMOTE_PATH:-}" ]] || fail "GDRIVE_REMOTE_PATH absent de .env."
[[ "$GDRIVE_REMOTE_PATH" != "gdrive:" ]] || fail "GDRIVE_REMOTE_PATH pointe sur la racine du Drive (gdrive:) — préciser un sous-dossier dédié dans .env."

mkdir -p consume

echo "Préconditions OK. Vérification d'accès en lecture à $GDRIVE_REMOTE_PATH..."
if ! docker run --rm \
    -e RCLONE_CONFIG=/rclone.conf \
    -v "$(pwd)/rclone.conf:/rclone.conf:ro" \
    rclone/rclone lsf "$GDRIVE_REMOTE_PATH" >/tmp/gdrive-sync-check.$$ 2>&1; then
  cat /tmp/gdrive-sync-check.$$ >&2
  rm -f /tmp/gdrive-sync-check.$$
  fail "impossible de lister $GDRIVE_REMOTE_PATH — vérifier que le dossier existe dans le Drive autorisé et que le nom est exact."
fi
file_count="$(wc -l < /tmp/gdrive-sync-check.$$ | tr -d ' ')"
rm -f /tmp/gdrive-sync-check.$$
echo "Accès en lecture OK ($file_count élément(s) trouvé(s) dans $GDRIVE_REMOTE_PATH)."

if grep -qE '^COMPOSE_PROFILES=gdrive-sync' .env; then
  echo "COMPOSE_PROFILES=gdrive-sync déjà actif."
elif grep -qE '^#\s*COMPOSE_PROFILES=gdrive-sync' .env; then
  sed -i 's/^#\s*COMPOSE_PROFILES=gdrive-sync/COMPOSE_PROFILES=gdrive-sync/' .env
  echo "COMPOSE_PROFILES=gdrive-sync activé dans .env."
else
  echo "COMPOSE_PROFILES=gdrive-sync" >> .env
  echo "COMPOSE_PROFILES=gdrive-sync ajouté à .env."
fi

echo "Démarrage de sidecar-gdrive-sync..."
docker compose up -d sidecar-gdrive-sync

cat <<'EOF'

sidecar-gdrive-sync démarré (synchronisation toutes les 5 minutes, premier
passage immédiat).
Suivre la première synchronisation :
  docker compose logs -f sidecar-gdrive-sync

Vérifier ensuite dans l'UI Paperless (https://paperless-jvince.duckdns.org ou
127.0.0.1:8082) que les documents du dossier Drive apparaissent bien, OCR
fait, sans action manuelle — objectif de sortie de la Phase 1.
EOF
