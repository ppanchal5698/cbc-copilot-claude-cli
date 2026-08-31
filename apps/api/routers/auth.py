"""Credential verification for NextAuth.

NextAuth owns the session; this endpoint only answers "are these credentials
good, and who is it?". Passwords are bcrypt-hashed and never leave the database.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, HTTPException

from cbc.db import db, serialise
from cbc.schemas import Credentials

router = APIRouter(prefix="/api/auth", tags=["auth"])

# `/api/auth/verify` is the one endpoint reachable without the internal token -
# NextAuth calls it - and nothing in the stack rate-limits anything.
#
# ponytail: an in-process counter, so the budget is per API process rather than
# per cluster. That is a real ceiling and an honest one; move it to Mongo or
# Redis if this ever runs more than one replica.
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 300
_attempts: dict[str, list[float]] = defaultdict(list)

# Verifying a password that does not exist has to cost the same as one that does.
# Skipping bcrypt on a miss returned in microseconds where a hit took ~100 ms,
# which told an attacker which addresses are registered - the thing the identical
# error message below is trying not to say.
_DUMMY_HASH = bcrypt.hashpw(b"never-matches", bcrypt.gensalt()).decode("utf-8")


def _too_many(key: str) -> bool:
    now = time.monotonic()
    recent = [at for at in _attempts[key] if now - at < WINDOW_SECONDS]
    recent.append(now)
    _attempts[key] = recent
    return len(recent) > MAX_ATTEMPTS


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@router.post("/verify")
async def verify(body: Credentials) -> dict:
    email = body.email.lower()
    if _too_many(email):
        raise HTTPException(429, "too many sign-in attempts; wait a few minutes")

    user = await db.users.find_one({"email": email})
    # Same response either way, and the same amount of work either way - do not
    # reveal whether an address is registered, by wording or by timing.
    hashed = user.get("passwordHash", "") if user else _DUMMY_HASH
    correct = verify_password(body.password, hashed)
    if not user or not correct:
        raise HTTPException(401, "invalid email or password")

    _attempts.pop(email, None)

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
