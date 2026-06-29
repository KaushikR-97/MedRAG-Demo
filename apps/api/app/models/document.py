from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MedicalDocument(Base):
    __tablename__ = "medical_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(String(512))
    storage_bucket: Mapped[str] = mapped_column(String(120), default="")
    storage_key: Mapped[str] = mapped_column(String(512), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    document_type: Mapped[str] = mapped_column(String(40), index=True)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    file_size_bytes: Mapped[int] = mapped_column(default=0)
    malware_status: Mapped[str] = mapped_column(String(32), default="pending")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    ocr_engine: Mapped[str] = mapped_column(String(64), default="")
    ocr_confidence: Mapped[str] = mapped_column(String(16), default="")
    ocr_review_status: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    ocr_handwriting_detected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ocr_warning: Mapped[str] = mapped_column(Text, default="")
    verified_text: Mapped[str] = mapped_column(Text, default="")
    image_modality: Mapped[str] = mapped_column(String(80), default="", index=True)
    image_ai_observations: Mapped[str] = mapped_column(Text, default="")
    clinician_verified_findings: Mapped[str] = mapped_column(Text, default="")
    clinician_verified_by: Mapped[str] = mapped_column(String(36), default="", index=True)
    image_review_status: Mapped[str] = mapped_column(String(32), default="not_required", index=True)
    image_embedding_status: Mapped[str] = mapped_column(String(32), default="not_required", index=True)
    image_embedding_model: Mapped[str] = mapped_column(String(160), default="")
    image_vector_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    verified_by_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_to_rag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
