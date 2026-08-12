from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth_schema import (
    AccessTokenResponse,
    GoogleExchangeRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(tags=["auth"])

@router.post("/register", status_code=201)
async def register_user(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await auth_service.register(db, data)
    return {"message": "Registration successful", "user_id": user.id}

@router.post("/login", response_model=TokenResponse)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.login(db, form_data)

@router.post("/refreshtoken", response_model=AccessTokenResponse)
async def refresh_token(
    refresh_token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.refresh_access_token(db, refresh_token_data)

@router.get("/google/login")
def google_login():
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        "&response_type=code"
        "&scope=openid email profile"
    )
    return RedirectResponse(google_auth_url)

@router.post("/google/exchange")
async def google_exchange(
    data: GoogleExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.google_exchange(db, data.code)
