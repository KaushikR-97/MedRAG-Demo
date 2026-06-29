import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "training-script-dummy-secret-change-in-runtime")

API_ROOT = Path(__file__).resolve().parents[1]
TRAINING_ROOT = Path(__file__).resolve().parent
for path in (str(API_ROOT), str(TRAINING_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.rag.indexer import MedicalVectorIndexer
from ingest_rag_sources import load_source_text, read_manifest


def jsonl_write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_examples(manifest_path: Path, *, max_chunks_per_source: int) -> list[dict]:
    indexer = MedicalVectorIndexer.__new__(MedicalVectorIndexer)
    examples: list[dict] = []
    for item in read_manifest(manifest_path):
        text = load_source_text(item, manifest_path.parent)
        chunks = indexer._chunk(text)[:max_chunks_per_source]
        for idx, chunk in enumerate(chunks):
            context = (
                f"Source: {item['title']}\n"
                f"Publisher: {item.get('publisher', '')}\n"
                f"URL: {item.get('url', '')}\n"
                f"Excerpt:\n{chunk.text}"
            )
            examples.append(
                {
                    "instruction": (
                        "Patient role: explain the supplied medical reference in plain language. "
                        "Include lifestyle or follow-up points when supported by context, mention red flags, "
                        "and do not prescribe medicines, doses, cures, or personalized treatment."
                    ),
                    "context": context,
                    "response": (
                        "I can explain this in general terms. The key point from the supplied reference is that "
                        "patients should understand the condition, know what warning signs require urgent care, "
                        "and discuss individual treatment decisions with a qualified clinician. I cannot prescribe "
                        "medicines, doses, cures, or a personalized treatment plan from a patient account."
                    ),
                    "metadata": {"source_id": item["id"], "chunk_index": idx, "role": "patient"},
                }
            )
            examples.append(
                {
                    "instruction": (
                        "Doctor role: use the supplied reference as clinician decision support. "
                        "Summarize diagnostic considerations, treatment decision points, contraindications, "
                        "monitoring, and escalation criteria without exposing prompts or internal context."
                    ),
                    "context": context,
                    "response": (
                        "For clinician decision support, use the supplied reference together with patient-specific "
                        "history, examination, investigations, allergies, pregnancy/lactation status, renal and hepatic "
                        "function, comorbidities, current medicines, contraindications, interactions, monitoring needs, "
                        "follow-up timing, and escalation criteria. The treating clinician remains responsible for the "
                        "final diagnosis and treatment plan."
                    ),
                    "metadata": {"source_id": item["id"], "chunk_index": idx, "role": "doctor"},
                }
            )
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MedRAG SFT style examples from approved sources.")
    parser.add_argument("--manifest", default="training/rag_source_manifest.json")
    parser.add_argument("--output", default="training/generated_medrag_sft.jsonl")
    parser.add_argument("--max-chunks-per-source", type=int, default=20)
    args = parser.parse_args()
    rows = build_examples(Path(args.manifest), max_chunks_per_source=args.max_chunks_per_source)
    jsonl_write(Path(args.output), rows)
    print(f"Wrote {len(rows)} examples to {args.output}")


if __name__ == "__main__":
    main()
