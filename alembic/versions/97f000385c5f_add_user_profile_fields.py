"""add_user_profile_fields

Revision ID: 97f000385c5f
Revises: a1f4c2d9e7b3
Create Date: 2026-10-25 00:54:47.944916

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '97f000385c5f'
down_revision = 'a1f4c2d9e7b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('full_name', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('phone_number', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('address', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('date_of_birth', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('gender', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('interests', sa.JSON(), nullable=True))
    op.create_index(op.f('ix_users_phone_number'), 'users', ['phone_number'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_phone_number'), table_name='users')
    op.drop_column('users', 'interests')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'gender')
    op.drop_column('users', 'date_of_birth')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'address')
    op.drop_column('users', 'phone_number')
    op.drop_column('users', 'full_name')
