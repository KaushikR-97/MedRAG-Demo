import re
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User


AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
PHONE_RE = re.compile(r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ABHA_RE = re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b")
DATE_RE = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")


@dataclass(frozen=True)
class DataAccessDecision:
    allowed: bool
    reason: str


class PrivacyService:
    """Central privacy and data-loss-prevention policy.

    The goal is to keep PHI access explicit and prevent accidental leakage in
    AI responses, logs, exports, and staff workflows.
    """

    def redact_phi(self, text: str, db_session: Session | None = None, patient_id: str | None = None) -> str:
        if not text:
            return text
        redacted = AADHAAR_RE.sub("[REDACTED_AADHAAR]", text)
        redacted = ABHA_RE.sub("[REDACTED_ABHA]", redacted)
        redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
        redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
        redacted = DATE_RE.sub("[REDACTED_DATE]", redacted)
        redacted = PAN_RE.sub("[REDACTED_ID]", redacted)

        if patient_id and db_session:
            try:
                user = db_session.get(User, patient_id)
                if user and user.full_name:
                    full_name = user.full_name.strip()
                    if len(full_name) > 1:
                        redacted = re.sub(rf"\b{re.escape(full_name)}\b", "[REDACTED_NAME]", redacted, flags=re.IGNORECASE)
                    
                    # Redact components of the name to catch parts (e.g. John, Doe)
                    parts = [p.strip() for p in full_name.split() if len(p.strip()) > 1]
                    parts.sort(key=len, reverse=True)
                    for part in parts:
                        redacted = re.sub(rf"\b{re.escape(part)}\b", "[REDACTED_NAME]", redacted, flags=re.IGNORECASE)
            except Exception:
                pass
        return redacted

    def assert_no_download(self, *, actor: User, patient_id: str, resource: str) -> None:
        if actor.id == patient_id:
            return
        if actor.role in {"doctor", "hospital_admin"}:
            raise HTTPException(
                status_code=403,
                detail=f"Download/export blocked for {resource}. Clinical staff may view minimum necessary data only.",
            )
        raise HTTPException(status_code=403, detail="Access denied")

    def minimum_necessary_text(self, *, actor: User, patient_id: str, text: str, db: Session | None = None) -> str:
        # HIPAA requirement: remove patient name and identifiers for all roles including clinical queries
        return self.redact_phi(text, db_session=db, patient_id=patient_id)

