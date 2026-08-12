# Plan de conception — service bitwarden

Ce document répond aux besoins exprimés dans `analyse-besoin-fonctionnel.md`. Il propose une architecture cible et une stratégie de mise en œuvre progressive.

**État des décisions** : FAI = SFR fibre (préfixe IPv6 traité comme potentiellement variable, sans garantie de stabilité) ; routeur personnel capable de gérer un pare-feu IPv6 entrant (avec vigilance sur la double couche pare-feu box SFR/routeur — voir §3) ; usage multi-utilisateurs (2-3 comptes) ; Vaultwarden retenu ; nom de domaine = sous-domaine **DuckDNS** gratuit (cf. §4bis) ; **conteneurisation via Docker Compose obligatoire** (CT-6) — un seul fichier `compose.yaml` orchestrant tous les composants. Toutes les décisions structurantes sont maintenant prises ; les phases A à D (§5) peuvent être implémentées.

## 1. Architecture cible

```
Internet (IPv6)
      |
      v
Routeur domestique
  - pare-feu IPv6 : autorise 443 (et 80 si HTTP-01) vers l'IPv6 du serveur
  - pas de NAT nécessaire en IPv6 (adressage de bout en bout)
      |
      v
Serveur local — un seul compose.yaml (Docker Compose), 4 services
  +------------------+     +----------------+     +------------------------+
  |  reverse-proxy   |<--->|  vaultwarden   |     |  sidecar-ddns          |
  |  (nginx)         |     |  (API + vault) |     |  (met à jour AAAA)     |
  |  TLS termination |     +----------------+     +------------------------+
  +--------^---------+
           | volume partagé (certificats)
  +--------+---------+
  |  sidecar-acme     |
  |  (obtient/renouvelle le certificat, DNS-01 recommandé)
  +-------------------+
```

Vaultwarden n'est jamais exposé directement sur internet : seul le reverse-proxy écoute sur les ports publics.

## 2. Composants

### 2.1 vaultwarden
- Image `vaultwarden/server`, retenue pour sa légèreté (sqlite, faible empreinte mémoire) — adaptée à un serveur domestique (Bitwarden officiel, plus lourd/MSSQL, écarté).
- Volume dédié pour les données (base sqlite, attachments, sends, config).
- N'écoute qu'en interne (réseau docker), jamais directement sur une interface publique.
- Configuration clé : `ADMIN_TOKEN` (secret fort, non committé), `SIGNUPS_ALLOWED=false` une fois les 2-3 comptes créés, `WEBSOCKET_ENABLED=true` (sync temps réel).
- Invitations (2-3 utilisateurs, BF-9) : soit configurer un SMTP (le plus confortable pour des invitations récurrentes), soit utiliser le fallback Vaultwarden — l'admin génère le lien d'invitation depuis le panneau `/admin` et le transmet hors bande (message, etc.), sans dépendre d'un serveur mail. Le SMTP n'est donc pas bloquant pour démarrer.

### 2.2 reverse-proxy (nginx)
- Termine le TLS, relaie vers vaultwarden en HTTP interne.
- Charge certificat/clé depuis un volume partagé avec le sidecar ACME.
- Recharge sa configuration après chaque renouvellement (déclenché par le sidecar, ex. `nginx -s reload`).
- Headers de sécurité : HSTS, `X-Content-Type-Options`, etc.

