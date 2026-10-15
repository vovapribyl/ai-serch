"""Add the additive Gate 4 v2 candidate-labeling protocol.

Revision ID: 0007_gate4_candidate_annotations
Revises: 0006_gate4_result_axes
"""

import sqlalchemy as sa
from alembic import op


revision = "0007_gate4_candidate_annotations"
down_revision = "0006_gate4_result_axes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows are explicitly legacy; no action history is interpreted or rewritten.
    op.add_column(
        "evaluation_examples",
        sa.Column("protocol_version", sa.String(length=8), nullable=False, server_default="v1"),
    )
    op.create_table(
        "candidate_annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evaluation_example_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_candidate_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("variant_reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_example_id"], ["evaluation_examples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_candidate_id"], ["evaluation_candidates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("evaluation_example_id", "evaluation_candidate_id", name="uq_candidate_annotations_example_candidate"),
        sa.CheckConstraint("relation IN ('SAME_PRODUCT', 'VARIANT', 'UNRELATED', 'NOT_REVIEWED')", name="ck_candidate_annotations_relation"),
    )


def downgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM evaluation_examples WHERE protocol_version = 'v2') THEN
            RAISE EXCEPTION 'Cannot downgrade Gate 4 v2 while v2 evidence exists.';
        END IF;
    END $$;
    """)
    op.drop_table("candidate_annotations")
    op.drop_column("evaluation_examples", "protocol_version")
