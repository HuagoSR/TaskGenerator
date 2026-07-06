from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class Phase12DashboardRequest(BaseModel):
    baseline_report_path: str
    regression_report_path: str
    negative_control_report_path: str
    substrate_hardening_report_path: str
    workflow_context_review_report_path: str
    eval_campaign_report_path: Optional[str] = None
    transition_prior_report_path: str
    output_dir: str


class Phase12DashboardSummary(BaseModel):
    candidate_ready_before: int = 0
    candidate_ready_after: int = 0
    verifier_pass_before: int = 0
    verifier_pass_after: int = 0
    negative_control_pass_rate: float = 0.0
    applied_promotion_count: int = 0
    rollback_record_count: int = 0
    missing_typed_resource_skill_count_before: int = 0
    missing_typed_resource_skill_count_after: int = 0
    workflow_improved_case_count: int = 0
    workflow_degraded_case_count: int = 0
    eval_selected_case_count: int = 0
    eval_summary_completion_rate: float = 0.0
    eval_usable_summary_rate: float = 0.0
    transition_observation_count: int = 0


class Phase12DashboardFocus(BaseModel):
    focus_id: str
    title: str
    owner_layer: str
    rationale: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    recommended_next_step: str


class Phase12GlobalDashboardReport(BaseModel):
    phase12_global_dashboard_version: str = "v1"
    request: Phase12DashboardRequest
    summary: Phase12DashboardSummary
    focus_areas: List[Phase12DashboardFocus] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12DashboardBuilder:
    def build(
        self,
        baseline_report_path: str | Path,
        regression_report_path: str | Path,
        negative_control_report_path: str | Path,
        substrate_hardening_report_path: str | Path,
        workflow_context_review_report_path: str | Path,
        transition_prior_report_path: str | Path,
        output_dir: str | Path,
        eval_campaign_report_path: str | Path | None = None,
    ) -> Phase12GlobalDashboardReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = Phase12DashboardRequest(
            baseline_report_path=str(baseline_report_path),
            regression_report_path=str(regression_report_path),
            negative_control_report_path=str(negative_control_report_path),
            substrate_hardening_report_path=str(substrate_hardening_report_path),
            workflow_context_review_report_path=str(workflow_context_review_report_path),
            eval_campaign_report_path=str(eval_campaign_report_path) if eval_campaign_report_path else None,
            transition_prior_report_path=str(transition_prior_report_path),
            output_dir=str(output_path),
        )
        baseline = load_json_file(str(baseline_report_path))
        regression = load_json_file(str(regression_report_path))
        negative = load_json_file(str(negative_control_report_path))
        substrate = load_json_file(str(substrate_hardening_report_path))
        workflow = load_json_file(str(workflow_context_review_report_path))
        transition = load_json_file(str(transition_prior_report_path))
        eval_campaign = load_json_file(str(eval_campaign_report_path)) if eval_campaign_report_path else None

        negative_total = int(negative.get("result_count") or 0)
        negative_passed = int(negative.get("passed_count") or 0)
        summary = Phase12DashboardSummary(
            candidate_ready_before=int(baseline.get("baseline_candidate_ready_count") or 0),
            candidate_ready_after=int((regression.get("summary") or {}).get("candidate_ready_count") or 0),
            verifier_pass_before=int(baseline.get("baseline_verifier_pass_count") or 0),
            verifier_pass_after=int((regression.get("summary") or {}).get("verifier_pass_count") or 0),
            negative_control_pass_rate=round((negative_passed / negative_total), 4) if negative_total else 0.0,
            applied_promotion_count=int((substrate.get("summary") or {}).get("applied_promotion_count") or 0),
            rollback_record_count=int((substrate.get("summary") or {}).get("rollback_record_count") or 0),
            missing_typed_resource_skill_count_before=int(
                (substrate.get("summary") or {}).get("pre_missing_typed_resource_skill_count") or 0
            ),
            missing_typed_resource_skill_count_after=int(
                (substrate.get("summary") or {}).get("post_missing_typed_resource_skill_count") or 0
            ),
            workflow_improved_case_count=int(
                (load_json_file(str(Path(workflow_context_review_report_path).parent / "phase12_real_worldness_comparison_report.json")).get("improved_case_count") or 0)
            ),
            workflow_degraded_case_count=int(
                (load_json_file(str(Path(workflow_context_review_report_path).parent / "phase12_real_worldness_comparison_report.json")).get("degraded_case_count") or 0)
            ),
            eval_selected_case_count=int((eval_campaign or {}).get("summary", {}).get("selected_case_count") or 0),
            eval_summary_completion_rate=float((eval_campaign or {}).get("summary", {}).get("summary_completion_rate") or 0.0),
            eval_usable_summary_rate=float((eval_campaign or {}).get("summary", {}).get("usable_summary_rate") or 0.0),
            transition_observation_count=int((transition.get("diagnostics") or {}).get("observation_count") or 0),
        )
        focus_areas = self._focus_areas(summary=summary, eval_campaign=eval_campaign)
        report = Phase12GlobalDashboardReport(
            request=request,
            summary=summary,
            focus_areas=focus_areas,
            notes=[
                "Phase 12 dashboard is a phase-scoped evidence aggregator over regression, gate hardness, substrate, workflow, eval, and transition observations.",
                "It is intended for hardening decisions, not as a replacement for the lower-level batch or verifier reports.",
            ],
        )
        (output_path / "phase12_global_dashboard_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _focus_areas(
        self,
        summary: Phase12DashboardSummary,
        eval_campaign: Optional[Dict[str, Any]],
    ) -> List[Phase12DashboardFocus]:
        focus: List[Phase12DashboardFocus] = []
        if summary.missing_typed_resource_skill_count_after > 0:
            focus.append(
                Phase12DashboardFocus(
                    focus_id="focus_phase12_pipeline_a_remaining_gaps",
                    title="Continue Pipeline A substrate repair on remaining typed-resource gaps.",
                    owner_layer="pipeline_a",
                    rationale="Phase 12 reduced missing typed resources but did not eliminate them.",
                    evidence={
                        "before": summary.missing_typed_resource_skill_count_before,
                        "after": summary.missing_typed_resource_skill_count_after,
                    },
                    recommended_next_step="Collect new source evidence for Tier D skills and review whether additional Tier A/B patches can be promoted safely.",
                )
            )
        if summary.eval_selected_case_count == 0:
            focus.append(
                Phase12DashboardFocus(
                    focus_id="focus_phase12_eval_campaign_missing",
                    title="Run the guarded executed eval mini-campaign.",
                    owner_layer="evaluation",
                    rationale="Phase 12 cannot close without at least one executed mini-campaign.",
                    evidence={},
                    recommended_next_step="Select three candidate_ready, verifier-pass, export-compatible cases and run the two-model campaign.",
                )
            )
        elif summary.eval_summary_completion_rate < 0.8:
            focus.append(
                Phase12DashboardFocus(
                    focus_id="focus_phase12_eval_robustness",
                    title="Stabilize executed evaluation evidence.",
                    owner_layer="evaluation",
                    rationale="The current mini-campaign did not achieve the desired summary completion rate.",
                    evidence={
                        "summary_completion_rate": summary.eval_summary_completion_rate,
                        "usable_summary_rate": summary.eval_usable_summary_rate,
                    },
                    recommended_next_step="Inspect runner/grade/summary failures before treating the eval evidence as Phase 12-complete.",
                )
            )
        return focus
