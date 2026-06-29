"""Add member_user_id to family_members and create simulated_whatsapp_messages.

Revision ID: 20250625_0009
Revises: 20250612_0008
Create Date: 2025-06-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20250625_0009"
down_revision: str | None = "20250612_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add member_user_id column to family_members
    op.add_column(
        "family_members",
        sa.Column("member_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_family_members_member_user_id", "family_members", ["member_user_id"])

    # Create simulated_whatsapp_messages table
    op.create_table(
        "simulated_whatsapp_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("to_phone", sa.String(40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("consent_grant_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="sent"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulated_whatsapp_messages_to_phone", "simulated_whatsapp_messages", ["to_phone"])


def downgrade() -> None:
    # Drop indexes and tables
    op.drop_index("ix_simulated_whatsapp_messages_to_phone", table_name="simulated_whatsapp_messages")
    op.drop_table("simulated_whatsapp_messages")
    
    op.drop_index("ix_family_members_member_user_id", table_name="family_members")
    op.drop_column("family_members", "member_user_id")
