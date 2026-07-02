import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_rw_task_eval_summarizer import RwTaskEvalSummarizer  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_RUN_REPORT = (
    SCRATCH
    / "rw_task_eval_run_real_smoke_e2b_escalated"
    / "rw_task_eval_run_report.json"
)
DEFAULT_GRADE_DIR = SCRATCH / "rw_task_eval_input_smoke_e2b_grades"
DEFAULT_OUTPUT_DIR = SCRATCH / "rw_task_eval_summary_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize a V3 rw-task eval runner report and grader output without mutating Pipeline B state."
    )
    parser.add_argument("--run-report", type=Path, default=DEFAULT_RUN_REPORT)
    parser.add_argument("--grade-report", type=Path, default=None)
    parser.add_argument("--grade-dir", type=Path, default=DEFAULT_GRADE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    summarizer = RwTaskEvalSummarizer()
    report = summarizer.summarize(
        run_report_path=args.run_report,
        grade_report_path=args.grade_report,
        grade_dir=args.grade_dir,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "case_id": report.case_id,
                "summary_status": report.summary_status,
                "evidence_use": report.evidence_use,
                "run_status": report.run_status,
                "toolchain_completed": report.toolchain_completed,
                "sample_count": report.sample_count,
                "successful_sample_count": report.successful_sample_count,
                "average_score_ratio": report.average_score_ratio,
                "warning_reason_codes": report.warning_reason_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
