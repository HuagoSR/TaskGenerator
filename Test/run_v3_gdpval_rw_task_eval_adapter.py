from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_rw_task_eval_adapter import (  # noqa: E402
    DEFAULT_MODELS,
    DEFAULT_GRADER_MODEL,
    GDPValRwTaskEvalAdapter,
    GDPValRwTaskEvalRequest,
)


DEFAULT_SUBSET_MANIFEST = ROOT / "artifacts" / "phase14" / "gdpval_subset" / "gdpval_finance_audit_subset_manifest.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "gdpval_eval_baseline"
DEFAULT_RW_TASK_ROOT = ROOT.parent / "rw-task"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare or run GDPVal calibration-only tasks through the rw-task diagnostic toolchain."
    )
    parser.add_argument("--subset-manifest-path", default=str(DEFAULT_SUBSET_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--mode", choices=["prepare", "dry-run", "execute"], default="dry-run")
    parser.add_argument("--model", action="append", default=None, help="Model to evaluate. Repeat for multiple models.")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", default=str(DEFAULT_RW_TASK_ROOT))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--env-path", default=str(DEFAULT_RW_TASK_ROOT / ".env"))
    parser.add_argument("--task-limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=7200)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument(
        "--agent-max-tokens",
        type=int,
        default=16000,
        help="Completion-token cap patched into rw-task stirrup_batch before execution.",
    )
    parser.add_argument(
        "--grader-model",
        default=DEFAULT_GRADER_MODEL,
        help="Model used by bench_standalone.grade_deliverables via GRADER_MODEL.",
    )
    args = parser.parse_args()

    models = args.model if args.model else list(DEFAULT_MODELS)
    request = GDPValRwTaskEvalRequest(
        subset_manifest_path=args.subset_manifest_path,
        output_dir=args.output_dir,
        mode=args.mode,
        models=models,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
        env_path=args.env_path,
        task_limit=args.task_limit,
        overwrite=args.overwrite,
        command_timeout_seconds=args.command_timeout_seconds,
        run_eval=args.run_eval,
        agent_max_tokens=args.agent_max_tokens,
        grader_model=args.grader_model,
    )
    report = GDPValRwTaskEvalAdapter().run(request)
    print(
        json.dumps(
            {
                "mode": args.mode,
                "output_dir": str(Path(args.output_dir).resolve()),
                "campaign_report_path": str(Path(args.output_dir).resolve() / "gdpval_eval_campaign_report.json"),
                "model_gap_profile_path": str(Path(args.output_dir).resolve() / "gdpval_model_gap_profile.json"),
                "failure_report_path": str(Path(args.output_dir).resolve() / "gdpval_eval_failure_report.json"),
                "prepared_task_count": report.prepared_task_count,
                "blocked_task_count": report.blocked_task_count,
                "model_count": report.model_count,
                "executed_model_count": report.executed_model_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
