import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_teacher_runner import TeacherRunner  # noqa: E402


DEFAULT_TEACHER_INPUT_MANIFEST_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_input_smoke" / "teacher_input_manifest.json"
)
DEFAULT_TEACHER_INPUT_VALIDATION_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_input_smoke" / "teacher_input_validation_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "teacher_runner_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic teacher-mode GoldenRun scaffold from teacher input artifacts."
    )
    parser.add_argument("--teacher-input-manifest", type=Path, default=DEFAULT_TEACHER_INPUT_MANIFEST_PATH)
    parser.add_argument(
        "--teacher-input-validation-report",
        type=Path,
        default=DEFAULT_TEACHER_INPUT_VALIDATION_REPORT_PATH,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    runner = TeacherRunner()
    golden_run, report = runner.build(
        teacher_input_manifest_path=args.teacher_input_manifest,
        teacher_input_validation_report_path=args.teacher_input_validation_report,
    )
    outputs = runner.write_outputs(golden_run, report, args.output_dir)
    print(
        json.dumps(
            {
                **outputs,
                "blueprint_id": golden_run.blueprint_id,
                "readiness": golden_run.readiness,
                "step_count": len(golden_run.steps),
                "intermediate_state_count": len(golden_run.intermediate_states),
                "final_check_count": len(golden_run.final_checks),
                "complete_step_count": report.diagnostics.complete_step_count,
                "partial_step_count": report.diagnostics.partial_step_count,
                "blocked_step_count": report.diagnostics.blocked_step_count,
                "warning_reason_codes": report.diagnostics.warning_reason_codes,
                "blocking_reason_codes": report.diagnostics.blocking_reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
