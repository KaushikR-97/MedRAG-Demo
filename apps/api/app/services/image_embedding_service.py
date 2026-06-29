from __future__ import annotations

import io
import uuid
from dataclasses import dataclass

import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings

try:
    import open_clip
    from PIL import Image
except Exception:  # pragma: no cover - optional production dependency
    Image = None
    open_clip = None


@dataclass(frozen=True)
class ImageEmbeddingResult:
    status: str
    model: str
    vector_id: str = ""
    error: str = ""


class BioMedClipImageIndexer:
    """Indexes medical images into a separate Qdrant collection.

    The image vectors are used for similarity/retrieval support only. They are
    not diagnostic findings, and they do not enter clinical RAG until a
    clinician verifies image-derived text.
    """

    def __init__(self) -> None:
        self.client = (
            QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
            if settings.qdrant_url
            else None
        )
        self.device = settings.image_embedding_device
        self._model = None
        self._preprocess = None

    def index_image(
        self,
        *,
        document_id: str,
        patient_id: str,
        image_bytes: bytes,
        mime_type: str,
        filename: str,
        modality: str,
    ) -> ImageEmbeddingResult:
        if not settings.image_embedding_enabled:
            return ImageEmbeddingResult(status="disabled", model=settings.image_embedding_model)
        if self.client is None:
            return ImageEmbeddingResult(
                status="skipped_no_qdrant",
                model=settings.image_embedding_model,
            )
        if Image is None or open_clip is None:
            return ImageEmbeddingResult(
                status="skipped_missing_dependency",
                model=settings.image_embedding_model,
                error="Install open-clip-torch and Pillow to enable BioMedCLIP image embeddings.",
            )
        if not mime_type.startswith("image/"):
            return ImageEmbeddingResult(status="not_required", model=settings.image_embedding_model)

        try:
            vector = self._embed(image_bytes)
            self._ensure_collection(vector_size=len(vector))
            vector_id = str(uuid.uuid4())
            self.client.upsert(
                collection_name=settings.qdrant_image_collection,
                points=[
                    PointStruct(
                        id=vector_id,
                        vector=vector,
                        payload={
                            "document_id": document_id,
                            "patient_id": patient_id,
                            "filename": filename,
                            "mime_type": mime_type,
                            "modality": modality,
                            "model": settings.image_embedding_model,
                            "source_type": "medical_image",
                            "visibility": f"patient:{patient_id}",
                        },
                    )
                ],
            )
            return ImageEmbeddingResult(
                status="indexed",
                model=settings.image_embedding_model,
                vector_id=vector_id,
            )
        except Exception as exc:
            return ImageEmbeddingResult(
                status="failed",
                model=settings.image_embedding_model,
                error=str(exc),
            )

    def _load_model(self) -> None:
        if self._model is not None and self._preprocess is not None:
            return
        model, _, preprocess = open_clip.create_model_and_transforms(
            "hf-hub:" + settings.image_embedding_model,
        )
        model.eval()
        model.to(self.device)
        self._model = model
        self._preprocess = preprocess

    def _embed(self, image_bytes: bytes) -> list[float]:
        self._load_model()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_tensor = self._preprocess(image).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            features = self._model.encode_image(image_tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        return features[0].detach().cpu().float().tolist()

    def _ensure_collection(self, *, vector_size: int) -> None:
        collections = {item.name for item in self.client.get_collections().collections}
        if settings.qdrant_image_collection not in collections:
            self.client.create_collection(
                collection_name=settings.qdrant_image_collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
