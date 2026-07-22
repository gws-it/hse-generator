import os
import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from models import User
from auth import get_current_user

router = APIRouter(prefix="/api/photobot", tags=["photobot"])

PHOTOBOT_API_URL = os.getenv("PHOTOBOT_API_URL", "").rstrip("/")
PHOTOBOT_API_TOKEN = os.getenv("PHOTOBOT_API_TOKEN", "")


def _headers():
    return {"Authorization": f"Bearer {PHOTOBOT_API_TOKEN}"}


def _require_configured():
    if not PHOTOBOT_API_URL:
        raise HTTPException(503, "Photo bot is not configured (set PHOTOBOT_API_URL / PHOTOBOT_API_TOKEN)")


@router.get("/status")
def photobot_status(current_user: User = Depends(get_current_user)):
    """Server-side proxy to the bot's /status — keeps PHOTOBOT_API_TOKEN off the browser."""
    _require_configured()
    try:
        resp = requests.get(f"{PHOTOBOT_API_URL}/status", headers=_headers(), timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Photo bot unreachable: {e}")
    return resp.json()


@router.post("/reconnect")
def photobot_reconnect(current_user: User = Depends(get_current_user)):
    """Server-side proxy to the bot's /reconnect."""
    _require_configured()
    try:
        resp = requests.post(f"{PHOTOBOT_API_URL}/reconnect", headers=_headers(), timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Photo bot unreachable: {e}")
    return resp.json()


@router.get("/qr")
def photobot_qr(current_user: User = Depends(get_current_user)):
    """Server-side proxy to the bot's /qr — streams the current QR PNG through."""
    _require_configured()
    try:
        resp = requests.get(f"{PHOTOBOT_API_URL}/qr", headers=_headers(), timeout=10)
        if resp.status_code == 404:
            raise HTTPException(404, "No fresh QR code available")
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(502, f"Photo bot unreachable: {e}")
    return StreamingResponse(iter([resp.content]), media_type="image/png")
