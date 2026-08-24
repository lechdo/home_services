# video_fetcher

Récupère, pour un usage personnel, une vidéo diffusée en HLS (lecteur JWPlayer) par un site tiers — à partir de l'URL de sa page, ou, si l'automatisation échoue sur un site donné, à partir d'un ping.gif capturé manuellement dans les DevTools.

Voir `CLAUDE.md` pour le fonctionnement technique (pourquoi ces deux étapes sont nécessaires) et `_plan/plan.md` pour l'historique des blocages déjà rencontrés.

## Prérequis

- `ffmpeg` installé sur la machine.
- Google Chrome installé (`/usr/bin/google-chrome`) — utilisé par le mode automatique via Puppeteer.
- Node.js + dépendances installées une fois : `npm install` dans ce dossier.
- **Toujours utiliser un dossier de sortie sous `$HOME`** (ex. `~/videos`), jamais `/tmp` : si `ffmpeg` est un paquet snap, il est confiné à `$HOME` et échoue avec des erreurs trompeuses sinon.

## Mode automatique (recommandé) — `fetch.js`

Il suffit de l'URL de la page contenant la vidéo :

```bash
node fetch.js "<url_de_la_page>" ~/videos
```

Ce que le script fait :
1. Ouvre la page dans Chrome (headless), repère l'iframe du lecteur.
2. Déclenche la lecture (API JWPlayer + clic sur le vrai bouton play).
3. Capture le ping d'analytics JWPlayer contenant le manifest HLS (ignore le premier ping de "setup", qui ne le contient pas).
4. Extrait le titre depuis `.film-detail-title` sur la page.
5. Télécharge la vidéo via `ffmpeg` avec les bons en-têtes, sous `<dossier_sortie>/<titre>.mp4`.

Si le film met du temps à démarrer, le script réessaye de déclencher la lecture toutes les 2 secondes pendant 40 secondes avant d'abandonner.

### Si ça ne marche pas sur un nouveau site

Le sélecteur du bouton play (`.jw-icon-display[aria-label="Play"]`) et l'appel à l'API JWPlayer sont propres à la structure de JWPlayer sur les sites déjà testés. Si un autre site utilise une structure différente (ou un autre lecteur), il faut :

1. Ouvrir la page dans un vrai navigateur, DevTools → inspecter l'élément du bouton play réel.
2. Adapter la liste `selectors` dans `tryTriggerPlayback()` (`fetch.js`) avec le bon sélecteur.

## Mode manuel — `fetch_video.py`

À utiliser si le mode automatique échoue à déclencher la lecture, mais que tu as pu récupérer toi-même l'URL du `ping.gif` dans l'onglet **Network** des DevTools (après avoir lancé la vidéo à la main) :

```bash
python3 fetch_video.py --ping "<url_complète_du_ping.gif>" --page "<url_de_la_page>" --out ~/videos
```

- `--ping` (obligatoire) : URL complète du `ping.gif`, avec ses paramètres de query (contient `mu`, le manifest).
- `--page` (optionnel) : URL de la page, pour extraire automatiquement le titre via `.film-detail-title`.
- `--title` (optionnel) : force le titre du fichier de sortie (prioritaire sur `--page`).
- `--out` (optionnel) : dossier de sortie, `.` par défaut — **toujours un chemin sous `$HOME`**.
- `--referer` (optionnel) : force le domaine à utiliser pour `Referer`/`Origin` (par défaut déduit automatiquement du domaine du manifest — voir `CLAUDE.md`, ne pas utiliser le `pu` du ping directement).

## Si le téléchargement échoue avec un 403

C'est presque toujours un `Referer`/`Origin` incorrect, pas un blocage IP (voir `_plan/plan.md`). Pour diagnostiquer :

1. DevTools → onglet Network, relancer la vidéo, trouver une requête de segment `.ts` réussie (200).
2. Clic droit → **Copy → Copy as cURL (bash)**.
3. Comparer les headers `origin`/`referer` de cette requête avec ceux que le script a utilisés (affichés dans sa sortie) — le domaine du CDN doit correspondre.
4. Si besoin, forcer le bon domaine avec `--referer` (`fetch_video.py`) ou l'ajuster directement dans `fetch.js`/`cdnRootDomain()`.
