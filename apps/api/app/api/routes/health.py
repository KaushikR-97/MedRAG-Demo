from fastapi import APIRouter
from qdrant_client import QdrantClient
from redis import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    checks = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    if settings.qdrant_url:
        try:
            QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=2).get_collections()
            checks["qdrant"] = "ok"
        except Exception as exc:
            checks["qdrant"] = f"error: {type(exc).__name__}"
    else:
        checks["qdrant"] = "not_configured"

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
