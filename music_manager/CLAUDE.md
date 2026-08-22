# Service music_manager — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge un « Spotify maison » : une bibliothèque musicale streamée (Navidrome) alimentée par un petit site interne qui télécharge des pistes depuis YouTube.

Voir `_plan/plan.md` avant toute implémentation — rien n'est encore codé, ce dossier ne contient pour l'instant que la conversation d'origine (`conversation.md`) et ce plan.

## Rôle du service

Deux composants, packagés dans **un seul** `compose.yaml` (comme `minecraft` avec son serveur de jeu + son panel) :

- **navidrome** : serveur de musique (image officielle `deluan/navidrome`), indexe une bibliothèque de fichiers audio, expose une interface web et l'API Subsonic/OpenSubsonic pour les clients mobiles (Symfonium).
- **fetcher** : petit site web maison (Flask), qui prend une ou plusieurs URLs YouTube (vidéo unique **ou playlist**), télécharge l'audio en MP3 via `yt-dlp`, nomme le fichier d'après le titre de la vidéo, et le dépose dans la bibliothèque musicale partagée avec navidrome.

Ces deux composants restent des **sous-parties d'un seul service** : ils partagent un volume de données (la bibliothèque musicale) sans que cela viole le principe d'autonomie racine, exactement comme `minecraft` (serveur de jeu + panel) partage déjà un réseau Docker interne dédié entre ses propres composants — la frontière d'autonomie est le service, pas le conteneur.

## Exposition : un seul sous-domaine, deux chemins

Décision explicite de l'utilisateur : un seul DNS, `music-jvince.duckdns.org`, avec deux chemins — `/navidrome` et `/fetcher`. C'est une **exception documentée** à la convention par ailleurs suivie dans ce dépôt (`edge/_plan/architecture.md` : « un sous-domaine par service backend, jamais de routage par chemin sous un même nom ») — exception cohérente ici puisque navidrome et fetcher ne sont pas deux services distincts mais deux composants d'un seul (`music_manager`), qui n'a donc besoin que d'une seule entrée dans la table de routage d'`edge`, avec deux `location {}` au lieu d'un `server_name` chacun. Voir `_plan/plan.md` phase 4 pour le détail technique (chaque composant a une contrainte différente pour fonctionner correctement sous un sous-chemin).

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : un unique `compose.yaml`, deux services (`navidrome`, `fetcher`), un volume nommé partagé pour la bibliothèque musicale.
- **Hébergé sur le second serveur physique (`192.168.1.109`), pas le Raspberry Pi** — même raisonnement que `paperless`/`actual-budget`/`minecraft` (`edge/_plan/plan.md`) : le Pi 3 (1 Go RAM) n'a pas la marge pour un serveur de streaming avec transcodage à la volée ni pour des conversions `ffmpeg` à la demande. Les ports publiés le sont donc sur l'IP LAN du second serveur, pas `127.0.0.1` (`edge` y accède à travers le réseau local, pas en loopback).
- **Aucune gestion TLS/DNS propre** : les deux composants publient chacun un port HTTP local sur l'hôte ; c'est `edge` qui termine le TLS et gère le renouvellement automatique (contrat d'intégration standard, `edge/_plan/architecture.md`) — rien à faire côté `music_manager` pour le certificat ou son renouvellement.
- **fetcher doit gérer aussi bien une URL de vidéo unique qu'une URL de playlist YouTube** (besoin exprimé explicitement) — `yt-dlp` gère nativement les deux à partir de la même URL, pas de logique de détection à écrire à la main.
- **Authentification du fetcher** : le fetcher déclenche des téléchargements et écrit sur disque — jamais laissé sans authentification alors qu'il est exposé publiquement. Suit le même schéma que le panel `minecraft` (comptes réels, mots de passe hashés bcrypt, session cookie, pas d'auto-inscription) plutôt qu'une Basic Auth côté edge, pour la même raison (meilleure UX, traçabilité de qui déclenche quoi).
- **Pas de `provisioning/`** envisagé pour l'instant : ni navidrome ni fetcher n'ont de taxonomie/config structurelle créée via API à déclarer séparément (les comptes navidrome sont créés une fois à la main, comme vikunja) — à réévaluer si ça change.
- **Statut sauvegarde/`protocole-donnees.md`** : question ouverte, voir `_plan/plan.md` phase 6 — la bibliothèque téléchargée depuis YouTube est en théorie ré-téléchargeable (comme `paperless`, dont la source vit sur Google Drive), mais une vidéo peut disparaître de YouTube entre-temps ; à trancher avant un usage réel prolongé.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — plan de réalisation par phases.
- `conversation.md` — échange d'origine ayant motivé le choix de Navidrome + Symfonium.
- `edge/CLAUDE.md` et `edge/_plan/architecture.md` — contrat d'intégration edge, y compris l'exception de routage par chemin documentée ci-dessus.
