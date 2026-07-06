import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase12_eval_campaign import Phase12EvalCampaignRunner  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_BATCH_REPORT = (
    SCRATCH
    / "phase12_hardening_phase1234_smoke_v2"
    / "phase12_workflow_context"
    / "workflow_strengthened_regression_5case"
    / "batch"
    / "pipeline_b_batch_report.json"
)
DEFAULT_OUTPUT_DIR = SCRATCH / "phase12_eval_campaign_v1"
DEFAULT_RW_TASK_ROOT = Path(r"E:\THU\2026Spring\SRT\rw-task")
DEFAULT_PYTHON_EXE = Path(r"D:\miniconda3\envs\real-world-task\python.exe")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 12 guarded executed eval mini-campaign.")
    parser.add_argument("--batch-report", type=Path, default=DEFAULT_BATCH_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", action="append", default=["gpt-5.4-pro", "gpt-4o-mini"])
    parser.add_argument("--case-count", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK_ROOT)
    parser.add_argument("--python-exe", type=Path, default=DEFAULT_PYTHON_EXE)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--allow-draft-eval", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    report = Phase12EvalCampaignRunner().run(
        batch_report_path=args.batch_report,
        output_dir=args.output_dir,
        models=args.model,
        case_count=args.case_count,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
        run_eval=args.run_eval,
        allow_draft_eval=args.allow_draft_eval,
        overwrite=args.overwrite,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    print(
        json.dumps(
            {
                "phase12_eval_campaign_report_path": str(args.output_dir / "phase12_eval_campaign_report.json"),
                "selected_case_count": report.summary.selected_case_count,
                "summary_completion_rate": report.summary.summary_completion_rate,
                "usable_summary_rate": report.summary.usable_summary_rate,
                "campaign_status": report.summary.campaign_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
