#!/usr/bin/env bash
# Autorise rclone à accéder à Google Drive et génère rclone.conf.
#
# La seule étape qui reste réellement manuelle : suivre le lien affiché par
# `rclone authorize` dans un vrai navigateur et se connecter/autoriser l'accès
# à son propre Google Drive. Ce script se contente d'éviter le copier-coller
# manuel du token JSON dans rclone.conf (source d'erreur : virgule oubliée,
# guillemet mal fermé...).
#
# À exécuter sur une machine qui a un navigateur (pas forcément celle qui
# héberge bitwarden en prod) — si ce n'est pas la même machine, copier ensuite
# le rclone.conf généré ici vers bitwarden/ sur la machine cible (ex. scp vers
# le Raspberry Pi), voir _plan/plan-sauvegarde.md.
#
# Usage : ./authorize-gdrive.sh [--force]
#   --force   écrase un rclone.conf existant (sinon le script refuse)

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(dirname "$script_dir")"
rclone_conf="$service_dir/rclone.conf"
rclone_example="$service_dir/rclone.conf.example"

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
fi

if [[ -f "$rclone_conf" && "$force" -ne 1 ]]; then
  echo "Erreur : $rclone_conf existe déjà. Relancer avec --force pour l'écraser." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Erreur : docker introuvable sur cette machine." >&2
  exit 1
fi

echo "Ouverture du flux d'autorisation rclone <-> Google Drive."
echo "Un lien va s'afficher ci-dessous : ouvre-le dans un navigateur, connecte-toi"
echo "et autorise l'accès à ton propre Google Drive."
echo

authorize_log="$(mktemp)"
trap 'rm -f "$authorize_log"' EXIT

# -it obligatoire : rclone authorize attend un vrai terminal interactif.
docker run --rm -it rclone/rclone authorize "drive" | tee "$authorize_log"

token_json="$(grep -o '{"access_token".*}' "$authorize_log" | tail -n1 || true)"

if [[ -z "$token_json" ]]; then
  echo >&2
  echo "Erreur : impossible de retrouver le bloc JSON du token dans la sortie ci-dessus." >&2
  echo "Recopie-le manuellement dans $rclone_conf (voir $rclone_example)." >&2
  exit 1
fi

sed "s#^token = .*#token = ${token_json}#" "$rclone_example" > "$rclone_conf"

echo
echo "rclone.conf généré : $rclone_conf"
echo "Si cette machine n'est pas celle qui héberge bitwarden en prod, copie ce"
echo "fichier vers le dossier bitwarden/ de la machine cible avant d'exécuter"
echo "setup-backup.sh là-bas."
