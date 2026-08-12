# Architecture — edge

## Vue d'ensemble

```
                                Internet
                                    │
                     vault.<base>.duckdns.org
                     paperless.<base>.duckdns.org
                     (...)
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │             EDGE               │
                    │                                │
                    │  sidecar-ddns   (1 seul, met   │
                    │                 à jour TOUS    │
                    │                 les sous-doms) │
                    │  sidecar-acme   (1 seul, DNS-01│
                    │                 DuckDNS, tous  │
                    │                 les sous-doms) │
                    │  reverse-proxy  (TLS + routage │
                    │                 par Host header)│
                    └───────────────┬────────────────┘
                                    │  HTTP (comme un client externe)
                    ┌───────────────┼────────────────┐
                    ▼                                ▼
          127.0.0.1:PORT_bitwarden          127.0.0.1:PORT_paperless
                    │                                │
          ┌─────────────────┐              ┌──────────────────┐
          │   bitwarden     │              │    paperless     │
          │ (service autonome│              │ (service autonome │
          │  Docker Compose) │              │  Docker Compose)  │
          └─────────────────┘              └──────────────────┘
```

Chaque flèche `edge → service backend` est un appel HTTP simple vers un port publié sur l'hôte — jamais un réseau Docker partagé, jamais un fichier commun.

## Contrat d'intégration : ce qu'un service backend doit faire pour être routé par edge

1. **Publier un port HTTP** sur l'hôte (ex. `127.0.0.1:8081:80` dans son propre `compose.yaml`). Ce port ne parle jamais TLS : `edge` s'en occupe.
2. **Ne posséder aucun token DuckDNS, aucun certificat, aucun sidecar DDNS/ACME.** Si le service en avait avant (cas de bitwarden), les retirer lors de la migration.
3. **Ne rien connaître d'edge.** Le service backend n'a pas besoin de savoir qu'il est routé, ni par qui, ni comment. Aucune configuration côté backend ne référence `edge`.
4. Optionnel : si le service a besoin de websockets (cas de vaultwarden `/notifications/hub`), le signaler dans la config de routage d'edge (upgrade headers), toujours côté edge uniquement.

## Ce qu'edge seul connaît (routing config interne à `/edge/`)

Une table de routage, propre à `edge`, qui associe :

| sous-domaine | upstream (host:port) | websocket |
|---|---|---|
| `jvince.duckdns.org` (bitwarden) | `127.0.0.1:8081` | oui (`/notifications/hub` — routé, bug 3012 corrigé, voir `bitwarden/_plan/plan-migration-edge.md`) |
| `paperless-jvince.duckdns.org` (paperless) | `127.0.0.1:8082` | non |

Note : `edge/compose.yaml` tourne en `network_mode: host` (voir Phase 4 de `plan.md`), donc l'upstream est bien `127.0.0.1:PORT` et non `host.docker.internal:PORT` — cette dernière forme a été essayée puis abandonnée (502 systématique, un port publié en `127.0.0.1` n'étant pas joignable depuis un réseau bridge Docker).

Cette table vit uniquement dans `/edge/` (ex. `nginx/conf.d/*.conf` générés ou statiques). Ajouter un service = ajouter une entrée ici, sans toucher au service backend au-delà de la Phase 1 du contrat ci-dessus.

## DDNS et ACME centralisés : pourquoi c'est correct de mutualiser ici

Le principe d'autonomie interdit de partager une ressource *entre deux services métier*. Mais le token DuckDNS et les certificats ne sont pas une ressource métier d'un service — ce sont l'objet même du service `edge`. Centraliser ici n'est pas une violation de l'autonomie : c'est literally le rôle de ce service, au même titre qu'un CDN ou un load balancer managé le ferait pour n'importe quelle infra, sans jamais toucher au code ou à la config des applications qu'il route.

Conséquence pratique : une seule requête de mise à jour DDNS peut couvrir tous les sous-domaines (l'API DuckDNS accepte une liste `domains=vault,paperless,...`), puisque tous ces sous-domaines pointent vers la même IP publique (même réseau domestique).

## Réutilisation de la découverte technique de bitwarden

Le sidecar DDNS actuel de bitwarden a déjà découvert et résolu un problème réel, directement réutilisable ici sans modification de logique :

- `www.duckdns.org` n'a pas d'enregistrement AAAA : impossible de compter sur l'auto-détection IPv6 de DuckDNS.
- Déterminer l'IPv6 publique via un service dual-stack (`api6.ipify.org`), puis l'envoyer explicitement à DuckDNS en IPv4.
- Le conteneur DDNS doit tourner en `network_mode: host` pour voir l'IPv6 réelle de la machine (le réseau bridge Docker par défaut ne route pas l'IPv6 sortant).

Ces choix techniques sont documentés une seule fois ici (dans `edge`) ; bitwarden n'aura plus besoin de les maintenir après sa migration (voir `plan.md`, phase migration).
