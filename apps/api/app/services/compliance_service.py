from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.compliance import CareTeamMembership, ConsentGrant
from app.models.user import User


class ComplianceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def can_access_patient(self, *, actor: User, patient_id: str, scope: str) -> bool:
        if actor.id == patient_id:
            return True

        now = datetime.now(UTC)
        # If actor is a patient, they can access another patient's data only via ConsentGrant
        if actor.role == "patient":
            consent = (
                self.db.query(ConsentGrant)
                .filter(
                    ConsentGrant.patient_id == patient_id,
                    ConsentGrant.grantee_id == actor.id,
                    ConsentGrant.scope.in_([scope, "all"]),
                    ConsentGrant.revoked_at.is_(None),
                    ConsentGrant.starts_at <= now,
                    or_(ConsentGrant.expires_at.is_(None), ConsentGrant.expires_at > now),
                )
                .first()
            )
            return consent is not None

        # For doctors/hospital admins, they need a valid consent grant, or doctors can have an appointment
        if actor.role not in {"doctor", "hospital_admin"}:
            return False

        consent = (
            self.db.query(ConsentGrant)
            .filter(
                ConsentGrant.patient_id == patient_id,
                ConsentGrant.grantee_id == actor.id,
                ConsentGrant.scope.in_([scope, "all"]),
                ConsentGrant.revoked_at.is_(None),
                ConsentGrant.starts_at <= now,
                or_(ConsentGrant.expires_at.is_(None), ConsentGrant.expires_at > now),
            )
            .first()
        )
        if consent is not None:
            return True

        membership = (
            self.db.query(CareTeamMembership)
            .filter(
                CareTeamMembership.patient_id == patient_id,
                CareTeamMembership.clinician_id == actor.id,
                CareTeamMembership.active.is_(True),
            )
            .first()
        )
        return membership is not None


    def break_glass_access(self, *, actor: User, patient_id: str, purpose: str, ip_address: str = "") -> bool:
        if actor.role not in {"doctor", "hospital_admin"}:
            return False
        
        # Log emergency break-glass access immediately to the audit system
        from app.services.audit_service import AuditService
        AuditService(self.db).record(
            actor=actor,
            patient_id=patient_id,
            action="compliance.break_glass",
            purpose=purpose,
            resource_type="patient_record",
            resource_id=patient_id,
            ip_address=ip_address,
            details={"message": "CRITICAL: Emergency break-glass access triggered by clinician", "clinician_role": actor.role}
        )
        return True
