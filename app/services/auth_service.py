import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)
from app.models.user import User
from app.repositories.token_repo import refresh_token_repo
from app.repositories.user_repo import user_repo
from app.schemas.auth_schema import (
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)


class AuthService:
    async def register(self, db: AsyncSession, data: RegisterRequest) -> User:
        if data.email and await user_repo.get_by_email(db, data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email has already been registered",
            )
        if await user_repo.get_by_username(db, data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username has already been used",
            )

        return await user_repo.create(
            db,
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
        )

    async def login(self, db: AsyncSession, form_data: OAuth2PasswordRequestForm) -> TokenResponse:
        user = await user_repo.get_by_email_or_username(db, form_data.username)
        if not user or not verify_password(form_data.password, user.password_hash):
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

        return await self.issue_tokens(db, user)

    async def logout(self, db: AsyncSession, refresh_token: str) -> None:
        rt = await refresh_token_repo.get_by_token(db, refresh_token)
        if not rt or rt.revoked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refresh token is invalid or already revoked",
            )
        await refresh_token_repo.revoke(db, refresh_token)

    async def logout_all(self, db: AsyncSession, user_id: int) -> None:
        await refresh_token_repo.revoke_all_by_user(db, user_id)

    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token_data: RefreshTokenRequest,
    ) -> TokenResponse:
        # Validate JWT signature and expiration
        verify_refresh_token(refresh_token_data.refresh_token)

        rt = await refresh_token_repo.get_by_token(db, refresh_token_data.refresh_token)
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

        # Refresh token rotation: revoke old token and issue new token pair
        await refresh_token_repo.revoke(db, refresh_token_data.refresh_token)
        return await self.issue_tokens(db, user)

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

        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account must have an email",
            )

        user = await user_repo.get_by_email(db, email)
        if not user:
            user = await user_repo.create(
                db,
                username=email.split("@")[0] + "_" + uuid.uuid4().hex[:6],
                email=email,
                password_hash=hash_password(uuid.uuid4().hex),
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been disabled",
            )

        return await self.issue_tokens(db, user)

    async def issue_tokens(self, db: AsyncSession, user: User) -> TokenResponse:
        access_token, access_expires_at = create_token(user.id, "access")
        refresh_token, refresh_expires_at = create_token(user.id, "refresh")
        await refresh_token_repo.create(db, user.id, refresh_token, refresh_expires_at)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=refresh_expires_at,
        )


auth_service = AuthService()
