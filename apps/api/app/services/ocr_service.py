from __future__ import annotations

import io
from dataclasses import dataclass

from app.core.config import settings

try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover - optional runtime dependency
    PaddleOCR = None

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional runtime dependency
    PdfReader = None

try:
    import fitz
except Exception:  # pragma: no cover - optional runtime dependency
    fitz = None


HANDWRITING_HINTS = {
    "handwritten",
    "hand writing",
    "written",
    "manual",
    "rx",
    "doctor note",
}


@dataclass(frozen=True)
class OcrResult:
    text: str
    engine: str
    confidence: float
    review_status: str
    handwriting_detected: bool
    warning: str = ""


class OcrService:
    """Production OCR boundary with a hard handwriting safety gate.

    PaddleOCR is the primary OCR engine because it is practical for printed
    scanned reports, prescriptions, and multilingual document images. Handwritten
    prescriptions are treated as unsafe for automatic DB text storage unless a
    human verifies/transcribes them first.
    """

    def __init__(self) -> None:
        self._ocr = None

    def extract(
        self,
        content: bytes,
        *,
        mime_type: str,
        document_type: str,
        filename: str = "",
    ) -> OcrResult:
        if mime_type == "application/pdf":
            native = self._extract_native_pdf_text(content)
            if native:
                return OcrResult(
                    text=native,
                    engine="pypdf",
                    confidence=1.0,
                    review_status="machine_ocr_ready_for_human_verification",
                    handwriting_detected=False,
                )
            return self._extract_scanned_pdf(content, document_type=document_type, filename=filename)

        if mime_type.startswith("image/"):
            return self._extract_image(content, document_type=document_type, filename=filename)

        return OcrResult(
            text="",
            engine=settings.ocr_engine,
            confidence=0.0,
            review_status="unsupported_mime_type",
            handwriting_detected=False,
            warning=f"OCR is not configured for MIME type {mime_type}.",
        )

    def _extract_native_pdf_text(self, content: bytes) -> str:
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [(page.extract_text() or "").strip() for page in reader.pages[:20]]
            text = "\n\n".join(page for page in pages if page)
        except Exception:
            return ""
        if len(text.strip()) < 80:
            return ""
        return text.strip()

    def _extract_scanned_pdf(self, content: bytes, *, document_type: str, filename: str) -> OcrResult:
        if fitz is None:
            return OcrResult(
                text="",
                engine="paddleocr",
                confidence=0.0,
                review_status="ocr_dependency_missing",
                handwriting_detected=self._has_handwriting_hint(document_type, filename),
                warning="Install PyMuPDF to render scanned PDFs before OCR.",
            )
        try:
            pdf = fitz.open(stream=content, filetype="pdf")
            page_texts: list[str] = []
            confidences: list[float] = []
            for page_index in range(min(5, pdf.page_count)):
                page = pdf.load_page(page_index)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                result = self._run_paddle_ocr(pix.tobytes("png"))
                page_texts.append(result.text)
                if result.confidence:
                    confidences.append(result.confidence)
            text = "\n\n".join(part for part in page_texts if part.strip())
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
        except Exception as exc:
            return OcrResult(
                text="",
                engine="paddleocr",
                confidence=0.0,
                review_status="ocr_failed",
                handwriting_detected=self._has_handwriting_hint(document_type, filename),
                warning=str(exc),
            )
        return self._apply_review_policy(
            text=text,
            confidence=confidence,
            engine="paddleocr+pdf_render",
            document_type=document_type,
            filename=filename,
        )

    def _extract_image(self, content: bytes, *, document_type: str, filename: str) -> OcrResult:
        result = self._run_paddle_ocr(content)
        return self._apply_review_policy(
            text=result.text,
            confidence=result.confidence,
            engine=result.engine,
            document_type=document_type,
            filename=filename,
            warning=result.warning,
        )

    def _run_paddle_ocr(self, image_bytes: bytes) -> OcrResult:
        if PaddleOCR is None or Image is None:
            return OcrResult(
                text="",
                engine="paddleocr",
                confidence=0.0,
                review_status="ocr_dependency_missing",
                handwriting_detected=False,
                warning="Install the OCR extra: pip install -e .[ocr]",
            )
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            ocr = self._load_paddle()
            raw = ocr.ocr(self._pil_to_array(image), cls=True)
            lines, confidences = self._parse_paddle_response(raw)
        except Exception as exc:
            return OcrResult(
                text="",
                engine="paddleocr",
                confidence=0.0,
                review_status="ocr_failed",
                handwriting_detected=False,
                warning=str(exc),
            )
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return OcrResult(
            text="\n".join(lines).strip(),
            engine="paddleocr",
            confidence=confidence,
            review_status="machine_ocr_ready_for_human_verification",
            handwriting_detected=False,
        )

    def _load_paddle(self):
        if self._ocr is None:
            lang = settings.ocr_languages.split(",")[0].strip() or "en"
            self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        return self._ocr

    @staticmethod
    def _pil_to_array(image):
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency comes with OCR stack
            raise RuntimeError("numpy is required for PaddleOCR image conversion") from exc
        return np.array(image)

    def _parse_paddle_response(self, raw) -> tuple[list[str], list[float]]:
        lines: list[str] = []
        confidences: list[float] = []
        for page in raw or []:
            for item in page or []:
                if not item or len(item) < 2:
                    continue
                text_score = item[1]
                if not isinstance(text_score, (list, tuple)) or len(text_score) < 2:
                    continue
                text = str(text_score[0]).strip()
                try:
                    score = float(text_score[1])
                except (TypeError, ValueError):
                    score = 0.0
                if text:
                    lines.append(text)
                    confidences.append(score)
        return lines, confidences

    def _apply_review_policy(
        self,
        *,
        text: str,
        confidence: float,
        engine: str,
        document_type: str,
        filename: str,
        warning: str = "",
    ) -> OcrResult:
        handwriting_detected = self._detect_handwriting(
            confidence=confidence,
            document_type=document_type,
            filename=filename,
            extracted_text=text,
        )
        if handwriting_detected and not settings.ocr_store_handwritten_raw_text:
            return OcrResult(
                text="",
                engine=engine,
                confidence=confidence,
                review_status="handwriting_human_transcription_required",
                handwriting_detected=True,
                warning=(
                    warning
                    or "Handwritten prescription suspected. OCR text was not stored in DB; "
                    "a human must transcribe and verify it first."
                ),
            )

        if confidence < settings.ocr_min_confidence:
            return OcrResult(
                text=text,
                engine=engine,
                confidence=confidence,
                review_status="low_confidence_human_verification_required",
                handwriting_detected=handwriting_detected,
                warning=warning or "OCR confidence is below the configured threshold.",
            )

        return OcrResult(
            text=text,
            engine=engine,
            confidence=confidence,
            review_status="machine_ocr_ready_for_human_verification",
            handwriting_detected=handwriting_detected,
            warning=warning,
        )

    def _detect_handwriting(
        self,
        *,
        confidence: float,
        document_type: str,
        filename: str,
        extracted_text: str,
    ) -> bool:
        is_prescription = document_type == "prescription" or "prescription" in filename.lower()
        if not is_prescription:
            return False
        if self._has_handwriting_hint(document_type, filename):
            return True
        if confidence and confidence < settings.ocr_handwriting_confidence_threshold:
            return True
        token_count = len(extracted_text.split())
        return token_count < 8

    @staticmethod
    def _has_handwriting_hint(document_type: str, filename: str) -> bool:
        haystack = f"{document_type} {filename}".lower()
        return any(hint in haystack for hint in HANDWRITING_HINTS)
