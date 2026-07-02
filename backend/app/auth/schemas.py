"""Pydantic schemas for authentication request bodies and responses.

These are the shapes of the JSON going in and out of /auth/* endpoints.
They are separate from the ORM models (app/db/models/) — the ORM models
describe the database; these schemas describe the API contract.
"""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── Request bodies ────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters.")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GuestLoginRequest(BaseModel):
    email: EmailStr


# ── Response bodies ───────────────────────────────────────────────────────────


class LoginUserOut(BaseModel):
    """User fields returned in the login response body (C01 §4, extended by D11 §8.4).

    roles/permissions are not ORM attributes on User — the caller must build this
    with model_construct() or pass them explicitly, not User-backed model_validate().
    """
    id: UUID
    email: str
    display_name: str | None
    preferred_language: str
    must_change_password: bool
    roles: list[str]
    permissions: list[str]

    model_config = {"from_attributes": True}


class LoginSessionOut(BaseModel):
    """Session metadata returned in the login response body (C01 §4)."""
    portfolios_count: int
    notifications_poll_interval_seconds: int


class LoginResponse(BaseModel):
    """Returned on successful login / register.
    The session token itself travels in the httpOnly pi_session cookie."""
    user: LoginUserOut
    session: LoginSessionOut


class UserResponse(BaseModel):
    """Public representation of a user — never includes password_hash."""
    id: UUID
    email: str
    auth_provider: str
    display_name: str | None
    preferred_language: str
    must_change_password: bool

    model_config = {"from_attributes": True}
