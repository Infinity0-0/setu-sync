import json
import random
import string
import asyncio
import uuid
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db, ActiveRoom, ChatFeed, RoomFileMeta, UserRoomSession

logger = logging.getLogger("setu.room")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

router = APIRouter(prefix="/api/room", tags=["Setu P2P Room Engine"])

# ---------------------------------------------------------------------------
# 🛡️ Rate Limiter (simple in-memory token bucket)
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, max_per_minute: int = 10):
        self.max_per_minute = max_per_minute
        self.buckets: Dict[str, list] = {}

    def is_allowed(self, key: str) -> bool:
        now = datetime.utcnow()
        if key not in self.buckets:
            self.buckets[key] = []
        # Remove entries older than 60 seconds
        self.buckets[key] = [t for t in self.buckets[key] if now - t < timedelta(seconds=60)]
        if len(self.buckets[key]) >= self.max_per_minute:
            return False
        self.buckets[key].append(now)
        return True

rate_limiter = RateLimiter(max_per_minute=10)

# ---------------------------------------------------------------------------
# 🧠 Signaling Manager: WebSockets & The Wipeout Protocol
# ---------------------------------------------------------------------------
WIPEOUT_GRACE_SECONDS = 0  # seconds to wait before deleting an empty room (immediate wipeout)

class RoomConnectionManager:
    def __init__(self):
        # Format: { room_id: { session_id: { "socket": WebSocket, "name": str, "is_starter": bool } } }
        self.rooms: Dict[str, Dict[str, dict]] = {}
        # Pending wipeout tasks: { room_id: asyncio.Task }
        self._pending_wipeouts: Dict[str, asyncio.Task] = {}

    async def connect(self, room_id: str, session_id: str, default_name: str, is_starter: bool, websocket: WebSocket):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        
        # ✅ Cancel any pending wipeout — someone reconnected in time!
        if room_id in self._pending_wipeouts:
            self._pending_wipeouts[room_id].cancel()
            del self._pending_wipeouts[room_id]
            logger.info(f"Wipeout cancelled for room {room_id} — user reconnected.")
            
        self.rooms[room_id][session_id] = {
            "socket": websocket,
            "name": default_name,
            "is_starter": is_starter
        }
        await self.broadcast_user_list(room_id)

    async def disconnect(self, room_id: str, session_id: str, db: Session):
        if room_id in self.rooms and session_id in self.rooms[room_id]:
            del self.rooms[room_id][session_id]
            
            # 🛑 EMPTY ROOM: schedule a delayed wipeout (grace period for reconnects)
            if not self.rooms[room_id]:
                del self.rooms[room_id]
                logger.info(f"🧹 Room {room_id} empty. Scheduling wipeout in {WIPEOUT_GRACE_SECONDS}s...")
                task = asyncio.create_task(self._delayed_wipeout(room_id, db))
                self._pending_wipeouts[room_id] = task
            else:
                await self.broadcast_user_list(room_id)

    async def _delayed_wipeout(self, room_id: str, db: Session):
        """Wait for the grace period, then wipe the room if still empty."""
        try:
            await asyncio.sleep(WIPEOUT_GRACE_SECONDS)
            # Double-check room is still empty (not reconnected)
            if room_id not in self.rooms or not self.rooms[room_id]:
                logger.info(f"🧹 Grace period ended. Wiping room {room_id}...")
                self.wipeout_room_data(room_id, db)
                if room_id in self.rooms:
                    del self.rooms[room_id]
            else:
                logger.info(f"Room {room_id} has active users after grace period — wipeout skipped.")
        except asyncio.CancelledError:
            logger.info(f"Wipeout task for room {room_id} was cancelled (user rejoined).")
        finally:
            self._pending_wipeouts.pop(room_id, None)

    def wipeout_room_data(self, room_id: str, db: Session):
        """Database se us room ka poora chat aur registry record hamesha ke liye delete."""
        try:
            # Also clean up user session tracking for this room
            db.query(UserRoomSession).filter(UserRoomSession.room_id == room_id).delete()
            db.query(RoomFileMeta).filter(RoomFileMeta.room_id == room_id).delete()
            db.query(ChatFeed).filter(ChatFeed.room_id == room_id).delete()
            db.query(ActiveRoom).filter(ActiveRoom.room_id == room_id).delete()
            db.commit()
            print(f"✅ Room {room_id} completely wiped out (last user left).")
        except Exception as e:
            db.rollback()
            print(f"❌ Wipeout Error: {e}")

    async def broadcast_user_list(self, room_id: str):
        if room_id in self.rooms:
            users_data = [
                {"session_id": sid, "name": u["name"], "is_starter": u["is_starter"]}
                for sid, u in self.rooms[room_id].items()
            ]
            await self._broadcast(room_id, {"type": "user_list", "data": users_data})

    async def _broadcast(self, room_id: str, payload: dict):
        if room_id in self.rooms:
            for user in list(self.rooms[room_id].values()):
                try:
                    await user["socket"].send_json(payload)
                except Exception:
                    pass

    # 🚀 WEBRTC SIGNALING ROUTER
    async def forward_signal(self, room_id: str, target_session_id: str, payload: dict):
        if room_id in self.rooms and target_session_id in self.rooms[room_id]:
            try:
                await self.rooms[room_id][target_session_id]["socket"].send_json(payload)
            except Exception:
                pass


