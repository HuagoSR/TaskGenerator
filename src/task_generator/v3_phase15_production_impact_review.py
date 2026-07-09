from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


ProductionImpactDecision = Literal[
    "review_complete_keep_experiment_flag",
    "review_complete_release_candidate",
    "blocked_by_structural_regression",
    "insufficient_evidence",
]


class Phase15ProductionImpactReviewRequest(BaseModel):
    production_dashboard_report_path: str
    production_qa_gate_report_path: str
    production_diversity_report_path: str
    output_dir: str


class Phase15ProductionImpactReviewReport(BaseModel):
    report_version: str = "v3.phase15_production_impact_review.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15ProductionImpactReviewRequest
    decision: ProductionImpactDecision
    release_ready: bool = False
    structural_regression_detected: bool = False
    explicit_review_completed: bool = False
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    blocking_reasons: List[str] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15ProductionImpactReviewer:
    """Review Phase 15 reform production impact without silently promoting release state."""

    def build(self, request: Phase15ProductionImpactReviewRequest) -> Phase15ProductionImpactReviewReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        dashboard = load_json_file(request.production_dashboard_report_path)
        qa = load_json_file(request.production_qa_gate_report_path)
        diversity = load_json_file(request.production_diversity_report_path)

        summary = dashboard.get("summary") or {}
        qa_summary = qa.get("summary") or {}
        diversity_diagnostics = diversity.get("diagnostics") or {}
        blocking_reasons = self._blocking_reasons(summary, qa_summary)
        review_reasons = self._review_reasons(summary, qa_summary, diversity_diagnostics)
        decision = self._decision(summary, blocking_reasons, review_reasons)
        report = Phase15ProductionImpactReviewReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            decision=decision,
            release_ready=decision == "review_complete_release_candidate",
            structural_regression_detected=bool(blocking_reasons),
            explicit_review_completed=decision in {"review_complete_keep_experiment_flag", "review_complete_release_candidate"},
            evidence_summary={
                "case_count": summary.get("case_count"),
                "candidate_ready_count": summary.get("candidate_ready_count"),
                "production_ready_count": summary.get("production_ready_count"),
                "review_required_count": summary.get("review_required_count"),
                "blocked_count": summary.get("blocked_count"),
                "verifier_pass_rate": summary.get("verifier_pass_rate"),
                "export_compatible_rate": summary.get("export_compatible_rate"),
                "workflow_context_fit_distribution": dashboard.get("workflow_context_fit_distribution"),
                "real_worldness_distribution": dashboard.get("real_worldness_distribution"),
                "qa_decision_distribution": dashboard.get("qa_decision_distribution"),
                "qa_finding_code_counts": qa_summary.get("finding_code_counts"),
                "diversity_warnings": diversity_diagnostics.get("warnings") or [],
            },
            blocking_reasons=blocking_reasons,
            review_reasons=review_reasons,
            next_actions=self._next_actions(decision),
            notes=[
                "This review proves production-impact review was performed; it does not mutate release or default-generator state.",
                "review_complete_keep_experiment_flag is a governed non-release decision, not production approval.",
                "Release promotion still requires clean eval evidence and an explicit reviewed promotion decision.",
            ],
        )
        (output_dir / "phase15_production_impact_review_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _blocking_reasons(self, summary: Dict[str, Any], qa_summary: Dict[str, Any]) -> List[str]:
        reasons: List[str] = []
        if int(summary.get("case_count") or 0) == 0:
            reasons.append("no_reform_cases_reviewed")
        if int(summary.get("candidate_ready_count") or 0) < 4:
            reasons.append("candidate_ready_count_below_phase15_review_floor")
        if int(summary.get("blocked_count") or 0) > 0:
            reasons.append("production_dashboard_blocked_cases_present")
        if int(qa_summary.get("blocked_count") or 0) > 0:
            reasons.append("production_qa_blocked_cases_present")
        if float(summary.get("verifier_pass_rate") or 0.0) < 1.0:
            reasons.append("verifier_pass_rate_below_one")
        if float(summary.get("export_compatible_rate") or 0.0) < 1.0:
            reasons.append("export_compatible_rate_below_one")
        return reasons

    def _review_reasons(
        self,
        summary: Dict[str, Any],
        qa_summary: Dict[str, Any],
        diversity_diagnostics: Dict[str, Any],
    ) -> List[str]:
        reasons: List[str] = []
        if int(summary.get("production_ready_count") or 0) == 0:
            reasons.append("no_governed_production_ready_cases")
        if int(summary.get("review_required_count") or 0) > 0:
            reasons.append("qa_cases_still_review_required")
        finding_counts = qa_summary.get("finding_code_counts") or {}
        if finding_counts.get("global_validity_diagnostic_only"):
            reasons.append("global_validity_remains_diagnostic_only")
        if diversity_diagnostics.get("warnings"):
            reasons.append("batch_diversity_warnings_require_scaleup_review")
        return sorted(set(reasons))

    def _decision(
        self,
        summary: Dict[str, Any],
        blocking_reasons: List[str],
        review_reasons: List[str],
    ) -> ProductionImpactDecision:
        if blocking_reasons:
            return "blocked_by_structural_regression"
        if int(summary.get("case_count") or 0) == 0:
            return "insufficient_evidence"
        if not review_reasons and int(summary.get("production_ready_count") or 0) > 0:
            return "review_complete_release_candidate"
        return "review_complete_keep_experiment_flag"

    def _next_actions(self, decision: ProductionImpactDecision) -> List[str]:
        if decision == "blocked_by_structural_regression":
            return ["Fix structural production blockers before continuing Phase 15 promotion review."]
        if decision == "review_complete_release_candidate":
            return ["Use clean paired eval evidence and explicit promotion review before any release/default-chain change."]
        if decision == "review_complete_keep_experiment_flag":
            return [
                "Keep the Phase 15 reform behind the explicit experiment flag.",
                "Use clean paired eval evidence before deciding promotion or rollback.",
                "Review diagnostic-only validity and diversity concentration before release packaging.",
            ]
        return ["Regenerate the reform production dashboard and QA reports with at least four reform cases."]
