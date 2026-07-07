from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_rw_task_eval_adapter import DEFAULT_GRADER_MODEL, DEFAULT_MODELS  # noqa: E402
from task_generator.v3_gdpval_single_case_eval import GDPValSingleCaseEvaluator, SingleCaseEvalRequest  # noqa: E402


DEFAULT_SUBSET_MANIFEST = ROOT / "artifacts" / "phase14" / "gdpval_subset" / "gdpval_finance_audit_subset_manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "phase14" / "gdpval_single_case_runs"
DEFAULT_RW_TASK_ROOT = ROOT.parent / "rw-task"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or inspect one GDPVal calibration case at a time.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--mode",
        choices=["diagnose-existing", "prepare-regrade", "execute-regrade", "execute"],
        default="diagnose-existing",
    )
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--case-index", type=int, default=None, help="1-based selected-record index.")
    parser.add_argument("--source-run", default=None, help="Existing GDPVal campaign directory to inspect/regrade.")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--subset-manifest-path", default=str(DEFAULT_SUBSET_MANIFEST))
    parser.add_argument("--model", action="append", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", default=str(DEFAULT_RW_TASK_ROOT))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--env-path", default=str(DEFAULT_RW_TASK_ROOT / ".env"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=7200)
    parser.add_argument("--agent-max-tokens", type=int, default=16000)
    parser.add_argument("--case-timeout-seconds", type=int, default=7200)
    parser.add_argument("--sandbox-timeout-seconds", type=int, default=3600)
    parser.add_argument("--grader-model", default=DEFAULT_GRADER_MODEL)
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    models = args.model if args.model else list(DEFAULT_MODELS)
    request = SingleCaseEvalRequest(
        run_id=args.run_id,
        mode=args.mode,
        task_id=args.task_id,
        case_index=args.case_index,
        source_run=args.source_run,
        output_dir=str(output_dir),
        subset_manifest_path=args.subset_manifest_path,
        models=models,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
        env_path=args.env_path,
        overwrite=args.overwrite,
        run_eval=args.run_eval,
        command_timeout_seconds=args.command_timeout_seconds,
        agent_max_tokens=args.agent_max_tokens,
        case_timeout_seconds=args.case_timeout_seconds,
        sandbox_timeout_seconds=args.sandbox_timeout_seconds,
        grader_model=args.grader_model,
    )
    report = GDPValSingleCaseEvaluator().run(request)
    decision = json.loads(Path(report.continue_decision_path).read_text(encoding="utf-8"))
    gap = json.loads(Path(report.case_gap_profile_path).read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "mode": args.mode,
                "output_dir": str(Path(output_dir).resolve()),
                "task_id": report.task_id,
                "case_slug": report.case_slug,
                "decision": decision.get("decision"),
                "usable_for_gap_analysis": gap.get("usable_for_gap_analysis"),
                "score_gap": gap.get("score_gap"),
                "single_case_report_path": str(Path(output_dir).resolve() / "single_case_report.json"),
                "deliverable_diagnostic_report_path": report.deliverable_diagnostic_report_path,
                "sanitized_regrade_report_path": report.sanitized_regrade_report_path,
                "case_gap_profile_path": report.case_gap_profile_path,
                "continue_decision_path": report.continue_decision_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
