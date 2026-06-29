import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from jose import jwt
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.feature_modules import (
    Appointment,
    ConsultationMessage,
    ConsultationRoom,
    ConsultationSignal,
)
from app.models.user import User


class ConsultationCrypto:
    """Authenticated encryption boundary for consultation payloads."""

    key_version = "v1"

    def __init__(self) -> None:
        key_material = settings.consultation_encryption_key.strip()
        if not key_material:
            if settings.environment.lower() == "production":
                raise ValueError("CONSULTATION_ENCRYPTION_KEY must be configured in production environments")
            # Cryptographically derive a separate, independent key from settings.jwt_secret to avoid single-key weakness
            import hmac
            import hashlib
            derived = hmac.new(
                settings.jwt_secret.encode("utf-8"),
                b"consultation-encryption-key-salt",
                hashlib.sha256
            ).digest()
            key = base64.urlsafe_b64encode(derived)
        elif key_material.startswith("fernet:"):
            key = key_material.removeprefix("fernet:").encode("utf-8")
        else:
            digest = hashlib.sha256(key_material.encode("utf-8")).digest()
            key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key)

    def encrypt_json(self, payload: dict[str, Any]) -> str:
        return self._fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8")

    def decrypt_json(self, ciphertext: str) -> dict[str, Any]:
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError("Encrypted consultation payload could not be verified") from exc
        return json.loads(plaintext.decode("utf-8"))


