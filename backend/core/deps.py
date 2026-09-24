"""Shared FastAPI dependencies: current user resolution and role gates."""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from core.security import decode_token
from models.enums import UserRole
from models.user import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if creds is None:
        raise CREDENTIALS_EXC
    claims = decode_token(creds.credentials, expected_type="access")
    if not claims:
        raise CREDENTIALS_EXC

    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise CREDENTIALS_EXC

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise CREDENTIALS_EXC
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    return user


async def get_current_user_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """For endpoints that work anonymously but personalise when signed in.

    'Scan Before You Buy' is the motivating case: a shopper must be able to scan
    without an account, but a logged-in scan also feeds their alert list.
    """
    if creds is None:
        return None
    claims = decode_token(creds.credentials, expected_type="access")
    if not claims:
        return None
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    return user if (user and user.is_active) else None


def require_roles(*roles: str) -> Callable:
    """Dependency factory gating an endpoint to specific roles.

    Admin is intentionally allowed everywhere -- it is the platform operator
    role, and excluding it would make the admin console impossible to build.
    """
    allowed = set(roles)

    async def _guard(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role == UserRole.ADMIN or user.role in allowed:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires one of roles: {', '.join(sorted(allowed))}",
        )

    return _guard


# Convenience aliases used across the route modules
require_officer = require_roles(UserRole.OFFICER, UserRole.SENIOR_OFFICER)
require_senior = require_roles(UserRole.SENIOR_OFFICER)
require_admin = require_roles(UserRole.ADMIN)
require_consumer = require_roles(UserRole.CONSUMER)
require_brand = require_roles(UserRole.BRAND)

CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated["User | None", Depends(get_current_user_optional)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
OfficerUser = Annotated[User, Depends(require_officer)]
SeniorUser = Annotated[User, Depends(require_senior)]
AdminUser = Annotated[User, Depends(require_admin)]
ConsumerUser = Annotated[User, Depends(require_consumer)]
BrandUser = Annotated[User, Depends(require_brand)]
