# Analyse de besoin fonctionnel — service bitwarden

## 1. Contexte

Le service doit héberger une instance de gestionnaire de mots de passe compatible Bitwarden sur un serveur local (domicile), et la rendre accessible depuis internet, alors que la connexion internet du site ne dispose que d'une adresse **IPv6** routée par le FAI (pas d'IPv4 publique garantie — CGNAT probable). Le serveur est situé derrière un routeur domestique.

## 2. Objectifs

- **OBJ-1** — Disposer d'une instance Bitwarden-compatible utilisable au quotidien (web vault, extension navigateur, applications mobiles/desktop).
- **OBJ-2** — Rendre cette instance accessible depuis internet en IPv6, via un nom de domaine.
- **OBJ-3** — Sécuriser les échanges avec un certificat TLS valide et gratuit (Let's Encrypt), renouvelé automatiquement sans intervention manuelle.
- **OBJ-4** — Pouvoir tester la solution progressivement : d'abord en local, puis en conditions réelles (accès externe), de façon réversible.

## 3. Acteurs

- **Utilisateur principal** (administrateur du service, seul utilisateur ou petit groupe/famille du vault).
- **Clients Bitwarden** (web vault, extension navigateur, app mobile, app desktop, CLI) — consomment l'API exposée par le service.
- **Let's Encrypt** (autorité de certification) — émet/renouvelle les certificats TLS.
- **Fournisseur DNS** (registrar / provider de la zone DNS du domaine) — doit permettre soit une mise à jour dynamique de l'enregistrement AAAA, soit une API exploitable pour un challenge ACME DNS-01.
- **FAI** — SFR (offre fibre). Fournit la connectivité IPv6 via la box SFR (interface de gestion pare-feu/redirection appelée "FGW"). Pas de garantie documentée de stabilité du préfixe dans la durée — à traiter comme potentiellement variable (voir Q2).

## 4. Besoins fonctionnels

| ID | Besoin |
|---|---|
| BF-1 | Fournir un serveur compatible API Bitwarden (vault chiffré, synchronisation multi-device). |
| BF-2 | Le service doit être joignable depuis internet via une URL HTTPS stable, même si l'adresse/préfixe IPv6 du serveur change. |
| BF-3 | Présenter un certificat TLS valide, reconnu par les clients, émis gratuitement (Let's Encrypt), sans rupture de service lors du renouvellement. |
| BF-4 | Automatiser le renouvellement du certificat via un composant dédié ("sidecar"), sans action manuelle récurrente, avec détection d'échec. |
| BF-5 | Le nom de domaine doit se mettre à jour automatiquement (DDNS) si le préfixe IPv6 change. |
| BF-6 | Pouvoir valider le service en local (sans dépendre de la résolution DNS publique ni de l'exposition internet) avant toute mise en production réelle. |
| BF-7 | Protéger l'accès administrateur (token fort) et supporter la 2FA pour les comptes utilisateurs. |
| BF-8 | Permettre la sauvegarde et la restauration des données du vault indépendamment du reste de l'infrastructure. |

## 5. Besoins non fonctionnels

- **Disponibilité** : résister à un changement de préfixe IPv6 sans intervention manuelle prolongée (convergence DNS en quelques minutes).
- **Sécurité** : aucun secret (token admin, clé API DNS) committé dans le repo ; TLS 1.2+ uniquement ; headers de sécurité (HSTS...).
- **Simplicité d'exploitation** : le service démarre/s'arrête comme une unité via Docker Compose, sans étape manuelle complexe récurrente.
- **Réversibilité** : l'exposition internet doit pouvoir être désactivée facilement sans casser l'usage local.
- **Faible empreinte ressources** : le serveur local n'est pas dédié haute performance → privilégier une implémentation légère.

## 6. Contraintes

- **CT-1** — Pas d'IPv4 publique garantie (CGNAT probable) : aucune solution ne doit dépendre d'un accès entrant IPv4.
- **CT-2** — Préfixe IPv6 potentiellement non fixe : nécessite une mise à jour dynamique du DNS (DDNS).
- **CT-3** — Renouvellement Let's Encrypt : nécessite un challenge HTTP-01 (port 80 entrant joignable) ou DNS-01 (API du fournisseur DNS) — arbitrage en conception.
- **CT-4** — Routeur domestique : configuration explicite du pare-feu/forwarding IPv6 nécessaire (pas de NAT en IPv6, mais un pare-feu par défaut bloque en général l'entrant).
- **CT-5** — Rate limits Let's Encrypt en production : les tests répétés doivent utiliser l'environnement staging.
- **CT-6** — Le service doit être entièrement conteneurisé et orchestré via **Docker Compose** (un fichier `compose.yaml` unique regroupant vaultwarden, reverse-proxy, sidecar-acme et sidecar-ddns) — pas de composant installé nativement sur l'hôte, hors Docker lui-même.

## 7. Hypothèses / réponses au besoin

- **Q1 — Nom de domaine** : **résolu** — pas de domaine existant, utilisation d'un sous-domaine **DuckDNS** gratuit (ex. `xxx.duckdns.org`). Le fournisseur DNS est donc DuckDNS ; le challenge ACME DNS-01 s'appuiera sur le plugin DuckDNS d'`acme.sh`/`certbot`, et le sidecar-ddns utilisera l'API DuckDNS (mise à jour par token). Option domaine payant laissée ouverte pour une évolution ultérieure si besoin.
- **Q2 — Stabilité du préfixe IPv6 (SFR fibre)** : non documentée avec certitude ; à traiter comme **potentiellement variable** (aucune garantie de préfixe fixe sur une offre résidentielle). Le design doit donc systématiquement inclure un DDNS IPv6, sans supposer de stabilité. À confirmer empiriquement en Phase C (observer si le préfixe change sur plusieurs jours/semaines, ou après un redémarrage de la box).
- **Q3 — Pare-feu IPv6 du routeur** : **résolu** — le routeur domestique permet de configurer un pare-feu IPv6 entrant (redirection de ports). Point d'attention propre à SFR fibre : la box SFR expose sa propre interface de gestion IPv6 ("FGW") ; si un routeur personnel est branché derrière la box, il faut soit ouvrir les ports aux deux niveaux (box SFR + routeur personnel), soit basculer la box en mode "Passthrough/Bridge" pour ne gérer le pare-feu IPv6 qu'à un seul endroit (recommandé pour éviter une double couche de pare-feu à maintenir).
- **Q4 — Vaultwarden vs Bitwarden officiel** : **résolu** — Vaultwarden retenu par défaut (léger, compatible clients, adapté multi-utilisateurs 2-3 personnes).
- **Q5 — Mono/multi-utilisateurs** : **résolu** — usage multi-utilisateurs, 2 à 3 personnes. Impact : le besoin d'inviter des comptes doit être couvert (BF-9 ci-dessous) ; une configuration SMTP n'est pas strictement obligatoire (Vaultwarden permet à l'admin de générer manuellement un lien d'invitation à partager hors bande), mais reste l'option la plus confortable pour 2-3 utilisateurs récurrents.

## 7bis. Besoin complémentaire identifié

| ID | Besoin |
|---|---|
| BF-9 | Permettre l'invitation de 2 à 3 utilisateurs distincts (comptes séparés), avec ou sans SMTP configuré (fallback : lien d'invitation généré manuellement par l'admin). |

## 8. Hors périmètre

- Migration de données depuis un autre gestionnaire de mots de passe.
- Haute disponibilité / clustering (un seul serveur local, pas de redondance prévue).
- Gestion multi-tenant avancée (organisations complexes, SSO entreprise).
