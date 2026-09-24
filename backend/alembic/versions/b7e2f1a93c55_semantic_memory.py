"""Semantic memory: 384-d embeddings, project scope, provenance, dedup, HNSW index

Revision ID: b7e2f1a93c55
Revises: a1c4e7d90b12
Create Date: 2026-09-23 23:10:00

The embedding model changed (Qwen3-Embedding-8B/4096 -> BAAI/bge-small-en-v1.5/384). Vectors of
different sizes/models are not comparable, so this migration refuses to run when agent_memories
has rows instead of truncating, padding or silently dropping them: re-embed or clear them first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7e2f1a93c55'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7d90b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TYPES = "'fact', 'decision', 'preference', 'context', 'lesson'"


def upgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM agent_memories")).scalar()
    if rows:
        raise RuntimeError(
            f"agent_memories has {rows} rows embedded at 4096 dimensions. They cannot be converted to the "
            "new 384-d model. Re-embed them or DELETE them explicitly, then re-run the migration."
        )
    op.execute("ALTER TABLE agent_memories ALTER COLUMN embedding TYPE vector(384)")
    op.add_column('agent_memories', sa.Column('project_id', sa.String(length=36), nullable=False))
    op.add_column('agent_memories', sa.Column('source_event_id', sa.String(length=36), nullable=True))
    op.add_column('agent_memories', sa.Column('importance', sa.SmallInteger(), server_default='3', nullable=False))
    op.add_column('agent_memories', sa.Column('content_hash', sa.String(length=64), nullable=False))
    op.create_foreign_key('fk_agent_memories_project', 'agent_memories', 'projects', ['project_id'], ['id'])
    op.create_check_constraint('ck_agent_memories_type', 'agent_memories', f"memory_type IN ({TYPES})")
    op.create_check_constraint('ck_agent_memories_importance', 'agent_memories', "importance BETWEEN 1 AND 5")
    op.create_index('uq_agent_memories_scope_hash', 'agent_memories',
                    ['project_id', 'memory_type', 'content_hash'], unique=True)
    op.create_index('ix_agent_memories_embedding_hnsw', 'agent_memories', ['embedding'],
                    postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})


def downgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM agent_memories")).scalar()
    if rows:
        raise RuntimeError(f"agent_memories has {rows} rows; refusing to downgrade the vector dimension.")
    op.drop_index('ix_agent_memories_embedding_hnsw', table_name='agent_memories')
    op.drop_index('uq_agent_memories_scope_hash', table_name='agent_memories')
    op.drop_constraint('ck_agent_memories_importance', 'agent_memories', type_='check')
    op.drop_constraint('ck_agent_memories_type', 'agent_memories', type_='check')
    op.drop_constraint('fk_agent_memories_project', 'agent_memories', type_='foreignkey')
    op.drop_column('agent_memories', 'content_hash')
    op.drop_column('agent_memories', 'importance')
    op.drop_column('agent_memories', 'source_event_id')
    op.drop_column('agent_memories', 'project_id')
    op.execute("ALTER TABLE agent_memories ALTER COLUMN embedding TYPE vector(4096)")
