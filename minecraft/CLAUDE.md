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

## Authentification du panel

Mini-application avec vrais comptes (pas de Basic Auth au niveau d'edge) : sessions, mots de passe hashés (bcrypt), ~10 comptes créés à la main (pas d'auto-inscription, même logique que vikunja). Décision du 2026-08-17, motivée par une meilleure UX qu'un popup Basic Auth et par la traçabilité (savoir qui a démarré/arrêté le serveur).

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases.
- `_plan/plan-sauvegarde.md` — sauvegarde des maps (données utilisateur critiques, non déclarables).
- `edge/CLAUDE.md` et `edge/_plan/architecture.md` — contrat d'intégration, y compris la partie `stream {}` spécifique à ce service.
