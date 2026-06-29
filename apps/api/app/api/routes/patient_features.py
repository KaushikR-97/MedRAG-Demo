import uuid
import json
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.security import get_current_user, generate_12_digit_id
from app.db.session import get_db
from app.models.user import User
from app.models.compliance import ConsentGrant
from app.models.patient import PatientProfile
from app.models.feature_modules import FamilyMember, IotPillboxAlert, MedicationReminder, PatientCalendarEvent
from app.schemas.features import (
    AppointmentCreate,
    FamilyMemberCreate,
    FamilyMemberRegisterRequest,
    FamilyMemberResponse,
    LabResultCreate,
    MedicationReminderCreate,
    MentalHealthCreate,
    PregnancyCreate,
    SymptomTrackRequest,
    VaccinationCreate,
    PillboxPingRequest,
    PillboxAlertRecord,
    MentalHealthConversationScreeningRequest,
    MentalHealthScreeningResponse,
)
from app.services.care_workflow_service import CareWorkflowService
from app.services.clinical_tools_service import ClinicalToolsService
from app.services.compliance_service import ComplianceService

router = APIRouter()


@router.post("/appointments")
def book_appointment(
    payload: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).book_appointment(patient_id=patient_id, payload=payload.model_dump())
    return {"id": record.id, "status": record.status}


