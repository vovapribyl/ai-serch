"""Initial empty schema.

Revision ID: 0001_initial_empty_schema
Revises:
Create Date: 2026-08-31
"""

from alembic import op

revision = "0001_initial_empty_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
