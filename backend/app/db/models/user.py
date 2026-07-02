"""User ORM model — Spec D01 (Authentication & Identity).

Maps to the `users` table. A User owns one or more Portfolios (Spec D02).
The auth_provider field records which identity source was used to create
the account; password_hash is only populated when auth_provider = 'password'.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Enum values match Spec D01 §2 and the ERD.
_AUTH_PROVIDER_ENUM = Enum(
    "google", "microsoft", "password", "guest",
    name="auth_provider_enum",
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    auth_provider: Mapped[str] = mapped_column(_AUTH_PROVIDER_ENUM, nullable=False)
    # Only set when auth_provider = 'password'. Never logged or exposed in API responses.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Defaults to the global i18n.default_language (Spec D08). Stored per-user.
    preferred_language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="es"
    )
    # True for the bootstrap administrator and any admin-issued password reset
    # (Spec D11 §6.4). While true, non-password-change endpoints return HTTP 428.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Cascade delete: removing a User removes all their Portfolios and downstream data.
    portfolios: Mapped[list["Portfolio"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} provider={self.auth_provider!r}>"
