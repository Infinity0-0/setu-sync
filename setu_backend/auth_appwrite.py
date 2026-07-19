"""
auth_appwrite.py — Appwrite Authentication Client (Backend)

PURPOSE:
    This module handles all Appwrite authentication operations on the server side.
    It uses the Appwrite server SDK to communicate with the Appwrite cloud API.
    No Appwrite SDK runs on the frontend — all auth logic stays here.

FILES INVOLVED:
    - .env                → APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY
    - auth_routes.py      → imports functions from here and exposes FastAPI endpoints
    - main.py             -> mounts auth_routes.py as a sub-router

HOW TO ADD NEW AUTH FEATURES:
    1. Add a new function here (e.g. verify_email(user_id))
    2. Add a new endpoint in auth_routes.py
    3. Done — the frontend just calls the new endpoint.

USAGE:
    from auth_appwrite import create_account, login_account, ... 
"""

import os
import json
import logging
from typing import Optional
from datetime import datetime, timedelta

import requests

logger = logging.getLogger("auth_appwrite")

# ---------------------------------------------------------------------------
# Appwrite SDK is NOT directly used because of compatibility.
# Instead we call the Appwrite REST API directly via `requests`.
# This is cleaner, more reliable, and easier to debug.
# ---------------------------------------------------------------------------

ENDPOINT  = os.getenv("APPWRITE_ENDPOINT", "https://sgp.cloud.appwrite.io/v1")
PROJECT   = os.getenv("APPWRITE_PROJECT_ID", "")
API_KEY   = os.getenv("APPWRITE_API_KEY", "")

if not PROJECT or not API_KEY:
    logger.warning("APPWRITE_PROJECT_ID or APPWRITE_API_KEY is missing in .env")

# Timeout for all Appwrite REST calls (seconds) — prevents hung requests
_TIMEOUT = 20

# ---------------------------------------------------------------------------
# Headers for server-side API calls (uses API Key — full access)
# ---------------------------------------------------------------------------
def _headers(session_token: Optional[str] = None) -> dict:
    h = {
        "X-Appwrite-Project": PROJECT,
        "Content-Type": "application/json",
    }
    # For user-context operations (account, prefs), use session token.
    # For server-only operations (creating account, DB), use API KEY.
    if session_token:
        h["X-Appwrite-Session"] = session_token
    elif API_KEY:
        h["X-Appwrite-Key"] = API_KEY
    return h

