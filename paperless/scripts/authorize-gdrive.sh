#!/usr/bin/env bash
# Autorise rclone à *lire* le Google Drive de l'utilisateur (scope
# drive.readonly) et génère rclone.conf, pour la synchronisation
# unidirectionnelle Drive -> consume (Phase 1, cf. _plan/plan.md).
#
# Script indépendant de bitwarden/scripts/authorize-gdrive.sh (même principe,
# copie propre à ce service — cf. CLAUDE.md racine, aucun script partagé entre
# services) : celui-ci demande explicitement le scope "drive.readonly" et non
# "drive" (accès complet), pour qu'il soit structurellement impossible à ce
# service d'écrire sur le Drive de l'utilisateur — cohérent avec la contrainte
# d'immutabilité de la source.
#
# La seule étape qui reste réellement manuelle : suivre le lien affiché par
# `rclone authorize` dans un vrai navigateur et se connecter/autoriser l'accès
# (en lecture) à son propre Google Drive.
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

echo "Ouverture du flux d'autorisation rclone <-> Google Drive (lecture seule)."
echo "Un lien va s'afficher ci-dessous : ouvre-le dans un navigateur, connecte-toi"
echo "et autorise l'accès en LECTURE à ton propre Google Drive."
echo

authorize_log="$(mktemp)"
trap 'rm -f "$authorize_log"' EXIT

# -it obligatoire : rclone authorize attend un vrai terminal interactif.
# --drive-scope drive.readonly : demande le consentement Google en lecture
# seule (pas "drive", qui donnerait un accès complet en écriture).
docker run --rm -it rclone/rclone authorize "drive" --drive-scope drive.readonly | tee "$authorize_log"

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
echo "Si cette machine n'est pas celle qui héberge paperless en prod, copie ce"
echo "fichier vers le dossier paperless/ de la machine cible avant d'exécuter"
echo "setup-gdrive-sync.sh là-bas."
