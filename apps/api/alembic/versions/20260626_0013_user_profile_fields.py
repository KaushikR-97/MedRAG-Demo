"""Add profile and billing fields.

Revision ID: 20260626_0013
Revises: 20260625_0012
Create Date: 2026-06-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260626_0013"
down_revision: str | None = "20260625_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add columns to users
    op.add_column("users", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("city", sa.String(120), nullable=True, server_default=""))
    op.add_column("users", sa.Column("speciality", sa.String(160), nullable=True, server_default=""))

    # Add columns to consultation_slots
    op.add_column("consultation_slots", sa.Column("consultation_fee", sa.Float(), nullable=True, server_default="0.0"))
    op.add_column("consultation_slots", sa.Column("accept_insurance", sa.Boolean(), nullable=True, server_default="1"))

    # Add columns to appointments
    op.add_column("appointments", sa.Column("payment_method", sa.String(32), nullable=True, server_default="cash"))
    op.add_column("appointments", sa.Column("insurance_provider", sa.String(120), nullable=True, server_default=""))
    op.add_column("appointments", sa.Column("insurance_policy_number", sa.String(120), nullable=True, server_default=""))
    op.add_column("appointments", sa.Column("consultation_fee", sa.Float(), nullable=True, server_default="0.0"))


def downgrade() -> None:
    # Drop columns from appointments
    op.drop_column("appointments", "consultation_fee")
    op.drop_column("appointments", "insurance_policy_number")
    op.drop_column("appointments", "insurance_provider")
    op.drop_column("appointments", "payment_method")

    # Drop columns from consultation_slots
    op.drop_column("consultation_slots", "accept_insurance")
    op.drop_column("consultation_slots", "consultation_fee")

    # Drop columns from users
    op.drop_column("users", "speciality")
    op.drop_column("users", "city")
    op.drop_column("users", "age")
