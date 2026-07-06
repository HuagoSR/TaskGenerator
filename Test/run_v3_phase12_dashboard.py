import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase12_dashboard import Phase12DashboardBuilder  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_ROOT = SCRATCH / "phase12_hardening_phase1234_smoke_v2"
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT / "phase12_global_dashboard"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 12 global dashboard report.")
    parser.add_argument("--baseline-report", type=Path, default=DEFAULT_ROOT / "phase_12_baseline" / "phase12_baseline_report.json")
    parser.add_argument("--regression-report", type=Path, default=DEFAULT_ROOT / "phase12_candidate_ready_regression_report.json")
    parser.add_argument("--negative-control-report", type=Path, default=DEFAULT_ROOT / "phase12_negative_control_report.json")
    parser.add_argument("--substrate-hardening-report", type=Path, default=DEFAULT_ROOT / "phase12_substrate_hardening" / "phase12_substrate_audit_report.json")
    parser.add_argument("--workflow-context-review-report", type=Path, default=DEFAULT_ROOT / "phase12_workflow_context" / "phase12_workflow_context_review_report.json")
    parser.add_argument("--transition-prior-report", type=Path, default=DEFAULT_ROOT / "phase12_transition_prior_observation_report.json")
    parser.add_argument("--eval-campaign-report", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    report = Phase12DashboardBuilder().build(
        baseline_report_path=args.baseline_report,
        regression_report_path=args.regression_report,
        negative_control_report_path=args.negative_control_report,
        substrate_hardening_report_path=args.substrate_hardening_report,
        workflow_context_review_report_path=args.workflow_context_review_report,
        transition_prior_report_path=args.transition_prior_report,
        eval_campaign_report_path=args.eval_campaign_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "phase12_global_dashboard_report_path": str(args.output_dir / "phase12_global_dashboard_report.json"),
                "focus_area_count": len(report.focus_areas),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
