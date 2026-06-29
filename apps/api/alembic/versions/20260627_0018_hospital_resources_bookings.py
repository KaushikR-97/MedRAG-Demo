"""hospital resources bookings

Revision ID: 20260627_0018
Revises: 20260627_0017
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260627_0018"
down_revision = "20260627_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hospitals", sa.Column("ambulance_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hospitals", sa.Column("ambulance_types", sa.Text(), nullable=False, server_default=""))
    op.add_column("hospitals", sa.Column("beds_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hospitals", sa.Column("rooms_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hospitals", sa.Column("icu_beds_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hospitals", sa.Column("ac_rooms_total", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "hospital_resource_bookings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("hospital_id", sa.String(length=36), nullable=False),
        sa.Column("booking_type", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discharged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hospital_resource_bookings_patient_id", "hospital_resource_bookings", ["patient_id"])
    op.create_index("ix_hospital_resource_bookings_hospital_id", "hospital_resource_bookings", ["hospital_id"])
    op.create_index("ix_hospital_resource_bookings_booking_type", "hospital_resource_bookings", ["booking_type"])
    op.create_index("ix_hospital_resource_bookings_resource_type", "hospital_resource_bookings", ["resource_type"])
    op.create_index("ix_hospital_resource_bookings_status", "hospital_resource_bookings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hospital_resource_bookings_status", table_name="hospital_resource_bookings")
    op.drop_index("ix_hospital_resource_bookings_resource_type", table_name="hospital_resource_bookings")
    op.drop_index("ix_hospital_resource_bookings_booking_type", table_name="hospital_resource_bookings")
    op.drop_index("ix_hospital_resource_bookings_hospital_id", table_name="hospital_resource_bookings")
    op.drop_index("ix_hospital_resource_bookings_patient_id", table_name="hospital_resource_bookings")
    op.drop_table("hospital_resource_bookings")
    op.drop_column("hospitals", "ac_rooms_total")
    op.drop_column("hospitals", "icu_beds_total")
    op.drop_column("hospitals", "rooms_total")
    op.drop_column("hospitals", "beds_total")
    op.drop_column("hospitals", "ambulance_types")
    op.drop_column("hospitals", "ambulance_count")
