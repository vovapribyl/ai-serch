"""Persist Gate 4 result axes for completed evaluation examples.

Revision ID: 0006_gate4_result_axes
Revises: 0005_gate3_search
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_gate4_result_axes"
down_revision = "0005_gate3_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluation_examples", sa.Column("query_outcome", sa.String(length=32)))
    op.add_column("evaluation_examples", sa.Column("candidate_relation", sa.String(length=32)))


def downgrade() -> None:
    op.drop_column("evaluation_examples", "candidate_relation")
    op.drop_column("evaluation_examples", "query_outcome")
