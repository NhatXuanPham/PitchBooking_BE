from datetime import datetime

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class RefreshTokenRequest(BaseModel):
    refresh_token: str
class GoogleExchangeRequest(BaseModel):
    code: str


class AccessTokenResponse(BaseModel):
    access_token: str
    expires_at: datetime