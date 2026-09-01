"""Create storage for replaceable corpus versions.

Revision ID: 0002_corpus_versions
Revises: 0001_initial_empty_schema
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_corpus_versions"
down_revision = "0001_initial_empty_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpus_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "product_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "corpus_version_id",
            sa.Integer(),
            sa.ForeignKey("corpus_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=False),
        sa.UniqueConstraint("corpus_version_id", "product_id"),
    )


def downgrade() -> None:
    op.drop_table("product_records")
    op.drop_table("corpus_versions")
