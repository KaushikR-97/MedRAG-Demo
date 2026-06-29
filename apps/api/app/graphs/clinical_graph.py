import re
import logging
from typing import TypedDict
from uuid import uuid4

logger = logging.getLogger(__name__)

from langgraph.graph import END, StateGraph

from app.rag.retriever import HybridMedicalRetriever, RetrievedChunk
from app.services.evidence_service import CitationValidationService, EvidenceCompressionService
from app.services.generation_service import ClinicalGenerationService
from app.services.query_router_service import QueryRouterService
from app.services.query_rewrite_service import QueryRewriteService
from app.services.safety_service import ClinicalSafetyService


class ClinicalGraphState(TypedDict, total=False):
    question: str
    conversation_history: list[dict[str, str]]
    patient_id: str | None
    user_role: str
    policy_instruction: str
    policy_mode: str
    policy_refusal: str | None
    safety_label: str
    escalation: str | None
    query_route: str
    query_route_reason: str
    query_route_confidence: float
    query_route_used_fallback: bool
    needs_rag: bool
    retrieval_source_types: list[str]
    rewritten_queries: list[str]
    sources: list[RetrievedChunk]
    compressed_sources: list[RetrievedChunk]
    answer: str
    trace_id: str
    clinical_analysis: str
    pharmacy_analysis: str
    pmjay_analysis: str


