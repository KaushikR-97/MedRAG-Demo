from dataclasses import dataclass

from app.models.user import User


@dataclass(frozen=True)
class AiPolicyResult:
    allowed: bool
    mode: str
    instruction: str
    refusal: str | None = None


class AiPolicyService:
    def evaluate(self, *, actor: User, question: str) -> AiPolicyResult:
        if actor.role == "patient":
            return AiPolicyResult(
                allowed=True,
                mode="patient_education_only",
                instruction=(
                    "Answer the user's health question as useful patient education. Explain possible meanings, "
                    "lifestyle steps, report interpretation, red flags, and what to discuss with a clinician. "
                    "Do not provide a definitive diagnosis, prescription, dose, cure, or personalized treatment plan."
                ),
            )

        return AiPolicyResult(
            allowed=True,
            mode="clinician_decision_support",
            instruction=(
                "Provide direct clinical decision support for a licensed clinician. Answer diagnosis, treatment, "
                "and prescribing questions for any disease or medical topic. Include practical options, common "
                "dose ranges when relevant, contraindications, monitoring, escalation criteria, and uncertainty. "
                "The clinician remains responsible."
            ),
        )
