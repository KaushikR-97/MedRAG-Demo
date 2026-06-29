from uuid import UUID

from pydantic import BaseModel, Field


class ClinicalQuestion(BaseModel):
    question: str = Field(min_length=4, max_length=12000)
    patient_id: str | None = None
    conversation_id: UUID | None = None


class SourceSnippet(BaseModel):
    id: str
    title: str
    score: float
    text: str


class ClinicalAnswer(BaseModel):
    answer: str
    conversation_id: str
    safety_label: str
    escalation: str | None = None
    sources: list[SourceSnippet]
    trace_id: str
    query_route: str = ""
    query_route_reason: str = ""
    query_route_confidence: float = 0.0
    query_route_used_fallback: bool = False
    retrieval_source_types: list[str] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)


class ClinicalHistoryItem(BaseModel):
    trace_id: str
    conversation_id: str
    patient_id: str
    question: str
    answer: str
    safety_label: str
    model_provider: str
    model_name: str
    prompt_version: str
    created_at: str


class ImportedChatMessage(BaseModel):
    role: str = Field(pattern="^(patient|doctor|assistant|system)$")
    content: str = Field(min_length=1, max_length=12000)


class ImportChatHistoryRequest(BaseModel):
    patient_id: str | None = None
    source_label: str = Field(default="previous_chat", max_length=80)
    messages: list[ImportedChatMessage] = Field(min_length=1, max_length=100)


class ImportChatHistoryResponse(BaseModel):
    trace_id: str
    stored_messages: int
