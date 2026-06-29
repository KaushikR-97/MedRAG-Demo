from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import re
import uuid
from datetime import datetime, UTC

from app.core.security import require_role, get_current_user
from app.db.session import get_db
from app.models.document import MedicalDocument
from app.models.feature_modules import Appointment, Prescription, SecondOpinionRequest
from app.models.user import User
from app.schemas.features import (
    DrugInteractionRequest,
    PrescriptionCreate,
    ReferralRequest,
    SecondOpinionRequest as LegacySecondOpinionRequest,
    SoapRequest,
    SoapResponse,
    SecondOpinionCreateRequest,
    SecondOpinionResponseRequest,
    SecondOpinionRecord,
)
from app.services.care_workflow_service import CareWorkflowService
from app.services.clinical_tools_service import ClinicalToolsService
from app.services.compliance_service import ComplianceService

def redact_phi(text: str) -> str:
    # 1. Redact phone numbers (Indian formats: +919876543210, etc.)
    text = re.sub(r"\b(?:\+?91[\s-]?)?[6789]\d{9}\b", "[REDACTED PHONE]", text)
    # 2. Redact emails
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED EMAIL]", text)
    # 3. Redact Aadhaar card numbers
    text = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[REDACTED AADHAAR]", text)
    # 4. Redact patient names
    text = re.sub(r"\b(patient name|name|patient)\b\s*:\s*[A-Za-z\s\d]+(?=\n|$|\.)", r"\1: [REDACTED NAME]", text, flags=re.IGNORECASE)
    return text

router = APIRouter()


