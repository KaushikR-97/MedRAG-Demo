from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MedRAG India"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://medrag:medrag@postgres:5432/medrag"
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    consultation_encryption_key: str = ""
    consultation_room_expire_minutes: int = 240
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:8000"]
    allowed_origin_regex: str = r"https://.*\.cloudspaces\.litng\.ai"

    openai_api_key: str = ""
    openai_api_base: str = ""
    model_provider: str = "openai"
    model_name: str = "gpt-4.1-mini"
    query_router_provider: str = "local_zero_shot"
    query_router_model: str = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
    query_router_device: str = "cpu"
    query_router_confidence_threshold: float = 0.92
    query_rewrite_model: str = ""
    query_rewrite_max_queries: int = 3
    conversation_history_max_turns: int = 6
    conversation_history_max_chars: int = 6000
    evidence_max_chars_per_source: int = 900
    citation_validation_enabled: bool = True
    vision_model_enabled: bool = False
    vision_model_name: str = "gpt-4.1-mini"
    base_model_name: str = "BioMistral/BioMistral-7B"
    finetuned_adapter_path: str = ""
    local_model_device: str = "auto"
    local_model_load_in_4bit: bool = True
    local_model_max_new_tokens: int = 1536
    local_model_max_input_tokens: int = 0
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "medical_guidelines"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 4
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "cpu"
    image_embedding_enabled: bool = True
    image_embedding_model: str = "microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
    image_embedding_device: str = "cpu"
    qdrant_image_collection: str = "medical_image_embeddings"
    ocr_engine: str = "paddleocr"
    ocr_languages: str = "en"
    ocr_min_confidence: float = 0.70
    ocr_handwriting_confidence_threshold: float = 0.82
    ocr_store_handwritten_raw_text: bool = False
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "medrag-documents"
    s3_region: str = "ap-south-1"
    clamd_host: str = "clamav"
    clamd_port: int = 3310
    malware_scan_fail_open: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    twilio_sms_from: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    nhr_api_base: str = ""
    openweather_api_key: str = ""

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_non_prod(self) -> bool:
        return self.environment.lower() in {"local", "dev", "development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
