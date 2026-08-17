# Plan — service minecraft

Contexte et décisions d'architecture actées le 2026-08-17 (voir aussi `minecraft/CLAUDE.md`) :
- Pilotage du **conteneur** uniquement (machine hôte toujours allumée) — pas de Wake-on-LAN.
- Hébergement sur le second serveur (`192.168.1.109`), sous réserve de vérification RAM/CPU disponible (phase 0).
- Édition **Java uniquement** (TCP 25565).
- Authentification du panel via une mini-app avec vrais comptes (pas de Basic Auth edge).

RAM disponible confirmée par l'utilisateur (2026-08-17) : 64 Go sur le second serveur — large marge au-delà des 2-4 Go typiquement nécessaires à Paper, en plus de paperless/actual-budget déjà présents.

## Phase 0 — Vérifications préalables

- Vérifier la RAM/CPU réellement disponible sur `192.168.1.109` (`free -h`, `docker stats` des conteneurs déjà présents : paperless, actual-budget) avant d'y ajouter Minecraft. Un serveur Paper avec quelques joueurs consomme facilement 2-4 Go de RAM à lui seul — à comparer à la marge restante. Si la marge est insuffisante, revoir la décision d'hébergement (troisième machine dédiée) avant de poursuivre.
- Vérifier côté routeur/box que le pare-feu IPv6 autorise déjà (ou peut être étendu à) le port TCP 25565 entrant, en plus des 80/443 déjà ouverts (cf. `deploiement-raspberry.md`). Étape manuelle, hors dépôt.
- Décider de la version/modpack Minecraft visée (vanilla/Paper vierge, ou plugins spécifiques) — impacte la config de l'image mais pas l'architecture ci-dessous.

## Phase 1 — Serveur Minecraft (conteneur) — **implémentée (2026-08-17), pas encore testée avec la vraie image itzg/minecraft-server**

