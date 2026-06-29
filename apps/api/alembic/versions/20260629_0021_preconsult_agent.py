"""preconsult agent

Revision ID: 20260629_0021
Revises: 20260628_0020
Create Date: 2026-06-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260629_0021"
down_revision = "20260628_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pre_consultation_intakes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("doctor_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column("reason_for_call", sa.Text(), nullable=False),
        sa.Column("consent_request_id", sa.String(length=36), nullable=True),
        sa.Column("consent_grant_id", sa.String(length=36), nullable=True),
        sa.Column("draft_summary", sa.Text(), nullable=False),
        sa.Column("doctor_feedback", sa.Text(), nullable=False),
        sa.Column("reward_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pre_consultation_intakes_appointment_id", "pre_consultation_intakes", ["appointment_id"], unique=True)
    op.create_index("ix_pre_consultation_intakes_patient_id", "pre_consultation_intakes", ["patient_id"])
    op.create_index("ix_pre_consultation_intakes_doctor_id", "pre_consultation_intakes", ["doctor_id"])
    op.create_index("ix_pre_consultation_intakes_status", "pre_consultation_intakes", ["status"])
    op.create_index("ix_pre_consultation_intakes_consent_request_id", "pre_consultation_intakes", ["consent_request_id"])
    op.create_index("ix_pre_consultation_intakes_consent_grant_id", "pre_consultation_intakes", ["consent_grant_id"])


def downgrade() -> None:
    op.drop_index("ix_pre_consultation_intakes_consent_grant_id", table_name="pre_consultation_intakes")
    op.drop_index("ix_pre_consultation_intakes_consent_request_id", table_name="pre_consultation_intakes")
    op.drop_index("ix_pre_consultation_intakes_status", table_name="pre_consultation_intakes")
    op.drop_index("ix_pre_consultation_intakes_doctor_id", table_name="pre_consultation_intakes")
    op.drop_index("ix_pre_consultation_intakes_patient_id", table_name="pre_consultation_intakes")
    op.drop_index("ix_pre_consultation_intakes_appointment_id", table_name="pre_consultation_intakes")
    op.drop_table("pre_consultation_intakes")
