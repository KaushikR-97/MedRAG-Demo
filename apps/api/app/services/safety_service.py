import re

EMERGENCY_TERMS = {
    "chest pain",
    "difficulty breathing",
    "stroke",
    "unconscious",
    "severe bleeding",
    "suicidal",
}

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"forget\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"system\s+override",
    r"developer\s+mode",
    r"jailbreak",
    r"reveal\s+(?:your\s+)?system\s+prompt",
    r"what\s+is\s+your\s+system\s+prompt",
    r"tell\s+me\s+your\s+system\s+prompt",
    r"ignore\s+(?:the\s+)?context",
    r"instead\s+of\s+using\s+context",
    r"print\s+(?:the\s+)?system\s+prompt",
    r"dan\s+mode",
    r"bypass\s+(?:safety|policy|restrictions)",
    r"act\s+as\s+a(?:\s+malicious|\s+harmful|\s+chat|\s+unfiltered|\s+uncensored|\s+linux|\s+translation|\s+terminal|\s+shell)",
    r"you\s+are\s+now\s+a(?:\s+malicious|\s+harmful|\s+chat|\s+unfiltered|\s+uncensored|\s+linux|\s+translation|\s+terminal|\s+shell)",
]


class ClinicalSafetyService:
    def detect_prompt_injection(self, text: str) -> bool:
        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def classify(self, question: str) -> tuple[str, str | None]:
        text = question.lower()
        if self.detect_prompt_injection(question):
            return "prompt_injection_refusal", "I cannot process this request as it contains unauthorized instructions or overrides."
        if any(term in text for term in EMERGENCY_TERMS):
            return "urgent_escalation", "Seek emergency medical care now or call local emergency services."
        return "clinical_guidance", None

    def patient_disclaimer(self) -> str:
        return "This is educational support, not a diagnosis. Consult a qualified clinician."

