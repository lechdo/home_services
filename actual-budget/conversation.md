parles moi de actual budget 

Oui. Actual Budget est probablement très intéressant dans ton cas, surtout si ton objectif est de construire progressivement un petit SI familial auto-hébergé autour de Vaultwarden + Paperless.

5
C'est quoi ?

Actual Budget est une application de gestion financière open source, local-first et auto-hébergeable. Elle est conçue autour du principe de budget par enveloppes : tu attribues réellement l'argent que tu possèdes à des catégories, plutôt que de simplement prévoir tes dépenses.

Par exemple :

Revenus du mois : 4 000 €

Logement                 1 200 €
Courses                    600 €
Électricité                 150 €
Voiture                     250 €
Enfant                      200 €
Vacances                    300 €
Épargne sécurité            500 €
Dépenses diverses           400 €
--------------------------------
                         3 600 €

Puis chaque dépense vient réduire l'enveloppe correspondante.

L'intérêt est surtout de pouvoir répondre immédiatement à :

« Est-ce qu'on peut se permettre cette dépense ? »

plutôt que :

« Combien avons-nous sur le compte ? »

Pourquoi je pense que ça colle bien à ton projet familial

Tu as déjà :

Vaultwarden → identités, mots de passe, comptes familiaux
Paperless → documents administratifs
Actual → argent, budget, comptes, dépenses

Tu obtiens quelque chose d'assez cohérent :

Besoin familial	Service
Mots de passe	Vaultwarden
Documents	Paperless
Finances / budget	Actual Budget
Agenda	Google Calendar / éventuellement CalDAV
Tâches	GQueues / éventuellement autre
Photos	Immich
Fichiers	Nextcloud
Authentification	Keycloak, si réellement nécessaire

Et surtout, Actual est pensé pour fonctionner sur plusieurs appareils, avec synchronisation entre les clients via ton serveur.

Le gros avantage : le budget familial plutôt que la simple comptabilité

C'est là où Actual est assez différent d'une application bancaire.

Tu peux avoir par exemple :

                    BUDGET FAMILIAL

Dépenses courantes
 ├── Courses
 ├── Restaurants
 ├── Essence
 ├── Vêtements
 └── Loisirs

Charges
 ├── Loyer
 ├── Électricité
 ├── Assurances
 └── Télécom

Projets
 ├── Vacances
 ├── Voiture
 ├── Travaux maison
 └── Noël / anniversaires

Épargne
 ├── Épargne de précaution
 ├── Gros achats
 └── Long terme

Les sommes non dépensées restent dans leurs enveloppes et peuvent être reportées. C'est particulièrement intéressant pour les dépenses irrégulières : voiture, vacances, Noël, assurance annuelle, réparations, etc.

Et pour la banque ?

C'est probablement le point qui t'intéressera le plus.

Actual peut importer :

CSV
QIF
OFX
QFX
CAMT.053

et peut également utiliser des services d'open banking.

En Europe, Enable Banking est désormais supporté et a été ajouté en 2026. GoCardless BankAccountData reste également documenté, mais n'accepte plus de nouveaux comptes.

Donc pour une installation française en 2026, je regarderais particulièrement Enable Banking + ta banque avant de construire ton installation autour de la synchronisation bancaire.

Il y a néanmoins une nuance importante : la synchronisation bancaire n'est pas simplement une fonction locale magique. Les identifiants/API d'open banking sont conservés sur le serveur et ne sont pas couverts par le chiffrement E2E d'Actual.

Pour ton approche auto-hébergée, ce n'est pas forcément un problème, mais il faut en être conscient.

Et côté technique

C'est justement un logiciel qui se prête bien à ton environnement.

Tu peux le faire tourner en Docker et l'intégrer à ton infrastructure existante.

Le modèle est grosso modo :

                     Internet
                         │
                    reverse proxy
                         │
          ┌──────────────┴──────────────┐
          │                             │
     Vaultwarden                    Actual
          │                             │
     PostgreSQL?                    données budget
          │                             │
          └──────────────┬──────────────┘
                         │
                     serveur

Actual est local-first : le client travaille localement et les changements sont synchronisés entre appareils. Il propose également le chiffrement de bout en bout des données de budget.

