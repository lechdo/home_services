# Service video_fetcher — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service est un **outil CLI personnel**, pas un service réseau : il n'expose aucun port, ne tourne pas en permanence, et n'est jamais routé par `edge`. Il sert à récupérer, pour un usage personnel, une vidéo diffusée en HLS (JWPlayer) par un site tiers, à partir de l'URL de sa page.

## Rôle du service

Beaucoup de sites de streaming embarquent le lecteur (JWPlayer + `hls.js`) dans une iframe cross-origin hébergée sur le domaine du CDN lui-même, et chargent le flux via un manifest `.m3u8` obtenu dynamiquement (jamais présent tel quel dans le HTML statique). Ce service automatise :

1. Le chargement de la page dans Chrome piloté (Puppeteer), la détection de l'iframe du lecteur, et le déclenchement réel de la lecture (API JWPlayer + clic sur le bouton play réel).
2. La capture, dans le trafic réseau de l'onglet, du ping d'analytics JWPlayer (`ping.gif`) qui contient l'URL du manifest HLS (paramètre `mu`) — en ignorant le ping de setup précédent (`e=es`), qui ne le contient pas.
3. L'extraction du titre depuis `.film-detail-title` sur la page, pour nommer le fichier de sortie.
4. Le téléchargement via `ffmpeg`, avec les en-têtes HTTP corrects.

## Point technique clé : le bon `Referer`/`Origin`

Le `pu` (page URL) présent dans le ping d'analytics est celui de la page **conteneur** (ex. le site vitrine) — **pas** celui à utiliser pour télécharger le manifest/les segments. Le lecteur tourne dans une iframe cross-origin sur le domaine du CDN lui-même (confirmé par le header `sec-fetch-site: same-site` observé via "Copy as cURL" sur une requête de segment réussie), donc les règles anti-hotlink Cloudflare attendent un `Referer`/`Origin` sur le domaine racine du CDN (déduit des 2 derniers labels du hostname du manifest), pas sur celui de `pu`. Sans ce header correct, le CDN renvoie un 403 (page de blocage Cloudflare), qui peut à tort ressembler à un blocage IP ou à une détection de bot — ce n'en est pas un.

## Caractéristiques spécifiques

- **Deux modes d'usage**, voir `README.md` : entièrement automatique (`fetch.js`, juste l'URL de la page) ou manuel (`fetch_video.py`, si le ping.gif doit être fourni à la main — cas où l'automatisation du clic play échoue sur un site donné).
- **Dépendances non partagées** : `puppeteer-core` (Node, piloté sur le Chrome déjà installé sur la machine — pas de téléchargement de Chromium supplémentaire) et `ffmpeg` (déjà présent sur la machine). Aucune dépendance Python externe (stdlib uniquement).
- **Piège connu si `ffmpeg` est un paquet snap** : confinement AppArmor, lecture/écriture limitées à `$HOME` et ses sous-dossiers. Toujours utiliser un dossier de sortie sous `$HOME`, jamais `/tmp`, sous peine de "Permission denied"/"No such file or directory" trompeurs alors que le fichier/dossier existe bien.
- **Pas de secrets, pas de configuration structurelle, pas de données utilisateur persistées** : chaque exécution est ponctuelle (un fichier vidéo en sortie) — hors du périmètre de `provisioning/` et de `protocole-donnees.md`.
- **Usage strictement personnel** : cet outil ne doit pas être transformé en service exposé publiquement ni en outil de distribution/partage à des tiers.
- **Fragile par nature** : les sélecteurs CSS et l'API du lecteur (`jwplayer()`, classes `jw-*`) sont propres à JWPlayer et peuvent casser si un site change de lecteur ou de structure — pas une garantie de fonctionnement universel sur tout site vidéo.

## À lire avant de travailler sur ce service

- `_plan/plan.md` — historique des blocages rencontrés (CORS, Cloudflare, confinement snap) et pourquoi les solutions retenues ont été choisies plutôt que les alternatives essayées.
- `README.md` — usage pratique des deux scripts.
