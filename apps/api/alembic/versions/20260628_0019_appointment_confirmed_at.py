"""appointment confirmed timestamp

Revision ID: 20260628_0019
Revises: 20260627_0018
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260628_0019"
down_revision = "20260627_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("appointments", "confirmed_at")
