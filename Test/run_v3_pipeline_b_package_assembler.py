import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_package_assembler import PipelineBPackageAssembler  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_BLUEPRINT = SCRATCH / "prototype_from_subgraph_smoke" / "draft_task_blueprint.json"
DEFAULT_GENERATED_FILE_MANIFEST = SCRATCH / "reference_file_generation_smoke" / "generated_file_manifest.json"
DEFAULT_TEACHER_INPUT_MANIFEST = SCRATCH / "teacher_input_smoke" / "teacher_input_manifest.json"
DEFAULT_TEACHER_INPUT_VALIDATION_REPORT = (
    SCRATCH / "teacher_input_smoke" / "teacher_input_validation_report.json"
)
DEFAULT_GOLDEN_RUN = SCRATCH / "teacher_runner_smoke" / "golden_run.json"
DEFAULT_TEACHER_RUNNER_REPORT = SCRATCH / "teacher_runner_smoke" / "teacher_runner_report.json"
DEFAULT_TRAINING_ANNOTATION = SCRATCH / "training_annotation_smoke" / "training_annotation.json"
DEFAULT_TRAINING_ANNOTATION_REPORT = (
    SCRATCH / "training_annotation_smoke" / "training_annotation_report.json"
)
DEFAULT_RUBRIC = SCRATCH / "rubric_smoke" / "rubric.json"
DEFAULT_RUBRIC_REPORT = SCRATCH / "rubric_smoke" / "rubric_report.json"
DEFAULT_QUALITY_REPORT = SCRATCH / "quality_gate_smoke" / "pipeline_b_quality_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "package_assembler_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble current Pipeline B artifacts into a staged package directory."
    )
    parser.add_argument("--blueprint", type=Path, default=DEFAULT_BLUEPRINT)
    parser.add_argument("--generated-file-manifest", type=Path, default=DEFAULT_GENERATED_FILE_MANIFEST)
    parser.add_argument("--teacher-input-manifest", type=Path, default=DEFAULT_TEACHER_INPUT_MANIFEST)
    parser.add_argument(
        "--teacher-input-validation-report",
        type=Path,
        default=DEFAULT_TEACHER_INPUT_VALIDATION_REPORT,
    )
    parser.add_argument("--golden-run", type=Path, default=DEFAULT_GOLDEN_RUN)
    parser.add_argument("--teacher-runner-report", type=Path, default=DEFAULT_TEACHER_RUNNER_REPORT)
    parser.add_argument("--training-annotation", type=Path, default=DEFAULT_TRAINING_ANNOTATION)
    parser.add_argument(
        "--training-annotation-report",
        type=Path,
        default=DEFAULT_TRAINING_ANNOTATION_REPORT,
    )
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--rubric-report", type=Path, default=DEFAULT_RUBRIC_REPORT)
    parser.add_argument("--quality-report", type=Path, default=DEFAULT_QUALITY_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    assembler = PipelineBPackageAssembler()
    manifest = assembler.build(
        blueprint_path=args.blueprint,
        generated_file_manifest_path=args.generated_file_manifest,
        teacher_input_manifest_path=args.teacher_input_manifest,
        teacher_input_validation_report_path=args.teacher_input_validation_report,
        golden_run_path=args.golden_run,
        teacher_runner_report_path=args.teacher_runner_report,
        training_annotation_path=args.training_annotation,
        training_annotation_report_path=args.training_annotation_report,
        rubric_path=args.rubric,
        rubric_report_path=args.rubric_report,
        quality_report_path=args.quality_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "package_manifest_path": str(args.output_dir / "package_manifest.json"),
                "dataset_row_draft_path": str(args.output_dir / "dataset_row_draft.json"),
                "package_id": manifest.package_id,
                "blueprint_id": manifest.blueprint_id,
                "package_readiness": manifest.package_readiness,
                "quality_decision": manifest.diagnostics.quality_decision,
                "artifact_count": manifest.diagnostics.artifact_count,
                "copied_reference_file_count": manifest.diagnostics.copied_reference_file_count,
                "deferred_reference_file_count": manifest.diagnostics.deferred_reference_file_count,
                "export_blockers": manifest.diagnostics.export_blockers,
                "warning_reason_codes": manifest.diagnostics.warning_reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
