"""Pydantic v2 contracts for authentication and user profiles."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["officer", "senior_officer", "admin", "consumer", "brand"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, examples=["officer.sharma"])
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    # Public self-registration is limited to the two non-privileged roles;
    # officer/admin accounts are provisioned by an administrator.
    role: Literal["consumer", "brand"] = "consumer"
    brand_name: str | None = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must mix letters and numbers")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserProfile"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: Role
    full_name: str | None = None
    phone: str | None = None

    officer_id: str | None = None
    department: str | None = None
    jurisdiction_name: str | None = None
    jurisdiction_geojson: dict[str, Any] | None = None

    citizen_trust_score: float = 50.0
    verified_reporter: bool = False
    reports_submitted: int = 0
    reports_confirmed: int = 0
    trust_badge: str | None = None

    brand_id: int | None = None
    brand_name: str | None = None

    is_active: bool = True
    created_at: datetime | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


TokenResponse.model_rebuild()
