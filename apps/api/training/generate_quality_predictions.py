import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def resolve_existing_path(value: str, *, api_root: Path, repo_root: Path) -> Path:
    raw = Path(value).expanduser()
    candidates = [
        raw,
        api_root / raw,
        repo_root / raw,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (api_root / raw).resolve() if not raw.is_absolute() else raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate predictions JSONL for clinical quality cases.")
    parser.add_argument("--cases", default="training/clinical_quality_cases.jsonl")
    parser.add_argument("--output", default="training/predictions.jsonl")
    parser.add_argument("--base-model", default="BioMistral/BioMistral-7B")
    parser.add_argument("--adapter-path", default="models/biomistral-medical")
    parser.add_argument("--max-input-tokens", type=int, default=2500)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--continue-on-error", action="store_true", help="Write failed prediction rows instead of stopping at the first model error.")
    args = parser.parse_args()

    api_root = Path(__file__).resolve().parents[1]
    repo_root = api_root.parents[1]
    cases_path = resolve_existing_path(args.cases, api_root=api_root, repo_root=repo_root)
    output_path = resolve_existing_path(args.output, api_root=api_root, repo_root=repo_root)
    adapter_path = resolve_existing_path(args.adapter_path, api_root=api_root, repo_root=repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evaluator = Path(__file__).with_name("evaluate_adapter.py")
    cases = load_jsonl(cases_path)
    if not adapter_path.exists():
        raise SystemExit(
            f"Adapter path not found: {adapter_path}\n"
            "Pass --adapter-path models/biomistral-medical when running from apps/api, "
            "or --adapter-path apps/api/models/biomistral-medical when running from the repo root."
        )

    with output_path.open("w", encoding="utf-8") as handle:
        for case in cases:
            prompt = f"{case['role'].capitalize()} role: {case['question']}"
            command = [
                sys.executable,
                str(evaluator),
                "--base-model",
                args.base_model,
                "--adapter-path",
                str(adapter_path),
                "--max-input-tokens",
                str(args.max_input_tokens),
                "--max-new-tokens",
                str(args.max_new_tokens),
                "--prompt",
                prompt,
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                message = (
                    f"Prediction failed for {case['id']} with exit code {completed.returncode}\n"
                    f"Command: {' '.join(command)}\n"
                    f"STDOUT:\n{completed.stdout.strip() or '[empty]'}\n"
                    f"STDERR:\n{completed.stderr.strip() or '[empty]'}"
                )
                if not args.continue_on_error:
                    raise SystemExit(message)
                print(message, file=sys.stderr)
                handle.write(json.dumps({"id": case["id"], "answer": "", "error": message}, ensure_ascii=False) + "\n")
                handle.flush()
                continue
            answer = completed.stdout.strip()
            handle.write(json.dumps({"id": case["id"], "answer": answer}, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"Wrote prediction for {case['id']}")

    print(f"Predictions saved to {output_path}")


if __name__ == "__main__":
    main()
