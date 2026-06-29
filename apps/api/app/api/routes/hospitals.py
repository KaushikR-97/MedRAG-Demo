import uuid
import traceback
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role, hash_password, generate_12_digit_id
from app.db.session import get_db
from app.models.user import User
from app.models.feature_modules import Appointment, EmergencyDispatchRequest, Hospital, HospitalResourceBooking
from app.schemas.features import (
    AppointmentStatusUpdate,
    ConsultationBookingCreate,
    ConsultationSlotCreate,
    HospitalCreate,
    HospitalDepartmentCreate,
    HospitalDoctorCreate,
    HospitalDoctorRegister,
    HospitalResourceBookingCreate,
    HospitalResourceBookingUpdate,
    HospitalResourceUpdate,
)
from app.services.hospital_service import HospitalService
from app.services.compliance_service import ComplianceService
from app.services.preconsult_agent_service import PreConsultAgentService

router = APIRouter()


def _record(obj) -> dict:
    rec = {column.name: getattr(obj, column.name) for column in obj.__table__.columns}
    if isinstance(obj, Appointment):
        return _appointment_record(obj, rec)
    return rec


def _appointment_record(appointment: Appointment, rec: dict) -> dict:
    db = getattr(appointment, "_sa_instance_state", None)
    session = db.session if db is not None else None
    if session is not None:
        patient = session.get(User, appointment.patient_id) if appointment.patient_id else None
        doctor = session.get(User, appointment.doctor_id) if appointment.doctor_id else None
        rec["patient_name"] = patient.full_name if patient else appointment.patient_id
        rec["doctor_name"] = doctor.full_name if doctor else (appointment.doctor_id or "")
    else:
        rec["patient_name"] = appointment.patient_id
        rec["doctor_name"] = appointment.doctor_id or ""
    rec["confirmed_at"] = appointment.confirmed_at.isoformat() if appointment.confirmed_at else None
    rec["timezone"] = appointment.timezone or "Asia/Kolkata"
    start_at, end_at = _appointment_window(appointment.date, appointment.time_slot, rec["timezone"])
    rec["starts_at"] = start_at.isoformat() if start_at else ""
    rec["ends_at"] = end_at.isoformat() if end_at else ""
    rec["server_now"] = datetime.now(UTC).isoformat()
    return rec


def _appointment_window(date_text: str, time_slot: str, timezone_name: str) -> tuple[datetime | None, datetime | None]:
    try:
        start_text, end_text = time_slot.split("-", 1)
        slot_tz = ZoneInfo(timezone_name or "Asia/Kolkata")
        start_clock = time.fromisoformat(start_text.strip())
        end_clock = time.fromisoformat(end_text.strip())
        return (
            datetime.fromisoformat(f"{date_text}T{start_clock.isoformat()}").replace(tzinfo=slot_tz),
            datetime.fromisoformat(f"{date_text}T{end_clock.isoformat()}").replace(tzinfo=slot_tz),
        )
    except (ValueError, KeyError):
        return None, None


