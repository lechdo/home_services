Oui. Je partirais sur une architecture où le cloud reste la source documentaire immuable, tandis que ton service local devient une couche de gestion, d'indexation et d'enrichissement.

L'idée importante est de ne pas faire de GDrive un simple stockage derrière ton application : il faut clairement séparer document source et métadonnées produites par le système.

Architecture que je te proposerais
                         ┌─────────────────────┐
                         │       Google Drive  │
                         │                     │
                         │  fichiers originaux │
                         │  "source pure"      │
                         └──────────┬──────────┘
                                    │
                             sync / webhook
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                    Document Management Service                │
│                                                               │
│  ┌───────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ Ingestion     │────▶│ Document DB  │────▶│ Search index │ │
│  │ / Sync        │     │              │     │              │ │
│  └───────────────┘     └──────┬───────┘     └──────────────┘ │
│                               │                               │
│                         ┌─────▼─────┐                         │
│                         │ OCR / LAD │                         │
│                         │ RAD       │                         │
│                         └─────┬─────┘                         │
│                               │                               │
│              ┌────────────────┼────────────────┐              │
│              ▼                ▼                ▼              │
│           Tags            Metadata          Relations         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                             UI / API / CLI
1. Le principe fondamental

Je définirais trois niveaux :

1. Source

Le fichier tel qu'il existe dans GDrive :

document.pdf

avec :

drive_file_id
mime_type
sha256
taille
date de modification
propriétaire
chemin / dossier GDrive
version GDrive

Il n'est jamais modifié par le service.

2. Représentation locale

Ton service conserve éventuellement une copie locale :

storage/
    ab/
       cd/
          abcdef...pdf

Cette copie est un cache, pas la source de vérité.

3. Enrichissement

Tout ce qui est produit par ton système :

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

peut évoluer sans jamais toucher au fichier original.

RAD/LAD

Je séparerais également RAD et LAD.

LAD

Lecture automatique du document :

PDF/image
   │
   ▼
OCR
   │
   ▼
texte
   │
   ├── date
   ├── montant
   ├── numéro
   ├── nom
   ├── adresse
   └── etc.

Par exemple :

document_type: facture
supplier: EDF
invoice_number: 123456
invoice_date: 2026-07-31
amount: 142.37
currency: EUR
RAD

Reconnaissance/classification :

texte + layout + metadata
          │
          ▼
       classifier
          │
          ├── facture
          ├── contrat
          ├── courrier
          ├── relevé bancaire
          ├── assurance
          └── autre

Et surtout, je garderais la confiance :

document_type:
    value: facture
    confidence: 0.97
    source: classifier_v2

Cela permet ensuite d'avoir une validation humaine.

Le point intéressant : le document devient un objet

Plutôt que de penser :

« j'ai des fichiers »

je concevrais le système autour de :

j'ai des documents auxquels sont attachées plusieurs représentations et métadonnées.

Par exemple :

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

Ça devient beaucoup plus puissant qu'un simple gestionnaire de fichiers.

La synchronisation GDrive est le point délicat

Je ferais une synchronisation unidirectionnelle au niveau des fichiers :

GDrive
   │
   │  pull
   ▼
Local

et jamais :

Local metadata ──► GDrive

sauf éventuellement pour des opérations explicitement demandées par l'utilisateur.

Ainsi :

GDrive:
    facture-edf.pdf
          │
          ▼
Local:
    document #1842
          │
          ├── tag: énergie
          ├── type: facture
          ├── fournisseur: EDF
          ├── montant: 142.37 €
          └── date: 2026-07-31

Si ton application se plante complètement, tu peux reconstruire toute la base locale à partir de GDrive.

C'est une propriété extrêmement intéressante.

Et je conserverais l'historique

Par exemple :

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

Cela permet de distinguer :

même document + métadonnées modifiées

de :

nouvelle version du fichier

Et surtout de ne pas perdre les résultats LAD/RAD précédents.

Pour la recherche

Je mettrais probablement PostgreSQL + moteur full-text au départ, plutôt que de partir immédiatement sur Elasticsearch/OpenSearch.

Tu peux avoir :

PostgreSQL
│
├── documents
├── document_versions
├── tags
├── document_tags
├── extracted_fields
├── relations
└── sync_state

