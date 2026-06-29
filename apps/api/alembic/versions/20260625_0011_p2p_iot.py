"""Create second_opinion_requests and iot_pillbox_alerts tables.

Revision ID: 20260625_0011
Revises: 20260625_0010
Create Date: 2026-06-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260625_0011"
down_revision: str | None = "20260625_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create second_opinion_requests table
    op.create_table(
        "second_opinion_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("clinician_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("specialty", sa.String(120), nullable=False),
        sa.Column("redacted_summary", sa.Text(), nullable=False),
        sa.Column("clinical_question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("response_recommendation", sa.Text(), nullable=True),
        sa.Column("responder_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_second_opinion_requests_clinician_id", "second_opinion_requests", ["clinician_id"])
    op.create_index("ix_second_opinion_requests_specialty", "second_opinion_requests", ["specialty"])
    op.create_index("ix_second_opinion_requests_status", "second_opinion_requests", ["status"])

    # Create iot_pillbox_alerts table
    op.create_table(
        "iot_pillbox_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reminder_id", sa.String(36), sa.ForeignKey("medication_reminders.id"), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_iot_pillbox_alerts_reminder_id", "iot_pillbox_alerts", ["reminder_id"])
    op.create_index("ix_iot_pillbox_alerts_patient_id", "iot_pillbox_alerts", ["patient_id"])
    op.create_index("ix_iot_pillbox_alerts_status", "iot_pillbox_alerts", ["status"])


def downgrade() -> None:
    # Drop tables and indexes
    op.drop_index("ix_iot_pillbox_alerts_status", table_name="iot_pillbox_alerts")
    op.drop_index("ix_iot_pillbox_alerts_patient_id", table_name="iot_pillbox_alerts")
    op.drop_index("ix_iot_pillbox_alerts_reminder_id", table_name="iot_pillbox_alerts")
    op.drop_table("iot_pillbox_alerts")

    op.drop_index("ix_second_opinion_requests_status", table_name="second_opinion_requests")
    op.drop_index("ix_second_opinion_requests_specialty", table_name="second_opinion_requests")
    op.drop_index("ix_second_opinion_requests_clinician_id", table_name="second_opinion_requests")
    op.drop_table("second_opinion_requests")
