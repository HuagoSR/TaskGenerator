import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_promotion_postmortem import (  # noqa: E402
    Phase15CloseoutBuilder,
    Phase15CloseoutRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_AB_REPORT = PHASE15 / "ab_experiment" / "phase15_ab_experiment_report.json"
DEFAULT_QUEUE_REPORT = PHASE15 / "clean_eval_queue" / "phase15_clean_eval_queue_report.json"
DEFAULT_ATTEMPTED_EVAL = PHASE15 / "clean_eval_runs" / "baseline_case01_gpt4omini" / "rw_task_eval_run_report.json"
DEFAULT_DASHBOARD = PHASE15 / "production_impact" / "reform_dashboard" / "production_dashboard_report.json"
DEFAULT_READINESS = PHASE15 / "production_impact" / "reform_dashboard" / "release_readiness_report.json"
DEFAULT_OUTPUT = PHASE15 / "closeout"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 15 promotion proposal and postmortem reports.")
    parser.add_argument("--ab-experiment-report-path", type=Path, default=DEFAULT_AB_REPORT)
    parser.add_argument("--clean-eval-queue-report-path", type=Path, default=DEFAULT_QUEUE_REPORT)
    parser.add_argument("--attempted-eval-run-report-path", type=Path, default=DEFAULT_ATTEMPTED_EVAL)
    parser.add_argument("--production-dashboard-report-path", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--release-readiness-report-path", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = Phase15CloseoutRequest(
        ab_experiment_report_path=str(args.ab_experiment_report_path),
        clean_eval_queue_report_path=str(args.clean_eval_queue_report_path),
        attempted_eval_run_report_path=str(args.attempted_eval_run_report_path),
        production_dashboard_report_path=str(args.production_dashboard_report_path),
        release_readiness_report_path=str(args.release_readiness_report_path),
        output_dir=str(args.output_dir),
    )
    proposal, postmortem = Phase15CloseoutBuilder().build(request)
    print(
        json.dumps(
            {
                "promotion_recommendation": proposal.recommendation,
                "phase15_decision": postmortem.phase15_decision,
                "blocking_reasons": postmortem.blocking_reasons,
                "promotion_report_path": str(Path(args.output_dir) / "phase15_promotion_proposal.json"),
                "postmortem_report_path": str(Path(args.output_dir) / "phase15_postmortem_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
