import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_rw_task_exporter import PipelineBRwTaskExporter  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_PACKAGE_MANIFEST = SCRATCH / "package_assembler_smoke" / "package_manifest.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "rw_task_export_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a staged Pipeline B package into an rw-task-style draft case directory."
    )
    parser.add_argument("--package-manifest", type=Path, default=DEFAULT_PACKAGE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--case-id", type=str, default=None)
    parser.add_argument("--allow-revise-only", action="store_true")
    args = parser.parse_args()

    exporter = PipelineBRwTaskExporter()
    report = exporter.export(
        package_manifest_path=args.package_manifest,
        output_dir=args.output_dir,
        case_id=args.case_id,
        allow_revise_only=args.allow_revise_only,
    )
    print(
        json.dumps(
            {
                "package_id": report.package_id,
                "blueprint_id": report.blueprint_id,
                "export_decision": report.export_decision,
                "case_dir": report.case_dir,
                "reference_file_count": report.reference_file_count,
                "deliverable_file_count": report.deliverable_file_count,
                "rw_task_rubric_item_count": report.rw_task_rubric_item_count,
                "diagnostic_rubric_item_count": report.diagnostic_rubric_item_count,
                "reason_codes": report.reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
