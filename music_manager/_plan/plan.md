# Plan de réalisation — service music_manager

Contexte : voir `conversation.md` (échange d'origine) — objectif « Spotify maison » avec Navidrome comme serveur et Symfonium comme client Android, complété par un besoin exprimé ensuite : un petit outil pour alimenter la bibliothèque directement depuis des URLs YouTube (vidéo unique ou playlist), sans repasser par un PC.

## Phase 0 — Choix de la stack et des ports

- **navidrome** : image officielle `deluan/navidrome`, mono-conteneur, stockage SQLite intégré (pas de base séparée — même logique que `vikunja`/`actual-budget` pour un usage familial). Lit les tags audio existants (artiste/album/titre/pochette) ; pas de dépendance à MusicBrainz Picard pour ce périmètre (traité comme une amélioration future si la bibliothèque grossit avec des fichiers mal tagués — hors scope de cette demande).
- **fetcher** : image maison, `python:3.12-alpine` (même base que `minecraft/panel`), Flask + `yt-dlp` + `ffmpeg` (paquet `apk add ffmpeg`, nécessaire à `yt-dlp` pour l'extraction/conversion MP3).
- **Hébergement : second serveur physique (`192.168.1.109`), pas le Raspberry Pi** — même raisonnement que `paperless`/`actual-budget`/`minecraft` (`edge/_plan/plan.md` phases 7, 10, 12) : le Pi 3 n'a que ~600-700 Mo de RAM réellement disponibles pour Docker, déjà occupés par `edge`/`bitwarden`/`vikunja`, et ce service ajoute un serveur de streaming (transcodage à la volée) plus un outil qui lance `ffmpeg` à la demande — pas un profil de charge adapté à cette machine.
- **Ports** : en suivant la numérotation déjà utilisée dans ce dépôt (8081 bitwarden, 8082 paperless, 8083 actual-budget, 8084 vikunja, 8085 wol, 8086 minecraft-panel), bindés sur l'IP LAN du second serveur (pas `127.0.0.1` : `edge` tourne sur une machine distincte, même pattern que `paperless`/`actual-budget`/`minecraft`) :
  - `navidrome` → `192.168.1.109:8087:4533` (4533 = port interne par défaut de l'image).
  - `fetcher` → `192.168.1.109:8088:5000`.
- **Bibliothèque musicale** : un volume nommé `music`, monté en lecture-écriture dans les deux conteneurs — `fetcher` y écrit les MP3 téléchargés, `navidrome` les lit (et les réindexe). Partagé entre les deux *composants d'un même service*, pas entre deux services (voir `CLAUDE.md`) — pas une violation du principe d'autonomie racine.

## Phase 1 — `compose.yaml` (le service, structure commune)

Un seul fichier `music_manager/compose.yaml`, deux services :

```yaml
services:
  navidrome:
    image: deluan/navidrome:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:8087:4533"
    environment:
      ND_BASEURL: "/navidrome"          # voir Phase 2 — indispensable sous ce sous-chemin
      ND_SCANSCHEDULE: "@every 1m"      # réindexation périodique (voir Phase 2)
      ND_LOGLEVEL: "info"
    volumes:
      - navidrome_data:/data            # base Navidrome (SQLite), séparée de la musique
      - music:/music:ro                 # lecture seule côté navidrome, écrit uniquement par fetcher

  fetcher:
    build: ./fetcher
    restart: unless-stopped
    ports:
      - "127.0.0.1:8088:5000"
    environment:
      SCRIPT_NAME: "/fetcher"           # voir Phase 3 — génération d'URL correcte sous ce sous-chemin
    volumes:
      - music:/music                    # lecture-écriture, seul composant qui y écrit

volumes:
  navidrome_data:
  music:
```

Pas de `.env` nécessaire dans un premier temps (aucun secret : le mot de passe du compte fetcher est créé dans un fichier de comptes local, pas une variable d'environnement — voir Phase 3). À réévaluer si un secret apparaît.

## Phase 2 — Navidrome sous `/navidrome`

- **`ND_BASEURL=/navidrome`** : variable dédiée de Navidrome pour tourner derrière un reverse proxy qui le sert sous un sous-chemin plutôt qu'à la racine d'un sous-domaine — sans elle, les liens internes/assets généreraient des URLs absolues à la racine (`/...`) qui ne correspondent pas au chemin réellement exposé par `edge`, cassant l'interface. Contrairement à `fetcher` (Phase 3), Navidrome gère cette configuration nativement : `edge` n'a **pas** besoin de retirer le préfixe `/navidrome` avant de transmettre la requête (voir Phase 4).
- **Comptage/indexation — testé réellement, meilleur que prévu** : cette version de Navidrome embarque un watcher de système de fichiers (log `Watcher: Triggering scan for changed folders`) qui détecte un fichier déposé par `fetcher` en quelques secondes, sans attendre `ND_SCANSCHEDULE` — vérifié en déposant un MP3 réel dans `/music/YouTube` et en observant le scan sélectif déclenché immédiatement (`tracksImported=1`). `ND_SCANSCHEDULE: "@every 1m"` reste positionné comme filet de sécurité (au cas où le watcher manquerait un événement), pas comme mécanisme principal — pas besoin d'appel API explicite depuis `fetcher` à la fin d'un téléchargement.
- **Comptes utilisateurs** : créés une fois à la main via l'interface web (comme `vikunja`) — un compte par personne de la famille, inscription libre désactivée par défaut sur Navidrome (pas d'action supplémentaire nécessaire).
- **Organisation du dossier `/music`** : `fetcher` dépose les MP3 dans un sous-dossier dédié, ex. `/music/YouTube/<titre>.mp3` (voir Phase 3) — Navidrome sait indexer des fichiers sans structure Artiste/Album stricte (il retombe sur les tags ID3 embarqués, voir Phase 3), donc pas besoin de ranger par artiste/album à ce stade.
- **Transcodage** : laissé à la valeur par défaut de Navidrome (transcodage à la volée si le client le demande, ex. réseau mobile limité) — pas de profil de transcodage particulier à créer pour ce périmètre.

## Phase 3 — fetcher (spécification fonctionnelle)

### Interface

Une seule page (après authentification, voir plus bas) : un champ texte multi-lignes où coller une ou plusieurs URLs YouTube (une par ligne) — **chaque ligne peut être une vidéo unique ou une playlist**, `yt-dlp` détecte et développe automatiquement une playlist en la liste de ses vidéos, pas de logique de détection à écrire à la main côté fetcher. Un bouton de soumission lance les téléchargements en tâche de fond ; la page affiche l'état de chaque URL soumise (en attente / en cours / terminé / échec), avec rafraîchissement périodique côté client (`fetch` JS toutes les quelques secondes vers un endpoint `/status`) — même schéma que le tableau de bord `minecraft/panel` plutôt qu'un rechargement de page complet.

### Téléchargement (`yt-dlp`)

- Options clés : `--extract-audio --audio-format mp3 --audio-quality 0` (meilleure qualité MP3 disponible), `--embed-metadata` (écrit titre/artiste/album dans les tags ID3 à partir des métadonnées YouTube disponibles — mieux que rien, mais moins fiable qu'un vrai tag MusicBrainz ; acceptable pour ce périmètre), `--restrict-filenames` ou équivalent pour éviter des caractères problématiques dans le nom de fichier final.
- Nom de fichier : gabarit `%(title)s.%(ext)s` de `yt-dlp`, sortie directement sous `/music/YouTube/`.
- **Playlist** : une URL de playlist produit naturellement un fichier par vidéo de la playlist, avec le même gabarit de nommage — pas de traitement spécial nécessaire, `yt-dlp` boucle lui-même sur les entrées.
- **File de tâches** : un exécuteur en tâche de fond simple (ex. `ThreadPoolExecutor` avec une taille de pool réduite, état en mémoire process) suffit pour un usage familial — pas de Celery/Redis, ce serait une complexité disproportionnée pour ce volume d'usage (cohérent avec la règle racine de ne pas ajouter d'abstraction avant besoin réel). État des tâches non persisté entre redémarrages du conteneur — acceptable, un redémarrage pendant un téléchargement en cours est un cas rare et sans conséquence grave (juste à relancer l'URL).
- **Échecs** : une vidéo indisponible/privée/supprimée dans une playlist ne doit pas faire échouer tout le lot — `yt-dlp` continue les entrées suivantes par défaut (`--ignore-errors` à activer explicitement pour être sûr de ce comportement), le statut affiché à l'utilisateur distingue les entrées réussies des entrées en échec plutôt qu'un seul statut global pour toute une playlist.

### Détection des doublons (déjà téléchargé)

Besoin exprimé : ne pas retélécharger une vidéo déjà présente dans la bibliothèque, que ce soit parce que la même URL est resoumise, ou parce qu'une playlist contient une vidéo déjà récupérée individuellement auparavant. `yt-dlp` a une fonctionnalité dédiée à exactement ce cas plutôt qu'une logique à écrire à la main : `--download-archive /music/.yt-dlp-archive.txt`. Ce fichier (texte, une ligne par `extracteur id` déjà téléchargé) est :

- **persisté dans le volume `music`** (pas dans le conteneur `fetcher` lui-même) pour survivre à une recréation du conteneur — sans ça, l'historique de dédoublonnage serait perdu à chaque mise à jour de l'image.
- **vérifié automatiquement par `yt-dlp` avant chaque téléchargement**, y compris pour chaque entrée d'une playlist : une vidéo déjà présente dans l'archive est simplement ignorée (marquée « déjà téléchargée » dans le statut renvoyé à l'utilisateur), sans réseau ni conversion inutile.
- indexé par identifiant de vidéo (pas par titre ni par nom de fichier) — robuste même si le titre YouTube change légèrement entre deux visites de la même vidéo.

Ce mécanisme ne détecte pas les doublons *avant* l'existence de ce fichier (une piste déjà présente dans `/music` mais ajoutée manuellement, hors `fetcher`, avant la mise en service de ce mécanisme) — hors scope, pas de réconciliation rétroactive prévue.

### Principe : un seul exemplaire du fichier audio, du téléchargement à l'indexation

Besoin exprimé : pas de copies successives de la musique entre le téléchargement, l'étiquetage des métadonnées et Navidrome — un fichier ne doit exister qu'une seule fois sur disque, pour ne pas multiplier le poids de la bibliothèque. Concrètement, dans ce plan :

- `yt-dlp` écrit **directement** dans le chemin final `/music/YouTube/<titre>.mp3` — pas de dossier de « staging » intermédiaire distinct de la bibliothèque.
- Les tags ID3 (`--embed-metadata`) sont écrits **en place, dans ce même fichier** — aucune étape de copie vers un autre outil/dossier pour l'étiquetage.
- Navidrome ne fait qu'**indexer/lire** ce même fichier (volume `music` monté en lecture seule côté navidrome, voir Phase 1) — il ne l'ingère jamais dans sa propre base ni ne le duplique ailleurs.

Résultat : un seul exemplaire, un seul poids sur disque par piste, dès le premier téléchargement.

**Conséquence pour une amélioration future (Phase 6/`conversation.md`)** : si une identification plus poussée à la MusicBrainz (type Picard, par empreinte audio) est ajoutée un jour pour améliorer des métadonnées imprécises, elle devra impérativement **réécrire les tags dans ce même fichier en place** (ou au plus le renommer sur place, jamais le copier) — jamais un flux « copier vers un dossier de bibliothèque distinct, puis supprimer l'original », qui recréerait temporairement (ou durablement, en cas d'oubli) deux exemplaires du même fichier, contraire à cette contrainte.

### Authentification

Même schéma que `minecraft/panel` (voir son `CLAUDE.md`) : comptes réels (pas de Basic Auth côté `edge`), mots de passe hashés `bcrypt`, session cookie Flask, décorateur `login_required`, pas d'auto-inscription — comptes créés à la main (fichier local versionné hors secret, ou variables d'environnement au démarrage, à trancher à l'implémentation en suivant le même choix que `minecraft/panel`).

### Point technique à ne pas manquer : sous-chemin `/fetcher`

Contrairement à Navidrome (Phase 2), Flask n'a **pas** de notion native de « préfixe de chemin public » — sans configuration explicite, `url_for()` génère des URLs absolues à la racine (`/login`, `/status`...) qui ne correspondent pas au chemin réel `/fetcher/...` vu par le navigateur derrière `edge`, cassant les redirections et les appels JS. Deux ajustements nécessaires, à faire ensemble :

1. Côté `fetcher` : envelopper l'application avec `werkzeug.middleware.dispatcher` ou fixer `SCRIPT_NAME=/fetcher` (variable d'environnement lue par Werkzeug) combiné à un `ProxyFix` (`werkzeug.middleware.proxy_fix.ProxyFix`, avec `x_prefix=1`) pour que Flask reconstruise correctement `url_for()` à partir de l'en-tête envoyé par `edge`.
2. Côté `edge` (Phase 4) : transmettre l'en-tête `X-Forwarded-Prefix: /fetcher` dans le bloc `location /fetcher/`, et proxy-passer **sans** retirer le préfixe (`proxy_pass http://127.0.0.1:8088;` sans slash final trompeur — à tester réellement, ce point est une source classique d'erreurs subtiles de double-préfixe ou de préfixe manquant).

À vérifier réellement dans un navigateur avant de considérer cette phase terminée (pas seulement `curl`, qui ne révèle pas les liens internes cassés dans le HTML rendu) — même discipline que les autres services de ce dépôt (« testé, pas supposé »).

## Phase 4 — Intégration `edge`

Un seul sous-domaine, `music-jvince.duckdns.org`, à ajouter à `DUCKDNS_SUBDOMAINS` dans `edge/.env` (aux côtés de `paperless-jvince,jvince,task-jvince`) — `sidecar-ddns` et `sidecar-acme`, déjà en place côté `edge`, prennent alors en charge la mise à jour DNS et l'émission/le renouvellement automatique du certificat Let's Encrypt sans aucune action supplémentaire, exactement comme pour les sous-domaines déjà enregistrés.

Un seul fichier `edge/nginx/conf.d/music.conf` (à créer **côté edge uniquement**, jamais dans `music_manager` — contrat d'intégration standard) avec **un seul `server {}`** et deux `location {}` :

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name music-jvince.duckdns.org;

    ssl_certificate     /etc/nginx/certs/music-jvince/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/music-jvince/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location /navidrome/ {
        proxy_pass http://127.0.0.1:8087;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /fetcher/ {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /fetcher;   # voir Phase 3
    }
}
```

À tester progressivement comme d'habitude dans ce dépôt (certificat Let's Encrypt **staging** d'abord, vérifié, puis production — préserve le rate limit) avant de considérer cette phase terminée. Mettre à jour la table de routage de `edge/_plan/architecture.md` une fois fait (une seule ligne, les deux composants y étant mentionnés).

## Phase 5 — Client mobile (Symfonium)

Suit `conversation.md` : configurer Symfonium (et tout autre client Subsonic/OpenSubsonic) avec l'URL complète **incluant le sous-chemin** : `https://music-jvince.duckdns.org/navidrome` (pas juste le nom de domaine — point à vérifier explicitement à la configuration du client, certaines apps Subsonic supposent une racine de domaine et gèrent moins bien un sous-chemin que Navidrome lui-même ne le fait côté serveur).

## Phase 6 (future, décision ouverte) — Sauvegarde et `protocole-donnees.md`

Pas de `provisioning/` nécessaire (voir `CLAUDE.md`). Reste une question ouverte à trancher avant un usage réel prolongé, à ajouter dans `protocole-donnees.md` une fois décidée :

- La bibliothèque `/music` (volume `music`) contient des fichiers en théorie ré-téléchargeables depuis YouTube via `fetcher` lui-même — dans cet esprit, proche de `paperless` (source vivant sur Google Drive, décision explicite de ne pas dupliquer de sauvegarde).
- Mais une vidéo YouTube peut être supprimée/rendue privée entre le téléchargement initial et un besoin de restauration — contrairement à Google Drive (source stable), la source n'est pas garantie de rester disponible indéfiniment. Si la bibliothèque grossit et que sa perte deviendrait réellement gênante, écrire un `_plan/plan-sauvegarde.md` (calqué sur `actual-budget`/`vikunja` : à définir, sans réutiliser leur dépôt/remote — principe d'autonomie racine) plutôt que de compter sur un re-téléchargement systématique.
- Non traité plus avant dans cette demande initiale — décision explicite à prendre plus tard, comme cela a été fait pour d'autres services de ce dépôt.

## Implémenté et testé en local (2026-08-22)

Phases 0 à 3 codées (`compose.yaml`, `fetcher/`) et validées réellement (build + exécution réelle des deux conteneurs, pas seulement une relecture du code) :

- `docker compose build fetcher` : image construite sans erreur (Flask, bcrypt, waitress, yt-dlp, ffmpeg via `apk add`).
- `ND_BASEURL=/navidrome` confirmé : `curl http://127.0.0.1:8087/navidrome/` → redirection `302` vers `/navidrome/app/`.
- Authentification `fetcher` testée de bout en bout : compte créé, `POST /login` → session, `/` accessible ensuite (`GET /` → `200`).
- **Téléchargement réel** d'une vidéo YouTube publique courte (« Me at the zoo ») via `POST /submit` → fichier `Me at the zoo.mp3` déposé dans `/music/YouTube/`, statut renvoyé par `/status` : `"1 piste téléchargée"`.
- **Tags ID3 et pochette confirmés** (`ffprobe` sur le fichier produit) : `title`, `artist`, `genre`, `date` bien présents, plus un flux vidéo correspondant à la pochette embarquée (`EmbedThumbnail`) — comportement normal d'un ID3 avec image jointe, pas une anomalie.
- **Dédoublonnage confirmé** : resoumission de la même URL → statut `"skipped"` / `"déjà présent dans la bibliothèque"`, aucun second fichier créé (`find /music/YouTube -name "*.mp3" | wc -l` reste à `1`).
- **Indexation Navidrome plus réactive que prévu** : voir la correction apportée à la Phase 2 ci-dessus (watcher de système de fichiers intégré, quelques secondes, pas la minute de `ND_SCANSCHEDULE`).
- Conteneurs et volumes de test détruits après validation (`docker compose down -v`) — aucun compte ni donnée de test ne subsiste.

**Pas encore fait** :
- Le point technique `ProxyFix`/`X-Forwarded-Prefix` (Phase 3) n'a été testé qu'en accès direct (`http://127.0.0.1:8088/`, sans préfixe) — **pas encore vérifié dans un vrai navigateur derrière `/fetcher`**, à faire une fois la Phase 4 déployée pour de vrai (voir ci-dessous), avant de considérer ce point acquis.
- Phase 5 (Symfonium) et Phase 6 (sauvegarde) : non commencées, inchangées par rapport au plan initial.

## Phase 4 — état d'avancement (2026-08-22)

Fait, côté `edge`, entièrement en local/hors-ligne (pas d'appel réseau réel à DuckDNS/Let's Encrypt) :
- `edge/nginx/conf.d/music.conf` créé (voir Phase 4 ci-dessus pour le contenu).
- **Syntaxe validée réellement** : conteneur `nginx:1.27-alpine` jetable, isolé du volume `certs` réel, avec des certificats auto-signés factices générés à la volée pour tous les sous-domaines déjà référencés dans `nginx/conf.d/*.conf` (y compris `music-jvince`) → `nginx -t` → « syntax is ok », « test is successful ».
- `edge/.env` : `music-jvince` ajouté à `DUCKDNS_SUBDOMAINS` (aux côtés de `paperless-jvince,jvince,task-jvince` — liste A+AAAA classique, pas `DUCKDNS_SUBDOMAINS_V6ONLY` : à la différence du client Minecraft Java, un navigateur et l'app Symfonium font du Happy Eyeballs IPv4/IPv6 standard).
- `edge/_plan/architecture.md` : entrée ajoutée à la table de routage + nouvelle section « Cas particulier : un service qui a besoin d'un routage par chemin (music_manager) », documentant l'exception à la règle habituelle d'edge.

**Fait ensuite, confirmé par l'utilisateur (2026-08-22)** — le sous-domaine `music-jvince` existait déjà côté DuckDNS ; DDNS et certificat réels traités depuis cet environnement (détail complet dans `edge/_plan/plan.md` phase 14) :
- `sidecar-ddns` relancé avec `music-jvince` ajouté à `DUCKDNS_SUBDOMAINS` → `OK` confirmé, sans régression sur les trois sous-domaines déjà en place.
- Certificat **staging** émis et vérifié, puis **production** (`--issue --server letsencrypt --force`), réinstallé, vérifié réellement via `openssl x509` : `issuer=C=US, O=Let's Encrypt, CN=YE2` (sans `STAGING`), valide jusqu'au 2026-11-20.

**Bloqueur découvert en testant, sans lien avec `music_manager`, pas corrigé (hors périmètre de cette demande)** : `reverse-proxy` est en crash-loop dans cet environnement depuis avant cette session — certificats `task-jvince` et `minecraft-jvince` absents du volume `certs` local, alors que ces sous-domaines sont déjà référencés dans `nginx/conf.d/`. Tant que ce point n'est pas traité séparément (cause non investiguée ici), `reverse-proxy` ne peut pas être rechargé pour de vrai dans cet environnement, donc **la vérification HTTPS bout en bout de `music-jvince.duckdns.org` (Navidrome + fetcher, y compris le point `X-Forwarded-Prefix` de la Phase 3) reste à faire** une fois ce bloqueur résolu — le DNS et le certificat de `music-jvince`, eux, sont réels et déjà en place.
