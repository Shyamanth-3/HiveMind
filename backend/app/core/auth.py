"""
Authentication dependencies.

Identity comes from the `hm_session` httpOnly cookie (browsers) or an `Authorization: Bearer` header (API clients).
Cookie-authenticated state-changing requests must additionally come from an allowlisted Origin (CSRF defence, on top
of SameSite=Lax). Every failure is the same generic 401/403 so nothing about accounts or tokens leaks.
"""

from fastapi import Depends, HTTPException, Request, WebSocket
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.database import SessionLocal, get_db
from app.models import User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization[:7].lower() == "bearer ":
        return authorization[7:].strip() or None
    return None


def origin_is_trusted(origin: str | None) -> bool:
    return origin is not None and origin.rstrip("/") in settings.cors_origin_list


def _load_user(db: Session, token: str | None) -> User | None:
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    return user if user is not None and user.is_active else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header_token = _bearer(request.headers.get("authorization"))
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    user = _load_user(db, header_token or cookie_token)
    if user is None:
        raise _unauthenticated()
    if not header_token and request.method not in SAFE_METHODS and not origin_is_trusted(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="Untrusted origin")  # CSRF: cookie auth needs a trusted Origin
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def get_ws_user(websocket: WebSocket) -> User | None:
    """
    WebSocket identity: the same cookie / Bearer header as HTTP (sent with the handshake, so no credential ever
    travels in the URL). None = unauthenticated. Uses its own short session: a Depends(get_db) session would stay
    checked out of the pool for the whole (long-lived) connection.
    """
    token = _bearer(websocket.headers.get("authorization")) or websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    with SessionLocal() as db:
        user = _load_user(db, token)
        if user is not None:
            db.expunge(user)
        return user
