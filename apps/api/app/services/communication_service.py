import random
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.orm import Session
from twilio.rest import Client

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.feature_modules import OtpCode


class CommunicationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def send_otp(self, *, target: str, channel: str, purpose: str = "verify") -> OtpCode:
        code = f"{random.randint(0, 999999):06d}"
        record = OtpCode(
            id=str(uuid.uuid4()),
            target=target,
            channel=channel,
            code_hash=hash_password(code),
            purpose=purpose,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        self.db.add(record)
        self.db.commit()
        self._send_message(target=target, channel=channel, body=f"Your MedRAG OTP is {code}. It expires in 10 minutes.")
        return record

    def verify_otp(self, *, target: str, code: str, purpose: str = "verify") -> bool:
        record = (
            self.db.query(OtpCode)
            .filter(
                OtpCode.target == target,
                OtpCode.purpose == purpose,
                OtpCode.is_used.is_(False),
                OtpCode.expires_at > datetime.now(UTC),
            )
            .order_by(OtpCode.created_at.desc())
            .first()
        )
        if record is None or not verify_password(code, record.code_hash):
            return False
        record.is_used = True
        self.db.commit()
        return True

    def _send_message(self, *, target: str, channel: str, body: str) -> None:
        if channel in {"sms", "whatsapp"} and settings.twilio_account_sid:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            from_number = settings.twilio_whatsapp_from if channel == "whatsapp" else settings.twilio_sms_from
            to_number = f"whatsapp:{target}" if channel == "whatsapp" and not target.startswith("whatsapp:") else target
            client.messages.create(from_=from_number, to=to_number, body=body)
        elif channel == "email" and settings.smtp_username:
            msg = EmailMessage()
            msg["Subject"] = "MedRAG India OTP"
            msg["From"] = settings.smtp_username
            msg["To"] = target
            msg.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
                smtp.starttls()
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)

