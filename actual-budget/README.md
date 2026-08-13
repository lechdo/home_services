# actual-budget

Service Docker Compose auto-hébergeant [Actual Budget](https://actualbudget.org/), une application de budgétisation personnelle.

## Démarrage

```bash
cp .env.example .env   # rien d'obligatoire à changer pour un premier lancement local
docker compose up -d
```

Ouvrir `http://127.0.0.1:8083`. Le mot de passe d'accès se définit dans l'interface au premier lancement (pas de compte admin pré-configuré via variable d'environnement).

## Volumes et sauvegarde

Toutes les données (comptes, budgets, transactions) vivent dans le volume nommé `data`. Rien n'est régénérable en cas de perte — voir `_plan/plan-sauvegarde.md` pour le détail de ce qui est critique et le mécanisme de sauvegarde prévu (pas encore implémenté à ce stade, volontairement — voir ce fichier pour pourquoi et comment l'activer).

## Exposition Internet

Non exposé pour l'instant : le service n'écoute qu'en local (`127.0.0.1:8083`). Voir `_plan/plan.md` Phase 4 pour la marche à suivre si un accès depuis l'extérieur du réseau local devient nécessaire (délégué à `edge`, jamais géré par ce service directement).
