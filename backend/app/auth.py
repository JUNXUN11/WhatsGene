"""Single-user auth for the reviewer demo (decision 007).

One seeded user, no signup route. Passwords are PBKDF2-SHA256 hashes
(stdlib only); sessions are random tokens in SQLite, carried in an
HttpOnly cookie. Ownership: every web job carries user_id and routes
only serve jobs owned by the caller.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config, db

SESSION_COOKIE = "wg_session"
SESSION_TTL_DAYS = 14
_COOKIE_MAX_AGE = SESSION_TTL_DAYS * 24 * 3600

_HASH_PREFIX = "pbkdf2-sha256"
_HASH_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
    return f"{_HASH_PREFIX}${_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        prefix, iterations, salt_hex, digest_hex = (stored or "").split("$")
        if prefix != _HASH_PREFIX:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()


def cookie_max_age() -> int:
    return _COOKIE_MAX_AGE


def ensure_seeded_user() -> dict[str, Any] | None:
    """Create the AUTH_USERNAME user once; adopt pre-auth jobs. Idempotent.

    No-op when users exist or AUTH_PASSWORD is unset (e.g. offline tests).
    """
    if db.user_count() > 0:
        return None
    password = (config.AUTH_PASSWORD or "").strip()
    if not password:
        return None
    user = db.create_user(config.AUTH_USERNAME.strip() or "reviewer", hash_password(password))
    db.adopt_orphan_jobs(user["id"])
    return user


def resolve_session(token: str | None) -> dict[str, Any] | None:
    """Return the logged-in user for a session token, or None."""
    if not token:
        return None
    session = db.get_session(token)
    if not session:
        return None
    try:
        expired = datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        expired = True
    if expired:
        db.delete_session(token)
        return None
    return db.get_user(session["user_id"])
