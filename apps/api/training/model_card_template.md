# MedRAG Fine-Tuned Adapter Model Card

## Model

- Base model:
- Adapter name:
- Adapter URI:
- Prompt version:
- Training run ID:
- Approval status:

## Intended Use

This adapter is intended for MedRAG India workflows where retrieved guideline or verified patient context is provided in the prompt. It is not intended to answer medical questions without RAG context and safety checks.

## Training Data

- Dataset URI:
- Dataset SHA-256:
- Data source licensing:
- PHI de-identification method:
- Language coverage:

## Method

- Method: LoRA/QLoRA supervised fine-tuning
- Target modules:
- Epochs:
- Learning rate:
- Batch size:
- Gradient accumulation:

## Evaluation

- Clinical safety red-flag pass rate:
- Citation adherence:
- Refusal correctness:
- Hallucination rate:
- Doctor review notes:

## Known Limitations

- Must not replace clinician judgement.
- Must be used with retrieval and safety graph.
- Must be re-evaluated after dataset, prompt, base model, or adapter changes.

