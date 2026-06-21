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


class TokenResponse(BaseModel):
    """Returned on successful login / register. The refresh token is in a cookie."""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public representation of a user — never includes password_hash."""
    id: UUID
    email: str
    auth_provider: str
    display_name: str | None
    preferred_language: str

    model_config = {"from_attributes": True}  # allows model_validate(orm_instance)
