# Plan de réalisation — edge

> `edge` est extrait de ce qui existait déjà dans `bitwarden` (sidecar-acme, sidecar-ddns, reverse-proxy TLS + DuckDNS), pour être exploité par tous les services du dossier racine. Décisions actées : service dédié et autonome (pas de config partagée), un sous-domaine DuckDNS par service, migration de bitwarden incluse.

## Phase 0 — Squelette du service — **implémentée et validée**

- `compose.yaml` créé : `reverse-proxy` (nginx), `sidecar-ddns`, `sidecar-acme`, `cert-init`. Logique DDNS/ACME reprise de `bitwarden/compose.yaml` (détection IPv6 via `api6.ipify.org`, `network_mode: host` pour le DDNS, `profiles` pour activer/désactiver DuckDNS en local) — généralisée pour gérer plusieurs sous-domaines en une seule mise à jour DDNS (`DUCKDNS_SUBDOMAINS`).
- Table de routage matérialisée par un fichier nginx par service dans `nginx/conf.d/`, plus un gabarit `_example-service.conf.template` documentant comment en ajouter un.
- **Validé réellement** (2026-08-12) : `docker compose run --rm cert-init` génère le certificat auto-signé de test ; `docker compose up -d reverse-proxy` démarre ; `curl -k https://localhost` répond bien avec le texte de test ; `nginx -t` valide la config. Nettoyé ensuite (`docker compose down -v`), aucun `.env` laissé sur le disque.
- **Pas encore fait à ce stade** : `DUCKDNS_TOKEN` n'a pas encore été déplacé depuis `bitwarden/.env` — aucun sous-domaine réel n'existe encore côté edge (Phase 1), donc rien à migrer avant que le token soit effectivement utilisé ici.
- Voir `README.md` pour reproduire ces étapes.

## Phase 1 — Sous-domaines DuckDNS — **partiellement faite**

- `paperless-jvince.duckdns.org` créé (2026-08-12) sur le même compte DuckDNS que bitwarden. Token noté dans `edge/.env` (non committé).
- Reste à faire : réutiliser le sous-domaine déjà existant de bitwarden (`jvince.duckdns.org`) côté edge — ne se fera qu'à la Phase 5 (migration bitwarden), pas avant.
- Objectif de sortie de phase : chaque sous-domaine résout vers l'IP publique courante de la maison — **validé pour `paperless-jvince`** (voir Phase 2).

## Phase 2 — DDNS centralisé — **validée pour un sous-domaine**

- `sidecar-ddns` testé réellement (2026-08-12) avec `DUCKDNS_SUBDOMAINS=paperless-jvince` : réponse DuckDNS `OK`, confirmée par résolution publique tierce (`dig @1.1.1.1`) — l'IPv6 mise à jour correspond bien à celle envoyée.
- **Attention** : cette IPv6 est celle de l'environnement où tourne actuellement `edge` (poste de développement/sandbox), pas celle du réseau domestique final — même situation que la Phase B de bitwarden, testée sur un PC avant la bascule sur le Raspberry Pi cible (voir `bitwarden/README.md`). À refaire sur la machine définitive avant mise en production.
- **Non encore validé** : le format de réponse DuckDNS pour une mise à jour de **plusieurs** sous-domaines en une seule requête (`domains=sub1,sub2`) — un seul sous-domaine a été testé jusqu'ici. À revalider dès qu'un deuxième sous-domaine (ex. celui de bitwarden, Phase 5) sera ajouté à `DUCKDNS_SUBDOMAINS`.
- Conteneur arrêté après validation (`docker compose stop sidecar-ddns`) — à relancer (`docker compose up -d sidecar-ddns`) pour continuer vers la Phase 3 (émission du certificat).

## Phase 3 — ACME centralisé — **validée pour un sous-domaine**

