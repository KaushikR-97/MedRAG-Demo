import uuid
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import MedicalDocument
from app.models.feature_modules import (
    Appointment,
    FamilyMember,
    HealthTask,
    LabResult,
    MedicationReminder,
    MentalHealthScreening,
    PregnancyRecord,
    Prescription,
    SymptomEntry,
    VaccinationRecord,
)
from app.models.jobs import IngestionJob
from app.rag.clinical_timeline import build_prescription_timeline_context
from app.models.user import User
from app.rag.indexer import MedicalVectorIndexer
from app.services.clinical_tools_service import ClinicalToolsService
from app.services.storage_service import ObjectStorageService


class CareWorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tools = ClinicalToolsService()

    def create_prescription(self, *, doctor: User, payload: dict) -> Prescription:
        rx = Prescription(id=str(uuid.uuid4()), doctor_id=doctor.id, **payload)
        self.db.add(rx)
        self.db.commit()
        self.db.refresh(rx)
        self._mirror_prescription_to_vault_and_rag(rx=rx, doctor=doctor)
        return rx

    def _mirror_prescription_to_vault_and_rag(self, *, rx: Prescription, doctor: User) -> None:
        text = self._prescription_text(rx=rx, doctor=doctor)
        filename = f"Prescription-{rx.created_at.date().isoformat() if rx.created_at else datetime.now(UTC).date().isoformat()}-{rx.id[:8]}.txt"
        storage_bucket = ""
        storage_key = ""
        storage_uri = ""
        sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        size_bytes = len(text.encode("utf-8"))
        try:
            stored = ObjectStorageService().put_bytes(
                content=text.encode("utf-8"),
                key=f"patients/{rx.patient_id}/documents/prescriptions/{rx.id}.txt",
                content_type="text/plain; charset=utf-8",
            )
            storage_bucket = stored.bucket
            storage_key = stored.key
            storage_uri = stored.uri
            sha256 = stored.sha256
            size_bytes = stored.size_bytes
        except Exception:
            if not settings.is_non_prod:
                raise

        existing = (
            self.db.query(MedicalDocument)
            .filter(
                MedicalDocument.patient_id == rx.patient_id,
                MedicalDocument.document_type == "prescription",
                MedicalDocument.storage_key == storage_key,
            )
            .first()
            if storage_key
            else None
        )
        doc = existing or MedicalDocument(
            id=str(uuid.uuid4()),
            patient_id=rx.patient_id,
            original_filename=filename,
            storage_uri=storage_uri,
            storage_bucket=storage_bucket,
            storage_key=storage_key,
            sha256=sha256,
            document_type="prescription",
            mime_type="text/plain",
            file_size_bytes=size_bytes,
            malware_status="clean",
            ocr_text=text,
            ocr_engine="doctor_signed_prescription",
            ocr_confidence="1.000",
            ocr_review_status="doctor_signed",
            verified_text=text,
            verified_by_patient=True,
            status="verified",
        )
        doc.original_filename = filename
        doc.storage_uri = storage_uri
        doc.storage_bucket = storage_bucket
        doc.storage_key = storage_key
        doc.sha256 = sha256
        doc.file_size_bytes = size_bytes
        doc.ocr_text = text
        doc.verified_text = text
        doc.verified_by_patient = True
        doc.malware_status = "clean"
        doc.status = "verified"
        self.db.add(doc)
        self.db.flush()

        indexing_error = ""
        try:
            indexed = MedicalVectorIndexer().index_verified_document(
                document_id=doc.id,
                patient_id=doc.patient_id,
                title=doc.original_filename,
                text=text,
                document_type=doc.document_type,
                source_created_at=doc.created_at.isoformat() if doc.created_at else "",
                clinical_context=build_prescription_timeline_context(rx).as_payload(),
            )
        except Exception as exc:
            indexed = 0
            indexing_error = str(exc)
        doc.ingested_to_rag = indexed > 0
        doc.status = "rag_ingested" if indexed > 0 else "ingestion_failed"
        job = IngestionJob(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            patient_id=doc.patient_id,
            job_type="prescription_rag_ingest",
            status="completed" if indexed > 0 else "failed",
            error="" if indexed > 0 else indexing_error or "No prescription chunks were indexed into RAG",
            attempts=1,
        )
        self.db.add(job)
        self.db.commit()

    @staticmethod
    def _prescription_text(*, rx: Prescription, doctor: User) -> str:
        created_at = rx.created_at.isoformat() if rx.created_at else datetime.now(UTC).isoformat()
        return (
            "Signed Prescription\n"
            f"Prescription ID: {rx.id}\n"
            f"Date: {created_at}\n"
            f"Doctor: {doctor.full_name} ({doctor.id})\n"
            f"Patient ID: {rx.patient_id}\n"
            f"Diagnosis: {rx.diagnosis}\n"
            f"Medications: {rx.medications}\n"
            f"Dosage: {rx.dosage or 'As directed'}\n"
            f"Duration: {rx.duration or 'As directed'}\n"
            f"Instructions: {rx.instructions or 'Follow clinician instructions.'}\n"
            f"Follow-up Date: {rx.follow_up_date or 'Not specified'}\n"
            f"PM-JAY Covered: {'Yes' if rx.pmjay_covered else 'No'}\n"
        )

    def book_appointment(self, *, patient_id: str, payload: dict) -> Appointment:
        appt = Appointment(id=str(uuid.uuid4()), patient_id=patient_id, **payload)
        if not appt.booking_reference:
            appt.booking_reference = f"REQ-{uuid.uuid4().hex[:8].upper()}"
        self.db.add(appt)
        self.db.commit()
        self.db.refresh(appt)
        return appt

    def add_family_member(self, *, owner_id: str, payload: dict) -> FamilyMember:
        member = FamilyMember(id=str(uuid.uuid4()), owner_id=owner_id, **payload)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def create_medication_reminder(self, *, patient_id: str, payload: dict) -> MedicationReminder:
        reminder = MedicationReminder(id=str(uuid.uuid4()), patient_id=patient_id, **payload)
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def track_symptoms(self, *, patient_id: str, symptoms: str, severity: int, duration: str) -> SymptomEntry:
        entry = SymptomEntry(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            symptoms=symptoms,
            severity=severity,
            duration=duration,
            triage_result=self.tools.symptom_triage(symptoms=symptoms, severity=severity),
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def save_lab_result(self, *, patient_id: str, test_name: str, value: float, unit: str) -> LabResult:
        result = LabResult(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            test_name=test_name,
            value=value,
            unit=unit,
            interpretation=self.tools.interpret_lab(test_name=test_name, value=value, unit=unit),
        )
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def add_vaccination(self, *, patient_id: str, payload: dict) -> VaccinationRecord:
        record = VaccinationRecord(id=str(uuid.uuid4()), patient_id=patient_id, **payload)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def add_pregnancy(self, *, patient_id: str, lmp_date: str, notes: str = "") -> PregnancyRecord:
        estimated_due_date = ""
        try:
            lmp = datetime.fromisoformat(lmp_date)
            estimated_due_date = (lmp + timedelta(days=280)).date().isoformat()
        except ValueError:
            pass
        record = PregnancyRecord(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            lmp_date=lmp_date,
            estimated_due_date=estimated_due_date,
            notes=notes,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def save_mental_health_screening(
        self,
        *,
        patient_id: str,
        screening_type: str,
        score: int,
    ) -> MentalHealthScreening:
        screening = MentalHealthScreening(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            screening_type=screening_type,
            score=score,
            risk_level=self.tools.mental_health_risk(score=score, screening_type=screening_type),
        )
        self.db.add(screening)
        self.db.commit()
        self.db.refresh(screening)
        return screening

    def generate_health_tasks(self, *, patient_id: str) -> list[HealthTask]:
        task = HealthTask(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            task_type="annual_checkup",
            title="Schedule annual preventive health checkup",
            description="Generated by health score/reminder engine.",
            priority="medium",
            due_date=datetime.now(UTC).date().isoformat(),
        )
        self.db.add(task)
        self.db.commit()
        return [task]
