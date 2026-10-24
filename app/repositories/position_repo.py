from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enum import PitchType, SportType
from app.models.position import Position

DEFAULT_POSITIONS = [
    # Sân 5 (Futsal / Phủi sân 5)
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_5, "code": "GK", "name": "Thủ môn", "description": "Goalkeeper sân 5"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_5, "code": "FIXO", "name": "Thòng / Fixo", "description": "Hậu vệ thòng / Fixo"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_5, "code": "ALA_L", "name": "Ala trái", "description": "Tiền vệ cánh trái sân 5"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_5, "code": "ALA_R", "name": "Ala phải", "description": "Tiền vệ cánh phải sân 5"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_5, "code": "PIVOT", "name": "Cắm / Pivot", "description": "Tiền đạo cắm sân 5"},

    # Sân 7 (Phủi sân 7)
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_7, "code": "GK", "name": "Thủ môn", "description": "Thủ môn sân 7"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_7, "code": "THONG", "name": "Hậu vệ thòng", "description": "Hậu vệ quét / trung vệ thòng sân 7"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_7, "code": "CANH_L", "name": "Cánh trái", "description": "Hậu vệ / Tiền vệ cánh trái sân 7"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_7, "code": "CANH_R", "name": "Cánh phải", "description": "Hậu vệ / Tiền vệ cánh phải sân 7"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_7, "code": "GIUA", "name": "Tiền vệ giữa", "description": "Tiền vệ trung tâm điều tiết sân 7"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_7, "code": "CAM", "name": "Tiền đạo cắm", "description": "Tiền đạo mục tiêu sân 7"},

    # Sân 11
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "GK", "name": "Thủ môn", "description": "Goalkeeper"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "CB", "name": "Trung vệ", "description": "Center Back"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "LB", "name": "Hậu vệ cánh trái", "description": "Left Back"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "RB", "name": "Hậu vệ cánh phải", "description": "Right Back"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "CDM", "name": "Tiền vệ phòng ngự", "description": "Defensive Midfielder"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "CM", "name": "Tiền vệ trung tâm", "description": "Central Midfielder"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "CAM", "name": "Tiền vệ tấn công", "description": "Attacking Midfielder"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "ST", "name": "Tiền đạo cắm", "description": "Striker"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "LW", "name": "Tiền đạo cánh trái", "description": "Left Winger"},
    {"sport_type": SportType.FOOTBALL, "pitch_type": PitchType.PITCH_11, "code": "RW", "name": "Tiền đạo cánh phải", "description": "Right Winger"},
]


class PositionRepository:
    async def get_all(
        self,
        db: AsyncSession,
        sport_type: SportType | None = None,
        pitch_type: PitchType | None = None,
    ) -> list[Position]:
        stmt = select(Position)
        if sport_type:
            stmt = stmt.where(Position.sport_type == sport_type)
        if pitch_type:
            stmt = stmt.where(Position.pitch_type == pitch_type)
        stmt = stmt.order_by(Position.pitch_type, Position.id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, position_ids: list[int]) -> list[Position]:
        if not position_ids:
            return []
        stmt = select(Position).where(Position.id.in_(position_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(
        self,
        db: AsyncSession,
        code: str,
        pitch_type: PitchType,
        sport_type: SportType = SportType.FOOTBALL,
    ) -> Position | None:
        stmt = select(Position).where(
            Position.code == code,
            Position.pitch_type == pitch_type,
            Position.sport_type == sport_type,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def seed_default_positions(self, db: AsyncSession) -> list[Position]:
        created = []
        for pos_data in DEFAULT_POSITIONS:
            stmt = select(Position).where(
                Position.sport_type == pos_data["sport_type"],
                Position.pitch_type == pos_data["pitch_type"],
                Position.code == pos_data["code"],
            )
            res = await db.execute(stmt)
            if not res.scalar_one_or_none():
                pos = Position(**pos_data)
                db.add(pos)
                created.append(pos)
        await db.flush()
        return created


position_repo = PositionRepository()
