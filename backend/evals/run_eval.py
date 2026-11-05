"""Run the analyzer on the labelled sample agreements and report quality.

    LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=... python evals/run_eval.py

Metrics
- category recall: expected red-flag categories that were found
- false alarms: categories flagged that the label says must NOT be flagged
- risk level accuracy
- grounding: share of AI flags whose quote was found in the document (the rest are discarded)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.analyzer import Analyzer  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm import OpenAICompatibleLLM  # noqa: E402


def score(results: dict[str, dict], labels: dict[str, dict]) -> dict:
    exp_total = found = false_alarms = level_ok = kept = discarded = 0
    for name, lab in labels.items():
        r = results[name]
        cats = {f["category"] for f in r["flags"]}
        exp_total += len(lab["expected"])
        found += len(set(lab["expected"]) & cats)
        false_alarms += len(set(lab["must_not"]) & cats)
        level_ok += r["risk_level"] == lab["expected_level"]
        kept += sum(f["source"] == "ai" for f in r["flags"])
        discarded += r["discarded_flags"]
    return {
        "category_recall": found / exp_total if exp_total else None,
        "false_alarms": false_alarms,
        "risk_level_accuracy": level_ok / len(labels),
        "grounded_ai_flag_rate": kept / (kept + discarded) if kept + discarded else None,
    }


def main() -> None:
    s = Settings.from_env()
    if not s.llm_api_key:
        sys.exit("Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL first.")
    analyzer = Analyzer(OpenAICompatibleLLM(s.llm_api_key, s.llm_base_url, s.llm_model, s.llm_timeout_s), s)
    labels = json.loads((ROOT / "samples/labels.json").read_text())
    results = {}
    for name in labels:
        a = analyzer.analyze_pdf((ROOT / f"samples/{name}.pdf").read_bytes(), f"{name}.pdf")
        results[name] = a.model_dump(mode="json")
        cats = sorted({f.category for f in a.flags})
        print(f"{name}: score {a.risk_score} ({a.risk_level}), flags {cats}, discarded {a.discarded_flags}")
    m = score(results, labels)
    print(json.dumps(m, indent=2))
    (ROOT / "evals/results.json").write_text(json.dumps({"model": s.llm_model, "metrics": m}, indent=2))


if __name__ == "__main__":
    main()
