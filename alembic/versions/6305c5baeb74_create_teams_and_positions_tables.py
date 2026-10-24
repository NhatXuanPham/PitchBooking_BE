"""create_teams_and_positions_tables

Revision ID: 6305c5baeb74
Revises: 97f000385c5f
Create Date: 2026-10-24 22:12:30.075479

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6305c5baeb74'
down_revision = '97f000385c5f'
branch_labels = None
depends_on = None



def upgrade() -> None:
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sport_type', sa.String(length=20), server_default='FOOTBALL', nullable=False),
        sa.Column('pitch_type', sa.String(length=20), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sport_type', 'pitch_type', 'code', name='uq_positions_sport_pitch_code'),
    )
    op.create_index(op.f('ix_positions_code'), 'positions', ['code'], unique=False)
    op.create_index(op.f('ix_positions_pitch_type'), 'positions', ['pitch_type'], unique=False)
    op.create_index(op.f('ix_positions_sport_type'), 'positions', ['sport_type'], unique=False)

    positions_table = sa.table(
        'positions',
        sa.column('sport_type', sa.String),
        sa.column('pitch_type', sa.String),
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
    )
    op.bulk_insert(
        positions_table,
        [
            # Sân 5 (Futsal / Phủi sân 5)
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_5", "code": "GK", "name": "Thủ môn", "description": "Goalkeeper sân 5"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_5", "code": "FIXO", "name": "Thòng / Fixo", "description": "Hậu vệ thòng / Fixo"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_5", "code": "ALA_L", "name": "Ala trái", "description": "Tiền vệ cánh trái sân 5"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_5", "code": "ALA_R", "name": "Ala phải", "description": "Tiền vệ cánh phải sân 5"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_5", "code": "PIVOT", "name": "Cắm / Pivot", "description": "Tiền đạo cắm sân 5"},

            # Sân 7 (Phủi sân 7)
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_7", "code": "GK", "name": "Thủ môn", "description": "Thủ môn sân 7"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_7", "code": "THONG", "name": "Hậu vệ thòng", "description": "Hậu vệ quét / trung vệ thòng sân 7"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_7", "code": "CANH_L", "name": "Cánh trái", "description": "Hậu vệ / Tiền vệ cánh trái sân 7"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_7", "code": "CANH_R", "name": "Cánh phải", "description": "Hậu vệ / Tiền vệ cánh phải sân 7"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_7", "code": "GIUA", "name": "Tiền vệ giữa", "description": "Tiền vệ trung tâm điều tiết sân 7"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_7", "code": "CAM", "name": "Tiền đạo cắm", "description": "Tiền đạo mục tiêu sân 7"},

            # Sân 11
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "GK", "name": "Thủ môn", "description": "Goalkeeper"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "CB", "name": "Trung vệ", "description": "Center Back"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "LB", "name": "Hậu vệ cánh trái", "description": "Left Back"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "RB", "name": "Hậu vệ cánh phải", "description": "Right Back"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "CDM", "name": "Tiền vệ phòng ngự", "description": "Defensive Midfielder"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "CM", "name": "Tiền vệ trung tâm", "description": "Central Midfielder"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "CAM", "name": "Tiền vệ tấn công", "description": "Attacking Midfielder"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "ST", "name": "Tiền đạo cắm", "description": "Striker"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "LW", "name": "Tiền đạo cánh trái", "description": "Left Winger"},
            {"sport_type": "FOOTBALL", "pitch_type": "PITCH_11", "code": "RW", "name": "Tiền đạo cánh phải", "description": "Right Winger"},
        ]
    )

    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.String(length=255), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_teams_created_by_id'), 'teams', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_teams_name'), 'teams', ['name'], unique=False)

    op.create_table(
        'team_members',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_members_team_user'),
    )
    op.create_index(op.f('ix_team_members_team_id'), 'team_members', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_members_user_id'), 'team_members', ['user_id'], unique=False)
    op.create_index('uq_team_leader', 'team_members', ['team_id'], unique=True, postgresql_where=sa.text("role = 'LEADER'"))

    op.create_table(
        'team_member_positions',
        sa.Column('team_member_id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_member_id'], ['team_members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('team_member_id', 'position_id'),
    )


def downgrade() -> None:
    op.drop_table('team_member_positions')
    op.drop_index('uq_team_leader', table_name='team_members', postgresql_where=sa.text("role = 'LEADER'"))
    op.drop_index(op.f('ix_team_members_user_id'), table_name='team_members')
    op.drop_index(op.f('ix_team_members_team_id'), table_name='team_members')
    op.drop_table('team_members')
    op.drop_index(op.f('ix_teams_name'), table_name='teams')
    op.drop_index(op.f('ix_teams_created_by_id'), table_name='teams')
    op.drop_table('teams')
    op.drop_index(op.f('ix_positions_sport_type'), table_name='positions')
    op.drop_index(op.f('ix_positions_pitch_type'), table_name='positions')
    op.drop_index(op.f('ix_positions_code'), table_name='positions')
    op.drop_table('positions')
