from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """
    Repository methods only flush; the calling service owns the transaction
    and is responsible for committing.

    Public methods accept the raw refresh token; only its SHA-256 hash is persisted
    and compared, so a leaked database cannot be used to mint sessions.
    """

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        token: str,
        expires_at: datetime,
    ) -> RefreshToken:
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
        db.add(refresh_token)
        await db.flush()
        return refresh_token

    async def get_by_token(self, db: AsyncSession, token: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, db: AsyncSession, token: str) -> bool:
        """Revoke a token. Returns False if it was already revoked (or does not exist)."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hash_token(token),
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(stmt)
        return result.rowcount == 1

    async def revoke_all_by_user(self, db: AsyncSession, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        await db.execute(stmt)


refresh_token_repo = RefreshTokenRepository()
