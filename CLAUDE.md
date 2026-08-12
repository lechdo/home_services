# Home Services — CLAUDE.md racine

Ce dépôt regroupe plusieurs **services indépendants**. Ce fichier décrit les règles communes à tous les services. Chaque service a en plus son propre `CLAUDE.md` (dans son dossier) qui précise ses caractéristiques spécifiques, en complément (jamais en contradiction) de ce fichier racine.

## Principe d'architecture

- Chaque service vit dans son propre dossier à la racine du repo : `/<nom-du-service>/`.
- Un service est **autonome** : il ne partage aucun code, aucune dépendance, aucune configuration, aucun package, ni aucune ressource (base de données, fichiers, variables d'environnement, etc.) avec un autre service.
- La **seule** forme de communication autorisée entre services est via **API** (HTTP ou équivalent), comme le ferait un client externe. Pas d'import de code d'un service dans un autre, pas de librairie interne partagée, pas de base de données commune.
- Chaque service peut donc être développé, testé, déployé et versionné indépendamment des autres.

## Structure attendue d'un service

```
/<nom-du-service>/
  CLAUDE.md          # spécificités propres à ce service (complète le CLAUDE.md racine)
  _plan/
    plan.md           # plan de développement du service
    *.md               # autres documents de description du projet (specs, décisions, notes...)
  ... (code du service)
```

- `_plan/` : dossier documentaire uniquement (Markdown). Il contient le plan de réalisation et tous les documents de description/spécification du service. Ce n'est pas du code et ne doit pas être confondu avec la configuration ou le code source du service.
- Le `CLAUDE.md` de chaque service doit rester cohérent avec ce fichier racine : il ajoute des règles spécifiques au service (stack technique, conventions, contraintes), il ne redéfinit pas les règles transverses déjà énoncées ici.

## Exposition Internet des services

Un service qui a besoin d'être exposé publiquement (nom de domaine, TLS) ne gère jamais lui-même le DNS ni les certificats. Le point d'entrée Internet unique du dossier racine est le service `/edge/` : le service backend se contente de publier un port HTTP sur l'hôte, et `edge` route/termine le TLS. La communication entre `edge` et un service backend se fait uniquement en HTTP, comme le ferait un client externe — cela reste conforme au principe d'autonomie ci-dessus, `edge` n'étant lui-même qu'un service comme un autre. Voir `edge/CLAUDE.md` et `edge/_plan/architecture.md` pour le contrat d'intégration.

## Persistance et mise à jour des données

Un service qui crée de la configuration structurelle via son API/UI (types, taxonomies, règles...) doit la déclarer dans un `provisioning/` versionné, appliqué par un script idempotent — la base du service devient un état dérivé, pas la source de vérité. Un service avec des données utilisateur critiques non déclarables (contenu réel) doit avoir un `_plan/plan-sauvegarde.md` testé. Voir `protocole-donnees.md` pour le détail et le statut par service. Chaque service reste strictement autonome dans ces mécanismes (aucun script/ressource partagé entre services), conformément au principe d'architecture ci-dessus.

## Règles pour Claude

- Avant de travailler dans un service donné, lire son `CLAUDE.md` local ainsi que le contenu de son dossier `_plan/` pour comprendre le contexte et le plan prévu.
- Ne jamais faire référencer/importer du code d'un service depuis un autre service. Si un besoin de partage de logique apparaît, la solution est d'exposer une API depuis le service qui possède la donnée/logique, pas de dupliquer ou de coupler le code.
- Ne pas créer de dossier ou fichier partagé transverse (pas de `common/`, `shared/`, `libs/` à la racine) : cela casserait l'indépendance des services.
- Lors de la création d'un nouveau service, créer systématiquement : son dossier, son `CLAUDE.md`, et son dossier `_plan/` avec au moins un `plan.md`.
