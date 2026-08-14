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

## Phase 7 — Paperless sur un second serveur physique — **implémentée (2026-08-14), pas encore testée en conditions réelles**

- **Contexte** : `paperless` (et son sidecar rclone, futur RAD/LAD) va quitter la machine qui héberge `edge` pour un second serveur physique, sur le **même réseau local domestique** (confirmé). Ce second serveur possède déjà une IP LAN stable (réservation DHCP existante) mais **n'est pas allumé en permanence** — à la différence de la machine `edge`, qui doit rester joignable pour router tous les services.
- **Ce qui ne change pas** : le contrat d'intégration (`architecture.md`) reste valide tel quel — un seul sous-domaine, aucun token/cert/DDNS côté paperless, edge continue de parler HTTP simple vers un port publié par l'hôte backend. Le seul changement est que « l'hôte backend » n'est plus la machine locale d'edge : le contrat n'a jamais supposé que backend et edge partagent la même machine, seulement qu'ils communiquent en HTTP comme un client externe le ferait — ce qui reste vrai, que ce soit via `127.0.0.1` ou via une IP LAN.
- **À faire (routage)** :
  1. `nginx/conf.d/paperless.conf` : remplacer `proxy_pass http://127.0.0.1:8082;` par `proxy_pass http://<IP_LAN_PAPERLESS>:8082;` (IP LAN réservée du second serveur). Aucun changement de `network_mode: host` côté `reverse-proxy` : ce mode donne déjà accès à tout le réseau local de la machine hôte, pas seulement à la loopback — atteindre une IP LAN distante fonctionne identiquement à atteindre `127.0.0.1`.
  2. Resserrer les timeouts de connexion sur ce bloc précis : `proxy_connect_timeout 3s;`. Nécessaire car le défaut nginx (~60-75s, hérité du timeout TCP du noyau) est beaucoup trop long quand la machine distante est **éteinte** : le paquet SYN part et ne reçoit aucune réponse (ni refus immédiat, contrairement à un service arrêté mais machine allumée). `proxy_read_timeout`/`proxy_send_timeout` laissés à une valeur normale (ex. 30s), pour ne pas couper une requête légitime mais plus lente (ex. redémarrage à froid de Paperless).
  3. Page d'indisponibilité dédiée, servie localement par nginx (aucun appel réseau supplémentaire) : `proxy_intercept_errors on;` + `error_page 502 503 504 =503 /_edge/paperless-unavailable.html;`, avec en-tête `Retry-After` (ex. 300). Répond en HTTP **503** (temporaire), jamais un 502 brut. Fichier `edge/nginx/error-pages/paperless-unavailable.html`, monté dans `reverse-proxy` — reste une ressource propre à `edge` (c'est edge qui décrit comment il représente la panne d'un backend, pas paperless — cohérent avec le principe d'autonomie).
  4. Contenu de la page pensé pour un usage **familial** (Lucas/Virginie/Julien utilisent Paperless, cf. `paperless/_plan/plan.md` phase 0) : message clair et non technique, ex. « Paperless est temporairement indisponible — le serveur qui l'héberge est éteint. Réessayez plus tard, ou contactez Julien. » Pas de détail d'infra exposé (pas d'IP, pas de nom de service interne).
- **Décision explicite** : pas de health-check actif — nginx open-source ne le permet pas nativement (le module tiers `nginx_upstream_check_module` demanderait une recompilation). On reste sur une détection **passive** (timeout de connexion court + `error_page`), cohérente avec le principe de progressivité du repo. À revoir seulement si cette approche s'avère insuffisante en pratique (ex. si un stress applicatif type sondage automatique devient nécessaire).
- **Hors périmètre pour cette phase** (piste notée pour plus tard, pas demandée) : bouton « démarrer le serveur » (Wake-on-LAN) sur la page d'indisponibilité.
- **Fait (2026-08-14)** : IP LAN réelle du second serveur connue (`192.168.1.109`) et renseignée dans `paperless.conf` (`proxy_pass http://192.168.1.109:8082;`) ; timeouts appliqués (`proxy_connect_timeout 3s`, `proxy_read_timeout`/`proxy_send_timeout` à 30s) ; page `nginx/error-pages/paperless-unavailable.html` créée et montée dans `reverse-proxy` (nouveau volume `./nginx/error-pages:/etc/nginx/error-pages:ro` dans `compose.yaml`) ; bloc `location = /_edge/paperless-unavailable.html { internal; ... }` avec `Retry-After: 300`.
- **Pas encore fait** : appliquer ce changement sur la machine réelle (`docker compose up -d` + `nginx -t` + reload) et le tester en conditions réelles — serveur éteint (page 503 rapide, pas de 502 générique, pas d'attente ~60s) et reprise (serveur rallumé → paperless de nouveau joignable sans redémarrer `edge`). Pare-feu côté second serveur explicitement **reporté** (aucun pare-feu actif pour l'instant, décision de ne pas en activer un dans la précipitation sur une machine administrée à distance — voir `paperless/_plan/plan.md` phase 9) : le port `8082` reste donc, pour l'instant, ouvert à tout le LAN plutôt que restreint à l'IP d'edge (`192.168.1.99`).
- Détail côté paperless (binding du port, pare-feu, migration des volumes) : voir `paperless/_plan/plan.md` phase 9.

## Phase 8 — Intégration d'actual-budget, mode local uniquement — **implémentée et validée en local (2026-08-13)**

- **Contexte** : demande explicite (2026-08-13) de router `actual-budget` via `edge` **sans** attendre un besoin d'accès Internet — donc sans sous-domaine DuckDNS, sans certificat, sans passer par `sidecar-acme`/`sidecar-ddns`. Premier service de ce dossier dans ce cas : jusqu'ici, tout service routé par `edge` (bitwarden, paperless) suivait le contrat complet HTTPS/DuckDNS.
- **Nouveau mode documenté** (voir `architecture.md`, section dédiée) : un bloc nginx `listen 80`, `server_name budget.home.test`, sans entrée dans `DUCKDNS_SUBDOMAINS`. Le contrat d'intégration côté backend ne change pas (`actual-budget` publie juste `127.0.0.1:8083`, ne connaît rien d'edge) — seule la partie TLS/DNS publique du contrat est sciemment omise pour l'instant.
- **Pourquoi c'est bien local uniquement, sans action supplémentaire** : le pare-feu de la box (voir `deploiement-raspberry.md`) n'ouvre que le port 443 vers le Pi ; le port 80 n'est jamais transféré depuis Internet. `edge` (network_mode: host) n'est donc atteignable que depuis le réseau local, quel que soit le port — pas besoin de règle de pare-feu ni de restriction supplémentaire côté edge pour obtenir cette isolation.
- **Correction découverte à l'usage, le même jour** : le premier essai (HTTP simple, `listen 80`, pas de certificat) semblait fonctionner (`curl` OK) mais provoquait une erreur fatale dans un vrai navigateur — Actual a besoin d'un contexte sécurisé (`SharedArrayBuffer`) que le navigateur n'accorde qu'en HTTPS ou sur `localhost`, jamais sur un autre nom d'hôte en HTTP clair. Corrigé en ajoutant un certificat **auto-signé** (généré par `cert-init`, étendu pour gérer plusieurs hostnames — voir `compose.yaml`) : le bloc `budget.home.test` passe en `listen 443 ssl`, le `listen 80` devient une redirection 301 vers le 443. Toujours aucun sous-domaine DuckDNS, aucun certificat Let's Encrypt pour ce service.
- **Test réel réussi (local puis Pi, 2026-08-13)** : `docker compose run --rm cert-init` génère le certificat auto-signé de `budget.home.test` ; `nginx -t` valide ; `curl https://.../login` (avec `-k`, certificat non signé par une CA de confiance — attendu) sert la page de connexion Actual Budget, avec les en-têtes `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` déjà présents (émis par Actual lui-même, rien à ajouter côté nginx) ; `curl http://.../` répond bien 301 vers `https://`. Reproduit à l'identique sur le Raspberry Pi (rsync de `edge/`, `cert-init`, `nginx -s reload`) — premier service de ce dépôt validé en conditions réelles dans la même session que son implémentation. Aucune régression sur les blocs HTTPS existants (bitwarden/paperless), vérifié en parallèle.
- **Pas encore fait** : résolution DNS locale réelle de `budget.home.test` — pour l'instant, à ajouter manuellement dans le `/etc/hosts` de chaque appareil du foyer (ou accès direct par IP LAN du Pi, qui fonctionne identiquement puisque c'est l'unique bloc avec ce `server_name`). Chaque appareil devra accepter l'avertissement de certificat auto-signé une fois.
- **Évolution future, non déclenchée** : si un accès Internet devient utile, ajouter un sous-domaine DuckDNS dédié (ex. `budget.<base>.duckdns.org`) et un certificat Let's Encrypt, en suivant le contrat standard déjà utilisé pour bitwarden/paperless — remplacerait le certificat auto-signé, ne changerait rien au mécanisme de proxy.

## Phase 9 (ultérieure) — Services suivants

- Tout nouveau service du dossier racine ayant besoin d'exposition publique suit le même contrat d'intégration (`architecture.md`) : un port HTTP publié, une entrée dans la table de routage d'`edge`, rien de plus.
- Pour un service qui n'a besoin que d'un accès local (comme `actual-budget`, Phase 8), le même schéma « `listen 80`, pas de sous-domaine DuckDNS » s'applique — à condition qu'un seul service local-only en HTTP existe à la fois (voir note dans `actual-budget.conf` sur le `server_name` implicite par défaut).
