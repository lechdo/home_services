# Service edge — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service est le **point d'entrée Internet unique** de tous les services du dossier racine qui ont besoin d'être exposés publiquement (nom de domaine, TLS).

## Rôle du service

- Posséder **le** compte/token DuckDNS pour l'ensemble des services (un seul, pas un par service).
- Maintenir à jour les enregistrements DNS DuckDNS (DDNS) de tous les sous-domaines enregistrés.
- Émettre et renouveler les certificats TLS (Let's Encrypt, challenge DNS-01 DuckDNS) pour chacun de ces sous-domaines.
- Terminer le TLS et router chaque requête HTTPS entrante vers le service backend correspondant, selon le sous-domaine (Host header).

## Pourquoi un service à part, et pas une config partagée

Le `CLAUDE.md` racine interdit tout dossier/fichier/config/ressource partagé entre services (pas de `common/`, `shared/`, `libs/`). `edge` respecte cette règle strictement : ce n'est pas une exception, c'est un **service autonome de plus**, qui rend un service (le routage HTTPS) aux autres exactement comme le ferait un fournisseur externe :

- `edge` ne partage **aucun fichier, aucune config, aucun réseau Docker** avec les services qu'il route.
- `edge` communique avec chaque service backend **uniquement en HTTP**, vers un port que ce service publie sur l'hôte — exactement ce qu'un client externe ferait. C'est la seule forme de communication inter-services autorisée par le CLAUDE.md racine, et `edge` s'y conforme.
- Un service backend n'a **aucune connaissance** d'edge : il ne fait qu'exposer un port HTTP local. C'est `edge`, seul, qui sait quels services existent et comment les router (routing config interne à `/edge/`).
- Un service backend ne possède **jamais** son propre token DuckDNS, ses propres certificats, ou son propre sidecar DDNS/ACME une fois routé par `edge`. Toute cette responsabilité est centralisée ici, une seule fois, pour toute la maison.

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : `edge` est packagé entièrement via **Docker Compose** (reverse-proxy, sidecar-ddns, sidecar-acme). Aucun composant installé nativement sur l'hôte (hors Docker).
- **Un sous-domaine DuckDNS par service backend** (ex. `vault.<base>.duckdns.org`, `paperless.<base>.duckdns.org`), jamais de routage par chemin sous un même nom — plus simple pour le TLS (un cert/SAN par sous-domaine) et pour éviter des apps qui supposent être servies à la racine.
- **DDNS centralisé** : un seul sidecar met à jour l'IP (IPv6, cf. contrainte CGNAT découverte sur bitwarden) de **tous** les sous-domaines enregistrés en une fois — tous les services de cette maison sont sur le même réseau/la même IP publique, pas besoin d'un sidecar par service.
- **ACME centralisé** : un seul sidecar acme.sh gère l'émission/le renouvellement DNS-01 pour tous les sous-domaines.
- **Contrat d'intégration avec un service backend** (voir `_plan/architecture.md`) : le backend publie un port HTTP (jamais HTTPS, jamais de TLS géré par lui) sur l'hôte ; il n'a rien d'autre à faire pour être exposé.
- **Secrets** : le token DuckDNS ne vit que dans `/edge/.env` (jamais committé), nulle part ailleurs dans le dossier racine.
- **Non négociable** : si un service veut changer son mode d'exposition (nouveau sous-domaine, retrait), la modification se fait uniquement dans la config de routage d'`edge`, jamais en donnant à `edge` un accès quelconque au code/fichiers du service backend.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases, y compris la migration de bitwarden.
- `_plan/architecture.md` — schéma d'ensemble et contrat d'intégration service backend ↔ edge.