@router.post("")
def create_hospital(
    payload: HospitalCreate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        hospital = HospitalService(db).create_hospital(admin=admin, payload=payload.model_dump())
        return _record(hospital)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error creating hospital: {str(exc)}\n{traceback.format_exc()}") from exc



@router.get("")
def list_hospitals(
    city: str = Query(default=""),
    speciality: str = Query(default=""),
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        return [
            _record(item)
            for item in HospitalService(db).list_hospitals(city=city, speciality=speciality)
        ]
    except Exception as exc:
        raise HTTPException(400, f"Error listing hospitals: {str(exc)}\n{traceback.format_exc()}") from exc


@router.patch("/{hospital_id}/resources")
def update_hospital_resources(
    hospital_id: str,
    payload: HospitalResourceUpdate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        hospital = HospitalService(db)._assert_hospital_admin(admin=admin, hospital_id=hospital_id)
        for key, value in payload.model_dump().items():
            setattr(hospital, key, value)
        db.commit()
        db.refresh(hospital)
        return _record(hospital)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{hospital_id}/resources")
def post_hospital_resources(
    hospital_id: str,
    payload: HospitalResourceUpdate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    return update_hospital_resources(hospital_id=hospital_id, payload=payload, admin=admin, db=db)


@router.post("/resource-bookings")
def request_hospital_resource(
    payload: HospitalResourceBookingCreate,
    patient: User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        hospital = db.get(Hospital, payload.hospital_id)
        if hospital is None or not hospital.active:
            raise HTTPException(404, "Hospital not found")
        booking = HospitalResourceBooking(
            id=str(uuid.uuid4()),
            patient_id=patient.id,
            hospital_id=payload.hospital_id,
            booking_type=payload.booking_type,
            resource_type=payload.resource_type,
            reason=payload.reason,
            status="requested",
            created_at=datetime.now(UTC),
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        rec = _record(booking)
        rec["hospital_name"] = hospital.name
        return rec
    except HTTPException:
        raise
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error requesting hospital resource: {str(exc)}\n{traceback.format_exc()}") from exc


@router.get("/resource-bookings")
def list_hospital_resource_bookings(
    status: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(HospitalResourceBooking)
    if user.role == "patient":
        query = query.filter(HospitalResourceBooking.patient_id == user.id)
    elif user.role == "hospital_admin":
        hospital_ids = [h.id for h in db.query(Hospital).filter(Hospital.admin_user_id == user.id).all()]
        query = query.filter(HospitalResourceBooking.hospital_id.in_(hospital_ids or [""]))
    else:
        raise HTTPException(403, "Unsupported role")
    if status:
        query = query.filter(HospitalResourceBooking.status == status)
    rows = query.order_by(HospitalResourceBooking.created_at.desc()).limit(100).all()
    result = []
    for row in rows:
        hospital = db.get(Hospital, row.hospital_id)
        patient = db.get(User, row.patient_id)
        rec = _record(row)
        rec["hospital_name"] = hospital.name if hospital else ""
        rec["patient_name"] = patient.full_name if patient else row.patient_id
        rec["created_at"] = row.created_at.isoformat() if row.created_at else ""
        rec["approved_at"] = row.approved_at.isoformat() if row.approved_at else None
        rec["discharged_at"] = row.discharged_at.isoformat() if row.discharged_at else None
        result.append(rec)
    return result


@router.patch("/resource-bookings/{booking_id}")
def update_hospital_resource_booking(
    booking_id: str,
    payload: HospitalResourceBookingUpdate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    booking = db.get(HospitalResourceBooking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    hospital = db.get(Hospital, booking.hospital_id)
    if hospital is None or hospital.admin_user_id != admin.id:
        raise HTTPException(403, "Only the selected hospital admin can update this booking")
    booking.status = payload.status
    booking.admin_notes = payload.admin_notes
    if payload.status in {"approved", "admitted"} and booking.approved_at is None:
        booking.approved_at = datetime.now(UTC)
    if payload.status == "discharged":
        booking.discharged_at = datetime.now(UTC)
    db.commit()
    db.refresh(booking)
    rec = _record(booking)
    rec["hospital_name"] = hospital.name
    return rec


@router.post("/resource-bookings/{booking_id}/status")
def post_hospital_resource_booking_status(
    booking_id: str,
    payload: HospitalResourceBookingUpdate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    return update_hospital_resource_booking(booking_id=booking_id, payload=payload, admin=admin, db=db)


@router.post("/departments")
def create_department(
    payload: HospitalDepartmentCreate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        department = HospitalService(db).create_department(admin=admin, payload=payload.model_dump())
        return _record(department)
    except (LookupError, PermissionError) as exc:
        raise HTTPException(403 if isinstance(exc, PermissionError) else 404, str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error creating department: {str(exc)}\n{traceback.format_exc()}") from exc


@router.post("/doctors")
def assign_doctor(
    payload: HospitalDoctorCreate,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        record = HospitalService(db).assign_doctor(admin=admin, payload=payload.model_dump())
        return _record(record)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error assigning doctor: {str(exc)}\n{traceback.format_exc()}") from exc


@router.post("/slots")
def create_consultation_slot(
    payload: ConsultationSlotCreate,
    admin: User = Depends(require_role("hospital_admin", "doctor")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        slot = HospitalService(db).create_slot(admin=admin, payload=payload.model_dump())
        return _record(slot)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error processing slot release: {str(exc)}\n{traceback.format_exc()}") from exc


@router.get("/slots")
def list_consultation_slots(
    hospital_id: str = Query(default=""),
    doctor_id: str = Query(default=""),
    speciality: str = Query(default=""),
    date: str = Query(default=""),
    city: str = Query(default=""),
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        slots = HospitalService(db).list_slots(
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            speciality=speciality,
            date=date,
            city=city,
        )
        records = []
        from app.models.user import User
        for slot in slots:
            rec = _record(slot)
            doc = db.query(User).filter(User.id == slot.doctor_id).first()
            if doc:
                rec["doctor_name"] = doc.full_name
                rec["doctor_speciality"] = doc.speciality or "General Physician"
                rec["doctor_registration_number"] = doc.registration_number or "N/A"
            else:
                rec["doctor_name"] = "Unknown Doctor"
                rec["doctor_speciality"] = "General Physician"
                rec["doctor_registration_number"] = "N/A"
            records.append(rec)
        return records
    except Exception as exc:
        raise HTTPException(400, f"Error listing slots: {str(exc)}\n{traceback.format_exc()}") from exc


@router.post("/consultations/book")
def book_consultation(
    payload: ConsultationBookingCreate,
    patient: User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        appointment = HospitalService(db).book_consultation(
            patient=patient,
            slot_id=payload.slot_id,
            appointment_type=payload.appointment_type,
            reason=payload.reason,
            notes=payload.notes,
            urgency=payload.urgency,
            payment_method=payload.payment_method,
            insurance_provider=payload.insurance_provider,
            insurance_policy_number=payload.insurance_policy_number,
        )
        return _record(appointment)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error booking consultation: {str(exc)}\n{traceback.format_exc()}") from exc



@router.patch("/appointments/{appointment_id}")
def update_appointment_status(
    appointment_id: str,
    payload: AppointmentStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        appointment = HospitalService(db).update_appointment_status(
            actor=user,
            appointment_id=appointment_id,
            status=payload.status,
            cancellation_reason=payload.cancellation_reason,
        )
        if appointment.status == "confirmed" and appointment.doctor_id:
            try:
                PreConsultAgentService(db).ensure_for_confirmed_appointment(appointment=appointment, doctor=user)
            except Exception:
                db.rollback()
        return _record(appointment)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error updating appointment status: {str(exc)}\n{traceback.format_exc()}") from exc


@router.post("/appointments/{appointment_id}/status")
def post_appointment_status(
    appointment_id: str,
    payload: AppointmentStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return update_appointment_status(appointment_id=appointment_id, payload=payload, user=user, db=db)


@router.get("/appointments")
def list_my_appointments(
    patient_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        service = HospitalService(db)
        if user.role == "patient":
            target_patient_id = patient_id or user.id
            if not ComplianceService(db).can_access_patient(actor=user, patient_id=target_patient_id, scope="profile.read"):
                raise HTTPException(403, "Missing patient consent or care-team access")
            return [_record(item) for item in service.list_patient_appointments(patient_id=target_patient_id)]
        if user.role == "doctor":
            return [_record(item) for item in service.list_doctor_appointments(doctor_id=user.id)]
        return []
    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:
        raise HTTPException(400, f"Error listing appointments: {str(exc)}\n{traceback.format_exc()}") from exc


@router.post("/create-doctor")
def create_doctor_profile(
    payload: HospitalDoctorRegister,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(400, "Email already registered")
        HospitalService(db)._assert_hospital_admin(admin=admin, hospital_id=payload.hospital_id)
        doctor = User(
            id=generate_12_digit_id(db, User),
            email=str(payload.email),
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role="doctor",
            phone=payload.phone,
            registration_number=payload.registration_number,
            speciality=payload.speciality,
            city=db.get(Hospital, payload.hospital_id).city if db.get(Hospital, payload.hospital_id) else "",
        )
        db.add(doctor)
        db.flush()
        record = HospitalService(db).assign_doctor(
            admin=admin,
            payload={
                "hospital_id": payload.hospital_id,
                "department_id": payload.department_id,
                "doctor_id": doctor.id,
                "consultation_fee": payload.consultation_fee,
            },
        )
        return {
            "doctor_user_id": doctor.id,
            "doctor_assignment_id": record.id,
            "full_name": doctor.full_name,
            "email": doctor.email,
            "speciality": record.speciality or "",
        }
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(400, f"Error creating doctor: {str(exc)}\n{traceback.format_exc()}") from exc


@router.get("/doctors")
def list_doctors_by_city(
    city: str = Query(default=""),
    speciality: str = Query(default=""),
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        from app.models.feature_modules import HospitalDoctor
        query = db.query(User).filter(User.role == "doctor")
        if city:
            query = query.filter(User.city.ilike(f"%{city}%"))
        if speciality:
            query = query.filter(User.speciality.ilike(f"%{speciality}%"))
        
        doctors_list = []
        for doc in query.all():
            assignment = db.query(HospitalDoctor).filter(HospitalDoctor.doctor_id == doc.id, HospitalDoctor.active.is_(True)).first()
            fee = assignment.consultation_fee if assignment else 0.0
            doctors_list.append({
                "id": doc.id,
                "full_name": doc.full_name,
                "email": doc.email,
                "phone": doc.phone,
                "speciality": doc.speciality or "",
                "city": doc.city or "",
                "consultation_fee": fee
            })
        return doctors_list
    except Exception as exc:
        raise HTTPException(400, f"Error listing doctors by city: {str(exc)}\n{traceback.format_exc()}") from exc


@router.get("/ambulance/requests")
def list_ambulance_requests(
    status: str = Query(default="requested"),
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> list[dict]:
    hospital_ids = [
        item.id
        for item in db.query(Hospital).filter(Hospital.admin_user_id == admin.id, Hospital.active.is_(True)).all()
    ]
    query = db.query(EmergencyDispatchRequest)
    if hospital_ids:
        query = query.filter(EmergencyDispatchRequest.hospital_id.in_(hospital_ids))
    else:
        return []
    if status:
        query = query.filter(EmergencyDispatchRequest.status == status)
    rows = query.order_by(EmergencyDispatchRequest.created_at.desc()).limit(100).all()
    result = []
    for row in rows:
        patient = db.get(User, row.patient_id)
        hospital = db.get(Hospital, row.hospital_id) if row.hospital_id else None
        rec = _record(row)
        rec["patient_name"] = patient.full_name if patient else row.patient_id
        rec["hospital_name"] = hospital.name if hospital else "Unassigned hospital"
        rec["created_at"] = row.created_at.isoformat() if row.created_at else ""
        result.append(rec)
    return result


@router.post("/ambulance/requests/{request_id}/dispatch")
def approve_and_dispatch_ambulance(
    request_id: str,
    admin: User = Depends(require_role("hospital_admin")),
    db: Session = Depends(get_db),
) -> dict:
    request_record = db.get(EmergencyDispatchRequest, request_id)
    if request_record is None:
        raise HTTPException(404, "Ambulance request not found")
    hospital = db.get(Hospital, request_record.hospital_id) if request_record.hospital_id else None
    if hospital is None or hospital.admin_user_id != admin.id:
        raise HTTPException(403, "Only the selected hospital admin can dispatch this ambulance")
    if request_record.status != "requested":
        raise HTTPException(409, f"Ambulance request is already {request_record.status}")

    from app.services.ambulance_service import AmbulanceDispatchService
    reference = AmbulanceDispatchService().request_dispatch(
        patient_id=request_record.patient_id,
        symptoms=request_record.symptoms,
        location_text=request_record.location_text,
    )
    request_record.actor_id = admin.id
    request_record.status = "dispatched"
    request_record.provider_reference = reference
    db.commit()
    return {
        "id": request_record.id,
        "status": request_record.status,
        "provider_reference": reference,
        "eta": "8 minutes",
    }