- Image recommandée : `itzg/minecraft-server` (TYPE=PAPER par défaut), le standard de facto pour ce cas d'usage — gère le téléchargement/mise à jour du jar serveur, l'acceptation de l'EULA, l'arrêt propre (SIGTERM → sauvegarde), et une configuration entière par variables d'environnement plutôt qu'en éditant `server.properties` à la main.
- Un dossier par map sous `minecraft/maps/<nom>/` (ex. `maps/survival/`, `maps/creative/`) — chacun est un dossier de données Paper complet et autonome, monté sur `/data` dans le conteneur. Une map de départ suffit pour démarrer (`maps/survival/`), les autres se créent en copiant simplement un nouveau dossier vide (le serveur le génère au premier démarrage).
- `compose.yaml` : port de jeu publié sur l'IP LAN du second serveur (`192.168.1.109:25565:25565/tcp`), jamais `127.0.0.1` (service sur un hôte distinct d'edge, même contrat que paperless/actual-budget).
- Pas de `provisioning/` : la config du serveur (variables d'env, `server.properties`) est déjà versionnée via `compose.yaml`/`.env`, pas créée dynamiquement via une API à déclarer séparément (cf. `protocole-donnees.md`).

## Phase 2 — Panel de gestion (site de contrôle) — **implémentée et testée en conditions réelles (2026-08-17), hors itzg/minecraft-server**

- **Testé réellement** : `docker build` de `panel/`, lancé face à un vrai `docker-socket-proxy` (réseau Docker dédié, socket réel de l'hôte) — cycle complet login → sélection de map → démarrage → vérification du bind mount réellement créé (`docker inspect`) → arrêt → changement de map à l'arrêt → redémarrage → nouveau bind mount confirmé. L'image `itzg/minecraft-server` a été remplacée par `alpine:3.20` (`tail -f /dev/null`) pour ce test, uniquement pour éviter de télécharger/démarrer un vrai serveur Java — la logique testée (création/suppression/inspection de conteneur, bind mount dynamique) est strictement celle utilisée en production, indépendante de l'image.
- **Bug réel trouvé et corrigé** : `docker.DockerClient(base_url=...)` se connecte immédiatement à la construction pour négocier la version de l'API — si le client était créé au chargement du module (comme écrit initialement), tout le panel plantait au démarrage tant que `docker-socket-proxy` n'était pas encore prêt (course normale au démarrage de `docker compose up`), y compris pour `/login` qui n'a rien à voir avec Docker. Corrigé par une initialisation paresseuse (`docker_client()`, une fonction plutôt qu'une variable globale construite à l'import), avec la version d'API fixée explicitement (`version="1.44"`) pour éviter la négociation à chaque appel.
- **Second bug réel trouvé et corrigé** : un gestionnaire d'erreur générique qui redirige vers `/` quand Docker est inaccessible bouclait indéfiniment, parce que la route `/` elle-même appelle Docker (`server_status()`) et levait la même erreur. Corrigé en rendant `server_status()` résiliente par elle-même (état `"unknown"` affiché proprement dans le tableau de bord) — le gestionnaire d'erreur générique ne sert plus qu'aux routes d'action (`/start`, `/stop`, `/select-map`), qui redirigent ensuite vers un tableau de bord qui, lui, ne plante jamais.
- **Pas encore fait** : test avec la vraie image `itzg/minecraft-server` (téléchargement de l'image, montée effective du monde, arrêt propre SIGTERM — l'image est conçue pour sauvegarder le monde proprement à l'arrêt, contrairement au conteneur de test) ; création des comptes réels (~10 personnes) ; déploiement sur le second serveur physique.

- Petite application (dans l'esprit minimaliste de `wol/app/app.py` : peu de dépendances, pas de framework lourd) exposant :
  - Statut actuel (map active, en cours d'exécution ou non).
  - Bouton démarrer / arrêter.
  - Sélecteur de map (liste des dossiers présents sous `maps/`), désactivé si le serveur tourne (changer de map implique un redémarrage).
- Le panel ne parle jamais directement à `docker.sock`. Il passe par `docker-socket-proxy` (`tecnativa/docker-socket-proxy`), sur le réseau Docker interne du projet, avec les portées minimales nécessaires (containers + réseaux, lecture et écriture ciblée — pas d'accès images/volumes non utilisé ici).
- Démarrer/arrêter = start/stop du conteneur existant. Changer de map = recréer le conteneur avec un nouveau bind mount `/data` (le SDK Docker du panel gère cette recréation directement, sans passer par la CLI `docker compose`).
- Port HTTP local du panel : `8086` (prochain port libre après edge/bitwarden 8081, paperless 8082, actual-budget 8083, vikunja 8084, wol 8085 — convention du dépôt).

## Phase 3 — Authentification du panel — **implémentée et testée en conditions réelles (2026-08-17)**

- Sessions + mots de passe hashés (bcrypt), ~10 comptes créés à la main dans un fichier (pas de base de données dédiée nécessaire à cette échelle), pas d'auto-inscription — même logique que vikunja (registration désactivée après création manuelle des comptes). `panel/manage.py add|remove <username>` (exécuté via `docker compose exec panel ...`).
- **Testé réellement** (même session que Phase 2) : création d'un compte via `manage.py`, connexion, cookie de session signé (Flask, `SECRET_KEY`), accès protégé aux routes d'action, déconnexion.
- Cookie de session marqué `Secure` (n'est envoyé par le navigateur que sur une connexion HTTPS) — cohérent avec l'accès prévu via `https://minecraft-jvince.duckdns.org/` (edge termine le TLS ; le hop HTTP interne edge→panel ne change rien à ce que voit le navigateur). **Point de test à refaire une fois déployé derrière edge réel** : un test en HTTP direct (sans edge) ne peut pas valider ce comportement, seul un test via le vrai sous-domaine HTTPS le peut.
- Pas encore fait : créer les ~10 comptes réels ; journalisation de qui démarre/arrête le serveur (pas implémenté, pas demandé explicitement — pourrait s'ajouter facilement si besoin, ex. un log applicatif simple).

## Phase 4 — Intégration edge — **écrite (2026-08-17), config nginx validée par `nginx -t`, pas encore déployée sur la machine réelle**

Deux changements côté `edge`, documentés ici mais à réaliser/valider dans `edge/_plan/plan.md` et `architecture.md` (ce service n'a pas le droit de modifier son propre routage, cf. contrat d'intégration) :

- **Panel (HTTPS)** : nouveau `edge/nginx/conf.d/minecraft-panel.conf`, calqué sur `actual-budget.conf`/`paperless.conf` — `proxy_pass http://192.168.1.109:8086`, `proxy_connect_timeout` court, page d'indisponibilité dédiée (`error-pages/minecraft-panel-unavailable.html`) si le panel ou le second serveur ne répond pas. Sous-domaine DuckDNS : `minecraft-jvince.duckdns.org` (déjà fourni), à ajouter à `DUCKDNS_SUBDOMAINS` dans `edge/.env`.
- **Port de jeu (TCP brut, L4)** — premier usage du module `stream` de nginx dans ce dépôt :
  - edge ne monte actuellement aucun `nginx.conf` personnalisé (il utilise celui livré par l'image `nginx:1.27-alpine`, qui inclut seulement `conf.d/*.conf` dans le bloc `http {}`). Un bloc `stream {}` doit vivre au niveau racine de `nginx.conf`, pas dans `conf.d` — il faut donc fournir un `nginx.conf` complet (repris du défaut de l'image + ajout du bloc `stream { include /etc/nginx/stream.d/*.conf; }`), monté en plus de `conf.d/`.
  - Nouveau fichier `edge/nginx/stream.d/minecraft.conf` : `listen 25565; proxy_pass 192.168.1.109:25565;` (+ `proxy_connect_timeout` court, même raisonnement que pour le HTTP : le conteneur peut être arrêté).
  - Pas de page d'erreur possible sur ce port (protocole binaire, pas HTTP) — le client Minecraft affichera son échec de connexion natif.
  - Le sous-domaine `minecraft-jvince.duckdns.org` pointe vers l'IPv6 d'edge comme toujours (rien à changer côté `sidecar-ddns`, il gère déjà tous les sous-domaines de `DUCKDNS_SUBDOMAINS` en une fois) — le port 25565 est distinct du panel HTTPS mais sur le même hôte/la même IP.
- **Fait (2026-08-17)** : tous les fichiers ci-dessus écrits (`edge/nginx/nginx.conf`, `edge/nginx/stream.d/minecraft.conf`, `edge/nginx/conf.d/minecraft-panel.conf`, `edge/nginx/error-pages/minecraft-panel-unavailable.html`, `edge/compose.yaml` mis à jour, `DUCKDNS_SUBDOMAINS` mis à jour) — voir `edge/_plan/plan.md` phase 12 pour le détail. **Validé réellement** : `nginx -t` réussit avec la config complète d'edge (nouveau `nginx.conf` + tous les `conf.d/*.conf` existants + le nouveau `stream.d/minecraft.conf`), certificats de test générés à la volée pour la vérification — aucune régression détectée sur les blocs HTTPS existants (bitwarden/paperless/vikunja/actual-budget). `docker compose config` validé côté `edge` et côté `minecraft`.
- **Pas encore fait** : déploiement réel sur le Pi (ce test a été fait avec l'image `nginx:1.27-alpine` en local, pas sur la machine cible) ; émission du certificat Let's Encrypt ; ouverture du port 25565 au pare-feu de la box.

## Phase 5 — Sauvegarde des maps

Voir `_plan/plan-sauvegarde.md` — les mondes Minecraft sont des données utilisateur critiques non déclarables (cf. `protocole-donnees.md`), à sauvegarder indépendamment de tout autre service.

## Outils suggérés (récapitulatif)

| Besoin | Outil | Pourquoi |
|---|---|---|
| Serveur Minecraft | `itzg/minecraft-server` (image Docker) | Standard de facto, gère EULA/update/arrêt propre, config 100% par variables d'env |
| Isolation de l'accès Docker | `tecnativa/docker-socket-proxy` | Évite d'exposer `docker.sock` brut à une app accessible depuis Internet |
| Panel (start/stop/changement de map) | App maison minimaliste (style `wol/app/app.py`) + SDK Docker | Cohérent avec la philosophie DIY du dépôt, pas de dépendance lourde |
| Auth panel | bcrypt + sessions, comptes statiques | ~10 comptes fixes, pas besoin d'un IdP (Authelia jugé disproportionné pour cet usage) |
| Routage jeu (TCP 25565) | Module `stream` de nginx (déjà dans l'image `nginx:1.27-alpine`) | Garde `edge` comme point d'entrée unique même pour un protocole non-HTTP, sans nouvel outil |
