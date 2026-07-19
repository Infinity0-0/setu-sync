import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, BigInteger, Boolean, DateTime, Text, text, ForeignKey
from sqlalchemy import event
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _create_engine_safe():
    """Try Supabase first, fall back to SQLite if connection fails."""
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        try:
            eng = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
            )
            # Test connection
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("[DB] Connected to Supabase PostgreSQL")
            return eng
        except Exception as e:
            print(f"[DB] Supabase connection failed: {e}")
            print("[DB] Falling back to local SQLite database")

    # SQLite fallback
    sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_shares.db")
    eng = create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
    )
    
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if type(dbapi_connection).__module__ == "sqlite3":
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            
    print(f"[DB] Using SQLite: {sqlite_path}")
    return eng


engine = _create_engine_safe()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class FileShare(Base):
    __tablename__ = "file_shares"

    download_token = Column(String, primary_key=True, index=True)
    file_name = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=False)

    # Stored as wrapped (encrypted) hex — never raw AES key
    encryption_key_hex = Column(String, nullable=False)

    tg_message_ids = Column(Text, nullable=False, default="[]")
    password_hash = Column(String, nullable=True)
    password_salt = Column(String, nullable=True)
    is_one_time = Column(Boolean, default=False)
    expiry_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Separate token that authorises deleting/expiring this share
    # Only the uploader receives this token in the upload response
    delete_token = Column(String, nullable=True, index=True)

    def set_message_ids(self, ids_list):
        self.tg_message_ids = json.dumps(ids_list)

    def get_message_ids(self):
        try:
            return json.loads(self.tg_message_ids)
        except Exception:
            return []


class DownloadTicket(Base):
    __tablename__ = "download_tickets"

    ticket_id = Column(String, primary_key=True, index=True)
    download_token = Column(String, index=True)
    expiry_time = Column(DateTime, nullable=False)


class ActiveRoom(Base):
    __tablename__ = "active_rooms"

    room_id = Column(String, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    starter_session = Column(String, nullable=False)
    starter_user_id = Column(String, nullable=True, index=True)  # Persistent user ID (email)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


import uuid

class ChatFeed(Base):
    __tablename__ = "chat_media_feed"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(String, unique=True, index=True, nullable=False, default=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    room_id = Column(String, ForeignKey("active_rooms.room_id", ondelete="CASCADE"), index=True, nullable=False)
    sender_name = Column(String, nullable=False)
    content_type = Column(String, nullable=False)  # "text" or "image" or "file"
    message_body = Column(Text, nullable=False)
    reply_to_message_id = Column(String, nullable=True, index=True)
    reply_preview_text = Column(String, nullable=True)
    reply_preview_sender = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RoomFileMeta(Base):
    __tablename__ = "room_file_meta"

    file_id = Column(String, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("active_rooms.room_id", ondelete="CASCADE"), index=True, nullable=False)
    file_name = Column(String, nullable=False)
    size = Column(BigInteger, nullable=False)
    uploaded_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserRoomSession(Base):
    """Tracks which user is currently in which room.
    Prevents a user from joining multiple rooms simultaneously."""
    __tablename__ = "user_room_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)  # Persistent user ID (email)
    room_id = Column(String, ForeignKey("active_rooms.room_id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)


# Create tables (runs after engine is confirmed working)
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()