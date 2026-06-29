from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    blood_group: Mapped[str] = mapped_column(String(12), default="")
    date_of_birth: Mapped[str] = mapped_column(String(16), default="")
    gender: Mapped[str] = mapped_column(String(32), default="")
    allergies: Mapped[str] = mapped_column(Text, default="")
    chronic_conditions: Mapped[str] = mapped_column(Text, default="")
    current_medications: Mapped[str] = mapped_column(Text, default="")
    abha_number: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User", back_populates="profile")

