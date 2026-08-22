# music_manager

« Spotify maison » : bibliothèque musicale streamée avec [Navidrome](https://www.navidrome.org/), alimentée par un petit site interne (`fetcher`) qui télécharge des pistes depuis YouTube (vidéo unique ou playlist) en MP3.

Voir `CLAUDE.md` pour l'architecture et `_plan/plan.md` pour le détail par phases.

## Démarrage

```bash
cp .env.example .env   # puis générer FETCHER_SECRET_KEY (openssl rand -hex 32)
docker compose up -d --build
docker compose exec fetcher python manage.py add <utilisateur>
```

Navidrome (`192.168.1.109:8087` — second serveur physique, voir `CLAUDE.md`) crée son propre compte admin au premier accès à son interface web. `fetcher` (`192.168.1.109:8088`) n'a aucun compte par défaut — en créer au moins un avec `manage.py` avant de s'y connecter.

## Exposition publique

Un seul sous-domaine, `music-jvince.duckdns.org`, routé par `edge` avec deux chemins : `/navidrome` et `/fetcher` (voir `_plan/plan.md` phase 4 pour le bloc nginx à ajouter côté `edge`). Rien à faire côté `music_manager` pour le TLS/DNS.

## Bibliothèque musicale

Les MP3 téléchargés par `fetcher` sont déposés dans le volume `music` (partagé en lecture-écriture avec `fetcher`, en lecture seule avec `navidrome`), sous `YouTube/<titre>.mp3`. Une vidéo déjà téléchargée (fichier `.yt-dlp-archive.txt` à la racine du volume) n'est jamais retéléchargée, même via une playlist qui la recontient.
