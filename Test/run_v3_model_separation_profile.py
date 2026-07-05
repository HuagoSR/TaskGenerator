import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_model_separation_profile import ModelSeparationProfileBuilder  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_EVAL_SUMMARY = SCRATCH / "rw_task_eval_summary_smoke" / "pipeline_b_eval_summary_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "model_separation_profile_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a report-only model separation profile from existing eval summary artifacts."
    )
    parser.add_argument(
        "--eval-summary-report",
        type=Path,
        action="append",
        default=[],
        help="Path to a pipeline_b_eval_summary_report.json file. Can be repeated.",
    )
    parser.add_argument(
        "--eval-summary-dir",
        type=Path,
        default=None,
        help="Optional directory to recursively search for pipeline_b_eval_summary_report.json.",
    )
    parser.add_argument("--eval-feedback-report", type=Path, default=None)
    parser.add_argument("--task-verifier-report", type=Path, default=None)
    parser.add_argument("--global-validity-report", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    summary_reports = args.eval_summary_report or [DEFAULT_EVAL_SUMMARY]
    builder = ModelSeparationProfileBuilder()
    report = builder.build(
        eval_summary_report_paths=summary_reports,
        eval_summary_dir=args.eval_summary_dir,
        eval_feedback_report_path=args.eval_feedback_report,
        task_verifier_report_path=args.task_verifier_report,
        global_validity_report_path=args.global_validity_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "model_separation_profile_path": str(args.output_dir / "model_separation_profile.json"),
                "case_id": report.case_id,
                "task_id": report.task_id,
                "evaluation_status": report.evaluation_status,
                "eligibility_status": report.eligibility_status,
                "recommendation": report.recommendation,
                "usable_summary_count": report.diagnostics.usable_summary_count,
                "mixed_case_input": report.diagnostics.mixed_case_input,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
