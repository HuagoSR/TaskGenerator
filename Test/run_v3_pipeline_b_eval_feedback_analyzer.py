import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_eval_feedback_analyzer import (  # noqa: E402
    PipelineBEvalFeedbackAnalyzer,
)


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_EVAL_SUMMARY = SCRATCH / "rw_task_eval_summary_smoke" / "pipeline_b_eval_summary_report.json"
DEFAULT_RUBRIC = SCRATCH / "rubric_smoke" / "rubric.json"
DEFAULT_ANNOTATION = SCRATCH / "training_annotation_smoke" / "training_annotation.json"
DEFAULT_TEACHER_REPORT = SCRATCH / "teacher_runner_smoke" / "teacher_runner_report.json"
DEFAULT_QUALITY_REPORT = SCRATCH / "quality_gate_smoke" / "pipeline_b_quality_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "eval_feedback_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze draft rw-task eval output and convert it into report-only Pipeline B improvement feedback."
    )
    parser.add_argument("--eval-summary-report", type=Path, default=DEFAULT_EVAL_SUMMARY)
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--training-annotation", type=Path, default=DEFAULT_ANNOTATION)
    parser.add_argument("--teacher-runner-report", type=Path, default=DEFAULT_TEACHER_REPORT)
    parser.add_argument("--quality-gate-report", type=Path, default=DEFAULT_QUALITY_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    analyzer = PipelineBEvalFeedbackAnalyzer()
    report = analyzer.analyze(
        eval_summary_report_path=args.eval_summary_report,
        rubric_path=args.rubric,
        training_annotation_path=args.training_annotation,
        teacher_runner_report_path=args.teacher_runner_report,
        quality_gate_report_path=args.quality_gate_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "case_id": report.case_id,
                "feedback_status": report.feedback_status,
                "eval_evidence_use": report.eval_evidence_use,
                "quality_gate_decision": report.quality_gate_decision,
                "low_scoring_criterion_count": len(report.low_scoring_criteria),
                "pipeline_b_action_count": len(report.pipeline_b_actions),
                "pipeline_a_feedback_count": len(report.pipeline_a_feedback),
                "candidate_ready_blocker_count": len(report.candidate_ready_blockers),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
