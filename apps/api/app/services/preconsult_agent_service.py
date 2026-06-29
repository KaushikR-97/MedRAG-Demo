import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.compliance import ConsentGrant, PatientAccessRequest
from app.models.document import MedicalDocument
from app.models.feature_modules import Appointment, ConsultationMessage, PreConsultationIntake
from app.models.patient import PatientProfile
from app.models.user import User
from app.rag.retriever import RetrievedChunk
from app.services.compliance_service import ComplianceService
from app.services.consultation_service import ConsultationCrypto
from app.services.generation_service import ClinicalGenerationService


class PreConsultAgentService:
    """Consent-aware pre-consultation intake and doctor draft agent."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_for_confirmed_appointment(self, *, appointment: Appointment, doctor: User) -> PreConsultationIntake:
        if appointment.status != "confirmed":
            raise ValueError("Pre-consult agent starts after doctor confirmation")
        if not appointment.doctor_id:
            raise ValueError("Confirmed appointment has no doctor")
        intake = self._get_or_create_intake(appointment)
        intake.consent_request_id = self._ensure_patient_access_request(
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment.id,
        )
        self._sync_consent_grant(intake)
        intake.status = self._next_status(intake)
        self.db.commit()
        self.db.refresh(intake)
        return intake

    def get_for_appointment(self, *, appointment_id: str, actor: User) -> PreConsultationIntake:
        appointment = self._authorized_appointment(appointment_id=appointment_id, actor=actor)
        intake = self._get_or_create_intake(appointment)
        self._sync_consent_grant(intake)
        intake.status = self._next_status(intake)
        self.db.commit()
        self.db.refresh(intake)
        return intake

    def submit_patient_intake(
        self,
        *,
        appointment_id: str,
        patient: User,
        symptoms: str,
        reason_for_call: str,
    ) -> PreConsultationIntake:
        appointment = self._authorized_appointment(appointment_id=appointment_id, actor=patient)
        if appointment.patient_id != patient.id:
            raise PermissionError("Only the patient can submit pre-consult symptoms")
        if appointment.status != "confirmed":
            raise PermissionError("Doctor must confirm the appointment before pre-consult intake")
        intake = self._get_or_create_intake(appointment)
        intake.symptoms = symptoms.strip()
        intake.reason_for_call = reason_for_call.strip()
        self._sync_consent_grant(intake)
        intake.status = self._next_status(intake)
        intake.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(intake)
        return intake

    def generate_doctor_draft(self, *, appointment_id: str, doctor: User) -> PreConsultationIntake:
        appointment = self._authorized_appointment(appointment_id=appointment_id, actor=doctor)
        if appointment.doctor_id != doctor.id and doctor.role != "hospital_admin":
            raise PermissionError("Only the assigned doctor can prepare the pre-consult draft")
        intake = self._get_or_create_intake(appointment)
        self._sync_consent_grant(intake)
        if not intake.symptoms.strip() and not intake.reason_for_call.strip() and not appointment.reason.strip():
            intake.status = "awaiting_patient_intake"
            self.db.commit()
            self.db.refresh(intake)
            return intake
        if not self._has_active_consent(doctor_id=appointment.doctor_id, patient_id=appointment.patient_id):
            intake.status = "awaiting_patient_consent"
            self.db.commit()
            self.db.refresh(intake)
            return intake

        sources = self._build_sources(appointment=appointment, intake=intake)
        question = (
            "Prepare a doctor-only pre-consultation draft for the upcoming appointment. "
            "Use the patient's submitted symptoms/reason, appointment reason, secure chat symptoms, profile, and verified records. "
            "Return concise sections: Possible diagnoses/differentials, relevant medical history, suggested assessment questions, "
            "doctor-only treatment plan options with safety checks, red flags/escalation, and records used. "
            "This draft is not a patient instruction and must be reviewed by the doctor."
        )
        intake.draft_summary = ClinicalGenerationService().generate(
            question=question,
            user_role="doctor",
            conversation_history=[],
            sources=sources,
            disclaimer=None,
            policy_instruction=(
                "Doctor-facing pre-consult draft only. Include practical diagnosis and treatment considerations "
                "when clinically relevant, but explicitly require doctor verification before use."
            ),
            policy_mode="preconsult_doctor_agent",
        )
        intake.status = "draft_ready"
        intake.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(intake)
        return intake

    def record_doctor_feedback(
        self,
        *,
        appointment_id: str,
        doctor: User,
        approved: bool,
        feedback: str,
    ) -> PreConsultationIntake:
        appointment = self._authorized_appointment(appointment_id=appointment_id, actor=doctor)
        if appointment.doctor_id != doctor.id and doctor.role != "hospital_admin":
            raise PermissionError("Only the assigned doctor can score the pre-consult draft")
        intake = self._get_or_create_intake(appointment)
        intake.status = "doctor_approved" if approved else "doctor_rejected"
        intake.reward_score = 1 if approved else -1
        intake.doctor_feedback = feedback.strip()
        intake.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(intake)
        return intake

    def record(self, intake: PreConsultationIntake) -> dict:
        patient = self.db.get(User, intake.patient_id)
        doctor = self.db.get(User, intake.doctor_id)
        return {
            "id": intake.id,
            "appointment_id": intake.appointment_id,
            "patient_id": intake.patient_id,
            "doctor_id": intake.doctor_id,
            "status": intake.status,
            "symptoms": intake.symptoms,
            "reason_for_call": intake.reason_for_call,
            "consent_request_id": intake.consent_request_id,
            "consent_grant_id": intake.consent_grant_id,
            "draft_summary": intake.draft_summary,
            "doctor_feedback": intake.doctor_feedback,
            "reward_score": intake.reward_score,
            "created_at": intake.created_at.isoformat(),
            "updated_at": intake.updated_at.isoformat(),
            "patient_name": patient.full_name if patient else "",
            "doctor_name": doctor.full_name if doctor else "",
        }

    def _authorized_appointment(self, *, appointment_id: str, actor: User) -> Appointment:
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None:
            raise LookupError("Appointment not found")
        if actor.role == "patient" and appointment.patient_id != actor.id:
            raise PermissionError("Only the patient can access this pre-consult intake")
        if actor.role == "doctor" and appointment.doctor_id != actor.id:
            raise PermissionError("Only the assigned doctor can access this pre-consult intake")
        if actor.role not in {"patient", "doctor", "hospital_admin"}:
            raise PermissionError("Unsupported role")
        return appointment

    def _get_or_create_intake(self, appointment: Appointment) -> PreConsultationIntake:
        intake = (
            self.db.query(PreConsultationIntake)
            .filter(PreConsultationIntake.appointment_id == appointment.id)
            .first()
        )
        if intake is not None:
            return intake
        intake = PreConsultationIntake(
            id=str(uuid.uuid4()),
            appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id or "",
            status="awaiting_patient_intake",
        )
        self.db.add(intake)
        self.db.flush()
        return intake

    def _ensure_patient_access_request(self, *, patient_id: str, doctor_id: str, appointment_id: str) -> str:
        purpose = f"Pre-consultation review for appointment {appointment_id}"
        existing = (
            self.db.query(PatientAccessRequest)
            .filter(
                PatientAccessRequest.patient_id == patient_id,
                PatientAccessRequest.requester_id == doctor_id,
                PatientAccessRequest.scope == "all",
                PatientAccessRequest.status == "pending",
            )
            .order_by(PatientAccessRequest.created_at.desc())
            .first()
        )
        if existing is not None:
            return existing.id
        approved = (
            self.db.query(PatientAccessRequest)
            .filter(
                PatientAccessRequest.patient_id == patient_id,
                PatientAccessRequest.requester_id == doctor_id,
                PatientAccessRequest.scope == "all",
                PatientAccessRequest.status == "approved",
            )
            .order_by(PatientAccessRequest.decided_at.desc())
            .first()
        )
        if approved is not None:
            return approved.id
        request = PatientAccessRequest(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            requester_id=doctor_id,
            scope="all",
            purpose=purpose[:160],
            status="pending",
            created_at=datetime.now(UTC),
        )
        self.db.add(request)
        self.db.flush()
        return request.id

    def _sync_consent_grant(self, intake: PreConsultationIntake) -> None:
        request = self.db.get(PatientAccessRequest, intake.consent_request_id) if intake.consent_request_id else None
        if request and request.status == "approved":
            intake.consent_grant_id = request.consent_grant_id
        if intake.consent_grant_id:
            return
        grant = (
            self.db.query(ConsentGrant)
            .filter(
                ConsentGrant.patient_id == intake.patient_id,
                ConsentGrant.grantee_id == intake.doctor_id,
                ConsentGrant.scope == "all",
                ConsentGrant.revoked_at.is_(None),
                ConsentGrant.starts_at <= datetime.now(UTC),
                or_(ConsentGrant.expires_at.is_(None), ConsentGrant.expires_at > datetime.now(UTC)),
            )
            .order_by(ConsentGrant.starts_at.desc())
            .first()
        )
        if grant is not None:
            intake.consent_grant_id = grant.id

    def _has_active_consent(self, *, doctor_id: str, patient_id: str) -> bool:
        doctor = self.db.get(User, doctor_id)
        if doctor is None:
            return False
        return (
            ComplianceService(self.db).can_access_patient(actor=doctor, patient_id=patient_id, scope="clinical.ask")
            and ComplianceService(self.db).can_access_patient(actor=doctor, patient_id=patient_id, scope="documents.read")
        )

    @staticmethod
    def _next_status(intake: PreConsultationIntake) -> str:
        if intake.status in {"doctor_approved", "doctor_rejected"}:
            return intake.status
        if intake.draft_summary.strip():
            return "draft_ready"
        if not intake.symptoms.strip() and not intake.reason_for_call.strip():
            return "awaiting_patient_intake"
        if not intake.consent_grant_id:
            return "awaiting_patient_consent"
        return "ready_to_generate"

    def _build_sources(self, *, appointment: Appointment, intake: PreConsultationIntake) -> list[RetrievedChunk]:
        sources = [
            RetrievedChunk(
                id=f"appointment-{appointment.id}",
                title="Confirmed appointment details",
                score=1.0,
                text=(
                    f"Date: {appointment.date}; Time: {appointment.time_slot}; Mode: {appointment.consultation_mode}; "
                    f"Appointment reason: {appointment.reason or 'Not provided'}; Notes: {appointment.notes or 'None'}; "
                    f"Urgency: {appointment.urgency}."
                ),
            ),
            RetrievedChunk(
                id=f"preconsult-intake-{intake.id}",
                title="Patient pre-consult symptoms and reason",
                score=1.0,
                text=f"Symptoms: {intake.symptoms or 'Not submitted'}\nReason for call: {intake.reason_for_call or 'Not submitted'}",
            ),
        ]
        chat_text = self._chat_context(appointment_id=appointment.id)
        if chat_text:
            sources.append(
                RetrievedChunk(
                    id=f"consult-chat-{appointment.id}",
                    title="Secure consultation chat symptoms/context",
                    score=0.95,
                    text=chat_text,
                )
            )
        profile = self.db.query(PatientProfile).filter(PatientProfile.user_id == appointment.patient_id).first()
        patient = self.db.get(User, appointment.patient_id)
        if profile or patient:
            sources.append(
                RetrievedChunk(
                    id="patient-onboarding-profile",
                    title="Patient profile",
                    score=0.9,
                    text=(
                        f"Name: {patient.full_name if patient else 'Unknown'}; "
                        f"Age: {patient.age if patient and patient.age is not None else 'Not specified'}; "
                        f"City: {patient.city if patient else 'Not specified'}; "
                        f"Gender: {profile.gender if profile else 'Not specified'}; "
                        f"Blood group: {profile.blood_group if profile else 'Not specified'}; "
                        f"Allergies: {profile.allergies if profile else 'None declared'}; "
                        f"Chronic conditions: {profile.chronic_conditions if profile else 'None declared'}; "
                        f"Current medications: {profile.current_medications if profile else 'None declared'}."
                    ),
                )
            )
        docs = (
            self.db.query(MedicalDocument)
            .filter(
                MedicalDocument.patient_id == appointment.patient_id,
                MedicalDocument.verified_by_patient.is_(True),
            )
            .order_by(MedicalDocument.created_at.desc())
            .limit(8)
            .all()
        )
        for doc in docs:
            text = (doc.verified_text or doc.ocr_text or doc.clinician_verified_findings or "").strip()
            if not text:
                continue
            sources.append(
                RetrievedChunk(
                    id=f"patient-document-{doc.id}",
                    title=f"{doc.document_type}: {doc.original_filename}",
                    score=0.85,
                    text=text[:1800],
                )
            )
        return sources

    def _chat_context(self, *, appointment_id: str) -> str:
        rows = (
            self.db.query(ConsultationMessage)
            .filter(ConsultationMessage.appointment_id == appointment_id)
            .order_by(ConsultationMessage.created_at.asc())
            .limit(40)
            .all()
        )
        crypto = ConsultationCrypto()
        lines: list[str] = []
        for row in rows:
            try:
                payload = crypto.decrypt_json(row.ciphertext)
            except ValueError:
                continue
            sender = self.db.get(User, row.sender_id)
            label = sender.role if sender else "participant"
            body = str(payload.get("body", "")).strip()
            if body:
                lines.append(f"{label}: {body}")
        return "\n".join(lines)
