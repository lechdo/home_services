# Modèle de données conceptuel — Paperless (DMS personnel)

> Détail issu de `../conversation.md`. Complète `plan.md`. Ce modèle est conceptuel : la persistance réelle des métadonnées "source" et "versions" (si elle dépasse ce que Paperless stocke déjà nativement) reste à trancher en phase 6.

## Principe : penser "documents", pas "fichiers"

Au lieu de "j'ai des fichiers", le système est pensé comme "j'ai des documents auxquels sont attachées plusieurs représentations et métadonnées" :

```
Document
│
├── Source
│   ├── GDrive ID
│   ├── hash
│   ├── mime type
│   └── original filename
│
├── Content
│   ├── binary
│   ├── OCR text
│   └── pages
│
├── Classification
│   ├── type
│   ├── confidence
│   └── classifier version
│
├── Metadata
│   ├── date
│   ├── sender
│   ├── amount
│   └── ...
│
├── Organization
│   ├── tags
│   ├── folders
│   └── collections
│
└── Relations
    ├── replaces
    ├── related_to
    ├── attachment_of
    └── duplicate_of
```

## Les trois niveaux du Document

### 1. Source (jamais modifiée par le service)

Le fichier tel qu'il existe dans Google Drive, avec ses métadonnées propres :

- `drive_file_id`
- `mime_type`
- `sha256`
- taille
- date de modification
- propriétaire
- chemin / dossier GDrive
- version GDrive

### 2. Représentation locale (cache, pas source de vérité)

Copie locale éventuelle, adressée par hash :

```
storage/
    ab/
       cd/
          abcdef...pdf
```

### 3. Enrichissement (produit par le système, évolue librement)

```
document
 ├── classification
 ├── tags
 ├── OCR
 ├── extracted_text
 ├── entities
 ├── dates
 ├── amounts
 ├── sender
 ├── document_type
 ├── confidence
 └── relations
```

## Historisation des versions

Distinguer explicitement deux cas :
- **même document, métadonnées modifiées** (tag ajouté, type corrigé...) ;
- **nouvelle version du fichier source** (le PDF a changé dans Drive).

```
Document #1842

source:
    drive_id = abc123

versions:
    v1
       hash = 123...
       downloaded = 2026-07-20

    v2
       hash = 456...
       downloaded = 2026-07-31
```

Objectif : ne jamais perdre les résultats RAD/LAD calculés sur une version précédente quand une nouvelle version arrive.

## Distinction Classification / Tags / Collections

C'est une règle de conception à respecter strictement pour ne pas transformer les tags en système de dossiers déguisé.

| Notion | Répond à | Exemples |
|---|---|---|
| **Classification** (`document_type`) | "Qu'est-ce que ce document ?" | facture, contrat, bulletin de salaire, courrier, relevé bancaire |
| **Tags** | "Qu'est-ce que je veux lui associer ?" | EDF, maison, 2026, à vérifier, important, comptabilité |
| **Collections** | "Qu'est-ce que je veux regrouper temporairement ?" | Impôts 2026, Déménagement, Maison, Voiture |

## Correspondance avec les objets Paperless-ngx

| Concept conceptuel | Objet Paperless |
|---|---|
| Classification (`type`) | `document_type` |
| Metadata structurée (montant, date facture, fournisseur...) | **Custom Fields** typés (String, Date, Monetary...) |
| Organization (tags) | `tags` |
| Sender / émetteur | `correspondent` |
| Content (OCR text) | contenu indexé Paperless (recherche plein texte) |
| Source (`drive_file_id`, hash, version) | à faire porter soit par un Custom Field dédié, soit par le service RAD/LAD (à trancher en phase 6) |

## Exemple de résultat d'enrichissement (LAD)

```
document_type: facture
supplier: EDF
invoice_number: 123456
invoice_date: 2026-07-31
amount: 142.37
currency: EUR
```

Avec confiance et traçabilité de la source du résultat :

```
document_type:
    value: facture
    confidence: 0.97
    source: classifier_v2
```

## Exemple d'enrichissement sémantique visé à terme (phase 7)

```
Document #1842

entities:
    EDF
    Julien
    domicile

dates:
    2026-07-31

amount:
    142.37 €

semantic relations:
    → contrat EDF
    → précédent document #1721
    → catégorie "énergie"

actions:
    → paiement à effectuer
    → échéance 2026-08-15
```

## Choix de moteur de recherche

Démarrer avec le moteur plein texte de la PostgreSQL interne à Paperless (`pg_trgm` + FTS) sur OCR text / filename / tags / metadata. Ne considérer OpenSearch/Elasticsearch que si le volume ou les besoins de recherche le justifient concrètement — pas de multiplication de services par anticipation.
