"""Add agentic care coordination tables.

Revision ID: 20260428_0003
Revises: 20260428_0002
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260428_0003"
down_revision: str | None = "20260428_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_calendar_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_patient_calendar_events_patient_id", "patient_calendar_events", ["patient_id"])
    op.create_index("ix_patient_calendar_events_event_type", "patient_calendar_events", ["event_type"])
    op.create_index("ix_patient_calendar_events_starts_at", "patient_calendar_events", ["starts_at"])
    op.create_index("ix_patient_calendar_events_status", "patient_calendar_events", ["status"])

    op.create_table(
        "agent_action_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_name", sa.String(120), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("tool_payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_action_logs_patient_id", "agent_action_logs", ["patient_id"])
    op.create_index("ix_agent_action_logs_actor_id", "agent_action_logs", ["actor_id"])
    op.create_index("ix_agent_action_logs_agent_name", "agent_action_logs", ["agent_name"])
    op.create_index("ix_agent_action_logs_action", "agent_action_logs", ["action"])
    op.create_index("ix_agent_action_logs_status", "agent_action_logs", ["status"])

    op.create_table(
        "emergency_dispatch_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("location_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(120), nullable=False),
        sa.Column("safety_label", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_emergency_dispatch_requests_patient_id", "emergency_dispatch_requests", ["patient_id"])
    op.create_index("ix_emergency_dispatch_requests_actor_id", "emergency_dispatch_requests", ["actor_id"])
    op.create_index("ix_emergency_dispatch_requests_status", "emergency_dispatch_requests", ["status"])
    op.create_index("ix_emergency_dispatch_requests_safety_label", "emergency_dispatch_requests", ["safety_label"])


def downgrade() -> None:
    op.drop_index("ix_emergency_dispatch_requests_safety_label", table_name="emergency_dispatch_requests")
    op.drop_index("ix_emergency_dispatch_requests_status", table_name="emergency_dispatch_requests")
    op.drop_index("ix_emergency_dispatch_requests_actor_id", table_name="emergency_dispatch_requests")
    op.drop_index("ix_emergency_dispatch_requests_patient_id", table_name="emergency_dispatch_requests")
    op.drop_table("emergency_dispatch_requests")
    op.drop_index("ix_agent_action_logs_status", table_name="agent_action_logs")
    op.drop_index("ix_agent_action_logs_action", table_name="agent_action_logs")
    op.drop_index("ix_agent_action_logs_agent_name", table_name="agent_action_logs")
    op.drop_index("ix_agent_action_logs_actor_id", table_name="agent_action_logs")
    op.drop_index("ix_agent_action_logs_patient_id", table_name="agent_action_logs")
    op.drop_table("agent_action_logs")
    op.drop_index("ix_patient_calendar_events_status", table_name="patient_calendar_events")
    op.drop_index("ix_patient_calendar_events_starts_at", table_name="patient_calendar_events")
    op.drop_index("ix_patient_calendar_events_event_type", table_name="patient_calendar_events")
    op.drop_index("ix_patient_calendar_events_patient_id", table_name="patient_calendar_events")
    op.drop_table("patient_calendar_events")
