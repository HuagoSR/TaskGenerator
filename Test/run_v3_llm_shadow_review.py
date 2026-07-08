import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_llm_shadow_review import (  # noqa: E402
    LLMShadowReviewBuilder,
    LLMShadowReviewRequest,
)


PHASE14 = ROOT / "artifacts" / "phase14"
PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_EXECUTE_REPORT = PHASE14 / "llm_shadow" / "llm_shadow_execute_report.json"
DEFAULT_OUTPUT = PHASE15 / "llm_shadow_review"


def main() -> None:
    parser = argparse.ArgumentParser(description="Review Phase 14 LLM shadow metrics for Phase 15 adoption gates.")
    parser.add_argument("--llm-shadow-execute-report-path", type=Path, default=DEFAULT_EXECUTE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = LLMShadowReviewRequest(
        llm_shadow_execute_report_path=str(args.llm_shadow_execute_report_path),
        output_dir=str(args.output_dir),
    )
    report = LLMShadowReviewBuilder().build(request)
    print(
        json.dumps(
            {
                "reviewed_count": len(report.record_reviews),
                "role_recommendations": {
                    item.shadow_kind: item.adoption_recommendation for item in report.role_reviews
                },
                "review_report_path": str(Path(args.output_dir) / "llm_shadow_review_report.json"),
                "adoption_gate_report_path": str(Path(args.output_dir) / "llm_adoption_gate_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
