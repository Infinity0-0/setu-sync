"""
Migrate active_rooms.six_digit_code to code in PostgreSQL/Supabase.
Run: python migrate_db.py
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("No DATABASE_URL in .env - nothing to migrate")
    sys.exit(0)

url = DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

engine = create_engine(url, pool_pre_ping=True)

with engine.connect() as conn:
    # Check if the old column exists
    result = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'active_rooms' AND column_name = 'six_digit_code'"
    ))
    if result.fetchone():
        print("Renaming six_digit_code -> code...")
        conn.execute(text(
            "ALTER TABLE active_rooms RENAME COLUMN six_digit_code TO code"
        ))
        conn.commit()
        print("Done! Column renamed.")
    else:
        result2 = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'active_rooms' AND column_name = 'code'"
        ))
        if result2.fetchone():
            print("Column 'code' already exists - no migration needed.")
        else:
            print("No 'six_digit_code' or 'code' column found. Creating 'code' column...")
            conn.execute(text(
                "ALTER TABLE active_rooms ADD COLUMN code VARCHAR NOT NULL DEFAULT ''"
            ))
            conn.commit()
            print("Done! Column created.")