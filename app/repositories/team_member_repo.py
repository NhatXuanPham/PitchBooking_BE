from datetime import datetime, timezone
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enum import TeamMemberStatus, TeamRole
from app.models.position import Position
from app.models.team_member import TeamMember
from app.models.team_member_position import TeamMemberPosition



class TeamMemberRepository:
    async def create(
        self,
        db: AsyncSession,
        team_id: int,
        user_id: int,
        role: TeamRole = TeamRole.MEMBER,
        status: TeamMemberStatus = TeamMemberStatus.ACTIVE,
    ) -> TeamMember:
        member = TeamMember(
            team_id=team_id,
            user_id=user_id,
            role=role,
            status=status,
            joined_at=datetime.now(timezone.utc),
        )
        db.add(member)
        await db.flush()
        return member

    async def get_by_id(self, db: AsyncSession, member_id: int) -> TeamMember | None:
        stmt = (
            select(TeamMember)
            .options(
                selectinload(TeamMember.position_associations).joinedload(TeamMemberPosition.position),
                selectinload(TeamMember.user),
            )
            .where(TeamMember.id == member_id)
            .execution_options(populate_existing=True)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


    async def get_by_team_and_user(
        self,
        db: AsyncSession,
        team_id: int,
        user_id: int,
    ) -> TeamMember | None:
        stmt = (
            select(TeamMember)
            .options(
                selectinload(TeamMember.position_associations).joinedload(TeamMemberPosition.position),
                selectinload(TeamMember.user),
            )
            .where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_team(self, db: AsyncSession, team_id: int) -> list[TeamMember]:
        stmt = (
            select(TeamMember)
            .options(
                selectinload(TeamMember.position_associations).joinedload(TeamMemberPosition.position),
                selectinload(TeamMember.user),
            )
            .where(TeamMember.team_id == team_id)
            .order_by(
                # Order: LEADER first, then VICE_LEADER, then MEMBER, then joined_at
                TeamMember.role.desc(),
                TeamMember.joined_at.asc(),
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_user(self, db: AsyncSession, user_id: int) -> list[TeamMember]:
        stmt = (
            select(TeamMember)
            .options(
                selectinload(TeamMember.position_associations).joinedload(TeamMemberPosition.position),
                selectinload(TeamMember.team),
            )
            .where(TeamMember.user_id == user_id)
            .order_by(TeamMember.joined_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def set_positions(
        self,
        db: AsyncSession,
        team_member_id: int,
        position_ids: list[int],
        primary_position_id: int | None = None,
    ) -> None:
        await db.execute(
            delete(TeamMemberPosition).where(
                TeamMemberPosition.team_member_id == team_member_id
            )
        )
        unique_pos_ids = list(dict.fromkeys(position_ids))
        for pos_id in unique_pos_ids:
            is_primary = (pos_id == primary_position_id) if primary_position_id else False
            assoc = TeamMemberPosition(
                team_member_id=team_member_id,
                position_id=pos_id,
                is_primary=is_primary,
            )
            db.add(assoc)
        await db.flush()




    async def update_role(
        self,
        db: AsyncSession,
        member: TeamMember,
        new_role: TeamRole,
    ) -> TeamMember:
        member.role = new_role
        db.add(member)
        await db.flush()
        return member

    async def delete(self, db: AsyncSession, member: TeamMember) -> None:
        await db.delete(member)
        await db.flush()


team_member_repo = TeamMemberRepository()
