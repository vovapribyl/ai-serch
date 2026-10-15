"""Persist only final Gate 4 v3 sessions and reproducible run snapshots.

Revision ID: 0008_gate4_multiphoto_v3
Revises: 0007_gate4_candidate_annotations
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_gate4_multiphoto_v3"
down_revision = "0007_gate4_candidate_annotations"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("evaluation_input_photos", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("evaluation_example_id", sa.Uuid(), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(length=64), nullable=False), sa.Column("is_primary", sa.Boolean(), nullable=False), sa.ForeignKeyConstraint(["evaluation_example_id"], ["evaluation_examples.id"], ondelete="CASCADE"), sa.UniqueConstraint("evaluation_example_id", "ordinal", name="uq_evaluation_input_photos_ordinal"))
    op.create_table("evaluation_run_snapshots", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("evaluation_example_id", sa.Uuid(), nullable=False), sa.Column("run_ordinal", sa.Integer(), nullable=False), sa.Column("model_revisions", sa.JSON(), nullable=False), sa.Column("photo_model_results", sa.JSON(), nullable=False), sa.ForeignKeyConstraint(["evaluation_example_id"], ["evaluation_examples.id"], ondelete="CASCADE"), sa.UniqueConstraint("evaluation_example_id", "run_ordinal", name="uq_evaluation_run_snapshots_ordinal"))

def downgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM evaluation_examples WHERE protocol_version = 'v3') THEN
            RAISE EXCEPTION 'Cannot downgrade Gate 4 v3 while v3 evidence exists.';
        END IF;
    END $$;
    """)
    op.drop_table("evaluation_run_snapshots")
    op.drop_table("evaluation_input_photos")
