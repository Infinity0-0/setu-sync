import os
import json
import uuid
import shutil
import asyncio
import subprocess
import zipfile
import posixpath
import binascii
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
import websockets

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, WebSocket
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
 

from db import Base, engine, SessionLocal, get_db, FileShare, DownloadTicket, ActiveRoom, UserRoomSession, RoomFileMeta, ChatFeed
from auth_routes import router as auth_router
from setu import router as setu_router
from contact_api import router as contact_router
from crypto_utils import (
    encrypt_file_chunked,
    decrypt_stream_generator,
    hash_password,
    verify_password,
)
from tg_client import start_tg_client, stop_tg_client, upload_chunk, delete_chunks, tg_app, _ensure_connected

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# CORS — origins loaded from ALLOWED_ORIGINS env var (comma-separated)
# Example in .env:
#   ALLOWED_ORIGINS=https://setusync.space,https://www.setusync.space,http://localhost:8000
# ---------------------------------------------------------------------------
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "https://setusync.space,https://www.setusync.space,http://localhost:8000,http://127.0.0.1:8000",
)
origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Global dictionary to track Telegram upload progress
UPLOAD_PROGRESS = {}

# ---------------------------------------------------------------------------
# Background cleanup worker
# ---------------------------------------------------------------------------

async def auto_delete_worker():
    """Background loop to clean up expired shares, Telegram chunks, and orphaned rooms."""
    while True:
        try:
            # Use a fresh session — properly closed in finally block
            db = SessionLocal()
            try:
                now = datetime.utcnow()

                expired_shares = db.query(FileShare).filter(FileShare.expiry_time <= now).all()
                for share in expired_shares:
                    msg_ids = share.get_message_ids()
                    if msg_ids:
                        try:
                            await delete_chunks(msg_ids)
                        except Exception as tg_err:
                            print(f"[Cleanup] TG delete error for {share.download_token}: {tg_err}")
                    db.delete(share)

                expired_tickets = db.query(DownloadTicket).filter(DownloadTicket.expiry_time <= now).all()
                for ticket in expired_tickets:
                    db.delete(ticket)

                # 🧹 Clean up orphaned rooms: rooms older than 24 hours with no active WebSocket
                # These are rooms that were created but never joined, or abandoned without proper leave
                from setu import manager as room_manager
                orphan_cutoff = now - timedelta(hours=24)
                orphaned_rooms = db.query(ActiveRoom).filter(
                    ActiveRoom.created_at <= orphan_cutoff
                ).all()
                for room in orphaned_rooms:
                    # Only wipe if no active WebSocket connection exists
                    if room.room_id not in room_manager.rooms or not room_manager.rooms[room.room_id]:
                        print(f"[Cleanup] 🧹 Wiping orphaned room {room.room_id} (created {room.created_at})")
                        # Delete all associated data
                        db.query(UserRoomSession).filter(UserRoomSession.room_id == room.room_id).delete()
                        db.query(RoomFileMeta).filter(RoomFileMeta.room_id == room.room_id).delete()
                        db.query(ChatFeed).filter(ChatFeed.room_id == room.room_id).delete()
                        db.delete(room)

                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Auto-delete error: {e}")
            finally:
                db.close()

        except Exception as outer:
            print(f"Auto-delete outer error: {outer}")

        await asyncio.sleep(60)


