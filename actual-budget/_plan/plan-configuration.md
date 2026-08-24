# Plan de configuration — service actual-budget

Source : `conversation.md` (échange du 2026-08-13, avant tout déploiement du service).

## 0. Périmètre et statut

Ce document décrit la configuration **cible** de l'usage d'Actual Budget une fois le service déployé et connecté à une source bancaire : arborescence de catégories, règles de catégorisation, échéances récurrentes, méthode de budget, et rapports/dashboards à mettre en place pour répondre au besoin exprimé (« vision claire des dépenses par thème, évaluation du budget, automatisation maximale »).

Ce n'est **pas** un `provisioning/` versionné : catégories, règles, échéances et budgets sont des données utilisateur créées via l'UI/API Actual (`user-files/*.sqlite`), pas une configuration d'infrastructure — conformément à `CLAUDE.md` de ce service et à `protocole-donnees.md` (racine). Ce fichier sert de **référence à appliquer manuellement** dans l'UI (ou via un script ponctuel utilisant la CLI Actual), pas de source de vérité rejouée automatiquement à chaque déploiement.

Statut : dépend de deux prérequis :
- le déploiement effectif du service (`_plan/plan.md`) — **fait** ;
- le choix et le branchement d'un connecteur bancaire (Enable Banking pressenti pour la France en 2026, cf. section 8) — **pas encore fait** en production ; un import bancaire réel existe déjà dans le budget de **test** (`My-Finances`, 458 transactions), ce qui a permis de commencer section 1 dès maintenant.

