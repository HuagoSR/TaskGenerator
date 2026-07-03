import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_batch_feedback_analyzer import (  # noqa: E402
    PipelineBBatchFeedbackAnalyzer,
)


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_BATCH_REPORT = SCRATCH / "batch_runner_smoke" / "pipeline_b_batch_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "batch_feedback_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Pipeline B batch smoke output into report-first feedback."
    )
    parser.add_argument("--batch-report", type=Path, default=DEFAULT_BATCH_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    analyzer = PipelineBBatchFeedbackAnalyzer()
    report = analyzer.analyze(
        batch_report_path=args.batch_report,
        output_dir=args.output_dir,
    )
    top_action = report.prioritized_actions[0].title if report.prioritized_actions else None
    print(
        json.dumps(
            {
                "batch_feedback_report_path": str(args.output_dir / "pipeline_b_batch_feedback_report.json"),
                "case_count": report.diagnostics.case_count,
                "systemic_finding_count": report.diagnostics.systemic_finding_count,
                "motif_specific_finding_count": report.diagnostics.motif_specific_finding_count,
                "case_specific_finding_count": report.diagnostics.case_specific_finding_count,
                "external_eval_candidate_count": report.diagnostics.external_eval_candidate_count,
                "priority_reason_codes": report.diagnostics.priority_reason_codes,
                "top_action": top_action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
