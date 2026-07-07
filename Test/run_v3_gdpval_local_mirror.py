import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_local_mirror import GDPValLocalMirrorBuilder  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "gdpval_local_mirror"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a calibration-only local mirror of GDPVal.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="0 means mirror every task in the dataset split.")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--exclude-rubrics", action="store_true")
    args = parser.parse_args()

    manifest = GDPValLocalMirrorBuilder().build(
        output_dir=args.output_dir,
        allow_network=args.allow_network,
        limit=args.limit,
        overwrite=args.overwrite,
        include_rubrics=not args.exclude_rubrics,
    )
    print(
        json.dumps(
            {
                "dataset_manifest_path": str(args.output_dir / "dataset_manifest.json"),
                "task_count": manifest.task_count,
                "mirrored_reference_file_count": manifest.mirrored_reference_file_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
