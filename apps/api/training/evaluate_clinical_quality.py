import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def evaluate_case(case: dict, answer: str) -> dict:
    answer_l = answer.lower()
    missing = [item for item in case.get("must_include", []) if item.lower() not in answer_l]
    forbidden = [item for item in case.get("must_not_include", []) if item.lower() in answer_l]
    return {
        "id": case["id"],
        "passed": not missing and not forbidden,
        "missing": missing,
        "forbidden": forbidden,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate saved clinical AI answers against role-specific quality gates. "
            "Predictions JSONL must contain id and answer fields."
        )
    )
    parser.add_argument("--cases", default="training/clinical_quality_cases.jsonl")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--min-pass-rate", type=float, default=0.9)
    args = parser.parse_args()

    cases = {row["id"]: row for row in load_jsonl(Path(args.cases))}
    predictions = load_jsonl(Path(args.predictions))
    results = []
    for pred in predictions:
        case = cases.get(pred["id"])
        if not case:
            results.append({"id": pred["id"], "passed": False, "missing": ["known case id"], "forbidden": []})
            continue
        results.append(evaluate_case(case, pred.get("answer", "")))

    passed = sum(1 for row in results if row["passed"])
    total = len(results)
    pass_rate = passed / total if total else 0.0
    print(json.dumps({"passed": passed, "total": total, "pass_rate": pass_rate, "results": results}, indent=2))
    if pass_rate < args.min_pass_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
