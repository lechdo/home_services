# Service minecraft — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge un serveur Minecraft (édition Java) accessible depuis l'extérieur du réseau local, plus un petit site de gestion permettant de le démarrer/arrêter et de changer de map.

## Rôle du service

- Faire tourner le process serveur Minecraft (Paper, via l'image `itzg/minecraft-server`) dans un conteneur dédié, démarré/arrêté à la demande — pas 24/7.
- Exposer un site web de gestion (`panel`) sur un port HTTP local, avec authentification, permettant à ~10 personnes autorisées de démarrer/arrêter le serveur et de choisir la map active.
- Ne jamais gérer soi-même le TLS, le DNS ou le sous-domaine public : c'est le rôle d'`edge` (voir `edge/CLAUDE.md`), y compris pour le port de jeu (voir plus bas, cas particulier).

## Deux surfaces réseau distinctes

Contrairement aux autres services routés par `edge` (uniquement HTTP/HTTPS), ce service en a deux, à ne pas confondre :

1. **Le panel de gestion (HTTP/HTTPS)** : suit le contrat d'intégration standard d'edge (`edge/_plan/architecture.md`) — port HTTP publié sur l'IP LAN du second serveur, edge termine le TLS et route en HTTPS, avec la page "serveur indisponible" habituelle si le panel lui-même ne répond pas.
2. **Le port de jeu Minecraft (TCP 25565, protocole binaire propriétaire, pas du HTTP)** : edge ne peut pas faire de reverse-proxy L7 dessus. Il est routé via un bloc `stream {}` nginx (proxy TCP brut, L4) — premier usage de ce module dans ce dépôt, voir `edge/_plan/plan.md`/`architecture.md` une fois cette phase faite côté edge. Quand le conteneur du serveur est arrêté, le client Minecraft voit une connexion refusée/timeout classique — aucune page HTML n'est possible sur ce port, c'est un comportement attendu (pas un bug à corriger).

Les deux passent par le même sous-domaine DuckDNS (`minecraft-jvince.duckdns.org`), simplement sur deux ports différents.

## Démarrage/arrêt : conteneur, pas la machine

Décision explicite (2026-08-17) : le panel pilote uniquement le **conteneur** du serveur Minecraft. Le second serveur physique (`192.168.1.109`) reste allumé en permanence — pas d'extinction/réveil de la machine elle-même, donc pas besoin du service `wol` ici. Si ce choix change un jour (économie d'énergie), cela redeviendrait un besoin de Wake-on-LAN — mais ce n'est pas ce qui est construit maintenant.

## Panel : accès à Docker sans exposer le socket brut

