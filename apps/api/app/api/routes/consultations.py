from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.features import (
    ConsultationMessageCreate,
    ConsultationMessageRecord,
    ConsultationRoomResponse,
    ConsultationSignalCreate,
    ConsultationSignalRecord,
)
from app.services.audit_service import AuditService
from app.services.consultation_service import ConsultationService

router = APIRouter()


@router.post("/{appointment_id}/room", response_model=ConsultationRoomResponse)
def join_consultation_room(
    appointment_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationRoomResponse:
    try:
        service = ConsultationService(db)
        room = service.get_or_create_room(appointment_id=appointment_id, actor=user)
        AuditService(db).record(
            actor=user,
            patient_id=room.patient_id,
            action="consultation.room_joined",
            purpose="video_consultation",
            resource_type="consultation_room",
            resource_id=room.id,
            ip_address=request.client.host if request.client else "",
            details={"appointment_id": appointment_id, "actor_role": user.role},
        )
        return ConsultationRoomResponse(
            id=room.id,
            appointment_id=room.appointment_id,
            patient_id=room.patient_id,
            doctor_id=room.doctor_id,
            status=room.status,
            expires_at=room.expires_at.isoformat(),
            room_token=service.issue_room_token(room=room, actor=user),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/{appointment_id}/room/end", response_model=ConsultationRoomResponse)
def end_consultation_room(
    appointment_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationRoomResponse:
    try:
        service = ConsultationService(db)
        room = service.end_room(appointment_id=appointment_id, actor=user)
        AuditService(db).record(
            actor=user,
            patient_id=room.patient_id,
            action="consultation.room_ended",
            purpose="video_consultation",
            resource_type="consultation_room",
            resource_id=room.id,
            ip_address=request.client.host if request.client else "",
            details={"appointment_id": appointment_id, "actor_role": user.role},
        )
        return ConsultationRoomResponse(
            id=room.id,
            appointment_id=room.appointment_id,
            patient_id=room.patient_id,
            doctor_id=room.doctor_id,
            status=room.status,
            expires_at=room.expires_at.isoformat(),
            room_token=service.issue_room_token(room=room, actor=user),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/{appointment_id}/messages", response_model=list[ConsultationMessageRecord])
def list_consultation_messages(
    appointment_id: str,
    since_id: str = "",
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConsultationMessageRecord]:
    try:
        service = ConsultationService(db)
        room = service.get_or_create_chat_room(appointment_id=appointment_id, actor=user)
        return [
            ConsultationMessageRecord(**record)
            for record in service.list_messages(room_id=room.id, actor=user, since_id=since_id, limit=limit)
        ]
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/{appointment_id}/messages", response_model=ConsultationMessageRecord)
def post_consultation_message(
    appointment_id: str,
    payload: ConsultationMessageCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsultationMessageRecord:
    try:
        service = ConsultationService(db)
        room = service.get_or_create_chat_room(appointment_id=appointment_id, actor=user)
        message = service.post_message(
            room_id=room.id,
            actor=user,
            body=payload.body,
            message_type=payload.message_type,
            client_message_id=payload.client_message_id,
        )
        AuditService(db).record(
            actor=user,
            patient_id=room.patient_id,
            action="consultation.message_sent",
            purpose="video_consultation",
            resource_type="consultation_message",
            resource_id=message.id,
            ip_address=request.client.host if request.client else "",
            details={"appointment_id": appointment_id, "message_type": payload.message_type},
        )
        return ConsultationMessageRecord(**service._message_record(message))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/{appointment_id}/signals")
def post_consultation_signal(
    appointment_id: str,
    payload: ConsultationSignalCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        service = ConsultationService(db)
        room = service.get_room_for_appointment(appointment_id=appointment_id, actor=user)
        signal = service.post_signal(
            room_id=room.id,
            actor=user,
            signal_type=payload.signal_type,
            payload=payload.payload,
        )
        return {"id": signal.id, "status": "queued"}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/{appointment_id}/signals", response_model=list[ConsultationSignalRecord])
def poll_consultation_signals(
    appointment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConsultationSignalRecord]:
    try:
        service = ConsultationService(db)
        room = service.get_room_for_appointment(appointment_id=appointment_id, actor=user)
        return [ConsultationSignalRecord(**record) for record in service.poll_signals(room_id=room.id, actor=user)]
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
