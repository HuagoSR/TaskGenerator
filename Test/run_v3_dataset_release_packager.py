import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_dataset_release_packager import DatasetReleasePackager  # noqa: E402


DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "releases"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Phase 13 dataset release bundle from a production batch."
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--qa-gate-report-path", type=Path, required=True)
    parser.add_argument("--diversity-report-path", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--include-review-required", action="store_true")
    args = parser.parse_args()

    artifact = DatasetReleasePackager().build(
        release_id=args.release_id,
        production_batch_manifest_path=args.manifest_path,
        production_qa_gate_report_path=args.qa_gate_report_path,
        production_batch_diversity_report_path=args.diversity_report_path,
        output_root=args.output_root,
        include_review_required=args.include_review_required,
    )
    print(
        json.dumps(
            {
                "release_manifest_path": artifact.release_manifest_path,
                "release_dir": artifact.release_dir,
                "release_mode": artifact.release_manifest.release_mode,
                "task_count": artifact.release_manifest.task_count,
                "production_ready_count": artifact.release_manifest.production_ready_count,
                "excluded_task_count": artifact.release_manifest.excluded_task_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
