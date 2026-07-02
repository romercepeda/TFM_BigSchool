"""Pydantic schemas for the Administration section — Spec D11 §7.2, §7.3."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AdminUserSummary(BaseModel):
    """One row in the paginated user list (D11 §7.2)."""
    id: UUID
    email: str
    auth_provider: str
    display_name: str | None
    roles: list[str]
    must_change_password: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int


class AdminUserDetail(AdminUserSummary):
    """Full detail view for one user (D11 §7.2): summary fields + portfolios_count.

    last_login is not included: the User entity has no such field (Spec D01 §5)
    and this changeset does not add one.
    """
    portfolios_count: int


class AssignRoleRequest(BaseModel):
    role_code: str = Field(min_length=1, max_length=64)


class ResetPasswordResponse(BaseModel):
    """Shown once to the acting administrator (D11 §7.2) — never persisted or logged."""
    new_password: str


class AdminRoleOut(BaseModel):
    """One row in the read-only roles screen (D11 §7.2).

    name/description are resolved server-side (translate_role_name/_description,
    Spec D08 pattern). permissions are left as raw codes, not translated: D11
    §4.1 keeps permission descriptions English-only in v1, and the codes
    (e.g. portfolio.create) are self-documenting per D11 §10's own rationale.
    """
    code: str
    name: str
    description: str
    is_default: bool
    is_admin_role: bool
    permissions: list[str]
