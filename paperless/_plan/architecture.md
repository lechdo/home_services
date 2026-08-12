# Architecture — Paperless (DMS personnel)

> Détail issu de `../conversation.md`. Complète `plan.md`.

## Vue d'ensemble en trois couches

```
                     ┌───────────────┐
                     │  Google Drive │
                     │  SOURCE PURE  │
                     └───────┬───────┘
                             │ rclone (sync unidirectionnelle)
                             ▼
                     ┌───────────────┐
                     │   ingestion   │  (dossier consume Paperless)
                     └───────┬───────┘
                             ▼
                    ┌─────────────────┐
                    │   PAPERLESS     │
                    │                 │
                    │ OCR             │
                    │ stockage        │
                    │ recherche       │
                    │ tags            │
                    │ types           │
                    │ custom fields   │
                    └────────┬────────┘
                             │ webhook (workflow Paperless)
                             ▼
                  ┌─────────────────────┐
                  │ SERVICE RAD/LAD     │
                  │                     │
                  │ classification      │
                  │ extraction          │
                  │ validation confiance│
                  │ règles métier       │
                  └──────────┬──────────┘
                             │ API REST Paperless (PATCH document)
                             ▼
                    ┌─────────────────┐
                    │   PAPERLESS     │
                    │ type / tags /   │
                    │ custom fields   │
                    └─────────────────┘
```

Règle de circulation : **Drive → Paperless → RAD/LAD → Paperless**. Jamais de retour vers Drive automatique.

## Pourquoi ne pas laisser Drive comme simple stockage passif

Le principal risque d'architecture identifié : traiter Drive comme un disque derrière l'application. On sépare donc explicitement :
- le **document source** (fichier + métadonnées Drive : `drive_file_id`, `mime_type`, `sha256`, taille, date de modification, propriétaire, chemin, version Drive) — jamais modifié ;
- les **métadonnées produites par le système** (classification, tags, OCR, entités, relations) — évoluent librement, sans jamais toucher au fichier original.

## Synchronisation Google Drive

- Sens unique : `GDrive → local`. Un flux `local metadata → GDrive` n'existe pas, sauf action explicite et volontaire de l'utilisateur.
- Outil : **rclone**, qui gère la détection des nouveaux fichiers, des modifications et des suppressions côté Drive.
- Propriété recherchée : si l'application (Paperless + RAD/LAD) est perdue/corrompue, toute la base peut être reconstruite à partir de Drive seul.

```
Google Drive
     │
     │ rclone
     ▼
/data/inbox (filesystem local)
     │
     │ Paperless consumer
     ▼
Paperless-ngx
     │
     ▼
PostgreSQL
```

## Pipeline de traitement comme système événementiel

But : pouvoir remplacer un composant (OCR, classifieur) sans réécrire le reste de l'application.

```
document.created
      ↓
ocr.required
      ↓
ocr.completed
      ↓
classification.required
      ↓
classification.completed
      ↓
metadata.extraction.required
      ↓
metadata.extraction.completed
      ↓
index.updated
```

Remplacements envisagés à terme, sans changer le reste du pipeline :
- `OCR v1 → OCR v2`
- `classifieur heuristique → LLM → modèle local spécialisé`

## Human-in-the-loop piloté par la confiance

```
        RAD/LAD
           │
     confidence 0.98
           │
           ▼
     automatique ✓


     confidence 0.61
           │
           ▼
   ┌─────────────────┐
   │ Validation       │
   │ utilisateur      │
   └────────┬────────┘
            │
            ▼
        metadata
```

Détail des seuils : voir `rad-lad-contract.md`.

## Pourquoi Paperless-ngx plutôt qu'une autre solution

Comparatif retenu dans la conversation (évaluation qualitative, à revalider à l'usage) :

| Solution         | OCR | Tags | Recherche | RAD/LAD | API | GDrive | Local |
|---|---|---|---|---|---|---|---|
| **Paperless-ngx** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Mayan EDMS | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| Teedy | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| Nextcloud + apps | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

Point de vigilance identifié : aucune de ces solutions n'a de synchronisation Drive native "propre" — d'où le recours à rclone comme brique de sync dédiée plutôt que d'attendre cette fonctionnalité de Paperless.

Alternative de repli si le besoin dérive vers un DMS professionnel (workflows complexes, signatures, permissions fines, audit) : **Mayan EDMS**. Non retenue au démarrage car plus lourde conceptuellement pour un usage personnel.

## Déploiement

Docker Compose local, sans Kubernetes au démarrage :

```
db (postgres)
broker (redis)    — non anticipé ici, découvert à l'implémentation (phase 0) :
                    Paperless-ngx a besoin d'une file de tâches (OCR,
                    indexation, matching Auto) même en usage mono-utilisateur.
paperless
rad-lad-service   (à développer, phases 3+)
frontend          (optionnel, phase 7)
```

**Implémenté (2026-08-12)** : `db` + `broker` + `paperless` (webserver), voir `plan.md` phase 0 pour le détail et `../compose.yaml`.

## Exposition Internet

Aucune logique DNS/TLS dans ce service : si une exposition publique est nécessaire (phase 8 de `plan.md`), le service publie simplement un port HTTP sur l'hôte et délègue le routage/TLS au service dédié `/edge/`, point d'entrée Internet unique pour tous les services du dossier racine (voir `../../edge/_plan/architecture.md`).
