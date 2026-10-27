from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user_repo import user_repo
from app.schemas.user_schema import UserUpdateRequest


class UserService:
    async def get_me(self, db: AsyncSession, user_id: int | str) -> User:
        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user = await user_repo.get_by_id(db, user_id_int)
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
        return user

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> User:
        user = await user_repo.get_by_id(db, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def update_me(
        self,
        db: AsyncSession,
        user_id: int | str,
        data: UserUpdateRequest,
    ) -> User:
        user = await self.get_me(db, user_id)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return user

        user = await user_repo.update(db, user, **update_data)
        await db.commit()
        await db.refresh(user)
        return user


user_service = UserService()

