"""emergency dispatch hospital location

Revision ID: 20260627_0016
Revises: 20260627_0015
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260627_0016"
down_revision = "20260627_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("emergency_dispatch_requests", sa.Column("hospital_id", sa.String(length=36), nullable=True))
    op.add_column("emergency_dispatch_requests", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("emergency_dispatch_requests", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_index("ix_emergency_dispatch_requests_hospital_id", "emergency_dispatch_requests", ["hospital_id"])


def downgrade() -> None:
    op.drop_index("ix_emergency_dispatch_requests_hospital_id", table_name="emergency_dispatch_requests")
    op.drop_column("emergency_dispatch_requests", "longitude")
    op.drop_column("emergency_dispatch_requests", "latitude")
    op.drop_column("emergency_dispatch_requests", "hospital_id")
