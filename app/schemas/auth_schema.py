from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enum import OtpPurpose


class RegisterRequest(BaseModel):
    # '@' is disallowed so a username can never collide with an email at login
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(..., min_length=8, max_length=128)
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class GoogleExchangeRequest(BaseModel):
    code: str


class AccessTokenResponse(BaseModel):
    access_token: str
    expires_at: datetime
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    message: str
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class VerifyEmailResponse(BaseModel):
    message: str
    tokens: TokenResponse | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendOtpRequest(BaseModel):
    email: EmailStr
    purpose: OtpPurpose