- Un seul `sidecar-acme` (DNS-01, plugin DuckDNS) qui émet/renouvelle les certificats pour chaque sous-domaine.
- Un certificat par sous-domaine (décision confirmée à l'usage) — plus simple à faire évoluer indépendamment, pas de ré-émission globale si un seul sous-domaine change.
- **Validé réellement (2026-08-12)** pour `paperless-jvince.duckdns.org` : émission staging via challenge DNS-01 (pose/vérification/retrait automatique du TXT chez DuckDNS par acme.sh), certificat installé dans `certs:/paperless-jvince/{fullchain,privkey}.pem`. Vérifié avec `openssl x509` : `issuer=(STAGING) Let's Encrypt`, `subject=CN=paperless-jvince.duckdns.org`, validité jusqu'au 2026-11-09.
- **Correction découverte à l'usage** (non anticipée à la conception) : `acme.sh --install-cert` ne crée pas le dossier de destination dans le volume `certs` — il faut le créer explicitement (`mkdir -p /certs/<subdomain>`) avant le premier `--install-cert` de chaque nouveau sous-domaine. Documenté dans `README.md` phase 3.
- Objectif de sortie de phase : certificats valides pour tous les sous-domaines, stockés dans un volume propre à `edge` (jamais partagé) — **fait pour `paperless-jvince`**, reste à refaire pour le sous-domaine de bitwarden lors de sa migration (Phase 5).
- **Pas encore fait** : passage en production (toujours en staging à ce stade, volontairement — voir Phase 4/5 avant de basculer).

## Phase 4 — Reverse-proxy et routage — **validée (via la migration bitwarden, Phase 5)**

- Un `reverse-proxy` nginx qui termine le TLS pour chaque sous-domaine et route vers l'upstream correspondant (table de routage, voir `architecture.md`).
- Chaque service backend doit d'abord respecter le contrat d'intégration (`architecture.md`) : publier un port HTTP sur l'hôte, ne rien connaître d'edge.
- **Correction majeure découverte à l'usage** (non anticipée à la conception) : `extra_hosts: host.docker.internal:host-gateway` ne peut PAS atteindre un port backend publié en `127.0.0.1:PORT` (un socket lié à la loopback n'accepte que les connexions locales à l'hôte, pas celles arrivant via la passerelle d'un réseau bridge Docker) — 502 systématique. Solution retenue : `reverse-proxy` tourne en `network_mode: host`, comme `sidecar-ddns`. `edge/compose.yaml` et tous les fichiers `nginx/conf.d/*.conf` mis à jour (`proxy_pass http://127.0.0.1:PORT`, plus de `host.docker.internal`).
- Objectif de sortie de phase : une requête HTTPS sur un sous-domaine atteint le bon service backend en HTTP — **validé réellement** avec bitwarden (voir Phase 5).

## Phase 5 — Migration de bitwarden — **implémentée et validée en local (2026-08-12)**

- Fait : retrait de `sidecar-acme`, `sidecar-ddns`, `cert-init` et de la terminaison TLS du `reverse-proxy` de `bitwarden/compose.yaml` (option a : reverse-proxy HTTP interne conservé, publié sur `127.0.0.1:8081`).
- Fait : `DUCKDNS_TOKEN` retiré de `bitwarden/.env`/`.env.example`.
- Fait : sous-domaine existant `jvince.duckdns.org` ajouté à `edge` (`DUCKDNS_SUBDOMAINS`, certificat staging émis/installé), bloc `edge/nginx/conf.d/bitwarden.conf` créé avec le support websocket pour `/notifications/hub`.
- **Test de bout en bout réussi** : `https://jvince.duckdns.org` (via edge, certificat staging, `--resolve` en environnement de test) sert la page Vaultwarden. Format DDNS multi-sous-domaines (`paperless-jvince,jvince`) validé au passage : réponse `OK` unique (pas concaténée par domaine), les deux résolvent correctement.
- **Bug pré-existant découvert, sans lien avec la migration** : `/notifications/hub` proxifie vers `vaultwarden:3012`, mais Vaultwarden 1.37.1 n'écoute plus sur ce port séparé (websocket temps réel probablement cassé depuis un moment). Non corrigé ici — voir `bitwarden/_plan/plan-migration-edge.md`.
- Objectif de sortie de phase : bitwarden fonctionne à l'identique pour l'utilisateur final, mais ne possède plus aucune logique DNS/TLS propre — **atteint pour le trafic HTTP standard**, pas encore vérifié pour le websocket (bug distinct ci-dessus).
- **Pas encore fait** : bascule en production (toujours staging), test sur la machine cible finale (Raspberry Pi, cf. `bitwarden/README.md`), purge des volumes orphelins `bitwarden_certs`/`bitwarden_acme_state` (laissés intacts, non référencés).
- Détail complet : voir `bitwarden/_plan/plan-migration-edge.md`.

## Phase 6 — Intégration de paperless — **implémentée et validée en local (2026-08-12)**

- Fait : socle Paperless-ngx implémenté (`db` + `broker` + `paperless`, voir `paperless/_plan/plan.md` phase 0 — devancée par rapport aux phases 1-6 métier de paperless, qui restent à faire) ; son webserver publie `127.0.0.1:8082`.
- Fait : `paperless.conf` créé dans `edge/nginx/conf.d/` pour le sous-domaine `paperless-jvince.duckdns.org` (créé dès la Phase 1 de ce plan, avant même que le service paperless existe).
- **Test de bout en bout réussi** : `https://paperless-jvince.duckdns.org` (via edge, certificat staging) sert la page de connexion Paperless-ngx.
- Objectif de sortie de phase : paperless accessible depuis Internet via son sous-domaine, sans qu'aucune config DNS/TLS n'existe dans le dossier `paperless/` — **atteint**.
- **Pas encore fait** : passage en production (toujours staging), test sur la machine cible finale, configuration métier de Paperless (types de documents, tags, RAD/LAD).

## Phase 7 (ultérieure) — Services suivants

- Tout nouveau service du dossier racine ayant besoin d'exposition publique suit le même contrat d'intégration (`architecture.md`) : un port HTTP publié, une entrée dans la table de routage d'`edge`, rien de plus.
