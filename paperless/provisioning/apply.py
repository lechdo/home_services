#!/usr/bin/env python3
"""Applique provisioning/seed.json à une instance Paperless-ngx en marche.

Idempotent : crée les entrées manquantes, met à jour celles dont les champs
déclarés dans le seed diffèrent, ne touche jamais à celles qui sont déjà
conformes, et ne supprime jamais une entrée absente du seed (voir
protocole-donnees.md — pas de destruction implicite).

Usage :
    set -a && source .env && set +a
    python3 provisioning/apply.py [--seed provisioning/seed.json] [--dry-run]

Ne dépend que de la bibliothèque standard (aucun `pip install` requis) pour
rester exécutable sur n'importe quelle machine cible sans préparation.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENDPOINTS = {
    "document_types": "/api/document_types/",
    "tags": "/api/tags/",
    "custom_fields": "/api/custom_fields/",
    "workflows": "/api/workflows/",
}


def get_token(base_url, username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{base_url}/api/token/", data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["token"]


def api_request(base_url, token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base_url}{path}", data=data, method=method)
    req.add_header("Authorization", f"Token {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp) if resp.status != 204 else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()}") from e


def list_all(base_url, token, path):
    items = []
    while path:
        page = api_request(base_url, token, "GET", path)
        items.extend(page["results"])
        next_url = page["next"]
        path = next_url.replace(base_url, "") if next_url else None
    return items


def needs_update(existing, desired):
    return any(existing.get(k) != v for k, v in desired.items() if k != "name")


def matches_subset(existing, desired):
    """True si chaque champ de `desired` correspond au même champ dans
    `existing` (les champs supplémentaires de `existing` — valeurs par défaut
    renvoyées par l'API, id générés... — sont ignorés). Compare récursivement
    listes/dicts imbriqués. Utilisé pour les ressources imbriquées (workflows)
    où l'API renvoie beaucoup plus de champs que ce qu'on déclare dans le
    seed — une égalité stricte comme `needs_update` déclencherait un faux
    "à mettre à jour" à chaque exécution."""
    if isinstance(desired, dict):
        if not isinstance(existing, dict):
            return False
        return all(k in existing and matches_subset(existing[k], v) for k, v in desired.items())
    if isinstance(desired, list):
        if not isinstance(existing, list) or len(existing) != len(desired):
            return False
        return all(matches_subset(e, d) for e, d in zip(existing, desired))
    return existing == desired


def workflow_needs_update(existing, desired):
    return not matches_subset(existing, {k: v for k, v in desired.items() if k != "name"})


def reconcile(base_url, token, endpoint, desired_entries, dry_run, needs_update_fn=needs_update):
    existing_by_name = {e["name"]: e for e in list_all(base_url, token, endpoint)}
    created, updated, unchanged = 0, 0, 0
    for entry in desired_entries:
        name = entry["name"]
        existing = existing_by_name.get(name)
        if existing is None:
            created += 1
            print(f"  + créer {name!r}" + (" (dry-run)" if dry_run else ""))
            if not dry_run:
                api_request(base_url, token, "POST", endpoint, entry)
        elif needs_update_fn(existing, entry):
            updated += 1
            print(f"  ~ mettre à jour {name!r}" + (" (dry-run)" if dry_run else ""))
            if not dry_run:
                api_request(base_url, token, "PATCH", f"{endpoint}{existing['id']}/", entry)
        else:
            unchanged += 1
    return created, updated, unchanged


NEEDS_UPDATE_FNS = {"workflows": workflow_needs_update}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default=os.path.join(os.path.dirname(__file__), "seed.json"))
    parser.add_argument("--base-url", default=os.environ.get("PAPERLESS_BASE_URL", "http://127.0.0.1:8082"))
    parser.add_argument("--dry-run", action="store_true", help="n'écrit rien, affiche seulement ce qui serait fait")
    args = parser.parse_args()

    username = os.environ.get("PAPERLESS_ADMIN_USER")
    password = os.environ.get("PAPERLESS_ADMIN_PASSWORD")
    if not username or not password:
        sys.exit("PAPERLESS_ADMIN_USER / PAPERLESS_ADMIN_PASSWORD doivent être exportées (ex: set -a && source .env && set +a)")

    with open(args.seed, encoding="utf-8") as f:
        seed = json.load(f)

    token = get_token(args.base_url, username, password)

    totals = {"created": 0, "updated": 0, "unchanged": 0}
    for key, endpoint in ENDPOINTS.items():
        if key not in seed:
            continue
        print(f"{key}:")
        c, u, n = reconcile(args.base_url, token, endpoint, seed[key], args.dry_run, NEEDS_UPDATE_FNS.get(key, needs_update))
        totals["created"] += c
        totals["updated"] += u
        totals["unchanged"] += n

    print(f"\nTotal : {totals['created']} créé(s), {totals['updated']} mis à jour, {totals['unchanged']} déjà conforme(s).")


if __name__ == "__main__":
    main()
