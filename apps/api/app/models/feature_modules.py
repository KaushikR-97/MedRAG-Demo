from datetime import UTC, datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    target: Mapped[str] = mapped_column(String(320), index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(80), index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    diagnosis: Mapped[str] = mapped_column(Text)
    medications: Mapped[str] = mapped_column(Text)
    dosage: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    follow_up_date: Mapped[str] = mapped_column(String(32), default="")
    pmjay_covered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    hospital_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    department_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    slot_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    appointment_type: Mapped[str] = mapped_column(String(120))
    consultation_mode: Mapped[str] = mapped_column(String(32), default="in_person", index=True)
    date: Mapped[str] = mapped_column(String(32))
    time_slot: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    urgency: Mapped[str] = mapped_column(String(32), default="routine", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    booking_reference: Mapped[str] = mapped_column(String(80), default="", index=True)
    cancellation_reason: Mapped[str] = mapped_column(Text, default="")
    payment_method: Mapped[str] = mapped_column(String(32), default="cash", index=True)
    insurance_provider: Mapped[str] = mapped_column(String(120), default="", nullable=True)
    insurance_policy_number: Mapped[str] = mapped_column(String(120), default="", nullable=True)
    consultation_fee: Mapped[float] = mapped_column(Float, default=0.0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))



class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    registration_number: Mapped[str] = mapped_column(String(120), default="", index=True)
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(120), default="", index=True)
    state: Mapped[str] = mapped_column(String(120), default="", index=True)
    pincode: Mapped[str] = mapped_column(String(16), default="", index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    emergency_phone: Mapped[str] = mapped_column(String(40), default="")
    ambulance_count: Mapped[int] = mapped_column(Integer, default=0)
    ambulance_types: Mapped[str] = mapped_column(Text, default="")
    beds_total: Mapped[int] = mapped_column(Integer, default=0)
    rooms_total: Mapped[int] = mapped_column(Integer, default=0)
    icu_beds_total: Mapped[int] = mapped_column(Integer, default=0)
    ac_rooms_total: Mapped[int] = mapped_column(Integer, default=0)
    admin_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class HospitalDepartment(Base):
    __tablename__ = "hospital_departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    speciality: Mapped[str] = mapped_column(String(160), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class HospitalDoctor(Base):
    __tablename__ = "hospital_doctors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("hospital_departments.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    speciality: Mapped[str] = mapped_column(String(160), default="", index=True)
    consultation_fee: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ConsultationSlot(Base):
    __tablename__ = "consultation_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hospital_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None, index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[str] = mapped_column(String(32), index=True)
    start_time: Mapped[str] = mapped_column(String(16))
    end_time: Mapped[str] = mapped_column(String(16))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    consultation_mode: Mapped[str] = mapped_column(String(32), default="in_person", index=True)
    capacity: Mapped[int] = mapped_column(default=1)
    booked_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    consultation_fee: Mapped[float] = mapped_column(Float, default=0.0)
    accept_insurance: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))



class HealthTask(Base):
    __tablename__ = "health_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    due_date: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    relation: Mapped[str] = mapped_column(String(80))
    age: Mapped[int] = mapped_column(default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    member_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)


class SimulatedWhatsappMessage(Base):
    __tablename__ = "simulated_whatsapp_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    to_phone: Mapped[str] = mapped_column(String(40), index=True)
    body: Mapped[str] = mapped_column(Text)
    consent_grant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="sent", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class MedicationReminder(Base):
    __tablename__ = "medication_reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(160))
    dosage: Mapped[str] = mapped_column(String(120), default="")
    schedule: Mapped[str] = mapped_column(String(160))
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SymptomEntry(Base):
    __tablename__ = "symptom_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    symptoms: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(default=1)
    duration: Mapped[str] = mapped_column(String(120), default="")
    triage_result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    test_name: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40), default="")
    interpretation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class VaccinationRecord(Base):
    __tablename__ = "vaccination_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    vaccine_name: Mapped[str] = mapped_column(String(160))
    dose_date: Mapped[str] = mapped_column(String(32))
    next_due_date: Mapped[str] = mapped_column(String(32), default="")


