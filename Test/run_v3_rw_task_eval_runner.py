import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_rw_task_eval_runner import RwTaskEvalRunner  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_PREP_REPORT = SCRATCH / "rw_task_eval_input_smoke" / "rw_task_eval_prep_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "rw_task_eval_run_dry_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or dry-run a guarded V3 rw-task evaluation smoke from an eval prep report."
    )
    parser.add_argument("--prep-report", type=Path, default=DEFAULT_PREP_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--run-eval",
        action="store_true",
        help="Actually execute prepared rw-task commands. Default is dry-run metadata only.",
    )
    parser.add_argument(
        "--allow-draft-eval",
        action="store_true",
        help="Required with --run-eval when the prep report is draft_inspection_only.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=int,
        default=0,
        help="Optional per-command timeout. 0 means no timeout.",
    )
    parser.add_argument(
        "--grader-model",
        default=None,
        help="Optional grader model for grade_deliverables; defaults to the evaluated model.",
    )
    args = parser.parse_args()

    runner = RwTaskEvalRunner()
    report = runner.run(
        prep_report_path=args.prep_report,
        output_dir=args.output_dir,
        run_eval=args.run_eval,
        allow_draft_eval=args.allow_draft_eval,
        command_timeout_seconds=args.command_timeout_seconds,
        grader_model=args.grader_model,
    )
    print(
        json.dumps(
            {
                "case_id": report.case_id,
                "run_status": report.run_status,
                "evaluation_mode": report.evaluation_mode,
                "commands_executed": report.commands_executed,
                "command_count": report.command_count,
                "blocking_reasons": report.blocking_reasons,
                "warnings": report.warnings,
                "output_dirs": report.output_dirs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report.run_status not in {"completed", "dry_run_ready"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
