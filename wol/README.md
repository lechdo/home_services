# wol

Relais Wake-on-LAN : réveille l'Optiplex depuis un smartphone Android, y compris depuis l'extérieur du réseau domestique. Voir `CLAUDE.md` et `_plan/plan.md` pour le contexte complet et l'état d'avancement par phase.

## Démarrage local

```bash
cp .env.example .env
# éditer .env : WOL_TARGET_MAC (adresse MAC de l'Optiplex), WOL_AUTH_TOKEN (openssl rand -hex 32)
docker compose up -d
curl http://127.0.0.1:8085/health          # -> ok
curl -X POST http://127.0.0.1:8085/wake -H "Authorization: Bearer <token>"
```

## Configuration Android (app HTTP Shortcuts)

1. Installer **HTTP Shortcuts** (Play Store ou F-Droid).
2. Créer un nouveau raccourci :
   - Méthode : `POST`
   - URL : `https://wol-jvince.duckdns.org/wake` (une fois la Phase 4/6 du plan faite ; en local sur le même wifi, `http://<ip-du-pi>:8085/wake` suffit pour tester avant l'intégration edge)
   - Onglet "Requête" → Headers → ajouter `Authorization: Bearer <token>` (le même que `WOL_AUTH_TOKEN`)
3. Ajouter le raccourci à l'écran d'accueil (bouton dédié dans HTTP Shortcuts).
4. Un tap = un magic packet envoyé ; l'app affiche le code de réponse HTTP pour confirmer.
