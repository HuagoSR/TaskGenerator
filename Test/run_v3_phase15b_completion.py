import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15b_completion import (  # noqa: E402
    Phase15BCompletionBuilder,
    Phase15BCompletionRequest,
)


DEFAULT_QUEUE_DIR = ROOT / "artifacts" / "phase15" / "clean_eval_queue"
DEFAULT_RUNS_DIR = ROOT / "artifacts" / "phase15" / "clean_eval_runs"
DEFAULT_PRODUCTION_IMPACT = (
    ROOT
    / "artifacts"
    / "phase15"
    / "production_impact"
    / "phase15_review"
    / "phase15_production_impact_review_report.json"
)
DEFAULT_LLM_CANDIDATE = ROOT / "artifacts" / "phase15" / "llm_candidate_layer" / "llm_candidate_layer_report.json"
DEFAULT_EVAL_OUTPUT = ROOT / "artifacts" / "phase15" / "eval_results"
DEFAULT_AUTOPSY_OUTPUT = ROOT / "artifacts" / "phase15" / "failure_autopsy"
DEFAULT_CLOSEOUT_OUTPUT = ROOT / "artifacts" / "phase15" / "phase15b_closeout"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 15B strong-model, gap-delta, autopsy, and closeout reports.")
    parser.add_argument("--clean-eval-queue-dir", type=Path, default=DEFAULT_QUEUE_DIR)
    parser.add_argument("--clean-eval-runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--production-impact-report", type=Path, default=DEFAULT_PRODUCTION_IMPACT)
    parser.add_argument("--llm-candidate-report", type=Path, default=DEFAULT_LLM_CANDIDATE)
    parser.add_argument("--eval-output-dir", type=Path, default=DEFAULT_EVAL_OUTPUT)
    parser.add_argument("--autopsy-output-dir", type=Path, default=DEFAULT_AUTOPSY_OUTPUT)
    parser.add_argument("--closeout-output-dir", type=Path, default=DEFAULT_CLOSEOUT_OUTPUT)
    args = parser.parse_args()

    report = Phase15BCompletionBuilder().build(
        Phase15BCompletionRequest(
            clean_eval_queue_dir=str(args.clean_eval_queue_dir),
            clean_eval_runs_dir=str(args.clean_eval_runs_dir),
            production_impact_report_path=str(args.production_impact_report),
            llm_candidate_report_path=str(args.llm_candidate_report),
            eval_output_dir=str(args.eval_output_dir),
            autopsy_output_dir=str(args.autopsy_output_dir),
            closeout_output_dir=str(args.closeout_output_dir),
        )
    )
    print(
        json.dumps(
            {
                "phase15b_decision": report.summary.get("phase15b_decision"),
                "promotion_decision": report.summary.get("promotion_decision"),
                "score_record_count": report.summary.get("score_record_count"),
                "strong_record_count": report.summary.get("strong_record_count"),
                "case_count": report.summary.get("case_count"),
                "mean_gap_delta": report.summary.get("mean_gap_delta"),
                "positive_gap_delta_case_count": report.summary.get("positive_gap_delta_case_count"),
                "negative_gap_delta_case_count": report.summary.get("negative_gap_delta_case_count"),
                "strong_model_eval_report_path": report.strong_model_eval_report_path,
                "gap_delta_report_path": report.gap_delta_report_path,
                "failure_autopsy_report_path": report.failure_autopsy_report_path,
                "postmortem_report_path": report.postmortem_report_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
