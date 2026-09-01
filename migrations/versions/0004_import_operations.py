"""Persist resumable corpus import operations.

Revision ID: 0004_import_operations
Revises: 0003_import_safety
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_import_operations"
down_revision = "0003_import_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_operations",
        sa.Column("operation_id", sa.String(length=32), primary_key=True),
        sa.Column("snapshot_name", sa.String(length=255), nullable=False),
        sa.Column("corpus_version_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("activation_status", sa.String(length=16), nullable=False),
        sa.Column("cleanup_status", sa.String(length=16), nullable=False),
        sa.Column("report_status", sa.String(length=16), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["corpus_version_id"], ["corpus_versions.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("import_operations")
