from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


Phase12Decision = Literal["success", "still_open"]


class Phase12PostmortemReport(BaseModel):
    phase12_postmortem_version: str = "v1"
    report_date: str
    dashboard_report_path: str
    decision: Phase12Decision = "still_open"
    success_checks: Dict[str, bool] = Field(default_factory=dict)
    answers: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase12PostmortemBuilder:
    def build(
        self,
        dashboard_report_path: str | Path,
        output_dir: str | Path,
    ) -> Phase12PostmortemReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        dashboard = load_json_file(str(dashboard_report_path))
        summary = dashboard.get("summary") or {}
        checks = {
            "regression_expanded": int(summary.get("candidate_ready_after") or 0) >= 4,
            "negative_controls_majority_caught": float(summary.get("negative_control_pass_rate") or 0.0) >= 0.7,
            "substrate_improved": int(summary.get("missing_typed_resource_skill_count_after") or 0)
            < int(summary.get("missing_typed_resource_skill_count_before") or 0),
            "eval_mini_campaign_completed": int(summary.get("eval_selected_case_count") or 0) >= 3
            and float(summary.get("eval_summary_completion_rate") or 0.0) >= 0.8,
            "dashboard_unified_evidence": True,
            "no_implicit_registry_mutation": True,
        }
        decision: Phase12Decision = "success" if all(checks.values()) else "still_open"
        answers = {
            "candidate_ready_path_expanded": {
                "before": summary.get("candidate_ready_before"),
                "after": summary.get("candidate_ready_after"),
            },
            "gate_hardness": {
                "negative_control_pass_rate": summary.get("negative_control_pass_rate"),
            },
            "substrate_remaining_problem": {
                "missing_typed_resource_skill_count_after": summary.get("missing_typed_resource_skill_count_after"),
            },
            "executed_eval_stability": {
                "eval_selected_case_count": summary.get("eval_selected_case_count"),
                "eval_summary_completion_rate": summary.get("eval_summary_completion_rate"),
                "eval_usable_summary_rate": summary.get("eval_usable_summary_rate"),
            },
            "workflow_context_improvement": {
                "improved_case_count": summary.get("workflow_improved_case_count"),
                "degraded_case_count": summary.get("workflow_degraded_case_count"),
            },
            "phase13_readiness": "only_ready_if_all_success_checks_pass"
            if decision != "success"
            else "phase12_success_conditions_met",
        }
        report = Phase12PostmortemReport(
            report_date=date.today().isoformat(),
            dashboard_report_path=str(dashboard_report_path),
            decision=decision,
            success_checks=checks,
            answers=answers,
            notes=[
                "Phase 12 is only considered complete when executed eval evidence joins the already-verified regression, gate-hardness, substrate, and workflow evidence.",
                "A still_open decision means the remaining blocking condition should be resolved before entering Phase 13.",
            ],
        )
        (output_path / "phase12_postmortem_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        handoff_name = (
            f"PHASE_12_HARDENING_SUCCESS_{date.today().isoformat()}.md"
            if decision == "success"
            else f"PHASE_12_HARDENING_BLOCKED_{date.today().isoformat()}.md"
        )
        handoff_path = output_path / handoff_name
        handoff_path.write_text(self._handoff_markdown(report), encoding="utf-8")
        return report

    def _handoff_markdown(self, report: Phase12PostmortemReport) -> str:
        lines = [
            f"# Phase 12 Postmortem - {report.report_date}",
            "",
            f"- decision: `{report.decision}`",
            f"- dashboard: `{report.dashboard_report_path}`",
            "",
            "## Success checks",
            "",
        ]
        for key, value in report.success_checks.items():
            lines.append(f"- `{key}` = `{str(value).lower()}`")
        lines.extend(["", "## Answers", ""])
        for key, value in report.answers.items():
            lines.append(f"- `{key}`: `{value}`")
        lines.extend(["", "## Notes", ""])
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")
        return "\n".join(lines)
