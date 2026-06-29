"""Add production OCR review fields.

Revision ID: 20260501_0006
Revises: 20260501_0005
Create Date: 2026-05-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260501_0006"
down_revision: str | None = "20260501_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medical_documents",
        sa.Column("ocr_engine", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "medical_documents",
        sa.Column("ocr_confidence", sa.String(16), nullable=False, server_default=""),
    )
    op.add_column(
        "medical_documents",
        sa.Column("ocr_review_status", sa.String(40), nullable=False, server_default="not_started"),
    )
    op.add_column(
        "medical_documents",
        sa.Column("ocr_handwriting_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "medical_documents",
        sa.Column("ocr_warning", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_medical_documents_ocr_review_status",
        "medical_documents",
        ["ocr_review_status"],
    )
    op.create_index(
        "ix_medical_documents_ocr_handwriting_detected",
        "medical_documents",
        ["ocr_handwriting_detected"],
    )


def downgrade() -> None:
    op.drop_index("ix_medical_documents_ocr_handwriting_detected", table_name="medical_documents")
    op.drop_index("ix_medical_documents_ocr_review_status", table_name="medical_documents")
    op.drop_column("medical_documents", "ocr_warning")
    op.drop_column("medical_documents", "ocr_handwriting_detected")
    op.drop_column("medical_documents", "ocr_review_status")
    op.drop_column("medical_documents", "ocr_confidence")
    op.drop_column("medical_documents", "ocr_engine")
