from __future__ import annotations

import gc
import re
import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from app.core.config import settings

try:
    import torch
except Exception:  # pragma: no cover - optional runtime cleanup
    torch = None


SECTION_ALIASES = {
    "chief complaint": "chief_complaint",
    "complaint": "chief_complaint",
    "history": "history",
    "history of present illness": "history",
    "past history": "past_history",
    "past medical history": "past_history",
    "allergies": "allergies",
    "medications": "medications",
    "current medications": "medications",
    "prescription": "prescription",
    "rx": "prescription",
    "diagnosis": "diagnosis",
    "assessment": "assessment",
    "plan": "plan",
    "advice": "advice",
    "follow up": "follow_up",
    "follow-up": "follow_up",
    "investigations": "investigations",
    "lab results": "lab_results",
    "laboratory": "lab_results",
    "vitals": "vitals",
    "discharge summary": "discharge_summary",
    "procedure": "procedure",
    "impression": "impression",
    "findings": "findings",
}

SECTION_RE = re.compile(
    r"^\s*(?P<header>[A-Za-z][A-Za-z /_-]{2,60})\s*[:：]\s*(?P<body>.*)$"
)


@dataclass(frozen=True)
class MedicalChunk:
    text: str
    section: str
    chunk_type: str
    parent_text: str
    start_char: int
    end_char: int


