from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enum import PitchType, SportType, TeamMemberStatus, TeamRole
from app.models.team import Team
from app.models.team_member import TeamMember
from app.repositories.position_repo import position_repo
from app.repositories.team_member_repo import team_member_repo
from app.repositories.team_repo import team_repo
from app.repositories.user_repo import user_repo
from app.schemas.team_schema import (
    AddMemberRequest,
    PositionResponse,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberPositionResponse,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdateRequest,
)


class TeamService:
    def _format_member_response(self, member: TeamMember) -> TeamMemberResponse:
        positions_list = []
        for assoc in member.position_associations:
            if assoc.position:
                positions_list.append(
                    TeamMemberPositionResponse(
                        position_id=assoc.position.id,
                        sport_type=assoc.position.sport_type,
                        pitch_type=assoc.position.pitch_type,
                        code=assoc.position.code,
                        name=assoc.position.name,
                        is_primary=assoc.is_primary,
                    )
                )

        return TeamMemberResponse(
            id=member.id,
            user_id=member.user_id,
            username=member.user.username if member.user else "",
            email=member.user.email if member.user else "",
            role=member.role,
            status=member.status,
            joined_at=member.joined_at,
            positions=positions_list,
        )

    async def create_team(
        self,
        db: AsyncSession,
        user_id: int,
        data: TeamCreateRequest,
    ) -> TeamResponse:
        user = await user_repo.get_by_id(db, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found or inactive",
            )

        team = await team_repo.create(
            db,
            name=data.name,
            created_by_id=user_id,
            description=data.description,
            avatar_url=data.avatar_url,
        )

        leader_member = await team_member_repo.create(
            db,
            team_id=team.id,
            user_id=user_id,
            role=TeamRole.LEADER,
            status=TeamMemberStatus.ACTIVE,
        )

        if data.my_position_ids:
            valid_positions = await position_repo.get_by_ids(db, data.my_position_ids)
            valid_ids = [p.id for p in valid_positions]
            if valid_ids:
                await team_member_repo.set_positions(db, leader_member.id, valid_ids)

        await db.commit()
        await db.refresh(team)

        return TeamResponse(
            id=team.id,
            name=team.name,
            description=team.description,
            avatar_url=team.avatar_url,
            created_by_id=team.created_by_id,
            is_active=team.is_active,
            members_count=1,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )

    async def get_team_detail(
        self,
        db: AsyncSession,
        team_id: int,
        current_user_id: int | None = None,
    ) -> TeamDetailResponse:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        members = await team_member_repo.list_by_team(db, team_id)
        members_response = [self._format_member_response(m) for m in members]

        my_role = None
        if current_user_id:
            for m in members:
                if m.user_id == current_user_id:
                    my_role = m.role
                    break

        return TeamDetailResponse(
            id=team.id,
            name=team.name,
            description=team.description,
            avatar_url=team.avatar_url,
            created_by_id=team.created_by_id,
            is_active=team.is_active,
            members_count=len(members),
            created_at=team.created_at,
            updated_at=team.updated_at,
            members=members_response,
            my_role=my_role,
        )

    async def list_teams(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
    ) -> list[TeamResponse]:
        results = await team_repo.list_teams(db, skip=skip, limit=limit, search=search)
        return [
            TeamResponse(
                id=team.id,
                name=team.name,
                description=team.description,
                avatar_url=team.avatar_url,
                created_by_id=team.created_by_id,
                is_active=team.is_active,
                members_count=members_count,
                created_at=team.created_at,
                updated_at=team.updated_at,
            )
            for team, members_count in results
        ]

    async def list_my_teams(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> list[TeamResponse]:
        results = await team_repo.list_by_user(db, user_id)
        return [
            TeamResponse(
                id=team.id,
                name=team.name,
                description=team.description,
                avatar_url=team.avatar_url,
                created_by_id=team.created_by_id,
                is_active=team.is_active,
                members_count=members_count,
                created_at=team.created_at,
                updated_at=team.updated_at,
            )
            for team, members_count in results
        ]

    async def update_team(
        self,
        db: AsyncSession,
        team_id: int,
        current_user_id: int,
        data: TeamUpdateRequest,
    ) -> TeamResponse:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        membership = await team_member_repo.get_by_team_and_user(db, team_id, current_user_id)
        if not membership or membership.role not in (TeamRole.LEADER, TeamRole.VICE_LEADER):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team leader or vice leader can update team details",
            )

        update_dict = {}
        if data.name is not None:
            update_dict["name"] = data.name
        if data.description is not None:
            update_dict["description"] = data.description
        if data.avatar_url is not None:
            update_dict["avatar_url"] = data.avatar_url

        if update_dict:
            await team_repo.update(db, team, **update_dict)
            await db.commit()
            await db.refresh(team)

        members = await team_member_repo.list_by_team(db, team_id)
        return TeamResponse(
            id=team.id,
            name=team.name,
            description=team.description,
            avatar_url=team.avatar_url,
            created_by_id=team.created_by_id,
            is_active=team.is_active,
            members_count=len(members),
            created_at=team.created_at,
            updated_at=team.updated_at,
        )

    async def delete_team(
        self,
        db: AsyncSession,
        team_id: int,
        current_user_id: int,
    ) -> dict[str, str]:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        membership = await team_member_repo.get_by_team_and_user(db, team_id, current_user_id)
        if not membership or membership.role != TeamRole.LEADER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the team leader can delete the team",
            )

        await team_repo.delete(db, team)
        await db.commit()
        return {"message": "Team deleted successfully"}

    async def add_member(
        self,
        db: AsyncSession,
        team_id: int,
        current_user_id: int,
        data: AddMemberRequest,
    ) -> TeamMemberResponse:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        requester_membership = await team_member_repo.get_by_team_and_user(db, team_id, current_user_id)
        if not requester_membership or requester_membership.role not in (TeamRole.LEADER, TeamRole.VICE_LEADER):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team leader or vice leader can add members",
            )

        target_user = None
        if data.user_id:
            target_user = await user_repo.get_by_id(db, data.user_id)
        elif data.identifier:
            target_user = await user_repo.get_by_email_or_username(db, data.identifier)

        if not target_user or not target_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found or inactive",
            )

        existing = await team_member_repo.get_by_team_and_user(db, team_id, target_user.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this team",
            )

        if data.role == TeamRole.LEADER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add member directly as leader. Transfer leadership instead.",
            )

        if requester_membership.role == TeamRole.VICE_LEADER and data.role != TeamRole.MEMBER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vice leader can only add regular members",
            )


        member = await team_member_repo.create(
            db,
            team_id=team_id,
            user_id=target_user.id,
            role=data.role,
            status=TeamMemberStatus.ACTIVE,
        )
        member.user = target_user

        valid_positions = []
        if data.position_ids:
            valid_positions = await position_repo.get_by_ids(db, data.position_ids)
            valid_ids = [p.id for p in valid_positions]
            if valid_ids:
                await team_member_repo.set_positions(db, member.id, valid_ids)

        await db.commit()
        return TeamMemberResponse(
            id=member.id,
            user_id=target_user.id,
            username=target_user.username,
            email=target_user.email,
            role=member.role,
            status=member.status,
            joined_at=member.joined_at,
            positions=[
                TeamMemberPositionResponse(
                    position_id=p.id,
                    sport_type=p.sport_type,
                    pitch_type=p.pitch_type,
                    code=p.code,
                    name=p.name,
                    is_primary=False,
                )
                for p in valid_positions
            ],
        )

    async def update_member_role(
        self,
        db: AsyncSession,
        team_id: int,
        member_id: int,
        current_user_id: int,
        new_role: TeamRole,
    ) -> TeamMemberResponse:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        requester_membership = await team_member_repo.get_by_team_and_user(db, team_id, current_user_id)
        if not requester_membership or requester_membership.role != TeamRole.LEADER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the team leader can change member roles",
            )

        target_member = await team_member_repo.get_by_id(db, member_id)
        if not target_member or target_member.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team member not found in this team",
            )

        if target_member.id == requester_membership.id and new_role != TeamRole.LEADER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leader cannot demote themselves directly. Transfer leadership to another member.",
            )

        if new_role == TeamRole.LEADER:
            if target_member.id == requester_membership.id:
                return self._format_member_response(target_member)
            await team_member_repo.update_role(db, requester_membership, TeamRole.VICE_LEADER)
            await team_member_repo.update_role(db, target_member, TeamRole.LEADER)
        else:
            await team_member_repo.update_role(db, target_member, new_role)

        await db.commit()
        return self._format_member_response(target_member)

    async def update_member_positions(
        self,
        db: AsyncSession,
        team_id: int,
        member_id: int,
        current_user_id: int,
        position_ids: list[int],
        primary_position_id: int | None = None,
    ) -> TeamMemberResponse:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        target_member = await team_member_repo.get_by_id(db, member_id)
        if not target_member or target_member.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team member not found in this team",
            )

        requester_membership = await team_member_repo.get_by_team_and_user(db, team_id, current_user_id)
        if not requester_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this team",
            )

        is_self = target_member.user_id == current_user_id
        is_admin = requester_membership.role in (TeamRole.LEADER, TeamRole.VICE_LEADER)
        if not is_self and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied to update positions for this member",
            )

        valid_positions = await position_repo.get_by_ids(db, position_ids)
        valid_ids = [p.id for p in valid_positions]

        await team_member_repo.set_positions(
            db,
            team_member_id=target_member.id,
            position_ids=valid_ids,
            primary_position_id=primary_position_id,
        )

        await db.commit()
        return TeamMemberResponse(
            id=target_member.id,
            user_id=target_member.user_id,
            username=target_member.user.username if target_member.user else "",
            email=target_member.user.email if target_member.user else "",
            role=target_member.role,
            status=target_member.status,
            joined_at=target_member.joined_at,
            positions=[
                TeamMemberPositionResponse(
                    position_id=p.id,
                    sport_type=p.sport_type,
                    pitch_type=p.pitch_type,
                    code=p.code,
                    name=p.name,
                    is_primary=(p.id == primary_position_id) if primary_position_id else False,
                )
                for p in valid_positions
            ],
        )

    async def remove_member(
        self,
        db: AsyncSession,
        team_id: int,
        member_id: int,
        current_user_id: int,
    ) -> dict[str, str]:
        team = await team_repo.get_by_id(db, team_id)
        if not team or not team.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )

        target_member = await team_member_repo.get_by_id(db, member_id)
        if not target_member or target_member.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team member not found in this team",
            )

        requester_membership = await team_member_repo.get_by_team_and_user(db, team_id, current_user_id)
        if not requester_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this team",
            )

        is_self = target_member.user_id == current_user_id

        if is_self:
            if target_member.role == TeamRole.LEADER:
                all_members = await team_member_repo.list_by_team(db, team_id)
                if len(all_members) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Leader cannot leave while team has other members. Transfer leadership first.",
                    )
                await team_repo.delete(db, team)
                await db.commit()
                return {"message": "You left and team was deleted as you were the only member"}

            await team_member_repo.delete(db, target_member)
            await db.commit()
            return {"message": "Left the team successfully"}
        else:
            if requester_membership.role == TeamRole.VICE_LEADER:
                if target_member.role != TeamRole.MEMBER:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Vice leader can only remove regular members",
                    )

            elif requester_membership.role != TeamRole.LEADER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only team leader or vice leader can remove members",
                )

            await team_member_repo.delete(db, target_member)
            await db.commit()
            return {"message": "Member removed from the team"}

    async def list_positions(
        self,
        db: AsyncSession,
        sport_type: SportType | None = None,
        pitch_type: PitchType | None = None,
    ) -> list[PositionResponse]:
        positions = await position_repo.get_all(db, sport_type=sport_type, pitch_type=pitch_type)
        if not positions and not sport_type and not pitch_type:
            positions = await position_repo.seed_default_positions(db)
            await db.commit()
        return [PositionResponse.model_validate(p) for p in positions]


team_service = TeamService()
