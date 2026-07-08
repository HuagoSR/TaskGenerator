import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_generated_task_comparison_eval import (  # noqa: E402
    DEFAULT_MODELS,
    GeneratedTaskComparisonEval,
    GeneratedTaskComparisonEvalRequest,
)
from task_generator.v3_rw_task_eval_prep import (  # noqa: E402
    DEFAULT_REAL_WORLD_TASK_PYTHON,
    DEFAULT_RW_TASK_ROOT,
)


DEFAULT_PLAN = ROOT / "artifacts" / "phase14" / "taskgenerator_comparison_eval_plan.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "generated_task_comparison_eval"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare or run Phase 14 generated TaskGenerator comparison tasks through rw-task."
    )
    parser.add_argument("--comparison-plan-path", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--mode", choices=["prepare", "dry-run", "execute"], default="dry-run")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK_ROOT)
    parser.add_argument("--python-exe", type=Path, default=DEFAULT_REAL_WORLD_TASK_PYTHON)
    parser.add_argument("--env-path", type=Path, default=None)
    parser.add_argument("--grader-model", default="gpt-5.4-pro")
    parser.add_argument("--agent-max-tokens", type=int, default=16000)
    parser.add_argument("--case-timeout-seconds", type=int, default=7200)
    parser.add_argument("--sandbox-timeout-seconds", type=int, default=3600)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=0)
    args = parser.parse_args()

    request = GeneratedTaskComparisonEvalRequest(
        comparison_plan_path=str(args.comparison_plan_path),
        output_dir=str(args.output_dir),
        mode=args.mode,
        models=args.model or list(DEFAULT_MODELS),
        task_ids=args.task_id,
        workers=args.workers,
        rw_task_root=str(args.rw_task_root),
        python_exe=str(args.python_exe),
        env_path=str(args.env_path) if args.env_path else None,
        grader_model=args.grader_model,
        agent_max_tokens=args.agent_max_tokens,
        case_timeout_seconds=args.case_timeout_seconds,
        sandbox_timeout_seconds=args.sandbox_timeout_seconds,
        run_eval=args.run_eval,
        overwrite=args.overwrite,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    report = GeneratedTaskComparisonEval().run(request)
    print(
        json.dumps(
            {
                "selected_task_count": report.selected_task_count,
                "model_count": report.model_count,
                "task_model_attempt_count": report.task_model_attempt_count,
                "prepared_count": report.prepared_count,
                "dry_run_ready_count": report.dry_run_ready_count,
                "completed_count": report.completed_count,
                "blocked_count": report.blocked_count,
                "failed_count": report.failed_count,
                "timeout_count": report.timeout_count,
                "report_path": str(Path(args.output_dir) / "generated_task_comparison_eval_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
