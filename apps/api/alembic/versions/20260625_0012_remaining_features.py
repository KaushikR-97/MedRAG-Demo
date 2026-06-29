"""Create guideline_drift_alerts and phr_ledger_blocks tables.

Revision ID: 20260625_0012
Revises: 20260625_0011
Create Date: 2026-06-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260625_0012"
down_revision: str | None = "20260625_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create guideline_drift_alerts table
    op.create_table(
        "guideline_drift_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("guideline_title", sa.String(200), nullable=False),
        sa.Column("published_source", sa.String(200), nullable=False),
        sa.Column("drift_reason", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.String(64), nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Create phr_ledger_blocks table
    op.create_table(
        "phr_ledger_blocks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("timeline_hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("nonce", sa.Integer(), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_phr_ledger_blocks_patient_id", "phr_ledger_blocks", ["patient_id"])


def downgrade() -> None:
    # Drop tables and indexes
    op.drop_index("ix_phr_ledger_blocks_patient_id", table_name="phr_ledger_blocks")
    op.drop_table("phr_ledger_blocks")
    op.drop_table("guideline_drift_alerts")
