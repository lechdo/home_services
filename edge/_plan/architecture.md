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

1. **Publier un port HTTP** sur l'hôte (ex. `127.0.0.1:8081:80` dans son propre `compose.yaml`). Ce port ne parle jamais TLS : `edge` s'en occupe. Rien n'impose que « l'hôte » soit la même machine que celle qui fait tourner `edge` : si le backend vit sur une autre machine du réseau local (cf. `plan.md` phase 7, paperless), le port doit simplement être accessible en HTTP depuis l'IP d'`edge` sur ce réseau (donc borné à l'IP LAN du backend, pas à `127.0.0.1`), et restreint par pare-feu à cette seule IP source — jamais ouvert à tout le LAN ni à Internet.
2. **Ne posséder aucun token DuckDNS, aucun certificat, aucun sidecar DDNS/ACME.** Si le service en avait avant (cas de bitwarden), les retirer lors de la migration.
3. **Ne rien connaître d'edge.** Le service backend n'a pas besoin de savoir qu'il est routé, ni par qui, ni comment. Aucune configuration côté backend ne référence `edge`.
4. Optionnel : si le service a besoin de websockets (cas de vaultwarden `/notifications/hub`), le signaler dans la config de routage d'edge (upgrade headers), toujours côté edge uniquement.

## Ce qu'edge seul connaît (routing config interne à `/edge/`)

Une table de routage, propre à `edge`, qui associe :

| sous-domaine | upstream (host:port) | TLS | websocket |
|---|---|---|---|
| `jvince.duckdns.org` (bitwarden) | `127.0.0.1:8081` | oui (DuckDNS + Let's Encrypt) | oui (`/notifications/hub` — routé, bug 3012 corrigé, voir `bitwarden/_plan/plan-migration-edge.md`) |
| `paperless-jvince.duckdns.org` (paperless) | `192.168.1.109:8082` (second serveur physique, cf. `plan.md` phase 7) | oui (DuckDNS + Let's Encrypt) | non |
| `task-jvince.duckdns.org` (vikunja) | `127.0.0.1:8084` (Raspberry Pi, cf. `vikunja/_plan/plan.md` phase 3b) | oui (DuckDNS + Let's Encrypt) — bascule depuis le mode local le 2026-08-14, voir ci-dessous | non |
| `budget.home.test` (actual-budget) | `192.168.1.109:8083` (second serveur physique, migré le 2026-08-14, cf. `plan.md` phase 10) | oui — **auto-signé**, pas Let's Encrypt (voir ci-dessous) | non |
| `minecraft-jvince.duckdns.org` (panel minecraft) | `192.168.1.109:8086` (second serveur physique, cf. `plan.md` phase 12) | oui (DuckDNS + Let's Encrypt) | non |

Note : `edge/compose.yaml` tourne en `network_mode: host` (voir Phase 4 de `plan.md`), donc l'upstream est bien `127.0.0.1:PORT` et non `host.docker.internal:PORT` — cette dernière forme a été essayée puis abandonnée (502 systématique, un port publié en `127.0.0.1` n'étant pas joignable depuis un réseau bridge Docker).

### Second mode : routage local uniquement, sans sous-domaine public

Le contrat d'intégration ci-dessus suppose implicitement qu'un service a besoin d'une exposition **publique** (sous-domaine DuckDNS + certificat Let's Encrypt). Depuis `actual-budget` (`plan.md` phase 8, 2026-08-13), un service peut aussi être routé par `edge` en restant **local uniquement**, avant même d'avoir un besoin d'accès Internet :

- Bloc nginx `listen 443 ssl`, `server_name <nom>.home.test`, avec un certificat **auto-signé** (généré par `cert-init`, jamais par `sidecar-acme`) — pas d'entrée dans `DUCKDNS_SUBDOMAINS`, pas de certificat de confiance publique.
- Isolation réseau obtenue gratuitement : la box ne transfère que le port 443 depuis Internet vers le Pi (voir `deploiement-raspberry.md`) — accepter le certificat auto-signé une fois par appareil ne change rien à cette isolation, elle vient du transfert de port, pas du TLS.
- Le contrat d'intégration côté backend reste identique (publier un port HTTP sur l'hôte, ne rien connaître d'edge) : seule la partie DNS public/Let's Encrypt est omise, pas le mécanisme de proxy.
- **Correction découverte à l'usage (2026-08-13, actual-budget)** : un premier essai en **HTTP simple** (sans aucun certificat, pas même auto-signé) semblait suffire — jusqu'à ce qu'un vrai navigateur affiche une erreur fatale côté Actual (« besoin de l'accès à SharedArrayBuffer »). Un navigateur ne traite comme « contexte sécurisé » que HTTPS ou `localhost`/`127.0.0.1` — jamais un autre nom d'hôte en clair, même strictement local/LAN. Toute app qui a besoin d'un contexte sécurisé (`SharedArrayBuffer`, service workers...) exige donc HTTPS ici aussi, quitte à rester auto-signé. Ce n'était pas visible avec `curl` (aucune vérification de contexte sécurisé côté HTTP) ni en testant depuis la machine hébergeant `edge` elle-même le cas échéant (`127.0.0.1` bénéficie de l'exception navigateur). D'où : port 80 gardé uniquement comme redirection 301 vers le 443, jamais comme mode de service réel.
- Limite actuelle : la résolution de `<nom>.home.test` n'est pas automatisée (pas de DNS local dans ce dépôt) — à ajouter manuellement dans le `/etc/hosts` de chaque appareil, ou accès direct par IP LAN de la machine qui héberge `edge` (fonctionne identiquement tant qu'un seul service local-only existe avec ce `server_name`, puisqu'il devient alors le fallback implicite pour tout `Host` non reconnu sur le 443).
- **Historique (2026-08-14)** : `vikunja` est passé brièvement par ce mode local (`vikunja.home.test`) avant la création de son sous-domaine DuckDNS le jour même — pendant cette fenêtre, deux services local-only coexistaient (`budget.home.test` et `vikunja.home.test`), et le fallback par IP nue ne pouvait plus servir qu'un seul des deux (le premier bloc chargé par nginx, ordre alphabétique des fichiers `conf.d/*.conf`). Redevenu vrai à nouveau depuis que `vikunja` a rejoint la table DuckDNS ci-dessus : `budget.home.test` est de nouveau l'unique service local-only. À reconsidérer si un futur service reste en mode local à son tour.
- Évolution naturelle : si le service a un jour besoin d'un accès Internet, il rejoint la table ci-dessus (sous-domaine DuckDNS + certificat Let's Encrypt), en suivant le contrat standard — remplace le certificat auto-signé, ne change rien au mécanisme de proxy.

