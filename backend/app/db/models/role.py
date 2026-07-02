"""Roles & permissions ORM models — Spec D11 §4.

Four tables:
    Permission        — seed-file-driven catalog of fine-grained authorization atoms.
    Role               — named bundle of permissions (e.g. administrator, investor).
    RolePermission     — join table, refreshed to match the seed file on every startup.
    UserRole           — the user-to-role link. A user's effective permissions are the
                          union of all RolePermission rows reachable via their UserRole rows.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name_key: Mapped[str] = mapped_column(String(128), nullable=False)
    description_key: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Permission code={self.code!r} active={self.active!r}>"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name_key: Mapped[str] = mapped_column(String(128), nullable=False)
    description_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # Exactly one role has is_default=True (auto-assigned on registration, D11 §6.2).
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Exactly one role has is_admin_role=True (always-one-admin guarantee, D11 §6.3).
    is_admin_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Role code={self.code!r} is_default={self.is_default!r} active={self.active!r}>"


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

    role: Mapped["Role"] = relationship()
    permission: Mapped["Permission"] = relationship()

    def __repr__(self) -> str:
        return f"<RolePermission role_id={self.role_id} permission_id={self.permission_id}>"


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Null when the assignment was automatic (e.g. the default role on registration).
    # Set to the acting administrator's id for manual grants (D11 §7.3).
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    role: Mapped["Role"] = relationship()

    def __repr__(self) -> str:
        return f"<UserRole user_id={self.user_id} role_id={self.role_id}>"