class MedicalVectorIndexer:
    def __init__(self) -> None:
        self.client = (
            QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
            if settings.qdrant_url
            else None
        )
        self.embedder = (
            SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
            if settings.qdrant_url
            else None
        )

    def ensure_collection(self, vector_size: int) -> None:
        if self.client is None:
            return
        collections = {item.name for item in self.client.get_collections().collections}
        if settings.qdrant_collection not in collections:
            self.client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def index_verified_document(
        self,
        *,
        document_id: str,
        patient_id: str,
        title: str,
        text: str,
        document_type: str = "",
        source_created_at: str = "",
        clinical_context: dict[str, str] | None = None,
        language: str = "en",
    ) -> int:
        if not settings.qdrant_url:
            return 1 if settings.is_non_prod else 0
        clinical_context = clinical_context or {}
        context_header = self._clinical_context_header(
            document_type=document_type,
            source_created_at=source_created_at,
            clinical_context=clinical_context,
        )
        chunks = self._chunk(f"{context_header}\n{text}" if context_header else text)
        if self.embedder is None or self.client is None:
            return 0
        chunk_texts = [chunk.text for chunk in chunks]
        vectors = self._encode_texts(chunk_texts)
        vector_size = len(vectors[0]) if vectors else 0
        if vector_size == 0:
            return 0
        self.ensure_collection(vector_size)
        self._delete_existing_document_points(document_id=document_id)
        parent_id = f"{document_id}:parent"
        points = []
        for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{chunk_index}")),
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "patient_id": patient_id,
                        "parent_id": parent_id,
                        "chunk_index": chunk_index,
                        "chunk_type": chunk.chunk_type,
                        "section": chunk.section,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "title": title,
                        "text": chunk.text,
                        "parent_text": chunk.parent_text,
                        "language": language,
                        "source_type": "verified_patient_document",
                        "visibility": f"patient:{patient_id}",
                        "document_type": document_type,
                        "timeline_state": clinical_context.get("timeline_state", ""),
                        "clinical_record_role": clinical_context.get("clinical_record_role", ""),
                        "lab_group": clinical_context.get("lab_group", ""),
                        "disease_names": clinical_context.get("disease_names", ""),
                        "prescription_state": clinical_context.get("prescription_state", ""),
                        "clinical_date": clinical_context.get("clinical_date", ""),
                        "source_created_at": clinical_context.get("clinical_date", "") or source_created_at,
                    },
                )
            )
        self.client.upsert(collection_name=settings.qdrant_collection, points=points)
        return len(points)

    def _delete_existing_document_points(self, *, document_id: str) -> None:
        if self.client is None:
            return
        try:
            self.client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="document_id",
                                match=MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception:
            return

    def index_reference_document(
        self,
        *,
        source_id: str,
        title: str,
        text: str,
        source_type: str = "guideline",
        url: str = "",
        publisher: str = "",
        publication_date: str = "",
        license_status: str = "",
        language: str = "en",
    ) -> int:
        if not settings.qdrant_url:
            return 1 if settings.is_non_prod else 0
        chunks = self._chunk(text)
        if self.embedder is None or self.client is None:
            return 0
        chunk_texts = [chunk.text for chunk in chunks]
        vectors = self._encode_texts(chunk_texts)
        vector_size = len(vectors[0]) if vectors else 0
        if vector_size == 0:
            return 0
        self.ensure_collection(vector_size)
        parent_id = f"{source_id}:parent"
        points = []
        for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{chunk_index}")),
                    vector=vector,
                    payload={
                        "document_id": source_id,
                        "source_id": source_id,
                        "parent_id": parent_id,
                        "chunk_index": chunk_index,
                        "chunk_type": chunk.chunk_type,
                        "section": chunk.section,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "title": title,
                        "text": chunk.text,
                        "parent_text": chunk.parent_text,
                        "language": language,
                        "source_type": source_type,
                        "visibility": "public",
                        "url": url,
                        "publisher": publisher,
                        "publication_date": publication_date,
                        "license_status": license_status,
                    },
                )
            )
        self.client.upsert(collection_name=settings.qdrant_collection, points=points)
        return len(points)

    def _encode_texts(self, texts: list[str]) -> list[list[float]]:
        if self.embedder is None or not texts:
            return []
        try:
            encoded = self.embedder.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return encoded.tolist()
        finally:
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

    def _chunk(
        self,
        text: str,
        *,
        target_chars: int = 900,
        overlap_chars: int = 140,
        parent_chars: int = 2400,
    ) -> list[MedicalChunk]:
        normalized = self._normalize_text(text)
        if not normalized:
            return []

        section_blocks = self._split_sections(normalized)
        chunks: list[MedicalChunk] = []
        for section, section_text, section_start in section_blocks:
            chunk_type = self._chunk_type(section=section, text=section_text)
            for chunk_text, local_start, local_end in self._split_with_overlap(
                section_text,
                target_chars=target_chars,
                overlap_chars=overlap_chars,
            ):
                start_char = section_start + local_start
                end_char = section_start + local_end
                chunks.append(
                    MedicalChunk(
                        text=self._format_chunk(section=section, text=chunk_text),
                        section=section,
                        chunk_type=chunk_type,
                        parent_text=self._parent_window(
                            normalized,
                            start=start_char,
                            end=end_char,
                            parent_chars=parent_chars,
                        ),
                        start_char=start_char,
                        end_char=end_char,
                    )
                )
        return chunks or [
            MedicalChunk(
                text=normalized,
                section="general",
                chunk_type="general",
                parent_text=normalized[:parent_chars],
                start_char=0,
                end_char=len(normalized),
            )
        ]

    def _normalize_text(self, text: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.replace("\r", "\n").split("\n")]
        return "\n".join(line for line in lines if line)

    def _split_sections(self, text: str) -> list[tuple[str, str, int]]:
        lines = text.split("\n")
        blocks: list[tuple[str, list[str], int]] = []
        current_section = "general"
        current_lines: list[str] = []
        current_start = 0
        cursor = 0

        for line in lines:
            section, body = self._section_from_line(line)
            if section:
                if current_lines:
                    blocks.append((current_section, current_lines, current_start))
                current_section = section
                current_lines = [body] if body else []
                current_start = cursor + line.find(body) if body else cursor
            else:
                if not current_lines:
                    current_start = cursor
                current_lines.append(line)
            cursor += len(line) + 1

        if current_lines:
            blocks.append((current_section, current_lines, current_start))

        return [(section, "\n".join(lines).strip(), start) for section, lines, start in blocks if lines]

    def _section_from_line(self, line: str) -> tuple[str | None, str]:
        match = SECTION_RE.match(line)
        if not match:
            return None, line
        header = re.sub(r"\s+", " ", match.group("header").strip().lower())
        section = SECTION_ALIASES.get(header)
        if not section:
            return None, line
        return section, match.group("body").strip()

    def _split_with_overlap(
        self,
        text: str,
        *,
        target_chars: int,
        overlap_chars: int,
    ) -> list[tuple[str, int, int]]:
        paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
        pieces: list[tuple[str, int, int]] = []
        current = ""
        current_start = 0
        search_from = 0

        for paragraph in paragraphs or [text]:
            para_start = text.find(paragraph, search_from)
            para_start = para_start if para_start >= 0 else search_from
            para_end = para_start + len(paragraph)
            search_from = para_end

            if len(paragraph) > target_chars:
                if current:
                    pieces.append((current.strip(), current_start, current_start + len(current)))
                    current = ""
                pieces.extend(
                    self._split_long_text(
                        paragraph,
                        base_start=para_start,
                        target_chars=target_chars,
                        overlap_chars=overlap_chars,
                    )
                )
                continue

            separator = "\n" if current else ""
            if current and len(current) + len(separator) + len(paragraph) > target_chars:
                pieces.append((current.strip(), current_start, current_start + len(current)))
                overlap = current[-overlap_chars:].strip()
                if overlap:
                    current = f"{overlap}\n{paragraph}"
                    current_start = max(current_start, para_start - len(overlap) - 1)
                else:
                    current = paragraph
                    current_start = para_start
            else:
                if not current:
                    current_start = para_start
                current = f"{current}{separator}{paragraph}"

        if current.strip():
            pieces.append((current.strip(), current_start, current_start + len(current)))
        return pieces

    def _split_long_text(
        self,
        text: str,
        *,
        base_start: int,
        target_chars: int,
        overlap_chars: int,
    ) -> list[tuple[str, int, int]]:
        chunks: list[tuple[str, int, int]] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + target_chars)
            if end < len(text):
                split_at = max(text.rfind(". ", start, end), text.rfind("; ", start, end))
                if split_at > start + target_chars // 2:
                    end = split_at + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append((chunk, base_start + start, base_start + end))
            if end >= len(text):
                break
            start = max(0, end - overlap_chars)
        return chunks

    def _parent_window(self, text: str, *, start: int, end: int, parent_chars: int) -> str:
        midpoint = (start + end) // 2
        window_start = max(0, midpoint - parent_chars // 2)
        window_end = min(len(text), window_start + parent_chars)
        return text[window_start:window_end].strip()

    def _chunk_type(self, *, section: str, text: str) -> str:
        if section in {
            "prescription",
            "medications",
            "diagnosis",
            "lab_results",
            "vitals",
            "impression",
            "findings",
            "discharge_summary",
        }:
            return section
        lowered = text.lower()
        if any(term in lowered for term in {"tablet", "capsule", "mg", "dose", "rx"}):
            return "prescription"
        if any(term in lowered for term in {"hba1c", "creatinine", "hemoglobin", "wbc", "platelet"}):
            return "lab_results"
        return "clinical_note" if section != "general" else "general"

    def _format_chunk(self, *, section: str, text: str) -> str:
        return f"Section: {section}\n{text.strip()}" if section != "general" else text.strip()

    def _clinical_context_header(
        self,
        *,
        document_type: str,
        source_created_at: str,
        clinical_context: dict[str, str],
    ) -> str:
        if not document_type and not clinical_context:
            return ""
        lines = [
            "Clinical timeline metadata:",
            f"Document type: {document_type or 'unknown'}",
        ]
        if source_created_at:
            lines.append(f"Record date: {source_created_at}")
        for key, label in {
            "clinical_record_role": "Record role",
            "timeline_state": "Timeline state",
            "lab_group": "Lab/report group",
            "disease_names": "Disease/diagnosis names",
            "prescription_state": "Prescription state",
            "clinical_date": "Clinical/report date",
        }.items():
            value = clinical_context.get(key, "")
            if value:
                lines.append(f"{label}: {value}")
        lines.append(
            "Retrieval rule: current-state answers should prefer current_snapshot or active records; historical and discharge records are background history unless the user asks for trends or past history."
        )
        return "\n".join(lines)
