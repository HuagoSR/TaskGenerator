import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_training_annotation_builder import TrainingAnnotationBuilder  # noqa: E402


DEFAULT_GOLDEN_RUN_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_runner_smoke" / "golden_run.json"
)
DEFAULT_TEACHER_RUNNER_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_runner_smoke" / "teacher_runner_report.json"
)
DEFAULT_TEACHER_INPUT_MANIFEST_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_input_smoke" / "teacher_input_manifest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "training_annotation_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build training annotations from deterministic teacher artifacts."
    )
    parser.add_argument("--golden-run", type=Path, default=DEFAULT_GOLDEN_RUN_PATH)
    parser.add_argument("--teacher-runner-report", type=Path, default=DEFAULT_TEACHER_RUNNER_REPORT_PATH)
    parser.add_argument("--teacher-input-manifest", type=Path, default=DEFAULT_TEACHER_INPUT_MANIFEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    builder = TrainingAnnotationBuilder()
    artifact, report = builder.build(
        golden_run_path=args.golden_run,
        teacher_runner_report_path=args.teacher_runner_report,
        teacher_input_manifest_path=args.teacher_input_manifest,
    )
    outputs = builder.write_outputs(artifact, report, args.output_dir)
    print(
        json.dumps(
            {
                **outputs,
                "blueprint_id": artifact.blueprint_id,
                "readiness": artifact.readiness,
                "supervision_item_count": len(artifact.supervision_items),
                "failure_mode_count": len(artifact.failure_modes),
                "hidden_trap_count": len(artifact.hidden_traps),
                "unresolved_gap_count": len(artifact.unresolved_gaps),
                "warning_reason_codes": report.diagnostics.warning_reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
