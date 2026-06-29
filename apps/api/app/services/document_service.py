import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.document import MedicalDocument
from app.models.user import User
from app.services.storage_service import ObjectStorageService

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
ALLOWED_DOCUMENT_TYPES = {
    "past_record",
    "health_scan",
    "lab_report",
    "prescription",
    "discharge_summary",
    "imaging",
    "dental_image",
    "symptom_photo",
    "vaccination_record",
    "insurance",
}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def register_upload(
        self,
        *,
        user: User,
        file: UploadFile,
        document_type: str,
        patient_id: str | None = None,
    ) -> MedicalDocument:
        if document_type not in ALLOWED_DOCUMENT_TYPES:
            raise ValueError("Unsupported medical document category")
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise ValueError("Unsupported document type")

        target_patient_id = patient_id or user.id
        key = f"patients/{target_patient_id}/documents/{uuid.uuid4()}-{file.filename or 'upload'}"
        stored = await ObjectStorageService().put_upload(file=file, key=key)
        if stored.size_bytes > MAX_UPLOAD_BYTES:
            raise ValueError("Document exceeds 20 MB limit")

        doc = MedicalDocument(
            id=str(uuid.uuid4()),
            patient_id=target_patient_id,
            original_filename=file.filename or "upload",
            storage_uri=stored.uri,
            storage_bucket=stored.bucket,
            storage_key=stored.key,
            sha256=stored.sha256,
            document_type=document_type,
            mime_type=file.content_type or "",
            file_size_bytes=stored.size_bytes,
            malware_status="pending",
            status="ocr_pending",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def verify_ocr(self, *, doc_id: str, user: User, verified_text: str) -> MedicalDocument:
        doc = self.db.get(MedicalDocument, doc_id)
        if doc is None or doc.patient_id != user.id:
            raise LookupError("Document not found")
        doc.verified_text = verified_text
        doc.verified_by_patient = True
        doc.ocr_review_status = "human_verified"
        doc.status = "verified"
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def verify_image_findings(self, *, doc_id: str, clinician: User, verified_findings: str) -> MedicalDocument:
        if clinician.role not in {"doctor", "hospital_admin"}:
            raise PermissionError("Only clinical staff can verify medical image findings")
        doc = self.db.get(MedicalDocument, doc_id)
        if doc is None:
            raise LookupError("Document not found")
        doc.clinician_verified_findings = verified_findings
        doc.clinician_verified_by = clinician.id
        doc.image_review_status = "clinician_verified"
        doc.verified_text = (
            f"Clinician-verified findings for {doc.image_modality or 'medical image'}:\n"
            f"{verified_findings}\n\n"
            "Note: Findings were verified by licensed clinical staff before RAG ingestion."
        )
        doc.verified_by_patient = False
        doc.status = "image_findings_verified"
        self.db.commit()
        self.db.refresh(doc)
        return doc
