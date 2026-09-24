"""JWT authentication -- spec routes/auth.py."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, or_, select

from app.config import settings
from core.deps import CurrentUser, DbSession
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from models.enums import UserRole
from models.user import User
from schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from schemas.common import Message

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _profile(user: User) -> UserProfile:
    p = UserProfile.model_validate(user)
    p.trust_badge = user.trust_badge
    return p


def _issue(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, {"username": user.username}),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_profile(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    """Self-service signup for consumers and brands.

    Officer and admin accounts are provisioned administratively -- allowing
    anyone to self-declare as an enforcement officer would be an obvious hole.
    """
    clash = (
        await db.execute(
            select(User).where(
                or_(
                    func.lower(User.username) == payload.username.lower(),
                    func.lower(User.email) == payload.email.lower(),
                )
            )
        )
    ).scalar_one_or_none()
    if clash:
        field = "username" if clash.username.lower() == payload.username.lower() else "email"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"That {field} is already registered"
        )

    user = User(
        username=payload.username,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
        phone=payload.phone,
        brand_name=payload.brand_name if payload.role == UserRole.BRAND else None,
        citizen_trust_score=settings.TRUST_SCORE_INITIAL,
    )
    db.add(user)
    await db.flush()
    if payload.role == UserRole.BRAND:
        user.brand_id = user.id
    await db.commit()
    await db.refresh(user)
    return _issue(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    """Accepts either username or email as the identifier."""
    user = (
        await db.execute(
            select(User).where(
                or_(
                    func.lower(User.username) == payload.username.lower(),
                    func.lower(User.email) == payload.username.lower(),
                )
            )
        )
    ).scalar_one_or_none()

    # Same message for "no such user" and "wrong password" -- do not leak which.
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return _issue(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    """Exchange a refresh token -- how the offline officer PWA stays signed in."""
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )
    user = (
        await db.execute(select(User).where(User.id == int(claims["sub"])))
    ).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")
    return _issue(user)


@router.get("/me", response_model=UserProfile)
async def me(user: CurrentUser) -> UserProfile:
    return _profile(user)


@router.patch("/me/password", response_model=Message)
async def change_password(
    payload: PasswordChangeRequest, user: CurrentUser, db: DbSession
) -> Message:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return Message(detail="Password updated")