et une recherche PostgreSQL sur :

OCR text
filename
tags
metadata

Puis ajouter éventuellement OpenSearch si le volume ou les besoins deviennent importants.

Pour ton usage, je privilégierais même initialement :

PostgreSQL + pg_trgm + FTS

avant de multiplier les services.

Je ferais aussi une distinction entre tags et classification

C'est important.

Classification

Ce que le document est :

facture
contrat
bulletin de salaire
courrier
relevé bancaire
Tags

Ce que tu veux lui associer :

EDF
maison
2026
à vérifier
important
comptabilité
Collections

Ce que tu veux regrouper temporairement :

Impôts 2026
Déménagement
Maison
Voiture

Ça évite de transformer les tags en système de dossiers déguisé.

Une architecture technique assez naturelle pour toi

Vu que tu travailles déjà beaucoup avec Python, je partirais probablement sur quelque chose comme :

                  ┌───────────────┐
                  │ Google Drive  │
                  └───────┬───────┘
                          │
                    Drive API
                          │
                  ┌───────▼───────┐
                  │ sync worker   │
                  └───────┬───────┘
                          │
              ┌───────────▼───────────┐
              │      PostgreSQL       │
              │                       │
              │ documents             │
              │ metadata              │
              │ tags                  │
              │ OCR results           │
              │ classifications       │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │      processing       │
              │                       │
              │ OCR                   │
              │ RAD/LAD               │
              │ thumbnails            │
              │ extraction            │
              └───────────┬───────────┘
                          │
                    ┌─────▼─────┐
                    │   API     │
                    │ FastAPI   │
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
             Web          CLI        TUI

Et tu pourrais faire tourner tout ça localement avec Docker Compose, avec seulement quelques composants :

postgres
document-service
worker
frontend

Pas besoin de Kubernetes ou d'une architecture distribuée au départ.

Mais il y a une décision d'architecture que je prendrais très tôt

Je ferais du pipeline de traitement un système événementiel :

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

Cela permet ensuite de remplacer progressivement les composants :

OCR v1
   ↓
OCR v2

classifier heuristique
   ↓
LLM
   ↓
modèle local spécialisé

sans refaire toute l'application.

Et surtout, ça ouvre la porte à un fonctionnement human-in-the-loop :

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

À mon avis, c'est là que le projet peut devenir vraiment intéressant : un DMS personnel local-first, où GDrive fournit l'archive immuable et ton service construit progressivement une représentation sémantique exploitable de tes documents.

Si tu veux aller plus loin, je peux te proposer 
le modèle de données PostgreSQL complet (tables, relations, états de synchronisation, versions et événements), qui est probablement la prochaine étape utile avant de choisir les librairies.

puis-je mettre en place ce service avec des outils déjà existant pour le service des documents?

Oui — et je te conseillerais clairement de ne pas développer toi-même le cœur du DMS. Ton besoin ressemble beaucoup à ce que plusieurs projets open source savent déjà faire : stockage, OCR, classement, tags, recherche, ingestion et éventuellement synchronisation.

Le point particulier de ton architecture est plutôt de faire de Google Drive la source documentaire "pure", et d'utiliser un DMS local comme couche intelligente.

Les candidats intéressants
4
Solution	OCR	Tags	Recherche	RAD/LAD	API	GDrive	Local
Paperless-ngx	⭐⭐⭐⭐⭐	⭐⭐⭐⭐⭐	⭐⭐⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐⭐⭐	⭐⭐⭐	⭐⭐⭐⭐⭐
Mayan EDMS	⭐⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐⭐	⭐⭐	⭐⭐⭐⭐⭐
Teedy	⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐	⭐⭐⭐⭐	⭐⭐	⭐⭐⭐⭐
Nextcloud + apps	⭐⭐⭐	⭐⭐⭐⭐	⭐⭐⭐	⭐⭐	⭐⭐⭐⭐	⭐⭐⭐	⭐⭐⭐⭐

Pour ton cas, Paperless-ngx serait mon premier candidat, assez nettement.

Pourquoi Paperless-ngx correspond bien

