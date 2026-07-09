from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from task_generator.v3_phase15_completion_audit import (
    Phase15CompletionAuditRequest,
    Phase15CompletionAuditor,
)
from task_generator.v3_phase15_external_eval_importer import (
    Phase15ExternalEvalImportRequest,
    Phase15ExternalEvalImporter,
)
from task_generator.v3_phase15_external_eval_result_builder import (
    Phase15ExternalEvalResultBuilder,
    Phase15ExternalEvalResultBuilderRequest,
)
from task_generator.v3_phase15_local_status import (
    Phase15LocalStatusBuilder,
    Phase15LocalStatusRequest,
)
from task_generator.v3_phase15_promotion_postmortem import (
    Phase15CloseoutBuilder,
    Phase15CloseoutRequest,
)
from task_generator.v3_phase15_production_impact_review import (
    Phase15ProductionImpactReviewRequest,
    Phase15ProductionImpactReviewer,
)


class Phase15CloseoutRefreshRequest(BaseModel):
    output_dir: str
    runbook_path: str
    permitted_eval_bundle_report_path: str
    external_results_path: str
    external_import_output_dir: str
    queue_report_path: str
    ab_experiment_report_path: str
    attempted_eval_run_report_path: str
    production_dashboard_report_path: str
    production_qa_gate_report_path: str
    production_diversity_report_path: str
    production_impact_review_report_path: str
    production_impact_review_output_dir: str
    release_readiness_report_path: str
    closeout_output_dir: str
    completion_audit_output_dir: str
    local_status_output_dir: str
    external_eval_readiness_report_path: str
    external_eval_script_path: str
    baseline_manifest_path: str
    llm_candidate_layer_report_path: str
    gap_autopsy_report_path: str
    pattern_library_report_path: str
    generator_reform_spec_path: str
    require_models: List[str] = Field(default_factory=lambda: ["gpt-4o-mini"])
    require_cases: List[str] = Field(default_factory=lambda: ["pipeline_b_batch_01_evidence_to_deliverable"])
    external_eval_authorization_status: str = "tenant_policy_denied"


