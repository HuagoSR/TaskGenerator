import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_llm_impact_evaluation import (  # noqa: E402
    LLMImpactEvaluationRequest,
    LLMImpactEvaluator,
)


DEFAULT_SHADOW_DIR = ROOT / "artifacts" / "phase14" / "llm_shadow"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "llm_impact"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Phase 14 LLM shadow readiness and adoption recommendation.")
    parser.add_argument("--llm-shadow-dir", type=Path, default=DEFAULT_SHADOW_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    request = LLMImpactEvaluationRequest(
        llm_shadow_dir=str(args.llm_shadow_dir),
        output_dir=str(args.output_dir),
    )
    report = LLMImpactEvaluator().build(request)
    print(
        json.dumps(
            {
                "shadow_kind_count": report.shadow_kind_count,
                "total_prepared_task_shadows": report.total_prepared_task_shadows,
                "total_awaiting_llm_output": report.total_awaiting_llm_output,
                "total_completed_metric_count": report.total_completed_metric_count,
                "impact_readiness": report.impact_readiness,
                "report_path": str(Path(args.output_dir) / "llm_impact_evaluation_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
