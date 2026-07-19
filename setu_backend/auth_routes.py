"""
auth_routes.py — FastAPI Authentication Endpoints

PURPOSE:
    All authentication-related API routes are defined here.
    Each route calls the corresponding function from auth_appwrite.py.

    The frontend (auth.js) calls these endpoints to signup/login/logout etc.
    Session tokens are stored in HttpOnly cookies for security.

FILES INVOLVED:
    - auth_appwrite.py    → imports backend auth functions
    - main.py             → mounts this router at /auth prefix
    - auth.html           → frontend login/signup page
    - auth.js             → frontend JavaScript calling these endpoints

HOW TO ADD A NEW ENDPOINT:
    1. Add a function in auth_appwrite.py (e.g., verify_email())
    2. Add a route here (e.g., @router.post("/verify-email"))
    3. Update auth.js to call the new endpoint
"""

import os
import json
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, Response, HTTPException, Cookie, Depends
from pydantic import BaseModel, EmailStr

from auth_appwrite import (
    create_account,
    login_account,
    get_account,
    delete_session,
    update_account_name,
    update_account_password,
    delete_account,
    get_prefs,
    update_prefs,
    get_full_profile,
    create_user_profile,
    get_user_profile,
    update_user_profile,
    update_last_active,
)

logger = logging.getLogger("auth_routes")

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    phone: Optional[str] = None
    gender: Optional[str] = None
    country: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UpdateNameRequest(BaseModel):
    name: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None
    Country: Optional[str] = None
    bio: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: get session token from cookie or Authorization header
# ---------------------------------------------------------------------------

def _get_session_token(request: Request) -> Optional[str]:
    """Extract session token from cookie first, then Authorization header."""
    # Try cookie first
    token = request.cookies.get("session_token")
    if token:
        return token
    # Try Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# ---------------------------------------------------------------------------
