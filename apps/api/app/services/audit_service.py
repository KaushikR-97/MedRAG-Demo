import hashlib
import json
import uuid

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.user import User


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        actor: User,
        patient_id: str,
        action: str,
        purpose: str,
        resource_type: str = "",
        resource_id: str = "",
        ip_address: str = "",
        details: dict | None = None,
    ) -> AuditEvent:
        previous = self.db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).first()
        previous_hash = previous.event_hash if previous else ""
        canonical = json.dumps(
            {
                "actor_id": actor.id,
                "patient_id": patient_id,
                "action": action,
                "purpose": purpose,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "ip_address": ip_address,
                "details": details or {},
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event = AuditEvent(
            id=str(uuid.uuid4()),
            actor_id=actor.id,
            patient_id=patient_id,
            action=action,
            purpose=purpose,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            details_json=json.dumps(details or {}, separators=(",", ":")),
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        self.db.add(event)
        self.db.commit()
        return event
