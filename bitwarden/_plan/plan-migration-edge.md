# Plan de migration — délégation DNS/TLS vers `edge`

> Décision actée (2026-08-12) : le DuckDNS/ACME/DDNS de bitwarden est extrait vers un nouveau service autonome `/edge/`, pour être réutilisé par l'ensemble des services du dossier racine (paperless notamment). Ce document décrit **comment migrer bitwarden** vers ce nouveau point d'entrée, sans casser le service déjà validé en Phase B (`plan-conception.md` §5).

Ce document ne remplace pas `plan-conception.md` : il en modifie uniquement le §1 (architecture), §2.2 à 2.4 (composants ACME/DDNS/reverse-proxy) et la fin du §5 (Phase C). Les besoins fonctionnels (`analyse-besoin-fonctionnel.md`) et les décisions Vaultwarden/multi-utilisateurs restent inchangées.

## Ce qui change

- `bitwarden` perd : `sidecar-acme`, `sidecar-ddns`, la terminaison TLS de son `reverse-proxy`, et le secret `DUCKDNS_TOKEN`.
- `bitwarden` gagne : un `reverse-proxy` (ou exposition directe de vaultwarden) qui ne parle plus qu'en HTTP interne, publié sur un port de l'hôte.
- `edge` récupère : le token DuckDNS, le sous-domaine existant (`jvince.duckdns.org`, déjà validé en Phase B — cf. `plan-conception.md` §5 Phase B), la logique DDNS/ACME déjà testée en conditions réelles (détection IPv6 via `api6.ipify.org`, `network_mode: host`, plugin `dns_duckdns`).

**Important** : le sous-domaine DuckDNS ne change pas. Aucune reconfiguration côté clients (extensions navigateur, apps mobiles Bitwarden déjà connectées).

## Étapes

1. **Ne rien casser tout de suite** : `edge` (phases 0-4 de `edge/_plan/plan.md`) doit être opérationnel et testé (au moins en Let's Encrypt staging, sur un sous-domaine de test) *avant* de toucher à `bitwarden/compose.yaml`.
2. **Publier le port HTTP de vaultwarden/reverse-proxy** sur l'hôte (ex. `127.0.0.1:8443:443` → à requalifier en HTTP pur, voir point 3), pour qu'`edge` puisse le joindre comme un client externe.
3. **Simplifier le `reverse-proxy` de bitwarden** : il n'a plus besoin de terminer le TLS ni de gérer de certificat. Deux options à trancher au moment de l'implémentation :
   - a) le garder comme simple proxy HTTP interne (utile pour les règles spécifiques déjà présentes : websocket `/notifications/hub`, `client_max_body_size`, headers) ;
   - b) le supprimer et publier directement le port HTTP de vaultwarden, en déplaçant ces règles spécifiques dans la config de routage d'`edge`.
   - Option (a) recommandée : elle garde ces réglages métier du côté du service qui les connaît (bitwarden), et `edge` reste un simple routeur TLS générique.
4. **Retirer** `sidecar-acme`, `sidecar-ddns`, le volume `certs`, le volume `acme_state`, et le profil Compose `duckdns` de `bitwarden/compose.yaml`.
5. **Retirer** `DUCKDNS_TOKEN` de `bitwarden/.env` et `.env.example`.
6. **Enregistrer bitwarden dans la table de routage d'`edge`** (`edge/_plan/architecture.md`) : sous-domaine existant → port HTTP publié par bitwarden, avec le flag websocket pour `/notifications/hub`.
7. **Retester la progressivité** déjà utilisée pour la Phase B/C de bitwarden (`plan-conception.md` §5) mais au niveau d'`edge` cette fois : staging Let's Encrypt d'abord, puis bascule production, avant de couper l'ancien chemin.
8. **Couper l'ancien chemin** seulement après validation : `bitwarden` ne publie plus le port 443 lui-même, seul `edge` écoute sur les ports publics de la machine.

## Risque principal et mitigation

Le risque principal est une coupure d'accès pour les utilisateurs déjà configurés (2-3 comptes, BF-9) si le sous-domaine change ou si la bascule TLS échoue. Mitigation : garder le sous-domaine identique, valider `edge` en staging avant toute coupure, et ne retirer les sidecars de `bitwarden` qu'après confirmation qu'`edge` sert correctement ce même sous-domaine en HTTPS.

## Statut

**Migration implémentée et validée en local (2026-08-12)**, option (a) retenue (reverse-proxy HTTP interne conservé). Détail :

- `bitwarden/compose.yaml` : `sidecar-acme`, `sidecar-ddns`, `cert-init` retirés, ainsi que les volumes `certs`/`acme_state`. `reverse-proxy` ne termine plus le TLS, écoute en clair sur `127.0.0.1:8081` (publié sur l'hôte).
- `bitwarden/.env` et `.env.example` : `DUCKDNS_TOKEN` et `COMPOSE_PROFILES=duckdns` retirés. `LOCAL_HOSTNAME` conservé (sert uniquement à construire `DOMAIN` pour vaultwarden).
- `bitwarden/nginx/conf.d/vaultwarden.conf` : blocs `ssl_*`/`listen 443 ssl` retirés, `listen 80`, `X-Forwarded-Proto` relayé depuis le header reçu d'edge plutôt que recalculé localement.
- Côté `edge` : sous-domaine existant `jvince.duckdns.org` ajouté à `DUCKDNS_SUBDOMAINS`, certificat staging émis/installé, bloc `nginx/conf.d/bitwarden.conf` créé (routage vers `127.0.0.1:8081`).
- **Correction découverte à l'usage, non anticipée à la conception** : `host.docker.internal:host-gateway` (essayé en premier côté edge) ne peut pas atteindre un port publié en `127.0.0.1:PORT` — un socket lié à la loopback n'accepte que les connexions arrivant par la loopback. Solution retenue : `network_mode: host` sur le `reverse-proxy` d'edge (documenté dans `edge/compose.yaml` et `edge/_plan/plan.md`).
- **Test de bout en bout réussi** : `https://jvince.duckdns.org` (via edge, certificat `(STAGING) Let's Encrypt`, `--resolve` vers l'environnement de test) sert bien la page Vaultwarden.
- **Bug pré-existant découvert à cette occasion, sans lien avec cette migration — corrigé (2026-08-12)** : `location /notifications/hub` proxifiait vers `vaultwarden:3012`, port qui n'existe plus depuis Vaultwarden 1.31.0 (le websocket a été intégré au port HTTP principal, activé par défaut depuis 1.31.0 — confirmé via la doc du projet). Corrigé : la location proxifie désormais vers `vaultwarden:80` (avec les mêmes headers que le bloc `/`), et `WEBSOCKET_ENABLED` (déprécié) a été remplacé par `ENABLE_WEBSOCKET` dans `compose.yaml`. **Validé réellement** : la requête d'upgrade websocket passe de `502` (port introuvable) à `401` (authentification requise — comportement normal sans token), en direct sur `127.0.0.1:8081` et via `edge` (`https://jvince.duckdns.org/notifications/hub`).
- **Pas encore fait** : bascule en production (toujours staging), test sur la machine cible finale (Raspberry Pi), suppression effective des anciens volumes orphelins `bitwarden_certs`/`bitwarden_acme_state` (laissés intacts sur disque, plus référencés par `compose.yaml`, à purger manuellement si souhaité : `docker volume rm bitwarden_certs bitwarden_acme_state`), test applicatif réel du websocket avec un compte/client Bitwarden authentifié (le `401` confirme juste que l'endpoint est atteignable, pas que la sync fonctionne de bout en bout).
