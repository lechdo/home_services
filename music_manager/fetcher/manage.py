#!/usr/bin/env python3
"""Gestion des comptes du fetcher — pas d'auto-inscription, comptes créés à
la main (même schéma que minecraft/panel/manage.py). Usage (depuis l'hôte) :
  docker compose exec fetcher python manage.py add alice
  docker compose exec fetcher python manage.py remove alice
"""
import getpass
import json
import os
import sys

import bcrypt

USERS_FILE = "/app/data/users.json"


def load():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    return {}


def save(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def add_user(username):
    password = getpass.getpass(f"Mot de passe pour {username}: ")
    confirm = getpass.getpass("Confirmer: ")
    if password != confirm:
        print("Les mots de passe ne correspondent pas.")
        sys.exit(1)
    users = load()
    users[username] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    save(users)
    print(f"Utilisateur « {username} » ajouté/mis à jour.")


def remove_user(username):
    users = load()
    users.pop(username, None)
    save(users)
    print(f"Utilisateur « {username} » supprimé (si présent).")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("add", "remove"):
        print("Usage: manage.py add|remove <username>")
        sys.exit(1)
    {"add": add_user, "remove": remove_user}[sys.argv[1]](sys.argv[2])
