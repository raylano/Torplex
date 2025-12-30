"""add_absolute_episode_number

Revision ID: 003
Revises: 002
Create Date: 2025-12-30 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add absolute_episode_number column to episodes table
    op.add_column('episodes', sa.Column('absolute_episode_number', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove absolute_episode_number column from episodes table
    op.drop_column('episodes', 'absolute_episode_number')
