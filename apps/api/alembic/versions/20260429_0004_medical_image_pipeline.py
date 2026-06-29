"""Add medical image review fields.

Revision ID: 20260429_0004
Revises: 20260428_0003
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260429_0004"
down_revision: str | None = "20260428_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("medical_documents", sa.Column("image_modality", sa.String(80), nullable=False, server_default=""))
    op.add_column("medical_documents", sa.Column("image_ai_observations", sa.Text(), nullable=False, server_default=""))
    op.add_column("medical_documents", sa.Column("clinician_verified_findings", sa.Text(), nullable=False, server_default=""))
    op.add_column("medical_documents", sa.Column("clinician_verified_by", sa.String(36), nullable=False, server_default=""))
    op.add_column("medical_documents", sa.Column("image_review_status", sa.String(32), nullable=False, server_default="not_required"))
    op.create_index("ix_medical_documents_image_modality", "medical_documents", ["image_modality"])
    op.create_index("ix_medical_documents_clinician_verified_by", "medical_documents", ["clinician_verified_by"])
    op.create_index("ix_medical_documents_image_review_status", "medical_documents", ["image_review_status"])


def downgrade() -> None:
    op.drop_index("ix_medical_documents_image_review_status", table_name="medical_documents")
    op.drop_index("ix_medical_documents_clinician_verified_by", table_name="medical_documents")
    op.drop_index("ix_medical_documents_image_modality", table_name="medical_documents")
    op.drop_column("medical_documents", "image_review_status")
    op.drop_column("medical_documents", "clinician_verified_by")
    op.drop_column("medical_documents", "clinician_verified_findings")
    op.drop_column("medical_documents", "image_ai_observations")
    op.drop_column("medical_documents", "image_modality")
