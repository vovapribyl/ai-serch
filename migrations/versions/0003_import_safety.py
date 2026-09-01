"""Persist import operation and image integrity metadata.

Revision ID: 0003_import_safety
Revises: 0002_corpus_versions
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_import_safety"
down_revision = "0002_corpus_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("corpus_versions", sa.Column("operation_id", sa.String(length=32), nullable=True))
    op.execute("UPDATE corpus_versions SET operation_id = md5(random()::text) WHERE operation_id IS NULL")
    op.alter_column("corpus_versions", "operation_id", nullable=False)
    op.create_unique_constraint("uq_corpus_versions_operation_id", "corpus_versions", ["operation_id"])
    op.add_column("product_records", sa.Column("image_sha256", sa.String(length=64), nullable=True))
    op.add_column("product_records", sa.Column("image_format", sa.String(length=16), nullable=True))
    op.execute("UPDATE product_records SET image_sha256 = '', image_format = 'UNKNOWN'")
    op.alter_column("product_records", "image_sha256", nullable=False)
    op.alter_column("product_records", "image_format", nullable=False)


def downgrade() -> None:
    op.drop_column("product_records", "image_format")
    op.drop_column("product_records", "image_sha256")
    op.drop_constraint("uq_corpus_versions_operation_id", "corpus_versions", type_="unique")
    op.drop_column("corpus_versions", "operation_id")
