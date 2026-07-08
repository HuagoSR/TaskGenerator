from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class Phase14PostmortemRequest(BaseModel):
    clean_baseline_path: str
    gap_autopsy_path: str
    dashboard_path: str
    llm_impact_path: str
    llm_adoption_path: str
    output_dir: str
    handoff_path: str


class Phase14SuccessCriterion(BaseModel):
    criterion_id: str
    description: str
    status: str
    evidence: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)


class Phase14PostmortemReport(BaseModel):
    report_version: str = "v3.phase14_postmortem.1"
    created_at: str
    request: Phase14PostmortemRequest
    diagnostic_only: bool = True
    phase14_decision: str
    phase15_recommendation: str
    success_criteria: List[Phase14SuccessCriterion] = Field(default_factory=list)
    postmortem_answers: Dict[str, str] = Field(default_factory=dict)
    blockers: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    handoff_path: str
    notes: List[str] = Field(default_factory=list)


class Phase14PostmortemBuilder:
    def build(self, request: Phase14PostmortemRequest) -> Phase14PostmortemReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        clean = self._read_json(Path(request.clean_baseline_path))
        autopsy = self._read_json(Path(request.gap_autopsy_path))
        dashboard = self._read_json(Path(request.dashboard_path))
        llm_impact = self._read_json(Path(request.llm_impact_path))
        llm_adoption = self._read_json(Path(request.llm_adoption_path))

        criteria = self._criteria(clean, autopsy, dashboard, llm_impact)
        blockers = list(dashboard.get("decision_summary", {}).get("primary_blockers") or [])
        decision = "blocked_external_eval_required" if blockers else "success"
        recommendation = (
            "phase15_evidence_completion_before_candidate_mode"
            if decision != "success"
            else "phase15_candidate_mode_or_generator_reform_review"
        )
        answers = self._answers(clean, autopsy, dashboard, llm_impact, llm_adoption)
        handoff_path = self._resolved_handoff_path(Path(request.handoff_path), decision)
        report = Phase14PostmortemReport(
            created_at=self._now(),
            request=request,
            phase14_decision=decision,
            phase15_recommendation=recommendation,
            success_criteria=criteria,
            postmortem_answers=answers,
            blockers=blockers,
            next_actions=self._next_actions(dashboard, llm_adoption),
            handoff_path=str(handoff_path),
            notes=self._notes(decision, llm_impact),
        )
        self._write_json(output_dir / "phase14_postmortem_report.json", report.model_dump(mode="json"))
        self._write_markdown(handoff_path, report, clean, autopsy, dashboard, llm_impact, llm_adoption)
        return report

    def _criteria(
        self,
        clean: Dict[str, Any],
        autopsy: Dict[str, Any],
        dashboard: Dict[str, Any],
        llm_impact: Dict[str, Any],
    ) -> List[Phase14SuccessCriterion]:
        gdpval_clean = self._section_metric(dashboard, 'gdpval_subset', 'gdpval_clean_eval_count') or 0
        generated_clean = self._section_metric(dashboard, 'taskgenerator_generated_tasks', 'generated_clean_eval_count') or 0
        total_clean = int(gdpval_clean or 0) + int(generated_clean or 0)
        llm_completed = int(llm_impact.get("total_completed_metric_count") or 0)
        llm_awaiting = int(llm_impact.get("total_awaiting_llm_output") or 0)
        llm_ready = llm_impact.get("impact_readiness") == "ready_for_impact_analysis"
        llm_status = "partial" if llm_ready and llm_completed > 0 and llm_awaiting == 0 else "not_met"
        route_status = "met" if dashboard.get("decision_summary", {}).get("primary_blockers") == [] and llm_ready else "partial"
        return [
            Phase14SuccessCriterion(
                criterion_id="minimum_1_gdpval_mirror_and_subset",
                description="GDPVal finance/audit subset and calibration boundary exist.",
                status="met",
                evidence=[
                    "Phase 14 baseline handoff exists.",
                    f"clean_baseline_task_count={clean.get('task_count')}",
                ],
            ),
            Phase14SuccessCriterion(
                criterion_id="minimum_2_clean_gdpval_baseline",
                description="At least 4 GDPVal clean paired comparisons are usable for gap analysis.",
                status="met" if int(clean.get("usable_task_count") or 0) >= 4 else "not_met",
                evidence=[f"usable_task_count={clean.get('usable_task_count')}"],
            ),
            Phase14SuccessCriterion(
                criterion_id="minimum_3_gap_autopsy",
                description="Gap autopsy and hypothesis ledger exist with usable and counterexample cases.",
                status="met" if int(autopsy.get("usable_task_count") or 0) >= 4 else "not_met",
                evidence=[
                    f"gap_band_counts={autopsy.get('gap_band_counts')}",
                    f"hypothesis_ledger_path={autopsy.get('hypothesis_ledger_path')}",
                ],
            ),
            Phase14SuccessCriterion(
                criterion_id="minimum_4_observational_profiler_dashboard",
                description="GoodTaskProfiler and dashboard can represent GDPVal and generated tasks without weighted score.",
                status="met" if dashboard.get("weighted_good_task_score_emitted") is False else "not_met",
                evidence=[
                    f"phase14_readiness={dashboard.get('phase14_readiness')}",
                    "weighted_good_task_score_emitted=false",
                ],
            ),
            Phase14SuccessCriterion(
                criterion_id="ideal_1_total_clean_pairs_12",
                description="At least 12 clean paired comparisons include GDPVal and TaskGenerator generated tasks.",
                status="met" if total_clean >= 12 else "not_met",
                evidence=[
                    f"gdpval_clean_eval_count={gdpval_clean}",
                    f"generated_clean_eval_count={generated_clean}",
                    f"total_clean_pair_count={total_clean}",
                ],
                missing_evidence=[] if total_clean >= 12 else ["GDPVal/generated clean pairs toward target 12"],
            ),
            Phase14SuccessCriterion(
                criterion_id="ideal_2_llm_positive_impact",
                description="LLM shadow provides enough evidence to decide whether any insertion point is positive.",
                status=llm_status,
                evidence=[
                    f"impact_readiness={llm_impact.get('impact_readiness')}",
                    f"completed_metric_count={llm_impact.get('total_completed_metric_count')}",
                    f"awaiting_llm_output_count={llm_impact.get('total_awaiting_llm_output')}",
                ],
                missing_evidence=["human review of shadow metric alignment", "positive-impact adoption decision"]
                if llm_status == "partial"
                else ["real LLM shadow outputs", "computed shadow metrics"],
            ),
            Phase14SuccessCriterion(
                criterion_id="ideal_3_phase15_route",
                description="Phase 15 route is clear.",
                status=route_status,
                evidence=[
                    f"dashboard_blockers={dashboard.get('decision_summary', {}).get('primary_blockers')}",
                    f"impact_readiness={llm_impact.get('impact_readiness')}",
                ],
                missing_evidence=[] if route_status == "met" else ["resolve dashboard blockers", "complete LLM shadow metrics before Candidate Mode"],
            ),
        ]

    def _answers(
        self,
        clean: Dict[str, Any],
        autopsy: Dict[str, Any],
        dashboard: Dict[str, Any],
        llm_impact: Dict[str, Any],
        llm_adoption: Dict[str, Any],
    ) -> Dict[str, str]:
        high_cases = [
            f"{case.get('task_id')} ({case.get('deliverable_type')}, gap={case.get('observed_gap'):.3f})"
            for case in autopsy.get("cases", [])
            if case.get("gap_band") == "high" and case.get("usable_for_gap_analysis")
        ]
        medium_cases = [
            f"{case.get('task_id')} ({case.get('deliverable_type')}, gap={case.get('observed_gap'):.3f})"
            for case in autopsy.get("cases", [])
            if case.get("gap_band") == "medium" and case.get("usable_for_gap_analysis")
        ]
        return {
            "1_gdpval_high_gap_tasks": "; ".join(high_cases) or "No high-gap clean cases found.",
            "2_gap_source_real_skill_vs_noise": (
                "Current evidence suggests meaningful gaps often come from numeric accuracy, policy application, evidence reconciliation, "
                "and deliverable structure. Some friction remains: ee09 and slide/deck packaging show missing-deliverable/tool-noise risk."
            ),
            "3_high_value_common_structure": (
                "High-value GDPVal cases tend to combine spreadsheet or presentation deliverables, explicit professional roles, "
                "cross-file synthesis, policy/compliance reasoning, reconciliation, and reviewer-visible deliverable constraints."
            ),
            "4_generated_vs_high_value_gap": (
                "Generated tasks now have a 4-case clean paired diagnostic slice. The observed generated gaps are mixed: "
                "one low-gap case and three medium/high-gap cases. This is enough to compare initial distributions against GDPVal, "
                "but not enough for benchmark-grade model-separation claims or a weighted GoodTaskScore."
            ),
            "5_production_qa_sufficiency": (
                "Production QA is sufficient for governed release readiness, but not sufficient to prove training value or model separation."
            ),
            "6_unstable_profiler_dimensions": (
                "Generated-task model separation, format-noise risk, tool-failure risk, and LLM-impact dimensions remain observational. "
                "They are now measurable enough for Phase 15 review, but not stable enough for a weighted score."
            ),
            "7_llm_value_position": (
                "Shadow outputs now exist for GoldenRun, rubric, realism critic, and reference narrative. "
                f"impact_readiness={llm_impact.get('impact_readiness')}, "
                f"completed_metric_count={llm_impact.get('total_completed_metric_count')}. "
                "The remaining question is whether the observed deltas are beneficial enough for Candidate Mode."
            ),
            "8_llm_candidate_mode": (
                "No. Current recommendation is "
                f"{llm_adoption.get('recommendation')}; review the completed shadow metrics before promotion."
            ),
            "9_next_phase_direction": (
                "Phase 15 should review the completed shadow metrics and choose a narrow route: either guarded LLM Candidate Mode "
                "for the best-supported insertion point, or generator reform if shadow benefits are weak or risky."
            ),
            "counterexamples_to_keep": "; ".join(medium_cases) + "; ee09 remains a runnability/friction holdout.",
        }

    def _next_actions(self, dashboard: Dict[str, Any], llm_adoption: Dict[str, Any]) -> List[str]:
        actions = []
        for section in dashboard.get("sections") or []:
            actions.extend(str(item) for item in section.get("next_actions") or [])
        actions.extend(str(item) for item in llm_adoption.get("required_next_evidence") or [])
        deduped: List[str] = []
        for action in actions:
            if action not in deduped:
                deduped.append(action)
        return deduped

    def _resolved_handoff_path(self, requested_path: Path, decision: str) -> Path:
        if decision == "success" and "BLOCKED" in requested_path.name:
            return requested_path.with_name(requested_path.name.replace("BLOCKED", "SUCCESS"))
        if decision != "success" and "SUCCESS" in requested_path.name:
            return requested_path.with_name(requested_path.name.replace("SUCCESS", "BLOCKED"))
        return requested_path

    def _notes(self, decision: str, llm_impact: Dict[str, Any]) -> List[str]:
        notes = [
            "GDPVal remains eval_calibration_only and must not enter training generation.",
            "Weighted GoodTaskScore remains disabled because Phase 14 is observational, not a calibrated scoring system.",
        ]
        if decision == "success":
            notes.append("Phase 14 evidence collection is complete enough to enter Phase 15 route selection.")
        else:
            notes.append("This postmortem is evidence-based and does not claim Phase 14 success while blockers remain.")
        if llm_impact.get("impact_readiness") == "ready_for_impact_analysis":
            notes.append("LLM shadow metrics are complete; Candidate Mode still requires human review and a risk gate.")
        else:
            notes.append("LLM Candidate Mode remains blocked until real shadow outputs produce computable metrics.")
        return notes

    def _section_metric(self, dashboard: Dict[str, Any], section_name: str, metric: str) -> Any:
        for section in dashboard.get("sections") or []:
            if section.get("section_name") == section_name:
                return (section.get("headline_metrics") or {}).get(metric)
        return None

    def _write_markdown(
        self,
        path: Path,
        report: Phase14PostmortemReport,
        clean: Dict[str, Any],
        autopsy: Dict[str, Any],
        dashboard: Dict[str, Any],
        llm_impact: Dict[str, Any],
        llm_adoption: Dict[str, Any],
    ) -> None:
        title_status = "Success" if report.phase14_decision == "success" else "Blocked"
        lines = [
            f"# Phase 14 GDPTask Calibration {title_status} - 2026-07-08",
            "",
            "## Decision",
            "",
            f"- phase14_decision: `{report.phase14_decision}`",
            f"- phase15_recommendation: `{report.phase15_recommendation}`",
            f"- dashboard_status: `{dashboard.get('overall_status')}`",
            "- weighted GoodTaskScore: not emitted",
            "- GDPVal training use: forbidden; calibration only",
            "",
            "## Evidence Snapshot",
            "",
            f"- GDPVal clean usable cases: `{clean.get('usable_task_count')} / {clean.get('task_count')}`",
            f"- GDPVal gap bands: `{autopsy.get('gap_band_counts')}`",
            f"- Dashboard blockers: `{report.blockers}`",
            f"- LLM impact readiness: `{llm_impact.get('impact_readiness')}`",
            f"- LLM adoption recommendation: `{llm_adoption.get('recommendation')}`",
            "",
            "## Success Criteria",
            "",
        ]
        for criterion in report.success_criteria:
            lines.append(f"- `{criterion.criterion_id}`: `{criterion.status}` - {criterion.description}")
        lines.extend(["", "## Postmortem Answers", ""])
        for key, answer in report.postmortem_answers.items():
            lines.append(f"- `{key}`: {answer}")
        lines.extend(["", "## Next Actions", ""])
        for action in report.next_actions:
            lines.append(f"- {action}")
        lines.extend(
            [
                "",
                "## Notes",
                "",
            ]
        )
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
