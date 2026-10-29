from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.models.enum import OtpPurpose

NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]


class RegisterRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.]+$")
    password: str = Field(..., min_length=8, max_length=128)


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
    state: str = Field(..., min_length=1, max_length=256)


class RegisterResponse(BaseModel):
    message: str
    tokens: TokenResponse | None = None


class MessageResponse(BaseModel):
    message: str




class ResetPasswordRequest(BaseModel):
    email: NormalizedEmail
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=128)



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


