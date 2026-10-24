from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enum import PitchType, SportType, TeamMemberStatus, TeamRole


class PositionResponse(BaseModel):
    id: int
    sport_type: SportType
    pitch_type: PitchType
    code: str
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class TeamMemberPositionResponse(BaseModel):
    position_id: int
    sport_type: SportType
    pitch_type: PitchType
    code: str
    name: str
    is_primary: bool = False



    model_config = {"from_attributes": True}



class TeamMemberResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    role: TeamRole
    status: TeamMemberStatus
    joined_at: datetime
    positions: list[TeamMemberPositionResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    avatar_url: str | None = None
    my_position_ids: list[int] = Field(default_factory=list)


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    avatar_url: str | None = None


class TeamResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    avatar_url: str | None = None
    created_by_id: int
    is_active: bool = True
    members_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamDetailResponse(TeamResponse):
    members: list[TeamMemberResponse] = Field(default_factory=list)
    my_role: TeamRole | None = None


class AddMemberRequest(BaseModel):
    user_id: int | None = None
    identifier: str | None = Field(None, description="Username or email of the user to add")
    role: TeamRole = TeamRole.MEMBER
    position_ids: list[int] = Field(default_factory=list)


class UpdateMemberRoleRequest(BaseModel):
    role: TeamRole


class UpdateMemberPositionsRequest(BaseModel):
    position_ids: list[int] = Field(default_factory=list)
    primary_position_id: int | None = None
