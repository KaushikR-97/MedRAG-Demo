from dataclasses import dataclass


DRUG_INTERACTIONS = {
    ("sildenafil", "nitrate"): ("contraindicated", "Risk of severe hypotension."),
    ("warfarin", "aspirin"): ("major", "Increased bleeding risk."),
    ("tramadol", "ssri"): ("major", "Risk of serotonin syndrome."),
    ("metformin", "furosemide"): ("moderate", "Monitor renal function and lactic acidosis risk."),
    ("ashwagandha", "sedative"): ("moderate", "Ashwagandha may enhance the sedative effects of CNS depressants."),
    ("turmeric", "warfarin"): ("major", "Turmeric antiplatelet activity can significantly increase bleeding risk when combined with Warfarin."),
    ("turmeric", "aspirin"): ("major", "Turmeric has antiplatelet activity; monitor bleeding when combined with Aspirin."),
    ("neem", "metformin"): ("moderate", "Neem may lower blood glucose; monitor closely for risk of hypoglycemia when combined with Metformin."),
    ("neem", "insulin"): ("moderate", "Neem has blood sugar lowering properties; monitor for insulin dosage adjustment needs."),
    ("tulsi", "anticoagulant"): ("moderate", "Tulsi may slow blood clotting; monitor bleeding risks if combined with anticoagulants."),
    ("tulsi", "aspirin"): ("moderate", "Tulsi has mild antiplatelet effects; watch for bruising or bleeding if taken with Aspirin."),
}


@dataclass(frozen=True)
class InteractionResult:
    medicine_a: str
    medicine_b: str
    severity: str
    message: str


class ClinicalToolsService:
    def check_interactions(self, medicines: list[str]) -> list[InteractionResult]:
        normalized = [medicine.lower().strip() for medicine in medicines]
        results: list[InteractionResult] = []
        for i, med_a in enumerate(normalized):
            for med_b in normalized[i + 1 :]:
                for (a, b), (severity, message) in DRUG_INTERACTIONS.items():
                    if (a in med_a and b in med_b) or (b in med_a and a in med_b):
                        results.append(InteractionResult(med_a, med_b, severity, message))
        return results

    def interpret_lab(self, *, test_name: str, value: float, unit: str = "") -> str:
        name = test_name.lower()
        if name in {"hba1c", "hbA1c".lower()}:
            if value >= 6.5:
                return "HbA1c is in diabetic range; clinician follow-up is recommended."
            if value >= 5.7:
                return "HbA1c is in prediabetes range; lifestyle and clinician review are recommended."
            return "HbA1c is below prediabetes threshold."
        if name in {"systolic_bp", "bp_systolic"}:
            return "High systolic BP; repeat measurement and clinician review are recommended." if value >= 140 else "Systolic BP is not high by this threshold."
        return "No local reference range configured for this test yet."

    def symptom_triage(self, *, symptoms: str, severity: int) -> str:
        text = symptoms.lower()
        if severity >= 8 or any(term in text for term in ["chest pain", "breathing", "unconscious", "stroke"]):
            return "urgent: seek emergency care or contact local emergency services."
        if severity >= 5:
            return "soon: book clinician consultation within 24-48 hours."
        return "routine: monitor symptoms and consult a clinician if persistent or worsening."

    def health_score(self, *, completed_checks: int, risk_factors: int) -> int:
        return max(0, min(100, 50 + completed_checks * 7 - risk_factors * 8))

    def mental_health_risk(self, *, score: int, screening_type: str) -> str:
        if score >= 20:
            return "severe"
        if score >= 15:
            return "moderately_severe"
        if score >= 10:
            return "moderate"
        if score >= 5:
            return "mild"
        return "minimal"

    def check_soap_note_diff(self, *, visit_summary: str, subjective: str, plan: str) -> list[str]:
        warnings: list[str] = []
        summary_lower = visit_summary.lower()
        sub_lower = subjective.lower()
        plan_lower = plan.lower()
        
        if "diabetes" in summary_lower or "metformin" in summary_lower or "insulin" in summary_lower:
            if "hba1c" not in summary_lower and "hba1c" not in sub_lower:
                warnings.append(
                    "Clinical Guideline Gap: Diagnosis or treatment of Diabetes mentioned, but no recent "
                    "HbA1c level review is documented in the subjective text. Recommend verifying HbA1c values."
                )
                
        if "hypertension" in summary_lower or "bp" in summary_lower or "blood pressure" in summary_lower:
            if "systolic" not in summary_lower and "diastolic" not in summary_lower and "bp monitoring" not in plan_lower:
                warnings.append(
                    "Clinical Guideline Gap: Hypertension or BP concerns mentioned, but no regular "
                    "blood pressure monitoring check-in has been scheduled in the treatment plan."
                )
                
        if "antibiotic" in plan_lower or "amoxicillin" in plan_lower or "azithromycin" in plan_lower:
            if "duration" not in plan_lower and "days" not in plan_lower:
                warnings.append(
                    "Clinical Safety Warning: Antibiotic prescription planned, but duration of therapy (number of days) "
                    "is not clearly specified in the plan."
                )
        return warnings