# ─── SIGNUP ───────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.post("/signup")
async def signup(req: SignupRequest):
    """
    Register a new user account.
    After successful signup, automatically logs in and returns a session token.
    """
    # 1. Create account
    result = create_account(email=req.email, password=req.password, name=req.name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Signup failed"))

    # 2. Auto-login after signup
    login_result = login_account(email=req.email, password=req.password)
    if not login_result["success"]:
        # Account created but login failed — still return success with warning
        return {
            "success": True,
            "warning": "Account created but auto-login failed. Please log in manually.",
            "user": {"email": req.email, "name": req.name},
        }

    # 3. Fetch account details (session response has userId but not name)
    from auth_appwrite import get_account as _get_account
    acc_info = _get_account(login_result["session_token"])
    user_name = acc_info.get("name", req.name) if acc_info.get("success") else req.name
    user_email = acc_info.get("email", req.email) if acc_info.get("success") else req.email
    user_id = acc_info.get("user_id", login_result.get("user_id", "")) if acc_info.get("success") else login_result.get("user_id", "")

    # 4. Update preferences with new fields
    prefs_update = {"Country": req.country}
    if req.phone:
        prefs_update["phone"] = req.phone
    if req.gender:
        prefs_update["gender"] = req.gender
    
    update_prefs(session_token=login_result["session_token"], prefs=prefs_update)

    # 5. Create/update profile in Appwrite Database (setusync) — optional, non-critical
    if user_id:
        now_str = datetime.utcnow().isoformat() + "Z"
        # Include all fields that exist in the collection schema
        profile_data = {
            "userId": user_id,
            "Name": req.name,
            "email": req.email,
            "Phone_no": req.phone or "",
            "Country": req.country,
            "Nickname": "",
            "gender": req.gender or "",
            "profileimage": "",
            "isVerified": False,
            "Firstlogin": now_str,
            "lastactive": now_str,
            "status": "active",
        }
        try:
            existing = get_user_profile(user_id)
            if existing["success"]:
                # Update existing: set Firstlogin if not set, update lastactive
                existing_profile = existing.get("profile", {})
                if not existing_profile.get("Firstlogin"):
                    profile_data["Firstlogin"] = now_str
                else:
                    # Don't overwrite Firstlogin
                    del profile_data["Firstlogin"]
                update_user_profile(user_id, profile_data)
            else:
                create_result = create_user_profile(user_id, profile_data)
                if not create_result["success"]:
                    logger.warning(f"Could not create DB profile: {create_result.get('error')}")
        except Exception as e:
            logger.warning(f"DB profile creation skipped (non-fatal): {e}")

    # 6. Return session token (frontend will store it)
    response_data = {
        "success": True,
        "message": "Account created and logged in successfully",
        "session_token": login_result["session_token"],
        "user": {
            "user_id": user_id,
            "email": user_email,
            "name": user_name,
        },
    }

    return response_data


# ---------------------------------------------------------------------------
# ─── LOGIN ────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(req: LoginRequest):
    """
    Log in with email and password.
    Returns a session token that the frontend stores securely.
    """
    result = login_account(email=req.email, password=req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid credentials"))

    # Fetch account to get name (session response doesn't include name)
    acc = get_account(session_token=result["session_token"])
    user_name = acc.get("name", "") if acc.get("success") else ""
    user_email = acc.get("email", req.email) if acc.get("success") else req.email
    user_id = acc.get("user_id", result.get("user_id", "")) if acc.get("success") else result.get("user_id", "")

    # Update lastactive on login
    if user_id:
        try:
            update_last_active(user_id)
        except Exception as e:
            logger.warning(f"Could not update lastactive on login: {e}")

    return {
        "success": True,
        "message": "Logged in successfully",
        "session_token": result["session_token"],
        "user": {
            "user_id": user_id,
            "email": user_email,
            "name": user_name,
        },
    }


# ---------------------------------------------------------------------------
# ─── PROFILE (Get current user) ──────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.get("/profile")
async def profile(request: Request):
    """
    Get the currently logged-in user's profile.
    Requires a valid session token in the Authorization header or cookie.
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = get_account(session_token=token)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid session"))

    return {
        "success": True,
        "user": {
            "user_id": result["user_id"],
            "email": result["email"],
            "name": result["name"],
        },
    }


# ---------------------------------------------------------------------------
# ─── LOGOUT ───────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout(request: Request):
    """
    Log out — deletes the current session on Appwrite.
    The frontend should also clear the stored token.
    """
    token = _get_session_token(request)
    if not token:
        return {"success": True, "message": "No active session"}

    result = delete_session(session_token=token)
    if not result["success"]:
        logger.warning(f"Logout warning: {result.get('error')}")
        # Still return success — we want the frontend to clear local state

    return {"success": True, "message": "Logged out successfully"}


@router.post("/update-last-active")
async def update_last_active_route(request: Request):
    """
    Update the user's lastactive timestamp in the database.
    Called periodically to track user activity.
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    acc = get_account(session_token=token)
    if not acc["success"]:
        raise HTTPException(status_code=401, detail="Invalid session")

    user_id = acc.get("user_id", "")
    if user_id:
        update_last_active(user_id)

    return {"success": True}


# ---------------------------------------------------------------------------
# ─── UPDATE NAME ─────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.put("/update-name")
async def update_name(request: Request, req: UpdateNameRequest):
    """
    Update the logged-in user's display name.
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = update_account_name(session_token=token, name=req.name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to update name"))

    return {"success": True, "name": result["name"]}


# ---------------------------------------------------------------------------
# ─── CHANGE PASSWORD ─────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.put("/change-password")
async def change_password(request: Request, req: ChangePasswordRequest):
    """
    Change the logged-in user's password.
    Requires the old password for verification.
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = update_account_password(
        session_token=token,
        old_password=req.old_password,
        new_password=req.new_password,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to change password"))

    return {"success": True, "message": "Password changed successfully"}


# ---------------------------------------------------------------------------
# ─── DELETE ACCOUNT ──────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.delete("/delete-account")
async def remove_account(request: Request):
    """
    Permanently delete the logged-in user's account.
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = delete_account(session_token=token)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete account"))

    return {"success": True, "message": "Account deleted permanently"}


# ---------------------------------------------------------------------------
# ─── GET FULL PROFILE ───────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.get("/full-profile")
async def full_profile(request: Request):
    """
    Get the complete user profile including preferences (nickname, phone).
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = get_full_profile(session_token=token)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "Failed to get profile"))

    return {"success": True, "user": result["user"]}


# ---------------------------------------------------------------------------
# ─── UPDATE PROFILE (Nickname, Phone, Name) ─────────────────────────────
# ---------------------------------------------------------------------------

@router.put("/update-profile")
async def update_profile(request: Request, req: UpdateProfileRequest):
    """
    Update the user's profile: nickname, phone, and/or display name.
    All fields are optional — only provided fields will be updated.
    """
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 1. Update Appwrite preferences
    prefs_update = {}
    if req.nickname is not None:
        prefs_update["nickname"] = req.nickname
    if req.phone is not None:
        prefs_update["phone"] = req.phone
    if req.gender is not None:
        prefs_update["gender"] = req.gender
    if req.Country is not None:
        prefs_update["country"] = req.Country
    if req.bio is not None:
        prefs_update["bio"] = req.bio

    if prefs_update:
        prefs_result = update_prefs(session_token=token, prefs=prefs_update)
        if not prefs_result["success"]:
            raise HTTPException(status_code=400, detail=prefs_result.get("error", "Failed to update preferences"))

    # 2. Update display name if provided
    if req.name is not None:
        name_result = update_account_name(session_token=token, name=req.name)
        if not name_result["success"]:
            raise HTTPException(status_code=400, detail=name_result.get("error", "Failed to update name"))

    # 3. Also update the Appwrite Database profile (setusyncprofile) — non-critical
    try:
        account = get_account(session_token=token)
        if account["success"]:
            user_id = account.get("user_id", "")
            if user_id:
                db_update = {}
                if req.nickname is not None:
                    db_update["Nickname"] = req.nickname
                if req.phone is not None:
                    db_update["Phone_no"] = req.phone
                if req.gender is not None:
                    db_update["gender"] = req.gender
                if req.Country is not None:
                    db_update["Country"] = req.Country
                if db_update:
                    existing = get_user_profile(user_id)
                    if existing["success"]:
                        update_user_profile(user_id, db_update)
                    else:
                        create_user_profile(user_id, db_update)
    except Exception as e:
        logger.warning(f"DB profile update skipped (non-fatal): {e}")

    # 4. Return updated full profile
    profile_result = get_full_profile(session_token=token)
    if profile_result["success"]:
        return {"success": True, "user": profile_result["user"]}
    
    return {"success": True, "message": "Profile updated"}


# ---------------------------------------------------------------------------
# ─── CHECK AUTH STATUS ───────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@router.get("/status")
async def auth_status(request: Request):
    """
    Quick check if the current session is valid.
    Used by the frontend to check login status on page load.
    """
    token = _get_session_token(request)
    if not token:
        return {"authenticated": False}

    result = get_account(session_token=token)
    if not result["success"]:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user": {
            "user_id": result["user_id"],
            "email": result["email"],
            "name": result["name"],
        },
    }