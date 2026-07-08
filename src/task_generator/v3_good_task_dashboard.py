from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class GoodTaskDashboardRequest(BaseModel):
    good_task_profiler_report_path: str
    generated_vs_gdpval_report_path: str
    generated_task_eval_summary_path: str
    llm_impact_report_path: str
    llm_adoption_report_path: str
    output_dir: str


class DashboardSection(BaseModel):
    section_name: str
    status: str
    headline_metrics: Dict[str, Any] = Field(default_factory=dict)
    blockers: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)


class GoodTaskDashboardReport(BaseModel):
    report_version: str = "v3.good_task_dashboard.1"
    created_at: str
    request: GoodTaskDashboardRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    weighted_good_task_score_emitted: bool = False
    overall_status: str
    phase14_readiness: str
    sections: List[DashboardSection] = Field(default_factory=list)
    decision_summary: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class GoodTaskDashboardBuilder:
    def build(self, request: GoodTaskDashboardRequest) -> GoodTaskDashboardReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        profiler = self._read_json(Path(request.good_task_profiler_report_path))
        comparison = self._read_json(Path(request.generated_vs_gdpval_report_path))
        generated_eval = self._read_json(Path(request.generated_task_eval_summary_path))
        llm_impact = self._read_json(Path(request.llm_impact_report_path))
        llm_adoption = self._read_json(Path(request.llm_adoption_report_path))

        sections = [
            self._gdpval_section(profiler, comparison),
            self._generated_section(profiler, comparison, generated_eval),
            self._llm_section(llm_impact, llm_adoption),
            self._comparison_section(comparison, generated_eval),
        ]
        blockers = [blocker for section in sections for blocker in section.blockers]
        overall_status = "blocked_pending_external_eval" if blockers else "ready_for_phase14_postmortem"
        report = GoodTaskDashboardReport(
            created_at=self._now(),
            request=request,
            overall_status=overall_status,
            phase14_readiness="partial_diagnostic_dashboard_ready",
            sections=sections,
            decision_summary={
                "can_claim_generated_vs_gdpval_model_separation": False,
                "can_emit_weighted_good_task_score": False,
                "can_enter_llm_candidate_mode": llm_adoption.get("recommendation") != "do_not_enter_llm_candidate_mode_yet",
                "blocking_reason_count": len(blockers),
                "primary_blockers": blockers,
            },
            notes=[
                "This dashboard consolidates current Phase 14 diagnostic evidence only.",
                "It does not include GDPVal tasks in training generation.",
                "It does not emit a weighted GoodTaskScore.",
                "Generated-vs-GDPVal model-separation and LLM adoption claims remain blocked until external eval evidence exists.",
            ],
        )
        self._write_json(output_dir / "good_task_dashboard_report.json", report.model_dump(mode="json"))
        self._write_json(output_dir / "good_task_dashboard_summary.json", self._summary(report))
        return report

    def _gdpval_section(self, profiler: Dict[str, Any], comparison: Dict[str, Any]) -> DashboardSection:
        clean = int(comparison.get("gdpval_clean_eval_count") or 0)
        status = "initial_calibration_value" if clean >= 4 else "insufficient_clean_gdpval_pairs"
        blockers = []
        if clean < 8:
            blockers.append("gdpval_clean_pairs_below_target_8")
        return DashboardSection(
            section_name="gdpval_subset",
            status=status,
            headline_metrics={
                "gdpval_profile_count": profiler.get("gdpval_profile_count"),
                "gdpval_clean_eval_count": clean,
                "evaluated_profile_count": profiler.get("evaluated_profile_count"),
            },
            blockers=blockers,
            next_actions=["Run queued GDPVal cases one at a time until clean paired comparisons approach 8."],
        )

    def _generated_section(
        self,
        profiler: Dict[str, Any],
        comparison: Dict[str, Any],
        generated_eval: Dict[str, Any],
    ) -> DashboardSection:
        clean = int(generated_eval.get("clean_pair_count") or comparison.get("generated_clean_eval_count") or 0)
        blockers = []
        if clean == 0:
            blockers.append("generated_tasks_have_no_clean_paired_eval")
        return DashboardSection(
            section_name="taskgenerator_generated_tasks",
            status="pending_external_eval" if blockers else "clean_pair_evidence_available",
            headline_metrics={
                "taskgenerator_profile_count": profiler.get("taskgenerator_profile_count"),
                "generated_clean_eval_count": clean,
                "generated_blocked_pair_count": generated_eval.get("blocked_pair_count"),
                "generated_completed_model_score_count": generated_eval.get("completed_model_score_count"),
            },
            blockers=blockers,
            next_actions=["Execute generated comparison tasks one at a time, then rerun generated eval summary and comparison reports."],
        )

    def _llm_section(self, llm_impact: Dict[str, Any], llm_adoption: Dict[str, Any]) -> DashboardSection:
        blockers = []
        if llm_impact.get("impact_readiness") != "ready_for_impact_analysis":
            blockers.append("llm_shadow_outputs_missing")
        if llm_adoption.get("recommendation") == "do_not_enter_llm_candidate_mode_yet":
            blockers.append("llm_candidate_mode_not_recommended")
        return DashboardSection(
            section_name="llm_shadow",
            status=str(llm_impact.get("impact_readiness") or "unknown"),
            headline_metrics={
                "shadow_kind_count": llm_impact.get("shadow_kind_count"),
                "prepared_task_shadows": llm_impact.get("total_prepared_task_shadows"),
                "awaiting_llm_output": llm_impact.get("total_awaiting_llm_output"),
                "completed_metric_count": llm_impact.get("total_completed_metric_count"),
                "adoption_recommendation": llm_adoption.get("recommendation"),
            },
            blockers=blockers,
            next_actions=list(llm_adoption.get("required_next_evidence") or []),
        )

    def _comparison_section(self, comparison: Dict[str, Any], generated_eval: Dict[str, Any]) -> DashboardSection:
        blockers = []
        readiness = str(comparison.get("comparison_readiness") or "unknown")
        if readiness != "clean_pair_comparison_available":
            blockers.append(str(comparison.get("blocked_reason") or "comparison_not_clean_pair_ready"))
        return DashboardSection(
            section_name="generated_vs_gdpval",
            status=readiness,
            headline_metrics={
                "gdpval_clean_eval_count": comparison.get("gdpval_clean_eval_count"),
                "generated_clean_eval_count": comparison.get("generated_clean_eval_count"),
                "generated_summary_clean_pair_count": generated_eval.get("clean_pair_count"),
            },
            blockers=blockers,
            next_actions=list(comparison.get("recommended_next_actions") or []),
        )

    def _summary(self, report: GoodTaskDashboardReport) -> Dict[str, Any]:
        return {
            "report_version": "v3.good_task_dashboard_summary.1",
            "created_at": self._now(),
            "overall_status": report.overall_status,
            "phase14_readiness": report.phase14_readiness,
            "weighted_good_task_score_emitted": report.weighted_good_task_score_emitted,
            "sections": [
                {
                    "section_name": section.section_name,
                    "status": section.status,
                    "blockers": section.blockers,
                }
                for section in report.sections
            ],
            "decision_summary": report.decision_summary,
        }

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
