# Règles de catégorisation — outillage

Implémente la section 2 de `../../_plan/plan-configuration.md` (« Automatisation de la catégorisation ») : un moteur générique (`apply-rules.js`) qui crée des règles Actual à partir d'un fichier déclaratif (`rules.*.json`), plutôt que de cliquer une par une dans l'UI.

## Principe

- `apply-rules.js` ne connaît aucun payee : il résout les catégories par leur nom (`"GROUPE > Catégorie"`) au moment de l'exécution, donc **il est réutilisable à l'identique** sur n'importe quel budget Actual (test ou prod), tant que l'arborescence de catégories du §1 du plan existe déjà dans ce budget.
- Une règle « catch-all » (`catchAllCategory`, stage `pre`) affecte par défaut **toutes** les transactions du compte à la catégorie tampon `À VÉRIFIER > À vérifier`. Les règles spécifiques tournent ensuite en stage par défaut et écrasent cette catégorie quand elles matchent — cf. `plan-configuration.md` §2.3. Résultat : rien ne reste silencieusement en `Uncategorized`.
- Le script est idempotent : le relancer ne duplique pas les règles déjà créées (comparaison par signature conditions+actions).

## Fichiers

- `apply-rules.js` — le moteur, générique, à ne pas modifier pour changer les règles.
- `rules.test.json` — le jeu de règles calibré sur les **458 transactions du budget de test** (`My-Finances`), utilisé pour valider le mécanisme le 2026-08-13. **Ne reflète pas de vrais payees bancaires** — inutile de le réutiliser en prod tel quel.

## Utilisation

```bash
npm install   # une seule fois, installe @actual-app/api

ACTUAL_SERVER_URL=http://127.0.0.1:8083 \
ACTUAL_PASSWORD='<mot de passe applicatif Actual>' \
ACTUAL_SYNC_ID='<Sync ID du budget, Paramètres > Paramètres avancés>' \
node apply-rules.js rules.test.json
```

Le Sync ID se trouve dans Actual : **Paramètres → Montrer les paramètres avancés → ID de synchronisation**.

## Reproduire cette étape en production

Le jour où le vrai compte bancaire (connecteur Enable Banking, cf. `plan-configuration.md` §8) est branché sur le budget de production :

1. Vérifier que l'arborescence de catégories du §1 existe dans le budget de prod (rejouer le script de création de catégories si besoin — voir le journal dans `plan-configuration.md`).
2. Laisser tourner l'import bancaire 2-3 mois (§7 étape 1) pour avoir un vrai échantillon de payees.
3. Exporter les payees réels (mêmes méthodes que pour le test : `api.getTransactions()` + comptage par fréquence) pour repérer les motifs récurrents.
4. Écrire un nouveau `rules.prod.json` (copier `rules.test.json` comme gabarit de structure, PAS son contenu) avec les vrais mots-clés observés.
5. Lancer `node apply-rules.js rules.prod.json` avec le Sync ID et le mot de passe du budget de **production**.
6. Réviser périodiquement la catégorie tampon `À vérifier` (§2.3) pour affiner `rules.prod.json` au fil du temps — relancer le script après chaque ajout, il est idempotent.

`rules.prod.json` n'est pas fourni ici : il dépend de payees bancaires réels non encore connus. Décider au moment venu s'il doit être committé (son contenu ne révèle que des enseignes, pas de montants — a priori pas sensible, mais à évaluer).
