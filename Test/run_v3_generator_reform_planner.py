import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_generator_reform_planner import (  # noqa: E402
    GeneratorReformPlanner,
    GeneratorReformPlannerRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_GAP_AUTOPSY = PHASE15 / "gap_autopsy" / "generated_task_gap_autopsy_report.json"
DEFAULT_PATTERN_LIBRARY = PHASE15 / "pattern_library" / "gdpval_productive_complexity_pattern_library.json"
DEFAULT_PATTERN_MAPPING = PHASE15 / "pattern_library" / "pattern_to_generator_mapping_report.json"
DEFAULT_OUTPUT = PHASE15 / "generator_reform"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 15 generator reform design spec.")
    parser.add_argument("--generated-task-gap-autopsy-path", type=Path, default=DEFAULT_GAP_AUTOPSY)
    parser.add_argument("--pattern-library-path", type=Path, default=DEFAULT_PATTERN_LIBRARY)
    parser.add_argument("--pattern-mapping-path", type=Path, default=DEFAULT_PATTERN_MAPPING)
    parser.add_argument("--target-motif", default="evidence_to_deliverable")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = GeneratorReformPlannerRequest(
        generated_task_gap_autopsy_path=str(args.generated_task_gap_autopsy_path),
        pattern_library_path=str(args.pattern_library_path),
        pattern_mapping_path=str(args.pattern_mapping_path),
        target_motif=args.target_motif,
        output_dir=str(args.output_dir),
    )
    report = GeneratorReformPlanner().build(request)
    print(
        json.dumps(
            {
                "target_motif": report.target_motif,
                "selected_patterns": report.selected_patterns,
                "spec_path": report.spec_path,
                "reform_summary": report.reform_summary,
                "report_path": str(Path(args.output_dir) / "generator_reform_design_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
