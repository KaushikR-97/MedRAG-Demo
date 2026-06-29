from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    id: str
    original_filename: str
    document_type: str
    status: str
    malware_status: str
    sha256: str
    ocr_text: str = ""
    ocr_engine: str = ""
    ocr_confidence: str = ""
    ocr_review_status: str = ""
    ocr_handwriting_detected: bool = False
    ocr_warning: str = ""
    image_modality: str = ""
    image_review_status: str = ""
    image_ai_observations: str = ""
    clinician_verified_findings: str = ""
    image_embedding_status: str = ""
    image_embedding_model: str = ""
    image_vector_id: str = ""
    verified_by_patient: bool
    ingested_to_rag: bool


class VerifyOcrRequest(BaseModel):
    verified_text: str = Field(min_length=1)


class VerifyImageFindingsRequest(BaseModel):
    verified_findings: str = Field(min_length=1)


class IngestionJobRecord(BaseModel):
    id: str
    document_id: str
    job_type: str
    status: str
    queue_job_id: str
    error: str
