"""Initial migration

Revision ID: 31ac285a6970
Revises: 
Create Date: 2026-07-06 18:32:34.462344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '31ac285a6970'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the base schema (everything that existed before agent_memories)."""
    op.create_table('projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('owner', sa.String(length=100), nullable=False),
        sa.Column('goal_summary', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('goal', sa.Text(), nullable=False),
        sa.Column('plan_text', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('success_criteria', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False, comment='Task type: plan, breakdown, research, build, review'),
        sa.Column('assigned_agent', sa.String(length=50), nullable=False, comment='Backend role key: ceo_agent, pm_agent, etc.'),
        sa.Column('depends_on', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='List of task IDs this task depends on'),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False, comment='e.g. run_created, plan_ready, task_completed'),
        sa.Column('agent', sa.String(length=50), nullable=True, comment='Backend role key, e.g., ceo_agent (null for system events)'),
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=False, comment='Event-specific data'),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('memory_chunks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding_dimensions', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False, comment='e.g. web_search:bakery_website_best_practices'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('agent_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('agent', sa.String(length=50), nullable=False, comment='Backend role key'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.String(length=20), nullable=False, comment='success, retried, failed'),
        sa.Column('model', sa.String(length=50), nullable=False, comment='e.g. gemini-2.0-flash'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('agent_logs', 'memory_chunks', 'events', 'tasks', 'runs', 'projects'):
        op.drop_table(table)
