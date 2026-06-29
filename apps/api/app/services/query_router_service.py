import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.core.config import settings

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional during lightweight test runs
    ChatOpenAI = None
    ChatPromptTemplate = None

try:
    from transformers import pipeline
except Exception:  # pragma: no cover - optional local router dependency
    pipeline = None

try:
    import torch
except Exception:  # pragma: no cover - optional local router dependency
    torch = None


QueryRoute = Literal[
    "no_rag_needed",
    "general_health_education",
    "clinical_guideline_needed",
    "patient_record_needed",
    "both_patient_record_and_guideline",
]

VALID_ROUTES = {
    "no_rag_needed",
    "general_health_education",
    "clinical_guideline_needed",
    "patient_record_needed",
    "both_patient_record_and_guideline",
}

ROUTE_LABELS = {
    "no_rag_needed": "app navigation, account help, or non-medical administration question",
    "general_health_education": "general health education that does not need records or guidelines",
    "clinical_guideline_needed": "medical question that needs clinical guidelines but not patient records",
    "patient_record_needed": "question that needs patient records, labs, scans, medications, or history",
    "both_patient_record_and_guideline": "clinical question that needs both patient records and medical guidelines",
}


@dataclass(frozen=True)
class QueryRoutingDecision:
    route: QueryRoute
    needs_rag: bool
    source_types: list[str]
    reason: str
    confidence: float
    used_fallback: bool = False


