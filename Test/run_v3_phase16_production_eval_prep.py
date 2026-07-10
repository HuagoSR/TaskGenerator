import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_production_eval_prep import (  # noqa: E402
    Phase16ProductionEvalPrepRequest,
    build_phase16_production_eval_prep,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Phase 16 production task packages and rw-task clean-eval prep artifacts."
    )
    parser.add_argument("--experiment-id", default="phase16_evidence_to_deliverable_contract_v2")
    parser.add_argument("--registry-path", type=Path, default=ROOT / "SkillRegistry" / "v3_skill_registry.json")
    parser.add_argument("--seed-report", type=Path, default=ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json")
    parser.add_argument(
        "--workflow-asset-path",
        type=Path,
        default=ROOT / "SkillRegistry" / "v3_workflow_archetype_registry.experimental.json",
    )
    parser.add_argument(
        "--motif-grammar-path",
        type=Path,
        default=ROOT / "SkillRegistry" / "v3_motif_graph_grammar.experimental.json",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "phase16" / "production_eval_prep")
    parser.add_argument("--target-motif", default="evidence_to_deliverable")
    parser.add_argument(
        "--max-cases-per-arm",
        type=int,
        default=3,
        help="Number of production cases to generate per arm; default reaches case03 for the two-case pilot.",
    )
    parser.add_argument(
        "--selected-case-ids",
        nargs="+",
        default=[
            "pipeline_b_batch_01_evidence_to_deliverable",
            "pipeline_b_batch_03_evidence_to_deliverable",
        ],
        help="Case IDs selected for the Phase16 two-case clean eval pilot.",
    )
    parser.add_argument("--skill-count", type=int, default=4)
    parser.add_argument("--models", nargs="+", default=["gpt-4o-mini", "gemini-3-pro-preview"])
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rw-task-root", type=Path, default=Path(r"E:\THU\2026Spring\SRT\rw-task"))
    parser.add_argument("--python-exe", type=Path, default=Path(r"D:\miniconda3\envs\real-world-task\python.exe"))
    parser.add_argument("--command-timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    result = build_phase16_production_eval_prep(
        Phase16ProductionEvalPrepRequest(
            experiment_id=args.experiment_id,
            registry_path=str(args.registry_path),
            seed_report_path=str(args.seed_report),
            workflow_asset_path=str(args.workflow_asset_path) if args.workflow_asset_path else None,
            motif_grammar_path=str(args.motif_grammar_path) if args.motif_grammar_path else None,
            output_dir=str(args.output_dir),
            target_motif=args.target_motif,
            max_cases_per_arm=args.max_cases_per_arm,
            selected_case_ids=args.selected_case_ids,
            skill_count=args.skill_count,
            models=args.models,
            workers=args.workers,
            rw_task_root=str(args.rw_task_root),
            python_exe=str(args.python_exe),
            command_timeout_seconds=args.command_timeout_seconds,
        )
    )
    queue_summary = result["clean_eval_queue"].get("summary") or {}
    experiment_summary = result["production_experiment"].get("summary") or {}
    runbook = result["external_eval_runbook"]
    print(
        json.dumps(
            {
                "experiment_summary": experiment_summary,
                "queue_summary": queue_summary,
                "runbook_blocking_reasons": runbook.get("blocking_reasons"),
                "outputs": result["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
