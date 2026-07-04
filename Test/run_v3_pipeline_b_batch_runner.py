import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunner  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_SEED_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "batch_runner_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a deterministic Pipeline B batch smoke across multiple motifs."
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-report", type=Path, default=DEFAULT_SEED_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--motif",
        action="append",
        default=None,
        help="Motif to include. Repeat for multiple motifs. Defaults to the Pipeline B motif priority list.",
    )
    parser.add_argument("--skill-count", type=int, default=4)
    parser.add_argument("--max-cases", type=int, default=3)
    parser.add_argument("--allow-caution", action="store_true")
    parser.add_argument("--workflow-archetype", default=None)
    parser.add_argument("--motif-grammar-path", type=Path, default=None)
    parser.add_argument("--target-difficulty-profile", default=None)
    parser.add_argument("--model", type=str, default="gpt-5.4-pro")
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

    runner = PipelineBBatchRunner()
    report = runner.run(
        registry_path=args.registry_path,
        seed_report_path=args.seed_report,
        output_dir=args.output_dir,
        motifs=args.motif,
        skill_count=args.skill_count,
        max_cases=args.max_cases,
        allow_caution=args.allow_caution,
        workflow_archetype=args.workflow_archetype,
        motif_grammar_path=args.motif_grammar_path,
        target_difficulty_profile=args.target_difficulty_profile,
        model=args.model,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
    )

    print(
        json.dumps(
            {
                "batch_report_path": str(args.output_dir / "pipeline_b_batch_report.json"),
                "case_count": report.diagnostics.case_count,
                "completed_case_count": report.diagnostics.completed_case_count,
                "failed_case_count": report.diagnostics.failed_case_count,
                "unique_subgraph_count": report.diagnostics.unique_subgraph_count,
                "duplicate_subgraph_count": report.diagnostics.duplicate_subgraph_count,
                "quality_decision_counts": report.diagnostics.quality_decision_counts,
                "package_readiness_counts": report.diagnostics.package_readiness_counts,
                "subgraph_confidence_counts": report.diagnostics.subgraph_confidence_counts,
                "role_filling_case_count": report.diagnostics.role_filling_case_count,
                "missing_role_counts": report.diagnostics.missing_role_counts,
                "repeated_reason_codes": report.diagnostics.repeated_reason_codes,
                "batch_warnings": report.diagnostics.batch_warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