class ConsultationService:
    LOCAL_TZ = ZoneInfo("Asia/Kolkata")

    def __init__(self, db: Session, crypto: ConsultationCrypto | None = None) -> None:
        self.db = db
        self.crypto = crypto or ConsultationCrypto()

    def get_or_create_room(self, *, appointment_id: str, actor: User) -> ConsultationRoom:
        appointment = self._get_authorized_video_appointment(appointment_id=appointment_id, actor=actor)
        if not appointment.doctor_id:
            raise PermissionError("Consultation has no assigned doctor")

        room = (
            self.db.query(ConsultationRoom)
            .filter(ConsultationRoom.appointment_id == appointment.id)
            .first()
        )
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=settings.consultation_room_expire_minutes)
        if room is None:
            room = ConsultationRoom(
                id=str(uuid.uuid4()),
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                status="active",
                created_at=now,
                expires_at=expires_at,
            )
            self.db.add(room)
        else:
            room.status = "active"
            room.ended_at = None
            if room.expires_at < now:
                room.expires_at = expires_at
        self.db.commit()
        self.db.refresh(room)
        return room

    def end_room(self, *, appointment_id: str, actor: User) -> ConsultationRoom:
        room = self.get_room_for_appointment(appointment_id=appointment_id, actor=actor)
        room.status = "ended"
        room.ended_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(room)
        return room

    def get_room_for_appointment(self, *, appointment_id: str, actor: User) -> ConsultationRoom:
        appointment = self._get_authorized_video_appointment(appointment_id=appointment_id, actor=actor)
        room = (
            self.db.query(ConsultationRoom)
            .filter(ConsultationRoom.appointment_id == appointment.id)
            .first()
        )
        if room is None:
            return self.get_or_create_room(appointment_id=appointment_id, actor=actor)
        return room

    def get_or_create_chat_room(self, *, appointment_id: str, actor: User) -> ConsultationRoom:
        appointment = self._get_authorized_chat_appointment(appointment_id=appointment_id, actor=actor)
        if not appointment.doctor_id:
            raise PermissionError("Consultation has no assigned doctor")
        room = (
            self.db.query(ConsultationRoom)
            .filter(ConsultationRoom.appointment_id == appointment.id)
            .first()
        )
        now = datetime.now(UTC)
        expires_at = self._chat_expires_at(appointment)
        if room is None:
            room = ConsultationRoom(
                id=str(uuid.uuid4()),
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                status="active",
                created_at=now,
                expires_at=expires_at,
            )
            self.db.add(room)
        else:
            room.status = "active"
            room.expires_at = max(self._as_utc(room.expires_at), expires_at)
        self.db.commit()
        self.db.refresh(room)
        return room

    def issue_room_token(self, *, room: ConsultationRoom, actor: User) -> str:
        self._assert_room_participant(room=room, actor=actor)
        expires_at = min(
            room.expires_at,
            datetime.now(UTC) + timedelta(minutes=30),
        )
        payload = {
            "sub": actor.id,
            "room_id": room.id,
            "appointment_id": room.appointment_id,
            "role": actor.role,
            "scope": "consultation.room",
            "exp": expires_at,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def post_message(
        self,
        *,
        room_id: str,
        actor: User,
        body: str,
        message_type: str = "text",
        client_message_id: str = "",
    ) -> ConsultationMessage:
        room = self._get_authorized_room(room_id=room_id, actor=actor)
        if room.status != "active" or self._as_utc(room.expires_at) < datetime.now(UTC):
            raise PermissionError("Consultation room is not active")
        recipient_id = self._other_participant_id(room=room, actor=actor)
        ciphertext = self.crypto.encrypt_json(
            {
                "body": body,
                "message_type": message_type,
                "client_message_id": client_message_id,
            }
        )
        message = ConsultationMessage(
            id=str(uuid.uuid4()),
            room_id=room.id,
            appointment_id=room.appointment_id,
            sender_id=actor.id,
            recipient_id=recipient_id,
            message_type=message_type,
            ciphertext=ciphertext,
            key_version=self.crypto.key_version,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def list_messages(self, *, room_id: str, actor: User, since_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        room = self._get_authorized_room(room_id=room_id, actor=actor)
        query = (
            self.db.query(ConsultationMessage)
            .filter(ConsultationMessage.room_id == room.id)
            .order_by(ConsultationMessage.created_at.asc())
        )
        rows = query.limit(min(max(limit, 1), 200)).all()
        if since_id:
            try:
                start_index = next(index for index, row in enumerate(rows) if row.id == since_id) + 1
                rows = rows[start_index:]
            except StopIteration:
                pass
        return [self._message_record(row) for row in rows]

    def post_signal(
        self,
        *,
        room_id: str,
        actor: User,
        signal_type: str,
        payload: dict[str, Any],
    ) -> ConsultationSignal:
        room = self._get_authorized_room(room_id=room_id, actor=actor)
        if room.status != "active" or self._as_utc(room.expires_at) < datetime.now(UTC):
            raise PermissionError("Consultation room is not active")
        signal = ConsultationSignal(
            id=str(uuid.uuid4()),
            room_id=room.id,
            sender_id=actor.id,
            recipient_id=self._other_participant_id(room=room, actor=actor),
            signal_type=signal_type,
            ciphertext=self.crypto.encrypt_json({"payload": payload}),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        return signal

    def poll_signals(self, *, room_id: str, actor: User) -> list[dict[str, Any]]:
        room = self._get_authorized_room(room_id=room_id, actor=actor)
        now = datetime.now(UTC)
        rows = (
            self.db.query(ConsultationSignal)
            .filter(
                ConsultationSignal.room_id == room.id,
                ConsultationSignal.recipient_id == actor.id,
                ConsultationSignal.consumed_at.is_(None),
                ConsultationSignal.expires_at > now,
            )
            .order_by(ConsultationSignal.created_at.asc())
            .limit(100)
            .all()
        )
        records = []
        for row in rows:
            decrypted = self.crypto.decrypt_json(row.ciphertext)
            row.consumed_at = now
            records.append(
                {
                    "id": row.id,
                    "room_id": row.room_id,
                    "sender_id": row.sender_id,
                    "signal_type": row.signal_type,
                    "payload": decrypted.get("payload", {}),
                    "created_at": row.created_at.isoformat(),
                }
            )
        self.db.commit()
        return records

    def _message_record(self, message: ConsultationMessage) -> dict[str, Any]:
        decrypted = self.crypto.decrypt_json(message.ciphertext)
        return {
            "id": message.id,
            "room_id": message.room_id,
            "appointment_id": message.appointment_id,
            "sender_id": message.sender_id,
            "recipient_id": message.recipient_id,
            "message_type": message.message_type,
            "body": decrypted.get("body", ""),
            "created_at": message.created_at.isoformat(),
            "read_at": message.read_at.isoformat() if message.read_at else None,
        }

    def _get_authorized_video_appointment(self, *, appointment_id: str, actor: User) -> Appointment:
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None:
            raise LookupError("Appointment not found")
        if appointment.consultation_mode != "video":
            raise PermissionError("This appointment is not a video consultation")
        if appointment.status != "confirmed":
            raise PermissionError("Doctor must confirm the booking before the consultation room opens")
        if actor.id not in {appointment.patient_id, appointment.doctor_id} and actor.role != "hospital_admin":
            raise PermissionError("Only consultation participants can access this room")
        if appointment.status in {"cancelled", "no_show"}:
            raise PermissionError("Consultation is not joinable")
        if not self._is_appointment_time_window(appointment):
            raise PermissionError("Video consultation opens only during the booked slot window")
        return appointment

    def _get_authorized_chat_appointment(self, *, appointment_id: str, actor: User) -> Appointment:
        appointment = self.db.get(Appointment, appointment_id)
        if appointment is None:
            raise LookupError("Appointment not found")
        if appointment.status != "confirmed":
            raise PermissionError("Doctor must confirm the booking before secure chat opens")
        if actor.id not in {appointment.patient_id, appointment.doctor_id} and actor.role != "hospital_admin":
            raise PermissionError("Only consultation participants can access this chat")
        if appointment.status in {"cancelled", "no_show"}:
            raise PermissionError("Consultation chat is not available")
        if datetime.now(UTC) > self._chat_expires_at(appointment):
            raise PermissionError("Secure consultation chat is available for 7 days after booking confirmation")
        return appointment

    @staticmethod
    def _chat_expires_at(appointment: Appointment) -> datetime:
        _start_dt, end_dt = ConsultationService._appointment_window(appointment)
        if end_dt is not None:
            return end_dt.astimezone(UTC) + timedelta(days=7)
        confirmed_at = appointment.confirmed_at or appointment.created_at
        return ConsultationService._as_utc(confirmed_at) + timedelta(days=7)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _is_appointment_time_window(appointment: Appointment) -> bool:
        start_dt, end_dt = ConsultationService._appointment_window(appointment)
        if start_dt is None or end_dt is None:
            return False
        now = datetime.now(start_dt.tzinfo)
        return start_dt <= now <= end_dt

    @staticmethod
    def _appointment_window(appointment: Appointment) -> tuple[datetime | None, datetime | None]:
        try:
            start_text, end_text = appointment.time_slot.split("-", 1)
            start_clock = time.fromisoformat(start_text.strip())
            end_clock = time.fromisoformat(end_text.strip())
            slot_tz = ZoneInfo(appointment.timezone or "Asia/Kolkata")
            start_dt = datetime.fromisoformat(f"{appointment.date}T{start_clock.isoformat()}").replace(tzinfo=slot_tz)
            end_dt = datetime.fromisoformat(f"{appointment.date}T{end_clock.isoformat()}").replace(tzinfo=slot_tz)
            return start_dt, end_dt
        except (ValueError, KeyError):
            return None, None

    def _get_authorized_room(self, *, room_id: str, actor: User) -> ConsultationRoom:
        room = self.db.get(ConsultationRoom, room_id)
        if room is None:
            raise LookupError("Consultation room not found")
        self._assert_room_participant(room=room, actor=actor)
        return room

    def _assert_room_participant(self, *, room: ConsultationRoom, actor: User) -> None:
        if actor.id not in {room.patient_id, room.doctor_id} and actor.role != "hospital_admin":
            raise PermissionError("Only consultation participants can access this room")

    def _other_participant_id(self, *, room: ConsultationRoom, actor: User) -> str:
        if actor.id == room.patient_id:
            return room.doctor_id
        if actor.id == room.doctor_id:
            return room.patient_id
        raise PermissionError("Only direct participants can send consultation payloads")
