# Service bitwarden — CLAUDE.md

Complète le `CLAUDE.md` racine. Ce service héberge un gestionnaire de mots de passe compatible Bitwarden, accessible depuis internet en IPv6, avec renouvellement automatique de certificat TLS via un sidecar dédié.

Voir `_plan/analyse-besoin-fonctionnel.md` (le besoin) et `_plan/plan-conception.md` (l'architecture cible) avant toute implémentation.

**Migration vers `edge` implémentée (2026-08-12)** : ce service ne possède plus de DuckDNS/ACME/DDNS propre. Le `reverse-proxy` ne termine plus le TLS — il écoute en HTTP interne sur `127.0.0.1:8081`, routé par le service `/edge/` qui possède désormais le sous-domaine (`jvince.duckdns.org`), le certificat et le token DuckDNS. Voir `_plan/plan-migration-edge.md` pour le détail et l'état exact (validé en local avec un certificat staging ; pas encore basculé en production ni testé sur la machine cible finale).

**Bug pré-existant découvert lors de la migration, sans lien avec elle — corrigé (2026-08-12)** : le websocket `/notifications/hub` proxifiait vers `vaultwarden:3012`, port supprimé depuis Vaultwarden 1.31.0 (websocket intégré au port HTTP principal). Corrigé et validé (401 au lieu de 502) — voir `_plan/plan-migration-edge.md`. Reste à valider avec un vrai client Bitwarden authentifié.

## Caractéristiques spécifiques à ce service

- **Conteneurisation obligatoire** : le service est packagé entièrement via **Docker Compose** — un unique `compose.yaml` orchestrant vaultwarden, reverse-proxy, sidecar-acme et sidecar-ddns. Aucun composant ne doit être installé nativement sur l'hôte (hors Docker lui-même).
- **Implémentation retenue par défaut** : Vaultwarden (compatible API Bitwarden, léger — sqlite), plutôt que Bitwarden officiel (qui nécessite MSSQL et davantage de ressources). Vaultwarden n'est pas un projet officiel Bitwarden ; à mentionner si pertinent (compatibilité clients identique, support communautaire).
- **Contrainte réseau structurante** : pas d'IPv4 publique fiable (CGNAT probable) → toute solution de certificat/exposition doit fonctionner en IPv6-only. Ne jamais concevoir une solution qui suppose un accès entrant IPv4.
- **Challenge ACME recommandé** : DNS-01 (API du fournisseur DNS) plutôt que HTTP-01, pour rester robuste face à un préfixe IPv6 qui peut changer et à un pare-feu entrant potentiellement instable. Ne changer ce choix qu'après avoir statué sur les questions ouvertes du besoin fonctionnel (fournisseur DNS, stabilité du préfixe).
- **Secrets** : ADMIN_TOKEN Vaultwarden, clé API DNS (si DNS-01), et tout secret SMTP ne doivent jamais être committés en clair dans ce dossier. Utiliser des variables d'environnement/secrets Docker non versionnés.
- **Tests obligatoirement progressifs** : local sans internet → local avec Let's Encrypt *staging* → exposition internet réelle en production. Ne jamais tester en production Let's Encrypt de façon répétée (rate limit).
- **Vaultwarden n'est jamais exposé directement** : seul le reverse-proxy écoute sur les ports publics (443, et 80 uniquement si HTTP-01 est finalement retenu).
