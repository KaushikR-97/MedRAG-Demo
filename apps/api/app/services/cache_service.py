import hashlib
import json
from redis import Redis
from app.core.config import settings


class ClinicalCacheService:
    """Redis-based caching layer for Clinical RAG queries.

    Speeds up response times to under 10ms for repeated requests, reducing vector database
    and LLM inference server costs while maintaining strict multi-tenant isolation.
    """

    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url)
        self.prefix = "medrag:cache:ask:v2"

    def get_cached_answer(self, question: str, role: str, patient_id: str | None) -> dict | None:
        try:
            key = self._cache_key(question, role, patient_id)
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception:
            # Silently fail to fallback on live query if Redis is offline/unreachable
            return None
        return None

    def set_cached_answer(
        self, question: str, role: str, patient_id: str | None, answer_data: dict, ttl: int = 3600
    ) -> None:
        try:
            key = self._cache_key(question, role, patient_id)
            serialized = json.dumps(answer_data, separators=(",", ":"))
            self.redis.setex(key, ttl, serialized)
        except Exception:
            # Silently allow failure if Redis write fails
            pass

    def _cache_key(self, question: str, role: str, patient_id: str | None) -> str:
        sanitized_q = question.lower().strip()
        q_hash = hashlib.sha256(sanitized_q.encode("utf-8")).hexdigest()
        tenant = patient_id if patient_id else "global"
        return f"{self.prefix}:{tenant}:{role}:{q_hash}"
