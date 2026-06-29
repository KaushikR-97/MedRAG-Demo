import uuid

from sqlalchemy.orm import Session

from app.models.document import MedicalDocument
from app.models.jobs import IngestionJob
from app.models.user import User
from app.services.queue_service import QueueService
from app.workers.document_jobs import process_document_pipeline


class IngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue_document_pipeline(self, *, doc: MedicalDocument, user: User) -> IngestionJob:
        return self._enqueue(doc=doc, user=user, job_type="document_ocr_ingest")

    def enqueue_verified_document_ingestion(self, *, doc: MedicalDocument, user: User) -> IngestionJob:
        return self._enqueue(doc=doc, user=user, job_type="document_rag_ingest")

    def _enqueue(self, *, doc: MedicalDocument, user: User, job_type: str) -> IngestionJob:
        ingestion_job = IngestionJob(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            patient_id=doc.patient_id,
            job_type=job_type,
            status="queued",
        )
        self.db.add(ingestion_job)
        self.db.flush()

        queue_job_id = QueueService().enqueue(
            process_document_pipeline,
            ingestion_job.id,
        )
        ingestion_job.queue_job_id = queue_job_id
        self.db.commit()
        self.db.refresh(ingestion_job)
        return ingestion_job
