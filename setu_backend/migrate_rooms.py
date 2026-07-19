"""
Migrate database: add starter_user_id column to active_rooms
and create user_room_sessions table.

Run: python migrate_rooms.py
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("No DATABASE_URL in .env - using SQLite (migration not needed, auto-creates tables)")
    sys.exit(0)

url = DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

engine = create_engine(url, pool_pre_ping=True)

with engine.connect() as conn:
    # Step 1: Add starter_user_id to active_rooms
    result = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'active_rooms' AND column_name = 'starter_user_id'"
    ))
    if not result.fetchone():
        print("Adding starter_user_id column to active_rooms...")
        conn.execute(text(
            "ALTER TABLE active_rooms ADD COLUMN starter_user_id VARCHAR"
        ))
        conn.commit()
        print("[OK] starter_user_id column added!")
    else:
        print("[OK] starter_user_id column already exists.")
    
    # Step 2: Create user_room_sessions table if it doesn't exist
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables "
        "WHERE table_name = 'user_room_sessions')"
    ))
    exists = result.fetchone()[0]
    if not exists:
        print("Creating user_room_sessions table...")
        conn.execute(text("""
            CREATE TABLE user_room_sessions (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                room_id VARCHAR NOT NULL REFERENCES active_rooms(room_id) ON DELETE CASCADE,
                session_id VARCHAR NOT NULL,
                joined_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX ix_user_room_sessions_user_id 
            ON user_room_sessions (user_id)
        """))
        conn.commit()
        print("[OK] user_room_sessions table created!")
    else:
        print("[OK] user_room_sessions table already exists.")
    
    print("Migration complete!")