class QueryRouterService:
    """Free local pre-retrieval router with conservative fallback.

    For the POC, the default provider is a Hugging Face zero-shot classifier, so
    no OpenAI credits are required. Any low confidence, unavailable model, or
    invalid route falls back to broad retrieval over both guidelines and verified
    patient records.
    """

    def __init__(self, *, confidence_threshold: float | None = None) -> None:
        self.confidence_threshold = confidence_threshold or settings.query_router_confidence_threshold

    def route(self, *, question: str, user_role: str) -> QueryRoutingDecision:
        deterministic = self._deterministic_patient_record_route(question=question)
        if deterministic is not None:
            return deterministic
        raw = self._invoke_router_llm(question=question, user_role=user_role)
        if raw is None:
            return self._fallback("Router LLM unavailable; defaulting to broad medical retrieval.", user_role=user_role)
        try:
            payload = self._parse_router_response(raw)
        except ValueError as exc:
            return self._fallback(f"Router LLM returned invalid output: {exc}", user_role=user_role)

        route = str(payload.get("route", ""))
        confidence = float(payload.get("confidence", 0))
        reason = str(payload.get("reason", "LLM router decision."))
        if route not in VALID_ROUTES:
            return self._fallback(f"Router LLM returned unsupported route: {route}", user_role=user_role)
        if confidence < self.confidence_threshold:
            return self._fallback(
                f"Router confidence {confidence:.2f} below threshold {self.confidence_threshold:.2f}.",
                user_role=user_role
            )
        return self._decision(route=route, confidence=confidence, reason=reason, used_fallback=False)

    def _invoke_router_llm(self, *, question: str, user_role: str) -> str | None:
        if settings.query_router_provider == "local_zero_shot":
            return self._invoke_local_zero_shot(question=question, user_role=user_role)
        if settings.query_router_provider != "openai":
            return None
        if not settings.openai_api_key or ChatOpenAI is None or ChatPromptTemplate is None:
            return None
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a strict medical RAG query router. Return only JSON. "
                    "Do not answer the medical question. Choose exactly one route: "
                    "no_rag_needed, general_health_education, clinical_guideline_needed, "
                    "patient_record_needed, both_patient_record_and_guideline. "
                    "Use patient_record_needed when verified patient records, labs, scans, "
                    "medications, allergies, prior chats, or history are needed. "
                    "Use clinical_guideline_needed when general medical guidelines are enough. "
                    "Use both when both could help. Use no_rag_needed only for app/help/admin queries. "
                    "Return JSON with keys route, confidence, reason. Confidence must be 0 to 1.",
                ),
                (
                    "human",
                    "User role: {user_role}\nQuestion: {question}\n"
                    "Return JSON only, no markdown.",
                ),
            ]
        )
        model = ChatOpenAI(
            model=settings.query_router_model or settings.model_name,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        response = (prompt | model).invoke({"user_role": user_role, "question": question})
        return str(response.content)

    def _invoke_local_zero_shot(self, *, question: str, user_role: str) -> str | None:
        classifier = get_zero_shot_router()
        if classifier is None:
            return None
        labels = list(ROUTE_LABELS.values())
        try:
            result = classifier(
                f"User role: {user_role}. Query: {question}",
                candidate_labels=labels,
                hypothesis_template="This query is about {}.",
                multi_label=False,
            )
        except Exception:
            return None
        if not result or not result.get("labels"):
            return None
        best_label = str(result["labels"][0])
        confidence = float(result["scores"][0])
        route = next(route for route, label in ROUTE_LABELS.items() if label == best_label)
        return json.dumps(
            {
                "route": route,
                "confidence": confidence,
                "reason": (
                    "Free local Hugging Face zero-shot router selected route "
                    f"'{route}' from label '{best_label}'."
                ),
            }
        )

    def _parse_router_response(self, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(parsed, dict):
            raise ValueError("expected JSON object")
        return parsed

    def _decision(
        self,
        *,
        route: str,
        confidence: float,
        reason: str,
        used_fallback: bool,
    ) -> QueryRoutingDecision:
        source_types: list[str]
        if route in {"no_rag_needed", "general_health_education"}:
            source_types = []
            needs_rag = False
        elif route == "clinical_guideline_needed":
            source_types = ["guideline"]
            needs_rag = True
        elif route == "patient_record_needed":
            source_types = ["verified_patient_document"]
            needs_rag = True
        else:
            source_types = ["guideline", "verified_patient_document"]
            needs_rag = True
        return QueryRoutingDecision(
            route=route,  # type: ignore[arg-type]
            needs_rag=needs_rag,
            source_types=source_types,
            reason=reason,
            confidence=confidence,
            used_fallback=used_fallback,
        )

    def _fallback(self, reason: str, user_role: str) -> QueryRoutingDecision:
        fallback_route = "both_patient_record_and_guideline"
        return self._decision(
            route=fallback_route,
            confidence=0.0,
            reason=reason,
            used_fallback=True,
        )

    def _deterministic_patient_record_route(self, *, question: str) -> QueryRoutingDecision | None:
        lowered = question.lower()
        record_cues = {
            "my ",
            "mine",
            "report",
            "lab",
            "blood test",
            "value",
            "level",
            "result",
            "reading",
        }
        lab_cues = {
            "uric acid",
            "hba1c",
            "hb a1c",
            "glucose",
            "creatinine",
            "tsh",
            "t3",
            "t4",
            "cholesterol",
            "triglyceride",
            "hdl",
            "ldl",
            "hemoglobin",
            "haemoglobin",
            "platelet",
            "wbc",
            "rbc",
            "bilirubin",
            "sgpt",
            "sgot",
            "alt",
            "ast",
        }
        if any(cue in lowered for cue in record_cues) and any(cue in lowered for cue in lab_cues):
            return self._decision(
                route="patient_record_needed",
                confidence=1.0,
                reason="Deterministic lab/report value query; patient records are required.",
                used_fallback=False,
            )
        return None


@lru_cache
def get_zero_shot_router():
    if pipeline is None:
        return None
    try:
        if settings.query_router_device == "auto":
            device = 0 if torch is not None and torch.cuda.is_available() else -1
        elif settings.query_router_device == "cuda":
            device = 0
        else:
            device = -1
        return pipeline(
            "zero-shot-classification",
            model=settings.query_router_model,
            device=device,
        )
    except Exception:
        return None
