import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_production_qa_gate import ProductionQAGateBuilder  # noqa: E402


DEFAULT_OUTPUT_SUBDIR = "production_qa_gate"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the report-first Phase 13 production QA gate."
    )
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--diversity-report-path", type=Path, default=None)
    parser.add_argument("--semantic-validation-report-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or (args.manifest_path.parent / DEFAULT_OUTPUT_SUBDIR)
    report = ProductionQAGateBuilder().build(
        production_batch_manifest_path=args.manifest_path,
        diversity_report_path=args.diversity_report_path,
        semantic_validation_report_path=args.semantic_validation_report_path,
        output_dir=output_dir,
    )
    print(
        json.dumps(
            {
                "production_batch_id": report.production_batch_id,
                "report_path": str(output_dir / "production_qa_gate_report.json"),
                "case_count": report.summary.case_count,
                "approved_production_candidate_count": report.summary.approved_production_candidate_count,
                "review_required_count": report.summary.review_required_count,
                "blocked_count": report.summary.blocked_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
