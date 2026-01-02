"""Add is_airing field to media_items

Revision ID: 001_add_is_airing
Revises: 
Create Date: 2024-12-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_is_airing'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_airing column with default False
    op.add_column('media_items', sa.Column('is_airing', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('media_items', 'is_airing')