Le panel doit démarrer/arrêter/recréer le conteneur Minecraft (recréer = nécessaire pour changer de map, voir plus bas). Il ne monte jamais `/var/run/docker.sock` directement (ce service est exposé sur Internet derrière une simple authentification à ~10 comptes — un accès Docker complet serait une prise de contrôle totale de l'hôte en cas de compromission). À la place :

- `docker-socket-proxy` (image `tecnativa/docker-socket-proxy`) expose une API Docker restreinte (`CONTAINERS`, `IMAGES`, `POST` — le strict nécessaire pour créer/démarrer/arrêter/supprimer le conteneur du serveur et s'assurer que son image existe) sur le réseau Docker interne du projet — jamais publié sur l'hôte.
- Le panel parle à ce proxy via le SDK Docker (pas de shell-out vers `docker compose`), pour recréer le conteneur avec le bon bind mount de map.

## Changement de map

Chaque map est un dossier complet et autonome sous `maps/<nom>/` (données complètes d'un monde Paper : `world/`, `server.properties`, `plugins/`, etc. — pas juste le dossier `world`). Une seule map active à la fois. Le panel change de map en recréant le conteneur avec `maps/<nom-choisi>` monté sur `/data`. Le nom de la map vient toujours d'une liste (contenu réel de `maps/`), jamais d'une saisie libre — pas de traversée de chemin possible.

## Création de map, difficulté, plugins — depuis le panel

Le panel permet aussi de créer une nouvelle map (nom validé, devient le nom du dossier sous `maps/`), de régler la difficulté par map (persistée dans `panel-data/state.json`, appliquée via la variable d'environnement `DIFFICULTY` au conteneur, recréé si elle change) et d'activer/désactiver deux plugins Paper prédéfinis :

- **LuckPerms** (autorisations/permissions en jeu).
- **GravesX** (tombe récupérable à la mort — successeur activement maintenu du plugin "Graves" original de Ranull).
- **Thizzy'z Tree Feller** (couper un arbre entier d'un coup).
- **VeinMiner** (miner un filon de minerai entier d'un coup).
- **EssentialsX** (`/home`, `/tpa`, `/kit`, `/warp` — confort multijoueur de base).

Catalogue volontairement restreint à ces deux besoins exprimés — pas de marketplace générique. Les jars sont récupérés à la demande via l'API Modrinth (toujours la dernière version compatible Paper, jamais d'URL de jar figée à maintenir à la main), mis en cache une fois (`panel-data/plugin-cache/`) puis copiés dans `maps/<nom>/plugins/` de la map concernée à l'activation. Ces trois réglages (map, difficulté, plugins) ne sont modifiables que serveur arrêté.

## Minuteur de session et notifications in-game (RCON)

Chaque démarrage (ou renouvellement) déclenche une fenêtre de 2h, après laquelle le serveur s'arrête tout seul — besoin exprimé par l'utilisateur pour éviter un serveur qui tourne indéfiniment sans surveillance. Le panel expose un bouton « Renouveler (+2h) » qui remet le compte à zéro à tout moment pendant que le serveur tourne.

- Échéance (`session_expires_at`) persistée dans `panel-data/state.json` (survit à un redémarrage du panel), avec la liste des seuils déjà notifiés (`session_notified`) pour ne jamais renvoyer deux fois le même message.
- Un thread de fond (`session_watchdog`, même logique que le pattern déjà utilisé pour start/stop asynchrones) vérifie toutes les 10s le temps restant tant que le serveur est réellement `running` (pas `starting`), envoie un message à tous les joueurs (`say ...` via RCON) aux seuils 15/10/5 minutes avant l'arrêt, puis déclenche l'arrêt automatique à échéance.
- **RCON activé sur le conteneur du serveur** (`ENABLE_RCON`, `RCON_PASSWORD` généré une fois et persisté, `RCON_PORT`), joignable par le panel uniquement via le réseau Docker interne dédié (`minecraft_net`, nommé explicitement dans `compose.yaml`) — le conteneur du serveur y est rattaché à sa création (`network=` du SDK Docker) pour que le panel puisse le joindre par nom de conteneur. Ce port n'est **jamais** publié sur l'hôte/LAN, même logique de moindre privilège que `docker-socket-proxy`.
- **Client RCON écrit à la main** (protocole Source RCON, quelques paquets binaires, pas de dépendance externe) plutôt que d'utiliser une librairie tierce : testé réellement avec la librairie `mcrcon`, qui appelle `signal.signal(SIGALRM, ...)` dans son constructeur — ce qui lève `ValueError: signal only works in main thread` dès qu'on l'instancie hors du thread principal, silencieusement avalé par le `try/except` du panel (aucune notification n'était jamais réellement envoyée). Le protocole étant trivial, la solution retenue est un petit client maison, thread-safe par construction.
- Notifications *best-effort* : un échec RCON (serveur pas encore prêt, conteneur qui s'arrête entre-temps) ne doit jamais interrompre le minuteur ni faire planter le thread de fond.

## Affichage de la version (Minecraft / Paper)

Le panel affiche la version Minecraft et la version Paper de la map sélectionnée, lues directement dans `maps/<nom>/logs/latest.log` (Paper y écrit "Starting minecraft server version ..." et "This server is running Paper version ... (Implementing API version ...)" dès le tout début de chaque démarrage) — jamais via l'API Docker (pas besoin d'élargir les droits de `docker-socket-proxy`), et ça fonctionne même serveur arrêté, tant qu'il a démarré au moins une fois sur cette map.

## Dynamisme visuel et rafraîchissement automatique

Le tableau de bord s'actualise seul (JS, `fetch` toutes les 3s vers `/status`, pas de rechargement de page) plutôt que de rester figé sur l'état lu au chargement — nécessaire car un démarrage/arrêt réel prend de 10s à 90s. `/start` et `/stop` sont asynchrones (exécutés dans un thread à part, un seul à la fois) : la requête HTTP répond immédiatement, l'état affiché passe par `starting`/`stopping` (indicateur animé) avant `running`/`stopped` (point statique). `starting` reflète la disponibilité réelle du serveur (recherche de `]: Done (` dans `logs/latest.log`), pas le simple état "conteneur lancé" de Docker — Paper met encore 30 à 90s à charger le monde après ce point.

## Authentification du panel

Mini-application avec vrais comptes (pas de Basic Auth au niveau d'edge) : sessions, mots de passe hashés (bcrypt), ~10 comptes créés à la main (pas d'auto-inscription, même logique que vikunja). Décision du 2026-08-17, motivée par une meilleure UX qu'un popup Basic Auth et par la traçabilité (savoir qui a démarré/arrêté le serveur).

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases.
- `_plan/plan-sauvegarde.md` — sauvegarde des maps (données utilisateur critiques, non déclarables).
- `edge/CLAUDE.md` et `edge/_plan/architecture.md` — contrat d'intégration, y compris la partie `stream {}` spécifique à ce service.
