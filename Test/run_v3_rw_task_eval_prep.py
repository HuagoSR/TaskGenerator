import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_rw_task_eval_prep import (  # noqa: E402
    DEFAULT_REAL_WORLD_TASK_PYTHON,
    DEFAULT_RW_TASK_ROOT,
    RwTaskEvalPrep,
)


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_CASE_DIR = SCRATCH / "rw_task_export_smoke"
DEFAULT_EVAL_INPUT_DIR = SCRATCH / "rw_task_eval_input_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a validated V3 rw-task export for later evaluation without running models."
    )
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--validation-report", type=Path, default=None)
    parser.add_argument("--eval-input-dir", type=Path, default=DEFAULT_EVAL_INPUT_DIR)
    parser.add_argument("--model", default="gpt-5.4-pro")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK_ROOT)
    parser.add_argument("--python-exe", type=Path, default=DEFAULT_REAL_WORLD_TASK_PYTHON)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    prep = RwTaskEvalPrep()
    report = prep.prepare(
        case_dir=args.case_dir,
        validation_report_path=args.validation_report,
        eval_input_dir=args.eval_input_dir,
        model=args.model,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "case_id": report.case_id,
                "prep_status": report.prep_status,
                "evaluation_mode": report.evaluation_mode,
                "eval_input_case_dir": report.eval_input_case_dir,
                "reference_file_count": report.reference_file_count,
                "would_run_commands": report.would_run_commands,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
