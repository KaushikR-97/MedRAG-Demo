import base64

from app.core.config import settings

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None
    HumanMessage = None
    SystemMessage = None


IMAGE_MODALITY_KEYWORDS = {
    "xray": "xray",
    "x-ray": "xray",
    "radiograph": "xray",
    "dental": "dental",
    "tooth": "dental",
    "teeth": "dental",
    "skin": "symptom_photo",
    "rash": "symptom_photo",
    "wound": "symptom_photo",
    "symptom": "symptom_photo",
    "scan": "scan",
    "mri": "mri",
    "ct": "ct",
    "ultrasound": "ultrasound",
}


class MedicalImageService:
    """Safe boundary for medical image handling.

    The output is not a diagnosis. It is a preliminary observation for clinician
    review. Only clinician-verified findings should be indexed into RAG.
    """

    def classify_modality(self, *, filename: str, document_type: str, mime_type: str) -> str:
        haystack = f"{filename} {document_type} {mime_type}".lower()
        for keyword, modality in IMAGE_MODALITY_KEYWORDS.items():
            if keyword in haystack:
                return modality
        if document_type in {"health_scan", "imaging"}:
            return "medical_image"
        if mime_type.startswith("image/"):
            return "clinical_photo"
        return ""

    def requires_clinician_review(self, *, mime_type: str, document_type: str) -> bool:
        return mime_type.startswith("image/") and document_type in {
            "health_scan",
            "imaging",
            "dental_image",
            "symptom_photo",
            "past_record",
        }

    def analyze_image(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        modality: str,
        filename: str,
    ) -> str:
        if not settings.vision_model_enabled:
            return self._safe_placeholder(modality=modality, filename=filename)
        if not settings.openai_api_key or ChatOpenAI is None or HumanMessage is None or SystemMessage is None:
            return self._safe_placeholder(modality=modality, filename=filename)

        encoded = base64.b64encode(image_bytes).decode("ascii")
        model = ChatOpenAI(
            model=settings.vision_model_name,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        try:
            response = model.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are a medical image intake assistant. Do not diagnose. "
                            "Describe only visible, non-final observations for clinician review. "
                            "Mention image quality limitations. State that a licensed clinician must verify findings. "
                            "Do not recommend treatment."
                        )
                    ),
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": (
                                    f"Modality hint: {modality}. Filename: {filename}. "
                                    "Return concise observations and limitations only."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                            },
                        ]
                    ),
                ]
            )
            return str(response.content)
        except Exception:
            return self._safe_placeholder(modality=modality, filename=filename)

    @staticmethod
    def _safe_placeholder(*, modality: str, filename: str) -> str:
        return (
            f"Image '{filename}' was classified as {modality or 'clinical image'}. "
            "No diagnostic interpretation was generated in this environment. "
            "A licensed clinician must review the original image and enter verified findings before RAG ingestion."
        )
