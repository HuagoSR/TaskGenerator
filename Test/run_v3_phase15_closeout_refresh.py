import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_closeout_refresh import (  # noqa: E402
    Phase15CloseoutRefreshRequest,
    Phase15CloseoutRefresher,
)


PHASE15 = ROOT / "artifacts" / "phase15"


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Phase 15 closeout state after external eval results are copied back.")
    parser.add_argument("--output-dir", type=Path, default=PHASE15 / "closeout_refresh")
    parser.add_argument("--runbook-path", type=Path, default=PHASE15 / "external_eval_runbook" / "phase15_external_eval_runbook.json")
    parser.add_argument("--permitted-eval-bundle-report-path", type=Path, default=PHASE15 / "permitted_eval_bundle" / "phase15_permitted_eval_bundle_report.json")
    parser.add_argument("--external-results-path", type=Path, default=PHASE15 / "external_eval_import" / "phase15_external_eval_results.json")
    parser.add_argument("--external-import-output-dir", type=Path, default=PHASE15 / "external_eval_import")
    parser.add_argument("--queue-report-path", type=Path, default=PHASE15 / "clean_eval_queue" / "phase15_clean_eval_queue_report.json")
    parser.add_argument("--ab-experiment-report-path", type=Path, default=PHASE15 / "ab_experiment" / "phase15_ab_experiment_report.json")
    parser.add_argument("--attempted-eval-run-report-path", type=Path, default=PHASE15 / "clean_eval_runs" / "baseline_case01_gpt4omini" / "rw_task_eval_run_report.json")
    parser.add_argument("--production-dashboard-report-path", type=Path, default=PHASE15 / "production_impact" / "reform_dashboard" / "production_dashboard_report.json")
    parser.add_argument("--production-qa-gate-report-path", type=Path, default=PHASE15 / "production_impact" / "reform_qa" / "production_qa_gate_report.json")
    parser.add_argument("--production-diversity-report-path", type=Path, default=PHASE15 / "production_impact" / "reform_diversity" / "production_batch_diversity_report.json")
    parser.add_argument("--production-impact-review-report-path", type=Path, default=PHASE15 / "production_impact" / "phase15_review" / "phase15_production_impact_review_report.json")
    parser.add_argument("--production-impact-review-output-dir", type=Path, default=PHASE15 / "production_impact" / "phase15_review")
    parser.add_argument("--release-readiness-report-path", type=Path, default=PHASE15 / "production_impact" / "reform_dashboard" / "release_readiness_report.json")
    parser.add_argument("--closeout-output-dir", type=Path, default=PHASE15 / "closeout")
    parser.add_argument("--completion-audit-output-dir", type=Path, default=PHASE15 / "completion_audit")
    parser.add_argument("--local-status-output-dir", type=Path, default=PHASE15 / "local_status")
    parser.add_argument("--external-eval-readiness-report-path", type=Path, default=PHASE15 / "external_eval_readiness" / "phase15_external_eval_readiness_report.json")
    parser.add_argument("--external-eval-script-path", type=Path, default=PHASE15 / "external_eval_runbook" / "run_phase15_first_pair_external_eval.ps1")
    parser.add_argument("--baseline-manifest-path", type=Path, default=PHASE15 / "baseline" / "phase15_baseline_manifest.json")
    parser.add_argument("--llm-candidate-layer-report-path", type=Path, default=PHASE15 / "llm_candidate_layer" / "llm_candidate_layer_report.json")
    parser.add_argument("--gap-autopsy-report-path", type=Path, default=PHASE15 / "gap_autopsy" / "generated_task_gap_autopsy_report.json")
    parser.add_argument("--pattern-library-report-path", type=Path, default=PHASE15 / "pattern_library" / "gdpval_productive_complexity_pattern_library.json")
    parser.add_argument("--generator-reform-spec-path", type=Path, default=PHASE15 / "generator_reform" / "evidence_to_deliverable_reform_spec.json")
    parser.add_argument("--require-model", action="append", default=None)
    parser.add_argument("--require-case", action="append", default=None)
    parser.add_argument(
        "--external-eval-authorization-status",
        default="tenant_policy_denied",
        choices=[
            "not_recorded",
            "approval_rejected",
            "requires_explicit_user_approval",
            "approved",
            "tenant_policy_denied",
        ],
    )
    args = parser.parse_args()

    request = Phase15CloseoutRefreshRequest(
        output_dir=str(args.output_dir),
        runbook_path=str(args.runbook_path),
        permitted_eval_bundle_report_path=str(args.permitted_eval_bundle_report_path),
        external_results_path=str(args.external_results_path),
        external_import_output_dir=str(args.external_import_output_dir),
        queue_report_path=str(args.queue_report_path),
        ab_experiment_report_path=str(args.ab_experiment_report_path),
        attempted_eval_run_report_path=str(args.attempted_eval_run_report_path),
        production_dashboard_report_path=str(args.production_dashboard_report_path),
        production_qa_gate_report_path=str(args.production_qa_gate_report_path),
        production_diversity_report_path=str(args.production_diversity_report_path),
        production_impact_review_report_path=str(args.production_impact_review_report_path),
        production_impact_review_output_dir=str(args.production_impact_review_output_dir),
        release_readiness_report_path=str(args.release_readiness_report_path),
        closeout_output_dir=str(args.closeout_output_dir),
        completion_audit_output_dir=str(args.completion_audit_output_dir),
        local_status_output_dir=str(args.local_status_output_dir),
        external_eval_readiness_report_path=str(args.external_eval_readiness_report_path),
        external_eval_script_path=str(args.external_eval_script_path),
        baseline_manifest_path=str(args.baseline_manifest_path),
        llm_candidate_layer_report_path=str(args.llm_candidate_layer_report_path),
        gap_autopsy_report_path=str(args.gap_autopsy_report_path),
        pattern_library_report_path=str(args.pattern_library_report_path),
        generator_reform_spec_path=str(args.generator_reform_spec_path),
        require_models=args.require_model or ["gpt-4o-mini"],
        require_cases=args.require_case or ["pipeline_b_batch_01_evidence_to_deliverable"],
        external_eval_authorization_status=args.external_eval_authorization_status,
    )
    report = Phase15CloseoutRefresher().build(request)
    print(
        json.dumps(
            {
                "final_status": report.final_status,
                "next_actions": report.next_actions,
                "report_path": str(Path(args.output_dir) / "phase15_closeout_refresh_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
