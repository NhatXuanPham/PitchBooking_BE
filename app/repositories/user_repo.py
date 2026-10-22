from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def _normalize_identifier(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip()
        return normalized.casefold() if normalized else None

    async def get_by_id(self, db: AsyncSession, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str | None) -> User | None:
        normalized_email = self._normalize_identifier(email)
        if not normalized_email:
            return None
        stmt = select(User).where(func.lower(User.email) == normalized_email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, db: AsyncSession, username: str) -> User | None:
        normalized_username = self._normalize_identifier(username)
        if not normalized_username:
            return None
        stmt = select(User).where(func.lower(User.username) == normalized_username)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_or_username(self, db: AsyncSession, identifier: str) -> User | None:
        normalized_identifier = self._normalize_identifier(identifier)
        if not normalized_identifier:
            return None
        # Usernames cannot contain '@', so an identifier with '@' is always an email.
        # Resolving to a single column avoids MultipleResultsFound on legacy data.
        if "@" in normalized_identifier:
            stmt = select(User).where(func.lower(User.email) == normalized_identifier)
        else:
            stmt = select(User).where(func.lower(User.username) == normalized_identifier)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, **kwargs) -> User:
        if "email" in kwargs and kwargs["email"]:
            kwargs["email"] = kwargs["email"].strip().lower()
        if "username" in kwargs and kwargs["username"]:
            kwargs["username"] = kwargs["username"].strip()
        user = User(**kwargs)
        db.add(user)
        # Flush only; the calling service owns the transaction and commits.
        await db.flush()
        return user

    async def update_password(self, db: AsyncSession, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        db.add(user)
        await db.flush()
        return user


user_repo = UserRepository()