class Phase15CloseoutRefreshReport(BaseModel):
    report_version: str = "v3.phase15_closeout_refresh.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15CloseoutRefreshRequest
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    final_status: Dict[str, Any] = Field(default_factory=dict)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15CloseoutRefresher:
    """Refresh Phase 15 closeout reports after external eval results are copied back."""

    def build(self, request: Phase15CloseoutRefreshRequest) -> Phase15CloseoutRefreshReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result_builder_report = Phase15ExternalEvalResultBuilder().build(
            Phase15ExternalEvalResultBuilderRequest(
                runbook_path=request.runbook_path,
                queue_report_path=request.queue_report_path,
                output_dir=request.external_import_output_dir,
                result_output_path=request.external_results_path,
                permitted_eval_bundle_report_path=request.permitted_eval_bundle_report_path,
                require_models=request.require_models,
                require_cases=request.require_cases,
            )
        )
        import_report = Phase15ExternalEvalImporter().build(
            Phase15ExternalEvalImportRequest(
                queue_report_path=request.queue_report_path,
                external_results_path=request.external_results_path,
                output_dir=request.external_import_output_dir,
                require_models=request.require_models,
                require_cases=request.require_cases,
            )
        )
        production_impact_review = Phase15ProductionImpactReviewer().build(
            Phase15ProductionImpactReviewRequest(
                production_dashboard_report_path=request.production_dashboard_report_path,
                production_qa_gate_report_path=request.production_qa_gate_report_path,
                production_diversity_report_path=request.production_diversity_report_path,
                output_dir=request.production_impact_review_output_dir,
            )
        )
        proposal, postmortem = Phase15CloseoutBuilder().build(
            Phase15CloseoutRequest(
                ab_experiment_report_path=request.ab_experiment_report_path,
                clean_eval_queue_report_path=request.queue_report_path,
                attempted_eval_run_report_path=request.attempted_eval_run_report_path,
                external_eval_import_report_path=str(Path(request.external_import_output_dir) / "phase15_external_eval_import_report.json"),
                production_dashboard_report_path=request.production_dashboard_report_path,
                release_readiness_report_path=request.release_readiness_report_path,
                output_dir=request.closeout_output_dir,
                external_eval_authorization_status=request.external_eval_authorization_status,
            )
        )
        audit_report = Phase15CompletionAuditor().build(
            Phase15CompletionAuditRequest(
                baseline_manifest_path=request.baseline_manifest_path,
                llm_candidate_layer_report_path=request.llm_candidate_layer_report_path,
                gap_autopsy_report_path=request.gap_autopsy_report_path,
                pattern_library_report_path=request.pattern_library_report_path,
                generator_reform_spec_path=request.generator_reform_spec_path,
                ab_experiment_report_path=request.ab_experiment_report_path,
                clean_eval_queue_report_path=request.queue_report_path,
                external_eval_import_report_path=str(Path(request.external_import_output_dir) / "phase15_external_eval_import_report.json"),
                production_dashboard_report_path=request.production_dashboard_report_path,
                production_impact_review_report_path=request.production_impact_review_report_path,
                phase15_postmortem_report_path=str(Path(request.closeout_output_dir) / "phase15_postmortem_report.json"),
                output_dir=request.completion_audit_output_dir,
            )
        )
        local_status = Phase15LocalStatusBuilder().build(
            Phase15LocalStatusRequest(
                completion_audit_report_path=str(Path(request.completion_audit_output_dir) / "phase15_completion_audit_report.json"),
                postmortem_report_path=str(Path(request.closeout_output_dir) / "phase15_postmortem_report.json"),
                external_eval_readiness_report_path=request.external_eval_readiness_report_path,
                permitted_eval_bundle_report_path=request.permitted_eval_bundle_report_path,
                external_eval_import_report_path=str(Path(request.external_import_output_dir) / "phase15_external_eval_import_report.json"),
                external_eval_runbook_path=request.runbook_path,
                external_eval_script_path=request.external_eval_script_path,
                output_dir=request.local_status_output_dir,
            )
        )

        report = Phase15CloseoutRefreshReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            steps=[
                {"step": "external_eval_result_builder", "summary": result_builder_report.summary},
                {
                    "step": "external_eval_importer",
                    "import_status": import_report.import_status,
                    "summary": import_report.summary,
                    "blocking_reasons": import_report.blocking_reasons,
                },
                {
                    "step": "production_impact_review",
                    "decision": production_impact_review.decision,
                    "explicit_review_completed": production_impact_review.explicit_review_completed,
                    "structural_regression_detected": production_impact_review.structural_regression_detected,
                    "review_reasons": production_impact_review.review_reasons,
                    "blocking_reasons": production_impact_review.blocking_reasons,
                },
                {
                    "step": "promotion_postmortem",
                    "promotion_recommendation": proposal.recommendation,
                    "phase15_decision": postmortem.phase15_decision,
                    "blocking_reasons": postmortem.blocking_reasons,
                },
                {
                    "step": "completion_audit",
                    "completion_status": audit_report.completion_status,
                    "summary": audit_report.summary,
                    "final_blockers": audit_report.final_blockers,
                },
                {
                    "step": "local_status",
                    "local_status": local_status.local_status,
                    "external_eval_import_status": local_status.external_eval_import_status,
                    "tenant_policy_status": local_status.tenant_policy_status,
                    "blocking_reasons": local_status.blocking_reasons,
                },
            ],
            final_status={
                "local_status": local_status.local_status,
                "phase15_completion_status": local_status.phase15_completion_status,
                "phase15_decision": local_status.phase15_decision,
                "external_eval_import_status": local_status.external_eval_import_status,
                "promotion_recommendation": proposal.recommendation,
            },
            next_actions=self._next_actions(local_status.local_status, audit_report.completion_status, import_report.import_status),
            notes=[
                "This refresh runner does not call external APIs.",
                "It is intended to be run after permitted-environment eval results or bundled grades are copied back.",
                "A completed result builder record is still only sanitized eval evidence; importer, postmortem, and audit reports remain the closeout gates.",
            ],
        )
        (output_dir / "phase15_closeout_refresh_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _next_actions(self, local_status: str, completion_status: str, import_status: str) -> List[str]:
        if completion_status == "complete":
            return ["Review the promotion proposal and mark Phase 15 complete only if all release/promotion expectations are satisfied."]
        if import_status != "ready_for_closeout":
            return ["Run the portable permitted-eval bundle in an allowed environment, copy back grades/results, then rerun this refresh."]
        if local_status != "ready_for_local_followup":
            return ["Inspect Phase 15 completion audit blockers and resolve production QA or postmortem gaps."]
        return ["Inspect the refreshed audit and postmortem before any default-chain promotion."]