Cette table vit uniquement dans `/edge/` (ex. `nginx/conf.d/*.conf` générés ou statiques). Ajouter un service = ajouter une entrée ici, sans toucher au service backend au-delà de la Phase 1 du contrat ci-dessus.

## Cas particulier : un service qui parle un protocole non-HTTP (minecraft)

Le contrat d'intégration ci-dessus suppose implicitement que le trafic à router est du HTTP/HTTPS (routage L7 par `Host` header, terminaison TLS). Depuis `minecraft` (`plan.md` phase 12, 2026-08-17), un service peut aussi avoir besoin d'exposer un port qui parle un protocole binaire propriétaire (le protocole réseau du jeu Minecraft, sur TCP 25565) — un reverse-proxy L7 ne peut pas router ce trafic.

- Ce port est routé via un bloc `stream {}` nginx (proxy L4, TCP brut) plutôt que `http {}` — premier usage de ce module dans ce dépôt. Config dans `nginx/stream.d/*.conf` (analogue à `conf.d/*.conf` pour le HTTP), incluse depuis un `nginx.conf` personnalisé (`nginx/nginx.conf`, remplace celui livré par défaut dans l'image nginx — nécessaire car le bloc `stream {}` doit vivre au niveau racine de la config, pas dans `conf.d/` qui n'est inclus que dans `http {}`).
- Aucune terminaison TLS sur ce port (le protocole du jeu n'en a pas la notion) et aucune page d'erreur possible si le backend ne répond pas (pas de HTTP à ce niveau) — un client Minecraft dont le serveur est éteint voit un échec de connexion natif, pas une page personnalisée.
- Le contrat d'intégration côté backend reste le même dans l'esprit (publier un port sur l'hôte, edge route sans que le backend ne le sache) — seule la couche de transport change (L4 au lieu de L7).
- Le panel web de gestion de ce même service (démarrer/arrêter le serveur, changer de map), lui, reste un service HTTP tout à fait standard et suit le contrat habituel (table de routage ci-dessus) — un même service backend peut donc avoir une entrée dans `conf.d/` **et** une entrée dans `stream.d/`, chacune pour un port distinct.

## DDNS et ACME centralisés : pourquoi c'est correct de mutualiser ici

Le principe d'autonomie interdit de partager une ressource *entre deux services métier*. Mais le token DuckDNS et les certificats ne sont pas une ressource métier d'un service — ce sont l'objet même du service `edge`. Centraliser ici n'est pas une violation de l'autonomie : c'est literally le rôle de ce service, au même titre qu'un CDN ou un load balancer managé le ferait pour n'importe quelle infra, sans jamais toucher au code ou à la config des applications qu'il route.

Conséquence pratique : une seule requête de mise à jour DDNS peut couvrir tous les sous-domaines (l'API DuckDNS accepte une liste `domains=vault,paperless,...`), puisque tous ces sous-domaines pointent vers la même IP publique (même réseau domestique).

## Réutilisation de la découverte technique de bitwarden

Le sidecar DDNS actuel de bitwarden a déjà découvert et résolu un problème réel, directement réutilisable ici sans modification de logique :

- `www.duckdns.org` n'a pas d'enregistrement AAAA : impossible de compter sur l'auto-détection IPv6 de DuckDNS.
- Déterminer l'IPv6 publique via un service dual-stack (`api6.ipify.org`), puis l'envoyer explicitement à DuckDNS en IPv4.
- Le conteneur DDNS doit tourner en `network_mode: host` pour voir l'IPv6 réelle de la machine (le réseau bridge Docker par défaut ne route pas l'IPv6 sortant).

Ces choix techniques sont documentés une seule fois ici (dans `edge`) ; bitwarden n'aura plus besoin de les maintenir après sa migration (voir `plan.md`, phase migration).
