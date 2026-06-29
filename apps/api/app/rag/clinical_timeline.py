from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.document import MedicalDocument
from app.models.feature_modules import Prescription


LAB_GROUP_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("diabetes_glucose_hba1c", ("hba1c", "glycated", "glucose", "fasting sugar", "ppbs", "rbs", "diabetes")),
    ("renal_kidney", ("creatinine", "urea", "egfr", "kidney", "renal", "uric acid")),
    ("liver_function", ("sgpt", "sgot", "alt", "ast", "bilirubin", "liver", "alp")),
    ("thyroid", ("tsh", "t3", "t4", "thyroid")),
    ("lipid_profile", ("cholesterol", "triglyceride", "hdl", "ldl", "lipid")),
    ("complete_blood_count", ("cbc", "hemoglobin", "haemoglobin", "wbc", "rbc", "platelet")),
    ("urine_analysis", ("urine", "albumin", "pus cells", "proteinuria")),
    ("infection_inflammation", ("crp", "esr", "dengue", "malaria", "widal", "culture")),
]

DIAGNOSIS_STOPWORDS = {
    "type",
    "acute",
    "chronic",
    "suspected",
    "with",
    "without",
    "and",
    "or",
    "mellitus",
    "disease",
    "syndrome",
}


@dataclass(frozen=True)
class ClinicalTimelineContext:
    clinical_record_role: str
    timeline_state: str
    lab_group: str = ""
    disease_names: str = ""
    prescription_state: str = ""
    clinical_date: str = ""

    def as_payload(self) -> dict[str, str]:
        return {
            "clinical_record_role": self.clinical_record_role,
            "timeline_state": self.timeline_state,
            "lab_group": self.lab_group,
            "disease_names": self.disease_names,
            "prescription_state": self.prescription_state,
            "clinical_date": self.clinical_date,
        }


def build_document_timeline_context(db: Session, doc: MedicalDocument) -> ClinicalTimelineContext:
    document_type = (doc.document_type or "").lower()
    text = f"{doc.original_filename}\n{doc.verified_text or doc.ocr_text}".lower()

    if document_type == "lab_report":
        lab_group = infer_lab_group(text)
        clinical_date = extract_document_clinical_datetime(doc).isoformat()
        return ClinicalTimelineContext(
            clinical_record_role="lab_report",
            timeline_state=lab_report_timeline_state(db, doc, lab_group),
            lab_group=lab_group,
            clinical_date=clinical_date,
        )

    if document_type == "prescription":
        diseases = infer_disease_names(doc.verified_text or doc.ocr_text)
        return ClinicalTimelineContext(
            clinical_record_role="prescription",
            timeline_state="active_condition" if prescription_is_active(doc.verified_text or "") else "past_condition",
            disease_names=diseases,
            prescription_state="active" if prescription_is_active(doc.verified_text or "") else "past",
            clinical_date=extract_document_clinical_datetime(doc).isoformat(),
        )

    if document_type == "discharge_summary":
        return ClinicalTimelineContext(
            clinical_record_role="discharge_summary",
            timeline_state="past_condition",
            disease_names=infer_disease_names(doc.verified_text or doc.ocr_text),
            clinical_date=extract_document_clinical_datetime(doc).isoformat(),
        )

    if document_type in {"past_record", "imaging", "health_scan", "vaccination_record"}:
        return ClinicalTimelineContext(
            clinical_record_role=document_type,
            timeline_state="historical",
            disease_names=infer_disease_names(doc.verified_text or doc.ocr_text),
            clinical_date=extract_document_clinical_datetime(doc).isoformat(),
        )

    return ClinicalTimelineContext(
        clinical_record_role=document_type or "patient_document",
        timeline_state="historical",
        disease_names=infer_disease_names(doc.verified_text or doc.ocr_text),
        clinical_date=extract_document_clinical_datetime(doc).isoformat(),
    )


def build_prescription_timeline_context(rx: Prescription) -> ClinicalTimelineContext:
    active = prescription_model_is_active(rx)
    return ClinicalTimelineContext(
        clinical_record_role="prescription",
        timeline_state="active_condition" if active else "past_condition",
        disease_names=infer_disease_names(rx.diagnosis),
        prescription_state="active" if active else "past",
    )


def infer_lab_group(text: str) -> str:
    lowered = text.lower()
    matches = [group for group, terms in LAB_GROUP_PATTERNS if any(_contains_clinical_term(lowered, term) for term in terms)]
    return "+".join(matches) if matches else "general_lab_report"


