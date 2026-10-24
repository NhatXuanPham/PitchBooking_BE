from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.team import Team
from app.models.team_member import TeamMember


class TeamRepository:
    async def create(
        self,
        db: AsyncSession,
        name: str,
        created_by_id: int,
        description: str | None = None,
        avatar_url: str | None = None,
    ) -> Team:
        team = Team(
            name=name.strip(),
            created_by_id=created_by_id,
            description=description.strip() if description else None,
            avatar_url=avatar_url.strip() if avatar_url else None,
        )
        db.add(team)
        await db.flush()
        return team

    async def get_by_id(self, db: AsyncSession, team_id: int) -> Team | None:
        stmt = (
            select(Team)
            .options(
                selectinload(Team.members).selectinload(TeamMember.position_associations),
                selectinload(Team.creator),
            )
            .where(Team.id == team_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_teams(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
    ) -> list[tuple[Team, int]]:
        """List active teams with member count"""
        members_count_subq = (
            select(TeamMember.team_id, func.count(TeamMember.id).label("members_count"))
            .group_by(TeamMember.team_id)
            .subquery()
        )

        stmt = (
            select(
                Team,
                func.coalesce(members_count_subq.c.members_count, 0).label("members_count"),
            )
            .outerjoin(members_count_subq, Team.id == members_count_subq.c.team_id)
            .where(Team.is_active.is_(True))
        )

        if search and search.strip():
            stmt = stmt.where(Team.name.ilike(f"%{search.strip()}%"))

        stmt = stmt.order_by(Team.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def count_teams(self, db: AsyncSession, search: str | None = None) -> int:
        stmt = select(func.count(Team.id)).where(Team.is_active.is_(True))
        if search and search.strip():
            stmt = stmt.where(Team.name.ilike(f"%{search.strip()}%"))
        result = await db.execute(stmt)
        return result.scalar_one() or 0

    async def list_by_user(self, db: AsyncSession, user_id: int) -> list[tuple[Team, int]]:
        """List teams where the user is a member with member counts"""
        members_count_subq = (
            select(TeamMember.team_id, func.count(TeamMember.id).label("members_count"))
            .group_by(TeamMember.team_id)
            .subquery()
        )

        stmt = (
            select(
                Team,
                func.coalesce(members_count_subq.c.members_count, 0).label("members_count"),
            )
            .join(TeamMember, (Team.id == TeamMember.team_id) & (TeamMember.user_id == user_id))
            .outerjoin(members_count_subq, Team.id == members_count_subq.c.team_id)
            .where(Team.is_active.is_(True))
            .order_by(TeamMember.joined_at.desc())
        )
        result = await db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def update(self, db: AsyncSession, team: Team, **kwargs) -> Team:
        for key, value in kwargs.items():
            if hasattr(team, key) and value is not None:
                setattr(team, key, value.strip() if isinstance(value, str) else value)
        db.add(team)
        await db.flush()
        return team

    async def delete(self, db: AsyncSession, team: Team) -> None:
        await db.delete(team)
        await db.flush()


team_repo = TeamRepository()
