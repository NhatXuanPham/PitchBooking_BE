from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.enum import UserRole


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MeResponse(UserResponse):
    pass