def lab_report_timeline_state(db: Session, doc: MedicalDocument, lab_group: str) -> str:
    groups = _lab_group_set(lab_group)
    if not groups:
        groups = {"general_lab_report"}
    candidates = (
        db.query(MedicalDocument)
        .filter(
            MedicalDocument.patient_id == doc.patient_id,
            MedicalDocument.document_type == "lab_report",
            MedicalDocument.status != "deleted_by_patient",
            MedicalDocument.verified_text != "",
        )
        .all()
    )
    current_by_group = []
    this_date = extract_document_clinical_datetime(doc)
    for group in groups:
        same_group = [
            candidate
            for candidate in candidates
            if group in _lab_group_set(
                infer_lab_group(f"{candidate.original_filename}\n{candidate.verified_text or candidate.ocr_text}".lower())
            )
        ]
        if not same_group:
            current_by_group.append(True)
            continue
        latest_date = max(extract_document_clinical_datetime(candidate) for candidate in same_group)
        current_by_group.append(this_date >= latest_date)
    if all(current_by_group):
        return "current_snapshot"
    if any(current_by_group):
        return "mixed_current_and_historical"
    return "historical"


def is_latest_lab_report(db: Session, doc: MedicalDocument, lab_group: str) -> bool:
    return lab_report_timeline_state(db, doc, lab_group) == "current_snapshot"


def extract_document_clinical_datetime(doc: MedicalDocument) -> datetime:
    text = f"{doc.original_filename}\n{doc.verified_text or doc.ocr_text}"
    parsed = extract_clinical_datetime(text)
    if parsed:
        return parsed
    return doc.created_at or datetime.min.replace(tzinfo=UTC)


def extract_clinical_datetime(text: str) -> datetime | None:
    normalized = re.sub(r"\s+", " ", text)
    labelled_patterns = [
        r"(?:report|reported|collection|collected|sample|specimen|test|result|date)\s*(?:date|on)?\s*[:\-]?\s*([0-9]{1,2}[-/ .][A-Za-z]{3,9}[-/ .][0-9]{2,4})",
        r"(?:report|reported|collection|collected|sample|specimen|test|result|date)\s*(?:date|on)?\s*[:\-]?\s*([0-9]{1,2}[-/ .][0-9]{1,2}[-/ .][0-9]{2,4})",
        r"(?:report|reported|collection|collected|sample|specimen|test|result|date)\s*(?:date|on)?\s*[:\-]?\s*([0-9]{4}[-/ .][0-9]{1,2}[-/ .][0-9]{1,2})",
    ]
    for pattern in labelled_patterns:
        for match in re.findall(pattern, normalized, flags=re.IGNORECASE):
            parsed = _parse_date(match)
            if parsed:
                return parsed

    dates = []
    for pattern in (
        r"(?<![A-Za-z0-9])[0-9]{1,2}[-/ .][A-Za-z]{3,9}[-/ .][0-9]{2,4}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[0-9]{1,2}[A-Za-z]{3,9}[0-9]{4}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[0-9]{4}[-/ .][0-9]{1,2}[-/ .][0-9]{1,2}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[0-9]{1,2}[-/ .][0-9]{1,2}[-/ .][0-9]{2,4}(?![A-Za-z0-9])",
    ):
        for match in re.findall(pattern, normalized, flags=re.IGNORECASE):
            parsed = _parse_date(match)
            if parsed:
                dates.append(parsed)
    if not dates:
        return None
    return max(dates)


def prescription_model_is_active(rx: Prescription) -> bool:
    if not rx.follow_up_date:
        return True
    try:
        follow_up = datetime.fromisoformat(rx.follow_up_date).date()
    except ValueError:
        return True
    return follow_up >= datetime.now(UTC).date()


def prescription_is_active(text: str) -> bool:
    follow_up_match = re.search(r"Follow-up Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text)
    if not follow_up_match:
        return True
    try:
        return datetime.fromisoformat(follow_up_match.group(1)).date() >= datetime.now(UTC).date()
    except ValueError:
        return True


def infer_disease_names(text: str) -> str:
    candidates: list[str] = []
    for pattern in (
        r"Diagnosis:\s*([^\n]+)",
        r"Assessment:\s*([^\n]+)",
        r"Discharge Diagnosis:\s*([^\n]+)",
        r"Final Diagnosis:\s*([^\n]+)",
    ):
        candidates.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    cleaned = []
    for candidate in candidates:
        normalized = re.sub(r"[^A-Za-z0-9 ,/+_-]", " ", candidate).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        if normalized and normalized.lower() not in DIAGNOSIS_STOPWORDS:
            cleaned.append(normalized[:120])
    if not cleaned:
        normalized_text = re.sub(r"[^A-Za-z0-9 ,/+_-]", " ", text).strip()
        normalized_text = re.sub(r"\s+", " ", normalized_text)
        if 2 <= len(normalized_text) <= 120:
            cleaned.append(normalized_text)
    return "; ".join(dict.fromkeys(cleaned))


def _contains_clinical_term(text: str, term: str) -> bool:
    if len(term) <= 4 and term.replace(" ", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def _lab_group_set(lab_group: str) -> set[str]:
    return {part for part in lab_group.split("+") if part}


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip().replace(".", " ").replace("/", "-").replace("_", "-")
    cleaned = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    formats = (
        "%Y-%m-%d",
        "%Y-%d-%m",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %b %y",
        "%d %B %y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%b-%y",
        "%d-%B-%y",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        if 1990 <= parsed.year <= datetime.now(UTC).year + 1:
            return parsed.replace(tzinfo=UTC)
    return None
