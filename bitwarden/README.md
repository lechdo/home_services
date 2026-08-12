# bitwarden

Voir `_plan/analyse-besoin-fonctionnel.md` et `_plan/plan-conception.md` pour le contexte complet.

## Où on en est (reprendre rapidement)

**Dernier état (2026-08-12)** : migration vers `edge` implémentée et validée en local (voir `_plan/plan-migration-edge.md`). Ce service ne gère plus lui-même son DNS/TLS — **les sections "Phase A/B/C" ci-dessous décrivent l'ancienne architecture (historique, conservée pour le contexte SFR/Raspberry Pi), remplacée par le flux suivant** :

- `bitwarden/compose.yaml` : seulement `vaultwarden` + `reverse-proxy` (HTTP interne, plus de TLS/DuckDNS ici). `reverse-proxy` publié sur `127.0.0.1:8081`.
- Le sous-domaine `jvince.duckdns.org`, le token DuckDNS et le certificat (actuellement **staging**) sont désormais possédés par le service `/edge/` — voir `../edge/README.md` pour le démarrer/reprendre.
- Volumes conservés : `bitwarden_vaultwarden_data` (données vaultwarden). `bitwarden_certs`/`bitwarden_acme_state` sont **orphelins** (plus référencés par ce `compose.yaml`, laissés intacts sur disque — purge manuelle possible : `docker volume rm bitwarden_certs bitwarden_acme_state`).
- Bug pré-existant découvert lors de la migration, sans lien avec elle, **corrigé** : le websocket `/notifications/hub` proxifiait vers le port 3012, supprimé depuis Vaultwarden 1.31.0 (websocket intégré au port HTTP principal). Route désormais vers `vaultwarden:80`, `ENABLE_WEBSOCKET=true` (remplace `WEBSOCKET_ENABLED`, déprécié). Validé : passe de `502` à `401` (auth requise, comportement normal). Reste à valider avec un vrai client Bitwarden authentifié — voir `_plan/plan-migration-edge.md`.

**Pour reprendre à l'identique** :
```bash
cd /ws/personal/home_services/edge && docker compose up -d       # DNS + TLS + routage
cd /ws/personal/home_services/bitwarden && docker compose up -d  # vaultwarden + reverse-proxy HTTP interne
curl -sSk --resolve jvince.duckdns.org:443:127.0.0.1 https://jvince.duckdns.org/ -o /dev/null -w "%{http_code}\n"
```

