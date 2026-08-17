import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_production_batch_runner import ProductionBatchRunner  # noqa: E402
from task_generator.v3_domain_profile import DEFAULT_DOMAIN_PROFILE_PATH  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_SEED_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
DEFAULT_WORKFLOW_ASSET_PATH = ROOT / "SkillRegistry" / "v3_workflow_archetype_registry.experimental.json"
DEFAULT_MOTIF_GRAMMAR_PATH = ROOT / "SkillRegistry" / "v3_motif_graph_grammar.experimental.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "production_batches"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the first Phase 13 production batch runner shell."
    )
    parser.add_argument("--production-batch-id", required=True)
    parser.add_argument(
        "--mode",
        choices=["dry_run", "candidate_run", "production_run"],
        default="dry_run",
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-report", type=Path, default=DEFAULT_SEED_REPORT_PATH)
    parser.add_argument("--workflow-asset-path", type=Path, default=DEFAULT_WORKFLOW_ASSET_PATH)
    parser.add_argument("--motif-grammar-path", type=Path, default=DEFAULT_MOTIF_GRAMMAR_PATH)
    parser.add_argument("--phase15-reform-spec-path", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--domain-scope", default="finance_audit")
    parser.add_argument("--domain-profile", default="finance_audit")
    parser.add_argument("--domain-profile-path", type=Path, default=DEFAULT_DOMAIN_PROFILE_PATH)
    parser.add_argument("--file-type", action="append", default=None)
    parser.add_argument("--motif", action="append", default=None)
    parser.add_argument("--skill-count", type=int, default=4)
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--case-index-offset", type=int, default=0)
    parser.add_argument("--motif-occurrence-offset", action="append", default=[])
    parser.add_argument("--allow-caution", action="store_true")
    parser.add_argument("--workflow-archetype", default=None)
    parser.add_argument("--target-difficulty-profile", default=None)
    parser.add_argument(
        "--proposal-input-manifest",
        type=Path,
        default=None,
        help=(
            "Governed case-to-proposal manifest for the "
            "reconstruction_experimental route."
        ),
    )
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
    motif_occurrence_offsets = {}
    for item in args.motif_occurrence_offset:
        if "=" not in item:
            parser.error("--motif-occurrence-offset must use motif=integer")
        motif, value = item.split("=", 1)
        motif_occurrence_offsets[motif] = int(value)

    output_dir = args.output_root / args.production_batch_id
    artifact = ProductionBatchRunner().run(
        production_batch_id=args.production_batch_id,
        mode=args.mode,
        registry_path=args.registry_path,
        seed_report_path=args.seed_report,
        workflow_asset_path=args.workflow_asset_path,
        motif_grammar_path=args.motif_grammar_path,
        phase15_reform_spec_path=args.phase15_reform_spec_path,
        output_dir=output_dir,
        domain_scope=args.domain_scope,
        file_type_scope=args.file_type or ["xlsx", "docx", "md", "txt"],
        motifs=args.motif,
        skill_count=args.skill_count,
        max_cases=args.max_cases,
        allow_caution=args.allow_caution,
        workflow_archetype=args.workflow_archetype,
        target_difficulty_profile=args.target_difficulty_profile,
        model=args.model,
        workers=args.workers,
        rw_task_root=args.rw_task_root,
        python_exe=args.python_exe,
        domain_profile=args.domain_profile,
        domain_profile_path=args.domain_profile_path,
        case_index_offset=args.case_index_offset,
        motif_occurrence_offsets=motif_occurrence_offsets,
        proposal_input_manifest_path=args.proposal_input_manifest,
    )

    print(
        json.dumps(
            {
                "manifest_path": artifact.manifest_path,
                "summary_report_path": artifact.summary_report_path,
                "batch_report_path": artifact.batch_report_path,
                "mode": artifact.manifest.request.mode,
                "execution_status": artifact.manifest.execution_status,
                "candidate_ready_count": artifact.manifest.summary.candidate_ready_count,
                "production_candidate_eligible_count": artifact.manifest.summary.production_candidate_eligible_count,
                "task_state_counts": artifact.manifest.summary.task_state_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
