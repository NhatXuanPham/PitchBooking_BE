from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

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


class SendOtpRequest(BaseModel):
    email: NormalizedEmail
    purpose: OtpPurpose = OtpPurpose.REGISTER
    resend: bool = False

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_purpose(cls, v: str | OtpPurpose) -> OtpPurpose:
        if isinstance(v, str):
            v_upper = v.strip().upper()
            return OtpPurpose(v_upper)
        return v


class SendOtpResponse(BaseModel):
    message: str
    email: EmailStr
    is_already_sent: bool = False
    cooldown_seconds: int = 0
    expires_in_seconds: int = 0


class RegisterVerifyOtpRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class RegisterVerifyOtpResponse(BaseModel):
    message: str
    email: EmailStr
    registration_token: str


class RegisterCompleteRequest(BaseModel):
    registration_token: str = Field(..., min_length=1)
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(..., min_length=8, max_length=128)