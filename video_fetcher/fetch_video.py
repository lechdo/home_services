#!/usr/bin/env python3
"""Reconstitue une vidéo à partir d'une URL de ping JWPlayer (ping.gif) fournie manuellement.

Usage:
    fetch_video.py --ping "<url_du_ping.gif>" [--page "<url_de_la_page>"] [--title "<titre_manuel>"] [--out DIR]

- --ping    : URL complète du ping.gif capturée dans l'onglet Network (contient mu/pu).
- --page    : URL de la page d'origine, utilisée pour extraire le titre via .film-detail-title.
- --title   : force le titre du fichier de sortie (prioritaire sur --page).
- --out     : dossier de sortie (défaut: dossier courant).
- --referer : force le domaine Referer/Origin (défaut: déduit du domaine du manifest).

Note : si `ffmpeg` est installé en snap, il est confiné par AppArmor et ne peut
lire/écrire que dans certains répertoires (typiquement $HOME et ses sous-dossiers).
Utilise --out avec un chemin sous $HOME, pas /tmp, sous peine de "Permission
denied"/"No such file or directory" trompeurs.
"""

import argparse
import html
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TITLE_CLASS_RE = re.compile(
    r'<div[^>]*class="[^"]*\bfilm-detail-title\b[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")


def parse_ping(ping_url: str) -> dict:
    query = ping_url.split("?", 1)[1] if "?" in ping_url else ping_url
    params = parse_qs(query)

    def first(key):
        values = params.get(key)
        return unquote(values[0]) if values else None

    return {
        "manifest_url": first("mu"),
        "embed_referer": first("pu"),
    }


def cdn_root_domain(url: str) -> str:
    """Domaine racine (2 derniers labels) du host, ex: share31121.sharecloudy.com -> sharecloudy.com.

    Heuristique : le lecteur tourne souvent dans une iframe hébergée sur le CDN
    lui-même (sous-domaine d'edge variable), et c'est CE domaine, pas celui du
    site embarqueur, qu'il faut utiliser comme Origin/Referer pour passer les
    règles anti-hotlink (cf. Cloudflare 'sec-fetch-site: same-site').
    """
    host = urlparse(url).hostname or ""
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def sanitize_filename(name: str) -> str:
    name = html.unescape(name).strip()
    name = re.sub(r'[\\/:*?"<>|]+', "", name)
    name = re.sub(r"\s+", " ", name)
    return name[:150] if name else "video"


def fetch_title(page_url: str) -> str | None:
    req = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
    except Exception as exc:
        print(f"Avertissement : impossible de récupérer la page ({exc})", file=sys.stderr)
        return None

    match = TITLE_CLASS_RE.search(body)
    if not match:
        print("Avertissement : div .film-detail-title introuvable dans la page.", file=sys.stderr)
        return None

    text = TAG_RE.sub("", match.group(1))
    return sanitize_filename(text)


def run_ffmpeg(manifest_url: str, referer: str, origin: str, output_file: Path):
    headers = (
        f"Referer: {referer}\r\n"
        f"Origin: {origin}\r\n"
        f"User-Agent: {USER_AGENT}\r\n"
    )
    args = ["ffmpeg", "-headers", headers, "-i", manifest_url, "-c", "copy", str(output_file)]

    print("\n$ " + " ".join(args) + "\n")
    result = subprocess.run(args)
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg a échoué (code {result.returncode})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ping", required=True, help="URL complète du ping.gif")
    parser.add_argument("--page", help="URL de la page d'origine (pour le titre)")
    parser.add_argument("--title", help="Force le titre du fichier de sortie")
    parser.add_argument("--out", default=".", help="Dossier de sortie")
    parser.add_argument(
        "--referer",
        help="Force le Referer/Origin à utiliser (par défaut: domaine racine du CDN, déduit de l'URL du manifest)",
    )
    args = parser.parse_args()

    info = parse_ping(args.ping)
    if not info["manifest_url"]:
        raise SystemExit("Erreur : paramètre 'mu' introuvable dans l'URL du ping fournie.")

    domain = args.referer or cdn_root_domain(info["manifest_url"])
    referer = f"https://{domain}/"
    origin = f"https://{domain}"

    print(f"Manifest      : {info['manifest_url']}")
    print(f"Page (pu)     : {info['embed_referer']} (non utilisé — voir CDN root ci-dessous)")
    print(f"Referer/Origin: {referer}")

    title = None
    if args.title:
        title = sanitize_filename(args.title)
    elif args.page:
        title = fetch_title(args.page)

    title = title or "video"
    print(f"Titre    : {title}")

    output_file = Path(args.out) / f"{title}.mp4"
    run_ffmpeg(info["manifest_url"], referer, origin, output_file)
    print(f"\nTerminé : {output_file}")


if __name__ == "__main__":
    main()
