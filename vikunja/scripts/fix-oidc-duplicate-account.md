# Protocole — compte fantôme créé par une connexion OIDC (authentik)

## Symptôme

Après bascule sur SSO authentik (`VIKUNJA_AUTH_LOCAL_ENABLED: "false"`, voir
`_plan/plan.md` phase 3b / `compose.yaml`), un utilisateur se connecte via
authentik, voit bien son nom affiché dans les paramètres Vikunja, mais **ne
retrouve plus ses tâches/projets/équipes** — comme si le compte était vide.

## Cause

Vikunja relie une connexion OIDC à un compte **uniquement** par la paire
`(issuer, subject)` embarquée dans le token — jamais par nom d'utilisateur ni
par email. Si cette paire ne correspond à aucun compte Vikunja existant,
Vikunja **crée automatiquement un nouveau compte vide** plutôt que d'échouer :
- avec le `preferred_username` du token si ce nom est libre côté Vikunja ;
- sinon avec un nom généré aléatoirement (style « adjective-adjective-noun »,
  ex. `vaguely-loved-pelican`) si le nom voulu est déjà pris par un compte
  existant (typiquement l'ancien compte local du même utilisateur).

Deux façons courantes d'arriver à ce (issuer, subject) inattendu :
1. **Plusieurs identités authentik partagent le même email** (ex. le
   superadmin `akadmin` créé automatiquement à l'installation d'authentik, et
   le vrai compte personnel — cas rencontré le 2026-08-27) : se connecter via
   la mauvaise session authentik crée un compte Vikunja pour *cette*
   identité-là.
2. **Le compte authentik a été recréé** (supprimé puis recréé avec le même
   nom) : authentik lui attribue un nouveau `subject` interne, différent de
   celui que Vikunja avait peut-être déjà enregistré.

Dans les deux cas, **aucune donnée n'est perdue** : l'ancien compte Vikunja
(local ou lié à l'ancien `subject`) garde toutes ses données intactes, il
n'est simplement plus atteignable par connexion OIDC tant que son
`issuer`/`subject` ne pointe pas vers la bonne identité authentik.

## Diagnostic — à faire avant toute correction

1. **Lister les comptes Vikunja** (sur la machine qui héberge le conteneur) :
   ```bash
   docker exec vikunja-vikunja-1 ./vikunja user list
   ```
   Repérer :
   - le compte qui a les vraies données (généralement `issuer=local`, c'est
     l'ancien compte d'avant la bascule SSO) → **le compte à garder** ;
   - le compte utilisé pour la connexion SSO actuelle (`issuer` = l'URL du
     provider authentik, `updated` récent = dernière connexion) → **le
     compte fantôme**.

2. **Vérifier qu'il n'y a pas eu de vraie activité sur le compte fantôme**
   avant de le supprimer — le script `fix-oidc-duplicate-account.sh` fait
   cette vérification automatiquement (projets hors "Inbox" par défaut,
   tâches, équipes, partages, filtres, favoris, webhooks, jetons API,
   commentaires, assignations, réactions, notifications, liens de partage) et
   s'arrête sans rien supprimer si l'une d'elles n'est pas vide. Dans ce cas,
   traitement manuel au cas par cas (réassigner les lignes concernées vers le
   compte à garder avant suppression) — le script ne le fait pas
   automatiquement.

   Si le compte authentik ambigu est `akadmin` (superadmin créé à
   l'installation, cf. `authentik/_plan/plan.md`), vérifier aussi qu'aucun
   autre service protégé par authentik n'a le même souci (l'admin s'est
   peut-être connecté par erreur sur `akadmin` plutôt que son compte
   personnel ailleurs aussi).

## Correction

```bash
ssh julien@raspi-home.local   # ou l'hôte qui héberge le service vikunja concerné
cd ~/home_services/vikunja/scripts   # ou où que ce script ait été déployé
./fix-oidc-duplicate-account.sh <compte_a_garder> <compte_fantome>
```

Exemple réel (2026-08-27) :
```bash
./fix-oidc-duplicate-account.sh julien vaguely-loved-pelican
```

Le script (voir son en-tête pour le détail) : sauvegarde la base, arrête
brièvement le conteneur (quelques secondes de coupure), relie l'identité OIDC
du compte fantôme au compte à garder, supprime le compte fantôme (uniquement
s'il est vide), puis redémarre le conteneur.

## Après correction

- Se reconnecter via authentik avec le compte concerné et vérifier que les
  projets/tâches/équipes attendus sont bien là.
- Si un deuxième compte fantôme existe pour un autre utilisateur du foyer
  (ex. Virginie), répéter l'opération avec ses propres noms de compte.
- Les sauvegardes intermédiaires (`~/vikunja-merge-backup/` sur l'hôte) ne
  sont pas supprimées automatiquement par le script — à nettoyer
  manuellement une fois la correction confirmée stable, ou à conserver si un
  `plan-sauvegarde.md` dédié (voir `_plan/plan.md` phase 5, non encore fait)
  ne couvre pas encore ce cas.

## Prévention

Pour éviter que ça se reproduise à chaque recréation de compte authentik :
côté authentik, éviter les comptes secondaires/de test partageant l'email
d'un compte réel (ici `akadmin`) sur les applications où ce email sert aussi
d'identifiant applicatif OIDC — ou, côté Vikunja, envisager (question
ouverte, non tranchée) un mapping OIDC qui matche par email en plus de
`(issuer, subject)` si une version future de Vikunja le permet en
configuration.
