import re


class DocumentExtractionService:
    def extract_prescription_fields(self, text: str) -> dict:
        medicines = re.findall(r"\b[A-Z][a-zA-Z]{2,}\s*(?:\d+(?:mg|ml|mcg))?", text)
        dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
        doctor = re.search(r"Dr\.?\s+([A-Za-z .]+)", text)
        return {
            "medicines": medicines[:20],
            "dates": dates[:10],
            "doctor": doctor.group(0) if doctor else "",
        }

