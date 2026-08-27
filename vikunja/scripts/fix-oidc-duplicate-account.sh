#!/usr/bin/env bash
# Corrige un compte Vikunja "fantôme" créé par une connexion OIDC (authentik)
# dont le (issuer, subject) ne correspondait à aucun compte Vikunja existant.
#
# Contexte et protocole complet : voir fix-oidc-duplicate-account.md dans ce
# même dossier avant d'utiliser ce script — en particulier comment identifier
# quel compte est "à garder" et lequel est le "fantôme" avant de lancer ceci.
#
# Ce script :
#   1. sauvegarde le fichier SQLite (vikunja.db + .db-wal/.db-shm) avant toute
#      modification ;
#   2. arrête brièvement le conteneur vikunja (coupure de quelques secondes) ;
#   3. relie l'identité OIDC (issuer/subject) du compte fantôme au compte à
#      garder, dans un conteneur jetable python:3-alpine monté sur le même
#      volume nommé (jamais en éditant le fichier à la main sur l'hôte) ;
#   4. supprime le compte fantôme et son projet "Inbox" par défaut vide —
#      seulement après avoir vérifié qu'il ne contient AUCUNE donnée réelle
#      (projet non-défaut, tâche, appartenance à une équipe, partage, filtre
#      enregistré, favori, webhook, jeton API, commentaire, assignation,
#      réaction, notification, lien de partage). Si une seule de ces
#      vérifications échoue, le script s'arrête sans rien supprimer — la
#      fusion doit alors être faite au cas par cas, pas automatiquement ;
#   5. redémarre le conteneur.
#
# Usage (à exécuter SUR la machine qui héberge le conteneur vikunja, ex.
# `ssh julien@raspi-home.local`, depuis n'importe quel dossier) :
#
#   ./fix-oidc-duplicate-account.sh <compte_a_garder> <compte_fantome>
#
# Exemple réel (2026-08-27) :
#   ./fix-oidc-duplicate-account.sh julien vaguely-loved-pelican
#
# Variables surchargeables si la config diffère de la prod actuelle :
#   VIKUNJA_COMPOSE_DIR (défaut: ~/home_services/vikunja)
#   VIKUNJA_CONTAINER   (défaut: vikunja-vikunja-1)
#   VIKUNJA_DATA_VOLUME (défaut: vikunja_data)

set -euo pipefail

KEEP_USERNAME="${1:?Usage: $0 <compte_a_garder> <compte_fantome>}"
DUP_USERNAME="${2:?Usage: $0 <compte_a_garder> <compte_fantome>}"
COMPOSE_DIR="${VIKUNJA_COMPOSE_DIR:-$HOME/home_services/vikunja}"
CONTAINER="${VIKUNJA_CONTAINER:-vikunja-vikunja-1}"
VOLUME="${VIKUNJA_DATA_VOLUME:-vikunja_data}"

echo "== 1. Sauvegarde de la base avant toute modification =="
ts=$(date +%Y%m%d-%H%M%S)
backup_dir="$HOME/vikunja-merge-backup"
mkdir -p "$backup_dir"
docker cp "$CONTAINER:/db/vikunja.db" "$backup_dir/vikunja-$ts.db"
docker cp "$CONTAINER:/db/vikunja.db-wal" "$backup_dir/vikunja-$ts.db-wal" 2>/dev/null || true
docker cp "$CONTAINER:/db/vikunja.db-shm" "$backup_dir/vikunja-$ts.db-shm" 2>/dev/null || true
echo "Sauvegarde: $backup_dir/vikunja-$ts.db (+ .db-wal/.db-shm si présents)"

echo
echo "== 2. État actuel des comptes =="
docker exec "$CONTAINER" ./vikunja user list

echo
echo "== 3. Arrêt du conteneur vikunja (coupure de quelques secondes) =="
(cd "$COMPOSE_DIR" && docker compose stop vikunja)

echo
echo "== 4. Application de la correction (conteneur jetable sur le volume $VOLUME) =="
docker run --rm -i -v "$VOLUME:/db" python:3-alpine python3 - "$KEEP_USERNAME" "$DUP_USERNAME" <<'PYEOF'
import sqlite3
import sys

keep_username, dup_username = sys.argv[1], sys.argv[2]
con = sqlite3.connect("/db/vikunja.db")
con.execute("PRAGMA busy_timeout = 5000")
cur = con.cursor()


