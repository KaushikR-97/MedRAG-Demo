"""Add v3/v4 feature module tables.

Revision ID: 20250428_0002
Revises: 20250428_0001
Create Date: 2025-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20250428_0002"
down_revision: str | None = "20250428_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("target", sa.String(320), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_otp_codes_user_id", "otp_codes", ["user_id"])
    op.create_index("ix_otp_codes_target", "otp_codes", ["target"])
    op.create_index("ix_otp_codes_channel", "otp_codes", ["channel"])
    op.create_index("ix_otp_codes_purpose", "otp_codes", ["purpose"])

    op.create_table(
        "prescriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doctor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("medications", sa.Text(), nullable=False),
        sa.Column("dosage", sa.Text(), nullable=False),
        sa.Column("duration", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("follow_up_date", sa.String(32), nullable=False),
        sa.Column("pmjay_covered", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prescriptions_patient_id", "prescriptions", ["patient_id"])
    op.create_index("ix_prescriptions_doctor_id", "prescriptions", ["doctor_id"])

    op.create_table(
        "appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doctor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("appointment_type", sa.String(120), nullable=False),
        sa.Column("date", sa.String(32), nullable=False),
        sa.Column("time_slot", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("urgency", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_status", "appointments", ["status"])
    op.create_index("ix_appointments_urgency", "appointments", ["urgency"])

    op.create_table(
        "health_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("due_date", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_health_tasks_patient_id", "health_tasks", ["patient_id"])
    op.create_index("ix_health_tasks_task_type", "health_tasks", ["task_type"])
    op.create_index("ix_health_tasks_priority", "health_tasks", ["priority"])
    op.create_index("ix_health_tasks_status", "health_tasks", ["status"])

    op.create_table(
        "family_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("relation", sa.String(80), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
    )
    op.create_index("ix_family_members_owner_id", "family_members", ["owner_id"])

    op.create_table(
        "medication_reminders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("medicine_name", sa.String(160), nullable=False),
        sa.Column("dosage", sa.String(120), nullable=False),
        sa.Column("schedule", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_medication_reminders_patient_id", "medication_reminders", ["patient_id"])

    op.create_table(
        "symptom_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("duration", sa.String(120), nullable=False),
        sa.Column("triage_result", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_symptom_entries_patient_id", "symptom_entries", ["patient_id"])

    op.create_table(
        "lab_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("test_name", sa.String(160), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lab_results_patient_id", "lab_results", ["patient_id"])
    op.create_index("ix_lab_results_test_name", "lab_results", ["test_name"])

    op.create_table(
        "vaccination_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vaccine_name", sa.String(160), nullable=False),
        sa.Column("dose_date", sa.String(32), nullable=False),
        sa.Column("next_due_date", sa.String(32), nullable=False),
    )
    op.create_index("ix_vaccination_records_patient_id", "vaccination_records", ["patient_id"])

    op.create_table(
        "pregnancy_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("lmp_date", sa.String(32), nullable=False),
        sa.Column("estimated_due_date", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
    )
    op.create_index("ix_pregnancy_records_patient_id", "pregnancy_records", ["patient_id"])

    op.create_table(
        "mental_health_screenings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("screening_type", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mental_health_screenings_patient_id", "mental_health_screenings", ["patient_id"])
    op.create_index("ix_mental_health_screenings_screening_type", "mental_health_screenings", ["screening_type"])

    op.create_table(
        "caregiver_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_caregiver_links_patient_id", "caregiver_links", ["patient_id"])
    op.create_index("ix_caregiver_links_token_hash", "caregiver_links", ["token_hash"], unique=True)

    op.create_table(
        "disease_outbreak_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state", sa.String(120), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("disease", sa.String(160), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_disease_outbreak_alerts_state", "disease_outbreak_alerts", ["state"])
    op.create_index("ix_disease_outbreak_alerts_city", "disease_outbreak_alerts", ["city"])
    op.create_index("ix_disease_outbreak_alerts_disease", "disease_outbreak_alerts", ["disease"])
    op.create_index("ix_disease_outbreak_alerts_severity", "disease_outbreak_alerts", ["severity"])


def downgrade() -> None:
    for index_name in [
        "ix_disease_outbreak_alerts_severity",
        "ix_disease_outbreak_alerts_disease",
        "ix_disease_outbreak_alerts_city",
        "ix_disease_outbreak_alerts_state",
    ]:
        op.drop_index(index_name, table_name="disease_outbreak_alerts")
    op.drop_table("disease_outbreak_alerts")
    op.drop_index("ix_caregiver_links_token_hash", table_name="caregiver_links")
    op.drop_index("ix_caregiver_links_patient_id", table_name="caregiver_links")
    op.drop_table("caregiver_links")
    op.drop_index("ix_mental_health_screenings_screening_type", table_name="mental_health_screenings")
    op.drop_index("ix_mental_health_screenings_patient_id", table_name="mental_health_screenings")
    op.drop_table("mental_health_screenings")
    op.drop_index("ix_pregnancy_records_patient_id", table_name="pregnancy_records")
    op.drop_table("pregnancy_records")
    op.drop_index("ix_vaccination_records_patient_id", table_name="vaccination_records")
    op.drop_table("vaccination_records")
    op.drop_index("ix_lab_results_test_name", table_name="lab_results")
    op.drop_index("ix_lab_results_patient_id", table_name="lab_results")
    op.drop_table("lab_results")
    op.drop_index("ix_symptom_entries_patient_id", table_name="symptom_entries")
    op.drop_table("symptom_entries")
    op.drop_index("ix_medication_reminders_patient_id", table_name="medication_reminders")
    op.drop_table("medication_reminders")
    op.drop_index("ix_family_members_owner_id", table_name="family_members")
    op.drop_table("family_members")
    for index_name in ["ix_health_tasks_status", "ix_health_tasks_priority", "ix_health_tasks_task_type", "ix_health_tasks_patient_id"]:
        op.drop_index(index_name, table_name="health_tasks")
    op.drop_table("health_tasks")
    for index_name in ["ix_appointments_urgency", "ix_appointments_status", "ix_appointments_doctor_id", "ix_appointments_patient_id"]:
        op.drop_index(index_name, table_name="appointments")
    op.drop_table("appointments")
    op.drop_index("ix_prescriptions_doctor_id", table_name="prescriptions")
    op.drop_index("ix_prescriptions_patient_id", table_name="prescriptions")
    op.drop_table("prescriptions")
    for index_name in ["ix_otp_codes_purpose", "ix_otp_codes_channel", "ix_otp_codes_target", "ix_otp_codes_user_id"]:
        op.drop_index(index_name, table_name="otp_codes")
    op.drop_table("otp_codes")

