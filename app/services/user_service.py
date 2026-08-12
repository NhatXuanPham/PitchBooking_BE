from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user_repo import user_repo
from app.schemas.user_schema import UserResponse


class UserService:
    async def get_me(self, db: AsyncSession, user_id: str) -> User:
        try:
            user_id_int = int(user_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="User not found")

        user = await user_repo.get_by_id(db, user_id_int)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

user_service = UserService()
