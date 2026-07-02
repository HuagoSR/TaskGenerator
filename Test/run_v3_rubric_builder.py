import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_rubric_builder import RubricBuilder  # noqa: E402


DEFAULT_TRAINING_ANNOTATION_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "training_annotation_smoke" / "training_annotation.json"
)
DEFAULT_TRAINING_ANNOTATION_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "training_annotation_smoke" / "training_annotation_report.json"
)
DEFAULT_GOLDEN_RUN_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_runner_smoke" / "golden_run.json"
)
DEFAULT_TEACHER_RUNNER_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_runner_smoke" / "teacher_runner_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "rubric_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a structured rubric from teacher and training artifacts.")
    parser.add_argument("--training-annotation", type=Path, default=DEFAULT_TRAINING_ANNOTATION_PATH)
    parser.add_argument(
        "--training-annotation-report",
        type=Path,
        default=DEFAULT_TRAINING_ANNOTATION_REPORT_PATH,
    )
    parser.add_argument("--golden-run", type=Path, default=DEFAULT_GOLDEN_RUN_PATH)
    parser.add_argument("--teacher-runner-report", type=Path, default=DEFAULT_TEACHER_RUNNER_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    builder = RubricBuilder()
    artifact, report = builder.build(
        training_annotation_path=args.training_annotation,
        training_annotation_report_path=args.training_annotation_report,
        golden_run_path=args.golden_run,
        teacher_runner_report_path=args.teacher_runner_report,
    )
    outputs = builder.write_outputs(artifact, report, args.output_dir)
    print(
        json.dumps(
            {
                **outputs,
                "blueprint_id": artifact.blueprint_id,
                "readiness": artifact.readiness,
                "section_count": report.diagnostics.section_count,
                "criterion_count": report.diagnostics.criterion_count,
                "candidate_criterion_count": report.diagnostics.candidate_criterion_count,
                "diagnostic_criterion_count": report.diagnostics.diagnostic_criterion_count,
                "rw_task_exportable_criterion_count": report.diagnostics.rw_task_exportable_criterion_count,
                "partial_criterion_count": report.diagnostics.partial_criterion_count,
                "warning_reason_codes": report.diagnostics.warning_reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
