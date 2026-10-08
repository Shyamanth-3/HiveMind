"""
Password hashing and access tokens. No custom cryptography: Argon2id (argon2-cffi defaults, RFC 9106 low-memory
profile) and HS256 JWTs (PyJWT). Tokens carry only the user id, issue time and expiry; they are never logged.
"""

import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

_hasher = PasswordHasher()
# Verified against when the account does not exist, so login timing does not reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("hivemind-timing-equaliser")
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: str, expires_minutes: int | None = None) -> tuple[str, int]:
    """Return (token, lifetime_seconds)."""
    lifetime = int((expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60)
    now = int(time.time())
    token = jwt.encode({"sub": user_id, "iat": now, "exp": now + lifetime, "typ": "access"},
                       settings.JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, lifetime


def decode_access_token(token: str) -> str | None:
    """The user id of a valid, unexpired access token, else None. Never raises, never echoes the token."""
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM],
                            options={"require": ["exp", "iat", "sub"]})
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if claims.get("typ") == "access" and isinstance(sub, str) and sub else None
