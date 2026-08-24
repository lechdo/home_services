# Plan — video_fetcher

Outil ponctuel, pas de phasage projet classique : ce document retrace surtout les blocages rencontrés et les décisions qui en résultent, pour ne pas les re-découvrir plus tard.

## Génèse

Besoin initial : reconstituer une vidéo à partir de fichiers `.ts` (segments MPEG Transport Stream) reçus séparément, sans manifest `.m3u8`. Vérification que les segments commencent par l'octet de sync `0x47` → flux non chiffré, simple concaténation + remux `ffmpeg` possible.

Étape suivante : trouver le manifest plutôt que manipuler des `.ts` bruts. Trouvé dans le paramètre `mu` (URL-encodé) d'un ping d'analytics JWPlayer (`ping.gif`), avec le referer de la page dans `pu`.

## Blocages rencontrés et résolutions

1. **CORS lors d'un `fetch()` cross-origin depuis la page conteneur** : le CDN ne renvoie pas de header `Access-Control-Allow-Origin` pour la page conteneur → abandon de l'approche "fetch en JS depuis le top document".
2. **403 Cloudflare avec le `Referer`/`Origin` de la page conteneur (`pu`)** : ressemblait à un blocage IP (page de blocage Cloudflare affichant l'IP), mais confirmé plus tard qu'il s'agissait uniquement du mauvais domaine de referer.
3. **Diagnostic via "Copy as cURL" d'une requête de segment réussie** (capturée dans les DevTools pendant une vraie lecture) : a révélé que `Origin`/`Referer` attendus sont ceux du **domaine du CDN lui-même** (`sec-fetch-site: same-site`), pas ceux de la page conteneur. Le lecteur tourne en réalité dans une iframe cross-origin hébergée sur le CDN. → Le script déduit désormais ce domaine à partir du hostname du manifest (2 derniers labels), au lieu d'utiliser `pu`.
4. **Automatisation du clic play (Puppeteer)** : les sélecteurs génériques devinés (`.jw-icon-playback`, etc.) ne correspondaient pas à la vraie structure JWPlayer. Le bon sélecteur (`.jw-icon-display[aria-label="Play"]`) a été obtenu en demandant à l'utilisateur d'inspecter le DOM réel. Ajout aussi d'un appel direct à l'API JWPlayer (`jwplayer().play(true)`) en complément, plus robuste qu'un clic UI pur.
5. **Le lecteur vit dans une iframe cross-origin** : les sélecteurs/API JWPlayer doivent cibler cette frame précise (`page.frames()`), pas le document principal — sinon aucun élément trouvé, aucun effet.
6. **`ffmpeg` snap, confinement AppArmor** : accès disque limité à `$HOME` et ses sous-dossiers. Un chemin de sortie sous `/tmp` produit des erreurs trompeuses ("Permission denied" / "No such file or directory") alors que le chemin existe et est normalement accessible — toujours utiliser un dossier sous `$HOME`.

## État actuel

Les deux scripts (`fetch.js` automatique, `fetch_video.py` manuel) fonctionnent de bout en bout, testés avec un téléchargement réel complet (film entier récupéré avec succès).

## Limites connues, non résolues

- Le premier ping capté (`e=es`) est toujours un ping de setup sans le manifest — normal, pas un bug. Le filtrage sur la présence du paramètre `mu` gère déjà ce cas.
- Le sélecteur du bouton play et l'appel à l'API JWPlayer sont spécifiques à JWPlayer. Un site utilisant un autre lecteur (Video.js, Plyr, lecteur maison...) nécessitera d'adapter `fetch.js` après inspection du DOM réel de ce site (voir méthode utilisée point 4 ci-dessus).
- Pas de gestion du cas où le manifest est un manifest "maître" avec plusieurs variantes de qualité — `fetch.js`/`fetch_video.py` passent l'URL du manifest tel que capté directement à `ffmpeg`, qui gère lui-même la sélection de variante.
