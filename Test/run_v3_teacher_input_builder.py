import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_teacher_input_builder import TeacherInputBuilder  # noqa: E402


DEFAULT_BLUEPRINT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "prototype_from_subgraph_smoke" / "draft_task_blueprint.json"
)
DEFAULT_SUBGRAPH_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "subgraph_sampler_smoke" / "pipeline_b_subgraph_report.json"
)
DEFAULT_REFERENCE_FILE_PLAN_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "reference_file_plan_smoke" / "reference_file_plan.json"
)
DEFAULT_GENERATED_FILE_MANIFEST_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "reference_file_generation_smoke" / "generated_file_manifest.json"
)
DEFAULT_PIPELINE_A_FEEDBACK_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "subgraph_sampler_smoke" / "pipeline_a_feedback.json"
)
DEFAULT_PROTOTYPE_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "prototype_from_subgraph_smoke" / "pipeline_b_prototype_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_input_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a teacher-mode input contract from current Pipeline B artifacts."
    )
    parser.add_argument("--blueprint", type=Path, default=DEFAULT_BLUEPRINT_PATH)
    parser.add_argument("--subgraph-report", type=Path, default=DEFAULT_SUBGRAPH_REPORT_PATH)
    parser.add_argument("--reference-file-plan", type=Path, default=DEFAULT_REFERENCE_FILE_PLAN_PATH)
    parser.add_argument("--generated-file-manifest", type=Path, default=DEFAULT_GENERATED_FILE_MANIFEST_PATH)
    parser.add_argument("--pipeline-a-feedback", type=Path, default=DEFAULT_PIPELINE_A_FEEDBACK_PATH)
    parser.add_argument("--prototype-report", type=Path, default=DEFAULT_PROTOTYPE_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    builder = TeacherInputBuilder()
    manifest, validation_report = builder.build(
        blueprint_path=args.blueprint,
        subgraph_report_path=args.subgraph_report,
        reference_file_plan_path=args.reference_file_plan,
        generated_file_manifest_path=args.generated_file_manifest,
        pipeline_a_feedback_path=args.pipeline_a_feedback,
        prototype_report_path=args.prototype_report,
    )
    outputs = builder.write_outputs(manifest, validation_report, args.output_dir)
    print(
        json.dumps(
            {
                **outputs,
                "blueprint_id": manifest.blueprint_id,
                "readiness": manifest.diagnostics.readiness,
                "generated_candidate_file_count": manifest.diagnostics.generated_candidate_file_count,
                "deferred_candidate_file_count": manifest.diagnostics.deferred_candidate_file_count,
                "evidence_contract_count": manifest.diagnostics.evidence_contract_count,
                "relationship_check_count": manifest.diagnostics.relationship_check_count,
                "blocking_reason_codes": manifest.diagnostics.blocking_reason_codes,
                "warning_reason_codes": manifest.diagnostics.warning_reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