Et contrairement à beaucoup de projets auto-hébergés, le projet est encore très actif : la version 26.7.0 est sortie le 1er juillet 2026, avec notamment des améliorations des rapports, tags et automatisations budgétaires.

Le point qui me semble particulièrement intéressant pour toi

Je ne l'utiliserais pas seulement comme un agrégateur de comptes bancaires.

Je le verrais plutôt comme le moteur financier du foyer.

Par exemple :

Paperless détecte :

facture EDF → 137,42 €

Actual sait :

catégorie = Électricité
budget restant = 180 €
→ OK

Et avec les transactions bancaires :

Carrefour → 86,32 €
→ Courses
→ enveloppe Courses : 213,68 € restantes

Tu pourrais donc progressivement arriver à un système où une grosse partie de la gestion administrative familiale devient automatique.

Actual possède d'ailleurs des règles, transactions planifiées, rapports, tags et une API, ce qui ouvre pas mal de possibilités d'automatisation.

Pour ton projet, je le mettrais clairement dans la shortlist, et probablement avant d'ajouter un autre outil de gestion financière plus généraliste.

Si tu veux aller plus loin, je peux aussi te proposer une architecture complète de ton "serveur familial" (Vaultwarden + Paperless + Actual + agenda + tâches + photos + fichiers), en distinguant ce qui vaut vraiment le coup d'auto-héberger de ce qui risque surtout de rajouter de la maintenance.

Non, et c'est justement un des points forts d'Actual Budget pour ton serveur familial.

Architecture très simple

Avec Docker, un seul conteneur Actual suffit :

                 actual-budget
                 ┌─────────────┐
 navigateur ────►│  Actual      │
 téléphone ─────►│  Server      │
                 │              │
                 │ SQLite       │
                 └──────┬───────┘
                        │
                 /data sur le host

Actual utilise SQLite, pas PostgreSQL, MariaDB ou Redis.

Le conteneur stocke ses données dans /data, avec notamment :

/data/
├── server-files/
│   └── account.sqlite
└── user-files/
    ├── ...sqlite
    └── ...blob

Les budgets eux-mêmes sont donc des fichiers SQLite stockés dans le volume persistant.

Donc ton docker-compose.yml peut être extrêmement léger

Conceptuellement :

services:
  actual:
    image: actualbudget/actual-server:latest
    restart: unless-stopped
    volumes:
      - ./data:/data
    ports:
      - "5006:5006"

C'est pratiquement tout ce dont Actual a besoin. La documentation officielle propose exactement ce modèle avec un volume /data.

Et c'est même assez différent de Paperless

Pour ton infrastructure familiale :

Paperless
   │
   ├── PostgreSQL
   ├── Redis
   ├── stockage documents
   └── consommateur / workers

Vaultwarden
   │
   └── SQLite (selon configuration)

Actual
   │
   └── SQLite

Actual est donc beaucoup plus léger à administrer que Paperless.

Et il n'a pas non plus besoin d'une base PostgreSQL centrale que tu pourrais mutualiser avec tes autres applications.

Le point important : sauvegarder /data

Dans ton cas, je traiterais tout le répertoire /data comme la donnée critique d'Actual.

Tu peux donc simplement faire :

/opt/services/actual/
├── compose.yml
└── data/       ← à sauvegarder

Puis ton système de backup habituel :

Actual /data
      │
      ▼
   restic
      │
      ├── NAS
      └── stockage distant

C'est particulièrement agréable avec SQLite : pas besoin de mettre en place un serveur PostgreSQL et ses procédures de dump. La documentation indique d'ailleurs explicitement que les données sont persistées via le volume /data.

Et il y a une subtilité intéressante

Actual est local-first : le serveur n'est pas exactement une « base de données centrale » classique. Les clients conservent eux-mêmes les données et le serveur assure notamment la synchronisation.

C'est probablement une bonne architecture pour ta famille :

             ┌───────────────┐
             │ Actual Server │
             │    SQLite     │
             └───────┬───────┘
                     │ sync
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       PC Julien   Android    PC autre

Donc pas de PostgreSQL à ajouter, pas de Redis, pas de service de cache obligatoire.

