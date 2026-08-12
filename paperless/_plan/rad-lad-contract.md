# Contrat RAD/LAD ↔ Paperless

> Détail issu de `../conversation.md`. Complète `plan.md`. Le format ci-dessous reprend l'exemple discuté ; il reste **à valider/figer** avant implémentation (phase 4-5 du plan), notamment les champs `evidence` et `classifier_version`.

## Rôle de ce contrat

Définir précisément ce que le service RAD/LAD produit en sortie, et comment ce résultat se traduit en appels à l'API Paperless — de façon à ce qu'une erreur d'IA ne devienne jamais une classification définitive sans contrôle.

## Deux classifications à ne pas confondre

1. **Classification native de Paperless** : matching par règles (`match` + `algorithm: Any/Auto`) sur le texte OCR, éventuellement complétée par l'algorithme `Auto` (réseau neuronal qui apprend des classifications déjà confirmées).
2. **RAD/LAD custom** : classification et extraction plus riches, produites par le service externe, puis injectées dans Paperless via API.

Le RAD/LAD custom n'intervient que là où (1) ne suffit pas.

## Déclenchement

```
Paperless
    │
    │ document ajouté / modifié
    ▼
Workflow Paperless (filtre sur contenu / tags / type / correspondant / custom fields)
    │
    │ webhook
    ▼
Service RAD/LAD
    │
    │ lit le texte OCR déjà produit par Paperless
    ▼
Classification + extraction
    │
    │ API Paperless
    ▼
Paperless (mise à jour du document)
```

## Format de sortie du RAD/LAD (proposition à figer)

```json
{
  "document_type": "facture",
  "confidence": 0.96,
  "classifier_version": "classifier_v2",
  "fields": {
    "supplier": { "value": "EDF", "confidence": 0.99 },
    "invoice_number": { "value": "123456", "confidence": 0.94 },
    "invoice_date": { "value": "2026-07-31", "confidence": 0.98 },
    "amount": { "value": 142.37, "confidence": 0.91 }
  }
}
```

Points à trancher avant implémentation :
- Faut-il un champ `evidence` (extrait de texte source justifiant chaque valeur) pour l'audit et la validation humaine ?
- `classifier_version` : convention de nommage/versionnement à définir (ex. `heuristic_v1`, `llm_v1_<model>`).
- Faut-il distinguer la confiance globale du document (`document_type.confidence`) de la confiance par champ (chaque `field.confidence`), avec des seuils potentiellement différents ?

## Politique de décision par seuils de confiance

```
confidence >= 0.95
        │
        ▼
   automatique

0.75 - 0.95
        │
        ▼
   automatique + tag "à vérifier"

< 0.75
        │
        ▼
   validation humaine (pas d'écriture automatique)
```

Ces seuils (0.95 / 0.75) sont ceux discutés en conception — à ajuster à l'usage réel une fois un échantillon de documents traité. La politique doit s'appliquer aussi bien à la confiance globale de `document_type` qu'à celle de chaque champ extrait, si la granularité par champ est retenue.

## Mapping vers l'API Paperless

Appel type après décision de la politique de confiance :

```
POST /api/documents/{id}/
```

```json
{
  "document_type": 4,
  "tags": [12, 15],
  "custom_fields": {
    "invoice_number": "2026-1234",
    "amount": 142.37
  }
}
```

- `document_type` : identifiant Paperless du type déterminé par le RAD/LAD (après passage par la politique de confiance).
- `tags` : peut inclure un tag "à vérifier" quand la confiance est dans la zone intermédiaire.
- `custom_fields` : un champ personnalisé Paperless par donnée structurée extraite (fournisseur, numéro de facture, dates, montants...), typés (String, Date, Monetary...) — voir `data-model.md` pour la correspondance avec le modèle conceptuel.

## Montée en sophistication progressive

Ne pas commencer par le niveau le plus complexe. Progression prévue, chaque niveau ne servant que pour les documents où le niveau précédent échoue :

```
règles Paperless
      ↓
Paperless Auto
      ↓
regex / heuristiques Python (RAD/LAD)
      ↓
modèle ML
      ↓
LLM / VLM
      ↓
modèle spécialisé
```

Exemple de répartition cible évoqué en conception, sur 1000 documents : ~900 traités par les règles Paperless, ~70 par l'algorithme Auto, ~30 nécessitant le RAD/LAD custom. À mesurer sur un vrai échantillon avant d'investir dans les niveaux les plus sophistiqués.

## Niveaux de classification à ne pas fusionner

Ne pas construire un `document_type` du type `facture-edf-maison-juillet-2026`. Séparer :

```
document_type
    │
    ├── Facture
    ├── Contrat
    ├── Courrier
    ├── Relevé
    └── Justificatif
```

puis laisser les **tags** porter le contexte (`EDF`, `Électricité`, `Maison`) et les **Custom Fields** porter les données structurées (`fournisseur = EDF`, `montant = 142.37`, `date = 2026-07-31`, `échéance = 2026-08-15`).
