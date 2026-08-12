# Protocole — installation du Raspberry Pi et intégration edge + bitwarden

Document transverse (comme `protocole-donnees.md`) : ce n'est pas un service, mais la procédure de mise en place de la **machine cible finale** décidée dans `bitwarden/README.md` — un Raspberry Pi dédié, qui hébergera à la fois `edge` (point d'entrée Internet unique) et `bitwarden` (vaultwarden). C'est un enchaînement d'actions physiques/manuelles : chaque commande sensible (flash de carte SD, `sudo` sur le Pi) doit être exécutée par toi, pas par Claude.

État au moment de l'écriture (2026-08-12) : `edge` et `bitwarden` sont validés **en local, sur ce PC**, avec des certificats Let's Encrypt **staging** (voir `edge/README.md`, `bitwarden/README.md`). Rien n'a encore tourné sur le Raspberry Pi. Une carte micro SD est branchée sur ce PC, détectée comme `/dev/sda` (14,9 Go, déjà partitionnée — résidu d'un usage antérieur, sera entièrement effacée à l'étape 1).

Paramètres retenus pour cette installation :

| Paramètre | Valeur |
|---|---|
| Modèle | Raspberry Pi 4 visé au départ (`bitwarden/_plan/plan-conception.md`) — **corrigé en Raspberry Pi 3 Model B+ (1 Go RAM)**, le matériel réellement disponible et utilisé (confirmé le 2026-08-12, voir note ci-dessous) |
| OS | Raspberry Pi OS **Lite (64-bit)** visé — **la carte a en réalité été flashée avec l'image Desktop complète** (voir correctif Partie 3bis) |
| Réseau | WiFi (SSID/mot de passe de la box SFR, saisis par toi dans l'imager — jamais transmis à Claude) |
| Accès | Headless complet — SSH par clé publique dès le premier boot, pas d'écran/clavier |
| Hostname | `raspi-home` → accessible ensuite via `raspi-home.local` (mDNS/avahi) — en pratique, la résolution mDNS a échoué depuis ce PC, connexion faite par IP DHCP (`192.168.1.99`) |
| Utilisateur | `julien`, authentification SSH par la clé déjà présente sur ce PC (`~/.ssh/id_rsa.pub`) |

**Note (2026-08-12)** : le matériel réellement utilisé est un Raspberry Pi 3 Model B+ (1 Go RAM, quad-core Cortex-A53), pas le Pi 4 initialement prévu dans `bitwarden/_plan/plan-conception.md`. Confirmé volontaire par l'utilisateur — `bitwarden/README.md` et `edge/README.md` ont été mis à jour en conséquence. Conséquence pratique : la marge RAM disponible pour Docker est nettement plus faible (~600-700 Mo après libération du GUI, voir Partie 3bis) qu'avec un Pi 4 ; à surveiller si un service supplémentaire (ex. paperless) devait être ajouté sur cette même machine plus tard.

## Partie 1 — Flasher la carte SD (à faire par toi, `rpi-imager` déjà installé)

**Cette étape efface intégralement le contenu actuel de `/dev/sda`.** À exécuter uniquement dans l'interface graphique `rpi-imager` (nécessite une confirmation root que Claude n'a pas — empreinte digitale configurée sur ce PC).

