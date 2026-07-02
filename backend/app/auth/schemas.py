"""Pydantic schemas for authentication request bodies and responses.

These are the shapes of the JSON going in and out of /auth/* endpoints.
They are separate from the ORM models (app/db/models/) — the ORM models
describe the database; these schemas describe the API contract.
"""

from uuid import UUID

from pydantic import BaseModel, Field

# email fields are plain str, not EmailStr: pydantic's email-validator rejects
# RFC 6762 special-use TLDs like .local as a syntax error, not just a
# deliverability warning — which would make it impossible to log in as the
# D11 §11 bootstrap administrator, whose default address is admin@portfolioia.local.
# User.email itself is an unconstrained String(255) at the DB layer (Spec D01 §5).


# ── Request bodies ────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, description="Minimum 8 characters.")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str


class GuestLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ChangePasswordRequest(BaseModel):
    """D11 §6.4, §7.4. current_password is optional: the frontend omits the field

    entirely while must_change_password is true (re-typing a password the user
    just saw once in a startup log adds no security value, only friction).
    The backend re-validates that omission is only accepted in that state.
    """
    current_password: str | None = None
    new_password: str = Field(min_length=12, description="Minimum 12 characters.")


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
    auth_provider: str
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
