import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_production_impact_review import (  # noqa: E402
    Phase15ProductionImpactReviewRequest,
    Phase15ProductionImpactReviewer,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_PRODUCTION = PHASE15 / "production_impact"


def main() -> None:
    parser = argparse.ArgumentParser(description="Review Phase 15 reform production impact without release mutation.")
    parser.add_argument("--production-dashboard-report-path", type=Path, default=DEFAULT_PRODUCTION / "reform_dashboard" / "production_dashboard_report.json")
    parser.add_argument("--production-qa-gate-report-path", type=Path, default=DEFAULT_PRODUCTION / "reform_qa" / "production_qa_gate_report.json")
    parser.add_argument("--production-diversity-report-path", type=Path, default=DEFAULT_PRODUCTION / "reform_diversity" / "production_batch_diversity_report.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_PRODUCTION / "phase15_review")
    args = parser.parse_args()

    request = Phase15ProductionImpactReviewRequest(
        production_dashboard_report_path=str(args.production_dashboard_report_path),
        production_qa_gate_report_path=str(args.production_qa_gate_report_path),
        production_diversity_report_path=str(args.production_diversity_report_path),
        output_dir=str(args.output_dir),
    )
    report = Phase15ProductionImpactReviewer().build(request)
    print(
        json.dumps(
            {
                "decision": report.decision,
                "explicit_review_completed": report.explicit_review_completed,
                "release_ready": report.release_ready,
                "structural_regression_detected": report.structural_regression_detected,
                "blocking_reasons": report.blocking_reasons,
                "review_reasons": report.review_reasons,
                "report_path": str(Path(args.output_dir) / "phase15_production_impact_review_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
