"""Migration: Add reply columns and message_id to chat_media_feed."""
from db import engine, ChatFeed
from sqlalchemy import text

def run_migration():
    try:
        with engine.connect() as conn:
            # Check if message_id column exists
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='chat_media_feed' AND column_name='message_id'"
            ))
            if result.fetchone() is None:
                print("Adding message_id column...")
                conn.execute(text(
                    "ALTER TABLE chat_media_feed ADD COLUMN message_id VARCHAR DEFAULT NULL"
                ))
                # Generate UUIDs for existing rows
                conn.execute(text(
                    "UPDATE chat_media_feed SET message_id = 'msg_migrated_' || id WHERE message_id IS NULL"
                ))
                # Make it unique and not null
                conn.execute(text(
                    "ALTER TABLE chat_media_feed ALTER COLUMN message_id SET NOT NULL"
                ))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_chat_media_feed_message_id ON chat_media_feed(message_id)"
                ))
                print("message_id column added.")
            else:
                print("message_id column already exists.")
            
            # Check reply_to_message_id
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='chat_media_feed' AND column_name='reply_to_message_id'"
            ))
            if result.fetchone() is None:
                print("Adding reply_to_message_id column...")
                conn.execute(text(
                    "ALTER TABLE chat_media_feed ADD COLUMN reply_to_message_id VARCHAR DEFAULT NULL"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_media_feed_reply_to ON chat_media_feed(reply_to_message_id)"
                ))
                print("reply_to_message_id column added.")
            else:
                print("reply_to_message_id column already exists.")
            
            # Check reply_preview_text
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='chat_media_feed' AND column_name='reply_preview_text'"
            ))
            if result.fetchone() is None:
                print("Adding reply_preview_text column...")
                conn.execute(text(
                    "ALTER TABLE chat_media_feed ADD COLUMN reply_preview_text VARCHAR DEFAULT NULL"
                ))
                print("reply_preview_text column added.")
            else:
                print("reply_preview_text column already exists.")
            
            # Check reply_preview_sender
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='chat_media_feed' AND column_name='reply_preview_sender'"
            ))
            if result.fetchone() is None:
                print("Adding reply_preview_sender column...")
                conn.execute(text(
                    "ALTER TABLE chat_media_feed ADD COLUMN reply_preview_sender VARCHAR DEFAULT NULL"
                ))
                print("reply_preview_sender column added.")
            else:
                print("reply_preview_sender column already exists.")
            
            conn.commit()
            print("Migration completed successfully!")
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    run_migration()