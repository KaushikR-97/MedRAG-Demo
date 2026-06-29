"""Create simulated_sms_messages table.

Revision ID: 20250625_0010
Revises: 20250625_0009
Create Date: 2025-06-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20250625_0010"
down_revision: str | None = "20250625_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create simulated_sms_messages table
    op.create_table(
        "simulated_sms_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False), # "inbound" or "outbound"
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulated_sms_messages_phone", "simulated_sms_messages", ["phone"])


def downgrade() -> None:
    # Drop table and indexes
    op.drop_index("ix_simulated_sms_messages_phone", table_name="simulated_sms_messages")
    op.drop_table("simulated_sms_messages")
