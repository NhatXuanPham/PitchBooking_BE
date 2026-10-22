from urllib.parse import urlencode

# pyrefly: ignore[missing-import]
from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_access_token
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
async def register_user(
    data: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.register(db, data, background_tasks)


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.verify_email(db, data.email, data.otp)


@router.post("/resend-otp", response_model=MessageResponse)
async def resend_otp(
    data: ResendOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.resend_otp(db, data.email, data.purpose, background_tasks)


@router.post("/login", response_model=TokenResponse)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.login(db, form_data)


@router.post("/refreshtoken", response_model=TokenResponse)
async def refresh_token(
    refresh_token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.refresh_access_token(db, refresh_token_data)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    await auth_service.logout(db, data.refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_access_token),
):
    await auth_service.logout_all(db, int(payload["sub"]))
    return {"message": "Logged out from all sessions successfully"}


@router.get("/google/login")
def google_login():
    query = urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID or "",
            "redirect_uri": settings.GOOGLE_REDIRECT_URI or "",
            "response_type": "code",
            "scope": "openid email profile",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@router.post("/google/exchange", response_model=TokenResponse)
async def google_exchange(
    data: GoogleExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.google_exchange(db, data.code)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.forgot_password(db, data.email, background_tasks)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.reset_password(
        db,
        email=data.email,
        otp=data.otp,
        new_password=data.new_password,
    )