# ─── Excalidraw Sync Server subprocess holder ─────────────────────────────
_sync_server_process = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sync_server_process
    # Start Excalidraw sync server (Node.js) as a subprocess
    sync_server_js = os.path.join(BASE_DIR, "whiteboard", "sync-server.js")
    try:
        _sync_server_process = subprocess.Popen(
            ["node", sync_server_js],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.join(BASE_DIR, "whiteboard"),  # ensure node resolves 'ws' from whiteboard/node_modules
        )
        # Give it a moment to start
        await asyncio.sleep(1.5)
        # Check if it's still alive
        if _sync_server_process.poll() is not None:
            stderr_out = _sync_server_process.stderr.read() if _sync_server_process.stderr else ""
            print(f"[Lifespan] ERROR: Sync server exited immediately: {stderr_out}")
        else:
            print(f"[Lifespan] OK: Excalidraw sync server started (PID {_sync_server_process.pid})")
    except Exception as e:
        print(f"[Lifespan] ERROR: Failed to start sync server: {e}")

    try:
        await asyncio.wait_for(start_tg_client(), timeout=12.0)
    except Exception as e:
        print(f"[Lifespan] WARNING: Failed to start Telegram client within timeout: {e}")
    cleaner_task = asyncio.create_task(auto_delete_worker())
    yield
    # ── Shutdown: kill sync server subprocess ────────────────────────────
    if _sync_server_process and _sync_server_process.poll() is None:
        print(f"[Lifespan] 🛑 Stopping sync server (PID {_sync_server_process.pid})...")
        _sync_server_process.terminate()
        try:
            _sync_server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _sync_server_process.kill()
            _sync_server_process.wait()
        print("[Lifespan] ✅ Sync server stopped")
    try:
        await stop_tg_client()
    except Exception as e:
        print(f"[Lifespan] WARNING: Failed to stop Telegram client: {e}")
    cleaner_task.cancel()



