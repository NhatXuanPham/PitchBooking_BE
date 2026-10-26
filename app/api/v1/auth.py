import hmac
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import (
    delete_auth_cookies,
    set_auth_cookies,
    verify_access_token,
)
from app.schemas.auth_schema import (
    ForgotPasswordRequest,
    GoogleExchangeRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    ResendOtpRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.services.auth_service import auth_service

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register_user(
    request: Request,
    data: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.register(db, data, background_tasks)


@router.post("/verify-email", response_model=VerifyEmailResponse)
@limiter.limit(settings.RATE_LIMIT_VERIFY_OTP)
async def verify_email(
    request: Request,
    response: Response,
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await auth_service.verify_email(db, data.email, data.otp)
    tokens = result.get("tokens")
    if tokens:
        set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return result


@router.post("/resend-otp", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_SEND_OTP)
async def resend_otp(
    request: Request,
    data: ResendOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.resend_otp(db, data.email, data.purpose, background_tasks)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login_user(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    tokens = await auth_service.login(db, form_data)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_REFRESH)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token_data: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    rt = (
        (refresh_token_data.refresh_token if refresh_token_data else None)
        or request.cookies.get("refresh_token")
    )
    if not rt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required in body or cookie",
        )
    tokens = await auth_service.refresh_access_token(
        db, RefreshTokenRequest(refresh_token=rt)
    )
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    data: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    rt = (data.refresh_token if data else None) or request.cookies.get("refresh_token")
    if rt:
        try:
            await auth_service.logout(db, rt)
        except HTTPException:
            pass
    delete_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_access_token),
):
    await auth_service.logout_all(db, int(payload["sub"]))
    delete_auth_cookies(response)
    return {"message": "Logged out from all sessions successfully"}


_OAUTH_COOKIE_PATH = "/api/v1/auth/google"


def _oauth_cookie_kwargs() -> dict:
    # Cross-site FE/BE in production (https) needs SameSite=None; Secure.
    # Locally (http) the FE and BE are same-site, so Lax works and Secure must be off.
    secure = settings.BACKEND_URL.startswith("https://")
    return {
        "path": _OAUTH_COOKIE_PATH,
        "httponly": True,
        "secure": secure,
        "samesite": "none" if secure else "lax",
    }


@router.get("/google/login")
def google_login():
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )

    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
    )
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")
    response.set_cookie(
        settings.OAUTH_STATE_COOKIE_NAME,
        state,
        max_age=settings.OAUTH_STATE_MAX_AGE_SECONDS,
        **_oauth_cookie_kwargs(),
    )
    return response


@router.post("/google/exchange", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def google_exchange(
    request: Request,
    response: Response,
    data: GoogleExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    # CSRF protection: the state Google echoed back must match the one stored in this
    # browser's cookie, proving the flow was started by this user (not an attacker's link).
    expected_state = request.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)
    if not expected_state or not hmac.compare_digest(expected_state, data.state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please start Google login again.",
        )

    tokens = await auth_service.google_exchange(db, data.code)
    # State is single-use
    response.delete_cookie(settings.OAUTH_STATE_COOKIE_NAME, **_oauth_cookie_kwargs())
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_SEND_OTP)
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.forgot_password(db, data.email, background_tasks)


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_VERIFY_OTP)
async def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.reset_password(
        db,
        email=data.email,
        otp=data.otp,
        new_password=data.new_password,
    )
