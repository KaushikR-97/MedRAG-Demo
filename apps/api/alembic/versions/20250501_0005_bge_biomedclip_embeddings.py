"""Add BioMedCLIP image embedding tracking fields.

Revision ID: 20250501_0005
Revises: 20250429_0004
Create Date: 2025-05-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20250501_0005"
down_revision: str | None = "20250429_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medical_documents",
        sa.Column(
            "image_embedding_status",
            sa.String(32),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column(
        "medical_documents",
        sa.Column("image_embedding_model", sa.String(160), nullable=False, server_default=""),
    )
    op.add_column(
        "medical_documents",
        sa.Column("image_vector_id", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_medical_documents_image_embedding_status",
        "medical_documents",
        ["image_embedding_status"],
    )
    op.create_index(
        "ix_medical_documents_image_vector_id",
        "medical_documents",
        ["image_vector_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_medical_documents_image_vector_id", table_name="medical_documents")
    op.drop_index("ix_medical_documents_image_embedding_status", table_name="medical_documents")
    op.drop_column("medical_documents", "image_vector_id")
    op.drop_column("medical_documents", "image_embedding_model")
    op.drop_column("medical_documents", "image_embedding_status")
