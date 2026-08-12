#!/usr/bin/env bash
# Finalise la mise en place de la sauvegarde restic+rclone (sidecar-backup),
# une fois rclone.conf généré (voir authorize-gdrive.sh).
#
# Idempotent : peut être relancé sans risque (n'écrase rien, ne réinitialise
# pas un dépôt restic déjà initialisé). Voir _plan/plan-sauvegarde.md pour le
# détail du mécanisme.
#
# Usage : ./setup-backup.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(dirname "$script_dir")"
cd "$service_dir"

fail() { echo "Erreur : $1" >&2; exit 1; }

[[ -f .env ]] || fail ".env introuvable — copier .env.example en .env et le compléter d'abord."
[[ -f rclone.conf ]] || fail "rclone.conf introuvable — lancer d'abord ./authorize-gdrive.sh (ou le copier depuis la machine où il a été généré)."

if grep -q 'token = {"access_token":"\.\.\.' rclone.conf 2>/dev/null; then
  fail "rclone.conf contient encore le token d'exemple — lancer ./authorize-gdrive.sh."
fi

# shellcheck disable=SC1091
source .env

[[ -n "${RESTIC_PASSWORD:-}" ]] || fail "RESTIC_PASSWORD absent de .env."
[[ "$RESTIC_PASSWORD" != changeme* ]] || fail "RESTIC_PASSWORD est encore la valeur d'exemple dans .env."
[[ -n "${RESTIC_REPOSITORY:-}" ]] || fail "RESTIC_REPOSITORY absent de .env."

echo "Préconditions OK (rclone.conf présent, secrets renseignés)."

if grep -qE '^COMPOSE_PROFILES=backup' .env; then
  echo "COMPOSE_PROFILES=backup déjà actif."
elif grep -qE '^#\s*COMPOSE_PROFILES=backup' .env; then
  sed -i 's/^#\s*COMPOSE_PROFILES=backup/COMPOSE_PROFILES=backup/' .env
  echo "COMPOSE_PROFILES=backup activé dans .env."
else
  echo "COMPOSE_PROFILES=backup" >> .env
  echo "COMPOSE_PROFILES=backup ajouté à .env."
fi

echo "Vérification de l'état du dépôt restic (peut prendre quelques secondes, restic s'installe dans le conteneur)..."
if docker compose run --rm --entrypoint sh sidecar-backup \
    -c "apk add --no-cache restic >/dev/null 2>&1 && restic snapshots >/dev/null 2>&1"; then
  echo "Dépôt restic déjà initialisé — pas de restic init nécessaire."
else
  echo "Dépôt restic non initialisé — initialisation..."
  docker compose run --rm --entrypoint sh sidecar-backup \
    -c "apk add --no-cache restic >/dev/null 2>&1 && restic init"
  echo "Dépôt restic initialisé."
fi

echo "Démarrage de sidecar-backup..."
docker compose up -d sidecar-backup

cat <<'EOF'

sidecar-backup démarré (backup quotidien, premier passage immédiat).
Suivre le premier backup :
  docker compose logs -f sidecar-backup

Rappel : tester la restauration au moins une fois avant de faire confiance au
dispositif (voir _plan/plan-sauvegarde.md §5) — pas encore fait à ce stade.
EOF
