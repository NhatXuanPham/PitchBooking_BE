from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TeamMemberPosition(Base):
    """Association table between TeamMember and Position with additional metadata"""
    __tablename__ = "team_member_positions"

    team_member_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("team_members.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("positions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    team_member: Mapped["TeamMember"] = relationship(back_populates="position_associations")
    position: Mapped["Position"] = relationship(back_populates="member_associations", lazy="joined")
