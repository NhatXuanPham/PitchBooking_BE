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
    cookie_kwargs,
    delete_auth_cookies,
    set_auth_cookies,
    verify_access_token,
)
from app.schemas.auth_schema import (
    GoogleExchangeRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SendOtpRequest,
    SendOtpResponse,
    TokenResponse,
)
from app.services.auth_service import auth_service

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register_user(
    request: Request,
    response: Response,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await auth_service.register(db, data)
    tokens = result.get("tokens")
    if tokens:
        set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return result


@router.post("/send-otp", response_model=SendOtpResponse)
@limiter.limit(settings.RATE_LIMIT_SEND_OTP)
async def send_otp(
    request: Request,
    data: SendOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.send_otp(
        db,
        email=data.email,
        purpose=data.purpose,
        resend=data.resend,
        background_tasks=background_tasks,
    )


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
        **cookie_kwargs(path=_OAUTH_COOKIE_PATH),
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
    expected_state = request.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)
    if not expected_state or not hmac.compare_digest(expected_state, data.state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please start Google login again.",
        )

    tokens = await auth_service.google_exchange(db, data.code)
    response.delete_cookie(settings.OAUTH_STATE_COOKIE_NAME, **cookie_kwargs(path=_OAUTH_COOKIE_PATH))
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens



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