### 2.3 sidecar-acme (renouvellement de certificat)
- Rôle unique et isolé : obtenir/renouveler le certificat Let's Encrypt, indépendamment du reverse-proxy — répond explicitement à BF-3/BF-4.
- **Méthode de challenge recommandée : DNS-01** (via l'API du fournisseur DNS). Justification : ne dépend pas de la joignabilité entrante (port 80), donc robuste face à un préfixe IPv6 instable ou un pare-feu capricieux (CT-1, CT-2, CT-3).
  - Alternative : HTTP-01, plus simple si le fournisseur DNS n'a pas d'API supportée par l'outil ACME retenu — nécessite alors que le port 80 soit fiablement joignable en IPv6.
- Outil envisagé : `acme.sh` (large support de fournisseurs DNS) ou `certbot` + plugin DNS du fournisseur.
- Fonctionnement : boucle périodique (cron interne, ex. 1x/jour) — Let's Encrypt renouvelle automatiquement si le certificat a moins de 30 jours de validité restants.
- Écrit le certificat renouvelé dans le volume partagé, puis déclenche le reload nginx.
- Secrets (clé API DNS) fournis via variable d'environnement/secret Docker, jamais committés dans le repo.

### 2.4 sidecar-ddns (mise à jour IPv6 dynamique)
- Détecte l'IPv6 publique courante et met à jour l'enregistrement AAAA du domaine si elle change — répond à BF-5/CT-2.
- Réalisable via `ddclient`, un script custom appelant l'API DNS, ou un client DDNS dédié selon le fournisseur retenu (ex. client DuckDNS si cette option est retenue — cf. §4bis).
- Astuce de conception : réserver une adresse IPv6 LAN stable (partie hôte fixe, ex. DHCPv6 avec réservation) pour que seule la partie préfixe change — simplifie la règle de pare-feu, qui n'a alors pas besoin d'être réécrite à chaque changement de préfixe si elle est exprimée en relatif à l'hôte.

## 3. Réseau & sécurité

- **Point spécifique SFR fibre** : la box SFR expose sa propre interface de gestion du pare-feu/redirection IPv6 (interface dite "FGW"). Si le serveur est branché directement sur la box SFR, la règle de pare-feu IPv6 se configure sur la box elle-même. Si un routeur personnel est branché derrière la box SFR (double équipement), il y a potentiellement **deux couches de pare-feu IPv6** à synchroniser (box SFR + routeur perso), ce qui complique la maintenance. Deux options :
  - Ouvrir les ports nécessaires aux deux niveaux (box SFR ET routeur perso) — fonctionne mais double la surface de configuration à maintenir.
  - Passer la box SFR en mode **Passthrough/Bridge** pour l'IPv6, afin que seul le routeur personnel gère le pare-feu IPv6 entrant (recommandé — un seul point de configuration, plus simple à auditer).
- Le routeur (celui qui gère effectivement le pare-feu IPv6 entrant, cf. point ci-dessus) forwarde les ports 443 — et 80 uniquement si HTTP-01 est finalement retenu — vers l'adresse IPv6 LAN du serveur.
- Seul le reverse-proxy écoute sur les ports publics ; vaultwarden reste interne au réseau docker.
- Panneau admin Vaultwarden (`/admin`) protégé par `ADMIN_TOKEN` fort, à restreindre davantage si possible (règle proxy dédiée).
- Durcissement ultérieur (hors MVP) : fail2ban ou équivalent sur les tentatives de connexion échouées.

## 4. Choix du challenge ACME — DNS-01 vs HTTP-01

| Critère | HTTP-01 | DNS-01 |
|---|---|---|
| Nécessite le port 80 ouvert en entrée | Oui | Non |
| Dépend de la stabilité du chemin réseau entrant | Oui | Non (dépend juste de l'API DNS) |
| Nécessite une API DNS supportée par l'outil ACME | Non | Oui |
| Complexité de mise en œuvre | Plus simple | Légèrement plus complexe (clé API) |

**Recommandation : DNS-01**, le contexte (IPv6 dynamique, routeur domestique, CGNAT probable en IPv4) rendant la joignabilité entrante moins fiable qu'un simple appel à une API DNS. À confirmer une fois Q1 tranchée (fournisseur DNS et support de son API par acme.sh/certbot).

## 4bis. Nom de domaine — DuckDNS (Q1, résolu)

Décision retenue : sous-domaine **DuckDNS** gratuit (ex. `xxx.duckdns.org`), pas de domaine payant pour l'instant.

- **sidecar-ddns** : met à jour l'enregistrement AAAA via l'API DuckDNS (simple requête HTTP authentifiée par token, à exécuter périodiquement — ex. toutes les 5 minutes — pour suivre un éventuel changement de préfixe IPv6 SFR).
- **sidecar-acme** : challenge DNS-01 via le plugin DuckDNS d'`acme.sh` (ou équivalent certbot), en utilisant le même token DuckDNS.
- Secret unique à protéger : le **token DuckDNS** (donne à la fois la mise à jour DNS et la capacité de challenge DNS-01) — à fournir en variable d'environnement/secret Docker, jamais committé.
- Migration future possible vers un domaine payant (OVH, Gandi...) sans remettre en cause l'architecture : seul le fournisseur DNS change dans sidecar-acme et sidecar-ddns.

## 5. Stratégie de test — du local vers le non-local

### Phase A — Local uniquement, sans exposition internet — **implémentée et validée**
- Stack (vaultwarden + nginx) lancée sur le réseau local, nom d'hôte local (ex. entrée `/etc/hosts` sur les postes de test) et certificat auto-signé — aucune dépendance internet, aucune ouverture de pare-feu.
- Implémentation : `compose.yaml` (services `vaultwarden`, `reverse-proxy`, `cert-init`), voir `README.md`.
- Validé (exécution réelle) : démarrage des conteneurs, génération du certificat auto-signé, accès HTTPS via nginx avec réponse 200 de Vaultwarden, arrêt/nettoyage propre.
- Reste à faire par l'utilisateur : test applicatif complet (création de compte, extension navigateur, synchronisation) sur le vrai réseau local.

### Phase B — Local, vrai domaine + Let's Encrypt staging — **implémentée et validée en conditions réelles**
- Domaine : sous-domaine DuckDNS `jvince.duckdns.org` (cf. §4bis), test depuis le LAN.
- Sidecar ACME (`sidecar-acme`, image `neilpang/acme.sh`) pointé sur l'environnement **staging** de Let's Encrypt (préserve le rate limit de production pendant les itérations), challenge DNS-01 via le plugin `dns_duckdns`.
- Sidecar DDNS (`sidecar-ddns`) met à jour l'enregistrement AAAA DuckDNS toutes les 5 minutes.
- Les deux sidecars sont derrière le profil Compose `duckdns` (n'affectent pas la Phase A par défaut).
- **Validé réellement** (avec le vrai token DuckDNS de l'utilisateur) : émission du certificat staging via DNS-01 (challenge TXT posé/vérifié/retiré automatiquement par acme.sh chez DuckDNS), installation dans le volume partagé, nginx sert bien ce certificat (`issuer=(STAGING) Artificial Amaranth YE1`), réponse HTTPS 200 de vaultwarden. `sidecar-ddns` met effectivement à jour l'enregistrement AAAA public (vérifié via une résolution DNS publique tierce, hors de la machine).
- **Deux corrections d'architecture apportées suite à ces tests réels** (non anticipées à la conception initiale) :
  1. `www.duckdns.org` n'a **pas d'enregistrement AAAA** (leur API n'est joignable qu'en IPv4). Il est donc impossible de compter sur l'auto-détection DuckDNS habituelle (requête en IPv6, paramètre `ipv6=` vide) — ça ne peut fonctionner qu'avec des fournisseurs dont le frontend est dual-stack. `sidecar-ddns` détermine donc lui-même l'IPv6 publique via un service tiers dual-stack (`api6.ipify.org`) puis la transmet explicitement à DuckDNS (`ipv6=<adresse>`) via une requête IPv4 classique. Ce point ne concerne que la mécanique DDNS ; il n'affecte pas l'émission du certificat (le challenge DNS-01 d'acme.sh passe par la même API DuckDNS mais uniquement en IPv4, sans dépendre d'IPv6).
  2. Le réseau bridge Docker par défaut (`internal`) ne fournit **aucune connectivité IPv6 sortante** aux conteneurs (limitation du démon Docker, pas de configuration spécifique appliquée). `sidecar-ddns` utilise donc `network_mode: host` plutôt que le réseau `internal`, pour voir directement les interfaces/l'IPv6 réelle de la machine hôte. Ceci ne remet pas en cause l'exposition entrante : le port-mapping Docker (`ports: "443:443"`) publie bien nginx à la fois en IPv4 et IPv6 côté hôte (`0.0.0.0:443` et `[::]:443`) même si le conteneur nginx lui-même n'a qu'une adresse IPv4 interne — Docker fait la traduction. Seule une sortie applicative depuis un conteneur (comme la découverte d'IPv6 par sidecar-ddns) est concernée.
- **Point d'attention pour la Phase C** (identifié mais pas encore traité) : sur cette machine, l'adresse IPv6 globale utilisée pour les connexions sortantes est une adresse temporaire (extensions de confidentialité RFC 4941), qui change périodiquement — distincte de l'adresse stable normalement utilisée pour joindre la machine en entrant (celle que la règle de pare-feu/forwarding du routeur doit cibler). Sur le serveur réel de la Phase C, il faudra soit désactiver les extensions de confidentialité IPv6 (`net.ipv6.conf.*.use_tempaddr=0`), soit s'assurer que `sidecar-ddns` rapporte bien l'adresse stable et non une adresse temporaire, sous peine de désynchronisation entre la règle de pare-feu (adresse fixe) et l'enregistrement DNS (adresse tournante).

### Phase C — Exposition internet réelle (production)
- Ouverture effective du pare-feu IPv6 (443, et 80 si HTTP-01 retenu).
- Bascule du sidecar ACME sur l'environnement de production Let's Encrypt.
- Test d'accès depuis un réseau réellement externe (ex. connexion mobile compatible IPv6) pour confirmer la joignabilité réelle et la validité du certificat.
- Test de résilience : vérifier le comportement lors d'un changement de préfixe IPv6 (redémarrage de la box si possible) pour valider le sidecar DDNS.

### Phase D — Validation du renouvellement automatique
- Déclenchement (forcé ou simulé) du sidecar ACME pour vérifier l'absence d'interruption de service et le rechargement effectif du nouveau certificat par nginx.

## 6. Sauvegarde

- Sauvegarde périodique du volume de données vaultwarden (base + attachments), si possible chiffrée, vers un support indépendant du serveur.
- Restauration testée au moins une fois avant la mise en production réelle (Phase C).

## 7. Roadmap / jalons proposés

1. ~~Validation des questions ouvertes (Q1-Q5) de l'analyse de besoin.~~ **Fait.**
2. Implémentation Phase A (local, sans internet).
3. Création du compte DuckDNS + implémentation sidecar-acme (DNS-01) et sidecar-ddns.
4. Implémentation Phase B (staging Let's Encrypt).
5. Implémentation Phase C (exposition internet réelle, Let's Encrypt production) — inclut la décision Passthrough/Bridge vs double pare-feu (§3).
6. Implémentation Phase D (validation du renouvellement) + mise en place de la sauvegarde.
7. Création des 2-3 comptes utilisateurs (invitation avec ou sans SMTP, BF-9).
8. Durcissement sécurité (fail2ban, restriction accès admin, supervision de l'expiration du certificat).

## 8. Risques & mitigations

| Risque | Mitigation |
|---|---|
| Changement de préfixe IPv6 non détecté → service inaccessible | Sidecar DDNS avec vérification fréquente + alerte en cas d'échec de mise à jour |
| Échec silencieux du renouvellement de certificat → expiration → coupure | Supervision explicite de la date d'expiration du certificat, pas seulement du succès du job de renouvellement |
| Rate limit Let's Encrypt atteint pendant les tests | Usage systématique de l'environnement staging en phase de test |
| Exposition prématurée du panneau admin ou de ports non nécessaires | N'ouvrir que le strict nécessaire (443, 80 seulement si HTTP-01), admin token fort, aucun secret en clair dans le repo |
