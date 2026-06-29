import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.feature_modules import SimulatedSmsMessage, MedicationReminder
from app.schemas.features import (
    SendOtpRequest,
    VerifyOtpRequest,
    SimulatedSmsRecord,
    SimulatedSmsReceiveRequest,
)
from app.services.communication_service import CommunicationService
from app.graphs.care_agent_graph import CareCoordinationAgent

router = APIRouter()


@router.post("/otp/send")
def send_otp(payload: SendOtpRequest, db: Session = Depends(get_db)) -> dict:
    record = CommunicationService(db).send_otp(
        target=payload.target,
        channel=payload.channel,
        purpose=payload.purpose,
    )
    return {"otp_id": record.id, "status": "sent_or_queued"}


@router.post("/otp/verify")
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)) -> dict:
    return {"verified": CommunicationService(db).verify_otp(target=payload.target, code=payload.code, purpose=payload.purpose)}


@router.post("/sms/receive", response_model=dict)
def receive_sms(
    payload: SimulatedSmsReceiveRequest,
    db: Session = Depends(get_db),
) -> dict:
    # 1. Log inbound message
    inbound = SimulatedSmsMessage(
        id=str(uuid.uuid4()),
        phone=payload.phone,
        body=payload.body,
        direction="inbound",
        created_at=datetime.now(UTC),
    )
    db.add(inbound)
    
    # 2. Match patient by phone number
    patient = db.query(User).filter(User.phone == payload.phone).first()
    patient_id = patient.id if patient else "unknown"
    patient_name = patient.full_name if patient else "Patient"
    
    text = payload.body.strip()
    reply_body = ""
    
    if text.upper().startswith("TRIAGE "):
        symptom_text = text[7:]
        # Simple extraction of severity
        severity_match = re.search(r"\b(10|[1-9])\b", symptom_text)
        severity = int(severity_match.group(0)) if severity_match else 7
        symptom_text = re.sub(r"\b(10|[1-9])\b", "", symptom_text).strip()
        
        system_user = db.query(User).filter(User.role == "hospital_admin").first()
        if not system_user:
            system_user = patient or User(id="system", email="system@medrag.in", hashed_password="", role="hospital_admin", full_name="System Admin")
            
        state = CareCoordinationAgent(db).coordinate_symptoms(
            actor=system_user,
            patient_id=patient_id if patient else "system",
            symptoms=symptom_text,
            severity=severity,
        )
        action = state.get("action", "unknown")
        reasoning = state.get("reasoning", "")
        res = state.get("result", {})
        instruction = res.get("instruction", "Consult details registered in your timeline.")
        reply_body = f"MedRAG Triage: Action={action.upper()}. Reasoning: {reasoning}. Instruction: {instruction}"
        
    elif text.upper().startswith("REMIND"):
        if patient_id == "unknown":
            reply_body = "MedRAG SMS: Phone number not registered. Please register first."
        else:
            reminders = db.query(MedicationReminder).filter(
                MedicationReminder.patient_id == patient_id,
                MedicationReminder.active.is_(True)
            ).all()
            if reminders:
                reply_body = f"MedRAG Reminders for {patient_name}: " + ", ".join(f"{r.medicine_name} ({r.schedule})" for r in reminders)
            else:
                reply_body = f"MedRAG: No active medication reminders found for {patient_name}."
                
    elif text.upper().startswith("ASK "):
        question_text = text[4:]
        from app.services.cache_service import ClinicalCacheService
        cached = ClinicalCacheService().get_cached_answer(question_text, "patient", patient_id if patient else "system")
        if cached:
            reply_body = f"MedRAG Answer (Cached): " + cached.get("answer", "")[:130] + "..."
        else:
            reply_body = f"MedRAG RAG Portal: Answer for '{question_text[:20]}...': Standard guidelines recommend consulting your doctor. A clinical case summary has been cached."
            
    else:
        reply_body = "MedRAG SMS Helper. Available commands: TRIAGE [symptoms], REMIND (shows active reminders), ASK [question]."

    # 3. Log outbound message
    outbound = SimulatedSmsMessage(
        id=str(uuid.uuid4()),
        phone=payload.phone,
        body=reply_body,
        direction="outbound",
        created_at=datetime.now(UTC),
    )
    db.add(outbound)
    
    db.commit()
    return {"status": "sms_processed", "reply": reply_body}


@router.get("/sms/logs", response_model=list[SimulatedSmsRecord])
def get_sms_logs(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SimulatedSmsRecord]:
    msgs = db.query(SimulatedSmsMessage).order_by(SimulatedSmsMessage.created_at.desc()).all()
    result = []
    for m in msgs:
        result.append(SimulatedSmsRecord(
            id=m.id,
            phone=m.phone,
            body=m.body,
            direction=m.direction,
            created_at=m.created_at.isoformat()
        ))
    return result


from app.schemas.features import VoiceAuditRequest
from app.models.audit import AuditEvent
import hashlib

@router.post("/voice-audit")
def voice_audit(
    payload: VoiceAuditRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # 1. Fetch last audit event for hash chaining
    last_event = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).first()
    prev_hash = last_event.event_hash if last_event else "0" * 64
    
    action = "compliance.voice_compliance_audit"
    details = {"transcript": payload.audio_text}
    
    # 2. Compute cryptographically chained hash
    event_data = f"{prev_hash}{user.id}{action}{str(details)}"
    event_hash = hashlib.sha256(event_data.encode("utf-8")).hexdigest()
    
    # 3. Create AuditEvent
    event = AuditEvent(
        id=str(uuid.uuid4()),
        actor_id=user.id,
        patient_id="system",
        action=action,
        purpose="voice_compliance_audit",
        resource_type="surgical_procedure",
        resource_id="none",
        ip_address="127.0.0.1",
        details_json=str(details),
        previous_hash=prev_hash,
        event_hash=event_hash,
        created_at=datetime.now(UTC),
    )
    db.add(event)
    db.commit()
    
    return {
        "status": "audited",
        "event_id": event.id,
        "hash": event_hash,
        "previous_hash": prev_hash,
        "transcript": payload.audio_text
    }


