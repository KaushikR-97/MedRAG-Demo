import tempfile
import uuid
import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user, hash_password
from app.db.session import get_db
from app.models.feature_modules import (
    Appointment,
    CaregiverLink,
    HealthTask,
    LabResult,
    MedicationReminder,
    Prescription,
    SymptomEntry,
)
from app.models.user import User
from app.services.clinical_tools_service import ClinicalToolsService
from app.services.voice_service import VoiceService
from app.schemas.features import (
    PmjayEligibilityRequest,
    PmjayEligibilityResponse,
    VoiceRxResponse,
    OcrSpellcheckRequest,
    OcrSpellcheckCorrection,
)

router = APIRouter()



@router.get("/timeline")
def health_timeline(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    target_id = patient_id or user.id
    from app.services.compliance_service import ComplianceService
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=target_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")

    events: list[dict] = []
    for rx in db.query(Prescription).filter(Prescription.patient_id == target_id).all():
        events.append({"type": "prescription", "id": rx.id, "date": rx.created_at.isoformat(), "title": rx.diagnosis})
    for lab in db.query(LabResult).filter(LabResult.patient_id == target_id).all():
        events.append({"type": "lab", "id": lab.id, "date": lab.created_at.isoformat(), "title": lab.test_name})
    for symptom in db.query(SymptomEntry).filter(SymptomEntry.patient_id == target_id).all():
        events.append({"type": "symptom", "id": symptom.id, "date": symptom.created_at.isoformat(), "title": symptom.symptoms[:80]})
    return {"events": sorted(events, key=lambda item: item["date"], reverse=True)}


@router.get("/pre-consult-summary")
def preconsult_summary(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    target_id = patient_id or user.id
    from app.services.compliance_service import ComplianceService
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=target_id, scope="profile.read"):
        raise HTTPException(403, "Missing patient consent or care-team access")

    latest_symptoms = db.query(SymptomEntry).filter(SymptomEntry.patient_id == target_id).order_by(SymptomEntry.created_at.desc()).limit(5).all()
    meds = db.query(MedicationReminder).filter(MedicationReminder.patient_id == target_id, MedicationReminder.active.is_(True)).all()
    tasks = db.query(HealthTask).filter(HealthTask.patient_id == target_id, HealthTask.status == "pending").all()
    return {
        "summary": {
            "recent_symptoms": [s.symptoms for s in latest_symptoms],
            "active_medications": [m.medicine_name for m in meds],
            "pending_tasks": [t.title for t in tasks],
            "red_flags": [s.triage_result for s in latest_symptoms if s.triage_result.startswith("urgent")],
        }
    }


@router.post("/pmjay-eligibility", response_model=PmjayEligibilityResponse)
def check_pmjay_eligibility(
    payload: PmjayEligibilityRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PmjayEligibilityResponse:
    patient_id = payload.patient_id or user.id
    from app.services.audit_service import AuditService
    AuditService(db).record(
        actor=user,
        patient_id=patient_id,
        action="pmjay.check_eligibility",
        purpose="financial_aid_matching",
        resource_type="pmjay_eligibility",
        resource_id="none",
        details={"diagnosis": payload.diagnosis},
    )
    from app.services.pmjay_service import PmjayMatcherService
    res = PmjayMatcherService(db).check_eligibility(diagnosis=payload.diagnosis, patient_id=patient_id)
    return PmjayEligibilityResponse(**res)


@router.get("/diet-recommendations")
def diet_recommendations(condition: str = "", user: User = Depends(get_current_user)) -> dict:
    text = condition.lower()
    if "diabetes" in text:
        recs = ["Prefer high-fiber meals", "Limit sugary drinks", "Discuss carbohydrate targets with clinician"]
    elif "hypertension" in text:
        recs = ["Reduce salt intake", "Prefer fruits/vegetables", "Monitor BP regularly"]
    else:
        recs = ["Prefer balanced meals", "Hydrate well", "Avoid tobacco and excess alcohol"]
    return {"patient_id": user.id, "recommendations": recs, "disclaimer": "Diet advice should be individualized by a clinician/dietitian."}


@router.post("/pmjay/claim-assist")
def pmjay_claim_assist(
    patient_id: str,
    diagnosis: str,
    hospital_state: str,
    _user: User = Depends(get_current_user),
) -> dict:
    return {
        "eligibility_checklist": [
            "Verify beneficiary eligibility in PM-JAY portal",
            "Map diagnosis to package code",
            "Attach prescription, admission note, ID, and discharge summary",
            f"Route to state health agency workflow for {hospital_state}",
        ],
        "diagnosis": diagnosis,
        "patient_id": patient_id,
    }


@router.post("/caregiver-link")
def create_caregiver_link(
    scope: str = "summary",
    hours: int = 72,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    raw_token = str(uuid.uuid4())
    link = CaregiverLink(
        id=str(uuid.uuid4()),
        patient_id=user.id,
        token_hash=hash_password(raw_token),
        scope=scope,
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )
    db.add(link)
    db.commit()
    return {"link_id": link.id, "token": raw_token, "expires_at": link.expires_at.isoformat()}


@router.post("/voice/transcribe", response_model=VoiceRxResponse)
async def transcribe_voice(
    language: str = "en",
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
) -> VoiceRxResponse:
    content = await file.read()
    suffix = "." + (file.filename or "audio.wav").split(".")[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    res = VoiceService().transcribe(tmp_path, language=language)
    return VoiceRxResponse(**res)


@router.get("/weather-health")
def weather_health(city: str = "", state: str = "", _user: User = Depends(get_current_user)) -> dict:
    return {
        "location": {"city": city, "state": state},
        "advice": [
            "Hydrate during heat waves",
            "Use masks/avoid outdoor exertion during poor air quality",
            "Follow local public health advisories during outbreaks",
        ],
        "source": "OpenWeather integration boundary",
    }


@router.post("/second-opinion/patient")
def patient_second_opinion(case_summary: str, user: User = Depends(get_current_user)) -> dict:
    return {
        "patient_id": user.id,
        "result": "A clinician should review this case. RAG-backed second opinion workflow can compare against guidelines.",
        "case_summary": case_summary,
    }


MASTER_MEDS = [
    "Metformin", "Aspirin", "Amoxicillin", "Atorvastatin", "Paracetamol", 
    "Ibuprofen", "Clopidogrel", "Warfarin", "Metoprolol", "Losartan"
]

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]


@router.post("/ocr/spellcheck", response_model=list[OcrSpellcheckCorrection])
def ocr_spellcheck(
    payload: OcrSpellcheckRequest,
    _user: User = Depends(get_current_user),
) -> list[OcrSpellcheckCorrection]:
    # Split text into potential drug words (by commas, spaces, or lines)
    words = [w.strip(",. ") for w in re.split(r"[\s,\n]+", payload.text) if w.strip(",. ")]
    result = []
    
    for word in words:
        if not word:
            continue
        
        # Check case-insensitive exact match
        exact_match = next((m for m in MASTER_MEDS if m.lower() == word.lower()), None)
        if exact_match:
            result.append(OcrSpellcheckCorrection(
                original=word,
                correction=exact_match,
                is_typo=False,
                suggestions=[]
            ))
            continue
            
        # Look for close spelling corrections
        suggestions = []
        best_match = None
        best_dist = 999
        for med in MASTER_MEDS:
            dist = levenshtein_distance(word.lower(), med.lower())
            if dist <= 3:
                suggestions.append(med)
                if dist < best_dist:
                    best_dist = dist
                    best_match = med
                    
        if best_match:
            result.append(OcrSpellcheckCorrection(
                original=word,
                correction=best_match,
                is_typo=True,
                suggestions=suggestions
            ))
        else:
            result.append(OcrSpellcheckCorrection(
                original=word,
                correction=word,
                is_typo=False,
                suggestions=[]
            ))
            
    return result