1. Lancer `rpi-imager` (menu applications, ou `rpi-imager` dans un terminal).
2. **Choose Device** → Raspberry Pi 3 (les modèles B/B+/A+ partagent la même image).
3. **Choose OS** → `Raspberry Pi OS (other)` → `Raspberry Pi OS **Lite** (64-bit)` — bien vérifier "Lite" et pas l'image par défaut (Desktop) : sur cette installation, l'image Desktop a été flashée par erreur (voir Partie 3bis), consommant une partie non négligeable des 1 Go de RAM disponibles pour rien sur une machine headless.
4. **Choose Storage** → sélectionner la carte de 14,9 Go (vérifier la taille affichée avant de continuer, pour ne pas se tromper de disque si plusieurs supports sont branchés).
5. Cliquer sur l'icône ⚙️ (réglages, en bas à droite) **avant** de cliquer sur Next/Write :
   - **Hostname** : `raspi-home`
   - **Enable SSH** → *Allow public-key authentication only* → coller la clé publique ci-dessous
   - **Set username and password** : username `julien`, mot de passe fort quand même demandé (filet de secours, l'auth par clé reste le mode normal)
   - **Configure wireless LAN** : SSID et mot de passe de la box SFR (à saisir toi-même dans le champ, pas ici), Wireless LAN country `FR`
   - **Set locale settings** : Time zone `Europe/Paris`, Keyboard layout `fr`
   - Sauvegarder les réglages.
6. **Write**, confirmer l'effacement, attendre la fin de l'écriture + vérification.

Clé publique à coller dans le champ SSH de l'imager :

```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCcP5h7DBpU1RYdeT1WViH8IhoKbwydZVJPbbEanzD94OUzn0lAH01CpSpmLNhp6FNY4Q3atifWWhahKmH1DuFQmfF3Yq8AOjTxe1Iw9qZspmtH1eDlVHjye21qhN6Nh1nHzAawWwstaIgLLzmAygp90BXk7KU/4ZxJZdasD1KETxZcpgWUc4ewHgwJvXq5Yd19GNiNnyjHnsnSPEOEOJvahYyRhAMc6OWQxuuWa8jO7ljgAklhCX8KivGm7vnNOR8CfgKPr+0FcDEgiuU50oJs5WevLLnEGw6Ud4PNEKaV5ke53Wp7cRoUgbBpxtZ/aQfNwdv4OxyEECtqzbgWJeiSa9nvLkHvb2vRLcGRVbkubE8t5jz50anpHUFiOdBotCp2KRwezqh03AUdmUb9eQ1vVNjhqTod54MSWAG6+1W+VkbUlyU82YVD7bGbgWnyhiGkzBMWkeYMLai5HNmTCamiVwyaWMqlL0DxsVIwoJJJW1u4yhTMTPRSSVB/1epi8tU= julien@jvince-scality
```

7. Éjecter la carte, l'insérer dans le Raspberry Pi, brancher l'alimentation (pas besoin d'écran/clavier/ethernet).

## Partie 2 — Premier boot et vérification d'accès

1. Attendre 1-2 minutes (premier boot, expansion du système de fichiers, connexion WiFi).
2. Depuis ce PC :
   ```bash
   ping raspi-home.local
   ssh julien@raspi-home.local
   ```
   La connexion doit s'établir par clé, sans demande de mot de passe. Si `raspi-home.local` ne résout pas (mDNS parfois filtré par la box), chercher l'IP attribuée dans la table DHCP de l'interface d'admin de la box SFR et utiliser `ssh julien@<ip>` à la place.
3. En cas d'échec de connexion WiFi (pas d'entrée dans la table DHCP après quelques minutes) : rebrancher la carte sur ce PC et vérifier le SSID/mot de passe saisis à l'étape 1.5 (erreur de frappe la cause la plus fréquente), ou repasser par un câble Ethernet le temps du premier diagnostic.

## Partie 3 — Durcissement de base et Docker (sur le Pi, en SSH)

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
# se reconnecter après le reboot : ssh julien@raspi-home.local

# Docker + plugin Compose (script officiel, inclut le plugin compose v2)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker julien
# se déconnecter/reconnecter pour que l'appartenance au groupe docker soit prise en compte
exit
ssh julien@raspi-home.local

docker compose version   # doit répondre, sans sudo
```

IPv6 stable (nécessaire pour DuckDNS/Let's Encrypt DNS-01 et pour la règle de pare-feu SFR — voir `bitwarden/README.md` Phase C §1.3, directement applicable ici) :

```bash
ip -6 addr show scope global
# repérer l'adresse marquée mngtmpaddr (stable), pas une adresse "temporary"

# le Pi étant une machine dédiée, désactiver les extensions de confidentialité IPv6 simplifie tout :
sudo tee /etc/sysctl.d/99-disable-ipv6-privacy.conf <<'EOF'
net.ipv6.conf.all.use_tempaddr=0
net.ipv6.conf.default.use_tempaddr=0
EOF
sudo sysctl --system
sudo reboot
```

Raspberry Pi OS Lite n'active aucun pare-feu par défaut (pas de `ufw`) — rien à faire de ce côté sur le Pi lui-même ; le filtrage se fera au niveau de la box SFR (Partie 5).

## Partie 3bis — Correctif : image Desktop flashée par erreur

Constaté le 2026-08-12 : la carte a été flashée avec l'image Desktop (présence de `xserver-xorg-core`, boot sur `graphical.target`, session graphique complète — labwc, pcmanfm, wireplumber, xdg-desktop-portal... — démarrée automatiquement) au lieu de l'image Lite prévue. Sur un Pi 3 B+ à 1 Go de RAM total, c'est significatif : la session graphique à elle seule occupait plusieurs dizaines de Mo par processus.

Plutôt que reflasher la carte (perte de la config SSH/WiFi déjà en place), correctif appliqué à chaud, réversible, sans toucher à la carte SD :

```bash
sudo systemctl set-default multi-user.target
sudo reboot
```

Bascule le boot sur une cible CLI pure — la session graphique ne démarre plus, la RAM qu'elle utilisait redevient disponible pour Docker. Se reconnecter en SSH après le reboot pour la suite.

## Partie 4 — Copier le projet sur le Pi

Depuis ce PC (pas sur le Pi), copie directe des deux dossiers de service, `.env` et secrets compris — transfert de machine à machine sur le LAN via SSH, pas via git (le dépôt n'a aucun commit à ce stade, et `.env`/`rclone.conf` ne doivent de toute façon jamais être commités) :

```bash
cd /ws/personal/home_services
rsync -avz --exclude '.git' edge/      julien@raspi-home.local:~/home_services/edge/
rsync -avz --exclude '.git' bitwarden/ julien@raspi-home.local:~/home_services/bitwarden/
```

Rappel (déjà noté dans `bitwarden/_plan/plan-sauvegarde.md`) : si `RESTIC_PASSWORD` n'a pas encore été recopié ailleurs que sur ce PC, le faire **avant** cette copie — perdu, les sauvegardes restic sont irrécupérables. Si `bitwarden/rclone.conf` existe déjà sur ce PC (autorisation Google Drive faite), il sera copié par le `rsync` ci-dessus ; sinon l'étape `scripts/authorize-gdrive.sh` peut être refaite directement sur le Pi.

## Partie 5 — Revalider en staging sur le Pi, puis suivre les étapes déjà documentées

Sur le Pi, reprendre exactement les commandes déjà données par `edge/README.md` et `bitwarden/README.md` ("Pour reprendre") :

```bash
cd ~/home_services/edge && docker compose up -d
cd ~/home_services/bitwarden && docker compose up -d
curl -sSk --resolve jvince.duckdns.org:443:127.0.0.1 https://jvince.duckdns.org/ -o /dev/null -w "bitwarden: %{http_code}\n"
curl -sSk --resolve paperless-jvince.duckdns.org:443:127.0.0.1 https://paperless-jvince.duckdns.org/ -o /dev/null -w "paperless: %{http_code}\n"
```

Point d'attention propre au changement de machine : `sidecar-ddns` va maintenant publier l'IPv6 **réelle du Pi sur le réseau domestique**, différente de celle de ce PC utilisée pour les tests précédents. Vérifier les logs (`docker compose logs -f sidecar-ddns`) et confirmer par une résolution DNS publique tierce (`dig AAAA jvince.duckdns.org @1.1.1.1`) que c'est bien la nouvelle adresse qui est publiée.

Une fois ce test en staging validé sur le Pi (le vrai objectif de cette Partie 5 — confirmer que le matériel définitif fonctionne, avant toute bascule en production), la suite est **déjà documentée et ne change pas** :

- Ouverture du pare-feu IPv6 de la box SFR vers le Pi (port 443 uniquement, vers l'adresse IPv6 stable notée en Partie 3) → `bitwarden/README.md`, Phase C §2.
- Bascule des certificats en production (Let's Encrypt, sans `--staging`) → `edge/README.md` Phase 3, section production.
- Création des comptes et validation depuis un réseau externe → `bitwarden/README.md`, Phase C §4-5.

Ces étapes ne sont pas dupliquées ici pour rester la source unique de vérité dans les README de chaque service.

## Checklist résumée

- [x] Carte SD flashée — écart constaté : hostname `raspi-home` et SSH par clé OK, mais **image Desktop au lieu de Lite** (corrigé en Partie 3bis) ; connexion finalement faite par IP DHCP (`192.168.1.99`), pas par `raspi-home.local` (mDNS non résolu depuis le PC de dev)
- [x] Premier boot + connexion SSH réussie
- [x] `apt full-upgrade`, Docker (v29) + Compose (v5.4.0) installés et vérifiés (`docker run hello-world` en arm64), IPv6 privacy extensions désactivées (adresse `mngtmpaddr` déjà stable)
- [x] `edge/` et `bitwarden/` copiés sur le Pi via `rsync` (avec `.env` ; pas de `rclone.conf` à copier, l'autorisation Google Drive n'a pas encore été faite sur le PC de dev)
- [x] `edge` + `bitwarden` démarrés sur le Pi (2026-08-12) — correctif nécessaire : le certificat de test auto-signé (`cert-init`) et les certificats staging vivent dans des **volumes Docker**, non copiés par `rsync` ; refaits sur le Pi (`cert-init`, puis réémission staging DNS-01 pour `jvince`/`paperless-jvince`). DDNS confirmé avec l'IPv6 réelle du Pi (`2a02:8428:96a:5801:ba27:ebff:fedb:f779`). **Test réussi : `https://jvince.duckdns.org` → 200 via edge sur le Pi** (bitwarden). `paperless-jvince` → 502, attendu : paperless n'a pas été copié sur ce Pi (hors périmètre de cette installation).
- [x] Pare-feu SFR ouvert (443 → Pi) — règle `edge-https` (TCP/443, destination = IPv6 du Pi) ajoutée dans la section "Réseau v6" de l'admin box (2026-08-12)
- [x] Certificat de production émis pour `jvince.duckdns.org` (piège rencontré et documenté dans `edge/README.md` : `--server letsencrypt` obligatoire, sinon échec silencieux sur ZeroSSL) ; validé depuis un point réellement externe au réseau domestique (TLS accepté sans avertissement, page Vaultwarden servie)
- [ ] Comptes créés (2-3 utilisateurs), sync temps réel validée avec un vrai client Bitwarden authentifié — reste à faire (`bitwarden/README.md` Phase C §4-5)

### Écarts et correctifs découverts à l'usage sur le Pi

- **Volumes Docker non transférés par `rsync`** : `rsync` ne copie que les fichiers du dépôt, jamais les volumes Docker (données, certificats, état acme.sh) qui vivent dans `/var/lib/docker/volumes/` sur la machine de dev. Sans conséquence ici car aucune donnée réelle n'existait encore (jamais basculé en production) — mais **si une bascule en production avait déjà eu lieu sur le PC de dev, ce protocole ne suffit pas** : il faudrait alors une vraie procédure de migration de volumes (export/import), pas un simple `rsync` du dossier service.
- **`cert-init` doit être rejoué sur chaque nouvelle machine** avant le premier démarrage de `reverse-proxy` : le bloc `server_name _` par défaut (`nginx/conf.d/00-default.conf`) référence un certificat auto-signé qui n'existe que dans le volume `edge_certs`, sinon `nginx` part en crash-loop (`cannot load certificate .../_test/fullchain.pem`).
