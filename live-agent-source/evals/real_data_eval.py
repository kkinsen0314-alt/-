"""Run deterministic tool evaluation on real CSV/Excel files."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import channel_analysis, funnel_analysis, inviter_analysis


def evaluate_file(file_path: str) -> dict:
    started = time.perf_counter()
    record = {"file_path": file_path}
    try:
        funnel = funnel_analysis(file_path)
        inviter = inviter_analysis(file_path, top_n=3)
        channel = channel_analysis(file_path, top_n=3)
        record.update({
            "status": "passed",
            "data_source": funnel.get("data_source"),
            "data_size": funnel.get("data_size"),
            "funnel": funnel.get("funnel"),
            "thresholds": funnel.get("thresholds"),
            "top_inviters": inviter.get("items", []),
            "top_channels": channel.get("items", []),
        })
    except Exception as exc:
        record.update({"status": "failed", "error": str(exc)})
    record["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="CSV/Excel paths")
    parser.add_argument("--output", default="evals/real_data_eval_latest.json")
    args = parser.parse_args()
    results = [evaluate_file(path) for path in args.files]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    passed = sum(item["status"] == "passed" for item in results)
    print(json.dumps({"total": len(results), "passed": passed, "failed": len(results) - passed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
