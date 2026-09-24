"""Add title, description, details to tasks (Phase 1: persist Builder output)

Revision ID: a1c4e7d90b12
Revises: ec1377b20fa7
Create Date: 2026-09-23 21:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1c4e7d90b12'
down_revision: Union[str, Sequence[str], None] = 'ec1377b20fa7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('title', sa.String(length=255), nullable=True))
    op.add_column('tasks', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('tasks', sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                                     comment='Builder extras: priority, estimated_complexity, required_files, acceptance_criteria'))


def downgrade() -> None:
    op.drop_column('tasks', 'details')
    op.drop_column('tasks', 'description')
    op.drop_column('tasks', 'title')
