import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_ab_experiment_runner import (  # noqa: E402
    Phase15AbExperimentRequest,
    Phase15AbExperimentRunner,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_SEED_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
DEFAULT_WORKFLOW_ASSET_PATH = ROOT / "SkillRegistry" / "v3_workflow_archetype_registry.experimental.json"
DEFAULT_MOTIF_GRAMMAR_PATH = ROOT / "SkillRegistry" / "v3_motif_graph_grammar.experimental.json"
DEFAULT_REFORM_SPEC = PHASE15 / "generator_reform" / "evidence_to_deliverable_reform_spec.json"
DEFAULT_LLM_CANDIDATE_LAYER = PHASE15 / "llm_candidate_layer" / "llm_candidate_layer_report.json"
DEFAULT_OUTPUT = PHASE15 / "ab_experiment"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 15 controlled A/B/C experiment ledger.")
    parser.add_argument("--experiment-id", default="phase15_evidence_to_deliverable_v0")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-report", type=Path, default=DEFAULT_SEED_REPORT_PATH)
    parser.add_argument("--workflow-asset-path", type=Path, default=DEFAULT_WORKFLOW_ASSET_PATH)
    parser.add_argument("--motif-grammar-path", type=Path, default=DEFAULT_MOTIF_GRAMMAR_PATH)
    parser.add_argument("--reform-spec-path", type=Path, default=DEFAULT_REFORM_SPEC)
    parser.add_argument("--llm-candidate-layer-path", type=Path, default=DEFAULT_LLM_CANDIDATE_LAYER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-motif", default="evidence_to_deliverable")
    parser.add_argument("--max-cases-per-arm", type=int, default=4)
    parser.add_argument("--skill-count", type=int, default=4)
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
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-reform-proxy", action="store_true")
    args = parser.parse_args()

    request = Phase15AbExperimentRequest(
        experiment_id=args.experiment_id,
        registry_path=str(args.registry_path),
        seed_report_path=str(args.seed_report),
        workflow_asset_path=str(args.workflow_asset_path),
        motif_grammar_path=str(args.motif_grammar_path),
        reform_spec_path=str(args.reform_spec_path),
        llm_candidate_layer_path=str(args.llm_candidate_layer_path),
        output_dir=str(args.output_dir),
        target_motif=args.target_motif,
        max_cases_per_arm=args.max_cases_per_arm,
        skill_count=args.skill_count,
        model=args.model,
        workers=args.workers,
        rw_task_root=str(args.rw_task_root),
        python_exe=str(args.python_exe),
        execute_baseline=not args.skip_baseline,
        execute_reform_proxy=not args.skip_reform_proxy,
    )
    report = Phase15AbExperimentRunner().run(request)
    print(
        json.dumps(
            {
                "experiment_id": report.request.experiment_id,
                "summary": report.summary,
                "arms": [
                    {
                        "arm_id": arm.arm_id,
                        "arm_status": arm.arm_status,
                        "candidate_ready_count": arm.candidate_ready_count,
                        "comparable_for_clean_paired_eval": arm.comparable_for_clean_paired_eval,
                        "reason_codes": arm.reason_codes,
                    }
                    for arm in report.arms
                ],
                "report_path": str(Path(args.output_dir) / "phase15_ab_experiment_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
