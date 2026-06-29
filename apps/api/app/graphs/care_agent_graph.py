import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.models.feature_modules import (
    AgentActionLog,
    Appointment,
    EmergencyDispatchRequest,
    HealthTask,
    PatientCalendarEvent,
)
from app.models.user import User
from app.services.ambulance_service import AmbulanceDispatchService
from app.services.audit_service import AuditService
from app.services.safety_service import ClinicalSafetyService


class CareAgentState(TypedDict, total=False):
    patient_id: str
    actor_id: str
    symptoms: str
    severity: int
    location_text: str
    preferred_date: str
    preferred_time_slot: str
    action: Literal["yearly_scan", "doctor_appointment", "ambulance"]
    safety_label: str
    reasoning: str
    result: dict
    acoustic_cough_type: str
    wheeze_acoustic_type: str


class CareCoordinationAgent:
    """Bounded agentic workflow for care coordination.

    The agent can use only approved internal tools: create calendar events,
    create appointments, or request ambulance escalation. It does not diagnose
    and it writes a durable action log for every execution.
    """

    agent_name = "care-coordination-agent-v1"

    def __init__(self, db: Session, *, ambulance: AmbulanceDispatchService | None = None) -> None:
        self.db = db
        self.safety = ClinicalSafetyService()
        self.ambulance = ambulance or AmbulanceDispatchService()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(CareAgentState)
        workflow.add_node("assess", self._assess)
        workflow.add_node("schedule_yearly_scan", self._schedule_yearly_scan)
        workflow.add_node("book_doctor_appointment", self._book_doctor_appointment)
        workflow.add_node("request_ambulance", self._request_ambulance)
        workflow.add_node("log_action", self._log_action)

        workflow.set_entry_point("assess")
        workflow.add_conditional_edges(
            "assess",
            self._route_after_assessment,
            {
                "yearly_scan": "schedule_yearly_scan",
                "doctor_appointment": "book_doctor_appointment",
                "ambulance": "request_ambulance",
            },
        )
        workflow.add_edge("schedule_yearly_scan", "log_action")
        workflow.add_edge("book_doctor_appointment", "log_action")
        workflow.add_edge("request_ambulance", "log_action")
        workflow.add_edge("log_action", END)
        return workflow.compile()

    def plan_yearly_scan(
        self,
        *,
        actor: User,
        preferred_date: str,
        preferred_time_slot: str,
    ) -> CareAgentState:
        return self.graph.invoke(
            {
                "patient_id": actor.id,
                "actor_id": actor.id,
                "preferred_date": preferred_date,
                "preferred_time_slot": preferred_time_slot,
                "action": "yearly_scan",
            }
        )

    def coordinate_symptoms(
        self,
        *,
        actor: User,
        patient_id: str,
        symptoms: str,
        severity: int,
        location_text: str = "",
        preferred_date: str = "",
        preferred_time_slot: str = "",
        acoustic_cough_type: str = "none",
        wheeze_acoustic_type: str = "none",
    ) -> CareAgentState:
        return self.graph.invoke(
            {
                "patient_id": patient_id,
                "actor_id": actor.id,
                "symptoms": symptoms,
                "severity": severity,
                "location_text": location_text,
                "preferred_date": preferred_date,
                "preferred_time_slot": preferred_time_slot,
                "acoustic_cough_type": acoustic_cough_type,
                "wheeze_acoustic_type": wheeze_acoustic_type,
            }
        )

    def _assess(self, state: CareAgentState) -> CareAgentState:
        if state.get("action") == "yearly_scan":
            return {
                "action": "yearly_scan",
                "safety_label": "routine_preventive",
                "reasoning": "Patient requested annual preventive health scan scheduling.",
            }

        safety_label, escalation = self.safety.classify(state.get("symptoms", ""))
        severity = state.get("severity", 1)
        
        acoustic_cough = state.get("acoustic_cough_type", "none")
        wheeze_acoustic = state.get("wheeze_acoustic_type", "none")
        
        acoustic_critical = (acoustic_cough == "croupy") or (wheeze_acoustic == "severe")
        
        critical = safety_label == "urgent_escalation" or severity >= 9 or acoustic_critical
        if critical:
            reasoning = escalation
            if acoustic_critical:
                reasoning = f"Critical acoustic bio-markers detected (Cough: {acoustic_cough}, Wheeze: {wheeze_acoustic}). Triage escalated immediately to emergency ambulance dispatch."
            return {
                "action": "ambulance",
                "safety_label": "urgent_escalation",
                "reasoning": reasoning or "Critical symptom severity detected. Requesting emergency ambulance escalation.",
            }
        return {
            "action": "doctor_appointment",
            "safety_label": safety_label,
            "reasoning": "Symptoms are concerning but not classified as immediate emergency; booking doctor appointment.",
        }

    def _route_after_assessment(self, state: CareAgentState) -> str:
        return state["action"]

    def _schedule_yearly_scan(self, state: CareAgentState) -> CareAgentState:
        starts_at = self._parse_start(state.get("preferred_date", ""), state.get("preferred_time_slot", ""))
        calendar = PatientCalendarEvent(
            id=str(uuid.uuid4()),
            patient_id=state["patient_id"],
            event_type="yearly_health_scan",
            title="Yearly preventive health scan",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            status="scheduled",
            source=self.agent_name,
            metadata_json=json.dumps({"time_slot": state.get("preferred_time_slot", "")}, separators=(",", ":")),
        )
        task = HealthTask(
            id=str(uuid.uuid4()),
            patient_id=state["patient_id"],
            task_type="yearly_health_scan",
            title="Complete yearly preventive health scan",
            description="Agent-created annual scan reminder based on patient calendar preference.",
            priority="medium",
            due_date=starts_at.date().isoformat(),
            status="pending",
        )
        self.db.add(calendar)
        self.db.add(task)
        self.db.commit()
        return {
            "result": {
                "calendar_event_id": calendar.id,
                "health_task_id": task.id,
                "starts_at": starts_at.isoformat(),
                "status": calendar.status,
            }
        }

    def _book_doctor_appointment(self, state: CareAgentState) -> CareAgentState:
        date_value = state.get("preferred_date") or (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
        appt = Appointment(
            id=str(uuid.uuid4()),
            patient_id=state["patient_id"],
            doctor_id=None,
            appointment_type="symptom_review",
            consultation_mode="in_person",
            date=date_value,
            time_slot=state.get("preferred_time_slot") or "next_available",
            status="requested",
            urgency="high" if state.get("severity", 1) >= 7 else "routine",
            notes=f"Agent booked due to symptoms: {state.get('symptoms', '')[:500]}",
            reason=state.get("symptoms", "")[:1000],
            booking_reference=f"AGENT-{uuid.uuid4().hex[:8].upper()}",
        )
        self.db.add(appt)
        self.db.commit()
        return {
            "result": {
                "appointment_id": appt.id,
                "status": appt.status,
                "urgency": appt.urgency,
                "date": appt.date,
                "time_slot": appt.time_slot,
            }
        }

    def _request_ambulance(self, state: CareAgentState) -> CareAgentState:
        reference = self.ambulance.request_dispatch(
            patient_id=state["patient_id"],
            symptoms=state.get("symptoms", ""),
            location_text=state.get("location_text", ""),
        )
        dispatch = EmergencyDispatchRequest(
            id=str(uuid.uuid4()),
            patient_id=state["patient_id"],
            actor_id=state["actor_id"],
            symptoms=state.get("symptoms", ""),
            severity=state.get("severity", 10),
            location_text=state.get("location_text", ""),
            status="requested",
            provider_reference=reference,
            safety_label="urgent_escalation",
        )
        self.db.add(dispatch)
        self.db.commit()
        return {
            "result": {
                "dispatch_id": dispatch.id,
                "status": dispatch.status,
                "provider_reference": dispatch.provider_reference,
                "instruction": "Emergency symptoms detected. Call 108/112 or local emergency services immediately.",
            }
        }

    def _log_action(self, state: CareAgentState) -> CareAgentState:
        payload = state.get("result", {})
        log = AgentActionLog(
            id=str(uuid.uuid4()),
            patient_id=state["patient_id"],
            actor_id=state["actor_id"],
            agent_name=self.agent_name,
            action=state["action"],
            status="completed",
            reasoning=state.get("reasoning", ""),
            tool_payload_json=json.dumps(payload, separators=(",", ":")),
        )
        self.db.add(log)
        self.db.commit()
        actor = self.db.get(User, state["actor_id"])
        if actor:
            AuditService(self.db).record(
                actor=actor,
                patient_id=state["patient_id"],
                action=f"agent.{state['action']}",
                purpose="care_coordination",
                resource_type="agent_action_log",
                resource_id=log.id,
                details={"reasoning": state.get("reasoning", ""), "result": payload},
            )
        result = dict(payload)
        result["agent_action_log_id"] = log.id
        return {"result": result}

    @staticmethod
    def _parse_start(preferred_date: str, preferred_time_slot: str) -> datetime:
        date_value = preferred_date or (datetime.now(UTC) + timedelta(days=365)).date().isoformat()
        time_value = preferred_time_slot.split("-")[0].strip() if preferred_time_slot else "09:00"
        try:
            parsed = datetime.fromisoformat(f"{date_value}T{time_value}:00")
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        except ValueError:
            return datetime.now(UTC) + timedelta(days=365)