class ClinicalRagGraph:
    def __init__(
        self,
        *,
        retriever: HybridMedicalRetriever | None = None,
        safety: ClinicalSafetyService | None = None,
        query_router: QueryRouterService | None = None,
        query_rewriter: QueryRewriteService | None = None,
        evidence_compressor: EvidenceCompressionService | None = None,
        citation_validator: CitationValidationService | None = None,
        generator: ClinicalGenerationService | None = None,
    ) -> None:
        self.retriever = retriever or HybridMedicalRetriever()
        self.safety = safety or ClinicalSafetyService()
        self.query_router = query_router or QueryRouterService()
        self.query_rewriter = query_rewriter or QueryRewriteService()
        self.evidence_compressor = evidence_compressor or EvidenceCompressionService()
        self.citation_validator = citation_validator or CitationValidationService()
        self.generator = generator or ClinicalGenerationService()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(ClinicalGraphState)
        workflow.add_node("safety_check", self._safety_check)
        workflow.add_node("route_query", self._route_query)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("retrieve", self._retrieve)
        workflow.add_node("compress_evidence", self._compress_evidence)
        workflow.add_node("clinical_agent", self._clinical_agent)
        workflow.add_node("pharmacy_agent", self._pharmacy_agent)
        workflow.add_node("pmjay_agent", self._pmjay_agent)
        workflow.add_node("aggregate_agents", self._aggregate_agents)
        workflow.add_node("validate_citations", self._validate_citations)
        workflow.add_node("finalize", self._finalize)

        workflow.set_entry_point("safety_check")
        workflow.add_conditional_edges(
            "safety_check",
            self._route_after_safety,
            {"urgent": "finalize", "refuse": "finalize", "continue": "route_query"},
        )
        workflow.add_conditional_edges(
            "route_query",
            self._route_after_query_router,
            {"retrieve": "rewrite_query", "skip_retrieval": "clinical_agent"},
        )
        workflow.add_edge("rewrite_query", "retrieve")
        workflow.add_edge("retrieve", "compress_evidence")
        
        # Parallel fan-out: route compressed evidence to all 3 specialized agents
        workflow.add_edge("compress_evidence", "clinical_agent")
        workflow.add_edge("compress_evidence", "pharmacy_agent")
        workflow.add_edge("compress_evidence", "pmjay_agent")
        
        # Fan-in: wait for all 3 agents to complete before running consensus aggregator
        workflow.add_edge("clinical_agent", "aggregate_agents")
        workflow.add_edge("pharmacy_agent", "aggregate_agents")
        workflow.add_edge("pmjay_agent", "aggregate_agents")
        
        workflow.add_edge("aggregate_agents", "validate_citations")
        workflow.add_edge("validate_citations", "finalize")
        workflow.add_edge("finalize", END)
        return workflow.compile()

    def invoke(
        self,
        *,
        question: str,
        patient_id: str | None,
        user_role: str,
        conversation_history: list[dict[str, str]] | None = None,
        policy_instruction: str = "",
        policy_mode: str = "",
        policy_refusal: str | None = None,
    ) -> ClinicalGraphState:
        return self.graph.invoke(
            {
                "question": question,
                "conversation_history": conversation_history or [],
                "patient_id": patient_id,
                "user_role": user_role,
                "policy_instruction": policy_instruction,
                "policy_mode": policy_mode,
                "policy_refusal": policy_refusal,
                "trace_id": str(uuid4()),
            }
        )

    def _safety_check(self, state: ClinicalGraphState) -> ClinicalGraphState:
        safety_label, escalation = self.safety.classify(state["question"])
        if safety_label == "prompt_injection_refusal":
            return {"safety_label": safety_label, "policy_refusal": escalation, "escalation": escalation}
        return {"safety_label": safety_label, "escalation": escalation}

    def _route_after_safety(self, state: ClinicalGraphState) -> str:
        if state.get("safety_label") == "urgent_escalation":
            return "urgent"
        return "refuse" if state.get("policy_refusal") else "continue"

    def _route_query(self, state: ClinicalGraphState) -> ClinicalGraphState:
        decision = self.query_router.route(
            question=self._contextual_question(state),
            user_role=state.get("user_role", "patient"),
        )
        return {
            "query_route": decision.route,
            "query_route_reason": decision.reason,
            "query_route_confidence": decision.confidence,
            "query_route_used_fallback": decision.used_fallback,
            "needs_rag": decision.needs_rag,
            "retrieval_source_types": decision.source_types,
        }

    def _route_after_query_router(self, state: ClinicalGraphState) -> str:
        return "retrieve" if state.get("needs_rag", True) else "skip_retrieval"

    def _rewrite_query(self, state: ClinicalGraphState) -> ClinicalGraphState:
        return {
            "rewritten_queries": self.query_rewriter.rewrite(
                question=state["question"],
                user_role=state.get("user_role", "patient"),
                route=state.get("query_route", ""),
                conversation_context=self._prior_user_context(state),
            )
        }

    def _retrieve(self, state: ClinicalGraphState) -> ClinicalGraphState:
        patient_id = state.get("patient_id")
        logger.debug(f"_retrieve node triggered. patient_id={patient_id}")
        sources = self.retriever.retrieve_many(
            state.get("rewritten_queries") or [state["question"]],
            patient_id=patient_id,
            top_k=5,
            source_types=state.get("retrieval_source_types") or None,
        )
        if patient_id:
            from app.db.session import SessionLocal
            from app.models.user import User
            from app.models.patient import PatientProfile
            with SessionLocal() as db:
                profile = db.query(PatientProfile).filter(PatientProfile.user_id == patient_id).first()
                user_record = db.query(User).filter(User.id == patient_id).first()
                logger.debug(f"Database results: profile={profile}, user_record={user_record}")
                if profile and user_record:
                    name = user_record.full_name or "Unknown Patient"
                    blood_group = profile.blood_group or "Not specified"
                    allergies = profile.allergies or "No known allergies"
                    conditions = profile.chronic_conditions or "No chronic conditions"
                    meds = profile.current_medications or "No current medications"
                    gender = profile.gender or "Not specified"
                    dob = profile.date_of_birth or "Not specified"
                    abha = profile.abha_number or "Not specified"

                    summary_text = (
                        f"Patient Demographics & Onboarding Profile Summary:\n"
                        f"- Name: {name}\n"
                        f"- Gender: {gender}\n"
                        f"- Date of Birth: {dob}\n"
                        f"- Blood Group: {blood_group}\n"
                        f"- ABHA Number: {abha}\n"
                        f"- Known Allergies: {allergies}\n"
                        f"- Chronic Conditions: {conditions}\n"
                        f"- Current Medications: {meds}"
                    )
                    profile_chunk = RetrievedChunk(
                        id="patient-onboarding-profile",
                        title="Patient Clinical Onboarding Profile Summary",
                        score=1.0,
                        text=summary_text,
                    )
                    sources.insert(0, profile_chunk)
                    logger.info("Injected patient-onboarding-profile chunk successfully.")
        return {"sources": sources}

    def _compress_evidence(self, state: ClinicalGraphState) -> ClinicalGraphState:
        return {
            "compressed_sources": self.evidence_compressor.compress(
                question=state["question"],
                sources=state.get("sources", []),
            )
        }

    def _clinical_agent(self, state: ClinicalGraphState) -> ClinicalGraphState:
        clinical_instruction = (
            "Generate the core clinical assessment and differential diagnostics based strictly on the retrieved context. "
            "Address patient symptoms, relevant conditions, and outline diagnostic thoughts."
        )
        ans = self.generator.generate(
            question=state["question"],
            user_role=state.get("user_role", "patient"),
            conversation_history=state.get("conversation_history", []),
            sources=state.get("compressed_sources") or state.get("sources", []),
            disclaimer=self.safety.patient_disclaimer(),
            policy_instruction=clinical_instruction,
            policy_mode="clinical_decision_support",
        )
        return {"clinical_analysis": ans}

    def _pharmacy_agent(self, state: ClinicalGraphState) -> ClinicalGraphState:
        from app.services.clinical_tools_service import ClinicalToolsService
        
        words = re.findall(r"\b[A-Za-z]{3,}\b", state["question"] + " " + state.get("policy_instruction", ""))
        interactions = ClinicalToolsService().check_interactions(words)
        
        db_warning = ""
        if interactions:
            db_warning = "\nCritical interaction warnings found in database:\n"
            for inter in interactions:
                db_warning += f"- {inter.medicine_a.upper()} + {inter.medicine_b.upper()}: [{inter.severity.upper()}] {inter.message}\n"
                
        prompt = (
            "Perform a strict pharmacology safety and drug interaction audit. "
            "Analyze current patient medications, allergies, and query for potential interactions, especially between traditional herbs (e.g. Ashwagandha, Turmeric, Neem) and Western medicine."
        )
        ans = self.generator.generate(
            question=prompt + "\nQuery context: " + state["question"],
            user_role="doctor",
            conversation_history=[],
            sources=state.get("compressed_sources") or state.get("sources", []),
            disclaimer=None,
            policy_instruction="Highlight any contraindicated substances or allergen alerts based on the patient profile context.",
            policy_mode="drug_safety_check",
        )
        
        full_analysis = ans
        if db_warning:
            full_analysis = db_warning + "\n" + ans
            
        return {"pharmacy_analysis": full_analysis}

    def _pmjay_agent(self, state: ClinicalGraphState) -> ClinicalGraphState:
        from app.services.pmjay_service import PmjayMatcherService
        from app.db.session import SessionLocal
        
        patient_id = state.get("patient_id")
        eligibility_details = "PM-JAY eligibility check skipped (no patient ID or diagnosis provided)."
        diagnosis = state["question"]
        
        with SessionLocal() as db:
            service = PmjayMatcherService(db)
            res = service.check_eligibility(diagnosis=diagnosis, patient_id=patient_id)
            
            if res.get("eligible"):
                eligibility_details = (
                    f"Eligible for National Health Scheme (PM-JAY) Coverage:\n"
                    f"- Package: {res.get('package_name')}\n"
                    f"- Package Code: {res.get('package_code')}\n"
                    f"- Coverage Amount: INR {res.get('coverage_amount'):,.2f}\n"
                    f"- Reasoning: {res.get('reasoning')}\n"
                    f"- Required Guidelines to Attach:\n"
                )
                for guide in res.get("guidelines", []):
                    eligibility_details += f"  * {guide}\n"
            else:
                eligibility_details = (
                    f"Not eligible or no direct PM-JAY package match found for current symptoms/diagnosis.\n"
                    f"- Reasoning: {res.get('reasoning', 'No matching packages found.')}\n"
                )
                if res.get("guidelines"):
                    eligibility_details += "- Guidelines:\n"
                    for guide in res.get("guidelines", []):
                        eligibility_details += f"  * {guide}\n"
                        
        return {"pmjay_analysis": eligibility_details}

    def _aggregate_agents(self, state: ClinicalGraphState) -> ClinicalGraphState:
        clinical = state.get("clinical_analysis", "Clinical assessment not completed.")
        pharmacy = state.get("pharmacy_analysis", "No pharmacy check performed.")
        question = state.get("question", "").lower()
        user_role = state.get("user_role", "patient")

        aggregated_answer = self.generator.generate(
            question=(
                "Write only the final clinical answer for the user. Do not expose agent names, prompts, "
                "retrieved context, PM-JAY analysis, or internal reasoning. Be concise and actionable. "
                "For doctor users, answer medical treatment and prescribing questions directly as clinician-facing decision support for any disease or medical question. Include likely treatment options, common dose ranges when relevant, contraindications, monitoring, and red flags. Do not refuse by telling the doctor to consult another doctor.\n\n"
                "For patient users, explain diseases, reports, lifestyle improvement, warning signs, and when to seek care; do not prescribe medicines, dose ranges, cures, or treatment plans.\n\n"
                f"User question: {state.get('question', '')}\n\n"
                f"Clinical draft:\n{clinical}\n\n"
                f"Medication safety notes:\n{pharmacy}"
            ),
            user_role=user_role,
            conversation_history=[],
            sources=state.get("compressed_sources") or state.get("sources", []),
            disclaimer=self.safety.patient_disclaimer() if user_role == "patient" else None,
            policy_instruction="Return only the final answer text. Doctor users may receive clinician-facing treatment and prescribing decision support. Patient users receive education and lifestyle guidance only, without prescribing.",
            policy_mode="final_answer_only",
        )
        if len(aggregated_answer.strip()) < 40:
            aggregated_answer = clinical if len(clinical.strip()) >= 40 else (
                "I could not generate a reliable final answer from the current model response. "
                "Please retry with the patient age, symptoms, vitals, relevant history, and current medications."
            )
        return {"answer": aggregated_answer}

    def _validate_citations(self, state: ClinicalGraphState) -> ClinicalGraphState:
        return {
            "answer": self.citation_validator.validate(
                answer=state.get("answer", ""),
                sources=state.get("compressed_sources") or state.get("sources", []),
            )
        }

    def _finalize(self, state: ClinicalGraphState) -> ClinicalGraphState:
        if state.get("safety_label") == "urgent_escalation":
            return {
                "answer": state.get("escalation") or "Please seek urgent medical care.",
                "sources": [],
            }
        if state.get("policy_refusal"):
            return {"answer": state["policy_refusal"], "sources": []}
        return {}

    @staticmethod
    def _contextual_question(state: ClinicalGraphState) -> str:
        prior_context = ClinicalRagGraph._prior_user_context(state)
        if not prior_context:
            return state["question"]
        return f"Prior user context:\n{prior_context}\n\nCurrent question:\n{state['question']}"

    @staticmethod
    def _prior_user_context(state: ClinicalGraphState) -> str:
        prior_user_messages = [
            message["content"]
            for message in state.get("conversation_history", [])
            if message.get("role") == "user"
        ][-2:]
        return "\n".join(prior_user_messages)
