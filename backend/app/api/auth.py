"""Authentication API endpoints — Spec D01 / D08 / Changeset C01.

Endpoints:
    POST  /auth/register         — create account with email + password
    POST  /auth/login            — log in with email + password
    POST  /auth/guest            — log in or register as guest (email only)
    POST  /auth/logout           — clear session and CSRF cookies
    GET   /auth/me               — return the currently authenticated user (protected)
    PATCH /auth/me/language      — update the user's preferred language (D08 §6.2)

Token strategy (Spec 00b §2, updated by C01):
    - A single session JWT is stored in the httpOnly pi_session cookie (7 days).
      JavaScript cannot read it; the browser sends it automatically on every request.
    - A non-httpOnly pi_csrf cookie is set alongside. The frontend reads it via
      document.cookie and echoes it in the X-CSRF-Token header on all unsafe requests.
    - There is no separate refresh endpoint — the session renews on the next login.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d08_schemas import LanguageUpdateRequest, LanguageUpdateResponse
from app.auth.csrf import generate_csrf_token
from app.auth.dependencies import get_current_user
from app.auth.jwt import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TOKEN_EXPIRE_DAYS,
    create_session_token,
)
from app.auth.schemas import (
    GuestLoginRequest,
    LoginRequest,
    LoginResponse,
    LoginSessionOut,
    LoginUserOut,
    RegisterRequest,
    UserResponse,
)
from app.config import get_config
from app.db.models.portfolio import Portfolio
from app.db.models.user import User
from app.db.session import get_db
from app.services.user_service import (
    authenticate_with_password,
    create_user,
    get_user_by_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSION_MAX_AGE = SESSION_TOKEN_EXPIRE_DAYS * 86_400


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _count_active_portfolios(db: AsyncSession, user_id: UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.user_id == user_id, Portfolio.status == "active")
    )
    return result.scalar_one()


def _set_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=_SESSION_MAX_AGE,
        secure=False,   # set True when serving over HTTPS
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # must be readable by JavaScript
        samesite="lax",
        max_age=_SESSION_MAX_AGE,
        secure=False,
        path="/",
    )


async def _build_login_response(
    response: Response,
    user: User,
    db: AsyncSession,
) -> LoginResponse:
    token = create_session_token(user.id, user.email)
    csrf_token = generate_csrf_token()
    _set_session_cookies(response, token, csrf_token)

    cfg = get_config()
    portfolios_count = await _count_active_portfolios(db, user.id)
    return LoginResponse(
        user=LoginUserOut.model_validate(user),
        session=LoginSessionOut(
            portfolios_count=portfolios_count,
            notifications_poll_interval_seconds=cfg.ai.notifications.poll_interval_seconds,
        ),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Register a new account with email and password.

    Returns 409 if the email is already registered.
    Returns 201 + session cookies + login payload on success.
    """
    existing = await get_user_by_email(db, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = await create_user(db, email=body.email, auth_provider="password", password=body.password)
    await db.commit()
    await db.refresh(user)
    return await _build_login_response(response, user, db)


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Log in with email and password.

    Returns 401 on invalid credentials (same message for wrong email or wrong
    password — avoids user enumeration).
    """
    user = await authenticate_with_password(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return await _build_login_response(response, user, db)


@router.post("/guest", response_model=LoginResponse)
async def guest_login(
    body: GuestLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Log in or register as a guest using only an email address.

    - If a guest account exists for this email → log in.
    - If no account exists → create a new guest account.
    - If a non-guest account exists → 409 (must use the correct method).

    Security note: no verification is performed (Spec D01 §4.3 accepted risk).
    """
    existing = await get_user_by_email(db, body.email)

    if existing is not None:
        if existing.auth_provider != "guest":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "An account already exists with this email. "
                    "Please sign in using the corresponding method."
                ),
            )
        return await _build_login_response(response, existing, db)

    user = await create_user(db, email=body.email, auth_provider="guest")
    await db.commit()
    await db.refresh(user)
    return await _build_login_response(response, user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear the session and CSRF cookies. Frontend should discard local state."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.patch("/me/language", response_model=LanguageUpdateResponse)
async def update_language(
    body: LanguageUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LanguageUpdateResponse:
    """Update the authenticated user's preferred UI language (D08 §6.2).

    Returns 400 if the requested language is not in i18n.supported_languages.
    """
    cfg = get_config()
    if body.language not in cfg.i18n.supported_languages:
        supported = ", ".join(cfg.i18n.supported_languages)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Language '{body.language}' is not supported. Supported: {supported}.",
        )

    current_user.preferred_language = body.language
    await db.commit()
    return LanguageUpdateResponse(preferred_language=current_user.preferred_language)
