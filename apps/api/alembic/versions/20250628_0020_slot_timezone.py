"""slot appointment timezone

Revision ID: 20250628_0020
Revises: 20250628_0019
Create Date: 2025-06-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20250628_0020"
down_revision = "20250628_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consultation_slots", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Kolkata"))
    op.add_column("appointments", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Kolkata"))


def downgrade() -> None:
    op.drop_column("appointments", "timezone")
    op.drop_column("consultation_slots", "timezone")
