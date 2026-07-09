from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


AuditStatus = Literal["proven", "incomplete", "blocked", "missing"]
Phase15CompletionStatus = Literal["complete", "not_complete"]


class Phase15CompletionAuditRequest(BaseModel):
    baseline_manifest_path: str
    llm_candidate_layer_report_path: str
    gap_autopsy_report_path: str
    pattern_library_report_path: str
    generator_reform_spec_path: str
    ab_experiment_report_path: str
    clean_eval_queue_report_path: str
    external_eval_import_report_path: str
    production_dashboard_report_path: str
    production_impact_review_report_path: Optional[str] = None
    phase15_postmortem_report_path: str
    output_dir: str


class Phase15AuditItem(BaseModel):
    requirement_id: str
    description: str
    status: AuditStatus
    evidence_paths: List[str] = Field(default_factory=list)
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15CompletionAuditReport(BaseModel):
    report_version: str = "v3.phase15_completion_audit.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15CompletionAuditRequest
    completion_status: Phase15CompletionStatus
    audit_items: List[Phase15AuditItem] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    final_blockers: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15CompletionAuditor:
    """Audit Phase 15 completion against the plan without substituting weaker evidence."""

    def build(self, request: Phase15CompletionAuditRequest) -> Phase15CompletionAuditReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        baseline = self._load_optional(request.baseline_manifest_path)
        llm_candidate = self._load_optional(request.llm_candidate_layer_report_path)
        gap_autopsy = self._load_optional(request.gap_autopsy_report_path)
        pattern_library = self._load_optional(request.pattern_library_report_path)
        reform_spec = self._load_optional(request.generator_reform_spec_path)
        ab_experiment = self._load_optional(request.ab_experiment_report_path)
        queue = self._load_optional(request.clean_eval_queue_report_path)
        eval_import = self._load_optional(request.external_eval_import_report_path)
        dashboard = self._load_optional(request.production_dashboard_report_path)
        production_impact_review = self._load_optional(request.production_impact_review_report_path or "")
        postmortem = self._load_optional(request.phase15_postmortem_report_path)

        items = [
            self._audit_baseline(request, baseline),
            self._audit_llm_gate(request, llm_candidate),
            self._audit_gap_autopsy(request, gap_autopsy),
            self._audit_pattern_library(request, pattern_library),
            self._audit_reform_design(request, reform_spec),
            self._audit_ab_experiment(request, ab_experiment),
            self._audit_clean_eval(request, queue, eval_import, postmortem),
            self._audit_production_impact(request, dashboard, production_impact_review, postmortem),
            self._audit_promotion_postmortem(request, postmortem),
        ]
        completion_status: Phase15CompletionStatus = "complete" if all(item.status == "proven" for item in items) else "not_complete"
        blockers = self._final_blockers(items)
        report = Phase15CompletionAuditReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            completion_status=completion_status,
            audit_items=items,
            summary=self._summary(items),
            final_blockers=blockers,
            next_actions=self._next_actions(blockers),
            notes=[
                "This audit checks whether Phase 15 is complete; it does not relax the Phase 15 plan.",
                "Prepared queues, runbooks, or deterministic closure do not prove clean paired eval completion.",
                "External eval evidence must be imported as sanitized item-level results before Phase 15 can close.",
            ],
        )
        (output_dir / "phase15_completion_audit_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _audit_baseline(self, request: Phase15CompletionAuditRequest, baseline: Dict[str, Any]) -> Phase15AuditItem:
        status: AuditStatus = "proven" if baseline.get("baseline_status") == "ready_for_phase15_p0" and not baseline.get("blockers") else "missing"
        return Phase15AuditItem(
            requirement_id="15.0_baseline_boundary",
            description="Phase 14 baseline and Phase 15 decision boundaries are frozen and traceable.",
            status=status,
            evidence_paths=[request.baseline_manifest_path],
            evidence_summary={
                "baseline_status": baseline.get("baseline_status"),
                "phase14_decision": baseline.get("phase14_decision"),
                "blockers": baseline.get("blockers"),
            },
            blocking_reasons=list(baseline.get("blockers") or []) if status != "proven" else [],
        )

    def _audit_llm_gate(self, request: Phase15CompletionAuditRequest, layer: Dict[str, Any]) -> Phase15AuditItem:
        recommendations_ok = layer.get("candidate_mode_default_enabled") is False
        return Phase15AuditItem(
            requirement_id="15.1_and_15.5_llm_gate",
            description="LLM shadow outputs are reviewed and guarded Candidate Mode remains explicit, not default.",
            status="proven" if recommendations_ok else "missing",
            evidence_paths=[request.llm_candidate_layer_report_path],
            evidence_summary={
                "experiment_candidate_enabled": layer.get("experiment_candidate_enabled"),
                "approved_candidate_roles": layer.get("approved_candidate_roles"),
                "diagnostic_only_roles": layer.get("diagnostic_only_roles"),
                "blocked_roles": layer.get("blocked_roles"),
            },
            blocking_reasons=[] if recommendations_ok else ["llm_candidate_default_boundary_not_proven"],
        )

    def _audit_gap_autopsy(self, request: Phase15CompletionAuditRequest, report: Dict[str, Any]) -> Phase15AuditItem:
        clean_count = int(report.get("clean_pair_count") or report.get("case_count") or 0)
        target = report.get("first_reform_target") or report.get("recommended_first_reform_target")
        status: AuditStatus = "proven" if clean_count >= 4 and target == "evidence_to_deliverable" else "missing"
        return Phase15AuditItem(
            requirement_id="15.2_generated_task_gap_autopsy",
            description="Generated task gap autopsy explains the 4 clean generated task pairs and selects the low-gap motif.",
            status=status,
            evidence_paths=[request.gap_autopsy_report_path],
            evidence_summary={
                "clean_pair_count": clean_count,
                "first_reform_target": target,
                "gap_band_counts": report.get("gap_band_counts"),
            },
            blocking_reasons=[] if status == "proven" else ["gap_autopsy_target_or_clean_pair_count_not_proven"],
        )

    def _audit_pattern_library(self, request: Phase15CompletionAuditRequest, report: Dict[str, Any]) -> Phase15AuditItem:
        pattern_count = int(report.get("pattern_count") or len(report.get("patterns") or []))
        status: AuditStatus = "proven" if pattern_count > 0 else "missing"
        return Phase15AuditItem(
            requirement_id="15.3_gdpval_pattern_library",
            description="GDPVal productive complexity pattern library exists for generator reform design.",
            status=status,
            evidence_paths=[request.pattern_library_report_path],
            evidence_summary={"pattern_count": pattern_count},
            blocking_reasons=[] if status == "proven" else ["pattern_library_missing_or_empty"],
        )

    def _audit_reform_design(self, request: Phase15CompletionAuditRequest, spec: Dict[str, Any]) -> Phase15AuditItem:
        deterministic_change_count = len(spec.get("deterministic_changes") or [])
        status: AuditStatus = "proven" if spec.get("target_motif") == "evidence_to_deliverable" and deterministic_change_count > 0 else "missing"
        return Phase15AuditItem(
            requirement_id="15.4_generator_reform_design",
            description="At least one low-gap motif has a controlled generator reform design.",
            status=status,
            evidence_paths=[request.generator_reform_spec_path],
            evidence_summary={
                "target_motif": spec.get("target_motif"),
                "reform_status": spec.get("reform_status"),
                "deterministic_change_count": deterministic_change_count,
            },
            blocking_reasons=[] if status == "proven" else ["reform_spec_not_ready"],
        )

    def _audit_ab_experiment(self, request: Phase15CompletionAuditRequest, report: Dict[str, Any]) -> Phase15AuditItem:
        summary = report.get("summary") or {}
        baseline_ready = (summary.get("candidate_ready_by_arm") or {}).get("baseline_deterministic", 0)
        reform_ready = (summary.get("candidate_ready_by_arm") or {}).get("generator_reform_only", 0)
        llm_reason_codes = summary.get("reason_codes") or []
        status: AuditStatus = "proven" if baseline_ready >= 4 and reform_ready >= 4 else "incomplete"
        return Phase15AuditItem(
            requirement_id="15.6_controlled_ab_experiment",
            description="Baseline and reform-only arms produce at least 4 candidate-ready tasks for the same motif; LLM arm is explicitly gated.",
            status=status,
            evidence_paths=[request.ab_experiment_report_path],
            evidence_summary={
                "baseline_candidate_ready": baseline_ready,
                "reform_candidate_ready": reform_ready,
                "clean_paired_eval_ready_arm_count": summary.get("clean_paired_eval_ready_arm_count"),
                "reason_codes": llm_reason_codes,
            },
            blocking_reasons=[] if status == "proven" else ["ab_experiment_candidate_ready_counts_below_4"],
            notes=["LLM candidate arm is blocked by design because no role was approved for artifact mutation."],
        )

    def _audit_clean_eval(
        self,
        request: Phase15CompletionAuditRequest,
        queue: Dict[str, Any],
        eval_import: Dict[str, Any],
        postmortem: Dict[str, Any],
    ) -> Phase15AuditItem:
        queue_summary = queue.get("summary") or {}
        import_summary = eval_import.get("summary") or {}
        complete_pair_count = int(import_summary.get("complete_pair_count") or 0)
        status: AuditStatus = "proven" if eval_import.get("import_status") == "ready_for_closeout" and complete_pair_count > 0 else "blocked"
        return Phase15AuditItem(
            requirement_id="15.7_clean_paired_eval",
            description="Clean paired eval is completed and imported for matched baseline/reform cases.",
            status=status,
            evidence_paths=[request.clean_eval_queue_report_path, request.external_eval_import_report_path, request.phase15_postmortem_report_path],
            evidence_summary={
                "queue_prepared_item_count": queue_summary.get("prepared_item_count"),
                "queue_paired_case_count": queue_summary.get("paired_case_count"),
                "import_status": eval_import.get("import_status"),
                "complete_pair_count": complete_pair_count,
                "postmortem_clean_paired_eval_completed": (postmortem.get("evidence_summary") or {}).get("eval", {}).get("clean_paired_eval_completed"),
            },
            blocking_reasons=["external_eval_results_missing_or_not_ready_for_closeout"] if status != "proven" else [],
            notes=["Current tenant policy blocks external task-package export; importer is ready for sanitized results from a permitted environment."],
        )

    def _audit_production_impact(
        self,
        request: Phase15CompletionAuditRequest,
        dashboard: Dict[str, Any],
        production_impact_review: Dict[str, Any],
        postmortem: Dict[str, Any],
    ) -> Phase15AuditItem:
        summary = dashboard.get("summary") or {}
        blocked_count = int(summary.get("blocked_count") or 0)
        candidate_ready = int(summary.get("candidate_ready_count") or 0)
        production_ready = int(summary.get("production_ready_count") or 0)
        review_completed = bool(production_impact_review.get("explicit_review_completed"))
        review_decision = production_impact_review.get("decision")
        review_blockers = list(production_impact_review.get("blocking_reasons") or [])
        status: AuditStatus = "incomplete"
        if candidate_ready >= 4 and blocked_count == 0 and production_ready > 0:
            status = "proven"
        elif candidate_ready >= 4 and blocked_count == 0 and review_completed and not review_blockers:
            status = "proven"
        elif candidate_ready >= 4 and blocked_count == 0:
            status = "incomplete"
        else:
            status = "missing"
        return Phase15AuditItem(
            requirement_id="15.8_production_qa_release_impact",
            description="Reform arm production impact is reviewed without structural blockers and has an explicit governed release or non-release decision.",
            status=status,
            evidence_paths=[
                request.production_dashboard_report_path,
                request.production_impact_review_report_path or "",
                request.phase15_postmortem_report_path,
            ],
            evidence_summary={
                "candidate_ready_count": candidate_ready,
                "production_ready_count": production_ready,
                "review_required_count": summary.get("review_required_count"),
                "blocked_count": blocked_count,
                "production_impact_review_decision": review_decision,
                "production_impact_review_completed": review_completed,
                "production_impact_review_reasons": production_impact_review.get("review_reasons"),
            },
            blocking_reasons=[] if status == "proven" else ["production_approval_or_release_readiness_not_proven"],
            notes=[
                "A completed keep-experiment-flag review proves production impact was reviewed without structural regression; it does not imply release readiness."
            ] if status == "proven" and not production_ready else [],
        )

    def _audit_promotion_postmortem(self, request: Phase15CompletionAuditRequest, postmortem: Dict[str, Any]) -> Phase15AuditItem:
        decision = postmortem.get("phase15_decision")
        status: AuditStatus = "proven" if decision == "success" else "incomplete"
        return Phase15AuditItem(
            requirement_id="15.9_15.10_promotion_postmortem",
            description="Promotion/rollback proposal and Phase 15 postmortem close with a justified Phase 16 decision.",
            status=status,
            evidence_paths=[request.phase15_postmortem_report_path],
            evidence_summary={
                "phase15_decision": decision,
                "recommendation": postmortem.get("recommendation"),
                "blocking_reasons": postmortem.get("blocking_reasons"),
            },
            blocking_reasons=list(postmortem.get("blocking_reasons") or []) if status != "proven" else [],
        )

    def _summary(self, items: List[Phase15AuditItem]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return {
            "item_count": len(items),
            "status_counts": dict(sorted(counts.items())),
            "proven_count": counts.get("proven", 0),
            "not_proven_count": len(items) - counts.get("proven", 0),
        }

    def _final_blockers(self, items: List[Phase15AuditItem]) -> List[str]:
        blockers = []
        for item in items:
            if item.status != "proven":
                blockers.extend(f"{item.requirement_id}:{reason}" for reason in (item.blocking_reasons or ["not_proven"]))
        return sorted(set(blockers))

    def _next_actions(self, blockers: List[str]) -> List[str]:
        if not blockers:
            return ["Mark Phase 15 complete after final review."]
        actions = [
            "Run first-pair external eval in a separately permitted environment.",
            "Import sanitized baseline/reform item-level scores with Test/run_v3_phase15_external_eval_importer.py.",
            "Regenerate Phase 15 postmortem and re-run this completion audit.",
        ]
        if any("production_approval" in blocker for blocker in blockers):
            actions.append("After eval import, run governed production approval or explicitly keep reform behind experiment flag.")
        return actions

    def _load_optional(self, path: str) -> Dict[str, Any]:
        resolved = Path(path)
        if not resolved.exists():
            return {}
        return load_json_file(str(resolved))
