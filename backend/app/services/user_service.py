"""User business logic — creation, lookup, authentication.

This layer sits between the API routers (app/api/) and the database models
(app/db/models/). Routers call service functions; service functions call
the ORM. This separation keeps the routers thin and the business rules testable.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, verify_password
from app.db.models.user import User
from app.roles.service import generate_password, grant_default_role


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Return the User with this email, or None if not found."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    """Return the User with this id, or None if not found."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    auth_provider: str,
    password: str | None = None,
    display_name: str | None = None,
    preferred_language: str = "es",
    must_change_password: bool = False,
    assign_default_role: bool = True,
) -> User:
    """Persist a new User. Caller must commit the session afterwards.

    Args:
        db: Active async database session.
        email: The user's email address (unique identifier).
        auth_provider: One of 'google', 'microsoft', 'password', 'guest'.
        password: Plaintext password — only for auth_provider='password'.
                  Will be hashed before storage. Must be None for other providers.
        display_name: Optional display name (populated from OAuth profile when available).
        preferred_language: ISO 639-1 code, defaults to the global i18n default.
        must_change_password: False for every normal registration flow (Spec D11 §6.4).
                  Only the bootstrap administrator (D11 §6.1) and admin-issued password
                  resets (D11 §7.2) set this to True — both pass it explicitly.
        assign_default_role: True for every normal registration flow — grants the
                  is_default: true role from the catalog (Investor in v1, D11 §6.2).
                  The bootstrap administrator (D11 §6.1) is the only exception: it is
                  assigned the Administrator role directly and passes False here.

    Returns:
        The newly created User (not yet committed to the database).
    """
    if auth_provider == "password" and not password:
        raise ValueError("password is required when auth_provider is 'password'.")

    user = User(
        email=email,
        auth_provider=auth_provider,
        password_hash=hash_password(password) if password else None,
        display_name=display_name,
        preferred_language=preferred_language,
        must_change_password=must_change_password,
    )
    db.add(user)
    await db.flush()  # writes to DB within the transaction, assigns user.id

    if assign_default_role:
        await grant_default_role(db, user.id)

    return user


async def authenticate_with_password(
    db: AsyncSession, email: str, password: str
) -> User | None:
    """Return the User if email + password are valid, None otherwise.

    Returns None (not a raised exception) so the caller can return a uniform
    401 without leaking whether the email exists or the password was wrong.
    """
    user = await get_user_by_email(db, email)
    if user is None or user.auth_provider != "password":
        return None
    if not verify_password(password, user.password_hash or ""):
        return None
    return user


async def admin_reset_password(db: AsyncSession, user: User, *, password_length: int) -> str:
    """Reset another user's password to a new random value (D11 §7.2).

    Sets must_change_password=true so the target is forced to pick their own
    password on next login — mirrors the bootstrap-admin flow (D11 §6.1).
    Returns the plaintext password; the caller shows it once and never stores it.
    """
    plaintext = generate_password(password_length)
    user.password_hash = hash_password(plaintext)
    user.must_change_password = True
    await db.commit()
    return plaintext
