"""Squelette du service RAD/LAD (Phase 3, cf. ../../_plan/plan.md).

Reçoit le webhook Paperless déclenché à l'ajout/modification d'un document,
récupère ce document et son texte OCR via l'API Paperless. Ne classe ni
n'extrait encore rien (Phase 4+) : ce squelette prouve seulement que le
pipeline Paperless -> RAD/LAD -> lecture OCR fonctionne de bout en bout.
"""

import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rad-lad")

PAPERLESS_BASE_URL = os.environ["PAPERLESS_BASE_URL"]
PAPERLESS_ADMIN_USER = os.environ["PAPERLESS_ADMIN_USER"]
PAPERLESS_ADMIN_PASSWORD = os.environ["PAPERLESS_ADMIN_PASSWORD"]

app = FastAPI(title="paperless-rad-lad")

_token = None


async def get_token(client: httpx.AsyncClient) -> str:
    global _token
    if _token is None:
        resp = await client.post(
            f"{PAPERLESS_BASE_URL}/api/token/",
            data={"username": PAPERLESS_ADMIN_USER, "password": PAPERLESS_ADMIN_PASSWORD},
        )
        resp.raise_for_status()
        _token = resp.json()["token"]
    return _token


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/paperless")
async def paperless_webhook(request: Request):
    payload = await request.json()
    document_id = payload.get("document_id")
    if document_id is None:
        raise HTTPException(status_code=400, detail="document_id manquant dans le payload du webhook")
    try:
        document_id = int(document_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"document_id invalide : {document_id!r}")

    async with httpx.AsyncClient() as client:
        token = await get_token(client)
        resp = await client.get(
            f"{PAPERLESS_BASE_URL}/api/documents/{document_id}/",
            headers={"Authorization": f"Token {token}"},
        )
        resp.raise_for_status()
        document = resp.json()

    content = document.get("content") or ""
    logger.info(
        "document %s reçu : titre=%r, %d caractères OCR (aperçu: %r)",
        document_id,
        document.get("title"),
        len(content),
        content[:200],
    )
    return {"received": True, "document_id": document_id, "ocr_length": len(content)}