**Décision initiale** : cible finale = un Raspberry Pi 4 dédié. **Corrigé (2026-08-12)** : le matériel réellement utilisé est un **Raspberry Pi 3 Model B+ (1 Go RAM)** — voir `../deploiement-raspberry.md` pour le détail et les écarts constatés (image Desktop flashée par erreur puis corrigée, RAM disponible plus faible qu'anticipé). Docker Compose reste retenu (Kubernetes/minikube écarté — trop lourd même pour un Pi4, a fortiori pour un Pi3, voir `_plan/plan-conception.md`).

**Fait (2026-08-12)** : `edge` + `bitwarden` déployés sur le Pi (`raspi-home`, `192.168.1.99`), certificats staging réémis sur cette machine (les volumes Docker de certs ne se copient pas avec les fichiers du dépôt), DDNS confirmé avec l'IPv6 réelle de la maison. **Test de bout en bout réussi sur le matériel définitif** : `https://jvince.duckdns.org` → `200` via edge sur le Pi.

**Prochaine étape** (protocole complet dans `../deploiement-raspberry.md`) :
1. ~~Installer Docker + Compose sur le Raspberry Pi, y copier `edge/` et `bitwarden/`.~~ Fait.
2. ~~Reproduire ce même flux (edge en staging) sur le Pi pour valider le matériel définitif.~~ Fait.
3. ~~Configurer le pare-feu IPv6 de la box SFR vers le Pi (443 → adresse IPv6 stable du Pi).~~ Fait (2026-08-12) — règle `edge-https`, TCP/443, ajoutée dans la section "Réseau v6" de l'admin box.
4. ~~Basculer le certificat `jvince.duckdns.org` en production côté `edge` (sans `--staging`), valider depuis un réseau externe.~~ **Fait (2026-08-12)** : certificat de production Let's Encrypt émis et installé (voir `../edge/README.md` pour un piège rencontré : `--server letsencrypt` est obligatoire, sinon acme.sh part sur ZeroSSL et échoue silencieusement). Validé depuis un point du réseau réellement externe (hors LAN de la maison) : TLS accepté sans avertissement, page de connexion Vaultwarden servie.
5. ~~Créer les 2-3 comptes.~~ **Fait (2026-08-12)** : 2 comptes créés, organisation "Foyer" + collection "Partagé" mises en place pour les mots de passe communs. `SIGNUPS_ALLOWED` repassé à `false` une fois les comptes créés.
6. Valider la sync temps réel avec un vrai client Bitwarden authentifié (le fix appliqué corrige l'accessibilité de l'endpoint — `401` au lieu de `502` — pas encore testé avec un compte/token réel).

### Comptes et organisation (2026-08-12)

- Deux comptes créés (`julien.vince@gmail.com`, propriétaire de l'organisation ; `vince.virginie.35@gmail.com`, membre). Organisation "Foyer", collection "Partagé" pour les mots de passe communs — tout le reste demeure privé à chaque compte.
- **Aucun SMTP configuré** sur ce serveur (`SMTP_HOST` absent de `.env`). Conséquence découverte à l'usage : Vaultwarden **n'affiche aucun lien d'invitation dans les logs** en l'absence de SMTP (contrairement à un comportement parfois documenté ailleurs) ; en revanche, pour un email correspondant à un compte local déjà existant, l'invitation à une organisation passe automatiquement au statut *Accepted* sans action de l'invité — il reste uniquement à ce que le **propriétaire de l'organisation** clique sur **Confirmer** dans Organisation → Membres pour finaliser (étape normale du flux Bitwarden, distincte de l'acceptation). Vérifié en lisant directement `users_organizations` dans `db.sqlite3` (lecture seule, via un conteneur `alpine`+`sqlite` monté sur le volume `bitwarden_vaultwarden_data`).
- Si des emails de vérification/réinitialisation de mot de passe sont nécessaires plus tard, il faudra configurer un vrai SMTP (`SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM` dans `.env`) — non fait pour l'instant, pas bloquant pour l'usage à 2 comptes actuel.

### Point non résolu : enregistrement DNS A (IPv4) parasite

Constaté le 2026-08-12 : `jvince.duckdns.org` a un enregistrement **A (IPv4)** `93.3.72.101` en plus du AAAA correct — résidu probable d'un test DDNS lancé depuis ce PC de dev avant la migration vers `edge` (l'API DuckDNS peut fixer l'IPv4 depuis l'IP de la requête même quand seul `ipv6=` est fourni explicitement). Rien n'écoute sur cette IPv4 : sans conséquence fonctionnelle tant que le client (navigateur, appli Bitwarden) choisit l'IPv6, mais source de confusion possible (vu en pratique : Chrome a affiché un avertissement de certificat en visitant par erreur `paperless-jvince.duckdns.org`, non lié à ce résidu, mais le réflexe de vérifier `dig A`/`dig AAAA` a permis de le repérer). **À nettoyer** : se connecter sur https://www.duckdns.org et vider manuellement le champ IPv4 du sous-domaine `jvince` (l'API de mise à jour ne permet pas de le faire sans risquer d'effacer aussi l'IPv6).

**Si des jours/semaines passent avant de reprendre** : le certificat staging installé (côté `edge` désormais) a une durée de validité limitée (~90 jours) — sans conséquence puisqu'il sera de toute façon réémis en production sur le Pi à la Phase C.

