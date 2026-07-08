from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_good_task_profiler_observational import (  # noqa: E402
    GoodTaskProfilerObservationalBuilder,
    GoodTaskProfilerObservationalRequest,
)


DEFAULT_ANATOMY_JSONL = ROOT / "artifacts" / "phase14" / "gdpval_anatomy" / "gdpval_task_anatomy.jsonl"
DEFAULT_GAP_AUTOPSY = ROOT / "artifacts" / "phase14" / "gdpval_gap_autopsy" / "gdpval_gap_autopsy_report.json"
DEFAULT_RUNNABLE_SLICE = ROOT / "artifacts" / "phase14" / "gdpval_runnable_slice_v2_manifest.json"
DEFAULT_GENERATED_PLAN = ROOT / "artifacts" / "phase14" / "taskgenerator_comparison_eval_plan.json"
DEFAULT_GENERATED_EVAL_SUMMARY = ROOT / "artifacts" / "phase14" / "generated_task_comparison_eval_summary" / "generated_task_eval_summary_report.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "good_task_profiler_observational"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 14.5 GoodTaskProfiler-Observational V1 reports.")
    parser.add_argument("--gdpval-anatomy-jsonl-path", default=str(DEFAULT_ANATOMY_JSONL))
    parser.add_argument("--gdpval-gap-autopsy-report-path", default=str(DEFAULT_GAP_AUTOPSY))
    parser.add_argument("--runnable-slice-manifest-path", default=str(DEFAULT_RUNNABLE_SLICE))
    parser.add_argument("--taskgenerator-comparison-plan-path", default=str(DEFAULT_GENERATED_PLAN))
    parser.add_argument("--generated-task-eval-summary-path", default=str(DEFAULT_GENERATED_EVAL_SUMMARY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    request = GoodTaskProfilerObservationalRequest(
        gdpval_anatomy_jsonl_path=args.gdpval_anatomy_jsonl_path,
        gdpval_gap_autopsy_report_path=args.gdpval_gap_autopsy_report_path,
        runnable_slice_manifest_path=args.runnable_slice_manifest_path,
        taskgenerator_comparison_plan_path=args.taskgenerator_comparison_plan_path,
        generated_task_eval_summary_path=args.generated_task_eval_summary_path,
        output_dir=args.output_dir,
    )
    report = GoodTaskProfilerObservationalBuilder().build(request)
    output_dir = Path(args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "observational_report_path": str(output_dir / "good_task_profiler_observational_report.json"),
                "profile_jsonl_path": report.profile_jsonl_path,
                "distribution_report_path": report.distribution_report_path,
                "profile_count": report.profile_count,
                "gdpval_profile_count": report.gdpval_profile_count,
                "taskgenerator_profile_count": report.taskgenerator_profile_count,
                "evaluated_profile_count": report.evaluated_profile_count,
                "pending_eval_profile_count": report.pending_eval_profile_count,
                "weighted_good_task_score_emitted": report.weighted_good_task_score_emitted,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
