"""Create isolated Gate 3 search and evaluation schema.

Revision ID: 0005_gate3_search
Revises: 0004_import_operations
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "0005_gate3_search"
down_revision = "0004_import_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "model_artifacts",
        sa.Column("model_key", sa.String(length=64), primary_key=True),
        sa.Column("repository_id", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("preprocessing_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "product_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corpus_version_id", sa.Integer(), nullable=False),
        sa.Column("product_record_id", sa.Integer(), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("vector", Vector(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["corpus_version_id"], ["corpus_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_record_id"], ["product_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_key"], ["model_artifacts.model_key"]),
        sa.UniqueConstraint(
            "corpus_version_id", "product_record_id", "model_key", name="uq_product_embeddings_model"
        ),
    )
    op.create_table(
        "evaluation_examples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("query_path", sa.String(length=1024), nullable=False),
        sa.Column("query_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corpus_version_id", sa.Integer(), nullable=False),
        sa.Column("model_keys", sa.JSON(), nullable=False),
        sa.Column("search_duration_ms", sa.Integer(), nullable=False),
        sa.Column("label_state", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["corpus_version_id"], ["corpus_versions.id"]),
    )
    op.create_table(
        "evaluation_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evaluation_example_id", sa.Uuid(), nullable=False),
        sa.Column("product_record_id", sa.Integer(), nullable=False),
        sa.Column("fused_rank", sa.Integer(), nullable=False),
        sa.Column("rrf_score", sa.Float(), nullable=False),
        sa.Column("per_model_ranks", sa.JSON(), nullable=False),
        sa.Column("per_model_raw_scores", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_example_id"], ["evaluation_examples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_record_id"], ["product_records.id"]),
    )
    op.create_table(
        "evaluation_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evaluation_example_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=True),
        sa.Column("variant_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_example_id"], ["evaluation_examples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["evaluation_candidates.id"]),
    )


def downgrade() -> None:
    op.drop_table("evaluation_actions")
    op.drop_table("evaluation_candidates")
    op.drop_table("evaluation_examples")
    op.drop_table("product_embeddings")
    op.drop_table("model_artifacts")
