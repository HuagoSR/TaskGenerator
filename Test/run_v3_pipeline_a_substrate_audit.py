import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_a_substrate_audit import PipelineASubstrateAuditor  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_BATCH_FEEDBACK_REPORT = (
    SCRATCH / "batch_feedback_smoke" / "pipeline_b_batch_feedback_report.json"
)
DEFAULT_BATCH_REPORT = SCRATCH / "batch_runner_smoke" / "pipeline_b_batch_report.json"
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_READINESS_REPORT = ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json"
DEFAULT_TRANSITION_GRAPH_REPORT = ROOT / "SkillRegistry" / "v3_skill_transition_graph_report.json"
DEFAULT_COMPOSITION_READINESS_REPORT = (
    ROOT / "SkillRegistry" / "v3_composition_readiness_report.json"
)
DEFAULT_OUTPUT_DIR = SCRATCH / "pipeline_a_substrate_audit_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Pipeline A substrate signals for skills sampled by Pipeline B batch smoke."
    )
    parser.add_argument(
        "--batch-feedback-report",
        type=Path,
        default=DEFAULT_BATCH_FEEDBACK_REPORT,
    )
    parser.add_argument("--batch-report", type=Path, default=DEFAULT_BATCH_REPORT)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
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
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    auditor = PipelineASubstrateAuditor()
    report = auditor.audit(
        batch_feedback_report_path=args.batch_feedback_report,
        batch_report_path=args.batch_report,
        registry_path=args.registry_path,
        readiness_report_path=args.readiness_report,
        transition_graph_report_path=args.transition_graph_report,
        composition_readiness_report_path=args.composition_readiness_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "substrate_audit_report_path": str(
                    args.output_dir / "pipeline_a_substrate_audit_report.json"
                ),
                "audited_skill_count": report.diagnostics.audited_skill_count,
                "batch_case_count": report.diagnostics.batch_case_count,
                "missing_typed_resource_skill_count": report.diagnostics.missing_typed_resource_skill_count,
                "single_source_skill_count": report.diagnostics.single_source_skill_count,
                "multi_source_skill_count": report.diagnostics.multi_source_skill_count,
                "transition_gap_skill_count": report.diagnostics.transition_gap_skill_count,
                "manual_resource_patch_candidate_count": report.diagnostics.manual_resource_patch_candidate_count,
                "new_source_evidence_candidate_count": report.diagnostics.new_source_evidence_candidate_count,
                "top_action": report.remediation_actions[0].title
                if report.remediation_actions
                else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
