from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_gap_autopsy import (  # noqa: E402
    GDPValGapAutopsyBuilder,
    GDPValGapAutopsyRequest,
)


DEFAULT_CLEAN_BASELINE = ROOT / "artifacts" / "phase14" / "gdpval_clean_baseline" / "gdpval_clean_baseline_report.json"
DEFAULT_ANATOMY_JSONL = ROOT / "artifacts" / "phase14" / "gdpval_anatomy" / "gdpval_task_anatomy.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "gdpval_gap_autopsy"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GDPVal clean-pair gap autopsy and hypothesis ledger reports.")
    parser.add_argument("--clean-baseline-path", default=str(DEFAULT_CLEAN_BASELINE))
    parser.add_argument("--anatomy-jsonl-path", default=str(DEFAULT_ANATOMY_JSONL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--task-limit", type=int, default=0)
    parser.add_argument("--task-id", action="append", default=None)
    parser.add_argument("--strong-model", default=None)
    parser.add_argument("--weak-model", default=None)
    args = parser.parse_args()

    request = GDPValGapAutopsyRequest(
        clean_baseline_path=args.clean_baseline_path,
        anatomy_jsonl_path=args.anatomy_jsonl_path,
        output_dir=args.output_dir,
        task_limit=args.task_limit,
        task_ids=args.task_id or [],
        strong_model=args.strong_model,
        weak_model=args.weak_model,
    )
    report = GDPValGapAutopsyBuilder().build(request)
    output_dir = Path(args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "gap_autopsy_report_path": str(output_dir / "gdpval_gap_autopsy_report.json"),
                "hypothesis_ledger_path": report.hypothesis_ledger_path,
                "case_autopsy_dir": report.case_autopsy_dir,
                "task_count": report.task_count,
                "usable_task_count": report.usable_task_count,
                "gap_band_counts": report.gap_band_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
