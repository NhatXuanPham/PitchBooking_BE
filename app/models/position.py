from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enum import PitchType, SportType


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport_type: Mapped[SportType] = mapped_column(
        String(20),
        default=SportType.FOOTBALL,
        nullable=False,
        index=True,
    )
    pitch_type: Mapped[PitchType] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    member_associations: Mapped[list["TeamMemberPosition"]] = relationship(
        back_populates="position",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("sport_type", "pitch_type", "code", name="uq_positions_sport_pitch_code"),
    )