# ---------------------------------------------------------------------------
# ─── ACCOUNT APIs ─────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def create_account(
    email: str,
    password: str,
    name: str,
) -> dict:
    """
    Register a new user account on Appwrite.

    Returns:
        {"success": True, "user_id": "...", "email": "...", "name": "..."}
        OR {"success": False, "error": "reason"}
    """
    url = f"{ENDPOINT}/account"
    payload = {
        "userId": "unique()",       # Let Appwrite generate a unique ID
        "email": email,
        "password": password,
        "name": name,
    }
    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code in (201, 200):
            return {
                "success": True,
                "user_id": data.get("$id", data.get("_id", "")),
                "email": data.get("email", email),
                "name": data.get("name", name),
            }
        else:
            error_msg = data.get("message", data.get("error", str(data)))
            logger.warning(f"Appwrite create_account failed: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite create_account network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def login_account(email: str, password: str) -> dict:
    """
    Create an email/password session (login).

    Returns:
        {"success": True, "session_token": "...", "user_id": "...", "email": "...", "name": "..."}
        OR {"success": False, "error": "reason"}
    """
    url = f"{ENDPOINT}/account/sessions/email"
    payload = {
        "email": email,
        "password": password,
    }
    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code in (201, 200):
            # ─── CORRECT WAY: When called server-side with an API Key,
            # Appwrite returns the session secret directly in the JSON body
            # under the key "secret". This is the session token.
            # Cookies / X-Fallback-Cookies are only set for browser clients.
            session_token = data.get("secret", "")

            # Fallback to X-Fallback-Cookies if secret is empty (older Appwrite)
            if not session_token:
                fallback = resp.headers.get("X-Fallback-Cookies", "{}")
                try:
                    fallback_dict = json.loads(fallback)
                    for k, v in fallback_dict.items():
                        if k.startswith("a_session_") and not k.endswith("_legacy"):
                            session_token = v
                            break
                except Exception:
                    pass

            # Fallback to response cookies
            if not session_token:
                for k, v in resp.cookies.get_dict().items():
                    if k.startswith("a_session_") and not k.endswith("_legacy"):
                        session_token = v
                        break

            logger.info(f"Appwrite login: session_token extracted (len={len(session_token)})")

            return {
                "success": True,
                "session_token": session_token,
                "user_id": data.get("userId", ""),
                "email": data.get("providerUid", email),
                "name": "",  # session response has no name; fetched separately
                "session_id": data.get("$id", ""),
                "expire": data.get("expire", ""),
            }
        else:
            error_msg = data.get("message", data.get("error", str(data)))
            logger.warning(f"Appwrite login_account failed: {error_msg}")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite login_account network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def get_account(session_token: str) -> dict:
    """
    Get the currently logged-in user's account details.

    Returns:
        {"success": True, "user_id": "...", "email": "...", "name": "..."}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account"
    try:
        resp = requests.get(url, headers=_headers(session_token), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code == 200:
            return {
                "success": True,
                "user_id": data.get("$id", ""),
                "email": data.get("email", ""),
                "name": data.get("name", ""),
            }
        else:
            error_msg = data.get("message", data.get("error", str(data)))
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite get_account network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def delete_session(session_token: str) -> dict:
    """
    Log out (delete the current session).

    Returns:
        {"success": True}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account/sessions/current"
    try:
        resp = requests.delete(url, headers=_headers(session_token), timeout=_TIMEOUT)
        if resp.status_code == 204:
            return {"success": True}
        else:
            data = resp.json()
            error_msg = data.get("message", data.get("error", str(data)))
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite delete_session network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def update_account_name(session_token: str, name: str) -> dict:
    """
    Update the logged-in user's display name.

    Returns:
        {"success": True, "name": "..."}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account/name"
    payload = {"name": name}
    try:
        resp = requests.patch(url, json=payload, headers=_headers(session_token), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code == 200:
            return {"success": True, "name": data.get("name", name)}
        else:
            error_msg = data.get("message", data.get("error", str(data)))
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite update_name network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def update_account_password(session_token: str, old_password: str, new_password: str) -> dict:
    """
    Change the logged-in user's password.

    Returns:
        {"success": True}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account/password"
    payload = {
        "oldPassword": old_password,
        "newPassword": new_password,
    }
    try:
        resp = requests.patch(url, json=payload, headers=_headers(session_token), timeout=_TIMEOUT)
        if resp.status_code == 204:
            return {"success": True}
        else:
            data = resp.json()
            error_msg = data.get("message", data.get("error", str(data)))
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite update_password network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def delete_account(session_token: str) -> dict:
    """
    Delete the logged-in user's account permanently.

    Returns:
        {"success": True}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account"
    try:
        resp = requests.delete(url, headers=_headers(session_token), timeout=_TIMEOUT)
        if resp.status_code == 204:
            return {"success": True}
        else:
            data = resp.json()
            error_msg = data.get("message", data.get("error", str(data)))
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite delete_account network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


# ---------------------------------------------------------------------------
# ─── DATABASE (Appwrite DB — collection "setusync" in database "setusyncprofile") ──
# ---------------------------------------------------------------------------

DATABASE_ID = "setusyncprofile"
COLLECTION_ID = os.getenv("APPWRITE_USER_COLLECTION_ID", "setusync")

def _db_headers(session_token: Optional[str] = None) -> dict:
    """Headers for Appwrite Database API calls."""
    h = {
        "X-Appwrite-Project": PROJECT,
        "Content-Type": "application/json",
    }
    if API_KEY:
        h["X-Appwrite-Key"] = API_KEY
    if session_token:
        h["X-Appwrite-Session"] = session_token
    return h

def create_user_profile(user_id: str, data: dict) -> dict:
    """
    Create a user profile document in Appwrite database.
    The document ID is the user_id for easy lookups.
    
    data fields supported: userId, Name, email, Phone_no, Country, Nickname,
                           gender, profileimage, isVerified, Firstlogin,
                           lastactive, status
    """
    url = f"{ENDPOINT}/databases/{DATABASE_ID}/collections/{COLLECTION_ID}/documents"
    payload = {
        "documentId": user_id,
        "data": data,
    }
    try:
        resp = requests.post(url, json=payload, headers=_db_headers(), timeout=_TIMEOUT)
        if resp.status_code in (201, 200):
            return {"success": True, "document": resp.json()}
        else:
            err = resp.json().get("message", str(resp.json()))
            logger.warning(f"Appwrite create_user_profile failed: {err}")
            return {"success": False, "error": err}
    except requests.RequestException as e:
        logger.error(f"Appwrite create_user_profile network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}

def get_user_profile(user_id: str) -> dict:
    """
    Get a user profile document from Appwrite database by user_id.
    NOTE: Appwrite returns document fields at the root level of the JSON
    (not nested under a "data" key). System fields are prefixed with "$".
    """
    url = f"{ENDPOINT}/databases/{DATABASE_ID}/collections/{COLLECTION_ID}/documents/{user_id}"
    try:
        resp = requests.get(url, headers=_db_headers(), timeout=_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            # Appwrite document: fields are at root level, strip system keys (start with $)
            profile = {}
            for k, v in data.items():
                if not k.startswith("$"):
                    profile[k] = v
            return {"success": True, "profile": profile}
        elif resp.status_code == 404:
            return {"success": False, "error": "Profile not found"}
        else:
            try:
                err = resp.json().get("message", str(resp.text))
            except Exception:
                err = resp.text
            return {"success": False, "error": err}
    except requests.RequestException as e:
        logger.error(f"Appwrite get_user_profile network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}

def update_user_profile(user_id: str, data: dict) -> dict:
    """
    Update a user profile document in Appwrite database.
    Only provided fields will be updated.
    """
    url = f"{ENDPOINT}/databases/{DATABASE_ID}/collections/{COLLECTION_ID}/documents/{user_id}"
    try:
        resp = requests.patch(url, json={"data": data}, headers=_db_headers(), timeout=_TIMEOUT)
        if resp.status_code == 200:
            return {"success": True, "document": resp.json()}
        else:
            err = resp.json().get("message", str(resp.json()))
            return {"success": False, "error": err}
    except requests.RequestException as e:
        logger.error(f"Appwrite update_user_profile network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


# ---------------------------------------------------------------------------
# ─── PREFERENCES (Nickname, Phone, etc.) ─────────────────────────────────
# ---------------------------------------------------------------------------

def get_prefs(session_token: str) -> dict:
    """
    Get the logged-in user's preferences (custom data like nickname, phone).

    Returns:
        {"success": True, "prefs": {"nickname": "...", "phone": "...", ...}}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account/prefs"
    try:
        resp = requests.get(url, headers=_headers(session_token), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code == 200:
            return {"success": True, "prefs": data}
        else:
            error_msg = data.get("message", data.get("error", str(data)))
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite get_prefs network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def update_prefs(session_token: str, prefs: dict) -> dict:
    """
    Update the logged-in user's preferences (nickname, phone, etc.).

    Example:
        update_prefs(token, {"nickname": "Johnny", "phone": "+91-9876543210"})

    Returns:
        {"success": True, "prefs": {...}}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}
    url = f"{ENDPOINT}/account/prefs"
    try:
        payload = {"prefs": prefs}
        resp = requests.patch(url, json=payload, headers=_headers(session_token), timeout=_TIMEOUT)
        data = resp.json()
        if resp.status_code == 200:
            return {"success": True, "prefs": data}
        else:
            error_msg = data.get("message", data.get("error", str(data)))
            logger.warning(f"Appwrite update_prefs failed: {error_msg} (body sent: {prefs})")
            return {"success": False, "error": error_msg}
    except requests.RequestException as e:
        logger.error(f"Appwrite update_prefs network error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


def get_full_profile(session_token: str) -> dict:
    """
    Get the complete user profile: account details + preferences + DB profile.
    Priority: DB profile > prefs > account for extra fields (phone, gender, country).

    Returns:
        {"success": True, "user": {...}, "prefs": {...}}
        OR {"success": False, "error": "reason"}
    """
    if not session_token:
        return {"success": False, "error": "No session token provided"}

    # 1. Get account (authoritative for email + name)
    account_result = get_account(session_token)
    if not account_result["success"]:
        return account_result

    user_id = account_result["user_id"]

    # 2. Get prefs (stores nickname, phone, gender, country as set during signup)
    prefs_result = get_prefs(session_token)
    prefs = prefs_result.get("prefs", {}) if prefs_result["success"] else {}

    # 3. Also try DB profile (setusync collection) for complete data
    db_result = get_user_profile(user_id)
    db_profile = db_result.get("profile", {}) if db_result["success"] else {}

    # Merge: DB profile takes precedence over prefs for extra fields
    def pick(*sources, key):
        for s in sources:
            val = s.get(key, "")
            if val:
                return val
        return ""

    return {
        "success": True,
        "user": {
            "user_id": user_id,
            "email": account_result["email"],
            "name": account_result["name"],
            "nickname": db_profile.get("Nickname") or prefs.get("nickname") or "",
            "phone": db_profile.get("Phone_no") or prefs.get("phone") or "",
            "gender": db_profile.get("gender") or prefs.get("gender") or "",
            "country": db_profile.get("Country") or prefs.get("country") or "",
            "bio": prefs.get("bio") or "",
            # DB-specific fields
            "profileimage": db_profile.get("profileimage", ""),
            "isVerified": db_profile.get("isVerified", False),
            "firstLogin": db_profile.get("Firstlogin", ""),
            "lastactive": db_profile.get("lastactive", ""),
            "status": db_profile.get("status", ""),
        },
        "prefs": prefs,
        "db_profile": db_profile,
    }


def update_last_active(user_id: str) -> dict:
    """
    Update the lastactive field in the user's DB profile to current time.
    """
    now_str = datetime.utcnow().isoformat() + "Z"
    return update_user_profile(user_id, {"lastactive": now_str})