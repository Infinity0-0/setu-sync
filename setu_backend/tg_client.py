import os
import asyncio
from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError, ChannelPrivateError
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if API_ID:
    API_ID = int(API_ID)

if CHANNEL_ID:
    CHANNEL_ID = int(CHANNEL_ID)

if API_ID and API_HASH:
    tg_app = TelegramClient(
        os.path.join(BASE_DIR, "setu_telethon_bot"),
        API_ID,
        API_HASH
    )
else:
    tg_app = None



async def _ensure_connected():
    """Start Telegram bot client if it is not already running."""
    if tg_app and not tg_app.is_connected():
        await tg_app.start(bot_token=BOT_TOKEN)


async def start_tg_client():
    """Start Telegram client and resolve the channel peer."""
    if not tg_app or not (API_ID and API_HASH and BOT_TOKEN and CHANNEL_ID):
        print("[TG] Telegram credentials are incomplete, skipping.")
        return

    await _ensure_connected()

    # Wait briefly so Pyrogram receives pending updates from Telegram
    # (e.g. "bot was added as admin to channel") — this populates the peer cache
    # in the disk session file (setu_bot.session) so channel resolves correctly
    if CHANNEL_ID:
        try:
            chat = await tg_app.get_entity(CHANNEL_ID)
            print(f"[TG] Connected to channel: {chat.title} (id={chat.id})")
        except ChannelPrivateError as e:
            print(f"[TG] WARNING: Could not resolve channel {CHANNEL_ID}: {e}")
            print("[TG] Please add the bot as an admin to your private channel first.")
        except ChatAdminRequiredError as e:
            print(f"[TG] WARNING: Bot is not an admin in channel {CHANNEL_ID}: {e}")
            print("[TG] Give the bot permission to post messages in the channel.")
        except Exception as e:
            print(f"[TG] Could not resolve channel peer: {e}")
            print("[TG] Make sure the bot is an admin in the channel.")


async def stop_tg_client():
    if tg_app and API_ID and BOT_TOKEN and tg_app.is_connected():
        await tg_app.disconnect()


async def upload_chunk(file_path: str, progress_callback=None) -> int:
    if not tg_app:
        raise RuntimeError("Telegram client is not initialized due to missing credentials.")

    await _ensure_connected()

    if not CHANNEL_ID:
        raise RuntimeError("CHANNEL_ID is not set in .env")

    try:
        msg = await asyncio.wait_for(
            tg_app.send_file(
                CHANNEL_ID,
                file_path,
                force_document=True,
                silent=True,
                progress_callback=progress_callback,
            ),
            timeout=300,  # 5-minute timeout per chunk for slower connections
        )
    except asyncio.TimeoutError:
        raise RuntimeError("Telegram upload timed out. Check bot permissions in channel.")
    except ChannelPrivateError as e:
        raise RuntimeError(
            f"Telegram channel could not be resolved ({CHANNEL_ID}). "
            "Add the bot as an admin to the private channel, then restart the app."
        ) from e
    except ChatAdminRequiredError as e:
        raise RuntimeError(
            "Telegram bot is not allowed to post in the channel. "
            "Make it an admin and enable posting messages."
        ) from e
    return msg.id


async def delete_chunks(message_ids: list):
    if not message_ids:
        return

    if not tg_app:
        return

    await _ensure_connected()

    try:
        await asyncio.wait_for(
            tg_app.delete_messages(CHANNEL_ID, message_ids),
            timeout=60,
        )
        print(f"[TG] Successfully DELETED messages {message_ids} from Telegram.")
    except asyncio.TimeoutError:
        print("[TG] delete_messages timed out — messages may not have been deleted.")
    except Exception as e:
        print(f"[TG] Error deleting messages: {e}")