---

## Sauvegarde (restic + rclone → Google Drive)

Voir `_plan/plan-sauvegarde.md` pour le détail complet. Statut (2026-08-12) : `sidecar-backup` implémenté dans `compose.yaml`, `RESTIC_PASSWORD` généré dans `.env`, et deux scripts (`scripts/authorize-gdrive.sh`, `scripts/setup-backup.sh`) préparés pour réduire la mise en place au strict geste manuel irréductible (l'autorisation OAuth dans un navigateur) — **toujours bloqué sur ce geste**, à faire par toi.

### 1. Autoriser rclone à accéder à ton Google Drive (à faire toi-même)

Sur une machine qui a un navigateur (pas forcément celle qui héberge bitwarden en prod) :

```bash
./scripts/authorize-gdrive.sh
```

Le script ouvre le flux `rclone authorize "drive"` : suis le lien affiché, connecte-toi/autorise l'accès à ton propre Google Drive. Il récupère ensuite lui-même le bloc JSON du token et génère `rclone.conf` — pas de copier-coller manuel dans le fichier.

Si cette machine n'est pas celle qui héberge bitwarden en prod (ex. tu autorises depuis ton PC mais la cible est le Raspberry Pi), copie le `rclone.conf` généré vers le dossier `bitwarden/` de la machine cible avant l'étape suivante.

### 2. Vérifier `RESTIC_PASSWORD` dans `.env`

Un mot de passe a déjà été généré et placé dans `.env`. **Si ce n'est pas déjà fait, copie-le maintenant ailleurs que sur cette machine** (gestionnaire de secrets, note physique...) — perdu, les sauvegardes chiffrées sont définitivement irrécupérables, y compris pour toi.

### 3. Finaliser la mise en place

```bash
./scripts/setup-backup.sh
```

Le script vérifie les préconditions, active `COMPOSE_PROFILES=backup` dans `.env`, initialise le dépôt restic **s'il ne l'est pas déjà** (idempotent — peut être relancé sans risque), puis démarre `sidecar-backup`. Suivre le premier backup avec `docker compose logs -f sidecar-backup`.

### 4. Tester la restauration (à faire au moins une fois avant de faire confiance au dispositif)

Voir `_plan/plan-sauvegarde.md` §5 pour la procédure complète (restauration dans un volume de test, jamais directement sur le volume de production au premier essai).

---

**Note** : les sections "Phase A/B/C" ci-dessous décrivent l'architecture *avant* la migration vers `edge` (DuckDNS/ACME/DDNS géré directement par ce service). Elles restent utiles pour le contexte (contraintes SFR/IPv6, cible Raspberry Pi) mais les commandes `docker compose` qu'elles donnent ne correspondent plus au `compose.yaml` actuel — se référer à `_plan/plan-migration-edge.md` et à `../edge/README.md` pour les commandes à jour.

## Phase A — local, sans exposition internet

Ne fait intervenir que `vaultwarden` + `reverse-proxy`, avec un certificat auto-signé — aucune ouverture de pare-feu, aucune dépendance internet. C'est le profil Compose par défaut (`sidecar-acme`/`sidecar-ddns` ne démarrent pas).

## Prérequis

- Docker + Docker Compose (`docker compose version`).
- Choisir un hôte local de test (ex. `vault.home.test`, TLD `.test` réservée aux tests — RFC 2606) et l'ajouter dans `/etc/hosts` de chaque machine qui doit accéder au service, en pointant vers l'IP LAN de ce serveur :
  ```
  192.168.x.y   vault.home.test
  ```

## 1. Configuration

```bash
cp .env.example .env
# éditer .env : LOCAL_HOSTNAME (doit correspondre à l'entrée /etc/hosts) et ADMIN_TOKEN (valeur forte, ex. openssl rand -base64 48)
```

## 2. Génération du certificat auto-signé

À exécuter une seule fois (le conteneur `cert-init` ne tourne jamais en continu) :

```bash
docker compose run --rm cert-init
```

Relancer cette commande si `LOCAL_HOSTNAME` change (le script ne régénère pas le certificat s'il en trouve déjà un dans le volume — supprimer le volume `bitwarden_certs` pour forcer une régénération).

## 3. Démarrage

```bash
docker compose up -d
docker compose ps
docker compose logs -f vaultwarden
```

## 4. Tests à réaliser

- Depuis un navigateur d'une machine du LAN (avec l'entrée `/etc/hosts` en place) : `https://vault.home.test` — un avertissement de certificat non fiable est **attendu** (auto-signé), à accepter manuellement pour les tests.
- Créer le premier compte, se connecter au web vault.
- Installer l'extension navigateur / l'app mobile, configurer le "self-hosted server URL" sur `https://vault.home.test`, vérifier la connexion et la synchronisation.
- Vérifier la synchronisation temps réel (websocket) : modifier une entrée sur un client, constater la mise à jour sur un autre client connecté.

## 5. Arrêt / nettoyage

```bash
docker compose down          # arrête les conteneurs, conserve les volumes (données + certificat)
docker compose down -v       # arrête et supprime aussi les volumes (perte des données et du certificat)
```

## Notes Phase A

- `ADMIN_TOKEN` en clair dans `.env` est acceptable pour cette phase de test local ; il devra être remplacé par un hash Argon2 avant l'exposition internet réelle (Phase C, durcissement — voir roadmap dans `_plan/plan-conception.md`).
- `.env` ne doit jamais être committé (secrets).

---

## Phase B — domaine réel (DuckDNS) + Let's Encrypt staging

Toujours en local (pas d'ouverture de pare-feu à ce stade) : on remplace le certificat auto-signé par un vrai certificat Let's Encrypt (environnement **staging**, pour ne pas consommer le rate limit de production pendant les tests), obtenu via challenge DNS-01 chez DuckDNS. `sidecar-acme` gère le renouvellement automatique, `sidecar-ddns` maintient l'enregistrement AAAA à jour.

### 1. Créer le compte DuckDNS

- Se connecter sur https://www.duckdns.org (login via un compte existant, ex. GitHub/Google).
- Créer un sous-domaine (ex. `moncoffre` → `moncoffre.duckdns.org`) et noter le **token** affiché en haut de la page.

### 2. Configuration

Dans `.env` :
```bash
LOCAL_HOSTNAME=moncoffre.duckdns.org
DUCKDNS_TOKEN=<le token DuckDNS>
COMPOSE_PROFILES=duckdns
```

### 3. Émission du certificat (une seule fois)

```bash
docker compose up -d sidecar-acme   # démarre le conteneur (mode daemon, sans effet immédiat)

# 1) émission du certificat en environnement STAGING (obligatoire pour les tests)
docker compose run --rm sidecar-acme --issue --staging \
  --dns dns_duckdns \
  -d "$LOCAL_HOSTNAME"

# 2) installation du certificat dans le volume partagé avec nginx
docker compose run --rm sidecar-acme --install-cert -d "$LOCAL_HOSTNAME" \
  --fullchain-file /certs/fullchain.pem \
  --key-file /certs/privkey.pem
```

`--install-cert` est mémorisé par acme.sh pour ce domaine : les renouvellements automatiques ultérieurs (cron interne du conteneur `sidecar-acme`, `command: daemon`) réinstalleront seuls le certificat renouvelé dans le même volume, sans action manuelle.

### 4. Démarrage complet

```bash
docker compose up -d      # avec COMPOSE_PROFILES=duckdns dans .env : les 4 services démarrent
docker compose ps
docker compose logs -f sidecar-ddns
```

### 5. Tests à réaliser

- `docker compose logs sidecar-ddns` : vérifier la ligne `DuckDNS AAAA à jour` (pas d'erreur de token/réseau).
- Depuis le LAN : `https://moncoffre.duckdns.org` — le navigateur affiche un avertissement "certificat non fiable" **normal en staging** (Let's Encrypt staging n'est pas reconnu par défaut par les navigateurs) ; c'est le comportement attendu, pas une erreur de configuration.
- Vérifier que `reverse-proxy` a bien chargé le nouveau certificat (pas l'auto-signé de la Phase A) : `docker compose exec reverse-proxy sh -c "openssl x509 -in /etc/nginx/certs/fullchain.pem -noout -issuer"` doit mentionner *(STAGING)* Let's Encrypt.
- Le reload nginx se fait au plus toutes les 6h (voir commentaire dans `compose.yaml`) : après l'étape 3, attendre le prochain cycle ou forcer un reload manuel pour test immédiat : `docker compose exec reverse-proxy nginx -s reload`.

### Notes Phase B

- Le secret **DUCKDNS_TOKEN** donne à la fois la mise à jour DNS et la capacité d'obtenir des certificats pour ce domaine — à protéger comme un secret sensible, jamais committé.
- Pour repartir de zéro (changer de sous-domaine, etc.) : `docker compose down -v` supprime aussi le volume `acme_state` (état/compte acme.sh) et `certs`.
- Passage en production (Phase C) : réémettre sans `--staging` (`docker compose run --rm sidecar-acme --issue --dns dns_duckdns -d "$LOCAL_HOSTNAME" --force`) puis ré-exécuter l'étape `--install-cert` — uniquement une fois le pare-feu IPv6 du routeur ouvert et le nom de domaine joignable depuis internet (voir `_plan/plan-conception.md`, Phase C).
- `sidecar-ddns` tourne en `network_mode: host` (pas sur le réseau `internal`) : c'est volontaire, voir le commentaire dans `compose.yaml` et `_plan/plan-conception.md` (§ Phase B) — le réseau bridge par défaut de Docker n'offre pas de sortie IPv6, nécessaire pour que ce conteneur détermine l'IPv6 publique réelle de la machine.
- L'IPv6 publiée par `sidecar-ddns` peut être une adresse temporaire (extensions de confidentialité IPv6) qui change périodiquement sur un poste de développement classique — sans conséquence en Phase B (LAN uniquement), mais à traiter avant la Phase C (voir note dans `_plan/plan-conception.md`).

---

## Phase C — exposition internet réelle (production)

Le serveur cible est une machine dédiée (NAS/Raspberry Pi/mini-PC), distincte de la machine utilisée pour les Phases A/B. **Toutes les étapes ci-dessous sont manuelles** : elles nécessitent un accès physique/admin au serveur dédié et au routeur, que je n'ai pas.

### 1. Préparer le serveur dédié

1. Installer Docker + Docker Compose sur cette machine.
2. Copier ce dossier `bitwarden/` (compose.yaml, nginx/, .env) sur cette machine.
3. Vérifier l'adresse IPv6 LAN de cette machine avec `ip -6 addr show scope global` : repérer l'adresse **stable** (celle marquée `mngtmpaddr`, ou l'adresse SLAAC si les extensions de confidentialité sont désactivées) — c'est celle-ci qui doit être ciblée par la règle de pare-feu du routeur, pas une adresse marquée `temporary` (qui change régulièrement).
   - Si la machine est bien dédiée à cet usage (contrairement à un PC portable qui change de réseau), désactiver les extensions de confidentialité IPv6 simplifie tout : `sudo sysctl -w net.ipv6.conf.all.use_tempaddr=0 net.ipv6.conf.default.use_tempaddr=0`, à rendre persistant dans `/etc/sysctl.d/99-disable-ipv6-privacy.conf`, puis reboot (ou renouveler le bail IPv6 de l'interface).
4. Reproduire la Phase B sur cette machine (`.env` avec `LOCAL_HOSTNAME`, `DUCKDNS_TOKEN`, `COMPOSE_PROFILES=duckdns`, puis émission du certificat **staging** comme en Phase B) pour valider que tout fonctionne aussi sur le matériel définitif avant de basculer en production.
5. Durcissement : régénérer `ADMIN_TOKEN` et le stocker sous forme de hash Argon2 plutôt qu'en clair :
   ```bash
   docker run --rm vaultwarden/server /vaultwarden hash
   # coller le hash obtenu (commence par $argon2...) dans ADMIN_TOKEN, dans .env
   ```
6. Une fois les 2-3 comptes créés (voir §5 ci-dessous), repasser `SIGNUPS_ALLOWED=false` dans `.env` puis `docker compose up -d` pour appliquer.

### 2. Configurer le routeur SFR (et le routeur personnel si présent)

1. Se connecter à l'interface d'admin de la box SFR (identifiants sur l'étiquette de la box ou l'espace client SFR).
2. Décider du mode réseau (cf. `_plan/plan-conception.md` §3) :
   - S'il y a un routeur personnel derrière la box SFR : passer la box SFR en mode **Bridge/Passthrough** pour l'IPv6, afin que le pare-feu ne se configure qu'à un seul endroit (le routeur personnel). Recommandé.
   - Sinon (serveur branché directement sur la box SFR) : le pare-feu se configure directement sur l'interface "FGW" de la box.
3. Sur l'équipement qui gère effectivement le pare-feu IPv6 entrant : ajouter une règle autorisant le port **443/TCP entrant** vers l'adresse IPv6 stable notée à l'étape 1.3. (Port 80 non nécessaire : le challenge ACME utilisé est DNS-01, pas HTTP-01.)
4. Vérifier qu'aucun pare-feu logiciel sur le serveur dédié lui-même (ufw/firewalld/iptables/nft) ne bloque le port 443 en entrée.

### 3. Basculer le certificat en production

Une fois le pare-feu ouvert et `jvince.duckdns.org` en théorie joignable depuis internet :

```bash
docker compose run --rm sidecar-acme --issue --dns dns_duckdns -d "$LOCAL_HOSTNAME" --force
docker compose run --rm sidecar-acme --install-cert -d "$LOCAL_HOSTNAME" \
  --fullchain-file /certs/fullchain.pem \
  --key-file /certs/privkey.pem
docker compose exec reverse-proxy nginx -s reload   # pour ne pas attendre le cycle de 6h
```

Ne faire cette étape qu'**une fois que tout le reste est en place et testé** (Phase B validée sur ce matériel, pare-feu ouvert) — le rate limit de production Let's Encrypt est plus strict qu'en staging, éviter de la répéter inutilement.

### 4. Créer les comptes (2-3 utilisateurs)

- Avec `SIGNUPS_ALLOWED=true` temporairement : chaque utilisateur crée son compte lui-même sur `https://jvince.duckdns.org`, puis repasser `SIGNUPS_ALLOWED=false`.
- Ou, sans exposer les inscriptions : générer un lien d'invitation depuis le panneau `/admin` (protégé par `ADMIN_TOKEN`) et le transmettre hors bande à chaque utilisateur.

### 5. Valider depuis un réseau réellement externe

- Depuis une connexion mobile (4G/5G compatible IPv6) ou en demandant à quelqu'un hors du domicile : ouvrir `https://jvince.duckdns.org` — doit répondre sans avertissement de certificat (production Let's Encrypt).
- Sur plusieurs jours/semaines : surveiller `docker compose logs sidecar-ddns` pour confirmer que l'IPv6 suit bien un éventuel changement de préfixe SFR, et que le service reste joignable après.
- Sur le long terme : `docker compose logs sidecar-acme` doit montrer un renouvellement automatique réussi avant l'expiration du certificat (tous les ~60 jours pour Let's Encrypt).