manager = RoomConnectionManager()

class RoomCreateRequest(BaseModel):
    session_id: str
    user_email: Optional[str] = None  # Sent by frontend from cached auth data

# ---------------------------------------------------------------------------
# 🔐 Helper: Get persistent user ID from request
# ---------------------------------------------------------------------------
async def get_persistent_user_id(request: Request, user_email_from_body: Optional[str] = None) -> Optional[str]:
    """Extract persistent user ID.
    Priority:
    1. user_email from request body (if auth header present)
    2. From Appwrite via Bearer token
    3. None (fallback to session_id)
    """
    auth_header = request.headers.get("Authorization", "")
    
    # Method 1: Frontend-sent email (fast, no external call needed)
    # Only trust if auth header is also present (proves user is authenticated)
    if user_email_from_body and auth_header.startswith("Bearer "):
        return user_email_from_body
    
    # Method 2: Try Appwrite validation
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from auth_appwrite import get_account
            user = get_account(token)
            if user and user.get("email"):
                return user["email"]
        except Exception:
            pass
    
    return None

# ---------------------------------------------------------------------------
# 🛠️ REST Endpoints
# ---------------------------------------------------------------------------

@router.post("/create")
async def create_new_room(req: RoomCreateRequest, request: Request, db: Session = Depends(get_db)):
    # 🔐 Get persistent user ID
    user_id = await get_persistent_user_id(request, req.user_email)
    
    # ⛔ CHECK 1: User already has an active room they created?
    if user_id:
        existing_owned = db.query(ActiveRoom).filter(
            ActiveRoom.starter_user_id == user_id
        ).first()
        if existing_owned:
            logger.info(f"User {user_id} already owns room {existing_owned.room_id}, returning existing")
            return {
                "status": "success", 
                "room_id": existing_owned.room_id, 
                "sync_code": existing_owned.code,
                "existing": True
            }
        
        # ⛔ CHECK 2: User already joined another room as member?
        existing_session = db.query(UserRoomSession).filter(
            UserRoomSession.user_id == user_id
        ).first()
        if existing_session:
            existing_room = db.query(ActiveRoom).filter(
                ActiveRoom.room_id == existing_session.room_id
            ).first()
            if existing_room:
                logger.warning(f"User {user_id} already in room {existing_session.room_id}")
                raise HTTPException(
                    status_code=409, 
                    detail="You are already connected to a room. Leave the current room first."
                )
            else:
                # Clean up orphaned session reference
                db.delete(existing_session)
                db.commit()
    
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"create:{client_ip}"):
        logger.warning(f"Rate limit hit for room creation from {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before creating another room.")
    
    import uuid
    room_id = f"setu-mesh-{uuid.uuid4().hex[:12]}"
    
    # 🔐 Generate a unique 8-char code — keep trying until we find one that doesn't collide
    max_attempts = 20
    eight_char_code = None
    for attempt in range(max_attempts):
        candidate = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        existing = db.query(ActiveRoom).filter(ActiveRoom.code == candidate).first()
        if not existing:
            eight_char_code = candidate
            break
    
    if not eight_char_code:
        logger.error(f"Could not generate unique room code after {max_attempts} attempts")
        raise HTTPException(status_code=500, detail="Failed to generate unique room code. Please try again.")
    
    try:
        new_room = ActiveRoom(
            room_id=room_id, 
            code=eight_char_code, 
            starter_session=req.session_id,
            starter_user_id=user_id  # Store the persistent user ID
        )
        db.add(new_room)
        db.commit()
        logger.info(f"Room created: {room_id} (code: {eight_char_code}) by user {user_id or req.session_id}")
        return {"status": "success", "room_id": room_id, "sync_code": eight_char_code}
    except Exception as e:
        db.rollback()
        logger.error(f"Room creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"DB Error: {str(e)}")


@router.post("/join")
async def join_room(request: Request, db: Session = Depends(get_db)):
    """Join a room. Multiple users allowed, sessions are cleanly upserted."""
    body = await request.json()
    code = body.get("code", "")
    session_id = body.get("session_id", "")
    
    user_id = await get_persistent_user_id(request)
    
    if not code or not session_id:
        raise HTTPException(status_code=400, detail="Missing code or session_id")
    
    room = db.query(ActiveRoom).filter(ActiveRoom.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found or expired")
    
    # Track authenticated user's session (upsert — always allow joining)
    if user_id:
        try:
            existing = db.query(UserRoomSession).filter(
                UserRoomSession.user_id == user_id
            ).first()
            if existing:
                # Update to current room (user may have switched rooms)
                existing.room_id = room.room_id
                existing.session_id = session_id
                existing.joined_at = datetime.utcnow()
            else:
                new_session = UserRoomSession(
                    user_id=user_id,
                    room_id=room.room_id,
                    session_id=session_id
                )
                db.add(new_session)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Session tracking failed (non-critical): {e}")
    
    return {
        "status": "success", 
        "room_id": room.room_id, 
        "code": room.code,
        "is_starter": (room.starter_session == session_id)
    }


@router.post("/leave")
async def leave_room(request: Request, db: Session = Depends(get_db)):
    """Remove user's session tracking when they leave a room.
    
    If the leaver is the starter, the entire room is wiped out immediately
    (chat, files, user sessions, and the room record itself).
    If the leaver is a regular member, only their session is cleaned up.
    """
    body = await request.json()
    room_id = body.get("room_id", "")
    session_id = body.get("session_id", "")
    
    user_id = await get_persistent_user_id(request)
    
    # Check if this session is the starter of this room
    room = db.query(ActiveRoom).filter(ActiveRoom.room_id == room_id).first()
    is_starter = room is not None and room.starter_session == session_id
    
    if is_starter:
        # 🧹 Starter leaving = WIPE OUT THE ENTIRE ROOM
        logger.info(f"🧹 Starter ({session_id}) leaving room {room_id} — wiping entire room")
        manager.wipeout_room_data(room_id, db)
        # Also clean in-memory WebSocket state
        if room_id in manager.rooms:
            # Close all pending websockets
            for sid, user_data in list(manager.rooms[room_id].items()):
                try:
                    await user_data["socket"].close(code=4004, reason="Room closed by starter")
                except Exception:
                    pass
            del manager.rooms[room_id]
        return {"status": "success", "room_wiped": True}
    
    # Regular member leaving — just clean up their session
    if user_id:
        existing = db.query(UserRoomSession).filter(
            UserRoomSession.user_id == user_id
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
    
    return {"status": "success"}


@router.get("/verify/{code}")
async def verify_sync_code(code: str, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"verify:{client_ip}"):
        logger.warning(f"Rate limit hit for room verify from {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    
    room = db.query(ActiveRoom).filter(ActiveRoom.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Code galat hai ya room expire ho gaya.")
    return {"status": "success", "room_id": room.room_id}

# ---------------------------------------------------------------------------
# ⚡ WebSocket Endpoint (Chat, Reply Support, WebRTC Signaling)
# ---------------------------------------------------------------------------

@router.websocket("/ws/{room_id}/{session_id}")
async def websocket_room_endpoint(websocket: WebSocket, room_id: str, session_id: str, db: Session = Depends(get_db)):
    room = db.query(ActiveRoom).filter(ActiveRoom.room_id == room_id).first()
    
    if not room:
        await websocket.accept()
        await websocket.send_json({"type": "error", "code": "room_expired", "message": "Room not found or has expired."})
        import asyncio
        try:
            # Sleep forever to prevent stale clients from reconnect looping
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        return
    
    is_starter = (room.starter_session == session_id)
    
    # ✅ Read display name from query parameter (sent by frontend)
    from urllib.parse import parse_qs
    query_params = parse_qs(websocket.url.query)
    user_name = query_params.get("name", [None])[0]
    if not user_name or not user_name.strip():
        user_name = f"Device-{session_id[:4]}"
    
    await manager.connect(room_id, session_id, user_name.strip(), is_starter, websocket)
    
    # Send existing chat history on connect (with reply metadata)
    history = db.query(ChatFeed).filter(ChatFeed.room_id == room_id).order_by(ChatFeed.id).all()
    if history:
        history_data = [{
            "message_id": h.message_id,
            "sender": h.sender_name,
            "content": h.message_body,
            "type": h.content_type,
            "reply_to_message_id": h.reply_to_message_id,
            "reply_preview_text": h.reply_preview_text,
            "reply_preview_sender": h.reply_preview_sender
        } for h in history]
        await websocket.send_json({"type": "chat_history", "data": history_data})

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            msg_type = message.get("type")

            # 1. LIVE CHAT & MEDIA HANDLING (with reply support)
            if msg_type in ["chat_text", "chat_image"]:
                current_user = manager.rooms[room_id][session_id]
                prefix = "[⭐ Starter] " if current_user["is_starter"] else ""
                sender_header = f"{prefix}{current_user['name']}"
                
                msg_id = f"msg_{uuid.uuid4().hex[:12]}"
                reply_to = message.get("reply_to_message_id")
                reply_text = None
                reply_sender = None
                
                if reply_to:
                    # Look up the original message for preview
                    original = db.query(ChatFeed).filter(ChatFeed.message_id == reply_to).first()
                    if original:
                        body = original.message_body
                        # Strip HTML tags for plain text preview
                        reply_text = re.sub(r'<[^>]+>', '', body)[:100]
                        reply_sender = original.sender_name
                    else:
                        reply_text = "Original message unavailable"
                        reply_sender = "Deleted"
                
                new_chat = ChatFeed(
                    message_id=msg_id,
                    room_id=room_id,
                    sender_name=sender_header,
                    content_type=msg_type,
                    message_body=message["content"],
                    reply_to_message_id=reply_to,
                    reply_preview_text=reply_text,
                    reply_preview_sender=reply_sender
                )
                db.add(new_chat)
                db.commit()

                await manager._broadcast(room_id, {
                    "type": "incoming_feed",
                    "message_id": msg_id,
                    "sender": sender_header,
                    "content_type": msg_type,
                    "content": message["content"],
                    "reply_to_message_id": reply_to,
                    "reply_preview_text": reply_text,
                    "reply_preview_sender": reply_sender
                })

            # 2. NAME CHANGE
            elif msg_type == "name_change":
                new_name = message["new_name"].strip()
                if new_name:
                    manager.rooms[room_id][session_id]["name"] = new_name
                    await manager.broadcast_user_list(room_id)
                    
            # 2.5 FILE SHARE & PING PONG
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif msg_type == "file_share":
                share_id = message.get("share_id")
                if share_id:
                    new_file = RoomFileMeta(
                        file_id=share_id,
                        room_id=room_id,
                        file_name=message.get("name", "Unknown File"),
                        size=message.get("size", 0),
                        uploaded_by=manager.rooms[room_id][session_id]["name"]
                    )
                    db.add(new_file)
                    db.commit()
                await manager._broadcast(room_id, message)

            # 3. WHITEBOARD SYNC (canvas-based live collab)
            elif msg_type == "whiteboard_draw":
                # Broadcast drawing actions to all other room members
                broadcast_msg = {
                    "type": "whiteboard_draw",
                    "payload": message.get("payload"),
                    "sender": session_id
                }
                # Send to everyone except sender
                if room_id in manager.rooms:
                    for sid, user in list(manager.rooms[room_id].items()):
                        if sid != session_id:
                            try:
                                await user["socket"].send_json(broadcast_msg)
                            except Exception:
                                pass

            elif msg_type == "whiteboard_sync":
                await manager._broadcast(room_id, {
                    "type": "whiteboard_sync",
                    "data": message.get("data"),
                    "sender": session_id
                })
            
            elif msg_type == "whiteboard_clear":
                await manager._broadcast(room_id, {
                    "type": "whiteboard_clear",
                    "sender": session_id
                })

            # 4. WEBRTC SIGNALING PIPELINE
            elif msg_type in ["webrtc_offer", "webrtc_answer", "webrtc_ice_candidate"]:
                target_id = message.get("target_session_id")
                if target_id:
                    signal_payload = {
                        "type": msg_type,
                        "sender_session_id": session_id,
                        "data": message.get("data")
                    }
                    await manager.forward_signal(room_id, target_id, signal_payload)

            # 5. CHAT DELETE (Unsend)
            elif msg_type == "chat_delete":
                message_id = message.get("message_id")
                if message_id:
                    # Verify the message belongs to this sender
                    current_user = manager.rooms[room_id][session_id]
                    prefix = "[⭐ Starter] " if current_user["is_starter"] else ""
                    sender_header = f"{prefix}{current_user['name']}"
                    
                    existing = db.query(ChatFeed).filter(
                        ChatFeed.message_id == message_id,
                        ChatFeed.room_id == room_id
                    ).first()
                    
                    if existing and existing.sender_name == sender_header:
                        db.delete(existing)
                        db.commit()
                        await manager._broadcast(room_id, {
                            "type": "chat_deleted",
                            "message_id": message_id
                        })

            # 6. CHAT EDIT
            elif msg_type == "chat_edit":
                message_id = message.get("message_id")
                new_content = message.get("content", "").strip()
                if message_id and new_content:
                    current_user = manager.rooms[room_id][session_id]
                    prefix = "[⭐ Starter] " if current_user["is_starter"] else ""
                    sender_header = f"{prefix}{current_user['name']}"
                    
                    existing = db.query(ChatFeed).filter(
                        ChatFeed.message_id == message_id,
                        ChatFeed.room_id == room_id
                    ).first()
                    
                    if existing and existing.sender_name == sender_header:
                        existing.message_body = new_content
                        db.commit()
                        await manager._broadcast(room_id, {
                            "type": "chat_edited",
                            "message_id": message_id,
                            "content": new_content
                        })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id} from room {room_id}")
        await manager.disconnect(room_id, session_id, db)
    except Exception as e:
        logger.error(f"WebSocket error in room {room_id} session {session_id}: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
        await manager.disconnect(room_id, session_id, db)