Paperless-ngx est déjà conçu autour d'une idée assez proche :

             documents
                 │
                 ▼
          ┌──────────────┐
          │ Paperless    │
          └──────┬───────┘
                 │
       ┌─────────┼──────────┐
       ▼         ▼          ▼
      OCR       Tags     Correspondents
       │         │          │
       └─────────┼──────────┘
                 ▼
              Search

Il gère notamment :

OCR ;
recherche plein texte ;
tags ;
correspondants ;
types de documents ;
champs personnalisés ;
règles automatiques ;
workflows ;
archivage ;
versions ;
API REST ;
consommation de documents depuis un dossier ;
authentification ;
permissions.

Et surtout, il est très facilement déployable en Docker.

Paperless-ngx — site officiel

Mais je ne ferais pas exactement ce que fait Paperless

C'est là que ton idée devient intéressante.

Je ne ferais pas :

GDrive
   ↓
Paperless
   ↓
modification des documents

mais :

                     ┌───────────────┐
                     │   Google      │
                     │    Drive      │
                     │               │
                     │ SOURCE PURE   │
                     └───────┬───────┘
                             │
                             │ sync
                             ▼
                    ┌─────────────────┐
                    │   Paperless     │
                    │                 │
                    │ OCR             │
                    │ tags            │
                    │ classification  │
                    │ recherche       │
                    └────────┬────────┘
                             │
                             │ API
                             ▼
                    ┌─────────────────┐
                    │ Ton application │
                    │                 │
                    │ orchestration   │
                    │ UI              │
                    │ IA              │
                    │ règles métier   │
                    └─────────────────┘

Paperless devient ton moteur documentaire.

Ton propre code devient une couche d'orchestration.

Le problème : Google Drive

C'est probablement le principal point à vérifier avant de partir sur Paperless.

Paperless sait très bien ingérer des fichiers depuis des répertoires, mais ton besoin est plutôt :

GDrive
   ⇅
local document repository

avec idéalement :

détection des nouveaux fichiers ;
détection des modifications ;
détection des suppressions ;
conservation de l'ID GDrive ;
gestion des versions ;
absence de modification du fichier original.

Tu peux résoudre ça avec rclone.

rclone

Il sait monter/synchroniser Google Drive et énormément d'autres stockages.

rclone — site officiel

Par exemple :

Google Drive
     │
     │ rclone
     ▼
/data/inbox
     │
     │ Paperless consumer
     ▼
Paperless

C'est déjà une architecture parfaitement viable.

Et même : tu pourrais ne presque rien coder au début

Je commencerais avec :

                 Google Drive
                      │
                    rclone
                      │
                      ▼
                local filesystem
                      │
                      ▼
                Paperless-ngx
                      │
                      ▼
                   PostgreSQL

Puis seulement ensuite :

                    API
                     │
                     ▼
             ton service Python
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
        GDrive       IA       interface
        sync       RAD/LAD      perso

Cela te permettrait de tester le concept avant d'investir dans le développement.

Il y a cependant une différence importante avec ton besoin

Paperless est excellent pour :

"Je veux archiver et retrouver mes documents."

Ton projet semble plutôt vouloir :

"Je veux construire une base documentaire sémantique à partir de mes documents."

Ce deuxième niveau peut être construit au-dessus de Paperless.

Par exemple :

Paperless
│
├── facture EDF
│   ├── OCR
│   ├── tag: énergie
│   └── type: facture
│
└── contrat assurance
    ├── OCR
    ├── tag: voiture
    └── type: contrat

Ton service peut alors ajouter :

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

Et là, Paperless fait le travail lourd, tandis que ton application apporte la couche intelligente.

Une autre possibilité : Mayan EDMS

Mayan EDMS est probablement plus intéressant si tu veux évoluer vers quelque chose de proche d'un DMS professionnel :

workflows ;
documents et versions ;
métadonnées ;
permissions ;
signatures ;
audit ;
indexation ;
OCR ;
API.

Mayan EDMS — site officiel

Mais il est aussi nettement plus lourd conceptuellement.

Pour un DMS personnel/local, je commencerais plutôt par Paperless.

Mon choix pour ton projet

