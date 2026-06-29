from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    care_agent,
    clinical,
    communication,
    consultations,
    compliance,
    doctor_features,
    documents,
    health,
    hospitals,
    patient_features,
    preconsult,
    public_health,
    shared_features,
)
from app.core.config import settings
from app.db.session import init_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.scope.get("path", "")
        if "//" in path:
            normalized = "/" + "/".join(part for part in path.split("/") if part)
            request.scope["path"] = normalized or "/"
            request.scope["raw_path"] = request.scope["path"].encode("ascii")
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.is_non_prod else None,
        redoc_url="/redoc" if settings.is_non_prod else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=settings.allowed_origin_regex or None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.environment.lower() == "production":
        from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
        app.add_middleware(HTTPSRedirectMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(care_agent.router, prefix="/care-agent", tags=["agentic-care"])
    app.include_router(documents.router, prefix="/documents", tags=["documents"])
    app.include_router(clinical.router, prefix="/clinical", tags=["clinical"])
    app.include_router(consultations.router, prefix="/consultations", tags=["consultations"])
    app.include_router(compliance.router, prefix="/compliance", tags=["compliance"])
    app.include_router(communication.router, prefix="/communication", tags=["communication"])
    app.include_router(patient_features.router, prefix="/patient", tags=["patient-features"])
    app.include_router(doctor_features.router, prefix="/doctor", tags=["doctor-features"])
    app.include_router(hospitals.router, prefix="/hospitals", tags=["hospital-management"])
    app.include_router(preconsult.router, prefix="/preconsult", tags=["preconsult-agent"])
    app.include_router(public_health.router, prefix="/public-health", tags=["public-health"])
    app.include_router(shared_features.router, prefix="/shared", tags=["shared-features"])

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    return app


app = create_app()
