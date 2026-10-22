import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_otp import EmailOtp


class EmailOtpRepository:
    """
    Repository methods only flush; the calling service owns the transaction
    and is responsible for committing.
    """

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        code_hash: str,
        purpose: str,
        expires_at: datetime,
    ) -> EmailOtp:
        otp = EmailOtp(
            user_id=user_id,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        db.add(otp)
        await db.flush()
        return otp

    async def get_latest_active_otp(
        self,
        db: AsyncSession,
        user_id: int,
        purpose: str,
    ) -> EmailOtp | None:
        stmt = (
            select(EmailOtp)
            .where(
                EmailOtp.user_id == user_id,
                EmailOtp.purpose == purpose,
                EmailOtp.used_at.is_(None),
            )
            .order_by(EmailOtp.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_latest_otp(
        self,
        db: AsyncSession,
        user_id: int,
        purpose: str,
    ) -> EmailOtp | None:
        stmt = (
            select(EmailOtp)
            .where(
                EmailOtp.user_id == user_id,
                EmailOtp.purpose == purpose,
            )
            .order_by(EmailOtp.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def invalidate_otps(
        self,
        db: AsyncSession,
        user_id: int,
        purpose: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(EmailOtp)
            .where(
                EmailOtp.user_id == user_id,
                EmailOtp.purpose == purpose,
                EmailOtp.used_at.is_(None),
            )
            .values(used_at=now)
        )
        await db.execute(stmt)

    async def increment_attempts(
        self,
        db: AsyncSession,
        otp_id: uuid.UUID,
        max_attempts: int,
    ) -> int | None:
        """
        Atomically increment the attempt counter.
        Returns the new attempt count, or None if the OTP had already reached max attempts
        (prevents concurrent requests from bypassing the attempt limit).
        """
        stmt = (
            update(EmailOtp)
            .where(
                EmailOtp.id == otp_id,
                EmailOtp.attempts < max_attempts,
            )
            .values(attempts=EmailOtp.attempts + 1)
            .returning(EmailOtp.attempts)
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_as_used(
        self,
        db: AsyncSession,
        otp_id: uuid.UUID,
        max_attempts: int,
    ) -> bool:
        """
        Atomically consume an OTP. Returns False if the OTP was already used,
        expired or locked (e.g. consumed by a concurrent request).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(EmailOtp)
            .where(
                EmailOtp.id == otp_id,
                EmailOtp.used_at.is_(None),
                EmailOtp.expires_at > now,
                EmailOtp.attempts < max_attempts,
            )
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(stmt)
        return result.rowcount == 1


otp_repo = EmailOtpRepository()