@router.post("/family")
def add_family(
    payload: FamilyMemberCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    record = CareWorkflowService(db).add_family_member(owner_id=user.id, payload=payload.model_dump())
    return {"id": record.id}


@router.post("/family/register")
def register_family_member(
    payload: FamilyMemberRegisterRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "patient":
        raise HTTPException(403, "Only patients can register family members")
    if not payload.full_name.strip():
        raise HTTPException(400, "Family member name is required")
    try:
        child_id = generate_12_digit_id(db, User)
        child_email = f"family_{child_id}@medrag.in"
        from app.core.security import hash_password
        child_user = User(
            id=child_id,
            email=child_email,
            hashed_password=hash_password(str(uuid.uuid4())),
            full_name=payload.full_name.strip(),
            role="patient",
            phone=user.phone or "",
            age=payload.age or None,
            city=user.city or "",
        )
        db.add(child_user)
        db.flush()

        child_profile = PatientProfile(id=str(uuid.uuid4()), user_id=child_id)
        db.add(child_profile)

        member = FamilyMember(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            full_name=payload.full_name.strip(),
            relation=payload.relation,
            age=payload.age or 0,
            notes=payload.notes,
            member_user_id=child_id,
        )
        db.add(member)

        consent = ConsentGrant(
            id=str(uuid.uuid4()),
            patient_id=child_id,
            grantee_id=user.id,
            scope=payload.scope,
            purpose=f"Family/caregiver access by {user.full_name}",
            starts_at=datetime.now(UTC),
            expires_at=None,
        )
        db.add(consent)

        db.commit()
        return {"id": member.id, "member_user_id": child_id}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Family member could not be linked because a related account already exists. Please retry.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(500, f"Family member linking failed at database layer: {type(exc).__name__}. Ensure migrations are applied with alembic upgrade head.") from exc


@router.get("/family", response_model=list[FamilyMemberResponse])
def get_family_members(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    members = db.query(FamilyMember).filter(FamilyMember.owner_id == user.id).all()
    result = []
    for m in members:
        consent = None
        if m.member_user_id:
            now = datetime.now(UTC)
            grant = db.query(ConsentGrant).filter(
                ConsentGrant.patient_id == m.member_user_id,
                ConsentGrant.grantee_id == user.id,
                ConsentGrant.revoked_at.is_(None),
                ConsentGrant.starts_at <= now,
                or_(ConsentGrant.expires_at.is_(None), ConsentGrant.expires_at > now)
            ).first()
            if grant:
                consent = {
                    "id": grant.id,
                    "scope": grant.scope,
                    "purpose": grant.purpose,
                    "expires_at": grant.expires_at.isoformat() if grant.expires_at else None
                }
        result.append({
            "id": m.id,
            "full_name": m.full_name,
            "relation": m.relation,
            "age": m.age,
            "notes": m.notes,
            "member_user_id": m.member_user_id,
            "active_consent": consent
        })
    return result


@router.get("/profile/{patient_id}")
def get_patient_profile(
    patient_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")

    profile = db.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
    if profile is None:
        raise HTTPException(404, "Patient profile not found")

    patient = db.query(User).filter(User.id == patient_id).first()
    return {
        "patient_id": patient_id,
        "full_name": patient.full_name if patient else "",
        "blood_group": profile.blood_group,
        "date_of_birth": profile.date_of_birth,
        "gender": profile.gender,
        "allergies": profile.allergies,
        "chronic_conditions": profile.chronic_conditions,
        "current_medications": profile.current_medications,
        "abha_number": profile.abha_number,
    }


@router.post("/medication-reminders")
def create_reminder(
    payload: MedicationReminderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).create_medication_reminder(
        patient_id=patient_id,
        payload=payload.model_dump(exclude={"patient_id"}),
    )
    event = PatientCalendarEvent(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        event_type="medication_reminder",
        title=f"Medication reminder: {record.medicine_name}",
        starts_at=datetime.now(UTC),
        status="active",
        source="medication_reminder",
        metadata_json=json.dumps({"reminder_id": record.id, "schedule": record.schedule}),
        created_at=datetime.now(UTC),
    )
    db.add(event)
    db.commit()
    return {
        "id": record.id,
        "patient_id": record.patient_id,
        "medicine_name": record.medicine_name,
        "dosage": record.dosage,
        "schedule": record.schedule,
        "active": record.active,
        "created_at": "",
    }


@router.post("/symptoms")
def track_symptoms(payload: SymptomTrackRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).track_symptoms(
        patient_id=patient_id,
        symptoms=payload.symptoms,
        severity=payload.severity,
        duration=payload.duration,
    )
    return {"id": record.id, "triage_result": record.triage_result}


@router.post("/labs")
def save_lab(payload: LabResultCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).save_lab_result(
        patient_id=patient_id,
        test_name=payload.test_name,
        value=payload.value,
        unit=payload.unit,
    )
    return {"id": record.id, "interpretation": record.interpretation}


@router.post("/vaccinations")
def add_vaccination(
    payload: VaccinationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).add_vaccination(patient_id=patient_id, payload=payload.model_dump())
    return {"id": record.id}


@router.post("/pregnancy")
def add_pregnancy(payload: PregnancyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).add_pregnancy(patient_id=patient_id, lmp_date=payload.lmp_date, notes=payload.notes)
    return {"id": record.id, "estimated_due_date": record.estimated_due_date}


@router.post("/mental-health")
def mental_health(payload: MentalHealthCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    record = CareWorkflowService(db).save_mental_health_screening(
        patient_id=patient_id,
        screening_type=payload.screening_type,
        score=payload.score,
    )
    return {"id": record.id, "risk_level": record.risk_level}


@router.post("/health-score")
def health_score(completed_checks: int = 0, risk_factors: int = 0) -> dict:
    return {"score": ClinicalToolsService().health_score(completed_checks=completed_checks, risk_factors=risk_factors)}


@router.post("/health-tasks/run")
def run_health_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    tasks = CareWorkflowService(db).generate_health_tasks(patient_id=user.id)
    return {"created": len(tasks), "tasks": [{"id": task.id, "title": task.title, "priority": task.priority} for task in tasks]}


@router.post("/pillbox/ping")
def pillbox_ping(
    payload: PillboxPingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    reminder = db.query(MedicationReminder).filter(MedicationReminder.id == payload.reminder_id).first()
    if not reminder:
        reminder = MedicationReminder(
            id=payload.reminder_id,
            patient_id=user.id,
            medicine_name="Metformin 500mg (Simulated)",
            schedule="twice a day",
            active=True
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        
    alert = IotPillboxAlert(
        id=str(uuid.uuid4()),
        reminder_id=reminder.id,
        patient_id=reminder.patient_id,
        status=payload.status,
        logged_at=datetime.now(UTC),
    )
    db.add(alert)
    
    # If missed, create a caregiver alert event in patient's calendar
    if payload.status == "missed":
        event = PatientCalendarEvent(
            id=str(uuid.uuid4()),
            patient_id=reminder.patient_id,
            event_type="caregiver_alert",
            title=f"[IoT Alert] Missed dose: {reminder.medicine_name}",
            starts_at=datetime.now(UTC),
            status="active",
            source="iot_pillbox",
            metadata_json=json.dumps({"medication": reminder.medicine_name, "reminder_id": reminder.id}),
            created_at=datetime.now(UTC),
        )
        db.add(event)
        
        # Log audit trail
        from app.services.audit_service import AuditService
        AuditService(db).record(
            actor=user,
            patient_id=reminder.patient_id,
            action="patient.pillbox_missed_alert",
            purpose="medication_adherence_safety",
            resource_type="medication_reminder",
            resource_id=reminder.id,
            details={"medication": reminder.medicine_name, "status": "missed"},
        )
        
    db.commit()
    return {"status": "logged", "alert_id": alert.id, "caregiver_notified": payload.status == "missed"}


@router.get("/pillbox/alerts", response_model=list[PillboxAlertRecord])
def get_pillbox_alerts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PillboxAlertRecord]:
    # Patients see their own logs, doctors/admins see all
    query = db.query(IotPillboxAlert)
    if user.role == "patient":
        query = query.filter(IotPillboxAlert.patient_id == user.id)
    alerts = query.order_by(IotPillboxAlert.logged_at.desc()).all()
    
    result = []
    for a in alerts:
        result.append(PillboxAlertRecord(
            id=a.id,
            reminder_id=a.reminder_id,
            patient_id=a.patient_id,
            status=a.status,
            logged_at=a.logged_at.isoformat()
        ))
    return result


@router.post("/mental-health/screen-conversation", response_model=MentalHealthScreeningResponse)
def screen_conversation(
    payload: MentalHealthConversationScreeningRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MentalHealthScreeningResponse:
    from app.models.feature_modules import MentalHealthScreening
    
    text = payload.conversation_text.lower()
    
    # Calculate simulated sentiment score based on keyword presence
    neg_words = ["sad", "hopeless", "anxious", "worry", "depressed", "tired", "sleep", "appetite", "worthless", "trouble", "fail", "hurt"]
    score_penalty = 0.0
    for word in neg_words:
        if word in text:
            score_penalty += 0.2
            
    sentiment_score = max(-1.0, min(1.0, 0.5 - score_penalty))
    
    # Calculate GAD7/PHQ9 scale score (0 to 27)
    calculated_score = int((1.0 - sentiment_score) * 10)
    calculated_score = max(0, min(27, calculated_score))
    
    if calculated_score >= 15:
        risk = "severe"
    elif calculated_score >= 10:
        risk = "moderate"
    elif calculated_score >= 5:
        risk = "mild"
    else:
        risk = "minimal"
        
    screening = MentalHealthScreening(
        id=str(uuid.uuid4()),
        patient_id=user.id,
        screening_type="phq9",
        score=calculated_score,
        risk_level=risk,
        created_at=datetime.now(UTC),
    )
    db.add(screening)
    db.commit()
    
    return MentalHealthScreeningResponse(
        score=calculated_score,
        risk_level=risk,
        sentiment_score=round(sentiment_score, 2)
    )


@router.post("/weather-health/allergen-sync")
def weather_allergen_sync(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.models.patient import PatientProfile
    from app.models.feature_modules import HealthTask
    
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.id).first()
    conditions = (profile.chronic_conditions or "").lower() if profile else ""
    
    has_respiratory = "asthma" in conditions or "allergy" in conditions or "allergies" in conditions or "bronchitis" in conditions
    
    tasks_created = []
    
    # Simulate a high AQI weather sync event
    simulated_aqi = 165
    simulated_pollen = "High"
    
    if has_respiratory:
        # 1. Trigger high AQI task
        aqi_task = HealthTask(
            id=str(uuid.uuid4()),
            patient_id=user.id,
            task_type="allergen_sync",
            title=f"[AQI Alert] High AQI ({simulated_aqi}): Stay indoors and keep rescue inhaler ready.",
            description="Simulated real-time sync with weather station indicating poor air quality.",
            priority="high",
            due_date="",
            status="pending",
            created_at=datetime.now(UTC),
        )
        db.add(aqi_task)
        tasks_created.append(aqi_task.title)
        
        # 2. Trigger high pollen task
        pollen_task = HealthTask(
            id=str(uuid.uuid4()),
            patient_id=user.id,
            task_type="allergen_sync",
            title=f"[Pollen Spike] Pollen level is {simulated_pollen}: Take antihistamine as prescribed.",
            description="Automated sync with meteorological aero-allergen reports.",
            priority="medium",
            due_date="",
            status="pending",
            created_at=datetime.now(UTC),
        )
        db.add(pollen_task)
        tasks_created.append(pollen_task.title)
        
        db.commit()
        
    return {
        "aqi": simulated_aqi,
        "pollen": simulated_pollen,
        "vulnerable": has_respiratory,
        "alerts_triggered": len(tasks_created),
        "tasks_created": tasks_created
    }


from pydantic import BaseModel

class AmbulanceDispatchCreate(BaseModel):
    symptoms: str
    location_text: str
    hospital_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None

@router.post("/ambulance/dispatch")
def dispatch_ambulance(
    payload: AmbulanceDispatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.ambulance_service import AmbulanceDispatchService
    from app.models.feature_modules import EmergencyDispatchRequest
    
    if user.role != "patient":
        raise HTTPException(403, "Only patients can request ambulance dispatches")
        
    dispatch_rec = EmergencyDispatchRequest(
        id=str(uuid.uuid4()),
        patient_id=user.id,
        actor_id=user.id,
        hospital_id=payload.hospital_id,
        symptoms=payload.symptoms,
        severity=10,
        location_text=payload.location_text,
        latitude=payload.latitude,
        longitude=payload.longitude,
        status="requested",
        provider_reference="",
        safety_label="urgent_escalation",
        created_at=datetime.now(UTC),
    )
    db.add(dispatch_rec)
    db.commit()
    
    return {
        "request_id": dispatch_rec.id,
        "booking_reference": "",
        "status": "requested",
        "eta": "Pending hospital dispatch approval",
        "symptoms": payload.symptoms,
        "location": payload.location_text,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    }

@router.get("/medication-reminders")
def list_reminders(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    target_id = patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=target_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    
    reminders = db.query(MedicationReminder).filter(MedicationReminder.patient_id == target_id).all()
    return [
        {
            "id": r.id,
            "patient_id": r.patient_id,
            "medicine_name": r.medicine_name,
            "dosage": r.dosage,
            "schedule": r.schedule,
            "active": r.active,
            "created_at": "",
        }
        for r in reminders
    ]
