"""add secure consultation rooms

Revision ID: 20260627_0015
Revises: 20260626_0014
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260627_0015"
down_revision: str | None = "20260626_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consultation_rooms",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("appointment_id", sa.String(length=36), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultation_rooms_appointment_id", "consultation_rooms", ["appointment_id"], unique=True)
    op.create_index("ix_consultation_rooms_patient_id", "consultation_rooms", ["patient_id"])
    op.create_index("ix_consultation_rooms_doctor_id", "consultation_rooms", ["doctor_id"])
    op.create_index("ix_consultation_rooms_status", "consultation_rooms", ["status"])
    op.create_index("ix_consultation_rooms_expires_at", "consultation_rooms", ["expires_at"])

    op.create_table(
        "consultation_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("room_id", sa.String(length=36), sa.ForeignKey("consultation_rooms.id"), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("sender_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultation_messages_room_id", "consultation_messages", ["room_id"])
    op.create_index("ix_consultation_messages_appointment_id", "consultation_messages", ["appointment_id"])
    op.create_index("ix_consultation_messages_sender_id", "consultation_messages", ["sender_id"])
    op.create_index("ix_consultation_messages_recipient_id", "consultation_messages", ["recipient_id"])
    op.create_index("ix_consultation_messages_message_type", "consultation_messages", ["message_type"])
    op.create_index("ix_consultation_messages_created_at", "consultation_messages", ["created_at"])

    op.create_table(
        "consultation_signals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("room_id", sa.String(length=36), sa.ForeignKey("consultation_rooms.id"), nullable=False),
        sa.Column("sender_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultation_signals_room_id", "consultation_signals", ["room_id"])
    op.create_index("ix_consultation_signals_sender_id", "consultation_signals", ["sender_id"])
    op.create_index("ix_consultation_signals_recipient_id", "consultation_signals", ["recipient_id"])
    op.create_index("ix_consultation_signals_signal_type", "consultation_signals", ["signal_type"])
    op.create_index("ix_consultation_signals_created_at", "consultation_signals", ["created_at"])
    op.create_index("ix_consultation_signals_expires_at", "consultation_signals", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_consultation_signals_expires_at", table_name="consultation_signals")
    op.drop_index("ix_consultation_signals_created_at", table_name="consultation_signals")
    op.drop_index("ix_consultation_signals_signal_type", table_name="consultation_signals")
    op.drop_index("ix_consultation_signals_recipient_id", table_name="consultation_signals")
    op.drop_index("ix_consultation_signals_sender_id", table_name="consultation_signals")
    op.drop_index("ix_consultation_signals_room_id", table_name="consultation_signals")
    op.drop_table("consultation_signals")

    op.drop_index("ix_consultation_messages_created_at", table_name="consultation_messages")
    op.drop_index("ix_consultation_messages_message_type", table_name="consultation_messages")
    op.drop_index("ix_consultation_messages_recipient_id", table_name="consultation_messages")
    op.drop_index("ix_consultation_messages_sender_id", table_name="consultation_messages")
    op.drop_index("ix_consultation_messages_appointment_id", table_name="consultation_messages")
    op.drop_index("ix_consultation_messages_room_id", table_name="consultation_messages")
    op.drop_table("consultation_messages")

    op.drop_index("ix_consultation_rooms_expires_at", table_name="consultation_rooms")
    op.drop_index("ix_consultation_rooms_status", table_name="consultation_rooms")
    op.drop_index("ix_consultation_rooms_doctor_id", table_name="consultation_rooms")
    op.drop_index("ix_consultation_rooms_patient_id", table_name="consultation_rooms")
    op.drop_index("ix_consultation_rooms_appointment_id", table_name="consultation_rooms")
    op.drop_table("consultation_rooms")
