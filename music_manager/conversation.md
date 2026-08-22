il y a t il moyen de créer une sorte de Spotify maison ?

Oui — et il y a plusieurs façons de faire un « Spotify maison », surtout si ton objectif est d'héberger ta propre bibliothèque musicale sur ton serveur familial.

Le projet qui me vient immédiatement à l'esprit est Navidrome.

🎵 Navidrome : probablement le meilleur choix
5

Navidrome est un serveur de musique open source qui fonctionne un peu comme Spotify :

tu mets tes fichiers MP3 / FLAC / AAC / OGG sur ton serveur ;
Navidrome indexe automatiquement ta bibliothèque ;
interface web ;
applications Android compatibles ;
recherche artistes / albums / morceaux ;
playlists ;
favoris ;
historique d'écoute ;
plusieurs utilisateurs ;
streaming depuis l'extérieur de la maison ;
transcodage si nécessaire ;
support des métadonnées et pochettes ;
compatible avec l'écosystème Subsonic/OpenSubsonic, donc énormément d'applications clientes.

Tu pourrais donc avoir par exemple :

                         INTERNET
                             │
                    ┌────────▼────────┐
                    │     Navidrome   │
                    │                 │
                    │  Bibliothèque   │
                    │   musicale      │
                    └────────┬────────┘
                             │
             ┌───────────────┼────────────────┐
             │               │                │
          Android          PC/Web          TV/Hi-Fi
             │               │                │
          musique         navigateur       client

Et surtout, ça colle très bien avec ton idée de serveur familial.

Mais il y a d'autres options
Solution	Esprit	Je la choisirais si…
Navidrome	🎵 Spotify minimaliste	tu veux principalement de la musique
Jellyfin	📺 Netflix + Spotify	tu veux aussi films, séries, musique
LMS / Lyrion Music Server	🎧 Hi-Fi multiroom	tu veux une vraie installation audio multiroom
Funkwhale	🌐 réseau musical	tu veux quelque chose de plus proche d'une plateforme musicale communautaire
Koel	🎵 Spotify web	tu veux surtout une belle interface web

Pour ton serveur familial, je partirais probablement sur Navidrome.

Et tu peux aller beaucoup plus loin

Tu peux avoir quelque chose de vraiment sympa :

Serveur

/ music
  / Artiste
    / Album
      01 - morceau.flac
      02 - morceau.flac

Navidrome
→ indexation automatique
→ pochettes
→ genres
→ artistes
→ playlists

Téléphones familiaux
→ application Android
→ chacun son compte
→ chacun ses playlists/favoris

À la maison
→ Chromecast / enceinte réseau / ampli
→ lecture depuis le serveur

À l'extérieur
→ VPN ou reverse proxy
→ accès à toute ta bibliothèque

Et contrairement à Spotify, tu possèdes réellement les fichiers et tu peux conserver du FLAC sans compression.

Il y a même une possibilité que je trouve particulièrement intéressante dans ton cas : faire un véritable « Spotify familial » avec Navidrome + téléchargement automatique de musique + gestion des métadonnées + accès Android + authentification commune avec tes autres services.

Ça pourrait devenir un très joli élément de ton serveur familial, à côté de Vaultwarden, Paperless, Actual Budget, Vikunja et Minecraft.

j'ai aussi besoin d'une interface mobile. c'est d'ailleurs le plus important

Oui, et dans ce cas je choisirais le serveur en fonction de l'expérience Android, plutôt que l'inverse.

🥇 Navidrome + une vraie app Android

Navidrome n'a pas forcément besoin d'avoir une excellente interface mobile lui-même : il expose une API compatible Subsonic/OpenSubsonic, et tu utilises une application Android dédiée.

C'est même assez puissant : tu peux avoir plusieurs clients selon tes besoins.

4
📱 Les applications que je regarderais

Symfonium serait probablement mon premier choix si tu veux quelque chose de vraiment agréable sur Android.

Il permet notamment :

navigation artistes / albums / genres ;
playlists ;
recherche ;
téléchargement hors ligne ;
lecture en arrière-plan ;
Android Auto ;
Chromecast ;
gestion de plusieurs serveurs ;
interface très adaptée au téléphone.

Et surtout, Navidrome + Symfonium donne beaucoup plus l'impression d'avoir un Spotify personnel qu'une simple interface web.

🏠 Pour ton serveur familial

Je verrais quelque chose comme :

                    ┌─────────────────┐
                    │    NAVIDROME    │
                    │                 │
                    │  FLAC / MP3     │
                    │  pochettes      │
                    │  métadonnées    │
                    └────────┬────────┘
                             │
                       OpenSubsonic
                             │
              ┌──────────────┼──────────────┐
              │              │              │
          📱 Toi          📱 Famille      💻 PC
        Symfonium        Symfonium       Web UI
              │
              ▼
        🎧 écoute locale
        📥 téléchargement
        🚗 Android Auto

Et tu peux conserver les fichiers originaux en FLAC sur ton serveur, tout en laissant Navidrome transcoder en MP3/AAC lorsque le téléphone ou la connexion le nécessite.

Un point important

Si l'interface mobile est le critère n°1, je ne choisirais pas Jellyfin uniquement parce qu'il fait aussi musique.

Jellyfin est excellent pour construire un Netflix familial, mais pour une bibliothèque musicale pure, Navidrome + client Android spécialisé est beaucoup plus proche de l'expérience Spotify.

Si tu veux, je peux te faire un comparatif Navidrome + 4/5 applications Android, en regardant surtout interface, téléchargement hors-ligne, Android Auto, Chromecast, playlists et coût.

navidrome va t il chercher les méta-données tout seul ?

Oui, mais avec une nuance importante : Navidrome sait récupérer certaines métadonnées automatiquement, mais je ne compterais pas sur lui pour faire tout le travail de catalogage à partir de fichiers mal tagués.

Ce que Navidrome fait

Il lit d'abord les tags intégrés aux fichiers audio :

artiste
album
titre
numéro de piste
année
genre
album artist
disque
etc.

Il peut ensuite récupérer/enrichir certaines informations et notamment les pochettes et métadonnées externes.

Pour une bibliothèque propre, je ferais plutôt
Fichiers audio
     │
     ▼
MusicBrainz Picard
     │
     │  identification + tags
     │  pochettes
     ▼
Bibliothèque musicale
     │
     ▼
Navidrome
     │
     ▼
📱 Symfonium

MusicBrainz Picard est particulièrement intéressant : tu lui donnes des albums ou des fichiers plus ou moins propres et il peut les identifier sur MusicBrainz, puis écrire les tags directement dans les fichiers.

Navidrome devient alors essentiellement le serveur/catalogue/lecteur, ce qui est beaucoup plus robuste.

Et pour les pochettes ?

C'est également quelque chose que je soignerais particulièrement. Une bonne bibliothèque peut avoir :

Artiste/
└── Album/
    ├── 01 - Track.flac
    ├── 02 - Track.flac
    ├── ...
    └── cover.jpg

Navidrome peut alors présenter une bibliothèque très propre dans l'application Android.

Donc oui : tu peux largement automatiser le processus, et si tu pars d'une grosse collection de MP3/FLAC existante, je peux te proposer une chaîne « je dépose mes fichiers → identification MusicBrainz → tags/pochettes → Navidrome → téléphone » quasiment sans intervention.
