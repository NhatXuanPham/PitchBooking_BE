from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class MeResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
