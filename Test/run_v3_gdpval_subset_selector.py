import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_subset_selector import GDPValSubsetSelector  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "gdpval_subset"
DEFAULT_MIRROR_MANIFEST = ROOT / "artifacts" / "phase14" / "gdpval_local_mirror" / "dataset_manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a finance/audit-oriented GDPVal calibration subset.")
    parser.add_argument("--mirror-manifest-path", type=Path, default=DEFAULT_MIRROR_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-count", type=int, default=10)
    args = parser.parse_args()

    subset_manifest, _ = GDPValSubsetSelector().build(
        mirror_manifest_path=args.mirror_manifest_path,
        output_dir=args.output_dir,
        target_count=args.target_count,
    )
    print(
        json.dumps(
            {
                "subset_manifest_path": str(args.output_dir / "gdpval_finance_audit_subset_manifest.json"),
                "selected_count": subset_manifest.selected_count,
                "selected_task_ids": subset_manifest.selected_task_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
