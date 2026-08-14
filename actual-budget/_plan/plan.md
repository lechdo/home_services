# Plan de réalisation — service actual-budget

## Phase 0 — Choix de la stack

- Image officielle `actualbudget/actual-server` (variante `latest-alpine`, plus légère). Mono-conteneur : le serveur embarque son propre stockage SQLite sous `/data` (`server-files/account.sqlite` + `user-files/*.sqlite`) — pas de Postgres/MySQL séparé à orchestrer, contrairement à paperless.
- Port interne du conteneur : `5006` (défaut de l'image).

## Phase 1 — `compose.yaml` minimal (fait, 2026-08-12)

- Un seul service `actual-budget`, réseau `internal` dédié (pas de partage avec un autre service, conformément au principe d'autonomie racine).
- Port publié uniquement en local : `127.0.0.1:8083:5006` — pas d'exposition Internet pour l'instant (voir Phase 3).
- `ACTUAL_TRUSTED_PROXIES: "127.0.0.1"` positionné dès maintenant : sans effet tant que rien ne proxifie ce service en local, mais évite un oubli le jour où `edge` (Phase 3) ou un accès local via un reverse-proxy de test s'ajoute.

## Phase 2 — Volumes gérés pour un backup ultérieur (fait, 2026-08-12)

Demande explicite : préparer les volumes pour pouvoir les sauvegarder plus tard, sans implémenter le mécanisme de sauvegarde maintenant.

- Volume **nommé** `data` (pas anonyme) monté sur `/data` — un volume nommé est adressable par son nom dans un futur `sidecar-backup`, alors qu'un volume anonyme obligerait à retrouver son identifiant généré.
- Contenu documenté dans `plan-sauvegarde.md` : ce que contient `/data`, pourquoi tout est critique (rien n'est régénérable depuis une source externe, à la différence de paperless).
- Aucun autre volume/bind-mount créé pour l'instant : pas de sur-ingénierie avant d'avoir un besoin réel.

## Phase 3 (future, non déclenchée) — Implémentation effective de la sauvegarde

À faire quand demandé explicitement, en suivant `_plan/plan-sauvegarde.md` :
- Ajouter un `sidecar-backup` à `compose.yaml`, derrière un profil Compose dédié (même schéma que `bitwarden/compose.yaml`), avec sa propre config rclone/restic — jamais partagée avec un autre service.
- Tester une restauration complète avant de considérer le dispositif fiable (cf. protocole-donnees.md, principe racine).

## Phase 4a — Exposition via `edge`, mode local uniquement — **implémentée et validée sur le Pi (2026-08-13)**

Demande explicite (2026-08-13) de router ce service via `edge` avant tout besoin d'accès depuis l'extérieur du réseau local — donc sans sous-domaine DuckDNS ni certificat Let's Encrypt.

- Rien ajouté côté `actual-budget` : le port `127.0.0.1:8083` était déjà publié (Phase 1), `ACTUAL_TRUSTED_PROXIES` déjà positionné — conforme au contrat d'intégration, qui ne change pas selon que l'exposition est publique ou locale (`edge/_plan/architecture.md`).
- Côté `edge` uniquement : `edge/nginx/conf.d/actual-budget.conf` (`server_name budget.home.test`, `proxy_pass http://127.0.0.1:8083`). Pas d'entrée dans `DUCKDNS_SUBDOMAINS`, pas de certificat Let's Encrypt.
- **Correction découverte à l'usage, le même jour** : un premier essai en HTTP simple (`listen 80`, sans certificat) fonctionnait avec `curl` mais provoquait une erreur fatale dans un vrai navigateur (« Actual a besoin de l'accès à SharedArrayBuffer ») — un navigateur n'accorde le contexte sécurisé qu'exige Actual qu'en HTTPS ou sur `localhost`, jamais sur un autre nom d'hôte en HTTP clair, même purement local. Corrigé avec un certificat **auto-signé** (généré par `cert-init` côté edge) : `budget.home.test` passe en `listen 443 ssl`, le port 80 devient une simple redirection 301. Voir `edge/_plan/architecture.md`/`plan.md` (phase 8) pour le détail.
- Résultat : accessible en HTTPS (certificat auto-signé, avertissement à accepter une fois par appareil) sur le réseau local, non joignable depuis Internet (la box ne transfère que le port 443 vers Internet, mais celui d'edge — voir `deploiement-raspberry.md` — le port 80 n'est jamais transféré, la redirection reste donc locale elle aussi), sans qu'`actual-budget` ait quoi que ce soit à connaître d'edge, de token DuckDNS ou de certificat.
- **Testé de bout en bout sur le Raspberry Pi** (pas seulement en local) : `rsync` de `edge/` vers le Pi, `docker compose run --rm cert-init`, `nginx -s reload`, `curl https://.../login` via edge sert bien la page de connexion Actual Budget, en-têtes `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` présents (émis par Actual lui-même).
- **Pas encore fait** : résolution DNS locale réelle de `budget.home.test` (à ajouter manuellement en `/etc/hosts` sur les appareils du foyer, ou accès direct par IP LAN du Pi).

## Phase 4b (future, optionnelle) — Exposition Internet via `edge`

Non nécessaire tant que l'usage reste local (réseau domestique). Si un accès depuis l'extérieur devient utile un jour :
- Ajouter un sous-domaine DuckDNS dédié (ex. `budget.<base>.duckdns.org`) et un certificat dans la table de routage d'`edge`, en suivant le contrat d'intégration standard complet (`edge/_plan/architecture.md`) — remplacerait le bloc local de la Phase 4a (à décider si les deux accès doivent coexister).
- Ne rien ajouter côté `actual-budget` au-delà du port déjà publié : ni certificat, ni token DuckDNS, ni sidecar DDNS/ACME propre (interdit par le principe d'autonomie racine — voir `edge/CLAUDE.md`).

## Phase 5 (future, non déclenchée) — Migration vers le second serveur physique, données comprises

**Contexte (2026-08-14)** : libérer de la RAM sur le Raspberry Pi 3 (1 Go total) pour y ajouter `vikunja` — `actual-budget` (Node.js) est le service le plus gourmand des trois déjà en place (`edge`, `bitwarden`, `actual-budget`). Décalque de la migration déjà faite pour `paperless` (`_plan/plan.md` phase 9 de `paperless`, `edge/_plan/plan.md` phase 7) vers le même second serveur physique, IP LAN déjà connue et réservée : `192.168.1.109`.

**Différence fondamentale avec la migration paperless — à ne jamais perdre de vue** : paperless a délibérément redémarré avec une **instance neuve** sur le second serveur (choix explicite, `paperless/_plan/plan.md` phase 9), parce que sa donnée réelle vit sur Google Drive — repartir de zéro ne perd rien. **Ici, ce n'est pas possible** : `plan-sauvegarde.md` documente que rien dans le volume `data` d'`actual-budget` n'est régénérable (aucune source externe). Cette phase migre donc les **données réelles**, elle ne recrée pas une instance vierge.

**Disponibilité — décision explicite (2026-08-14)** : comme pour paperless, on accepte une disponibilité **intermittente** — le second serveur n'est pas allumé en permanence, une page d'indisponibilité dédiée côté `edge` (503, pas de 502 brut) s'affiche quand il est éteint, à rallumer manuellement pour consulter/modifier le budget. Alternative écartée : garder le second serveur allumé en permanence pour ce service, ce qui aurait annulé une partie du bénéfice de la délocalisation.

### Étapes côté `actual-budget`

1. **Pré-requis** : le second serveur a déjà le monorepo cloné (fait pour paperless) — un simple `git pull` y récupère `actual-budget/` à jour, pas de nouveau clone. `actual-budget/.env` n'existe pas dans ce dépôt (aucune variable secrète pour ce service à date) — rien à transférer de ce côté, à la différence de paperless (`rclone.conf`).
2. **Arrêter proprement le service sur le Pi 3 avant toute copie** : `docker compose stop actual-budget`. Contrairement à un service tolérant une petite perte, copier un fichier SQLite pendant qu'un processus y écrit encore risquerait une corruption — zéro tolérance ici (donnée non régénérable).
3. **Snapshot cohérent** : appliquer pour de vrai, pour la première fois, la méthode déjà documentée mais jamais exécutée dans `plan-sauvegarde.md` (§2.1) — `sqlite3 <fichier> ".backup ..."` sur `server-files/account.sqlite` et sur chaque `user-files/*.sqlite` du volume `data`, plutôt qu'une copie brute des fichiers (filet de sécurité simple, même conteneur déjà arrêté).
4. **Transfert vers le second serveur** : `rsync -avz` du snapshot (reprise sur interruption, contrairement à `scp`) vers un nouveau volume nommé `data` dans `actual-budget/` sur le second serveur — jamais un chemin ou volume déjà utilisé par `paperless` sur cette même machine (principe d'autonomie racine, même en cohabitant sur le même serveur physique).
5. **Vérification d'intégrité avant de considérer le transfert réussi** : `sqlite3 <fichier> "PRAGMA integrity_check;"` sur chaque fichier arrivé, plus comparaison de hash (`sha256sum`) entre le snapshot source et le fichier reçu — pas de bascule tant que ces deux contrôles ne sont pas passés.
6. **Démarrage sur le second serveur** : `docker compose up -d` en pointant sur ce volume migré (pas une instance neuve, à la différence de paperless) ; validation fonctionnelle explicite dans l'UI Actual — les budgets/comptes/transactions existants doivent apparaître, pas seulement un conteneur `healthy`.
7. **Ne rien supprimer côté Pi 3 immédiatement** : garder le volume Docker d'origine intact (conteneur arrêté, pas de `docker compose down -v`) comme filet de secours le temps de valider quelques jours d'usage réel côté second serveur — cohérent avec la démarche de validation progressive déjà suivie pour les autres services de ce dépôt. Supprimer seulement une fois ce délai passé sans incident.

### Changements de configuration nécessaires

- **Binding du port** (`compose.yaml`) : remplacer `127.0.0.1:8083:5006` par `<IP_LAN_second_serveur>:8083:5006` — jamais `0.0.0.0` (même raisonnement que paperless : la requête vient désormais du réseau local via `edge`, pas de l'hôte local).
- **`ACTUAL_TRUSTED_PROXIES` à changer, point spécifique à ce service** (pas rencontré lors de la migration paperless) : fixé à `127.0.0.1` parce qu'`edge` et `actual-budget` tournaient jusqu'ici sur la même machine. Une fois `actual-budget` sur le second serveur, les requêtes arrivent de l'IP LAN de la machine `edge` (`192.168.1.99`), plus de `127.0.0.1` — sans ce changement, Actual ne fait plus confiance aux en-têtes `X-Forwarded-*` d'edge (IP client mal journalisée, potentiels effets de bord sur la vérification d'origine).
- **Aucun changement sur le mécanisme HTTPS/`SharedArrayBuffer`** (Phase 4a/8) : `edge` continue de terminer le TLS sur le Pi 3 et de parler HTTP simple à l'upstream, que ce soit `127.0.0.1` ou une IP LAN distante — le contrat déjà validé ne dépend pas de la localisation physique du backend.

### Côté `edge` (à faire là-bas uniquement, jamais dans ce dossier)

Voir `edge/_plan/plan.md` (nouvelle phase, décalque de la phase 7/paperless, adaptée au mode local `budget.home.test` déjà en place — pas de sous-domaine DuckDNS ni de certificat Let's Encrypt à ajouter à cette occasion) : `proxy_pass` vers l'IP LAN du second serveur, timeouts courts, page d'indisponibilité dédiée au budget (message différent de celle de paperless).

### Point de vigilance reporté, pas traité par cette phase

Pare-feu du second serveur toujours explicitement différé (`paperless/_plan/plan.md` phase 9) : le port `8082` (paperless) y est déjà ouvert à tout le LAN plutôt que restreint à l'IP d'`edge`. Ajouter le port `8083` (actual-budget) dans le même état accumule une deuxième exception au même risque déjà accepté — pas une raison de bloquer cette migration, mais un argument de plus pour traiter ce pare-feu avant d'ajouter un troisième service sur cette machine.

### Exécutée et testée en conditions réelles (2026-08-14)

- **Étapes 1-7 réalisées à l'identique du plan** : `actual-budget` arrêté proprement sur le Pi (`docker compose stop`), snapshot cohérent via `sqlite3 .backup` (conteneur alpine jetable, pas d'installation native sur l'hôte — cohérent avec le principe racine), transfert `rsync` (Pi → second serveur), vérification d'intégrité (`PRAGMA integrity_check` : `ok` sur les deux bases) et de hash (SHA-256 identique à chaque étape du transfert). Volume nommé `actual-budget_data` créé sur le second serveur et peuplé (`.migrate`, `server-files/account.sqlite`, `user-files/*.sqlite` + `.blob`), propriété `1001:1001` restaurée à l'identique de l'original.
- **Changements de configuration appliqués** : `compose.yaml` mis à jour (binding `192.168.1.109:8083:5006`, `ACTUAL_TRUSTED_PROXIES: "192.168.1.99"` — l'IP LAN de la machine qui *appelle* actual-budget, c'est-à-dire edge sur le Pi, pas celle du second serveur lui-même), déployé par `rsync` (pas de `git pull`, pour ne pas dépendre d'un commit préalable).
- **Piège découvert à l'usage, non anticipé dans le plan initial** : la publication du port sur une IP spécifique (`192.168.1.109:8083`, pas `127.0.0.1`) rend le service injoignable en local via `127.0.0.1` depuis le second serveur lui-même — un `curl http://127.0.0.1:8083` échoue (connexion refusée), il faut cibler l'IP LAN explicitement (`curl http://192.168.1.109:8083`) même en local sur cette machine. Sans conséquence pour `edge` (qui cible déjà l'IP LAN), mais à savoir pour tout diagnostic futur sur place.
- **Erreur opérationnelle corrigée en cours de route** : un premier `rsync` du dossier `actual-budget/` complet vers le second serveur a copié par erreur un sous-dossier local non suivi par git (`scripts/rules/`, avec `node_modules/` et surtout un cache `.cache-pi/My-Finances-*/{cache.sqlite,db.sqlite}` — une copie déchiffrée du budget réel utilisée localement pour un script de catégorisation). Supprimé immédiatement du second serveur après détection ; leçon pour toute prochaine synchronisation de ce dossier : exclure explicitement `scripts/` et `conversation.md` (non destinés au déploiement), ne transférer que ce qui sert à faire tourner le service.
- **Testé réellement de bout en bout** : conteneur `actual-budget` démarré sur le second serveur (`Migrations: DONE`, aucune erreur), `curl http://192.168.1.109:8083/` → `HTTP 200` ; via `edge` (Pi), `curl -k https://budget.home.test/` → `HTTP 200` avec en-têtes `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` présents. RAM du Pi vérifiée après bascule : ~254 Mio libres (contre les ~217 Mio avant, `actual-budget` ne tournant plus dessus).
- **Volume d'origine conservé intact sur le Pi** (conteneur arrêté, pas de `docker compose down -v`), comme prévu par le plan — filet de secours à supprimer seulement après quelques jours d'usage réel validé côté second serveur.
- **Pas encore fait** : validation visuelle par l'utilisateur (aucun identifiant Actual disponible côté agent pour se connecter et vérifier que les budgets/transactions migrés s'affichent correctement) ; test réel du scénario second serveur éteint (page 503, cf. `edge/_plan/plan.md` phase 10) ; décision sur le commit de ces changements ; suppression du volume d'origine sur le Pi après délai de validation.
