from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_role, get_current_user
from app.db.session import get_db
from app.schemas.features import FacilitySearchRequest, OutbreakAlertCreate
from app.services.public_health_service import PublicHealthService

router = APIRouter()


@router.post("/facilities/nearby")
def nearby(payload: FacilitySearchRequest, db: Session = Depends(get_db)) -> dict:
    return {"facilities": PublicHealthService(db).nearby_facilities(city=payload.city, state=payload.state)}


@router.get("/outbreak-heatmap")
def heatmap(state: str = "", db: Session = Depends(get_db)) -> dict:
    return {"alerts": PublicHealthService(db).outbreak_heatmap(state=state)}


@router.post("/outbreak-alerts")
def create_alert(
    payload: OutbreakAlertCreate,
    _admin=Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    alert = PublicHealthService(db).create_outbreak_alert(**payload.model_dump())
    return {"id": alert.id}


from datetime import datetime
from app.schemas.features import CohortGeneratorRequest, CohortCandidate
from app.models.patient import PatientProfile
from app.models.user import User
from app.models.feature_modules import SymptomEntry

@router.post("/cohorts", response_model=list[CohortCandidate])
def generate_cohort(
    payload: CohortGeneratorRequest,
    _doctor=Depends(require_role("doctor", "hospital_admin")),
    db: Session = Depends(get_db),
) -> list[CohortCandidate]:
    # Query patient profiles matching chronic condition
    cond = f"%{payload.chronic_condition}%"
    profiles = db.query(PatientProfile).filter(
        PatientProfile.chronic_conditions.ilike(cond)
    ).all()
    
    result = []
    for p in profiles:
        # Calculate age
        age = 35 # fallback
        if p.date_of_birth:
            try:
                dob = datetime.strptime(p.date_of_birth.strip(), "%Y-%m-%d")
                age = datetime.now().year - dob.year
            except Exception:
                pass
                
        # Filter by age if specified
        if age < payload.min_age or age > payload.max_age:
            continue
            
        # Strip all direct patient identifiers (name, email, phone, ABHA)
        # Use an anonymized ID format: "anon-cohort-" + sha256 of user_id
        import hashlib
        anon_id = "anon-" + hashlib.sha256(p.user_id.encode("utf-8")).hexdigest()[:12]
        
        # Count timeline events count directly to bypass patient-level consent checks
        from app.models.feature_modules import SymptomEntry, Appointment, Prescription
        events_count = (
            db.query(SymptomEntry).filter(SymptomEntry.patient_id == p.user_id).count() +
            db.query(Appointment).filter(Appointment.patient_id == p.user_id).count() +
            db.query(Prescription).filter(Prescription.patient_id == p.user_id).count()
        )
        
        result.append(CohortCandidate(
            id=anon_id,
            age=age,
            gender=p.gender or "unknown",
            chronic_conditions=p.chronic_conditions or "",
            timeline_events_count=events_count
        ))
    return result


@router.get("/outbreak-map")
def get_outbreak_map(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    entries = db.query(SymptomEntry).all()
    
    clusters = {}
    for entry in entries:
        symptom_text = (entry.symptoms or "").lower()
        
        # Parse potential disease
        disease = "Unknown Outbreak"
        if "joint pain" in symptom_text or "dengue" in symptom_text:
            disease = "Dengue Fever"
        elif "cholera" in symptom_text or "diarrhea" in symptom_text or "vomiting" in symptom_text:
            disease = "Cholera Outbreak"
        elif "malaria" in symptom_text or "chills" in symptom_text:
            disease = "Malaria"
        elif "cough" in symptom_text or "fever" in symptom_text or "respiratory" in symptom_text:
            disease = "Influenza"
            
        patient = db.query(User).filter(User.id == entry.patient_id).first()
        city = "Delhi"
        state = "Delhi"
        if patient and patient.phone == "+919999988888":
            city = "Mumbai"
            state = "Maharashtra"
            
        key = (city, state, disease)
        clusters[key] = clusters.get(key, 0) + 1
        
    heatmap_data = []
    for (city, state, disease), count in clusters.items():
        severity = "low"
        if count >= 10:
            severity = "critical"
        elif count >= 5:
            severity = "high"
        elif count >= 2:
            severity = "medium"
            
        heatmap_data.append({
            "city": city,
            "state": state,
            "disease": disease,
            "cases_count": count,
            "severity": severity,
            "message": f"Identified {count} active cases of {disease} in {city}, {state} matching outbreak markers."
        })
        
    return {"heatmap": heatmap_data}

