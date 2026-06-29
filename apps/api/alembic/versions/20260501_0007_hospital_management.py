"""Add hospital management and consultation booking.

Revision ID: 20260501_0007
Revises: 20260501_0006
Create Date: 2026-05-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260501_0007"
down_revision: str | None = "20260501_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hospitals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("registration_number", sa.String(120), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("city", sa.String(120), nullable=False, server_default=""),
        sa.Column("state", sa.String(120), nullable=False, server_default=""),
        sa.Column("pincode", sa.String(16), nullable=False, server_default=""),
        sa.Column("phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("emergency_phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("admin_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hospitals_name", "hospitals", ["name"])
    op.create_index("ix_hospitals_registration_number", "hospitals", ["registration_number"])
    op.create_index("ix_hospitals_city", "hospitals", ["city"])
    op.create_index("ix_hospitals_state", "hospitals", ["state"])
    op.create_index("ix_hospitals_pincode", "hospitals", ["pincode"])
    op.create_index("ix_hospitals_admin_user_id", "hospitals", ["admin_user_id"])
    op.create_index("ix_hospitals_active", "hospitals", ["active"])

    op.create_table(
        "hospital_departments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("speciality", sa.String(160), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_hospital_departments_hospital_id", "hospital_departments", ["hospital_id"])
    op.create_index("ix_hospital_departments_name", "hospital_departments", ["name"])
    op.create_index("ix_hospital_departments_speciality", "hospital_departments", ["speciality"])
    op.create_index("ix_hospital_departments_active", "hospital_departments", ["active"])

    op.create_table(
        "hospital_doctors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column(
            "department_id",
            sa.String(36),
            sa.ForeignKey("hospital_departments.id"),
            nullable=False,
        ),
        sa.Column("doctor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("speciality", sa.String(160), nullable=False, server_default=""),
        sa.Column("consultation_fee", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hospital_doctors_hospital_id", "hospital_doctors", ["hospital_id"])
    op.create_index("ix_hospital_doctors_department_id", "hospital_doctors", ["department_id"])
    op.create_index("ix_hospital_doctors_doctor_id", "hospital_doctors", ["doctor_id"])
    op.create_index("ix_hospital_doctors_speciality", "hospital_doctors", ["speciality"])
    op.create_index("ix_hospital_doctors_active", "hospital_doctors", ["active"])

    op.create_table(
        "consultation_slots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column(
            "department_id",
            sa.String(36),
            sa.ForeignKey("hospital_departments.id"),
            nullable=False,
        ),
        sa.Column("doctor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.String(32), nullable=False),
        sa.Column("start_time", sa.String(16), nullable=False),
        sa.Column("end_time", sa.String(16), nullable=False),
        sa.Column("consultation_mode", sa.String(32), nullable=False, server_default="in_person"),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("booked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_consultation_slots_hospital_id", "consultation_slots", ["hospital_id"])
    op.create_index("ix_consultation_slots_department_id", "consultation_slots", ["department_id"])
    op.create_index("ix_consultation_slots_doctor_id", "consultation_slots", ["doctor_id"])
    op.create_index("ix_consultation_slots_date", "consultation_slots", ["date"])
    op.create_index("ix_consultation_slots_consultation_mode", "consultation_slots", ["consultation_mode"])
    op.create_index("ix_consultation_slots_status", "consultation_slots", ["status"])

    op.add_column("appointments", sa.Column("hospital_id", sa.String(36), nullable=False, server_default=""))
    op.add_column("appointments", sa.Column("department_id", sa.String(36), nullable=False, server_default=""))
    op.add_column("appointments", sa.Column("slot_id", sa.String(36), nullable=False, server_default=""))
    op.add_column(
        "appointments",
        sa.Column("consultation_mode", sa.String(32), nullable=False, server_default="in_person"),
    )
    op.add_column("appointments", sa.Column("reason", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "appointments",
        sa.Column("booking_reference", sa.String(80), nullable=False, server_default=""),
    )
    op.add_column(
        "appointments",
        sa.Column("cancellation_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_appointments_hospital_id", "appointments", ["hospital_id"])
    op.create_index("ix_appointments_department_id", "appointments", ["department_id"])
    op.create_index("ix_appointments_slot_id", "appointments", ["slot_id"])
    op.create_index("ix_appointments_consultation_mode", "appointments", ["consultation_mode"])
    op.create_index("ix_appointments_booking_reference", "appointments", ["booking_reference"])


def downgrade() -> None:
    op.drop_index("ix_appointments_booking_reference", table_name="appointments")
    op.drop_index("ix_appointments_consultation_mode", table_name="appointments")
    op.drop_index("ix_appointments_slot_id", table_name="appointments")
    op.drop_index("ix_appointments_department_id", table_name="appointments")
    op.drop_index("ix_appointments_hospital_id", table_name="appointments")
    op.drop_column("appointments", "cancellation_reason")
    op.drop_column("appointments", "booking_reference")
    op.drop_column("appointments", "reason")
    op.drop_column("appointments", "consultation_mode")
    op.drop_column("appointments", "slot_id")
    op.drop_column("appointments", "department_id")
    op.drop_column("appointments", "hospital_id")

    op.drop_table("consultation_slots")
    op.drop_table("hospital_doctors")
    op.drop_table("hospital_departments")
    op.drop_table("hospitals")
