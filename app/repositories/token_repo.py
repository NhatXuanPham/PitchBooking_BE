import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    async def create(self, db: AsyncSession, user_id: uuid.UUID, token: str, expires_at: datetime) -> RefreshToken:
        refresh_token = RefreshToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )
        db.add(refresh_token)
        await db.commit()
        await db.refresh(refresh_token)
        return refresh_token

    async def get_by_token(self, db: AsyncSession, token: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token == token)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, db: AsyncSession, token: str) -> None:
        refresh_token = await self.get_by_token(db, token)
        if refresh_token:
            refresh_token.revoked = True
            refresh_token.revoked_at = datetime.utcnow()
            await db.commit()

    async def revoke_all_by_user(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        stmt = select(RefreshToken).where(RefreshToken.user_id == user_id)
        result = await db.execute(stmt)
        tokens = result.scalars().all()
        for refresh_token in tokens:
            refresh_token.revoked = True
            refresh_token.revoked_at = datetime.utcnow()
        await db.commit()


refresh_token_repo = RefreshTokenRepository()
