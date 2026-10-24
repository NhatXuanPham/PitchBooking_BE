from fastapi import APIRouter, Depends, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token, verify_access_token
from app.models.enum import PitchType, SportType
from app.schemas.auth_schema import MessageResponse

from app.schemas.team_schema import (
    AddMemberRequest,
    PositionResponse,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
    UpdateMemberPositionsRequest,
    UpdateMemberRoleRequest,
)
from app.services.team_service import team_service

router = APIRouter(tags=["teams"])

oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user_id(payload: dict = Depends(verify_access_token)) -> int:
    return int(payload["sub"])


def get_optional_user_id(token: str | None = Depends(oauth2_optional)) -> int | None:
    if not token:
        return None
    try:
        payload = decode_token(token, token_type="access")
        return int(payload["sub"])
    except Exception:
        return None


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    sport_type: SportType | None = Query(None, description="Filter by sport (e.g. FOOTBALL)"),
    pitch_type: PitchType | None = Query(None, description="Filter by pitch format (e.g. PITCH_5, PITCH_7, PITCH_11)"),
    db: AsyncSession = Depends(get_db),
):
    return await team_service.list_positions(db, sport_type=sport_type, pitch_type=pitch_type)




@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: TeamCreateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new football team (clan). Creator automatically becomes the team LEADER."""
    return await team_service.create_team(db, user_id=user_id, data=data)


@router.get("/", response_model=list[TeamResponse])
async def list_teams(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="Search team by name"),
    db: AsyncSession = Depends(get_db),
):
    """List public active teams with search and pagination"""
    return await team_service.list_teams(db, skip=skip, limit=limit, search=search)


@router.get("/my-teams", response_model=list[TeamResponse])
async def list_my_teams(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """List all teams that the current user belongs to"""
    return await team_service.list_my_teams(db, user_id=user_id)


@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team_detail(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: int | None = Depends(get_optional_user_id),
):
    """Get team details, including roster members and player positions"""
    return await team_service.get_team_detail(db, team_id=team_id, current_user_id=current_user_id)


@router.put("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: int,
    data: TeamUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update team info (name, description, avatar). Leader or vice leader only."""
    return await team_service.update_team(db, team_id=team_id, current_user_id=user_id, data=data)


@router.delete("/{team_id}", response_model=MessageResponse)
async def delete_team(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Delete a team. Team leader only."""
    return await team_service.delete_team(db, team_id=team_id, current_user_id=user_id)


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    team_id: int,
    data: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Add a new member to the team (Leader or Vice Leader only)"""
    return await team_service.add_member(db, team_id=team_id, current_user_id=user_id, data=data)


@router.patch("/{team_id}/members/{member_id}/role", response_model=TeamMemberResponse)
async def update_member_role(
    team_id: int,
    member_id: int,
    data: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    Update member role (Leader only).
    Promote to VICE_LEADER, demote to MEMBER, or transfer leadership by assigning LEADER.
    """
    return await team_service.update_member_role(
        db,
        team_id=team_id,
        member_id=member_id,
        current_user_id=user_id,
        new_role=data.role,
    )


@router.put("/{team_id}/members/{member_id}/positions", response_model=TeamMemberResponse)
async def update_member_positions(
    team_id: int,
    member_id: int,
    data: UpdateMemberPositionsRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update positions/titles for a member (Member themselves, Leader, or Vice Leader)"""
    return await team_service.update_member_positions(
        db,
        team_id=team_id,
        member_id=member_id,
        current_user_id=user_id,
        position_ids=data.position_ids,
        primary_position_id=data.primary_position_id,
    )


@router.delete("/{team_id}/members/{member_id}", response_model=MessageResponse)
async def remove_member(
    team_id: int,
    member_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Remove a member from the team (Kick by leader/vice leader or leave by the member)"""
    return await team_service.remove_member(
        db,
        team_id=team_id,
        member_id=member_id,
        current_user_id=user_id,
    )