Pour ton projet de serveur familial, Actual est même un assez bon exemple du type de service que tu sembles rechercher : une application complète, un conteneur, un volume persistant, un reverse proxy et des backups.

est ce un service lourd ? 

Non, Actual Budget est très léger — surtout comparé à Paperless.

Pour un serveur familial avec quelques utilisateurs, je le classerais parmi les services auto-hébergés faciles à caser sur une petite machine.

Ordre de grandeur

Actual Server est essentiellement :

un serveur Node.js
une base SQLite
un volume de données
pas de PostgreSQL
pas de Redis
pas de worker séparé
pas de moteur OCR
pas d'indexation lourde

En fonctionnement normal, la charge CPU est donc généralement très faible. La RAM est également modeste ; pour ton usage familial, je ne lui réserverais certainement pas une grosse quantité de mémoire.

À comparer :

Service	Ressources	Charge typique
Actual Budget	🟢 faible	🟢 très faible
Vaultwarden	🟢 faible	🟢 très faible
Paperless	🟠 moyenne	🟠 variable
Immich	🔴 moyenne/forte	🔴 forte lors de l'indexation
Nextcloud	🟠 moyenne	🟠 moyenne
Jellyfin	🟠/🔴	🔴 si transcodage

Pour Actual + Vaultwarden, tu peux quasiment les considérer comme deux petits services annexes sur ton serveur.

Dans ton cas

Sur ton OptiPlex, qui est largement surdimensionné pour ça, tu pourrais faire tourner sans problème :

Docker
│
├── Vaultwarden
├── Actual Budget
├── Paperless
├── PostgreSQL
├── Redis
├── reverse-proxy
└── ...

et Actual ne sera clairement pas le service qui déterminera les besoins matériels.

Le seul moment où Actual peut avoir une activité un peu plus importante est lors de certaines opérations de synchronisation/import ou sur de très gros historiques, mais pour une famille avec quelques années de transactions bancaires, c'est négligeable.

Donc oui : si ton critère est "ajouter un service familial sans ajouter une usine à gaz", Actual Budget est un excellent candidat.

aujourd’hui 13:59
comment exploiter actual une fois qu'il a les donées de banque? je souhaites avoir une vision claire des dépenses par thème, avoir de quoi évaluer le budget, et ce en automatisant au maximum

Oui — et je pense qu'il faut justement ne pas utiliser Actual comme un simple relevé bancaire amélioré. Pour ton besoin, je le configurerais comme un système en trois niveaux :

les transactions bancaires arrivent automatiquement ;
Actual les classe automatiquement ;
le budget et les rapports te donnent une lecture synthétique du foyer.

L'objectif serait qu'au quotidien tu n'aies quasiment rien à saisir.

1. D'abord, construire une bonne arborescence

Je commencerais par des catégories assez larges, plutôt que 50 catégories ultra-précises.

Par exemple :

🏠 LOGEMENT
   Loyer / crédit
   Électricité
   Eau
   Chauffage
   Internet / téléphone
   Entretien

🍎 ALIMENTATION
   Courses
   Restaurants
   Livraison

🚗 TRANSPORT
   Carburant
   Entretien
   Assurance
   Transports en commun

👨‍👩‍👦 FAMILLE
   Enfant
   Vêtements
   Activités
   Santé
   École

🎮 LOISIRS
   Sorties
   Culture
   Jeux / informatique
   Abonnements

🛒 VIE COURANTE
   Vêtements
   Maison
   Hygiène
   Achats divers

💰 PROJETS / ÉPARGNE
   Vacances
   Voiture
   Travaux
   Épargne de précaution
   Gros achats

💸 IMPÔTS / ADMINISTRATIF
   Impôts
   Taxes
   Frais bancaires

Je privilégierais 10–15 groupes avec 3–8 catégories chacun.

Pourquoi ? Parce que ton objectif est de pouvoir ouvrir Actual et comprendre en quelques secondes :

« Où part notre argent ? »

Les rapports d'Actual permettent justement d'analyser les dépenses par catégories et groupes, et les rapports ont été enrichis récemment.

2. L'automatisation la plus importante : les règles

C'est là qu'Actual devient vraiment intéressant.