Je ferais donc :

                         GOOGLE DRIVE
                             │
                             │
                        rclone / API
                             │
                             ▼
                      ┌──────────────┐
                      │   SYNC       │
                      │   SERVICE    │
                      └──────┬───────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  PAPERLESS      │
                    │                 │
                    │ OCR             │
                    │ classification  │
                    │ tags            │
                    │ full text       │
                    │ metadata        │
                    │ search          │
                    └────────┬────────┘
                             │
                         REST API
                             │
                             ▼
                    ┌─────────────────┐
                    │   TON SERVICE   │
                    │                 │
                    │ RAD/LAD avancé  │
                    │ IA              │
                    │ relations       │
                    │ règles          │
                    │ automatisation  │
                    └────────┬────────┘
                             │
                     ┌───────┼────────┐
                     ▼       ▼        ▼
                    Web      CLI      TUI

Et je ne remplacerais Paperless par ton propre backend tant que tu n'as pas une raison concrète de le faire.

Il y a toutefois une question architecturale importante à régler avant même de choisir Paperless : est-ce que tu veux que les documents restent physiquement dans GDrive et que Paperless n'en garde qu'une copie/cache, ou acceptes-tu que Paperless devienne le stockage local principal avec GDrive comme sauvegarde/source externe ?

Dans ton idée de "source pure", je privilégierais fortement la première solution.

avec paperless, comment programmer la reconnaissance des types de documents par rapport au retour du RAD/LAD

Oui. Et en fait Paperless-ngx possède déjà une partie de ce mécanisme, mais il faut distinguer deux choses :

la classification native de Paperless à partir du texte OCR ;
ton propre RAD/LAD, qui peut produire une classification beaucoup plus riche et que tu peux ensuite injecter dans Paperless via son API.

Paperless fait déjà de l'appariement automatique des types, tags et correspondants à partir du texte OCR, avec notamment un algorithme Auto basé sur un réseau neuronal qui apprend des classifications existantes.

1. Le plus simple : utiliser le moteur de classification de Paperless

Supposons que tu crées les types :

Facture
Contrat
Relevé bancaire
Courrier administratif
Bulletin de salaire
Impôt
Assurance

Tu peux définir pour chaque type des règles de matching.

Par exemple :

Document type = Facture

match:
    facture
    montant
    TVA
    échéance
    total TTC

algorithm:
    Any

Ou plus spécifiquement :

Document type = Facture EDF

match:
    EDF
    fournisseur
    montant
    consommation

Paperless exécute ce matching après extraction du contenu et peut automatiquement affecter le type, les tags et le correspondant.

Mais ce n'est probablement pas ce que tu veux à terme.

2. Ton RAD/LAD peut devenir le véritable classifieur

Je verrais plutôt ton pipeline comme ça :

                 document
                    │
                    ▼
              Paperless OCR
                    │
                    ▼
             texte OCR brut
                    │
                    ▼
              ton service
                 RAD/LAD
                    │
           ┌────────┼─────────┐
           ▼        ▼         ▼
        type      champs    confiance
        facture   montant      0.97
                  date
                  fournisseur

Puis ton service appelle l'API Paperless :

POST /api/documents/{id}/

pour lui dire :

{
    "document_type": 4,
    "tags": [12, 15],
    "custom_fields": {
        "invoice_number": "2026-1234",
        "amount": 142.37
    }
}

L'API Paperless permet effectivement de modifier les types, tags et champs personnalisés des documents.

3. Je ferais surtout une couche de décision entre RAD/LAD et Paperless

C'est important pour ne pas transformer une erreur d'IA en classification définitive.

Par exemple, ton moteur retourne :

{
  "document_type": "facture",
  "confidence": 0.96,
  "fields": {
    "supplier": {
      "value": "EDF",
      "confidence": 0.99
    },
    "invoice_number": {
      "value": "123456",
      "confidence": 0.94
    },
    "invoice_date": {
      "value": "2026-07-31",
      "confidence": 0.98
    },
    "amount": {
      "value": 142.37,
      "confidence": 0.91
    }
  }
}

Et ton orchestrateur applique une politique :

confidence >= 0.95
        │
        ▼
   automatique

0.75 - 0.95
        │
        ▼
   automatique +
   "à vérifier"

< 0.75
        │
        ▼
   validation humaine

Ça te donne quelque chose de beaucoup plus robuste.

4. Les Custom Fields de Paperless sont parfaits pour le LAD

Paperless permet de créer des champs personnalisés typés : texte, nombre, date, etc.

