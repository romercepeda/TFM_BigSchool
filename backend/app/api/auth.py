"""Authentication API endpoints — Spec D01 / D08.

Endpoints:
    POST  /auth/register         — create account with email + password
    POST  /auth/login            — log in with email + password
    POST  /auth/guest            — log in or register as guest (email only)
    POST  /auth/refresh          — exchange refresh cookie for new access token
    POST  /auth/logout           — clear the refresh token cookie
    GET   /auth/me               — return the currently authenticated user (protected)
    PATCH /auth/me/language      — update the user's preferred language (D08 §6.2)

Token strategy (Spec 00b §2):
    - Access token  → returned in the JSON response body, short-lived (15 min).
      The frontend stores it in memory (not localStorage) and sends it as
      "Authorization: Bearer <token>" on every request.
    - Refresh token → stored in an httpOnly cookie, long-lived (30 days).
      JavaScript cannot read it, preventing XSS-based token theft.
      Sent automatically by the browser on POST /auth/refresh.
"""

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d08_schemas import LanguageUpdateRequest, LanguageUpdateResponse
from app.auth.dependencies import get_current_user
from app.auth.jwt import (
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_EXPIRE_DAYS,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.auth.schemas import (
    GuestLoginRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.config import get_config
from app.db.models.user import User
from app.db.session import get_db
from app.services.user_service import (
    authenticate_with_password,
    create_user,
    get_user_by_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_MAX_AGE_SECONDS = REFRESH_TOKEN_EXPIRE_DAYS * 86_400


# ── Internal helper ────────────────────────────────────────────────────────────


def _issue_tokens(response: Response, user: User) -> TokenResponse:
    """Create both tokens, set the refresh cookie, and return the access token."""
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,              # blocks JavaScript access
        samesite="lax",
        max_age=_REFRESH_MAX_AGE_SECONDS,
        secure=False,               # change to True when serving over HTTPS
    )
    return TokenResponse(access_token=access_token)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new account with email and password.

    Returns 409 if the email is already registered.
    Returns 201 + access token on success, sets refresh cookie.
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
    return _issue_tokens(response, user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Log in with email and password.

    Returns 401 on invalid credentials (same message whether the email
    doesn't exist or the password is wrong — avoids user enumeration).
    """
    user = await authenticate_with_password(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return _issue_tokens(response, user)


@router.post("/guest", response_model=TokenResponse)
async def guest_login(
    body: GuestLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
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
        # Returning guest — no verification required per Spec D01 §4.
        return _issue_tokens(response, existing)

    # New guest account.
    user = await create_user(db, email=body.email, auth_provider="guest")
    await db.commit()
    await db.refresh(user)
    return _issue_tokens(response, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    """Issue a new access token by presenting the refresh token cookie.

    The browser sends the httpOnly cookie automatically — no Authorization
    header needed on this endpoint.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired. Please log in again.",
    )
    if refresh_token_cookie is None:
        raise credentials_exception

    try:
        payload = decode_refresh_token(refresh_token_cookie)
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise credentials_exception from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return _issue_tokens(response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear the refresh token cookie. The frontend should discard the access token."""
    response.delete_cookie(REFRESH_COOKIE_NAME)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the currently authenticated user's profile.

    This endpoint requires a valid Bearer access token in the Authorization header.
    It is the canonical way to verify that a token works and to fetch user info.
    """
    return UserResponse.model_validate(current_user)


@router.patch("/me/language", response_model=LanguageUpdateResponse)
async def update_language(
    body: LanguageUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LanguageUpdateResponse:
    """Update the authenticated user's preferred UI language (D08 §6.2).

    The change takes effect immediately — all subsequent authenticated requests
    will use the new language for translations.
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
