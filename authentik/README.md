# authentik

Fournisseur SSO / forward-auth pour les services routés par `edge`, sauf `bitwarden`. Voir `CLAUDE.md` et `_plan/plan.md` avant toute modification.

## Où on en est

**Phase 0 (squelette)** : `compose.yaml` créé (`postgresql`, `redis`, `server`, `worker`) — pas encore déployé, pas encore de sous-domaine `edge`, pas encore de service protégé. Hébergement prévu sur le second serveur physique (`192.168.1.109`), qui reste désormais allumé en permanence (cf. `_plan/plan.md`).

## Prérequis

- Docker + Docker Compose, sur `192.168.1.109` (pas le Raspberry Pi).
- Vérifier la dernière version d'authentik avant le premier déploiement (https://github.com/goauthentik/authentik/releases) et mettre à jour le tag d'image dans `compose.yaml` si besoin (ne jamais utiliser `latest`, cf. commentaire dans `compose.yaml`).

## Phase 0/1 — squelette et validation locale

```bash
cd /chemin/vers/authentik   # sur 192.168.1.109
cp .env.example .env
# compléter AUTHENTIK_SECRET_KEY et AUTHENTIK_PG_PASSWORD (commandes dans .env.example)
docker compose up -d
docker compose logs -f server   # attendre "Startup complete"
```

Premier compte admin : ouvrir `http://192.168.1.109:8089/if/flow/initial-setup/` (en local, avant tout sous-domaine public) et suivre l'assistant intégré.

## Phase 2+ — intégration edge, sous-domaine public, services protégés

Voir `_plan/plan.md` — pas encore implémenté à ce stade.

## Arrêt / nettoyage

```bash
docker compose down          # conserve les volumes (base, secrets internes)
docker compose down -v       # supprime aussi les volumes (perte des comptes/config)
```
