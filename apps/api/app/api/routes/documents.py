from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.document import MedicalDocument
from app.models.feature_modules import Hospital, HospitalResourceBooking
from app.models.jobs import IngestionJob
from app.models.user import User
from app.schemas.documents import DocumentRecord, IngestionJobRecord, VerifyImageFindingsRequest, VerifyOcrRequest
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService
from app.services.privacy_service import PrivacyService
from app.services.storage_service import ObjectStorageService
from app.services.compliance_service import ComplianceService

router = APIRouter()


@router.post("/upload", response_model=DocumentRecord)
async def upload_document(
    document_type: str,
    patient_id: str | None = None,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRecord:
    target_patient_id = patient_id or user.id
    if user.role == "patient" and target_patient_id != user.id:
        raise HTTPException(403, "Patients can only upload to their own vault")
    if user.role == "hospital_admin" and not _hospital_can_upload_for_patient(db, user, target_patient_id):
        raise HTTPException(403, "Hospital upload window is closed. Uploads are allowed until 3 days after discharge.")
    if user.role not in {"patient", "hospital_admin"} and target_patient_id != user.id:
        raise HTTPException(403, "Only patients or authorized hospital admins can upload patient records")
    try:
        doc = await DocumentService(db).register_upload(
            user=user,
            file=file,
            document_type=document_type,
            patient_id=target_patient_id,
        )
        IngestionService(db).enqueue_document_pipeline(doc=doc, user=user)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return DocumentRecord.model_validate(doc, from_attributes=True)


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if doc.patient_id != user.id:
        raise HTTPException(403, "Only the patient can delete this record")
    doc.status = "deleted_by_patient"
    db.commit()
    return {"status": "deleted"}


@router.post("/{doc_id}/retry-ingestion", response_model=DocumentRecord)
def retry_document_ingestion(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRecord:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if doc.patient_id != user.id and not ComplianceService(db).can_access_patient(
        actor=user,
        patient_id=doc.patient_id,
        scope="documents.read",
    ):
        raise HTTPException(403, "Access denied")
    if doc.status == "deleted_by_patient":
        raise HTTPException(404, "Document not found")

    if (doc.verified_by_patient or doc.image_review_status == "clinician_verified") and doc.verified_text:
        doc.ingested_to_rag = False
        db.add(doc)
        db.flush()
        IngestionService(db).enqueue_verified_document_ingestion(doc=doc, user=user)
    else:
        doc.status = "uploaded"
        doc.malware_status = "pending"
        doc.ocr_warning = ""
        doc.ingested_to_rag = False
        db.add(doc)
        db.flush()
        IngestionService(db).enqueue_document_pipeline(doc=doc, user=user)
    db.refresh(doc)
    return DocumentRecord.model_validate(doc, from_attributes=True)


@router.get("", response_model=list[DocumentRecord])
def list_documents(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentRecord]:
    target_id = patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=target_id, scope="documents.read"):
        raise HTTPException(403, "Access denied")
    docs = db.query(MedicalDocument).filter(
        MedicalDocument.patient_id == target_id,
        MedicalDocument.status != "deleted_by_patient",
    ).all()
    return [DocumentRecord.model_validate(d, from_attributes=True) for d in docs]


def _hospital_can_upload_for_patient(db: Session, admin: User, patient_id: str) -> bool:
    now = datetime.now(UTC)
    return (
        db.query(HospitalResourceBooking)
        .join(Hospital, Hospital.id == HospitalResourceBooking.hospital_id)
        .filter(
            Hospital.admin_user_id == admin.id,
            HospitalResourceBooking.patient_id == patient_id,
            HospitalResourceBooking.status.in_(["approved", "admitted", "discharged"]),
            (
                HospitalResourceBooking.discharged_at.is_(None)
                | (HospitalResourceBooking.discharged_at >= now - timedelta(days=3))
            ),
        )
        .first()
        is not None
    )


@router.post("/{doc_id}/verify-image-findings", response_model=DocumentRecord)
def verify_image_findings(
    doc_id: str,
    payload: VerifyImageFindingsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRecord:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=doc.patient_id, scope="documents.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    try:
        verified = DocumentService(db).verify_image_findings(
            doc_id=doc_id,
            clinician=user,
            verified_findings=payload.verified_findings,
        )
        IngestionService(db).enqueue_verified_document_ingestion(doc=verified, user=user)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return DocumentRecord.model_validate(verified, from_attributes=True)


@router.post("/{doc_id}/verify-ocr", response_model=DocumentRecord)
def verify_ocr(
    doc_id: str,
    payload: VerifyOcrRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRecord:
    try:
        doc = DocumentService(db).verify_ocr(doc_id=doc_id, user=user, verified_text=payload.verified_text)
        IngestionService(db).enqueue_verified_document_ingestion(doc=doc, user=user)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return DocumentRecord.model_validate(doc, from_attributes=True)


@router.get("/jobs/{job_id}", response_model=IngestionJobRecord)
def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestionJobRecord:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.patient_id != user.id and not ComplianceService(db).can_access_patient(
        actor=user,
        patient_id=job.patient_id,
        scope="documents.read",
    ):
        raise HTTPException(404, "Job not found")
    return IngestionJobRecord.model_validate(job, from_attributes=True)


@router.get("/{doc_id}/jobs", response_model=list[IngestionJobRecord])
def list_document_jobs(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IngestionJobRecord]:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=doc.patient_id, scope="documents.read"):
        raise HTTPException(404, "Document not found")
    jobs = (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == doc_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(20)
        .all()
    )
    return [IngestionJobRecord.model_validate(job, from_attributes=True) for job in jobs]


@router.get("/{doc_id}/download")
def download_document(
    doc_id: str,
    inline: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    PrivacyService().assert_no_download(actor=user, patient_id=doc.patient_id, resource="medical_document")
    if not doc.storage_key and doc.verified_text:
        content = doc.verified_text.encode("utf-8")
    else:
        content = ObjectStorageService().get_bytes(bucket=doc.storage_bucket, key=doc.storage_key)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=content,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{doc.original_filename}"',
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


from app.schemas.features import ImagerySimilarityResponse

@router.get("/imagery/similar-cases/{doc_id}", response_model=ImagerySimilarityResponse)
def get_similar_cases(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImagerySimilarityResponse:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
        
    modality = (doc.image_modality or "").lower()
    
    similar_cases = []
    
    if "chest" in modality or "x-ray" in modality or "xray" in modality:
        similar_cases = [
            {
                "case_id": "case-sim-001",
                "modality": "Chest X-Ray",
                "observations": "Increased opacity in lower right lobe, indicative of lobar pneumonia.",
                "treatment_plan": "Amoxicillin 500mg TDS for 7 days. Scheduled follow-up in 10 days.",
                "outcome": "Resolved: complete clearance of opacity observed on follow-up X-Ray.",
                "similarity_score": 0.94
            },
            {
                "case_id": "case-sim-002",
                "modality": "Chest X-Ray",
                "observations": "Bilateral infiltrates with cavitation in upper lobes. Suspected pulmonary TB.",
                "treatment_plan": "Standard 4-drug HRZE anti-tubercular therapy for 2 months, followed by 4 months HR.",
                "outcome": "Completed: patient cured, sputum smear negative at end of treatment.",
                "similarity_score": 0.88
            },
            {
                "case_id": "case-sim-003",
                "modality": "Chest X-Ray",
                "observations": "Mild hyperinflation with flattened diaphragms, matching chronic COPD findings.",
                "treatment_plan": "Tiotropium inhaler once daily, Salbutamol PRN. Recommended smoking cessation.",
                "outcome": "Stable: symptoms managed, lung function maintained at baseline.",
                "similarity_score": 0.81
            }
        ]
    elif "dental" in modality or "teeth" in modality or "ortho" in modality:
        similar_cases = [
            {
                "case_id": "case-sim-004",
                "modality": "Dental Panoramic X-Ray",
                "observations": "Deep dentinal caries in lower right second molar (tooth #47) with pulpal involvement.",
                "treatment_plan": "Root canal therapy followed by crown placement. Recommended fluoride mouthwash.",
                "outcome": "Successful: pain eliminated, tooth fully restored.",
                "similarity_score": 0.91
            },
            {
                "case_id": "case-sim-005",
                "modality": "Dental Panoramic X-Ray",
                "observations": "Impacted lower third molars (teeth #38 and #48) showing horizontal impaction.",
                "treatment_plan": "Surgical extraction of bilateral third molars under local anesthesia.",
                "outcome": "Healed: normal postoperative recovery, no nerve paresthesia.",
                "similarity_score": 0.85
            },
            {
                "case_id": "case-sim-006",
                "modality": "Dental Panoramic X-Ray",
                "observations": "Generalized horizontal bone loss, diagnostic of moderate chronic periodontitis.",
                "treatment_plan": "Scaling and root planing (deep cleaning), chlorhexidine mouthrinse, 3-month recall.",
                "outcome": "Managed: pocket depths reduced, bleeding on probing resolved.",
                "similarity_score": 0.79
            }
        ]
    else:
        # Default cases
        similar_cases = [
            {
                "case_id": "case-sim-007",
                "modality": "General Imaging Scan",
                "observations": "Standard scan showing unremarkable structures.",
                "treatment_plan": "Reassured patient. No active intervention needed.",
                "outcome": "Normal",
                "similarity_score": 0.75
            }
        ]
        
    return ImagerySimilarityResponse(similar_cases=similar_cases)
