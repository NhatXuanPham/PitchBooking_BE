from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_access_token
from app.schemas.user_schema import MeResponse, UserResponse
from app.services.user_service import user_service

router = APIRouter(tags=["users"])

@router.get("/me", response_model=MeResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_access_token),
):
    return await user_service.get_me(db, payload["sub"])
