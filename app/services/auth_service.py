import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import BackgroundTasks, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_token,
    generate_otp,
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_password,
    verify_refresh_token,
)
from app.models.enum import OtpPurpose
from app.models.user import User
from app.repositories.otp_repo import otp_repo
from app.repositories.token_repo import refresh_token_repo
from app.repositories.user_repo import user_repo
from app.schemas.auth_schema import (
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

INVALID_OTP_MSG = "Invalid or expired OTP. Please request a new one."
OTP_LOCKED_MSG = "OTP has expired or exceeded maximum attempts. Please request a new OTP."
OTP_SENT_GENERIC_MSG = "If the email is eligible, an OTP has been sent to it."

_dummy_password_hash: str | None = None


def _get_dummy_password_hash() -> str:
    """Lazily computed hash used to equalize login timing for unknown users."""
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = hash_password(uuid.uuid4().hex)
    return _dummy_password_hash


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _generate_default_username(email: str) -> str:
    local_part = re.sub(r"[^A-Za-z0-9_.]", "", email.split("@")[0])[:40] or "user"
    return f"{local_part}_{uuid.uuid4().hex[:6]}"


class AuthService:
    async def _is_in_cooldown(
        self,
        db: AsyncSession,
        user_id: int,
        purpose: OtpPurpose,
        now: datetime,
    ) -> bool:
        latest_otp = await otp_repo.get_latest_otp(db, user_id, purpose)
        if not latest_otp or not latest_otp.created_at:
            return False
        elapsed = (now - _to_utc(latest_otp.created_at)).total_seconds()
        return elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS

    async def _issue_otp(
        self,
        db: AsyncSession,
        user: User,
        purpose: OtpPurpose,
        now: datetime,
    ) -> str:
        """Invalidate previous OTPs of the same purpose and create a new one (no commit)."""
        await otp_repo.invalidate_otps(db, user.id, purpose)
        otp_code = generate_otp()
        expires_at = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        await otp_repo.create(db, user.id, hash_otp(otp_code), purpose, expires_at)
        return otp_code

    async def _send_otp_email(
        self,
        user: User,
        purpose: OtpPurpose,
        otp_code: str,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        if purpose == OtpPurpose.REGISTER:
            send_func = email_service.send_registration_otp_email
        else:
            send_func = email_service.send_password_reset_otp_email

        kwargs = {"to_email": user.email, "username": user.username, "otp": otp_code}
        if background_tasks is not None:
            background_tasks.add_task(send_func, **kwargs)
            return

        try:
            await send_func(**kwargs)
        except Exception:
            logger.exception("Failed to send %s OTP email to %s", purpose, user.email)

    async def _consume_otp(
        self,
        db: AsyncSession,
        user: User,
        purpose: OtpPurpose,
        otp_code: str,
    ) -> None:
        """
        Verify and consume an OTP (no commit on success).
        On a wrong code, the attempt counter is incremented and committed before raising.
        """
        otp = await otp_repo.get_latest_active_otp(db, user.id, purpose)
        now = datetime.now(timezone.utc)
        if not otp or otp.expires_at <= now or otp.attempts >= settings.MAX_OTP_ATTEMPTS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=OTP_LOCKED_MSG)

        if not verify_otp_hash(otp_code, otp.code_hash):
            attempts = await otp_repo.increment_attempts(db, otp.id, settings.MAX_OTP_ATTEMPTS)
            await db.commit()
            remaining = 0 if attempts is None else max(0, settings.MAX_OTP_ATTEMPTS - attempts)
            if remaining == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OTP. Maximum attempts exceeded. Please request a new OTP.",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OTP. You have {remaining} attempts remaining.",
            )

        if not await otp_repo.mark_as_used(db, otp.id, settings.MAX_OTP_ATTEMPTS):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=OTP_LOCKED_MSG)

    async def _resolve_otp_user(
        self, db: AsyncSession, email: str, purpose: OtpPurpose
    ) -> User | None:
        user = await user_repo.get_by_email(db, email)
        if purpose == OtpPurpose.REGISTER:
            if user:
                if user.is_email_verified:
                    if not user.is_active:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Account has been disabled",
                        )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email has already been registered. Please log in.",
                    )
                return user
            try:
                user = await user_repo.create(
                    db,
                    username=_generate_default_username(email),
                    email=email,
                    password_hash=hash_password(uuid.uuid4().hex),
                    is_active=True,
                    is_email_verified=False,
                )
                await db.flush()
                return user
            except IntegrityError:
                await db.rollback()
                user = await user_repo.get_by_email(db, email)
                if user:
                    if user.is_email_verified:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Email has already been registered. Please log in.",
                        )
                    return user
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Account is being created concurrently. Please try again.",
                )

        if purpose == OtpPurpose.RESET_PASSWORD:
            return user if (user and user.is_active and user.is_email_verified) else None

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported OTP purpose",
        )

    async def send_otp(
        self,
        db: AsyncSession,
        email: str,
        purpose: OtpPurpose = OtpPurpose.REGISTER,
        resend: bool = False,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict:
        email = email.strip().lower()
        now = datetime.now(timezone.utc)

        user = await self._resolve_otp_user(db, email, purpose)
        if not user:
            return {
                "message": OTP_SENT_GENERIC_MSG,
                "email": email,
                "is_already_sent": False,
                "cooldown_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
                "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
            }

        active_otp = await otp_repo.get_latest_active_otp(db, user.id, purpose)
        latest_otp = await otp_repo.get_latest_otp(db, user.id, purpose)

        cooldown_remaining = 0
        if latest_otp and latest_otp.created_at:
            elapsed = (now - _to_utc(latest_otp.created_at)).total_seconds()
            cooldown_remaining = max(0, int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed))

        if not resend and active_otp:
            exp = _to_utc(active_otp.expires_at)
            if exp > now and active_otp.attempts < settings.MAX_OTP_ATTEMPTS:
                return {
                    "message": "Verification code has already been sent and is still valid. Please check your inbox.",
                    "email": user.email,
                    "is_already_sent": True,
                    "cooldown_seconds": cooldown_remaining,
                    "expires_in_seconds": max(0, int((exp - now).total_seconds())),
                }

        if cooldown_remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {cooldown_remaining} seconds before requesting a new code.",
            )

        try:
            otp_code = await self._issue_otp(db, user, purpose, now)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A verification code request is already in progress. Please try again.",
            )
        await self._send_otp_email(user, purpose, otp_code, background_tasks)

        return {
            "message": (
                "A new verification code has been sent to your email."
                if resend
                else "Verification code has been sent to your email."
            ),
            "email": user.email,
            "is_already_sent": False,
            "cooldown_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
        }

    async def register(
        self,
        db: AsyncSession,
        data: RegisterRequest,
    ) -> dict:
        email = data.email.strip().lower()
        username = data.username.strip()

        user = await user_repo.get_by_email(db, email)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_OTP_MSG)
        if user.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email has already been registered. Please log in.",
            )

        existing_username = await user_repo.get_by_username(db, username)
        if existing_username and existing_username.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username has already been used",
            )

        await self._consume_otp(db, user, OtpPurpose.REGISTER, data.otp)

        try:
            user.username = username
            user.password_hash = hash_password(data.password)
            user.is_active = True
            user.is_email_verified = True
            db.add(user)
            await db.flush()

            tokens = await self.issue_tokens(db, user)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing_username = await user_repo.get_by_username(db, username)
            if existing_username and existing_username.id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username has already been used",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration is being processed concurrently. Please try again.",
            )

        return {
            "message": "Account created successfully",
            "tokens": tokens,
        }


    async def login(self, db: AsyncSession, form_data: OAuth2PasswordRequestForm) -> TokenResponse:
        user = await user_repo.get_by_email_or_username(db, form_data.username)
        password_hash = user.password_hash if user else _get_dummy_password_hash()
        password_ok = verify_password(form_data.password, password_hash)
        if not user or not password_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email or password is incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been disabled",
            )
        if not user.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email.",
            )

        tokens = await self.issue_tokens(db, user)
        await db.commit()
        return tokens

    async def logout(self, db: AsyncSession, refresh_token: str) -> None:
        if not await refresh_token_repo.revoke(db, refresh_token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refresh token is invalid or already revoked",
            )
        await db.commit()

    async def logout_all(self, db: AsyncSession, user_id: int) -> None:
        await refresh_token_repo.revoke_all_by_user(db, user_id)
        await db.commit()

    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token_data: RefreshTokenRequest,
    ) -> TokenResponse:
        token = refresh_token_data.refresh_token
        verify_refresh_token(token)

        rt = await refresh_token_repo.get_by_token(db, token)
        now = datetime.now(timezone.utc)
        if not rt or rt.revoked or rt.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid, expired or revoked",
            )

        user = await user_repo.get_by_id(db, rt.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been disabled",
            )

        if not await refresh_token_repo.revoke(db, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid, expired or revoked",
            )
        tokens = await self.issue_tokens(db, user)
        await db.commit()
        return tokens

    async def google_exchange(self, db: AsyncSession, code: str) -> TokenResponse:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth is not configured",
            )

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange authorization code with Google",
                )

            token_data = token_response.json()
            if "access_token" not in token_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google OAuth did not return an access token",
                )

            user_info_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            if user_info_resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch user profile from Google",
                )
            user_info = user_info_resp.json()

        email = (user_info.get("email") or "").strip().lower()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account must have an email",
            )
        if user_info.get("verified_email") is not True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified",
            )

        user = await user_repo.get_by_email(db, email)
        if user and user.is_email_verified and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been disabled",
            )

        try:
            if not user:
                user = await user_repo.create(
                    db,
                    username=_generate_default_username(email),
                    email=email,
                    password_hash=hash_password(uuid.uuid4().hex),
                    is_active=True,
                    is_email_verified=True,
                    full_name=user_info.get("name"),
                    avatar_url=user_info.get("picture"),
                )
            elif not user.is_email_verified:
                user.is_active = True
                user.is_email_verified = True
                if "@" in user.username:
                    user.username = _generate_default_username(email)
                user.password_hash = hash_password(uuid.uuid4().hex)
                if not user.full_name and user_info.get("name"):
                    user.full_name = user_info.get("name")
                if not user.avatar_url and user_info.get("picture"):
                    user.avatar_url = user_info.get("picture")
                db.add(user)
                await otp_repo.invalidate_otps(db, user.id, OtpPurpose.REGISTER)
                await refresh_token_repo.revoke_all_by_user(db, user.id)

            tokens = await self.issue_tokens(db, user)
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account is being created concurrently. Please try again.",
            )
        return tokens

    async def issue_tokens(self, db: AsyncSession, user: User) -> TokenResponse:
        """Create a token pair and persist the refresh token. Caller must commit."""
        access_token, access_expires_at = create_token(user.id, "access")
        refresh_token, refresh_expires_at = create_token(user.id, "refresh")
        await refresh_token_repo.create(db, user.id, refresh_token, refresh_expires_at)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=refresh_expires_at,
        )

    async def reset_password(
        self,
        db: AsyncSession,
        email: str,
        otp: str,
        new_password: str,
    ) -> dict:
        user = await user_repo.get_by_email(db, email)
        if not user or not user.is_active or not user.is_email_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_OTP_MSG)

        await self._consume_otp(db, user, OtpPurpose.RESET_PASSWORD, otp)
        await user_repo.update_password(db, user, hash_password(new_password))
        await refresh_token_repo.revoke_all_by_user(db, user.id)
        await db.commit()
        return {"message": "Password has been reset successfully"}


auth_service = AuthService()