def get_user(username):
    cur.execute("SELECT id, issuer, subject FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"Compte introuvable: {username}")
    return row


keep_id, keep_issuer, keep_subject = get_user(keep_username)
dup_id, dup_issuer, dup_subject = get_user(dup_username)

if keep_id == dup_id:
    sys.exit("Abandon : les deux noms de compte désignent le même id.")

if keep_issuer not in ("local", ""):
    sys.exit(
        f"Abandon : le compte à garder ({keep_username}, id={keep_id}) a déjà un "
        f"issuer OIDC ({keep_issuer!r}) différent de 'local' — vérification manuelle requise."
    )
if not dup_issuer or dup_issuer == "local":
    sys.exit(
        f"Abandon : le compte fantôme ({dup_username}, id={dup_id}) n'est pas un "
        f"compte OIDC (issuer={dup_issuer!r}) — ce script ne traite que ce cas précis "
        f"(compte OIDC orphelin sans donnée)."
    )

# --- garde-fous : le compte fantôme ne doit contenir AUCUNE donnée réelle ---
checks = {
    "projet(s) hors 'Inbox' par défaut": (
        "SELECT COUNT(*) FROM projects WHERE owner_id = ? AND title != 'Inbox'", (dup_id,)
    ),
    "tâche(s) dans son Inbox par défaut": (
        "SELECT COUNT(*) FROM tasks WHERE project_id IN "
        "(SELECT id FROM projects WHERE owner_id = ?)", (dup_id,)
    ),
    "tâche(s) créée(s) par ce compte": (
        "SELECT COUNT(*) FROM tasks WHERE created_by_id = ?", (dup_id,)
    ),
    "assignation(s) à des tâches": (
        "SELECT COUNT(*) FROM task_assignees WHERE user_id = ?", (dup_id,)
    ),
    "commentaire(s)": (
        "SELECT COUNT(*) FROM task_comments WHERE author_id = ?", (dup_id,)
    ),
    "réaction(s)": (
        "SELECT COUNT(*) FROM reactions WHERE user_id = ?", (dup_id,)
    ),
    "appartenance à une équipe": (
        "SELECT COUNT(*) FROM team_members WHERE user_id = ?", (dup_id,)
    ),
    "partage(s) de projet reçus": (
        "SELECT COUNT(*) FROM users_projects WHERE user_id = ?", (dup_id,)
    ),
    "filtre(s) enregistré(s)": (
        "SELECT COUNT(*) FROM saved_filters WHERE owner_id = ?", (dup_id,)
    ),
    "favori(s)": (
        "SELECT COUNT(*) FROM favorites WHERE user_id = ?", (dup_id,)
    ),
    "webhook(s)": (
        "SELECT COUNT(*) FROM webhooks WHERE user_id = ?", (dup_id,)
    ),
    "jeton(s) API": (
        "SELECT COUNT(*) FROM api_tokens WHERE owner_id = ?", (dup_id,)
    ),
    "notification(s)": (
        "SELECT COUNT(*) FROM notifications WHERE notifiable_id = ?", (dup_id,)
    ),
    "lien(s) de partage créé(s)": (
        "SELECT COUNT(*) FROM link_shares WHERE shared_by_id = ?", (dup_id,)
    ),
}
problems = []
for label, (sql, params) in checks.items():
    cur.execute(sql, params)
    n = cur.fetchone()[0]
    if n:
        problems.append(f"  - {label}: {n}")

if problems:
    sys.exit(
        f"Abandon : le compte fantôme ({dup_username}, id={dup_id}) contient des "
        f"données réelles — ce script ne supprime rien automatiquement dans ce cas :\n"
        + "\n".join(problems)
        + "\nTraitement manuel requis (réassignation au cas par cas des lignes listées "
        "ci-dessus vers le compte à garder, avant suppression)."
    )

print(f"Compte à garder : {keep_username} (id={keep_id})")
print(f"Compte fantôme  : {dup_username} (id={dup_id}, issuer={dup_issuer})")
print("Vérifications OK : le compte fantôme ne contient aucune donnée réelle.")

# --- 1. relier l'identité OIDC du fantôme au compte à garder ---
cur.execute(
    "UPDATE users SET issuer = ?, subject = ? WHERE id = ?",
    (dup_issuer, dup_subject, keep_id),
)

# --- 2. supprimer les traces du compte fantôme (dans l'ordre des dépendances) ---
cur.execute("SELECT id FROM projects WHERE owner_id = ?", (dup_id,))
dup_project_ids = [r[0] for r in cur.fetchall()]
for pid in dup_project_ids:
    cur.execute("SELECT id FROM project_views WHERE project_id = ?", (pid,))
    view_ids = [r[0] for r in cur.fetchall()]
    for vid in view_ids:
        cur.execute("DELETE FROM buckets WHERE project_view_id = ?", (vid,))
        cur.execute("DELETE FROM task_buckets WHERE project_view_id = ?", (vid,))
        cur.execute("DELETE FROM task_positions WHERE project_view_id = ?", (vid,))
    cur.execute("DELETE FROM project_views WHERE project_id = ?", (pid,))
    cur.execute("DELETE FROM projects WHERE id = ?", (pid,))

cur.execute("DELETE FROM sessions WHERE user_id = ?", (dup_id,))
cur.execute("DELETE FROM user_tokens WHERE user_id = ?", (dup_id,))
cur.execute("DELETE FROM totp WHERE user_id = ?", (dup_id,))
cur.execute("DELETE FROM users WHERE id = ?", (dup_id,))

con.commit()
con.close()
print("Correction appliquée.")
PYEOF

echo
echo "== 5. Redémarrage du conteneur vikunja =="
(cd "$COMPOSE_DIR" && docker compose up -d vikunja)
sleep 2

echo
echo "== 6. État final des comptes =="
docker exec "$CONTAINER" ./vikunja user list

echo
echo "== Terminé =="
echo "Reconnecte-toi via authentik en tant que '$KEEP_USERNAME' : le prochain login OIDC doit désormais retomber directement sur ce compte."
