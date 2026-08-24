#!/usr/bin/env node
/**
 * Usage : node fetch.js "<url_de_la_page>" [dossier_sortie]
 *
 * 1. Ouvre la page dans Chrome headless.
 * 2. Déclenche la lecture pour forcer le ping JWPlayer (ping.gif).
 * 3. Extrait l'URL du manifest HLS (param `mu`) et le referer (param `pu`).
 * 4. Récupère le titre depuis .film-detail-title.
 * 5. Lance ffmpeg pour télécharger la vidéo sous ce titre.
 */

const puppeteer = require("puppeteer-core");
const { spawn } = require("child_process");
const path = require("path");

const CHROME_PATH = "/usr/bin/google-chrome";
const PING_PATTERN = /ping\.gif\?/;
const PING_TIMEOUT_MS = 40000;
const RETRIGGER_INTERVAL_MS = 2000;

function sanitizeFilename(name) {
  return name
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "")
    .replace(/\s+/g, " ")
    .slice(0, 150);
}

function parsePing(url) {
  const query = url.split("?", 2)[1] || "";
  const params = new URLSearchParams(query);
  return {
    manifestUrl: params.get("mu") ? decodeURIComponent(params.get("mu")) : null,
    embedPageUrl: params.get("pu") ? decodeURIComponent(params.get("pu")) : null,
  };
}

// Le lecteur tourne dans une iframe hébergée sur le domaine du CDN lui-même
// (cf. sec-fetch-site: same-site observé) : c'est CE domaine, pas celui de la
// page conteneur (pu), qu'il faut utiliser comme Origin/Referer pour le
// téléchargement — sinon Cloudflare bloque en 403.
function cdnRootDomain(url) {
  const host = new URL(url).hostname;
  const labels = host.split(".");
  return labels.slice(-2).join(".");
}

async function waitForPingWithManifest(page, onEachPing) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      page.off("request", onRequest);
      reject(new Error(`Timeout : aucun ping.gif avec 'mu' capté après ${PING_TIMEOUT_MS}ms`));
    }, PING_TIMEOUT_MS);

    function onRequest(request) {
      const url = request.url();
      if (PING_PATTERN.test(url)) {
        onEachPing(url);
        if (/[?&]mu=/.test(url)) {
          clearTimeout(timer);
          page.off("request", onRequest);
          resolve(url);
        }
      }
    }

    page.on("request", onRequest);
  });
}

async function findVideoFrame(page) {
  for (const frame of page.frames()) {
    try {
      const hasVideo = await frame.$(".jw-video, video");
      if (hasVideo) return frame;
    } catch (_) {
      // frame détachée ou cross-origin non accessible, on continue
    }
  }
  return null;
}

async function tryTriggerPlayback(page) {
  // 1. API JWPlayer directe (la plus fiable : passe par le vrai state machine
  //    du lecteur, ce qui déclenche les événements d'analytics attendus).
  await page.evaluate(() => {
    try {
      if (typeof window.jwplayer === "function") {
        const instances = window.jwplayer().getPlaylist ? [window.jwplayer()] : [];
        // jwplayer() sans argument renvoie souvent la dernière instance créée.
        window.jwplayer().play(true);
      }
    } catch (_) {}
  });

  // 2. Clics "réels" (dispatchés via CDP, donc considérés comme un vrai geste
  //    utilisateur) sur les éléments d'UI probables du lecteur.
  const selectors = [
    ".jw-icon-display[aria-label='Play']",
    ".jw-icon-display",
    "[role='button'][aria-label='Play']",
    ".jw-video",
    ".jwplayer",
    "video",
  ];
  for (const selector of selectors) {
    const el = await page.$(selector);
    if (el) {
      try {
        await el.click({ delay: 50 });
      } catch (_) {
        // certains éléments ne sont pas cliquables directement, on continue
      }
    }
  }

  // 3. Fallback : lecture programmatique directe de la balise <video>.
  await page.evaluate(() => {
    document.querySelectorAll("video").forEach((v) => {
      v.muted = true;
      v.play().catch(() => {});
    });
  });
}

async function extractTitle(page) {
  try {
    const title = await page.$eval(".film-detail-title", (el) => el.textContent);
    return sanitizeFilename(title) || "video";
  } catch (_) {
    return "video";
  }
}

function runFfmpeg(manifestUrl, referer, origin, outputFile) {
  const headers = `Referer: ${referer}\r\nOrigin: ${origin}\r\n`;
  const args = ["-headers", headers, "-i", manifestUrl, "-c", "copy", outputFile];

  console.log(`\n$ ffmpeg ${args.join(" ")}\n`);

  return new Promise((resolve, reject) => {
    const proc = spawn("ffmpeg", args, { stdio: "inherit" });
    proc.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`ffmpeg a terminé avec le code ${code}`));
    });
  });
}

async function main() {
  const pageUrl = process.argv[2];
  const outDir = process.argv[3] || ".";

  if (!pageUrl) {
    console.error("Usage: node fetch.js <url_de_la_page> [dossier_sortie]");
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--autoplay-policy=no-user-gesture-required"],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800 });

    let seenCount = 0;
    const pingPromise = waitForPingWithManifest(page, (url) => {
      seenCount += 1;
      console.log(`  ping #${seenCount} (sans manifest) : ${url.split("?")[1]?.slice(0, 60)}...`);
    });

    console.log(`Chargement de ${pageUrl} ...`);
    await page.goto(pageUrl, { waitUntil: "domcontentloaded", timeout: 30000 });

    // Relance périodiquement la tentative de lecture pendant qu'on attend le ping
    // contenant le manifest (le premier ping est souvent un simple "setup").
    // Le lecteur vit typiquement dans une iframe cross-origin (le <video> a un
    // src blob: sur le domaine du CDN) : il faut cibler cette frame précise,
    // pas le document principal.
    const retrigger = setInterval(() => {
      findVideoFrame(page)
        .then((frame) => tryTriggerPlayback(frame || page.mainFrame()))
        .catch(() => {});
    }, RETRIGGER_INTERVAL_MS);

    let pingUrl;
    try {
      pingUrl = await pingPromise;
    } finally {
      clearInterval(retrigger);
    }
    console.log(`Ping avec manifest capté : ${pingUrl}`);

    const { manifestUrl, embedPageUrl } = parsePing(pingUrl);
    if (!manifestUrl) {
      throw new Error("Paramètre 'mu' introuvable dans le ping capté.");
    }
    const domain = cdnRootDomain(manifestUrl);
    const referer = `https://${domain}/`;
    const origin = `https://${domain}`;
    console.log(`Manifest      : ${manifestUrl}`);
    console.log(`Page (pu)     : ${embedPageUrl} (non utilisé pour le téléchargement)`);
    console.log(`Referer/Origin: ${referer}`);

    const title = await extractTitle(page);
    console.log(`Titre    : ${title}`);

    const outputFile = path.join(outDir, `${title}.mp4`);
    await runFfmpeg(manifestUrl, referer, origin, outputFile);

    console.log(`\nTerminé : ${outputFile}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error("Erreur :", err.message);
  process.exit(1);
});