app = FastAPI(title="Setu Secure Sync API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Authentication Router ──────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(setu_router)
app.include_router(contact_router)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_arcname(raw_path: str, idx: int) -> str:
    """
    Sanitise a user-supplied relative path for use as a zip arcname.
    Prevents path-traversal attacks (e.g. '../../etc/passwd').
    """
    # normalise and strip any leading '/' or '..'
    safe = posixpath.normpath(raw_path.replace("\\", "/")).lstrip("/")
    # After normpath, leading '..' segments become relative — strip them again
    parts = [p for p in safe.split("/") if p and p != ".."]
    return "/".join(parts) if parts else f"file_{idx}"


def _cleanup_files(*paths: str):
    """Delete files silently, ignoring missing-file errors."""
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


class VerifyPasswordRequest(BaseModel):
    password: str


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload(
    files: List[UploadFile] = File(...),
    relative_paths: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    one_time_download: str = Form("false"),
    upload_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    # Limit total upload size to 10GB per request
    total_size = 0
    for f in files:
        f.file.seek(0, os.SEEK_END)
        total_size += f.file.tell()
        f.file.seek(0)
    
    if total_size > 10 * 1024 * 1024 * 1024:
        raise HTTPException(400, "Total upload size exceeds the 10GB limit")

    is_one_time = one_time_download.lower() == "true"
    # Alphanumeric 6-char code: 2 letters + 4 digits
    import random
    import string
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    digits = ''.join(random.choices(string.digits, k=4))
    share_id = letters + digits

    # Parse relative paths for folder structure preservation
    paths_list: list = []
    if relative_paths:
        try:
            paths_list = json.loads(relative_paths)
        except Exception:
            paths_list = []

    temp_file_path = ""
    tmp_part_files: list[str] = []          # track every temp file for cleanup
    file_name_to_save = ""
    file_size_to_save = 0

    try:
        is_single_flat_file = (len(files) == 1 and not paths_list)

        if is_single_flat_file:
            f = files[0]
            safe_name = os.path.basename(f.filename or "file")
            file_name_to_save = safe_name
            temp_file_path = os.path.join(TEMP_DIR, f"{share_id}_{safe_name}")
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
        else:
            # Multiple files OR folder upload — zip everything
            if paths_list:
                top_folder = paths_list[0].split("/")[0] if "/" in paths_list[0] else "folder"
                file_name_to_save = f"{top_folder}_{share_id}.zip"
            else:
                file_name_to_save = f"sync_files_{share_id}.zip"

            temp_file_path = os.path.join(TEMP_DIR, file_name_to_save)
            with zipfile.ZipFile(temp_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for idx, f in enumerate(files):
                    # ✅ Sanitise arcname — prevents path-traversal
                    if paths_list and idx < len(paths_list):
                        arcname = _safe_arcname(paths_list[idx], idx)
                    else:
                        arcname = os.path.basename(f.filename or f"file_{idx}")

                    tmp_path = os.path.join(TEMP_DIR, f"tmp_{uuid.uuid4().hex}")
                    tmp_part_files.append(tmp_path)
                    with open(tmp_path, "wb") as buf:
                        shutil.copyfileobj(f.file, buf)
                    zipf.write(tmp_path, arcname=arcname)
                    # Remove immediately after adding to zip
                    _cleanup_files(tmp_path)

        file_size_to_save = os.path.getsize(temp_file_path)

        output_prefix = os.path.join(TEMP_DIR, f"enc_{share_id}")
        # ✅ encrypt_file_chunked now returns wrapped_key_hex (encrypted key)
        wrapped_key_hex, segment_paths = encrypt_file_chunked(temp_file_path, output_prefix)

        # Pyrogram progress callback
        async def tg_progress(current, total):
            if upload_id and total > 0:
                percent = int((current / total) * 100)
                UPLOAD_PROGRESS[upload_id] = percent

        msg_ids = []
        for segment in segment_paths:
            try:
                msg_id = await upload_chunk(segment, progress_callback=tg_progress)
                msg_ids.append(msg_id)
            finally:
                _cleanup_files(segment)   # ✅ always cleaned up

        _cleanup_files(temp_file_path)

        # Clean up the progress dictionary
        if upload_id in UPLOAD_PROGRESS:
            del UPLOAD_PROGRESS[upload_id]

        pwd_hash = None
        pwd_salt = None
        if password:
            pwd_hash, pwd_salt = hash_password(password)

        expiry = datetime.utcnow() + timedelta(minutes=7)
        delete_token = uuid.uuid4().hex     # ✅ secret token for expire endpoint

        new_share = FileShare(
            download_token=share_id,
            file_name=file_name_to_save,
            file_size=file_size_to_save,
            encryption_key_hex=wrapped_key_hex,   # ✅ encrypted, not raw
            password_hash=pwd_hash,
            password_salt=pwd_salt,
            is_one_time=is_one_time,
            expiry_time=expiry,
            delete_token=delete_token,
        )
        new_share.set_message_ids(msg_ids)
        db.add(new_share)
        db.commit()

        return {
            "share_id": share_id,
            "delete_token": delete_token,          # ✅ returned only once at upload
            "password_protected": bool(password),
            "one_time_download": is_one_time,
            "files": [{"saved_as": file_name_to_save, "size": file_size_to_save}],
        }

    except Exception as e:
        # ✅ Thorough cleanup on failure
        _cleanup_files(temp_file_path, *tmp_part_files)
        raise HTTPException(500, f"Upload failed: {str(e)}")


# ---------------------------------------------------------------------------
# Share info & Progress
# ---------------------------------------------------------------------------

@app.get("/api/progress/{upload_id}")
def get_progress(upload_id: str):
    percent = UPLOAD_PROGRESS.get(upload_id, 0)
    return {"status": "telegram", "percent": percent}

@app.get("/api/share/{token}")
async def get_share_info(token: str, db: Session = Depends(get_db)):
    share = db.query(FileShare).filter(FileShare.download_token == token).first()
    if not share or share.expiry_time <= datetime.utcnow():
        raise HTTPException(404, "Share not found or expired")

    is_protected = bool(share.password_hash)

    return {
        "share_id": share.download_token,
        "password_protected": is_protected,
        "one_time_download": share.is_one_time,
        "expiry_time": share.expiry_time.isoformat() + "Z",
        "file_name": "Protected File" if is_protected else share.file_name,
        "file_size": 0 if is_protected else share.file_size,
    }


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------

@app.post("/api/verify-password/{token}")
async def verify_pass(token: str, req: VerifyPasswordRequest, db: Session = Depends(get_db)):
    share = db.query(FileShare).filter(FileShare.download_token == token).first()
    if not share or share.expiry_time <= datetime.utcnow():
        raise HTTPException(404, "Share not found or expired")

    if not share.password_hash:
        raise HTTPException(400, "Share is not password protected")

    if not verify_password(req.password, share.password_hash, share.password_salt):
        raise HTTPException(403, "Incorrect password")

    ticket_id = uuid.uuid4().hex
    ticket = DownloadTicket(
        ticket_id=ticket_id,
        download_token=token,
        expiry_time=datetime.utcnow() + timedelta(minutes=5),  # ✅ was 30s — too short
    )
    db.add(ticket)
    db.commit()

    return {"ticket": ticket_id, "file_name": share.file_name, "file_size": share.file_size}


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

@app.get("/download/{token}")
async def download_file(token: str, ticket: Optional[str] = None, db: Session = Depends(get_db)):
    share = db.query(FileShare).filter(FileShare.download_token == token).first()
    if not share or share.expiry_time <= datetime.utcnow():
        raise HTTPException(404, "Share not found or expired")

    if share.password_hash:
        if not ticket:
            raise HTTPException(403, "Ticket required for password protected files")

        db_ticket = db.query(DownloadTicket).filter(
            DownloadTicket.ticket_id == ticket,
            DownloadTicket.download_token == token,
        ).first()

        if not db_ticket or db_ticket.expiry_time <= datetime.utcnow():
            if db_ticket:
                db.delete(db_ticket)
                db.commit()
            raise HTTPException(403, "Invalid or expired download ticket")

        db.delete(db_ticket)
        db.commit()

    msg_ids = share.get_message_ids()[:]  # copy list
    wrapped_key_hex = share.encryption_key_hex
    file_name = share.file_name

    if share.is_one_time:
        # Delete DB record FIRST, then cleanup TG async
        db.delete(share)
        db.commit()
        asyncio.create_task(delete_chunks(msg_ids))
        # Return empty stream for one-time
        async def empty_gen():
            yield b""
        return StreamingResponse(
            empty_gen(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )

    channel_id = int(os.getenv("CHANNEL_ID"))

    # ✅ Ensure Telegram client is connected before streaming download
    try:
        await _ensure_connected()
    except Exception as e:
        raise HTTPException(503, f"Telegram client unavailable: {e}")

    return StreamingResponse(
        decrypt_stream_generator(tg_app, channel_id, msg_ids, wrapped_key_hex),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


# ---------------------------------------------------------------------------
# Expire share — requires delete_token (only uploader has it)
# ---------------------------------------------------------------------------

@app.post("/api/expire/{token}")
async def expire_share(token: str, delete_token: str, db: Session = Depends(get_db)):
    """
    Expire a share early. Caller must supply the delete_token that was
    returned at upload time — prevents anyone else from deleting shares.
    """
    share = db.query(FileShare).filter(FileShare.download_token == token).first()

    if not share:
        return {"status": "not_found"}

    # ✅ Validate ownership via delete_token
    if share.delete_token != delete_token:
        raise HTTPException(403, "Invalid delete token")

    msg_ids = share.get_message_ids()
    db.delete(share)
    db.commit()

    if msg_ids:
        asyncio.create_task(delete_chunks(msg_ids))

    return {"status": "success"}


# ---------------------------------------------------------------------------
# Share redirect & static files
# ---------------------------------------------------------------------------

# FRONTEND_URL is read once at startup — set it in your .env file
_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://setusync.space")

@app.get("/")
async def root_redirect(code: Optional[str] = None):
    if code:
        return RedirectResponse(url=f"{_FRONTEND_URL}/?code={code}")
    return RedirectResponse(url=_FRONTEND_URL)

@app.get("/share/{share_id}")
async def share_redirect(share_id: str):
    return RedirectResponse(url=f"{_FRONTEND_URL}/?code={share_id}")


# ---------------------------------------------------------------------------
# Excalidraw Collab Sync — WebSocket Proxy
# Proxies /api/excalidraw/sync/{room_id} → ws://localhost:5858/{room_id}
# The sync-server.js (Node.js) must be running on port 5858
# ---------------------------------------------------------------------------

import re as _re

WB_SYNC_PORT     = int(os.getenv("TLDRAW_SYNC_PORT", "5858"))  # keep env-var name for compat
WB_MAX_MSG_BYTES = 512 * 1024  # 512 KB — drop oversized messages at the proxy level
_SAFE_ROOM_RE    = _re.compile(r'^[a-zA-Z0-9_\-]{1,128}$')

@app.websocket("/api/excalidraw/sync/{room_id}")
async def excalidraw_sync_proxy(websocket: WebSocket, room_id: str):
    # ── Validate room_id to prevent path-traversal / SSRF ─────────────────
    if not _SAFE_ROOM_RE.match(room_id):
        await websocket.close(1008, "Invalid room_id")
        return

    await websocket.accept()
    raw_session = websocket.query_params.get("sessionId", f"s-{uuid.uuid4().hex[:8]}")
    # Sanitise session_id before embedding in URL
    session_id  = raw_session[:64] if _SAFE_ROOM_RE.match(raw_session) else f"s-{uuid.uuid4().hex[:8]}"
    raw_name    = websocket.query_params.get("name", "User")[:64]
    target_uri  = (
        f"ws://localhost:{WB_SYNC_PORT}/{room_id}"
        f"?sessionId={session_id}&name={raw_name}"
    )

    try:
        async with websockets.connect(target_uri) as backend_ws:

            async def client_to_backend():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if "text" in msg and msg["text"] is not None:
                            if len(msg["text"]) <= WB_MAX_MSG_BYTES:
                                await backend_ws.send(msg["text"])
                        elif "bytes" in msg and msg["bytes"] is not None:
                            if len(msg["bytes"]) <= WB_MAX_MSG_BYTES:
                                await backend_ws.send(msg["bytes"])
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    print(f"[wb-proxy] client→backend error room={room_id}: {e}")

            async def backend_to_client():
                try:
                    async for msg in backend_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except Exception as e:
                    print(f"[wb-proxy] backend→client error room={room_id}: {e}")

            tasks = [
                asyncio.create_task(client_to_backend()),
                asyncio.create_task(backend_to_client()),
            ]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    except (ConnectionRefusedError, OSError):
        print(f"[wb-proxy] ⚠ Sync server not running on port {WB_SYNC_PORT}. Attempting to start it automatically...")
        # ── Attempt to start sync server as fallback ────────────────────────
        try:
            sync_server_js = os.path.join(BASE_DIR, "whiteboard", "sync-server.js")
            subprocess.Popen(
                ["node", sync_server_js],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.join(BASE_DIR, "whiteboard"),
            )
            # Wait up to 3 seconds for it to come up, then retry once
            for i in range(6):
                await asyncio.sleep(0.5)
                try:
                    async with websockets.connect(target_uri) as backend_ws2:
                        # Re-run the relay loop inline (same logic as above)
                        async def c2b():
                            try:
                                while True:
                                    msg = await websocket.receive()
                                    if msg.get("type") == "websocket.disconnect":
                                        break
                                    if "text" in msg and msg["text"] is not None:
                                        if len(msg["text"]) <= WB_MAX_MSG_BYTES:
                                            await backend_ws2.send(msg["text"])
                                    elif "bytes" in msg and msg["bytes"] is not None:
                                        if len(msg["bytes"]) <= WB_MAX_MSG_BYTES:
                                            await backend_ws2.send(msg["bytes"])
                            except WebSocketDisconnect:
                                pass
                            except Exception as e:
                                print(f"[wb-proxy] c2b error after auto-start: {e}")
                        async def b2c():
                            try:
                                async for msg in backend_ws2:
                                    if isinstance(msg, str):
                                        await websocket.send_text(msg)
                                    else:
                                        await websocket.send_bytes(msg)
                            except Exception as e:
                                print(f"[wb-proxy] b2c error after auto-start: {e}")
                        tasks2 = [asyncio.create_task(c2b()), asyncio.create_task(b2c())]
                        _, pending2 = await asyncio.wait(tasks2, return_when=asyncio.FIRST_COMPLETED)
                        for t in pending2:
                            t.cancel()
                            try:
                                await t
                            except asyncio.CancelledError:
                                pass
                        print(f"[wb-proxy] ✅ Auto-started sync server and connected successfully")
                        return
                except (ConnectionRefusedError, OSError):
                    continue
            # If we get here, auto-start failed
            print(f"[wb-proxy] ❌ Failed to auto-start sync server on port {WB_SYNC_PORT}")
            await websocket.close(1011, "Sync server unavailable")
        except Exception as auto_err:
            print(f"[wb-proxy] ❌ Error during auto-start fallback: {auto_err}")
            await websocket.close(1011, "Sync server unavailable")
    except Exception as e:
        print(f"[wb-proxy] Proxy error room={room_id}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


# Mount whiteboard build output FIRST so it takes priority over root static
import os
wb_dir = os.path.join(BASE_DIR, "whiteboard", "dist")
os.makedirs(wb_dir, exist_ok=True)
app.mount("/whiteboard", StaticFiles(directory=wb_dir, html=True), name="whiteboard")

# SECURITY FIX: The root static mount has been removed as it exposed the entire backend directory.
# If you are hosting the frontend separately (e.g., Cloudflare Pages), this is not needed.
# app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")
