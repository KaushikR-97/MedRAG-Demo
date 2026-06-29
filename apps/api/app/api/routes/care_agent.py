from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.graphs.care_agent_graph import CareCoordinationAgent
from app.models.user import User
from app.schemas.features import CareAgentResponse, SymptomCareAgentRequest, YearlyHealthScanRequest
from app.services.compliance_service import ComplianceService

router = APIRouter()


@router.post("/yearly-health-scan", response_model=CareAgentResponse)
def schedule_yearly_health_scan(
    payload: YearlyHealthScanRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareAgentResponse:
    del request
    if user.role != "patient":
        raise HTTPException(403, "Only patients can self-schedule yearly health scans")
    state = CareCoordinationAgent(db).plan_yearly_scan(
        actor=user,
        preferred_date=payload.preferred_date,
        preferred_time_slot=payload.preferred_time_slot,
    )
    return CareAgentResponse(
        action=state["action"],
        safety_label=state["safety_label"],
        reasoning=state["reasoning"],
        result=state["result"],
    )


@router.post("/symptom-action", response_model=CareAgentResponse)
def coordinate_symptom_action(
    payload: SymptomCareAgentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareAgentResponse:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    state = CareCoordinationAgent(db).coordinate_symptoms(
        actor=user,
        patient_id=patient_id,
        symptoms=payload.symptoms,
        severity=payload.severity,
        location_text=payload.location_text,
        preferred_date=payload.preferred_date,
        preferred_time_slot=payload.preferred_time_slot,
        acoustic_cough_type=payload.acoustic_cough_type,
        wheeze_acoustic_type=payload.wheeze_acoustic_type,
    )
    return CareAgentResponse(
        action=state["action"],
        safety_label=state["safety_label"],
        reasoning=state["reasoning"],
        result=state["result"],
    )
