from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.models.enum import OtpPurpose

# Emails are case-insensitive in practice: store and compare them in lowercase
NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]


class RegisterRequest(BaseModel):
    # '@' is disallowed so a username can never collide with an email at login
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(..., min_length=8, max_length=128)
    email: NormalizedEmail


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None


class GoogleExchangeRequest(BaseModel):
    code: str
    # `state` query param Google sent back; must match the cookie set by /google/login
    state: str = Field(..., min_length=1, max_length=256)


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
    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendOtpRequest(BaseModel):
    email: NormalizedEmail
    purpose: OtpPurpose