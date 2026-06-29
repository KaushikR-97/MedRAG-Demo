from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    base_model: Mapped[str] = mapped_column(String(200), index=True)
    dataset_uri: Mapped[str] = mapped_column(String(512))
    dataset_sha256: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(80), default="qlora")
    hyperparameters_json: Mapped[str] = mapped_column(Text, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    training_run_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    base_model: Mapped[str] = mapped_column(String(200))
    adapter_uri: Mapped[str] = mapped_column(String(512))
    adapter_sha256: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(80))
    approval_status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    approved_by: Mapped[str] = mapped_column(String(120), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

