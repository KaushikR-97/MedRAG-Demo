"""make slot hospital nullable

Revision ID: 20260626_0014
Revises: 20260626_0013
Create Date: 2026-06-26
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260626_0014"
down_revision: str | None = "20260626_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table("consultation_slots") as batch_op:
        batch_op.alter_column("hospital_id", existing_type=sa.String(36), nullable=True)
        batch_op.alter_column("department_id", existing_type=sa.String(36), nullable=True)

def downgrade() -> None:
    with op.batch_alter_table("consultation_slots") as batch_op:
        batch_op.alter_column("department_id", existing_type=sa.String(36), nullable=False)
        batch_op.alter_column("hospital_id", existing_type=sa.String(36), nullable=False)