Tu pourrais donc définir :

Document type: Facture

Custom fields:
────────────────────────────
Fournisseur       String
Numéro facture    String
Date facture      Date
Date échéance     Date
Montant HT        Monetary
TVA               Monetary
Montant TTC       Monetary

Ton LAD remplit ensuite ces champs.

Exemple :

             ┌───────────────┐
             │   FACTURE     │
             └───────┬───────┘
                     │
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
    fournisseur   invoice_no     amount
       EDF          123456       142.37

Et Paperless devient alors l'interface de consultation et de recherche.

5. Et tu peux aller beaucoup plus loin avec les workflows

Les workflows récents de Paperless sont particulièrement intéressants pour ton architecture.

Ils peuvent déclencher des actions après l'ajout ou la modification d'un document et filtrer notamment sur :

contenu ;
tags ;
type de document ;
correspondant ;
champs personnalisés ;
etc.

Ils peuvent également appeler un webhook.

Donc tu peux faire :

Paperless
    │
    │ document ajouté
    ▼
Workflow
    │
    │ webhook
    ▼
┌───────────────────────┐
│ Ton RAD/LAD service   │
│                       │
│ OCR complémentaire    │
│ classification        │
│ extraction            │
└───────────┬───────────┘
            │
            │ API
            ▼
        Paperless

C'est probablement l'intégration que je privilégierais.

6. Tu peux même avoir plusieurs niveaux de classification

Je ne limiterais pas document_type à quelque chose comme facture.

Je ferais par exemple :

document_type
    │
    ├── Facture
    ├── Contrat
    ├── Courrier
    ├── Relevé
    └── Justificatif

Puis les tags donnent le contexte :

Facture
├── EDF
├── Électricité
└── Maison

Et les Custom Fields donnent les données structurées :

fournisseur = EDF
montant = 142.37
date = 2026-07-31
échéance = 2026-08-15

C'est beaucoup plus propre que d'avoir :

facture-edf-maison-juillet-2026

comme une seule catégorie.

7. Il y a même un très bon mécanisme pour commencer sans IA

Je commencerais avec :

                 OCR
                  │
                  ▼
        règles Paperless
                  │
          ┌───────┴───────┐
          ▼               ▼
       reconnu          inconnu
          │               │
          ▼               ▼
      classification   RAD/LAD
      automatique          │
                            ▼
                       classification

Puis tu observes les documents qui échouent.

Exemple :

1000 documents

900 → règles Paperless
 70  → Auto
 30  → RAD/LAD

Et seulement ensuite tu développes ton classifieur sophistiqué.

D'autant que Paperless possède justement un algorithme Auto qui apprend des classifications que tu lui as déjà données.

Mais je changerais légèrement ton architecture initiale

Après avoir regardé les possibilités actuelles de Paperless, je ferais plutôt :

                        GOOGLE DRIVE
                             │
                             │ sync
                             ▼
                     ┌───────────────┐
                     │   ingestion   │
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
                             │
                         webhook
                             ▼
                  ┌─────────────────────┐
                  │ TON SERVICE RAD/LAD │
                  │                     │
                  │ classification      │
                  │ extraction          │
                  │ validation          │
                  │ règles métier       │
                  └──────────┬──────────┘
                             │
                          API │
                             ▼
                    ┌─────────────────┐
                    │   PAPERLESS     │
                    │                 │
                    │ type            │
                    │ tags            │
                    │ metadata        │
                    └─────────────────┘

Et surtout : ton service RAD/LAD ne devrait pas remplacer le moteur documentaire de Paperless.

Il devrait être un moteur d'intelligence externe qui enrichit Paperless.

Ça te permettrait de commencer avec zéro IA, puis d'ajouter progressivement :

règles
  ↓
Paperless Auto
  ↓
regex / heuristiques Python
  ↓
modèle ML
  ↓
LLM / VLM
  ↓
modèle spécialisé

sans changer ton DMS.

Si tu veux construire ça sérieusement, l'étape suivante que je regarderais est le format exact du résultat RAD/LAD et le contrat entre ton service et Paperless : 
je peux te proposer une structure JSON avec document_type, confidence, fields, evidence, classifier_version, 
puis montrer comment elle se transforme automatiquement en objets Paperless.
