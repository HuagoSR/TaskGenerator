import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_production_batch_diversity import ProductionBatchDiversityBuilder  # noqa: E402


DEFAULT_OUTPUT_SUBDIR = "production_diversity"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a report-only production batch diversity / dedup report."
    )
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or (args.manifest_path.parent / DEFAULT_OUTPUT_SUBDIR)
    report = ProductionBatchDiversityBuilder().build(
        production_batch_manifest_path=args.manifest_path,
        output_dir=output_dir,
    )
    print(
        json.dumps(
            {
                "production_batch_id": report.production_batch_id,
                "report_path": str(output_dir / "production_batch_diversity_report.json"),
                "case_count": report.summary.case_count,
                "unique_motif_count": report.summary.unique_motif_count,
                "duplicate_subgraph_count": report.summary.duplicate_subgraph_count,
                "warnings": report.diagnostics.warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
