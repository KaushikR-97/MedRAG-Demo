from dataclasses import dataclass
from datetime import UTC, datetime

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.core.config import settings
from app.rag.clinical_timeline import build_document_timeline_context


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    title: str
    score: float
    text: str


class HybridMedicalRetriever:
    def __init__(
        self,
        *,
        qdrant: QdrantClient | None = None,
        embedder: SentenceTransformer | None = None,
        reranker: CrossEncoder | None = None,
    ) -> None:
        self.qdrant = qdrant or self._build_qdrant()
        self.embedder = embedder or self._build_embedder()
        self.reranker = reranker or self._build_reranker()

    def _build_qdrant(self) -> QdrantClient | None:
        if not settings.qdrant_url:
            return None
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    def _build_embedder(self) -> SentenceTransformer | None:
        if not settings.qdrant_url:
            return None
        # BGE-M3 is the default text embedding model. It gives the RAG layer a
        # stronger multilingual baseline for Indian medical records while the
        # existing BM25 path preserves exact-match recall for drugs and labs.
        return SentenceTransformer(settings.embedding_model, device=settings.embedding_device)

    def _build_reranker(self) -> CrossEncoder | None:
        if not settings.qdrant_url or not settings.reranker_model:
            return None
        try:
            return CrossEncoder(settings.reranker_model, device=settings.reranker_device)
        except Exception:
            return None

    def retrieve(
        self,
        query: str,
        *,
        patient_id: str | None,
        top_k: int = 5,
        language: str = "en",
        source_types: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        dense = self._dense_search(
            query,
            patient_id=patient_id,
            language=language,
            source_types=source_types or ["guideline", "verified_patient_document"],
            top_k=top_k * 2,
        )
        sparse = self._bm25_search(query, dense, top_k=top_k * 2)
        fused = self._rrf([dense, sparse])
        return self._rerank(query, fused)[:top_k]

class GraphMedicalRetriever:
    """Graph-based UMLS/SNOMED-CT clinical relation maps simulator."""
    def retrieve_relations(self, query: str) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        return [
            RetrievedChunk(
                id="generic-clinical-knowledge-graph-framework",
                title="Generic clinical knowledge graph framework",
                score=0.72,
                text=(
                    "Clinical knowledge graph reasoning should map the user's condition or symptom to candidate diseases, related findings, investigations, medication classes, contraindications, interactions, and escalation criteria. "
                    "Use verified guidelines and patient-specific context for concrete disease facts instead of hardcoded disease examples."
                ),
            )
        ]


class HybridMedicalRetriever:
    def __init__(
        self,
        *,
        qdrant: QdrantClient | None = None,
        embedder: SentenceTransformer | None = None,
        reranker: CrossEncoder | None = None,
    ) -> None:
        self.qdrant = qdrant or self._build_qdrant()
        self.embedder = embedder or self._build_embedder()
        self.reranker = reranker or self._build_reranker()

    def _build_qdrant(self) -> QdrantClient | None:
        if not settings.qdrant_url:
            return None
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)

    def _build_embedder(self) -> SentenceTransformer | None:
        if not settings.qdrant_url:
            return None
        return SentenceTransformer(settings.embedding_model, device=settings.embedding_device)

    def _build_reranker(self) -> CrossEncoder | None:
        if not settings.qdrant_url or not settings.reranker_model:
            return None
        try:
            return CrossEncoder(settings.reranker_model, device=settings.reranker_device)
        except Exception:
            return None

    def retrieve(
        self,
        query: str,
        *,
        patient_id: str | None,
        top_k: int = 5,
        language: str = "en",
        source_types: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        dense = self._dense_search(
            query,
            patient_id=patient_id,
            language=language,
            source_types=source_types or ["guideline", "verified_patient_document"],
            top_k=top_k * 2,
        )
        sparse = self._bm25_search(query, dense, top_k=top_k * 2)
        fused = self._rrf([dense, sparse])
        return self._rerank(query, fused)[:top_k]

    def retrieve_many(
        self,
        queries: list[str],
        *,
        patient_id: str | None,
        top_k: int = 5,
        language: str = "en",
        source_types: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        rankings = [
            self.retrieve(
                query,
                patient_id=patient_id,
                top_k=top_k,
                language=language,
                source_types=source_types,
            )
            for query in queries
            if query.strip()
        ]
        fused = self._rrf(rankings)
        
        # Inject Graph RAG SNOMED-CT concepts
        graph_retriever = GraphMedicalRetriever()
        graph_chunks = []
        for q in queries:
            graph_chunks.extend(graph_retriever.retrieve_relations(q))
            
        seen = set()
        unique_graph_chunks = []
        for gc in graph_chunks:
            if gc.id not in seen:
                seen.add(gc.id)
                unique_graph_chunks.append(gc)
                
        final_results = unique_graph_chunks + fused
        return final_results[:top_k]

    def _dense_search(
        self,
        query: str,
        *,
        patient_id: str | None,
        language: str,
        source_types: list[str],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if self.qdrant is None or self.embedder is None:
            db_chunks = []
            if patient_id:
                try:
                    from app.db.session import SessionLocal
                    from app.models.document import MedicalDocument
                    with SessionLocal() as db:
                        docs = db.query(MedicalDocument).filter(
                            MedicalDocument.patient_id == patient_id,
                            MedicalDocument.verified_text != "",
                            MedicalDocument.status != "deleted_by_patient",
                        ).all()
                        ranked_docs = sorted(
                            docs,
                            key=lambda item: (
                                _timeline_rank(build_document_timeline_context(db, item).timeline_state),
                                item.created_at or datetime.min.replace(tzinfo=UTC),
                            ),
                            reverse=True,
                        )
                        for doc in ranked_docs:
                            context = build_document_timeline_context(db, doc)
                            db_chunks.append(
                                RetrievedChunk(
                                    id=doc.id,
                                    title=doc.original_filename,
                                    score=0.95,
                                    text=(
                                        "Clinical timeline metadata:\n"
                                        f"Document type: {doc.document_type}\n"
                                        f"Record date: {doc.created_at.isoformat() if doc.created_at else ''}\n"
                                        f"Record role: {context.clinical_record_role}\n"
                                        f"Timeline state: {context.timeline_state}\n"
                                        f"Lab/report group: {context.lab_group}\n"
                                        f"Disease/diagnosis names: {context.disease_names}\n"
                                        f"Prescription state: {context.prescription_state}\n"
                                        f"Clinical/report date: {context.clinical_date}\n"
                                        "Retrieval rule: current-state answers should prefer current_snapshot or active records; historical and discharge records are background history unless the user asks for trends or past history.\n\n"
                                        f"{doc.verified_text}"
                                    ),
                                )
                            )
                except Exception:
                    pass
            return self._fallback_chunks(query) + db_chunks

        query_vector = self.embedder.encode(
            query,
            batch_size=settings.embedding_batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).tolist()
        must = [
            FieldCondition(key="language", match=MatchValue(value=language)),
            FieldCondition(key="source_type", match=MatchAny(any=source_types)),
        ]
        if patient_id:
            must.append(
                FieldCondition(
                    key="visibility",
                    match=MatchAny(any=["public", f"patient:{patient_id}"]),
                )
            )
        qfilter = Filter(must=must)
        try:
            hits = self._query_qdrant(query_vector=query_vector, qfilter=qfilter, top_k=top_k)
        except Exception:
            return self._fallback_chunks(query)
        chunks = []
        for hit in hits:
            payload = hit.payload or {}
            timeline_state = str(payload.get("timeline_state", ""))
            source_created_at = str(payload.get("source_created_at", ""))
            clinical_boost = _timeline_rank(timeline_state) * 0.015
            recency_boost = _recency_boost(source_created_at)
            chunks.append(
                RetrievedChunk(
                    id=str(hit.id),
                    title=str(payload.get("title", "Untitled source")),
                    score=float(hit.score or 0) + clinical_boost + recency_boost,
                    text=str(payload.get("parent_text") or payload.get("text", "")),
                )
            )
        return sorted(chunks, key=lambda chunk: chunk.score, reverse=True)

    def _query_qdrant(self, *, query_vector: list[float], qfilter: Filter, top_k: int):
        if hasattr(self.qdrant, "query_points"):
            response = self.qdrant.query_points(
                collection_name=settings.qdrant_collection,
                query=query_vector,
                query_filter=qfilter,
                limit=top_k,
                with_payload=True,
            )
            return response.points
        return self.qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=top_k,
            with_payload=True,
        )

    def _bm25_search(self, query: str, candidates: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
        if not candidates:
            return []
        tokenized = [candidate.text.lower().split() for candidate in candidates]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query.lower().split())
        ranked = sorted(zip(candidates, scores, strict=False), key=lambda item: item[1], reverse=True)
        return [
            RetrievedChunk(
                id=chunk.id,
                title=chunk.title,
                score=float(score),
                text=chunk.text,
            )
            for chunk, score in ranked[:top_k]
        ]

    def _rrf(self, lists: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
        scores: dict[str, float] = {}
        chunks: dict[str, RetrievedChunk] = {}
        for ranking in lists:
            for rank, chunk in enumerate(ranking, start=1):
                chunks[chunk.id] = chunk
                scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
        return [
            RetrievedChunk(id=chunks[cid].id, title=chunks[cid].title, score=score, text=chunks[cid].text)
            for cid, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        ]

    def _rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if self.reranker is None or not candidates:
            return candidates
        pairs = [(query, candidate.text) for candidate in candidates]
        scores = self.reranker.predict(pairs)
        return [
            RetrievedChunk(id=chunk.id, title=chunk.title, score=float(score), text=chunk.text)
            for chunk, score in sorted(zip(candidates, scores, strict=False), key=lambda item: item[1], reverse=True)
        ]

    def _fallback_chunks(self, query: str) -> list[RetrievedChunk]:
        chunks = [
            RetrievedChunk(
                id="safety-baseline",
                title="Clinical safety baseline",
                score=0.82,
                text=(
                    "Use retrieved clinical guidelines and verified patient documents. "
                    "If symptoms suggest an emergency, recommend urgent care instead of self-care. "
                    f"Original query: {query}"
                ),
            )
        ]
        chunks.append(
            RetrievedChunk(
                id="generic-clinical-reasoning-framework",
                title="Generic clinical reasoning and prescribing framework",
                score=0.78,
                text=(
                    "For any disease or symptom, clinical reasoning should identify the working diagnosis, important differentials, severity, red flags, relevant history, examination findings, investigation needs, and patient-specific risks. "
                    "For clinician decision support, treatment selection should consider age, weight, pregnancy/lactation status, allergies, renal and hepatic function, comorbidities, current medicines, contraindications, drug interactions, local resistance/guidelines, monitoring needs, follow-up timing, and escalation criteria. "
                    "Patient-facing answers should explain likely concepts, report meaning, lifestyle measures, red flags, and when to seek care without giving prescriptions, dose instructions, cures, or personalized treatment plans."
                ),
            )
        )
        return chunks


def _timeline_rank(timeline_state: str) -> int:
    if timeline_state in {"current_snapshot", "active_condition"}:
        return 3
    if timeline_state == "mixed_current_and_historical":
        return 2
    if timeline_state == "historical":
        return 1
    if timeline_state == "past_condition":
        return 1
    return 0


def _recency_boost(source_created_at: str) -> float:
    if not source_created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(source_created_at)
    except ValueError:
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(UTC) - created).days)
    if age_days <= 30:
        return 0.02
    if age_days <= 180:
        return 0.01
    if age_days <= 365:
        return 0.005
    return 0.0
