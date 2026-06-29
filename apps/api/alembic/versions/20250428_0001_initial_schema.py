"""Initial MedRAG schema.

Revision ID: 20250428_0001
Revises:
Create Date: 2025-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20250428_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("registration_number", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "patient_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("blood_group", sa.String(length=12), nullable=False),
        sa.Column("date_of_birth", sa.String(length=16), nullable=False),
        sa.Column("gender", sa.String(length=32), nullable=False),
        sa.Column("allergies", sa.Text(), nullable=False),
        sa.Column("chronic_conditions", sa.Text(), nullable=False),
        sa.Column("current_medications", sa.Text(), nullable=False),
        sa.Column("abha_number", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_patient_profiles_user_id", "patient_profiles", ["user_id"])

    op.create_table(
        "medical_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("storage_bucket", sa.String(length=120), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("malware_status", sa.String(length=32), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("verified_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("verified_by_patient", sa.Boolean(), nullable=False),
        sa.Column("ingested_to_rag", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medical_documents_document_type", "medical_documents", ["document_type"])
    op.create_index("ix_medical_documents_patient_id", "medical_documents", ["patient_id"])
    op.create_index("ix_medical_documents_sha256", "medical_documents", ["sha256"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("purpose", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=80), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("previous_hash", sa.String(length=128), nullable=False),
        sa.Column("event_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_event_hash", "audit_events", ["event_hash"], unique=True)
    op.create_index("ix_audit_events_patient_id", "audit_events", ["patient_id"])

    op.create_table(
        "consent_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("grantee_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=160), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["grantee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_grants_grantee_id", "consent_grants", ["grantee_id"])
    op.create_index("ix_consent_grants_patient_id", "consent_grants", ["patient_id"])
    op.create_index("ix_consent_grants_scope", "consent_grants", ["scope"])

    op.create_table(
        "care_team_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("clinician_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinician_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_team_memberships_clinician_id", "care_team_memberships", ["clinician_id"])
    op.create_index("ix_care_team_memberships_patient_id", "care_team_memberships", ["patient_id"])

    op.create_table(
        "audit_retention_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("legal_basis", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("queue_job_id", sa.String(length=120), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["medical_documents.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index("ix_ingestion_jobs_job_type", "ingestion_jobs", ["job_type"])
    op.create_index("ix_ingestion_jobs_patient_id", "ingestion_jobs", ["patient_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    op.create_table(
        "answer_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("safety_label", sa.String(length=80), nullable=False),
        sa.Column("model_provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("retrieved_sources_json", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_answer_traces_actor_id", "answer_traces", ["actor_id"])
    op.create_index("ix_answer_traces_patient_id", "answer_traces", ["patient_id"])
    op.create_index("ix_answer_traces_safety_label", "answer_traces", ["safety_label"])
    op.create_index("ix_answer_traces_trace_id", "answer_traces", ["trace_id"], unique=True)

    op.create_table(
        "training_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("base_model", sa.String(length=200), nullable=False),
        sa.Column("dataset_uri", sa.String(length=512), nullable=False),
        sa.Column("dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=False),
        sa.Column("hyperparameters_json", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_runs_base_model", "training_runs", ["base_model"])
    op.create_index("ix_training_runs_status", "training_runs", ["status"])

    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("training_run_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("base_model", sa.String(length=200), nullable=False),
        sa.Column("adapter_uri", sa.String(length=512), nullable=False),
        sa.Column("adapter_sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("approved_by", sa.String(length=120), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_model_artifacts_approval_status", "model_artifacts", ["approval_status"])
    op.create_index("ix_model_artifacts_training_run_id", "model_artifacts", ["training_run_id"])


def downgrade() -> None:
    op.drop_index("ix_model_artifacts_training_run_id", table_name="model_artifacts")
    op.drop_index("ix_model_artifacts_approval_status", table_name="model_artifacts")
    op.drop_table("model_artifacts")
    op.drop_index("ix_training_runs_status", table_name="training_runs")
    op.drop_index("ix_training_runs_base_model", table_name="training_runs")
    op.drop_table("training_runs")
    op.drop_index("ix_answer_traces_trace_id", table_name="answer_traces")
    op.drop_index("ix_answer_traces_safety_label", table_name="answer_traces")
    op.drop_index("ix_answer_traces_patient_id", table_name="answer_traces")
    op.drop_index("ix_answer_traces_actor_id", table_name="answer_traces")
    op.drop_table("answer_traces")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_patient_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_job_type", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_table("audit_retention_policies")
    op.drop_index("ix_care_team_memberships_patient_id", table_name="care_team_memberships")
    op.drop_index("ix_care_team_memberships_clinician_id", table_name="care_team_memberships")
    op.drop_table("care_team_memberships")
    op.drop_index("ix_consent_grants_scope", table_name="consent_grants")
    op.drop_index("ix_consent_grants_patient_id", table_name="consent_grants")
    op.drop_index("ix_consent_grants_grantee_id", table_name="consent_grants")
    op.drop_table("consent_grants")
    op.drop_index("ix_audit_events_patient_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_hash", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_medical_documents_patient_id", table_name="medical_documents")
    op.drop_index("ix_medical_documents_document_type", table_name="medical_documents")
    op.drop_table("medical_documents")
    op.drop_index("ix_patient_profiles_user_id", table_name="patient_profiles")
    op.drop_table("patient_profiles")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_medical_documents_sha256", table_name="medical_documents")
