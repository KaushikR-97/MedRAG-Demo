import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.graphs.clinical_graph import ClinicalRagGraph
from app.models.jobs import AnswerTrace
from app.models.user import User
from app.rag.retriever import RetrievedChunk
from app.schemas.clinical import (
    ClinicalAnswer,
    ClinicalHistoryItem,
    ClinicalQuestion,
    ImportChatHistoryRequest,
    ImportChatHistoryResponse,
    SourceSnippet,
)
from app.services.audit_service import AuditService
from app.services.ai_policy_service import AiPolicyService
from app.services.compliance_service import ComplianceService
from app.services.privacy_service import PrivacyService
from app.services.trace_service import AnswerTraceService, TraceTimer
from app.services.cache_service import ClinicalCacheService
from app.services.generation_service import ClinicalGenerationService

router = APIRouter()


@router.post("/ask", response_model=ClinicalAnswer)
def ask_clinical_question(
    payload: ClinicalQuestion,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClinicalAnswer:
    patient_id = payload.patient_id or user.id
    conversation_id = str(payload.conversation_id or uuid.uuid4())
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    policy = AiPolicyService().evaluate(actor=user, question=payload.question)
    timer = TraceTimer()

    cache_service = ClinicalCacheService()
    direct_value_query = _is_patient_record_value_query(payload.question)
    cached = None if direct_value_query else cache_service.get_cached_answer(payload.question, user.role, patient_id)
    if cached and _is_gibberish_answer(cached.get("answer", "")):
        cached = None
    if cached:
        AuditService(db).record(
            actor=user,
            patient_id=patient_id,
            action="clinical.ask_cache_hit",
            purpose="answer_health_question",
            ip_address=request.client.host if request.client else "",
            details={"question_length": len(payload.question), "conversation_id": conversation_id},
        )
        trace_id = str(uuid.uuid4())
        trace_sources = [
            RetrievedChunk(
                id=source["id"],
                title=source["title"],
                score=source["score"],
                text=source["text"],
            )
            for source in cached.get("sources", [])
        ]
        trace_service = AnswerTraceService(db)
        trace_service.record(
            trace_id=trace_id,
            conversation_id=conversation_id,
            actor=user,
            patient_id=patient_id,
            question=payload.question,
            safety_label=cached["safety_label"],
            sources=trace_sources,
            answer=cached["answer"],
            latency_ms=timer.elapsed_ms(),
        )
        return ClinicalAnswer(
            answer=cached["answer"],
            conversation_id=conversation_id,
            safety_label=cached["safety_label"],
            escalation=cached.get("escalation"),
            sources=[
                SourceSnippet(
                    id=s["id"],
                    title=s["title"],
                    score=s["score"],
                    text=s["text"],
                )
                for s in cached.get("sources", [])
            ],
            trace_id=trace_id,
            query_route=cached.get("query_route", ""),
            query_route_reason=cached.get("query_route_reason", ""),
            query_route_confidence=cached.get("query_route_confidence", 0.0),
            query_route_used_fallback=cached.get("query_route_used_fallback", False),
            retrieval_source_types=cached.get("retrieval_source_types", []),
            rewritten_queries=cached.get("rewritten_queries", []),
        )

    AuditService(db).record(
        actor=user,
        patient_id=patient_id,
        action="clinical.ask",
        purpose="answer_health_question",
        ip_address=request.client.host if request.client else "",
        details={"question_length": len(payload.question), "conversation_id": conversation_id},
    )
    trace_service = AnswerTraceService(db)
    conversation_history = trace_service.recent_conversation(
        conversation_id=conversation_id,
        actor=user,
        patient_id=patient_id,
    )
    try:
        state = ClinicalRagGraph().invoke(
            question=payload.question,
            patient_id=patient_id,
            user_role=user.role,
            conversation_history=conversation_history,
            policy_instruction=policy.instruction,
            policy_mode=policy.mode,
            policy_refusal=policy.refusal,
        )
    except Exception as exc:
        fallback_answer = _fallback_clinical_answer(payload.question, user.role)
        state = {
            "answer": fallback_answer,
            "trace_id": str(uuid.uuid4()),
            "safety_label": "fallback_answer",
            "sources": [],
            "query_route": "fallback",
            "query_route_reason": f"Clinical graph failed: {exc}",
            "query_route_confidence": 0.0,
            "query_route_used_fallback": True,
            "retrieval_source_types": [],
            "rewritten_queries": [],
        }
    direct_value_answer = _direct_lab_value_answer(payload.question, state.get("sources", []))
    raw_answer = direct_value_answer or state["answer"]
    answer = PrivacyService().minimum_necessary_text(actor=user, patient_id=patient_id, text=raw_answer, db=db)
    if _is_gibberish_answer(answer):
        answer = _fallback_clinical_answer(payload.question, user.role, sources=state.get("sources", []))
        state["safety_label"] = "fallback_answer"
        state["query_route"] = "fallback"
        state["query_route_reason"] = "Repetitive model output suppressed"
        state["query_route_confidence"] = 0.0
        state["query_route_used_fallback"] = True
    sources = [
        SourceSnippet(
            id=source.id,
            title=source.title,
            score=source.score,
            text=PrivacyService().minimum_necessary_text(actor=user, patient_id=patient_id, text=source.text, db=db),
        )
        for source in state.get("sources", [])
    ]
    trace_sources = [
        RetrievedChunk(
            id=source.id,
            title=source.title,
            score=source.score,
            text=PrivacyService().minimum_necessary_text(actor=user, patient_id=patient_id, text=source.text, db=db),
        )
        for source in state.get("sources", [])
    ]
    trace_service.record(
        trace_id=state["trace_id"],
        conversation_id=conversation_id,
        actor=user,
        patient_id=patient_id,
        question=payload.question,
        safety_label=state["safety_label"],
        sources=trace_sources,
        answer=answer,
        latency_ms=timer.elapsed_ms(),
    )
    cache_payload = {
        "answer": answer,
        "safety_label": state["safety_label"],
        "escalation": state.get("escalation"),
        "sources": [
            {"id": s.id, "title": s.title, "score": s.score, "text": s.text}
            for s in trace_sources
        ],
        "query_route": state.get("query_route", ""),
        "query_route_reason": state.get("query_route_reason", ""),
        "query_route_confidence": state.get("query_route_confidence", 0.0),
        "query_route_used_fallback": state.get("query_route_used_fallback", False),
        "retrieval_source_types": state.get("retrieval_source_types", []),
        "rewritten_queries": state.get("rewritten_queries", []),
    }
    if not direct_value_query:
        cache_service.set_cached_answer(payload.question, user.role, patient_id, cache_payload)
    return ClinicalAnswer(
        answer=answer,
        conversation_id=conversation_id,
        safety_label=state["safety_label"],
        escalation=state.get("escalation"),
        sources=sources,
        trace_id=state["trace_id"],
        query_route=state.get("query_route", ""),
        query_route_reason=state.get("query_route_reason", ""),
        query_route_confidence=state.get("query_route_confidence", 0.0),
        query_route_used_fallback=state.get("query_route_used_fallback", False),
        retrieval_source_types=state.get("retrieval_source_types", []),
        rewritten_queries=state.get("rewritten_queries", []),
    )


def _fallback_clinical_answer(question: str, role: str, sources: list[RetrievedChunk] | None = None) -> str:
    return ClinicalGenerationService._fallback_generation(
        question=question,
        user_role=role,
        reason="Clinical graph failed",
        source_text=_source_text(sources or []),
    )


def _source_text(sources: list[RetrievedChunk]) -> str:
    return "\n".join(f"- [{source.id}] {source.title}: {source.text}" for source in sources)


def _is_gibberish_answer(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 160:
        return False
    compact = re.sub(r"\s+", "", stripped.lower())
    if re.search(r"([a-z]{3,12})\1{8,}", compact):
        return True
    words = re.findall(r"[a-zA-Z]{2,}", stripped.lower())
    if len(words) < 40:
        return False
    unique_ratio = len(set(words)) / len(words)
    most_common_count = max(words.count(word) for word in set(words))
    return unique_ratio < 0.18 or most_common_count >= 18


LAB_VALUE_ALIASES: dict[str, list[str]] = {
    "uric acid": ["uric acid", "serum uric acid", "s uric acid"],
    "hba1c": ["hba1c", "hb a1c", "glycated hemoglobin", "glycated haemoglobin"],
    "creatinine": ["creatinine", "serum creatinine"],
    "glucose": ["glucose", "fasting glucose", "fasting blood sugar", "fbs", "rbs", "ppbs"],
    "tsh": ["tsh", "thyroid stimulating hormone"],
    "cholesterol": ["cholesterol", "total cholesterol"],
    "triglyceride": ["triglyceride", "triglycerides"],
    "hemoglobin": ["hemoglobin", "haemoglobin", "hb"],
    "platelet": ["platelet", "platelets", "platelet count"],
}


def _is_patient_record_value_query(question: str) -> bool:
    lowered = question.lower()
    record_cues = {"my ", "report", "lab", "blood test", "value", "level", "result", "reading"}
    return any(cue in lowered for cue in record_cues) and any(
        alias in lowered
        for aliases in LAB_VALUE_ALIASES.values()
        for alias in aliases
    )


def _direct_lab_value_answer(question: str, sources: list[RetrievedChunk]) -> str | None:
    lowered = question.lower()
    requested_aliases = [
        (label, aliases)
        for label, aliases in LAB_VALUE_ALIASES.items()
        if any(alias in lowered for alias in aliases)
    ]
    if not requested_aliases:
        return None
    for label, aliases in requested_aliases:
        for source in sources:
            value = _extract_lab_value(source.text, aliases)
            if value:
                report_date = _extract_metadata_line(source.text, "Clinical/report date") or _extract_metadata_line(source.text, "Record date")
                date_text = f" dated {report_date}" if report_date else ""
                return (
                    f"Your latest {label} value found in your uploaded report{date_text} is {value}. "
                    "This is from your medical record context, not a generic answer. Please discuss the result with your clinician for interpretation with symptoms, medicines, kidney function, and other reports."
                )
    return None


def _extract_lab_value(text: str, aliases: list[str]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        for alias in aliases:
            if alias.lower() not in line.lower():
                continue
            escaped = re.escape(alias)
            patterns = [
                rf"{escaped}\s*(?:[:=\-]|\s)\s*([0-9]+(?:\.[0-9]+)?\s*(?:mg/dl|mg/dL|mmol/L|%|g/dL|g/dl|u/L|IU/L|mIU/L|ng/mL|cells/[a-zA-Z]+)?)",
                rf"([0-9]+(?:\.[0-9]+)?\s*(?:mg/dl|mg/dL|mmol/L|%|g/dL|g/dl|u/L|IU/L|mIU/L|ng/mL|cells/[a-zA-Z]+)?)\s+{escaped}",
            ]
            for pattern in patterns:
                match = re.search(pattern, line, flags=re.IGNORECASE)
                if match:
                    return match.group(1).strip()
    compact = re.sub(r"\s+", " ", text)
    for alias in aliases:
        match = re.search(
            rf"{re.escape(alias)}\s*(?:[:=\-]|\s)\s*([0-9]+(?:\.[0-9]+)?\s*(?:mg/dl|mg/dL|mmol/L|%|g/dL|g/dl|u/L|IU/L|mIU/L|ng/mL|cells/[a-zA-Z]+)?)",
            compact,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
    return None


def _extract_metadata_line(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


@router.get("/history", response_model=list[ClinicalHistoryItem])
def list_clinical_history(
    patient_id: str | None = None,
    limit: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClinicalHistoryItem]:
    target_patient_id = patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=target_patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Missing patient consent or care-team access")
    rows = (
        db.query(AnswerTrace)
        .filter(AnswerTrace.patient_id == target_patient_id)
        .order_by(AnswerTrace.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return [
        ClinicalHistoryItem(
            trace_id=row.trace_id,
            conversation_id=row.conversation_id,
            patient_id=row.patient_id,
            question=row.question,
            answer=row.answer,
            safety_label=row.safety_label,
            model_provider=row.model_provider,
            model_name=row.model_name,
            prompt_version=row.prompt_version,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


@router.post("/history/import", response_model=ImportChatHistoryResponse)
def import_previous_chat_history(
    payload: ImportChatHistoryRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportChatHistoryResponse:
    patient_id = payload.patient_id or user.id
    if not ComplianceService(db).can_access_patient(actor=user, patient_id=patient_id, scope="clinical.ask"):
        raise HTTPException(403, "Missing patient consent or care-team access")

    privacy = PrivacyService()
    redacted_messages = [
        {"role": message.role, "content": privacy.redact_phi(message.content)}
        for message in payload.messages
    ]
    questions = [item["content"] for item in redacted_messages if item["role"] in {"patient", "doctor"}]
    answers = [item["content"] for item in redacted_messages if item["role"] == "assistant"]
    trace_id = str(uuid.uuid4())
    trace = AnswerTrace(
        id=str(uuid.uuid4()),
        trace_id=trace_id,
        conversation_id="",
        actor_id=user.id,
        patient_id=patient_id,
        question="\n\n".join(questions)[:8000] or "Imported previous chat",
        safety_label="imported_history",
        model_provider="imported",
        model_name=payload.source_label,
        prompt_version="chat-import-v1",
        retrieved_sources_json=json.dumps(
            [{"source": payload.source_label, "messages": redacted_messages}],
            separators=(",", ":"),
        ),
        answer="\n\n".join(answers)[:8000] or "Imported chat contained no assistant answer",
        latency_ms=0,
    )
    db.add(trace)
    db.commit()
    AuditService(db).record(
        actor=user,
        patient_id=patient_id,
        action="clinical.history_imported",
        purpose="continuity_of_care",
        resource_type="answer_trace",
        resource_id=trace_id,
        ip_address=request.client.host if request.client else "",
        details={"message_count": len(payload.messages), "source_label": payload.source_label},
    )
    return ImportChatHistoryResponse(trace_id=trace_id, stored_messages=len(payload.messages))
