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
# Generic response so the endpoint does not reveal whether an email is registered
OTP_SENT_GENERIC_MSG = "If the email is eligible, an OTP has been sent to it."

_dummy_password_hash: str | None = None


def _get_dummy_password_hash() -> str:
    """Lazily computed hash used to equalize login timing for unknown users."""
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = hash_password(uuid.uuid4().hex)
    return _dummy_password_hash


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
        elapsed = (now - latest_otp.created_at).total_seconds()
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

        # Data is already committed at this point; never fail the request because of SMTP.
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

        # Atomic consume: fails if a concurrent request already used/locked this OTP
        if not await otp_repo.mark_as_used(db, otp.id, settings.MAX_OTP_ATTEMPTS):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=OTP_LOCKED_MSG)

    async def register(
        self,
        db: AsyncSession,
        data: RegisterRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict:
        username = data.username.strip()
        existing_user = await user_repo.get_by_email(db, data.email)
        if existing_user and existing_user.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email has already been registered",
            )

        # Username is unique at DB level regardless of verification status
        user_by_username = await user_repo.get_by_username(db, username)
        if user_by_username and (not existing_user or user_by_username.id != existing_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username has already been used",
            )

        now = datetime.now(timezone.utc)
        try:
            if existing_user:
                if not existing_user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Account has been disabled",
                    )
                # While a verification code is still pending, do not allow the credentials
                # to be overwritten. Otherwise a third party could replace the password right
                # before the real owner enters the OTP from their inbox. Also limits email spam.
                pending_otp = await otp_repo.get_latest_active_otp(
                    db, existing_user.id, OtpPurpose.REGISTER
                )
                if (
                    pending_otp
                    and pending_otp.expires_at > now
                    and pending_otp.attempts < settings.MAX_OTP_ATTEMPTS
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "A verification code has already been sent to this email. "
                            "Please verify it or request a new code via resend."
                        ),
                    )

                user = existing_user
                user.username = username
                user.password_hash = hash_password(data.password)
                db.add(user)
                await db.flush()
            else:
                user = await user_repo.create(
                    db,
                    username=username,
                    email=data.email,
                    password_hash=hash_password(data.password),
                    is_email_verified=False,
                )

            otp_code = await self._issue_otp(db, user, OtpPurpose.REGISTER, now)
            await db.commit()
        except IntegrityError:
            # Concurrent registration with the same email/username
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email or username has already been used",
            )

        await self._send_otp_email(user, OtpPurpose.REGISTER, otp_code, background_tasks)

        return {
            "message": "Registration initiated. Please enter the OTP sent to your email to verify your account.",
            "email": user.email,
        }

    async def verify_email(
        self,
        db: AsyncSession,
        email: str,
        otp_code: str,
    ) -> dict:
        user = await user_repo.get_by_email(db, email)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_OTP_MSG)
        if user.is_email_verified:
            return {"message": "Email is already verified", "tokens": None}

        await self._consume_otp(db, user, OtpPurpose.REGISTER, otp_code)
        user.is_email_verified = True
        db.add(user)

        # Auto-login upon successful verification (same transaction)
        tokens = await self.issue_tokens(db, user)
        await db.commit()
        return {
            "message": "Email verified successfully",
            "tokens": tokens,
        }

    async def resend_otp(
        self,
        db: AsyncSession,
        email: str,
        purpose: OtpPurpose,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict:
        """
        Always returns the same generic response so callers cannot probe which emails
        are registered. Ineligible requests and requests within the cooldown are no-ops.
        """
        generic = {"message": OTP_SENT_GENERIC_MSG}

        user = await user_repo.get_by_email(db, email)
        if not user or not user.is_active:
            return generic
        if purpose == OtpPurpose.REGISTER and user.is_email_verified:
            return generic
        if purpose == OtpPurpose.RESET_PASSWORD and not user.is_email_verified:
            return generic

        now = datetime.now(timezone.utc)
        if await self._is_in_cooldown(db, user.id, purpose, now):
            return generic

        otp_code = await self._issue_otp(db, user, purpose, now)
        await db.commit()
        await self._send_otp_email(user, purpose, otp_code, background_tasks)
        return generic

    async def login(self, db: AsyncSession, form_data: OAuth2PasswordRequestForm) -> TokenResponse:
        user = await user_repo.get_by_email_or_username(db, form_data.username)
        if not user:
            # Run a hash verification anyway so response time does not reveal unknown users
            verify_password(form_data.password, _get_dummy_password_hash())
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email or password is incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not verify_password(form_data.password, user.password_hash):
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
                detail="Email is not verified. Please verify your email first.",
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
        # Validate JWT signature and expiration
        verify_refresh_token(token)

        rt = await refresh_token_repo.get_by_token(db, token)
        if rt and rt.revoked:
            # Reuse of an already-rotated token: likely stolen, revoke the whole family
            await refresh_token_repo.revoke_all_by_user(db, rt.user_id)
            await db.commit()
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

        # Refresh token rotation: atomic revoke guards against concurrent reuse
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
        # Only trust/link the email if Google has verified ownership of it
        if user_info.get("verified_email") is not True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified",
            )

        user = await user_repo.get_by_email(db, email)
        if user and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been disabled",
            )

        try:
            if not user:
                local_part = re.sub(r"[^A-Za-z0-9_.]", "", email.split("@")[0])[:40] or "user"
                user = await user_repo.create(
                    db,
                    username=f"{local_part}_{uuid.uuid4().hex[:6]}",
                    email=email,
                    password_hash=hash_password(uuid.uuid4().hex),
                    is_email_verified=True,
                    full_name=user_info.get("name"),
                    avatar_url=user_info.get("picture"),
                )
            elif not user.is_email_verified:
                # The unverified account may have been created by someone else using this
                # email (pre-account takeover). Discard its credentials before linking.
                user.is_email_verified = True
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

    async def forgot_password(
        self,
        db: AsyncSession,
        email: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict:
        return await self.resend_otp(db, email, OtpPurpose.RESET_PASSWORD, background_tasks)

    async def reset_password(
        self,
        db: AsyncSession,
        email: str,
        otp: str,
        new_password: str,
    ) -> dict:
        user = await user_repo.get_by_email(db, email)
        if not user or not user.is_active or not user.is_email_verified:
            # Same error as a wrong OTP: does not reveal whether the email exists
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_OTP_MSG)

        await self._consume_otp(db, user, OtpPurpose.RESET_PASSWORD, otp)
        await user_repo.update_password(db, user, hash_password(new_password))
        await refresh_token_repo.revoke_all_by_user(db, user.id)
        await db.commit()
        return {"message": "Password has been reset successfully"}


auth_service = AuthService()
