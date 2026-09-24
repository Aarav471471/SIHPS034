"""SHA-256 evidence sealing + JWT authentication -- spec core/security.py.

Two distinct concerns live here because the spec groups them:

1. *Evidence integrity* -- every uploaded surface is hashed on arrival.  The
   hash is UNIQUE in the database, so a photograph physically cannot be
   submitted twice, and a session-level seal chains the per-image hashes so any
   later tampering with the evidence set is detectable.

2. *Identity* -- short-lived access tokens plus long-lived refresh tokens, the
   latter sized for officers who work offline for days at a stretch.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.config import settings

TokenType = Literal["access", "refresh"]

# bcrypt cost factor. 12 is the current sane default: ~250ms per hash, which is
# painful to brute-force but invisible at login.
BCRYPT_ROUNDS = 12


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
# The `bcrypt` package is used directly rather than through passlib: passlib
# 1.7.4's backend-detection probe raises against bcrypt >= 4.1, and this layer
# is thin enough that the abstraction bought nothing.
def _to72(password: str) -> bytes:
    """bcrypt silently ignores input past 72 BYTES -- truncate explicitly.

    Sliced on bytes, not characters, because non-ASCII names and passphrases
    make those two lengths differ.
    """
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to72(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to72(plain), hashed.encode())
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def _create_token(
    subject: str | int,
    token_type: TokenType,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_urlsafe(12),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    subject: str | int, role: str, extra: dict[str, Any] | None = None
) -> str:
    payload = {"role": role, **(extra or {})}
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        payload,
    )


def create_refresh_token(subject: str | int) -> str:
    return _create_token(
        subject, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any] | None:
    """Return the claims, or None if the token is invalid/expired/wrong-type."""
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if expected_type and claims.get("type") != expected_type:
        return None
    return claims


# --------------------------------------------------------------------------
# Evidence integrity
# --------------------------------------------------------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def seal_evidence(session_id: str, image_hashes: list[str]) -> str:
    """Chain per-image hashes into one tamper-evident session seal.

    Order-independent (hashes are sorted) so re-uploading surfaces in a
    different sequence does not invalidate a legitimate seal, but adding,
    removing or altering any image does.
    """
    payload = session_id + "|" + "|".join(sorted(image_hashes))
    return hmac.new(
        settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def verify_seal(session_id: str, image_hashes: list[str], seal: str) -> bool:
    return hmac.compare_digest(seal_evidence(session_id, image_hashes), seal)


# --------------------------------------------------------------------------
# Opaque tokens (brand dispute links, QR badges)
# --------------------------------------------------------------------------
def generate_token(prefix: str = "", nbytes: int = 24) -> str:
    raw = secrets.token_urlsafe(nbytes)
    return f"{prefix}_{raw}" if prefix else raw


def generate_reference(prefix: str, seq: int | None = None) -> str:
    """Human-quotable reference, e.g. 'rep_1029' / 'cert_4421' (spec section 6)."""
    tail = str(seq) if seq is not None else secrets.randbelow(9000) + 1000
    return f"{prefix}_{tail}"
