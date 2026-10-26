from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enum import TeamMemberStatus, TeamRole

if TYPE_CHECKING:
    from app.models.team import Team
    from app.models.team_member_position import TeamMemberPosition
    from app.models.user import User


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[TeamRole] = mapped_column(
        String(20),
        default=TeamRole.MEMBER,
        nullable=False,
    )
    status: Mapped[TeamMemberStatus] = mapped_column(
        String(20),
        default=TeamMemberStatus.ACTIVE,
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="team_memberships", lazy="joined")
    position_associations: Mapped[list["TeamMemberPosition"]] = relationship(
        back_populates="team_member",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        Index(
            "uq_team_leader",
            "team_id",
            unique=True,
            postgresql_where=(role == "LEADER"),
        ),
    )