Supposons que le CMB fournisse :

CARREFOUR MARKET ELBEUF

Tu catégorises une fois :

Alimentation → Courses

Actual peut ensuite apprendre cette association et créer une règle automatiquement. Les règles peuvent notamment agir sur le payee, la catégorie, le compte, le montant, la date ou les notes.

Donc après quelques semaines :

CMB
 │
 ▼
Transaction
 │
 ▼
Actual
 │
 ├── "CARREFOUR" → Courses
 ├── "TOTAL" → Carburant
 ├── "NETFLIX" → Abonnements
 ├── "EDF" → Électricité
 ├── "AMAZON" → Achats divers
 └── "ASSURANCE X" → Assurances

Et tu n'as plus besoin de catégoriser ces transactions.

Encore mieux : nettoyer les noms

Les banques donnent souvent des noms atroces :

CB*1234 AMAZON EU SARL 08/13

Actual peut apprendre à transformer ça en :

Amazon

puis appliquer :

Amazon → Achats divers

Il dispose justement d'un système de Payee Rules et de Category Learning.

3. Les transactions récurrentes : les schedules

Deuxième gros morceau d'automatisation.

Tu as probablement des dépenses comme :

Loyer                 tous les mois
Assurance              tous les mois
Internet               tous les mois
Netflix                tous les mois
Électricité            tous les mois
Crèche / école         tous les mois

Tu peux créer des Schedules.

Actual sait alors anticiper :

13 août

Déjà dépensé             2 140 €
À venir                  1 380 €

──────────────────────────────
Dépenses prévisibles     3 520 €

Les schedules peuvent être récurrents, avoir une date de fin, ou être ponctuels, et peuvent être automatiquement inscrits dans le registre ou nécessiter une validation.

C'est particulièrement utile pour ton objectif de prévision budgétaire.

4. Ensuite vient le vrai budget

C'est là que je distinguerais deux choses.

Dépenses régulières

Par exemple :

Courses             650 €/mois
Carburant           250 €/mois
Restaurants          150 €/mois
Loisirs             150 €/mois

Tu fixes un budget.

Dépenses irrégulières

Et là, Actual devient beaucoup plus intéressant.

Par exemple :

Assurance voiture       600 €/an
Vacances              2 400 €/an
Noël                    600 €/an
Entretien voiture       800 €/an
Travaux               1 200 €/an

Au lieu de penser :

« Je dois dépenser 600 € en décembre »

tu penses :

« Je mets 50 €/mois dans l'enveloppe Noël. »

Ainsi, quand décembre arrive :

Noël
Budget disponible : 600 €
Dépense            : 520 €
Solde              : 80 €

C'est exactement le type de problème que le système d'enveloppes d'Actual cherche à résoudre. La vue Budget affiche notamment budgeté / dépensé / solde, avec report des sommes restantes.

5. Et tu peux aller encore plus loin dans l'automatisation

La version actuelle d'Actual dispose d'un système de Budget Templates / Goals, encore expérimental, qui peut automatiser le remplissage du budget.

Par exemple :

Courses
→ budget moyen des 6 derniers mois

Électricité
→ montant prévu par le schedule

Vacances
→ 200 €/mois

Noël
→ atteindre 600 € en décembre

Épargne
→ 10 % des revenus

Donc au lieu de faire chaque mois :

« Bon, combien je mets dans chaque catégorie ? »

tu peux progressivement arriver à :

Actual connaît les règles de financement du budget.

La documentation donne même comme exemples le budget basé sur une moyenne des six derniers mois, le remplissage jusqu'à un plafond, ou un pourcentage des revenus.

6. Pour ta vision des dépenses : je ferais trois niveaux

C'est probablement le point le plus important pour toi.

Niveau 1 — vue immédiate
Dépenses du mois

Alimentation       720 €   ███████████
Logement         1 350 €   █████████████████
Transport          310 €   █████
Famille            240 €   ████
Loisirs            180 €   ███
Divers             220 €   ███

Tu veux pouvoir répondre instantanément :

« Combien avons-nous dépensé ce mois-ci ? »

Niveau 2 — comparaison

Puis :

                 Juin    Juillet    Août
