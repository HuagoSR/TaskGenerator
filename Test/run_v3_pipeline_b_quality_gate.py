import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_quality_gate import PipelineBQualityGate  # noqa: E402


DEFAULT_GENERATED_FILE_MANIFEST = (
    ROOT
    / "artifacts"
    / "pipeline_b"
    / "scratch"
    / "reference_file_generation_smoke"
    / "generated_file_manifest.json"
)
DEFAULT_TEACHER_INPUT_VALIDATION_REPORT = (
    ROOT
    / "artifacts"
    / "pipeline_b"
    / "scratch"
    / "teacher_input_smoke"
    / "teacher_input_validation_report.json"
)
DEFAULT_TEACHER_RUNNER_REPORT = (
    ROOT
    / "artifacts"
    / "pipeline_b"
    / "scratch"
    / "teacher_runner_smoke"
    / "teacher_runner_report.json"
)
DEFAULT_TRAINING_ANNOTATION_REPORT = (
    ROOT
    / "artifacts"
    / "pipeline_b"
    / "scratch"
    / "training_annotation_smoke"
    / "training_annotation_report.json"
)
DEFAULT_RUBRIC_REPORT = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "rubric_smoke" / "rubric_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "quality_gate_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic Pipeline B package-level quality gate."
    )
    parser.add_argument("--generated-file-manifest", type=Path, default=DEFAULT_GENERATED_FILE_MANIFEST)
    parser.add_argument(
        "--teacher-input-validation-report",
        type=Path,
        default=DEFAULT_TEACHER_INPUT_VALIDATION_REPORT,
    )
    parser.add_argument("--teacher-runner-report", type=Path, default=DEFAULT_TEACHER_RUNNER_REPORT)
    parser.add_argument(
        "--training-annotation-report",
        type=Path,
        default=DEFAULT_TRAINING_ANNOTATION_REPORT,
    )
    parser.add_argument("--rubric-report", type=Path, default=DEFAULT_RUBRIC_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    gate = PipelineBQualityGate()
    report = gate.build(
        generated_file_manifest_path=args.generated_file_manifest,
        teacher_input_validation_report_path=args.teacher_input_validation_report,
        teacher_runner_report_path=args.teacher_runner_report,
        training_annotation_report_path=args.training_annotation_report,
        rubric_report_path=args.rubric_report,
    )
    outputs = gate.write_outputs(report, args.output_dir)
    print(
        json.dumps(
            {
                **outputs,
                "blueprint_id": report.blueprint_id,
                "decision": report.decision.decision,
                "finding_count": len(report.findings),
                "blocking_count": report.decision.blocking_count,
                "revise_count": report.decision.revise_count,
                "reason_codes": report.decision.reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