@router.post("/prescriptions")
def create_prescription(
    payload: PrescriptionCreate,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    if not ComplianceService(db).can_access_patient(actor=doctor, patient_id=payload.patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    rx = CareWorkflowService(db).create_prescription(doctor=doctor, payload=payload.model_dump())
    prescription_doc = (
        db.query(MedicalDocument)
        .filter(
            MedicalDocument.patient_id == rx.patient_id,
            MedicalDocument.document_type == "prescription",
            MedicalDocument.verified_text.contains(rx.id),
        )
        .order_by(MedicalDocument.created_at.desc())
        .first()
    )
    interactions = ClinicalToolsService().check_interactions(payload.medications.splitlines())
    return {
        "id": rx.id,
        "document_id": prescription_doc.id if prescription_doc else "",
        "ingested_to_rag": bool(prescription_doc.ingested_to_rag) if prescription_doc else False,
        "interaction_warnings": [item.__dict__ for item in interactions],
    }


@router.get("/prescriptions/renewal-alerts")
def rx_renewal_alerts(doctor: User = Depends(require_role("doctor", "hospital_admin")), db: Session = Depends(get_db)) -> dict:
    records = db.query(Prescription).filter(Prescription.doctor_id == doctor.id).all()
    return {"alerts": [{"prescription_id": rx.id, "follow_up_date": rx.follow_up_date} for rx in records if rx.follow_up_date]}


@router.post("/drug-interactions")
def drug_interactions(payload: DrugInteractionRequest, _doctor: User = Depends(require_role("doctor", "hospital_admin"))) -> dict:
    return {"interactions": [item.__dict__ for item in ClinicalToolsService().check_interactions(payload.medicines)]}


@router.post("/soap-note", response_model=SoapResponse)
def soap_note(payload: SoapRequest, _doctor: User = Depends(require_role("doctor", "hospital_admin"))) -> SoapResponse:
    text = payload.visit_summary
    soap = {
        "subjective": f"Patient reports: {text}",
        "objective": "Vitals: BP 120/80 mmHg, Pulse 72/min, Temp 98.6 F. Labs: Reviewed standard panels.",
        "assessment": f"Differential diagnoses evaluated. Primary query: {text[:80]}...",
        "plan": "Continue current dosage. Schedule regular follow-up in 2 weeks. Monitor for any red flag symptoms.",
    }
    warnings = ClinicalToolsService().check_soap_note_diff(
        visit_summary=text,
        subjective=soap["subjective"],
        plan=soap["plan"]
    )
    return SoapResponse(soap=soap, diff_warnings=warnings)


@router.post("/referral-letter")
def referral(
    payload: ReferralRequest,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    if not ComplianceService(db).can_access_patient(actor=doctor, patient_id=payload.patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    return {
        "letter": (
            f"Referral from Dr/Hospital user {doctor.full_name} for patient {payload.patient_id}. "
            f"Speciality: {payload.speciality}. Reason: {payload.reason}."
        )
    }


@router.post("/second-opinion")
def second_opinion(payload: LegacySecondOpinionRequest, _doctor: User = Depends(require_role("doctor", "hospital_admin"))) -> dict:
    return {
        "analysis": "Compare case summary against retrieved guideline context before finalizing.",
        "case_summary": payload.case_summary,
        "guideline_context": payload.guideline_context,
    }


@router.post("/second-opinion/create", response_model=SecondOpinionRecord)
def create_second_opinion_request(
    payload: SecondOpinionCreateRequest,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> SecondOpinionRecord:
    # Redact patient identifiers from the summary
    redacted = redact_phi(payload.redacted_summary)
    
    req = SecondOpinionRequest(
        id=str(uuid.uuid4()),
        clinician_id=doctor.id,
        specialty=payload.specialty,
        redacted_summary=redacted,
        clinical_question=payload.clinical_question,
        status="pending",
        created_at=datetime.now(UTC),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    
    # Audit log
    from app.services.audit_service import AuditService
    AuditService(db).record(
        actor=doctor,
        patient_id="system",
        action="doctor.create_second_opinion",
        purpose="clinical_cooperation",
        resource_type="second_opinion_request",
        resource_id=req.id,
        details={"specialty": req.specialty},
    )
    
    return SecondOpinionRecord(
        id=req.id,
        clinician_id=req.clinician_id,
        specialty=req.specialty,
        redacted_summary=req.redacted_summary,
        clinical_question=req.clinical_question,
        status=req.status,
        response_recommendation=req.response_recommendation,
        responder_id=req.responder_id,
        created_at=req.created_at.isoformat()
    )


@router.get("/second-opinion/board", response_model=list[SecondOpinionRecord])
def get_second_opinion_board(
    _doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> list[SecondOpinionRecord]:
    reqs = db.query(SecondOpinionRequest).order_by(SecondOpinionRequest.created_at.desc()).all()
    result = []
    for r in reqs:
        result.append(SecondOpinionRecord(
            id=r.id,
            clinician_id=r.clinician_id,
            specialty=r.specialty,
            redacted_summary=r.redacted_summary,
            clinical_question=r.clinical_question,
            status=r.status,
            response_recommendation=r.response_recommendation,
            responder_id=r.responder_id,
            created_at=r.created_at.isoformat()
        ))
    return result


@router.post("/second-opinion/respond", response_model=SecondOpinionRecord)
def respond_second_opinion(
    payload: SecondOpinionResponseRequest,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> SecondOpinionRecord:
    req = db.query(SecondOpinionRequest).filter(SecondOpinionRequest.id == payload.request_id).first()
    if not req:
        raise HTTPException(404, "Second opinion request not found")
        
    req.status = "responded"
    req.response_recommendation = payload.response_recommendation
    req.responder_id = doctor.id
    db.commit()
    db.refresh(req)
    
    # Audit log
    from app.services.audit_service import AuditService
    AuditService(db).record(
        actor=doctor,
        patient_id="system",
        action="doctor.respond_second_opinion",
        purpose="clinical_cooperation_response",
        resource_type="second_opinion_request",
        resource_id=req.id,
        details={"specialty": req.specialty},
    )
    
    return SecondOpinionRecord(
        id=req.id,
        clinician_id=req.clinician_id,
        specialty=req.specialty,
        redacted_summary=req.redacted_summary,
        clinical_question=req.clinical_question,
        status=req.status,
        response_recommendation=req.response_recommendation,
        responder_id=req.responder_id,
        created_at=req.created_at.isoformat()
    )


@router.post("/differential-diagnosis")
def differential(payload: LegacySecondOpinionRequest, _doctor: User = Depends(require_role("doctor", "hospital_admin"))) -> dict:
    return {"differentials": ["Needs clinician-entered findings", "Use guideline-backed DDx model here"], "safety": "not a diagnosis"}


@router.get("/analytics")
def analytics(_doctor: User = Depends(require_role("doctor", "hospital_admin")), db: Session = Depends(get_db)) -> dict:
    return {
        "appointments": db.query(Appointment).count(),
        "prescriptions": db.query(Prescription).count(),
        "pmjay_prescriptions": db.query(Prescription).filter(Prescription.pmjay_covered.is_(True)).count(),
    }


@router.get("/prescriptions")
def list_prescriptions(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    if patient_id:
        if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="clinical.ask"):
            raise HTTPException(403, "Access denied")
        records = db.query(Prescription).filter(Prescription.patient_id == patient_id).all()
    else:
        if user.role == "doctor":
            records = db.query(Prescription).filter(Prescription.doctor_id == user.id).all()
        else:
            records = db.query(Prescription).filter(Prescription.patient_id == user.id).all()
    response = []
    for r in records:
        prescription_doc = (
            db.query(MedicalDocument)
            .filter(
                MedicalDocument.patient_id == r.patient_id,
                MedicalDocument.document_type == "prescription",
                MedicalDocument.verified_text.contains(r.id),
                MedicalDocument.status != "deleted_by_patient",
            )
            .order_by(MedicalDocument.created_at.desc())
            .first()
        )
        response.append(
            {
            "id": r.id,
            "patient_id": r.patient_id,
            "doctor_id": r.doctor_id,
            "diagnosis": r.diagnosis,
            "medications": r.medications,
            "dosage": r.dosage,
            "duration": r.duration,
            "instructions": r.instructions,
            "follow_up_date": r.follow_up_date,
            "pmjay_covered": r.pmjay_covered,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "document_id": prescription_doc.id if prescription_doc else "",
            "ingested_to_rag": bool(prescription_doc.ingested_to_rag) if prescription_doc else False,
        }
        )
    return response


@router.post("/ai-prescription")
def suggest_ai_prescription(
    payload: dict,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(400, "patient_id required")
    if not ComplianceService(db).can_access_patient(actor=doctor, patient_id=patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Access denied")
        
    from app.models.patient import PatientProfile
    from app.models.user import User as UserModel
    
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
    patient_user = db.get(UserModel, patient_id)
    
    if not profile or not patient_user:
        raise HTTPException(404, "Patient not found")
        
    allergies = profile.allergies or "No known allergies"
    conditions = profile.chronic_conditions or "No chronic conditions"
    meds = profile.current_medications or "No current medications"
    notes = payload.get("notes", "")
    
    from app.services.generation_service import ClinicalGenerationService
    from app.rag.retriever import RetrievedChunk
    
    profile_summary = (
        f"Allergies: {allergies}\n"
        f"Chronic Conditions: {conditions}\n"
        f"Current Medications: {meds}\n"
        f"Active clinical visit notes: {notes}"
    )
    
    source = RetrievedChunk(
        id="patient-profile",
        title="Patient Profile Summary",
        score=1.0,
        text=profile_summary
    )
    
    prompt = (
        "Generate a structured drug prescription draft. "
        "Review the allergies and current medications to avoid interactions. "
        "Provide direct recommendations for medicine name, dosage, duration, and instructions. "
        "Format the response strictly as a JSON object with keys: diagnosis, medications, dosage, duration, instructions. "
        "Keep it concise."
    )
    
    gen_service = ClinicalGenerationService()
    ai_raw = gen_service.generate(
        question=prompt,
        user_role="doctor",
        conversation_history=[],
        sources=[source],
        disclaimer=None
    )
    
    import json
    try:
        clean_text = ai_raw.strip()
        if clean_text.startswith("```"):
            clean_text = clean_text.strip("`")
            if clean_text.lower().startswith("json"):
                clean_text = clean_text[4:].strip()
        parsed = json.loads(clean_text)
    except Exception:
        parsed = {
            "diagnosis": "Diagnosed based on clinical presentation",
            "medications": "AI Recommendations:\n" + ai_raw,
            "dosage": "As recommended",
            "duration": "As recommended",
            "instructions": "As recommended",
        }
        
    return parsed


@router.get("/prescriptions/{rx_id}/education")
def educate_patient_on_prescription(
    rx_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rx = db.get(Prescription, rx_id)
    if rx is None:
        raise HTTPException(404, "Prescription not found")
    if rx.patient_id != user.id and not ComplianceService(db).can_access_patient(actor=user, patient_id=rx.patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Access denied")
        
    from app.services.generation_service import ClinicalGenerationService
    from app.rag.retriever import RetrievedChunk
    
    rx_details = (
        f"Medications: {rx.medications}\n"
        f"Dosage: {rx.dosage}\n"
        f"Duration: {rx.duration}\n"
        f"Instructions: {rx.instructions}\n"
        f"Diagnosis: {rx.diagnosis}"
    )
    
    source = RetrievedChunk(
        id="prescription-details",
        title="Doctor Prescription Details",
        score=1.0,
        text=rx_details
    )
    
    prompt = (
        "Explain in plain, educational language how the patient should take these medications. "
        "Highlight food requirements (before/after meal), precautions, minor side effects, "
        "and red flags to call the doctor immediately. Keep it easy to understand and friendly."
    )
    
    gen_service = ClinicalGenerationService()
    education = gen_service.generate(
        question=prompt,
        user_role="patient",
        conversation_history=[],
        sources=[source],
        disclaimer="Disclaimer: This is for educational support only. Follow your doctor's instructions."
    )
    
    return {"education": education}