**Avancement** :
- **Sections 1 et 2 : rejouées sur le budget de PRODUCTION (Raspberry Pi) le 2026-08-13**, en plus du budget de test où elles avaient été validées initialement. Le budget de test n'a finalement pas servi de source unique de vérité "à ne pas réutiliser" comme envisagé au départ : les payees du budget de test étaient en fait de vrais payees du foyer (import bancaire réel fait en amont, juste dans un budget distinct du budget de prod) — `rules.test.json` s'est donc avéré directement pertinent pour la prod, pas seulement un gabarit.
  - **Méthode** : API `@actual-app/api` plutôt que l'UI web (création manuelle par clic peu fiable — menus contextuels cliqués par erreur, DOM pas toujours synchro avec les captures d'écran). Script de catégories non committé (jeté après usage, cf. `scripts/rules/README.md` pour la procédure de reproduction) ; `scripts/rules/apply-rules.js` + `categorize-existing.js` committés et réutilisés tels quels (résolution des catégories par nom, aucune dépendance à des ID codés en dur).
  - **Accès au serveur de prod** : le port `8083` d'`actual-budget` n'étant publié qu'en `127.0.0.1` sur le Pi (cf. `edge/_plan/architecture.md`), les scripts ont été exécutés via un tunnel SSH (`ssh -L 18083:127.0.0.1:8083 ...`) plutôt qu'en passant par `edge` — évite toute question de certificat auto-signé pour un usage scripté ponctuel, edge reste le seul chemin pour l'usage réel (navigateur).
  - **Anciens groupes par défaut d'Actual** (`Usual Expenses`, `Investments and Savings`) supprimés sur les deux budgets — mêmes UUID que sur tout budget neuf (confirmé empiriquement), donc le script de suppression est réutilisable sans adaptation.
  - **Résultat budget de test** (458 transactions) : 334 (73 %) catégorisées automatiquement, 124 (27 %) dans `À VÉRIFIER`.
  - **Résultat budget de production** (2424 transactions déjà présentes sur le compte `Cheque Julien`, historique importé avant cette étape) : 1557 (64 %) catégorisées automatiquement, 867 (36 %) dans `À VÉRIFIER` — proportion plus élevée qu'en test, cohérent avec un historique complet plus varié (plus de marchands ponctuels/ambigus). 0 transaction restée en `Uncategorized` dans les deux cas — comportement voulu par §2.3 (catch-all), pas un échec de couverture.
  - **Incident résolu en cours de route** : la synchronisation navigateur↔serveur échouait silencieusement (413 côté `edge`, `client_max_body_size` par défaut de nginx trop petit pour le payload `/sync/sync` d'Actual) — corrigé côté `edge` (voir `edge/_plan/plan.md`), sans quoi des comptes créés dans l'UI restaient coincés localement sans jamais atteindre le serveur.
- Sections 3 à 8 : toujours à appliquer — nécessitent le passage en production pour de vrai (schedules, budget réel, connexion bancaire automatisée — l'import initial semble avoir été fait manuellement/ponctuellement, pas encore via un connecteur type Enable Banking, cf. §8).

## 1. Arborescence de catégories cible

Principe retenu (issu de la conversation) : **10 à 15 groupes, 3 à 8 catégories chacun** — pas de granularité fine. Le niveau utile est celui qui permet une décision (« Carrefour → Courses » oui, « Carrefour → Courses → Légumes » non, sauf besoin réel avéré).

Trois blocs distincts, pour ne pas noyer l'épargne dans les dépenses (section 4) :

**Revenus** (groupe spécial `Income` d'Actual)
- Salaires
- Autres revenus

**Dépenses courantes**

| Groupe | Catégories |
|---|---|
| Logement | Loyer / crédit, Électricité, Eau, Chauffage, Internet / téléphone, Entretien |
| Alimentation | Courses, Restaurants, Livraison |
| Transport | Carburant, Entretien véhicule, Assurance véhicule, Transports en commun |
| Famille | Enfant, Vêtements, Activités, Santé, École |
| Loisirs | Sorties, Culture, Jeux / informatique, Abonnements, Sport (ajoutée le 2026-08-13) |
| Vie courante | Maison, Hygiène, Achats divers |
| Impôts / administratif | Impôts, Taxes, Frais bancaires |

**Objectifs / épargne** (enveloppes alimentées mensuellement, cf. section 4)
- Vacances
- Voiture (gros entretien / achat)
- Travaux
- Noël / anniversaires
- Épargne de précaution
- Gros achats

**Transferts** (groupe ajouté le 2026-08-13, temporaire)
- Transfert Virginie — compense les virements vers/depuis le compte de Virginie tant qu'il n'est pas lui-même ajouté au budget (ce qui permettrait d'utiliser le vrai mécanisme de virement natif d'Actual, invisible dans les rapports de dépenses, plutôt qu'une catégorie). Groupe à part plutôt que dans Objectifs/Épargne : ce n'est pas de l'épargne, juste de l'argent qui change de compte — le séparer garde le calcul `Reste = Revenus − Dépenses − Objectifs` (section 6) correct. **À supprimer** le jour où le compte de Virginie est ajouté au budget (repasser les transactions historiques par le virement natif à ce moment-là, si souhaité).

## 2. Automatisation de la catégorisation (objectif : maximiser la couverture)

C'est le point central du besoin exprimé (« automatiser au maximum »). L'objectif n'est pas seulement de créer quelques règles, mais de tendre vers **le moins d'intervention manuelle possible** sur les dépenses récurrentes, avec un filet de sécurité pour ne jamais laisser une transaction silencieusement mal classée.

### 2.1 Mécanisme de base : Payee Rules + Category Learning

Actual apprend l'association payee → catégorie après une catégorisation manuelle répétée, et permet aussi de nettoyer un nom de commerçant brut fourni par la banque (renommage payee, ex. `CB*1234 AMAZON EU SARL 08/13` → `Amazon`) avant d'appliquer la règle de catégorie. Une fois la règle créée, toute transaction future du même payee est catégorisée automatiquement dès l'import/la synchronisation — c'est le socle de l'automatisation.

Ces règles ne peuvent être créées qu'une fois les **libellés bancaires réels** connus (post connexion bancaire) — la liste ci-dessous, tirée des exemples de la conversation, est un point de départ à ajuster, pas une liste figée :

| Payee (brut ou nettoyé) | Catégorie |
|---|---|
| CARREFOUR* | Alimentation → Courses |
| TOTAL* | Transport → Carburant |
| NETFLIX | Loisirs → Abonnements |
| EDF | Logement → Électricité |
| AMAZON* | Vie courante → Achats divers |
| ASSURANCE * | Transport → Assurance véhicule (à affiner selon le contrat) |

À construire progressivement (étape 2 de la feuille de route, section 7) au fil des transactions réelles, jusqu'à couvrir la majorité des dépenses récurrentes courantes.

### 2.2 Règles en cascade, pas des règles isolées

Pour maximiser le taux de couverture plutôt que de multiplier les règles exactes une par une :

1. **Règles de renommage payee** en premier (regex/« contient », ex. tout ce qui contient `AMAZON` → payee `Amazon`), pour absorber les variantes de libellés bancaires (numéro de CB, date, suffixes de société) sous un seul nom propre.
2. **Règles de catégorie sur le payee nettoyé**, pas sur le libellé brut — une seule règle `Amazon → Achats divers` couvre alors toutes les variantes déjà normalisées à l'étape 1.
3. **Règles génériques de repli sur mot-clé** quand un commerçant a plusieurs enseignes/variantes prévisibles (ex. tout payee « contient TOTAL » → Carburant, tout payee « contient PHARMACIE » → Santé), plutôt qu'une règle par enseigne rencontrée.
4. **Règles sur montant/compte** en complément quand le payee seul ne suffit pas (ex. prélèvement d'un montant fixe connu sur un compte donné → catégorie associée), utile pour les abonnements dont le libellé bancaire est peu explicite.

### 2.3 Filet de sécurité : ne jamais laisser une transaction « invisible »

Pour que l'automatisation reste fiable dans la durée sans supervision constante :

- Créer une catégorie tampon **« À vérifier »** (hors des groupes de dépenses habituels) comme catégorie par défaut des transactions importées sans règle correspondante, plutôt que de les laisser en `Uncategorized` — elle reste ainsi visible dans les rapports comme une anomalie à traiter, pas silencieusement absente.
- Revue périodique courte (hebdomadaire au démarrage, mensuelle une fois la couverture stabilisée) du solde de cette catégorie : chaque transaction qui y atterrit devient l'occasion de créer/affiner une règle (retour à 2.1–2.2), donc la charge manuelle décroît avec le temps au lieu de rester constante.
- Suivre un indicateur simple — **% de transactions catégorisées automatiquement dans le mois** (transactions hors « À vérifier » / total) — comme mesure de progrès de l'automatisation, à inclure dans le suivi mensuel (section 6).

### 2.4 Renforcement possible via Paperless (optionnel, phase future)

Piste évoquée dans la conversation, à ne considérer qu'une fois les étapes 1–3 de la feuille de route (section 7) stabilisées : rapprocher une facture détectée par `paperless` (ex. facture EDF, montant + date) avec la transaction bancaire correspondante dans Actual, pour fiabiliser/vérifier automatiquement la catégorie plutôt que de se fier au seul libellé bancaire. Resterait un script propre à `actual-budget` consommant l'API de `paperless` comme le ferait un client externe (principe d'autonomie racine — pas de couplage direct entre les deux services).

## 3. Transactions récurrentes (Schedules)

Dépenses mensuelles identifiées dans la conversation, candidates à un `Schedule` Actual (montant/date anticipés, avec ou sans validation automatique) une fois les contrats/montants réels connus :

- Loyer / crédit
- Assurance(s)
- Internet / téléphone
- Abonnements (ex. Netflix)
- Électricité
- Crèche / école

Objectif : la vue « dépenses prévisibles » (déjà dépensé + à venir) et le rapprochement avec les transactions bancaires réelles au fil du mois.

## 4. Budget : méthode de remplissage

Distinction essentielle reprise de la conversation :

- **Dépenses régulières courantes** → budget mensuel fixe, calé sur l'historique observé dès qu'il existe (moyenne 3/6/12 mois).
- **Dépenses irrégulières** → traitées comme des **objectifs d'épargne mensualisés**, pas comme une dépense ponctuelle à prévoir le mois où elle tombe. Exemples :

| Objectif | Coût annuel estimé | Enveloppe mensuelle |
|---|---|---|
| Assurance voiture | 600 €/an | 50 €/mois |
| Vacances | 2 400 €/an | 200 €/mois |
| Noël / anniversaires | 600 €/an | 50 €/mois |
| Entretien voiture | 800 €/an | ~67 €/mois |
| Travaux | 1 200 €/an | 100 €/mois |

Montants ci-dessus indicatifs (repris de la conversation) — à recalculer sur la base des dépenses réelles du foyer une fois l'historique disponible (étape 3, section 7).

- **Budget Templates / Goals** (fonctionnalité Actual encore expérimentale) pour automatiser le remplissage, selon le type de catégorie :

| Catégorie | Règle de remplissage envisagée |
|---|---|
| Courses | Moyenne des 6 derniers mois |
| Électricité | Montant du schedule associé |
| Vacances | Montant fixe mensuel (ex. 200 €) |
| Noël | Atteindre un montant cible à une date donnée (déc.) |
| Épargne de précaution | % des revenus du mois |

- **Lecture du foyer** : séparer explicitement Revenus / Dépenses courantes / Objectifs-épargne pour afficher `Reste = Revenus − Dépenses − Objectifs`, plutôt que de traiter l'épargne comme une dépense parmi d'autres.

## 5. Rapports / dashboards à mettre en place

Trois niveaux de lecture, tous réalisables avec les rapports natifs d'Actual (pas de dashboard externe nécessaire dans un premier temps) :

1. **Vue immédiate** — rapport « Dépenses du mois » par catégorie/groupe (répond à « combien avons-nous dépensé ce mois-ci ? »).
2. **Comparaison mensuelle** — rapport multi-mois par catégorie sur les 3 à 6 derniers mois (détecte les dérives : ex. Courses en hausse).
3. **Tendance longue vs budget** — rapport moyenne 6 mois comparée au montant budgété par catégorie, pour ajuster les budgets irréalistes (trop hauts ou trop bas).

Complément : un rapport dédié **Revenus vs Dépenses vs Épargne**, avec taux d'épargne (`Épargne / Revenus`), pour le pilotage global du foyer.

## 6. Automatisation avancée (optionnelle, phase future)

Actual expose une CLI/API permettant de lire/modifier comptes, transactions, catégories, règles, schedules et budgets. Piste évoquée dans la conversation : un script maison produisant un rapport mensuel familial automatique (revenus, dépenses, épargne, taux d'épargne, alertes de dérive vs moyenne, dépenses exceptionnelles, prévision de fin de mois), en y intégrant l'indicateur de couverture de l'automatisation défini en 2.3 (% de transactions catégorisées automatiquement / restées en « À vérifier »).

Une deuxième piste, spécifiquement pour maximiser la catégorisation (au-delà des règles Actual natives), serait un script périodique utilisant la CLI/API pour repérer les transactions encore en « À vérifier », proposer une catégorie par similarité avec les payees déjà classés (correspondance floue sur le libellé), et ne laisser à valider que les cas ambigus — mais seulement si le taux de couverture obtenu avec les règles natives (section 2) plafonne malgré leur affinement, pour ne pas construire une usine à gaz avant d'avoir constaté un besoin réel.

À ne pas implémenter avant d'avoir un historique réel suffisant (étapes 3/4 de la feuille de route). Si réalisé un jour, le script reste propre à ce service (pas de dépendance croisée avec un autre service du dépôt, principe d'autonomie racine).

## 7. Feuille de route

Reprend les 4 étapes proposées dans la conversation, adaptées aux prérequis de ce dépôt :

- **Étape 1** (bloquée par : déploiement du service + connexion bancaire) — 2 à 3 mois de données : synchroniser les comptes, nettoyer les payees, mettre en place l'arborescence de catégories (section 1).
- **Étape 2** — construire les règles de catégorisation au fil de l'eau (section 2) jusqu'à couverture large des dépenses courantes récurrentes.
- **Étape 3** — fixer des budgets réalistes à partir de l'historique observé, en distinguant dépenses régulières et irrégulières (section 4).
- **Étape 4** — ajouter schedules (section 3) et goals/templates (section 4), puis piloter via les rapports (section 5) ; envisager le script maison (section 6) si le besoin se confirme à l'usage.

## 8. Point de vigilance : synchronisation bancaire

Rappel signalé dans la conversation, à garder en tête au moment du branchement bancaire (hors périmètre de ce document) : les identifiants/API d'open banking sont conservés côté serveur et **ne sont pas couverts par le chiffrement E2E** d'Actual (contrairement aux données de budget elles-mêmes). Connecteur pressenti pour une installation française en 2026 : **Enable Banking** — GoCardless BankAccountData reste documenté mais n'accepte plus de nouveaux comptes.
