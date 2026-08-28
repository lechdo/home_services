# outline

Wiki personnel auto-hébergé (Outline). Voir `CLAUDE.md` et `_plan/plan.md` avant toute modification.

## Où on en est

**Phases 0-3 déployées et validées en production (2026-08-28)** : `outline` + `postgres` + `redis` tournent sur `192.168.1.109:8090`, routés par `edge` sous `https://doc.jvince.dynv6.net` (certificat Let's Encrypt de production), OIDC authentik configuré et validé jusqu'à la redirection (`_plan/plan.md`). **Reste à faire** : test de connexion réel par `julien`/`virginie` (interactif), et la sauvegarde (Phase 4).

## Prérequis

- Docker + Docker Compose, sur `192.168.1.109` (pas le Raspberry Pi).
- Vérifier la dernière version stable d'outline avant le premier déploiement (https://github.com/outline/outline/releases) et mettre à jour le tag d'image dans `compose.yaml` si besoin (ne jamais utiliser `latest`).

## Phase 0/1 — squelette et validation locale

```bash
cd /chemin/vers/outline   # sur 192.168.1.109
cp .env.example .env
# compléter OUTLINE_SECRET_KEY, OUTLINE_UTILS_SECRET, OUTLINE_PG_PASSWORD
# (commandes dans .env.example) ; OIDC_OUTLINE_CLIENT_SECRET peut rester
# vide tant que la Phase 3 n'est pas commencée (outline démarre sans, la
# connexion OIDC échouera juste tant que ce n'est pas rempli des deux côtés)
docker compose up -d
docker compose logs -f outline   # attendre que le serveur soit prêt
```

Validation en local (avant tout sous-domaine public) : `http://192.168.1.109:8090`.

## Phase 2+ — sous-domaine edge, SSO authentik, sauvegarde

Voir `_plan/plan.md` — pas encore implémenté à ce stade (fichiers de configuration déjà préparés : `edge/nginx/conf.d/outline.conf`, `authentik/provisioning/oidc-outline.yaml`, mais nécessitent encore : création manuelle de l'enregistrement dynv6 + CNAME `doc`, génération réelle des secrets, déploiement sur `192.168.1.109`, et test de connexion réel par `julien`/`virginie`).

## Arrêt / nettoyage

```bash
docker compose down          # conserve les volumes (base, documents, secrets internes)
docker compose down -v       # supprime aussi les volumes (perte du wiki)
```
