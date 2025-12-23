"""Add alternative_titles column to media_items

Revision ID: 002_add_alternative_titles
Revises: 001_add_is_airing
Create Date: 2025-12-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_alternative_titles'
down_revision = '001_add_is_airing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('media_items', sa.Column('alternative_titles', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('media_items', 'alternative_titles')
