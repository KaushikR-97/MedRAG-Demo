"""patient access requests

Revision ID: 20260627_0017
Revises: 20260627_0016
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260627_0017"
down_revision = "20260627_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_access_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("requester_id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("consent_grant_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["consent_grant_id"], ["consent_grants.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_access_requests_patient_id", "patient_access_requests", ["patient_id"])
    op.create_index("ix_patient_access_requests_requester_id", "patient_access_requests", ["requester_id"])
    op.create_index("ix_patient_access_requests_scope", "patient_access_requests", ["scope"])
    op.create_index("ix_patient_access_requests_status", "patient_access_requests", ["status"])
    op.create_index("ix_patient_access_requests_consent_grant_id", "patient_access_requests", ["consent_grant_id"])


def downgrade() -> None:
    op.drop_index("ix_patient_access_requests_consent_grant_id", table_name="patient_access_requests")
    op.drop_index("ix_patient_access_requests_status", table_name="patient_access_requests")
    op.drop_index("ix_patient_access_requests_scope", table_name="patient_access_requests")
    op.drop_index("ix_patient_access_requests_requester_id", table_name="patient_access_requests")
    op.drop_index("ix_patient_access_requests_patient_id", table_name="patient_access_requests")
    op.drop_table("patient_access_requests")
