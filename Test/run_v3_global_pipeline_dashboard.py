import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_global_pipeline_dashboard import GlobalPipelineDashboardBuilder  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_BATCH_REPORT = SCRATCH / "batch_runner_phase7_verifier_smoke" / "pipeline_b_batch_report.json"
DEFAULT_BATCH_FEEDBACK_REPORT = (
    SCRATCH / "batch_feedback_phase7_verifier_aware_smoke" / "pipeline_b_batch_feedback_report.json"
)
DEFAULT_SUBSTRATE_AUDIT_REPORT = (
    SCRATCH / "pipeline_a_substrate_audit_smoke" / "pipeline_a_substrate_audit_report.json"
)
DEFAULT_TYPED_RESOURCE_PATCH_PROPOSAL_REPORT = (
    SCRATCH / "typed_resource_patch_proposal_smoke" / "typed_resource_patch_proposal_report.json"
)
DEFAULT_PROMOTION_REPORT = SCRATCH / "promotion_manager_smoke" / "promotion_report.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "global_pipeline_dashboard_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a global pipeline dashboard from existing report-first artifacts."
    )
    parser.add_argument("--batch-report", type=Path, default=DEFAULT_BATCH_REPORT)
    parser.add_argument("--batch-feedback-report", type=Path, default=DEFAULT_BATCH_FEEDBACK_REPORT)
    parser.add_argument("--substrate-audit-report", type=Path, default=DEFAULT_SUBSTRATE_AUDIT_REPORT)
    parser.add_argument(
        "--typed-resource-patch-proposal-report",
        type=Path,
        default=DEFAULT_TYPED_RESOURCE_PATCH_PROPOSAL_REPORT,
    )
    parser.add_argument("--promotion-report", type=Path, default=DEFAULT_PROMOTION_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    promotion_report = args.promotion_report if args.promotion_report.exists() else None
    builder = GlobalPipelineDashboardBuilder()
    report = builder.build(
        batch_report_path=args.batch_report,
        batch_feedback_report_path=args.batch_feedback_report,
        substrate_audit_report_path=args.substrate_audit_report,
        typed_resource_patch_proposal_report_path=args.typed_resource_patch_proposal_report,
        promotion_report_path=promotion_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "global_pipeline_dashboard_report_path": str(
                    args.output_dir / "global_pipeline_dashboard_report.json"
                ),
                "case_count": report.diagnostics.case_count,
                "focus_area_count": report.diagnostics.focus_area_count,
                "snapshot_error_case_count": report.diagnostics.snapshot_error_case_count,
                "missing_promotion_report": report.diagnostics.missing_promotion_report,
                "candidate_ready_count": report.health_summary.training_evaluation_readiness.candidate_ready_count,
                "promotion_ready_count": report.health_summary.training_evaluation_readiness.promotion_ready_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
