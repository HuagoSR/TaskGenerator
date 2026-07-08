from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_clean_baseline import (  # noqa: E402
    GDPValCleanBaselineBuilder,
    GDPValCleanBaselineRequest,
)
from task_generator.v3_gdpval_rw_task_eval_adapter import DEFAULT_MODELS  # noqa: E402


DEFAULT_SUBSET_MANIFEST = ROOT / "artifacts" / "phase14" / "gdpval_subset" / "gdpval_finance_audit_subset_manifest.json"
DEFAULT_SINGLE_CASE_RUNS = ROOT / "artifacts" / "phase14" / "gdpval_single_case_runs"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "gdpval_clean_baseline"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the clean Phase 14.3 GDPVal single-case baseline summary.")
    parser.add_argument("--subset-manifest-path", default=str(DEFAULT_SUBSET_MANIFEST))
    parser.add_argument("--single-case-runs-dir", default=str(DEFAULT_SINGLE_CASE_RUNS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--model", action="append", default=None)
    parser.add_argument("--task-limit", type=int, default=5)
    parser.add_argument("--task-id", action="append", default=None)
    args = parser.parse_args()

    request = GDPValCleanBaselineRequest(
        subset_manifest_path=args.subset_manifest_path,
        single_case_runs_dir=args.single_case_runs_dir,
        output_dir=args.output_dir,
        models=args.model if args.model else list(DEFAULT_MODELS),
        task_limit=args.task_limit,
        task_ids=args.task_id or [],
    )
    report = GDPValCleanBaselineBuilder().build(request)
    output_dir = Path(args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "clean_baseline_report_path": str(output_dir / "gdpval_clean_baseline_report.json"),
                "clean_gap_profile_path": str(output_dir / "gdpval_clean_gap_profile.json"),
                "clean_failure_report_path": str(output_dir / "gdpval_clean_failure_report.json"),
                "task_count": report.task_count,
                "usable_task_count": report.usable_task_count,
                "needs_model_rerun_count": report.needs_model_rerun_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
