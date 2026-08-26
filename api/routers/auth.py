"""Credential verification for NextAuth.

NextAuth owns the session; this endpoint only answers "are these credentials
good, and who is it?". Passwords are bcrypt-hashed and never leave the database.
"""
from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, HTTPException

from api.db import db, serialise
from api.models import Credentials

router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@router.post("/verify")
async def verify(body: Credentials) -> dict:
    user = await db.users.find_one({"email": body.email.lower()})
    # Same response either way - do not reveal whether an address is registered.
    if not user or not verify_password(body.password, user.get("passwordHash", "")):
        raise HTTPException(401, "invalid email or password")

    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"lastSeenAt": datetime.now(timezone.utc)}}
    )
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", user["email"]),
        "initials": user.get("initials", user["email"][:2].upper()),
        "role": user.get("role", "estimator"),
    }


@router.get("/me/{email}")
async def me(email: str) -> dict:
    user = await db.users.find_one({"email": email.lower()}, {"passwordHash": 0})
    if not user:
        raise HTTPException(404, "user not found")
    return serialise(user)
