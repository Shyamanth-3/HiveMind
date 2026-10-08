"""
Auth API: register / login / logout / me. Public except `me`.

Failures are deliberately uniform: a wrong password and an unknown email are indistinguishable (same status, same
message, equalised hashing time). Passwords, hashes and tokens never appear in responses or logs.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.rate_limit import client_ip, enforce
from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.db.database import get_db
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    # No min length on login: never reveal the password policy through the login endpoint.
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    id: str
    email: str
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)


def _set_session(response: Response, user: User) -> None:
    token, lifetime = create_access_token(user.id)
    response.set_cookie(settings.SESSION_COOKIE_NAME, token, max_age=lifetime, httponly=True,
                        secure=settings.COOKIE_SECURE, samesite="lax", path="/")


@router.post("/register", response_model=UserResponse, status_code=201)
def register(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    if not settings.REGISTRATION_ENABLED:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    enforce("register", client_ip(request), settings.RATE_LIMIT_REGISTER_PER_HOUR, 3600)
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not register with these details")
    db.refresh(user)
    _set_session(response, user)
    return user


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    enforce("login", client_ip(request), settings.RATE_LIMIT_LOGIN_PER_MIN, 60)
    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.password_hash if user else None)
    if not (ok and user is not None and user.is_active):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()
    _set_session(response, user)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    """Clears the cookie. Tokens are stateless and short-lived; `ACCESS_TOKEN_EXPIRE_MINUTES` bounds any copy."""
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/", secure=settings.COOKIE_SECURE,
                           httponly=True, samesite="lax")


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