Alimentation      680      720       650
Transport         290      310       280
Loisirs           220      180       150
Famille           240      240       260

Tu détectes immédiatement les dérives.

Niveau 3 — tendance longue

Et là, le plus intéressant :

                    Moy. 6 mois    Budget
Alimentation           670 €        650 €
Transport              295 €        300 €
Loisirs                185 €        150 €
Famille                245 €        250 €

Tu peux alors décider :

« Notre budget alimentation à 650 € est irréaliste. On dépense 670 € depuis six mois. »

ou au contraire :

« On dépense 185 € en loisirs mais on prévoit 250 €. On peut réduire. »

Actual permet justement de préremplir un budget à partir des moyennes des 3, 6 ou 12 derniers mois.

7. Je ferais une distinction essentielle : dépenses vs épargne

Pour avoir une vision réellement utile du foyer, je ne mettrais pas :

Épargne

dans les dépenses.

Je ferais plutôt :

REVENUS
    Salaires
    Autres revenus

DÉPENSES
    Logement
    Alimentation
    Transport
    Famille
    Loisirs
    Vie courante
    etc.

OBJECTIFS
    Vacances
    Voiture
    Travaux
    Sécurité

Ainsi tu peux avoir :

Revenus                     4 500 €

Dépenses courantes         -3 250 €
Objectifs / épargne        -  700 €
                            ───────
Reste                         550 €

C'est beaucoup plus parlant pour piloter le foyer.

8. Et je pousserais l'automatisation assez loin

Avec ton profil technique, tu as même une possibilité intéressante : ne pas considérer Actual comme une boîte noire.

Actual possède désormais une CLI permettant de lire et modifier comptes, transactions, catégories, règles, schedules et budgets.

Donc à terme tu pourrais avoir :

              CMB
               │
               ▼
       Synchronisation
               │
               ▼
         Actual Budget
               │
       ┌───────┴────────┐
       │                │
     Rules          Schedules
       │                │
       ▼                ▼
Catégorisation      Prévisions
       │                │
       └───────┬────────┘
               ▼
            Reports

Et éventuellement un petit script maison qui produit, par exemple, un rapport familial mensuel :

BUDGET — AOÛT 2026

Revenus                 4 620 €
Dépenses                3 410 €
Épargne                   700 €

Taux d'épargne            15,2 %

⚠️ Courses       +12 % vs moyenne
✓ Transport       -8 %
✓ Loisirs        -15 %

Dépenses exceptionnelles :
  • Réparation voiture     380 €
  • Vêtements enfant       120 €

Prévision fin de mois :
  Reste estimé             410 €

Ça, pour moi, serait le vrai objectif de ton installation.

Ce que je ferais concrètement à ta place

Je partirais sur une mise en place en 4 étapes, sans chercher à tout automatiser immédiatement :

Étape 1 — 2/3 mois de données

Importer/synchroniser les comptes CMB et nettoyer les payees.

Étape 2 — automatisation

Créer progressivement les règles :

commerçant → catégorie

Après quelques semaines, la majorité des transactions courantes devrait être catégorisée automatiquement. Actual est justement conçu pour apprendre ces associations.

Étape 3 — budget réaliste

Utiliser l'historique pour déterminer :

combien coûte réellement notre foyer ?

puis fixer les budgets.

Étape 4 — pilotage

Ajouter schedules + objectifs + éventuellement les automatisations de budget, et utiliser les rapports pour suivre les tendances.

Et surtout

Je n'essaierais pas de catégoriser chaque dépense de manière excessivement fine.

Le bon niveau est celui qui permet de prendre une décision.

Par exemple :

Carrefour → Courses

est utile.

Mais :

Carrefour → Courses → Légumes

ne l'est probablement pas, sauf si tu veux réellement analyser la composition de tes courses.

Le but est que le système travaille pour vous, pas que vous passiez votre temps à administrer Actual.

Et vu ce que tu cherches à faire avec tes autres services familiaux, je pense qu'on peut aller assez loin : concevoir une arborescence Actual adaptée à un foyer français, avec les catégories, budgets, dépenses annuelles, règles automatiques et indicateurs que je mettrais en place. Ce serait probablement la meilleure étape avant de l'installer.