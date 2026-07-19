import os
import hashlib
import hmac
import binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

# CFB was moved in cryptography>=43 — import from new location with fallback
try:
    from cryptography.hazmat.decrepit.ciphers.modes import CFB
except ImportError:
    from cryptography.hazmat.primitives.ciphers.modes import CFB  # type: ignore[no-redef]



# 1.9 GB in bytes to stay under Telegram 2GB limit securely
MAX_FILE_SIZE = int(1.9 * 1024 * 1024 * 1024)
CHUNK_SIZE = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Key wrapping — AES key is encrypted before DB storage using APP_SECRET_KEY
# ---------------------------------------------------------------------------

def _get_wrapping_key() -> bytes:
    """Derive a 32-byte wrapping key from APP_SECRET_KEY using SHA-256."""
    secret = os.getenv("APP_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("APP_SECRET_KEY is not set in environment variables!")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def wrap_key(aes_key: bytes) -> str:
    """
    Encrypt the AES file-key with APP_SECRET_KEY using AES-GCM.
    Returns a hex string: nonce(24 hex) + ciphertext(64 hex) + tag(32 hex)
    stored as one concatenated hex string.
    """
    wrapping_key = _get_wrapping_key()
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(wrapping_key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, aes_key, None)
    return binascii.hexlify(nonce + ciphertext_with_tag).decode("utf-8")


def unwrap_key(wrapped_hex: str) -> bytes:
    """Decrypt the wrapped key from DB back to raw AES bytes."""
    wrapping_key = _get_wrapping_key()
    raw = binascii.unhexlify(wrapped_hex)
    nonce = raw[:12]
    ciphertext_with_tag = raw[12:]
    aesgcm = AESGCM(wrapping_key)
    return aesgcm.decrypt(nonce, ciphertext_with_tag, None)


# ---------------------------------------------------------------------------
# File encryption / decryption
# ---------------------------------------------------------------------------

def encrypt_file_chunked(input_file_path: str, output_prefix: str):
    """
    Encrypt file using AES-256-CFB, split into Telegram-safe segments.
    Returns (wrapped_key_hex, segment_paths).
    """
    key = os.urandom(32)
    iv = os.urandom(16)

    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), CFB(iv), backend=backend)
    encryptor = cipher.encryptor()

    segment_index = 0
    segments = []

    def new_segment():
        nonlocal segment_index
        segment_path = f"{output_prefix}.part{segment_index}"
        segments.append(segment_path)
        out_file = open(segment_path, "wb")
        if segment_index == 0:
            out_file.write(iv)
            return out_file, len(iv)
        return out_file, 0

    current_out_file, current_size = new_segment()

    try:
        with open(input_file_path, "rb") as in_file:
            while True:
                chunk = in_file.read(CHUNK_SIZE)
                if not chunk:
                    break

                encrypted_chunk = encryptor.update(chunk)

                if current_size + len(encrypted_chunk) > MAX_FILE_SIZE:
                    current_out_file.close()
                    segment_index += 1
                    current_out_file, current_size = new_segment()

                current_out_file.write(encrypted_chunk)
                current_size += len(encrypted_chunk)

            final_chunk = encryptor.finalize()
            if final_chunk:
                if current_size + len(final_chunk) > MAX_FILE_SIZE:
                    current_out_file.close()
                    segment_index += 1
                    current_out_file, current_size = new_segment()
                current_out_file.write(final_chunk)
    finally:
        current_out_file.close()

    # Wrap the key before returning — never store raw key
    wrapped_hex = wrap_key(key)
    return wrapped_hex, segments


async def decrypt_stream_generator(client, channel_id: int, message_ids: list, wrapped_key_hex: str):
    """
    Stream-decrypt Telegram chunks back to the browser.
    Accepts wrapped_key_hex (from DB) and unwraps it internally.
    """
    key = unwrap_key(wrapped_key_hex)

    backend = default_backend()
    iv = None
    decryptor = None

    iv_buffer = bytearray()
    iv_read = False

    for msg_id in message_ids:
        msgs = await client.get_messages(channel_id, ids=[msg_id])
        msg = msgs[0] if msgs else None
        if not msg or not msg.document:
            continue

        async for chunk in client.iter_download(msg.document):
            if not iv_read:
                iv_buffer.extend(chunk)
                if len(iv_buffer) >= 16:
                    iv = bytes(iv_buffer[:16])
                    cipher = Cipher(algorithms.AES(key), CFB(iv), backend=backend)
                    decryptor = cipher.decryptor()

                    remaining_chunk = bytes(iv_buffer[16:])
                    if remaining_chunk:
                        yield decryptor.update(remaining_chunk)
                    iv_read = True
            else:
                yield decryptor.update(chunk)

    if decryptor:
        final_chunk = decryptor.finalize()
        if final_chunk:
            yield final_chunk


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: bytes = None):
    if salt is None:
        salt = os.urandom(16)

    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )
    return (
        binascii.hexlify(pwd_hash).decode("utf-8"),
        binascii.hexlify(salt).decode("utf-8"),
    )


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    salt_bytes = binascii.unhexlify(password_salt)
    expected_hash, _ = hash_password(password, salt_bytes)
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_hash, password_hash)
