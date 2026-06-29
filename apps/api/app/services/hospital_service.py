import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.feature_modules import (
    Appointment,
    ConsultationSlot,
    Hospital,
    HospitalDepartment,
    HospitalDoctor,
)
from app.models.user import User


class HospitalService:
    LOCAL_TZ = ZoneInfo("Asia/Kolkata")

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_hospital(self, *, admin: User, payload: dict) -> Hospital:
        hospital = Hospital(id=str(uuid.uuid4()), admin_user_id=admin.id, **payload)
        self.db.add(hospital)
        self.db.commit()
        self.db.refresh(hospital)
        return hospital

    def create_department(self, *, admin: User, payload: dict) -> HospitalDepartment:
        self._assert_hospital_admin(admin=admin, hospital_id=payload["hospital_id"])
        department = HospitalDepartment(id=str(uuid.uuid4()), **payload)
        self.db.add(department)
        self.db.commit()
        self.db.refresh(department)
        return department

    def assign_doctor(self, *, admin: User, payload: dict) -> HospitalDoctor:
        self._assert_hospital_admin(admin=admin, hospital_id=payload["hospital_id"])
        try:
            doctor = self.db.get(User, payload["doctor_id"])
        except Exception as exc:
            raise LookupError(f"Invalid doctor ID format: {str(exc)}") from exc
        if doctor is None or doctor.role != "doctor":
            raise LookupError("Doctor user not found")
        try:
            department = self.db.get(HospitalDepartment, payload["department_id"])
        except Exception as exc:
            raise LookupError(f"Invalid department ID format: {str(exc)}") from exc
        if department is None or department.hospital_id != payload["hospital_id"]:
            raise LookupError("Department not found for hospital")
        try:
            record = HospitalDoctor(id=str(uuid.uuid4()), **payload)
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return record
        except Exception as exc:
            self.db.rollback()
            raise exc

    def create_slot(self, *, admin: User, payload: dict) -> ConsultationSlot:
        duration_minutes = int(payload.pop("slot_duration_minutes", 0) or 0)
        if admin.role == "doctor":
            payload["doctor_id"] = admin.id
            if not payload.get("hospital_id") or payload.get("hospital_id") == "personal":
                payload["hospital_id"] = None
            if not payload.get("department_id") or payload.get("department_id") == "personal":
                payload["department_id"] = None
        else:
            self._assert_hospital_admin(admin=admin, hospital_id=payload["hospital_id"])
            try:
                assignment = (
                    self.db.query(HospitalDoctor)
                    .filter(
                        HospitalDoctor.hospital_id == payload["hospital_id"],
                        HospitalDoctor.department_id == payload["department_id"],
                        HospitalDoctor.doctor_id == payload["doctor_id"],
                        HospitalDoctor.active.is_(True),
                    )
                    .first()
                )
            except Exception as exc:
                raise LookupError(f"Invalid hospital, department or doctor ID: {str(exc)}") from exc
            if assignment is None:
                raise LookupError("Doctor is not assigned to this hospital department")
            if not payload.get("consultation_fee"):
                payload["consultation_fee"] = assignment.consultation_fee or 0.0
        
        try:
            slot_payloads = self._expand_slot_window(payload=payload, duration_minutes=duration_minutes)
            created_slots: list[ConsultationSlot] = []
            for slot_payload in slot_payloads:
                if self._is_past_slot(slot_payload["date"], slot_payload["start_time"], slot_payload.get("timezone") or "Asia/Kolkata"):
                    raise ValueError("Cannot release consultation slots for a time that has already passed")
                overlapping_slot = (
                    self.db.query(ConsultationSlot)
                    .filter(
                        ConsultationSlot.doctor_id == slot_payload["doctor_id"],
                        ConsultationSlot.date == slot_payload["date"],
                        ConsultationSlot.status == "open",
                        ConsultationSlot.start_time < slot_payload["end_time"],
                        ConsultationSlot.end_time > slot_payload["start_time"],
                    )
                    .first()
                )
                if overlapping_slot is not None:
                    raise ValueError("Doctor already has an overlapping availability window")
                slot = ConsultationSlot(id=str(uuid.uuid4()), **slot_payload)
                self.db.add(slot)
                created_slots.append(slot)
            self.db.commit()
            self.db.refresh(created_slots[0])
            return created_slots[0]
        except Exception as exc:
            self.db.rollback()
            raise exc

    @staticmethod
    def _expand_slot_window(*, payload: dict, duration_minutes: int) -> list[dict]:
        if duration_minutes <= 0:
            return [payload]
        try:
            start_clock = time.fromisoformat(payload["start_time"])
            end_clock = time.fromisoformat(payload["end_time"])
        except ValueError as exc:
            raise ValueError("Start time and end time must use HH:MM format") from exc

        cursor = datetime.combine(datetime(2000, 1, 1), start_clock)
        window_end = datetime.combine(datetime(2000, 1, 1), end_clock)
        if window_end <= cursor:
            raise ValueError("End time must be after start time")

        slots = []
        while cursor + timedelta(minutes=duration_minutes) <= window_end:
            next_end = cursor + timedelta(minutes=duration_minutes)
            slot_payload = dict(payload)
            slot_payload["start_time"] = cursor.time().strftime("%H:%M")
            slot_payload["end_time"] = next_end.time().strftime("%H:%M")
            slots.append(slot_payload)
            cursor = next_end
        if not slots:
            raise ValueError("Availability window is shorter than the consultation duration")
        return slots

    def list_hospitals(self, *, city: str = "", speciality: str = "") -> list[Hospital]:
        query = self.db.query(Hospital).filter(Hospital.active.is_(True))
        if city:
            query = query.filter(Hospital.city.ilike(f"%{city}%"))
        if speciality:
            query = query.join(HospitalDepartment, HospitalDepartment.hospital_id == Hospital.id).filter(
                HospitalDepartment.speciality.ilike(f"%{speciality}%"),
                HospitalDepartment.active.is_(True),
            )
        return query.order_by(Hospital.name.asc()).limit(50).all()

    def list_slots(
        self,
        *,
        hospital_id: str = "",
        doctor_id: str = "",
        speciality: str = "",
        date: str = "",
        city: str = "",
    ) -> list[ConsultationSlot]:
        query = self.db.query(ConsultationSlot).filter(ConsultationSlot.status == "open")
        if hospital_id:
            query = query.filter(ConsultationSlot.hospital_id == hospital_id)
        if doctor_id:
            query = query.filter(ConsultationSlot.doctor_id == doctor_id)
        if date:
            query = query.filter(ConsultationSlot.date == date)
        if city or speciality:
            query = query.outerjoin(
                Hospital,
                Hospital.id == ConsultationSlot.hospital_id,
            ).outerjoin(
                User,
                User.id == ConsultationSlot.doctor_id,
            ).outerjoin(
                HospitalDepartment,
                HospitalDepartment.id == ConsultationSlot.department_id,
            )
        if city:
            query = query.filter(or_(Hospital.city.ilike(f"%{city}%"), User.city.ilike(f"%{city}%")))
        if speciality:
            query = query.filter(
                or_(
                    HospitalDepartment.speciality.ilike(f"%{speciality}%"),
                    User.speciality.ilike(f"%{speciality}%"),
                    ConsultationSlot.department_id.is_(None),
                )
            )
        today = datetime.now(self.LOCAL_TZ).date().isoformat()
        current_time = datetime.now(self.LOCAL_TZ).strftime("%H:%M")
        query = query.filter(
            or_(
                ConsultationSlot.date > today,
                and_(ConsultationSlot.date == today, ConsultationSlot.start_time > current_time),
            ),
            ConsultationSlot.booked_count < ConsultationSlot.capacity,
        )
        return query.order_by(ConsultationSlot.date.asc(), ConsultationSlot.start_time.asc()).limit(100).all()

    def book_consultation(
        self,
        *,
        patient: User,
        slot_id: str,
        appointment_type: str,
        reason: str,
        notes: str,
        urgency: str,
        payment_method: str = "cash",
        insurance_provider: str = "",
        insurance_policy_number: str = "",
    ) -> Appointment:
        slot = self.db.get(ConsultationSlot, slot_id)
        if slot is None or slot.status != "open":
            raise LookupError("Consultation slot not found")
        if self._is_past_slot(slot.date, slot.start_time, slot.timezone or "Asia/Kolkata"):
            raise ValueError("Consultation slot has already passed")
        if slot.booked_count >= slot.capacity:
            raise ValueError("Consultation slot is full")

        slot.booked_count += 1
        if slot.booked_count >= slot.capacity:
            slot.status = "booked"
        appointment = Appointment(
            id=str(uuid.uuid4()),
            patient_id=patient.id,
            doctor_id=slot.doctor_id,
            hospital_id=slot.hospital_id,
            department_id=slot.department_id,
            slot_id=slot.id,
            appointment_type=appointment_type,
            consultation_mode=slot.consultation_mode,
            date=slot.date,
            time_slot=f"{slot.start_time}-{slot.end_time}",
            timezone=slot.timezone or "Asia/Kolkata",
            status="requested",
            urgency=urgency,
            notes=notes,
            reason=reason,
            payment_method=payment_method,
            insurance_provider=insurance_provider,
            insurance_policy_number=insurance_policy_number,
            consultation_fee=slot.consultation_fee or 0.0,
            booking_reference=self._booking_reference(),
        )
        self.db.add(appointment)
        self.db.commit()
        self.db.refresh(appointment)
        return appointment

    def update_appointment_status(
        self,
        *,
        actor: User,
        appointment_id: str,
        status: str,
        cancellation_reason: str = "",
    ) -> Appointment:
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None:
            raise LookupError("Appointment not found")
        if actor.role == "patient" and appointment.patient_id != actor.id:
            raise PermissionError("Cannot update another patient's appointment")
        if actor.role in {"doctor", "hospital_admin"} and actor.role != "hospital_admin":
            if appointment.doctor_id != actor.id:
                raise PermissionError("Doctor can only update own appointments")

        if status == "cancelled" and appointment.slot_id:
            slot = self.db.get(ConsultationSlot, appointment.slot_id)
            if slot is not None and appointment.status != "cancelled":
                slot.booked_count = max(0, slot.booked_count - 1)
                if slot.status == "booked":
                    slot.status = "open"
        if actor.role == "patient" and status not in {"cancelled"}:
            raise PermissionError("Patients can only cancel their own appointments")
        if actor.role == "doctor" and status == "confirmed" and appointment.doctor_id != actor.id:
            raise PermissionError("Doctor can only confirm own appointments")
        if status == "confirmed" and appointment.status != "confirmed":
            appointment.confirmed_at = datetime.now(UTC)
        appointment.status = status
        appointment.cancellation_reason = cancellation_reason
        self.db.commit()
        self.db.refresh(appointment)
        return appointment

    def list_patient_appointments(self, *, patient_id: str) -> list[Appointment]:
        return (
            self.db.query(Appointment)
            .filter(Appointment.patient_id == patient_id)
            .order_by(Appointment.date.desc(), Appointment.time_slot.desc())
            .limit(100)
            .all()
        )

    def list_doctor_appointments(self, *, doctor_id: str) -> list[Appointment]:
        return (
            self.db.query(Appointment)
            .filter(Appointment.doctor_id == doctor_id)
            .order_by(Appointment.date.desc(), Appointment.time_slot.desc())
            .limit(100)
            .all()
        )

    def _assert_hospital_admin(self, *, admin: User, hospital_id: str) -> Hospital:
        try:
            hospital = self.db.get(Hospital, hospital_id)
        except Exception as exc:
            raise LookupError(f"Invalid hospital ID format or database error: {str(exc)}") from exc
        if hospital is None:
            raise LookupError("Hospital not found")
        if admin.role != "hospital_admin" or hospital.admin_user_id != admin.id:
            raise PermissionError("Only this hospital's admin can manage it")
        return hospital

    @staticmethod
    def _booking_reference() -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        return f"CONS-{stamp}-{uuid.uuid4().hex[:8].upper()}"

    def _is_past_slot(self, date_text: str, start_time: str, timezone_name: str = "Asia/Kolkata") -> bool:
        try:
            slot_tz = ZoneInfo(timezone_name or "Asia/Kolkata")
            slot_start = datetime.fromisoformat(f"{date_text}T{start_time}:00").replace(tzinfo=slot_tz)
        except (ValueError, KeyError):
            return True
        return slot_start <= datetime.now(slot_tz)
