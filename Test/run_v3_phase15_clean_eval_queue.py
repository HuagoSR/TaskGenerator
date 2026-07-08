import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_clean_eval_queue import (  # noqa: E402
    Phase15CleanEvalQueueBuilder,
    Phase15CleanEvalQueueRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_AB_REPORT = PHASE15 / "ab_experiment" / "phase15_ab_experiment_report.json"
DEFAULT_OUTPUT = PHASE15 / "clean_eval_queue"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare one-case, one-model Phase 15 clean eval queue items.")
    parser.add_argument("--ab-experiment-report-path", type=Path, default=DEFAULT_AB_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", action="append", default=None)
    parser.add_argument("--arm", action="append", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--rw-task-root",
        type=Path,
        default=Path(r"E:\THU\2026Spring\SRT\rw-task"),
    )
    parser.add_argument(
        "--python-exe",
        type=Path,
        default=Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
    )
    args = parser.parse_args()

    request = Phase15CleanEvalQueueRequest(
        ab_experiment_report_path=str(args.ab_experiment_report_path),
        output_dir=str(args.output_dir),
        models=args.model or ["gpt-4o-mini", "gemini-3-pro-preview"],
        arms=args.arm or ["baseline_deterministic", "generator_reform_only"],
        workers=args.workers,
        rw_task_root=str(args.rw_task_root),
        python_exe=str(args.python_exe),
    )
    report = Phase15CleanEvalQueueBuilder().build(request)
    print(
        json.dumps(
            {
                "summary": report.summary,
                "recommended_first_pair": report.execution_policy.get("recommended_first_pair"),
                "report_path": str(Path(args.output_dir) / "phase15_clean_eval_queue_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
