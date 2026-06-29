import json
import time
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.jobs import AnswerTrace
from app.models.user import User
from app.rag.retriever import RetrievedChunk
from app.services.privacy_service import PrivacyService


def effective_model_name() -> str:
    if settings.model_provider in {"local_hf", "local_finetuned"}:
        adapter_path = settings.finetuned_adapter_path.strip()
        return f"{settings.base_model_name}+{adapter_path}" if adapter_path else settings.base_model_name
    return settings.model_name


class TraceTimer:
    def __init__(self) -> None:
        self.started_at = time.perf_counter()

    def elapsed_ms(self) -> int:
        return round((time.perf_counter() - self.started_at) * 1000)


class AnswerTraceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        trace_id: str,
        conversation_id: str,
        actor: User,
        patient_id: str,
        question: str,
        safety_label: str,
        sources: list[RetrievedChunk],
        answer: str,
        latency_ms: int,
    ) -> AnswerTrace:
        privacy = PrivacyService()
        redacted_sources = [
            {
                "id": source.id,
                "title": source.title,
                "score": source.score,
                "text": privacy.redact_phi(source.text),
            }
            for source in sources
        ]
        trace = AnswerTrace(
            id=str(uuid.uuid4()),
            trace_id=trace_id,
            conversation_id=conversation_id,
            actor_id=actor.id,
            patient_id=patient_id,
            question=privacy.redact_phi(question),
            safety_label=safety_label,
            model_provider=settings.model_provider,
            model_name=effective_model_name(),
            prompt_version="clinical-rag-v1",
            retrieved_sources_json=json.dumps(redacted_sources),
            answer=privacy.redact_phi(answer),
            latency_ms=latency_ms,
        )
        self.db.add(trace)
        self.db.commit()
        return trace

    def recent_conversation(
        self,
        *,
        conversation_id: str,
        actor: User,
        patient_id: str,
        max_turns: int | None = None,
        max_chars: int | None = None,
    ) -> list[dict[str, str]]:
        turn_limit = max_turns or settings.conversation_history_max_turns
        char_limit = max_chars or settings.conversation_history_max_chars
        rows = (
            self.db.query(AnswerTrace)
            .filter(
                AnswerTrace.conversation_id == conversation_id,
                AnswerTrace.actor_id == actor.id,
                AnswerTrace.patient_id == patient_id,
            )
            .order_by(AnswerTrace.created_at.desc())
            .limit(turn_limit)
            .all()
        )
        selected_turns: list[tuple[str, str]] = []
        used_chars = 0
        for row in rows:
            turn_chars = len(row.question) + len(row.answer)
            if selected_turns and used_chars + turn_chars > char_limit:
                break
            if not selected_turns and turn_chars > char_limit:
                question_limit = min(len(row.question), char_limit // 2)
                question = row.question[:question_limit]
                answer = row.answer[: max(char_limit - len(question), 0)]
                selected_turns.append((question, answer))
                break
            selected_turns.append((row.question, row.answer))
            used_chars += turn_chars

        messages: list[dict[str, str]] = []
        for question, answer in reversed(selected_turns):
            messages.extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]
            )
        return messages
