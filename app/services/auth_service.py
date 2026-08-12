import uuid

import httpx
from fastapi import HTTPException
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
    AccessTokenResponse,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)


class AuthService:
    async def register(self, db: AsyncSession, data: RegisterRequest) -> User:
        if data.email and await user_repo.get_by_email(db, data.email):
            raise HTTPException(status_code=400, detail="Email has already been registered")
        if await user_repo.get_by_username(db, data.username):
            raise HTTPException(status_code=400, detail="Username has already been used")

        return await user_repo.create(
            db,
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
        )

    async def login(self, db: AsyncSession, form_data: OAuth2PasswordRequestForm) -> TokenResponse:
        user = await user_repo.get_by_email_or_username(db, form_data.username)
        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Email or password is incorrect")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account has been disabled")

        return await self.issue_tokens(db, user)

    async def logout(self, db: AsyncSession, refresh_token: str) -> None:
        rt = await refresh_token_repo.get_by_token(db, refresh_token)
        if not rt or rt.revoked:
            raise HTTPException(status_code=400, detail="Refresh token is invalid")
        await refresh_token_repo.revoke(db, refresh_token)

    async def logout_all(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        await refresh_token_repo.revoke_all_by_user(db, user_id)

    async def refresh_access_token(self, db: AsyncSession, refresh_token_data: RefreshTokenRequest) -> AccessTokenResponse:
        verify_refresh_token(refresh_token_data.refresh_token)

        rt = await refresh_token_repo.get_by_token(db, refresh_token_data.refresh_token)
        if not rt or rt.revoked:
            raise HTTPException(status_code=401, detail="Refresh token is invalid")

        access_token, expires_at = create_token(rt.user_id, "access")
        return AccessTokenResponse(access_token=access_token, expires_at=expires_at)

    async def google_exchange(self, db: AsyncSession, code: str) -> TokenResponse:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_data = response.json()
        if "error" in token_data:
            raise HTTPException(status_code=400, detail="Google OAuth failed")

        user_info = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        ).json()

        email = user_info["email"]
        user = await user_repo.get_by_email(db, email)
        if not user:
            user = await user_repo.create(
                db,
                username=email.split("@")[0] + "_" + str(uuid.uuid4())[:6],
                email=email,
                password_hash=hash_password(uuid.uuid4().hex),
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
