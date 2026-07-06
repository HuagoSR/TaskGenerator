import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_production_promotion_manager import ProductionPromotionManager  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply an explicit reviewer policy to promote reviewed production cases."
    )
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--qa-gate-report-path", type=Path, required=True)
    parser.add_argument("--review-spec-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    artifact = ProductionPromotionManager().apply_review(
        production_batch_manifest_path=args.manifest_path,
        base_production_qa_gate_report_path=args.qa_gate_report_path,
        production_review_spec_path=args.review_spec_path,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "promotion_report_path": str(args.output_dir / "production_promotion_report.json"),
                "reviewed_qa_report_path": str(args.output_dir / "reviewed_production_qa_gate_report.json"),
                "approved_production_candidate_count": artifact.summary.approved_production_candidate_count,
                "review_required_count": artifact.summary.review_required_count,
                "blocked_count": artifact.summary.blocked_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
