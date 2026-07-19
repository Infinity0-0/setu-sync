import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from tg_client import tg_app, CHANNEL_ID, _ensure_connected

logger = logging.getLogger("setu.contact")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

router = APIRouter(prefix="/api/contact", tags=["Setu Contact Form"])

# ── Request Model ─────────────────────────────────────────────────────────
class ContactPayload(BaseModel):
    name: str
    email: EmailStr
    type: str          # "Issue / Problem" | "Idea / Improvement" | "Other"
    message: str

# ── POST /api/contact ─────────────────────────────────────────────────────
@router.post("")
async def submit_contact(payload: ContactPayload, request: Request):
    """
    Receives a contact form submission and sends it to the Setu Telegram channel.
    Returns 200 on success, 500 if Telegram fails.
    """
    name = payload.name.strip()
    email = payload.email.strip()
    msg_type = payload.type.strip()
    body = payload.message.strip()

    # Quick validation
    if not name or not email or not msg_type or not body:
        return JSONResponse({"ok": False, "error": "All fields are required."}, status_code=400)
    if len(body) < 10:
        return JSONResponse({"ok": False, "error": "Message too short (min 10 chars)."}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"

    # ── Build Telegram message ────────────────────────────────────────────────
    text_body = f"""📨 **New message from Setu Bridge**
══════════════════════
👤 **Name:** {name}
📧 **Email:** {email}
🏷 **Type:** {msg_type}
🌍 **IP:** {client_ip}
──────────────────────
💬 **Message:**
{body}
"""

    # ── Send via Telegram ──────────────────────────────────────────────────
    try:
        if not tg_app or not CHANNEL_ID:
            logger.error("Telegram bot not configured. Cannot send contact form.")
            return JSONResponse(
                {"ok": False, "error": "Server notifications not configured. Please try again later."},
                status_code=500,
            )

        await _ensure_connected()
        await tg_app.send_message(CHANNEL_ID, text_body)
        logger.info(f"Contact form sent to TG: [{msg_type}] from {name} <{email}>")
        return JSONResponse({"ok": True, "message": "Message sent successfully!"})
    except Exception as exc:
        logger.error(f"Telegram send error: {exc}")
        return JSONResponse(
            {"ok": False, "error": "Could not send right now. Please try again in a moment."},
            status_code=500,
        )