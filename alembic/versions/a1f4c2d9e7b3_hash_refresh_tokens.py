"""hash refresh tokens at rest

Revision ID: a1f4c2d9e7b3
Revises: 8003e44a6833
Create Date: 2026-10-24 21:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f4c2d9e7b3'
down_revision = '8003e44a6833'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('refresh_tokens', sa.Column('token_hash', sa.String(length=64), nullable=True))
    # Hash existing tokens in place so current sessions keep working.
    # Matches app.core.security.hash_token: sha256(utf-8 bytes) as lowercase hex.
    op.execute(
        "UPDATE refresh_tokens "
        "SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')"
    )
    op.alter_column('refresh_tokens', 'token_hash', nullable=False)
    op.create_index(
        op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True
    )
    op.drop_index(op.f('ix_refresh_tokens_token'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'token')

    # Normalize stored emails to lowercase (the app already lowercases on create)
    op.execute("UPDATE users SET email = lower(trim(email)) WHERE email <> lower(trim(email))")


def downgrade() -> None:
    # Raw tokens cannot be recovered from hashes: existing sessions are dropped.
    op.execute("DELETE FROM refresh_tokens")
    op.add_column('refresh_tokens', sa.Column('token', sa.String(length=512), nullable=False))
    op.create_index(op.f('ix_refresh_tokens_token'), 'refresh_tokens', ['token'], unique=True)
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'token_hash')
