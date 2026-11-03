"""Accounts and sessions (decisions 007, 016, 017).

No signup route. The owner (the oldest account) is created on the
first-run page, or seeded from AUTH_PASSWORD on a server, and adds
everyone else from Settings. Passwords are PBKDF2-SHA256 hashes
(stdlib only); sessions are random tokens in SQLite, carried in an
HttpOnly cookie. Ownership: every web job carries user_id and routes
only serve jobs owned by the caller.

AUTH_MODE=single (decision 016) skips the login page for the owner's
own browser on this machine while the owner is the only account;
everyone else always logs in.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from . import config, db

SESSION_COOKIE = "wg_session"
SESSION_TTL_DAYS = 14
_COOKIE_MAX_AGE = SESSION_TTL_DAYS * 24 * 3600

_HASH_PREFIX = "pbkdf2-sha256"
_HASH_ITERATIONS = 200_000

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


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

    No-op when users exist or AUTH_PASSWORD is unset: the owner then
    creates the first account on the first-run page (create_owner).
    """
    if db.user_count() > 0:
        return None
    password = (config.AUTH_PASSWORD or "").strip()
    if not password:
        return None
    user = db.create_user(config.AUTH_USERNAME.strip() or "reviewer", hash_password(password))
    db.adopt_orphan_jobs(user["id"])
    return user


def check_password(password: str) -> None:
    """Raise ValueError when a new password is empty. No length or strength rule."""
    if not password:
        raise ValueError("Type a password.")


def create_account(username: str, password: str) -> dict[str, Any]:
    """A new account; ValueError with a plain message when it cannot be made."""
    name = (username or "").strip()
    if not USERNAME_RE.match(name):
        raise ValueError("Use 1 to 32 letters, digits, dots, dashes, or underscores for the username.")
    check_password(password)
    if db.get_user_by_username(name):
        raise ValueError(f"The username {name} is already taken.")
    return db.create_user(name, hash_password(password))


def create_owner(username: str, password: str) -> dict[str, Any]:
    """The first account on a fresh install; it adopts pre-auth jobs."""
    if db.user_count() > 0:
        raise ValueError("This WhatsGene already has an owner account.")
    user = create_account(username, password)
    db.adopt_orphan_jobs(user["id"])
    return user


def is_owner(user: Mapping[str, Any]) -> bool:
    owner = db.first_user()
    return owner is not None and owner["id"] == user["id"]


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


# AUTH_MODE=single trusts only the owner's browser on this machine. Each
# check closes one way in: a loopback socket (not the network), a
# loopback Host (not DNS rebinding), no forwarding header (not a tunnel
# or reverse proxy on this box), and no cross-site page (not CSRF).
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_PROXY_HEADERS = ("forwarded", "x-forwarded-for", "x-forwarded-host",
                  "x-real-ip", "cf-connecting-ip")


def _is_loopback(hostname: str | None) -> bool:
    return (hostname or "").lower() in _LOOPBACK_HOSTS


def _url_hostname(url: str) -> str | None:
    """Hostname of a URL or //host:port, or None when malformed."""
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def is_owner_browser(client_host: str | None, headers: Mapping[str, str]) -> bool:
    """True only for a direct request from a page served on this machine."""
    if not _is_loopback(client_host):
        return False
    if not _is_loopback(_url_hostname("//" + headers.get("host", ""))):
        return False
    if any(headers.get(name) for name in _PROXY_HEADERS):
        return False
    origin = headers.get("origin")
    if origin is not None and not _is_loopback(_url_hostname(origin)):
        return False
    return headers.get("sec-fetch-site", "") != "cross-site"


def single_mode_owner(client_host: str | None,
                      headers: Mapping[str, str]) -> dict[str, Any] | None:
    """The owner under AUTH_MODE=single for the owner's browser, else None.

    Only while the owner is the only account: once a second person has
    an account, anyone at this machine could be that person, so every
    browser logs in.
    """
    if config.AUTH_MODE != "single" or not is_owner_browser(client_host, headers):
        return None
    if db.user_count() != 1:
        return None
    return db.first_user()


def can_create_owner(client_host: str | None, headers: Mapping[str, str]) -> bool:
    """The first-run page is open: no account yet, and this machine's browser.

    The browser check stops anyone on the network from claiming the
    owner account first on a server started with --share.
    """
    return db.user_count() == 0 and is_owner_browser(client_host, headers)
