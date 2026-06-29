from pydantic import BaseModel, Field


class SendOtpRequest(BaseModel):
    target: str
    channel: str = Field(pattern="^(email|sms|whatsapp)$")
    purpose: str = "verify"


class VerifyOtpRequest(BaseModel):
    target: str
    code: str
    purpose: str = "verify"


class PrescriptionCreate(BaseModel):
    patient_id: str
    diagnosis: str
    medications: str
    dosage: str = ""
    duration: str = ""
    instructions: str = ""
    follow_up_date: str = ""
    pmjay_covered: bool = False


class AppointmentCreate(BaseModel):
    patient_id: str | None = None
    doctor_id: str | None = None
    hospital_id: str = ""
    department_id: str = ""
    slot_id: str = ""
    appointment_type: str
    consultation_mode: str = Field(default="in_person", pattern="^(in_person|video|phone)$")
    date: str
    time_slot: str
    urgency: str = "routine"
    notes: str = ""
    reason: str = ""


class HospitalCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    registration_number: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    pincode: str = ""
    phone: str = ""
    email: str = ""
    emergency_phone: str = ""
    ambulance_count: int = Field(default=0, ge=0)
    ambulance_types: str = ""
    beds_total: int = Field(default=0, ge=0)
    rooms_total: int = Field(default=0, ge=0)
    icu_beds_total: int = Field(default=0, ge=0)
    ac_rooms_total: int = Field(default=0, ge=0)


class HospitalResourceUpdate(BaseModel):
    ambulance_count: int = Field(default=0, ge=0)
    ambulance_types: str = ""
    beds_total: int = Field(default=0, ge=0)
    rooms_total: int = Field(default=0, ge=0)
    icu_beds_total: int = Field(default=0, ge=0)
    ac_rooms_total: int = Field(default=0, ge=0)


class HospitalResourceBookingCreate(BaseModel):
    hospital_id: str
    booking_type: str = Field(default="room", pattern="^(bed|room|icu|ac_room)$")
    resource_type: str = "general_bed"
    reason: str = ""


class HospitalResourceBookingUpdate(BaseModel):
    status: str = Field(pattern="^(requested|approved|admitted|discharged|rejected|cancelled)$")
    admin_notes: str = ""


class HospitalDepartmentCreate(BaseModel):
    hospital_id: str
    name: str = Field(min_length=2, max_length=160)
    speciality: str = ""
    description: str = ""


class HospitalDoctorCreate(BaseModel):
    hospital_id: str
    department_id: str
    doctor_id: str
    speciality: str = ""
    consultation_fee: float = Field(default=0, ge=0)


class ConsultationSlotCreate(BaseModel):
    hospital_id: str = ""
    department_id: str = ""
    doctor_id: str = ""
    date: str
    start_time: str
    end_time: str
    timezone: str = "Asia/Kolkata"
    slot_duration_minutes: int = Field(default=0, ge=0, le=480)
    consultation_mode: str = Field(default="in_person", pattern="^(in_person|video|phone)$")
    capacity: int = Field(default=1, ge=1, le=100)
    consultation_fee: float = 0.0
    accept_insurance: bool = True


class ConsultationBookingCreate(BaseModel):
    slot_id: str
    appointment_type: str = "consultation"
    reason: str = ""
    notes: str = ""
    urgency: str = "routine"
    payment_method: str = "cash"
    insurance_provider: str = ""
    insurance_policy_number: str = ""


class HospitalDoctorRegister(BaseModel):
    email: str
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = ""
    registration_number: str
    speciality: str = ""
    hospital_id: str
    department_id: str
    consultation_fee: float = 0.0


class AppointmentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(requested|confirmed|checked_in|completed|cancelled|no_show)$")
    cancellation_reason: str = ""


class PreConsultationIntakeSubmit(BaseModel):
    symptoms: str = Field(min_length=3, max_length=4000)
    reason_for_call: str = Field(default="", max_length=2000)


class PreConsultationFeedback(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=2000)


class PreConsultationRecord(BaseModel):
    id: str
    appointment_id: str
    patient_id: str
    doctor_id: str
    status: str
    symptoms: str
    reason_for_call: str
    consent_request_id: str | None
    consent_grant_id: str | None
    draft_summary: str
    doctor_feedback: str
    reward_score: int
    created_at: str
    updated_at: str
    patient_name: str = ""
    doctor_name: str = ""



class FamilyMemberCreate(BaseModel):
    full_name: str
    relation: str
    age: int = 0
    notes: str = ""


class MedicationReminderCreate(BaseModel):
    patient_id: str | None = None
    medicine_name: str
    dosage: str = ""
    schedule: str
    channel: str = "whatsapp"


class SymptomTrackRequest(BaseModel):
    patient_id: str | None = None
    symptoms: str
    severity: int = Field(ge=1, le=10)
    duration: str = ""


class LabResultCreate(BaseModel):
    patient_id: str | None = None
    test_name: str
    value: float
    unit: str = ""


class VaccinationCreate(BaseModel):
    patient_id: str | None = None
    vaccine_name: str
    dose_date: str
    next_due_date: str = ""


class PregnancyCreate(BaseModel):
    patient_id: str | None = None
    lmp_date: str
    notes: str = ""


class MentalHealthCreate(BaseModel):
    patient_id: str | None = None
    screening_type: str = Field(pattern="^(phq9|gad7)$")
    score: int = Field(ge=0, le=27)


