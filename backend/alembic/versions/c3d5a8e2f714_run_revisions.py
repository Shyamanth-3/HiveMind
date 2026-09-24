"""Guardian revision loop: run_revisions table, tasks.revision_number

Revision ID: c3d5a8e2f714
Revises: b7e2f1a93c55
Create Date: 2026-09-24 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d5a8e2f714'
down_revision: Union[str, Sequence[str], None] = 'b7e2f1a93c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = "'requested', 'revised', 'approved', 'needs_revision', 'rejected', 'failed'"


def upgrade() -> None:
    op.create_table(
        'run_revisions',
        sa.Column('id', sa.String(length=36), nullable=False,
                  comment='Deterministic: uuid5(run_id : source_review_event_id : revision_number)'),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('source_review_event_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('feedback', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('requested_changes', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('tasks_event_id', sa.String(length=36), nullable=True,
                  comment='tasks.generated event with the Builder output for this revision'),
        sa.Column('review_event_id', sa.String(length=36), nullable=True,
                  comment="review.completed event that judged this revision's output"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'revision_number', name='uq_run_revisions_run_number'),
        sa.CheckConstraint('revision_number >= 1', name='ck_run_revisions_number'),
        sa.CheckConstraint(f'status IN ({STATUSES})', name='ck_run_revisions_status'),
    )
    op.create_index('ix_run_revisions_run_id', 'run_revisions', ['run_id'])
    op.add_column('tasks', sa.Column(
        'revision_number', sa.Integer(), server_default='0', nullable=False,
        comment='0 = original Builder output; N = output of Guardian-requested revision N. Current set = highest.'))


def downgrade() -> None:
    op.drop_column('tasks', 'revision_number')
    op.drop_index('ix_run_revisions_run_id', table_name='run_revisions')
    op.drop_table('run_revisions')