class PregnancyRecord(Base):
    __tablename__ = "pregnancy_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    lmp_date: Mapped[str] = mapped_column(String(32))
    estimated_due_date: Mapped[str] = mapped_column(String(32), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class MentalHealthScreening(Base):
    __tablename__ = "mental_health_screenings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    screening_type: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[int]
    risk_level: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CaregiverLink(Base):
    __tablename__ = "caregiver_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    scope: Mapped[str] = mapped_column(String(120), default="summary")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiseaseOutbreakAlert(Base):
    __tablename__ = "disease_outbreak_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(120), index=True)
    city: Mapped[str] = mapped_column(String(120), index=True)
    disease: Mapped[str] = mapped_column(String(160), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PatientCalendarEvent(Base):
    __tablename__ = "patient_calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    source: Mapped[str] = mapped_column(String(80), default="agent")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AgentActionLog(Base):
    __tablename__ = "agent_action_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    tool_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EmergencyDispatchRequest(Base):
    __tablename__ = "emergency_dispatch_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    hospital_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    symptoms: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(default=10)
    location_text: Mapped[str] = mapped_column(Text, default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    provider_reference: Mapped[str] = mapped_column(String(120), default="")
    safety_label: Mapped[str] = mapped_column(String(80), default="urgent_escalation", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class HospitalResourceBooking(Base):
    __tablename__ = "hospital_resource_bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    booking_type: Mapped[str] = mapped_column(String(40), default="room", index=True)
    resource_type: Mapped[str] = mapped_column(String(80), default="general_bed", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    admin_notes: Mapped[str] = mapped_column(Text, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class SimulatedSmsMessage(Base):
    __tablename__ = "simulated_sms_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phone: Mapped[str] = mapped_column(String(40), index=True)
    body: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(10), index=True)  # "inbound" or "outbound"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class SecondOpinionRequest(Base):
    __tablename__ = "second_opinion_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    specialty: Mapped[str] = mapped_column(String(120), index=True)
    redacted_summary: Mapped[str] = mapped_column(Text)
    clinical_question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)  # "pending", "responded"
    response_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    responder_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class IotPillboxAlert(Base):
    __tablename__ = "iot_pillbox_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reminder_id: Mapped[str] = mapped_column(ForeignKey("medication_reminders.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)  # "taken", "missed"
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class GuidelineDriftAlert(Base):
    __tablename__ = "guideline_drift_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guideline_title: Mapped[str] = mapped_column(String(200))
    published_source: Mapped[str] = mapped_column(String(200))
    drift_reason: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(String(64), default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PhrLedgerBlock(Base):
    __tablename__ = "phr_ledger_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    block_index: Mapped[int] = mapped_column(Integer)
    timeline_hash: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[int] = mapped_column(Integer)
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ConsultationRoom(Base):
    __tablename__ = "consultation_rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsultationMessage(Base):
    __tablename__ = "consultation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("consultation_rooms.id"), index=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    message_type: Mapped[str] = mapped_column(String(32), default="text", index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    key_version: Mapped[str] = mapped_column(String(32), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsultationSignal(Base):
    __tablename__ = "consultation_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("consultation_rooms.id"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(32), index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PreConsultationIntake(Base):
    __tablename__ = "pre_consultation_intakes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="awaiting_patient_intake", index=True)
    symptoms: Mapped[str] = mapped_column(Text, default="")
    reason_for_call: Mapped[str] = mapped_column(Text, default="")
    consent_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    consent_grant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    draft_summary: Mapped[str] = mapped_column(Text, default="")
    doctor_feedback: Mapped[str] = mapped_column(Text, default="")
    reward_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