class DrugInteractionRequest(BaseModel):
    medicines: list[str]


class SecondOpinionRequest(BaseModel):
    case_summary: str
    guideline_context: str = ""


class SoapRequest(BaseModel):
    visit_summary: str


class ReferralRequest(BaseModel):
    patient_id: str
    reason: str
    speciality: str


class FacilitySearchRequest(BaseModel):
    city: str
    state: str


class OutbreakAlertCreate(BaseModel):
    state: str
    city: str
    disease: str
    severity: str
    message: str


class YearlyHealthScanRequest(BaseModel):
    preferred_date: str = ""
    preferred_time_slot: str = "09:00-11:00"


class SymptomCareAgentRequest(BaseModel):
    patient_id: str | None = None
    symptoms: str = Field(min_length=3, max_length=2000)
    severity: int = Field(ge=1, le=10)
    duration: str = ""
    location_text: str = ""
    preferred_date: str = ""
    preferred_time_slot: str = ""
    acoustic_cough_type: str = "none"
    wheeze_acoustic_type: str = "none"


class CareAgentResponse(BaseModel):
    action: str
    safety_label: str
    reasoning: str
    result: dict


class PmjayEligibilityRequest(BaseModel):
    diagnosis: str
    patient_id: str | None = None


class PmjayEligibilityResponse(BaseModel):
    eligible: bool
    package_name: str
    package_code: str
    coverage_amount: float
    reasoning: str
    guidelines: list[str]


class FamilyMemberRegisterRequest(BaseModel):
    full_name: str
    relation: str
    age: int = 0
    notes: str = ""
    scope: str = "all"


class FamilyMemberResponse(BaseModel):
    id: str
    full_name: str
    relation: str
    age: int
    notes: str
    member_user_id: str | None
    active_consent: dict | None


class WhatsappAlertRequest(BaseModel):
    consent_grant_id: str


class WhatsappAlertRecord(BaseModel):
    id: str
    to_phone: str
    body: str
    consent_grant_id: str | None
    status: str
    created_at: str


class SimulatedSmsRecord(BaseModel):
    id: str
    phone: str
    body: str
    direction: str
    created_at: str


class SimulatedSmsReceiveRequest(BaseModel):
    phone: str
    body: str


class VoiceRxResponse(BaseModel):
    raw_text: str
    text: str
    acoustic_cough_type: str
    wheeze_acoustic_type: str


class SoapResponse(BaseModel):
    soap: dict
    diff_warnings: list[str]


class RedTeamRecord(BaseModel):
    id: str
    prompt: str
    safety_label: str
    reply: str
    is_safe: bool
    created_at: str


class SecondOpinionCreateRequest(BaseModel):
    specialty: str
    redacted_summary: str
    clinical_question: str


class SecondOpinionResponseRequest(BaseModel):
    request_id: str
    response_recommendation: str


class SecondOpinionRecord(BaseModel):
    id: str
    clinician_id: str
    specialty: str
    redacted_summary: str
    clinical_question: str
    status: str
    response_recommendation: str | None
    responder_id: str | None
    created_at: str


class OcrSpellcheckRequest(BaseModel):
    text: str


class OcrSpellcheckCorrection(BaseModel):
    original: str
    correction: str
    is_typo: bool
    suggestions: list[str]


class PillboxPingRequest(BaseModel):
    reminder_id: str
    status: str  # "taken", "missed"


class PillboxAlertRecord(BaseModel):
    id: str
    reminder_id: str
    patient_id: str
    status: str
    logged_at: str


class MentalHealthConversationScreeningRequest(BaseModel):
    conversation_text: str


class MentalHealthScreeningResponse(BaseModel):
    score: int
    risk_level: str
    sentiment_score: float


class ImagerySimilarityResponse(BaseModel):
    similar_cases: list[dict]


class CohortGeneratorRequest(BaseModel):
    chronic_condition: str
    min_age: int = 0
    max_age: int = 120


class CohortCandidate(BaseModel):
    id: str
    age: int
    gender: str
    chronic_conditions: str
    timeline_events_count: int


class VoiceAuditRequest(BaseModel):
    audio_text: str


class GuidelineDriftAlertRecord(BaseModel):
    id: str
    guideline_title: str
    published_source: str
    drift_reason: str
    action_taken: str
    created_at: str


class LedgerVerifyResponse(BaseModel):
    is_valid: bool
    error: str | None


class LedgerBlockRecord(BaseModel):
    id: str
    patient_id: str
    block_index: int
    timeline_hash: str
    previous_hash: str
    nonce: int
    hash: str
    created_at: str


class ConsultationRoomResponse(BaseModel):
    id: str
    appointment_id: str
    patient_id: str
    doctor_id: str
    status: str
    expires_at: str
    room_token: str


class ConsultationMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    message_type: str = Field(default="text", pattern="^(text|audio_note|system)$")
    client_message_id: str = ""


class ConsultationMessageRecord(BaseModel):
    id: str
    room_id: str
    appointment_id: str
    sender_id: str
    recipient_id: str
    message_type: str
    body: str
    created_at: str
    read_at: str | None


class ConsultationSignalCreate(BaseModel):
    signal_type: str = Field(pattern="^(offer|answer|ice|leave|heartbeat)$")
    payload: dict


class ConsultationSignalRecord(BaseModel):
    id: str
    room_id: str
    sender_id: str
    signal_type: str
    payload: dict
    created_at: str
