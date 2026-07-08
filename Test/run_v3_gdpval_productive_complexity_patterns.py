import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_productive_complexity_patterns import (  # noqa: E402
    GDPValProductivePatternBuilder,
    GDPValProductivePatternRequest,
)


PHASE14 = ROOT / "artifacts" / "phase14"
PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_ANATOMY = PHASE14 / "gdpval_anatomy" / "gdpval_anatomy_summary_report.json"
DEFAULT_DISTRIBUTION = PHASE14 / "gdpval_anatomy" / "gdpval_task_anatomy_distribution.json"
DEFAULT_GAP_AUTOPSY = PHASE14 / "gdpval_gap_autopsy" / "gdpval_gap_autopsy_report.json"
DEFAULT_OUTPUT = PHASE15 / "pattern_library"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 15 GDPVal productive complexity pattern library.")
    parser.add_argument("--gdpval-anatomy-report-path", type=Path, default=DEFAULT_ANATOMY)
    parser.add_argument("--gdpval-anatomy-distribution-path", type=Path, default=DEFAULT_DISTRIBUTION)
    parser.add_argument("--gdpval-gap-autopsy-path", type=Path, default=DEFAULT_GAP_AUTOPSY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = GDPValProductivePatternRequest(
        gdpval_anatomy_report_path=str(args.gdpval_anatomy_report_path),
        gdpval_anatomy_distribution_path=str(args.gdpval_anatomy_distribution_path),
        gdpval_gap_autopsy_path=str(args.gdpval_gap_autopsy_path),
        output_dir=str(args.output_dir),
    )
    report = GDPValProductivePatternBuilder().build(request)
    print(
        json.dumps(
            {
                "pattern_count": report.pattern_count,
                "pattern_ids": [pattern.pattern_id for pattern in report.patterns],
                "library_path": str(Path(args.output_dir) / "gdpval_productive_complexity_pattern_library.json"),
                "mapping_path": str(Path(args.output_dir) / "pattern_to_generator_mapping_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
