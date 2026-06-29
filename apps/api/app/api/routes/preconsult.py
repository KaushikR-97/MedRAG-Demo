from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.features import (
    PreConsultationFeedback,
    PreConsultationIntakeSubmit,
    PreConsultationRecord,
)
from app.services.audit_service import AuditService
from app.services.preconsult_agent_service import PreConsultAgentService

router = APIRouter()


@router.get("/appointments/{appointment_id}", response_model=PreConsultationRecord)
def get_preconsultation(
    appointment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PreConsultationRecord:
    try:
        service = PreConsultAgentService(db)
        intake = service.get_for_appointment(appointment_id=appointment_id, actor=user)
        return PreConsultationRecord(**service.record(intake))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/appointments/{appointment_id}/intake", response_model=PreConsultationRecord)
def submit_preconsultation_intake(
    appointment_id: str,
    payload: PreConsultationIntakeSubmit,
    request: Request,
    patient: User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
) -> PreConsultationRecord:
    try:
        service = PreConsultAgentService(db)
        intake = service.submit_patient_intake(
            appointment_id=appointment_id,
            patient=patient,
            symptoms=payload.symptoms,
            reason_for_call=payload.reason_for_call,
        )
        AuditService(db).record(
            actor=patient,
            patient_id=patient.id,
            action="preconsult.patient_intake_submitted",
            purpose="preconsult_agent",
            resource_type="pre_consultation_intake",
            resource_id=intake.id,
            ip_address=request.client.host if request.client else "",
            details={"appointment_id": appointment_id, "status": intake.status},
        )
        return PreConsultationRecord(**service.record(intake))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/appointments/{appointment_id}/generate", response_model=PreConsultationRecord)
def generate_preconsultation_draft(
    appointment_id: str,
    request: Request,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> PreConsultationRecord:
    try:
        service = PreConsultAgentService(db)
        intake = service.generate_doctor_draft(appointment_id=appointment_id, doctor=doctor)
        AuditService(db).record(
            actor=doctor,
            patient_id=intake.patient_id,
            action="preconsult.draft_generated",
            purpose="preconsult_agent",
            resource_type="pre_consultation_intake",
            resource_id=intake.id,
            ip_address=request.client.host if request.client else "",
            details={"appointment_id": appointment_id, "status": intake.status},
        )
        return PreConsultationRecord(**service.record(intake))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/appointments/{appointment_id}/feedback", response_model=PreConsultationRecord)
def score_preconsultation_draft(
    appointment_id: str,
    payload: PreConsultationFeedback,
    request: Request,
    doctor: User = Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> PreConsultationRecord:
    try:
        service = PreConsultAgentService(db)
        intake = service.record_doctor_feedback(
            appointment_id=appointment_id,
            doctor=doctor,
            approved=payload.approved,
            feedback=payload.feedback,
        )
        AuditService(db).record(
            actor=doctor,
            patient_id=intake.patient_id,
            action="preconsult.draft_scored",
            purpose="preconsult_agent_reward",
            resource_type="pre_consultation_intake",
            resource_id=intake.id,
            ip_address=request.client.host if request.client else "",
            details={"approved": payload.approved, "reward_score": intake.reward_score},
        )
        return PreConsultationRecord(**service.record(intake))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
