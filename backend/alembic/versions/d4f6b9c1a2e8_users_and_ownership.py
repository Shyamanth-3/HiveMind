"""users table + projects.owner_id (authentication and resource ownership)

Additive only: nothing is dropped or rewritten. Existing projects keep owner_id NULL (unowned = visible to nobody
until an operator assigns them: see docs/PROJECT-STATUS.md, Phase 7).

Revision ID: d4f6b9c1a2e8
Revises: c3d5a8e2f714
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4f6b9c1a2e8'
down_revision: Union[str, Sequence[str], None] = 'c3d5a8e2f714'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.add_column('projects', sa.Column('owner_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_projects_owner_id_users', 'projects', 'users', ['owner_id'], ['id'])
    op.create_index('ix_projects_owner_id', 'projects', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_projects_owner_id', table_name='projects')
    op.drop_constraint('fk_projects_owner_id_users', 'projects', type_='foreignkey')
    op.drop_column('projects', 'owner_id')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
