import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_eval_orchestrator import EvalOrchestrator  # noqa: E402
from task_generator.v3_rw_task_eval_prep import (  # noqa: E402
    DEFAULT_REAL_WORLD_TASK_PYTHON,
    DEFAULT_RW_TASK_ROOT,
)


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_CASE_DIR = SCRATCH / "batch_runner_phase7_verifier_smoke" / "pipeline_b_batch_01_evidence_to_deliverable"
DEFAULT_BASE_PREP_REPORT = DEFAULT_CASE_DIR / "rw_task_eval_input" / "rw_task_eval_prep_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "eval_orchestrator_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrate multi-model V3 evaluation artifacts from one case or one base prep report."
    )
    parser.add_argument("--case-dir", type=Path, default=None)
    parser.add_argument("--validation-report", type=Path, default=None)
    parser.add_argument("--base-prep-report", type=Path, default=None)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK_ROOT)
    parser.add_argument("--python-exe", type=Path, default=DEFAULT_REAL_WORLD_TASK_PYTHON)
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--allow-draft-eval", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=0)
    args = parser.parse_args()

    models = args.model or ["gpt-5.4-pro", "gpt-4o-mini"]
    case_dir = args.case_dir
    base_prep_report = args.base_prep_report
    if case_dir is None and base_prep_report is None:
        case_dir = DEFAULT_CASE_DIR

    orchestrator = EvalOrchestrator()
    report = orchestrator.orchestrate(
        case_dir=case_dir,
        validation_report_path=args.validation_report,
        base_prep_report_path=base_prep_report,
        models=models,
        output_dir=args.output_dir,
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
                "evaluation_orchestration_report_path": str(
                    args.output_dir / "evaluation_orchestration_report.json"
                ),
                "batch_case_id": report.batch_case_id,
                "blueprint_id": report.blueprint_id,
                "rw_task_task_id": report.rw_task_task_id,
                "execution_mode": report.execution_mode,
                "model_count": report.diagnostics.model_count,
                "prepared_model_count": report.diagnostics.prepared_model_count,
                "summarized_model_count": report.diagnostics.summarized_model_count,
                "feedback_model_count": report.diagnostics.feedback_model_count,
                "model_separation_profile_path": report.model_separation_profile_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
