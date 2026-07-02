import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_rw_task_export_validator import RwTaskExportValidator  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_CASE_DIR = SCRATCH / "rw_task_export_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a local V3 rw-task-style export without running model evaluation."
    )
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--output-path", type=Path, default=None)
    args = parser.parse_args()

    validator = RwTaskExportValidator()
    report = validator.validate(case_dir=args.case_dir, output_path=args.output_path)
    print(
        json.dumps(
            {
                "case_id": report.case_id,
                "validation_status": report.validation_status,
                "blocking_count": report.blocking_count,
                "warning_count": report.warning_count,
                "reference_file_count": report.reference_file_count,
                "deliverable_file_count": report.deliverable_file_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
