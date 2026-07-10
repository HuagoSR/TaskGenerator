import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase12_hardening import Phase12HardeningRunner  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_PHASE11_REGRESSION_REPORT = (
    SCRATCH / "phase_11_batch_regression" / "phase_11_batch_regression_report.json"
)
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_SEED_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
DEFAULT_READINESS_REPORT = ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json"
DEFAULT_TRANSITION_GRAPH_REPORT = ROOT / "SkillRegistry" / "v3_skill_transition_graph_report.json"
DEFAULT_COMPOSITION_READINESS_REPORT = ROOT / "SkillRegistry" / "v3_composition_readiness_report.json"
DEFAULT_OUTPUT_ROOT = SCRATCH / "phase12_hardening"
DEFAULT_HANDOFF_DIR = ROOT / "artifacts" / "historical_phase_runs" / "phase12" / "handoffs"
DEFAULT_RW_TASK_ROOT = Path(r"E:\THU\2026Spring\SRT\rw-task")
DEFAULT_PYTHON_EXE = Path(r"D:\miniconda3\envs\real-world-task\python.exe")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the first Phase 12 hardening slice: baseline freeze, expanded regression, dashboard diff, and negative controls."
    )
    parser.add_argument(
        "--phase11-regression-report",
        type=Path,
        default=DEFAULT_PHASE11_REGRESSION_REPORT,
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-report", type=Path, default=DEFAULT_SEED_REPORT_PATH)
    parser.add_argument("--readiness-report", type=Path, default=DEFAULT_READINESS_REPORT)
    parser.add_argument(
        "--transition-graph-report",
        type=Path,
        default=DEFAULT_TRANSITION_GRAPH_REPORT,
    )
    parser.add_argument(
        "--composition-readiness-report",
        type=Path,
        default=DEFAULT_COMPOSITION_READINESS_REPORT,
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--handoff-dir", type=Path, default=DEFAULT_HANDOFF_DIR)
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--allow-caution", action="store_true")
    parser.add_argument("--motif-grammar-path", type=Path, default=None)
    parser.add_argument("--model", type=str, default="gpt-5.4-pro")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK_ROOT)
    parser.add_argument("--python-exe", type=Path, default=DEFAULT_PYTHON_EXE)
    parser.add_argument("--max-apply-count", type=int, default=3)
    args = parser.parse_args()

    report = Phase12HardeningRunner().run(
        phase11_regression_report_path=args.phase11_regression_report,
        registry_path=args.registry_path,
        seed_report_path=args.seed_report,
        readiness_report_path=args.readiness_report,
        transition_graph_report_path=args.transition_graph_report,
        composition_readiness_report_path=args.composition_readiness_report,
        output_root=args.output_root,
        max_cases=args.max_cases,
        allow_caution=args.allow_caution,
        motif_grammar_path=args.motif_grammar_path,
        model=args.model,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
        handoff_dir=args.handoff_dir,
        max_apply_count=args.max_apply_count,
    )

    print(
        json.dumps(
            {
                "phase12_hardening_report_path": str(args.output_root / "phase12_hardening_report.json"),
                "baseline_report_path": report.baseline_report_path,
                "baseline_handoff_path": report.baseline_handoff_path,
                "regression_report_path": report.regression_report_path,
                "dashboard_diff_report_path": report.dashboard_diff_report_path,
                "negative_control_report_path": report.negative_control_report_path,
                "substrate_hardening_report_path": report.substrate_hardening_report_path,
                "workflow_context_review_report_path": report.workflow_context_review_report_path,
                "transition_prior_report_path": report.transition_prior_report_path,
                "transition_prior_store_path": report.transition_prior_store_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
