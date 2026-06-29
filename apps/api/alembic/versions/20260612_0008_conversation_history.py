"""Add scoped conversation history to answer traces.

Revision ID: 20260612_0008
Revises: 20260501_0007
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260612_0008"
down_revision: str | None = "20260501_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answer_traces",
        sa.Column("conversation_id", sa.String(36), nullable=False, server_default=""),
    )
    op.create_index("ix_answer_traces_conversation_id", "answer_traces", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_traces_conversation_id", table_name="answer_traces")
    op.drop_column("answer_traces", "conversation_id")
