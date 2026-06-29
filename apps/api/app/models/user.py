from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(32), index=True)
    phone: Mapped[str] = mapped_column(String(32), default="")
    registration_number: Mapped[str] = mapped_column(String(64), default="")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), default="", nullable=True)
    speciality: Mapped[str | None] = mapped_column(String(160), default="", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    profile = relationship("PatientProfile", back_populates="user", uselist=False)


