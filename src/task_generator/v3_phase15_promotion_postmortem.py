from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


PromotionRecommendation = Literal[
    "promote_reform_to_default",
    "keep_experiment_flag_only",
    "rollback_reform_experiment",
]
Phase15Decision = Literal["success", "still_open", "blocked"]


class Phase15CloseoutRequest(BaseModel):
    ab_experiment_report_path: str
    clean_eval_queue_report_path: str
    attempted_eval_run_report_path: Optional[str] = None
    external_eval_import_report_path: Optional[str] = None
    production_dashboard_report_path: str
    release_readiness_report_path: str
    output_dir: str
    external_eval_authorization_status: str = "not_recorded"


class Phase15PromotionProposal(BaseModel):
    report_version: str = "v3.phase15_promotion_proposal.1"
    created_at: str
    diagnostic_only: bool = True
    recommendation: PromotionRecommendation
    deterministic_evidence: Dict[str, Any] = Field(default_factory=dict)
    eval_evidence: Dict[str, Any] = Field(default_factory=dict)
    production_evidence: Dict[str, Any] = Field(default_factory=dict)
    required_before_promotion: List[str] = Field(default_factory=list)
    rollback_conditions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15PostmortemReport(BaseModel):
    report_version: str = "v3.phase15_postmortem.1"
    created_at: str
    phase15_decision: Phase15Decision
    recommendation: str
    completed_steps: List[str] = Field(default_factory=list)
    still_open_steps: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    phase16_entry_conditions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15CloseoutBuilder:
    """Build Phase 15 promotion and postmortem reports from current deterministic evidence."""

    def build(self, request: Phase15CloseoutRequest) -> tuple[Phase15PromotionProposal, Phase15PostmortemReport]:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ab_report = load_json_file(request.ab_experiment_report_path)
        queue = load_json_file(request.clean_eval_queue_report_path)
        eval_run = self._load_optional(request.attempted_eval_run_report_path)
        eval_import = self._load_optional(request.external_eval_import_report_path)
        dashboard = load_json_file(request.production_dashboard_report_path)
        readiness = load_json_file(request.release_readiness_report_path)

        deterministic_evidence = self._deterministic_evidence(ab_report)
        eval_evidence = self._eval_evidence(
            queue,
            eval_run,
            eval_import,
            request.external_eval_authorization_status,
        )
        production_evidence = self._production_evidence(dashboard, readiness)
        recommendation = self._recommendation(deterministic_evidence, eval_evidence, production_evidence)
        proposal = Phase15PromotionProposal(
            created_at=self._now(),
            recommendation=recommendation,
            deterministic_evidence=deterministic_evidence,
            eval_evidence=eval_evidence,
            production_evidence=production_evidence,
            required_before_promotion=self._required_before_promotion(eval_evidence, production_evidence),
            rollback_conditions=[
                "clean paired eval shows no improvement or worse model separation for reform arm",
                "production QA introduces structural blockers after reform expansion",
                "LLM candidate layer is accidentally used to mutate truth, rubric, or evidence mappings",
                "default chain receives Phase 15 reform without explicit promotion review",
            ],
            notes=[
                "This proposal is report-first and does not mutate the production runner default path.",
                "The current safe recommendation is to keep the reform behind the explicit experiment flag.",
            ],
        )
        postmortem = Phase15PostmortemReport(
            created_at=self._now(),
            phase15_decision=self._phase15_decision(proposal),
            recommendation=self._postmortem_recommendation(proposal),
            completed_steps=self._completed_steps(deterministic_evidence, eval_evidence, production_evidence),
            still_open_steps=self._still_open_steps(eval_evidence, production_evidence),
            blocking_reasons=self._blocking_reasons(eval_evidence, production_evidence),
            evidence_summary={
                "deterministic": deterministic_evidence,
                "eval": eval_evidence,
                "production": production_evidence,
            },
            phase16_entry_conditions=[
                "At least one clean paired baseline/reform eval pair completes for both selected models.",
                "Promotion proposal moves from keep_experiment_flag_only to promote_reform_to_default or an explicit rollback decision is recorded.",
                "Release readiness is not blocked by production QA or single-scope concentration warnings when release is the target.",
            ],
            notes=[
                "Phase 15 has reached deterministic reform closure but not clean eval closure.",
                "Do not claim model-separation or training-value improvement from this phase until external clean paired eval completes.",
            ],
        )
        (output_dir / "phase15_promotion_proposal.json").write_text(
            proposal.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output_dir / "phase15_postmortem_report.json").write_text(
            postmortem.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return proposal, postmortem

    def _deterministic_evidence(self, ab_report: Dict[str, Any]) -> Dict[str, Any]:
        summary = ab_report.get("summary") or {}
        arms = {
            str(arm.get("arm_id")): arm
            for arm in ab_report.get("arms") or []
            if isinstance(arm, dict)
        }
        return {
            "experiment_id": (ab_report.get("request") or {}).get("experiment_id"),
            "clean_paired_eval_ready_arm_count": summary.get("clean_paired_eval_ready_arm_count"),
            "baseline_candidate_ready_count": (arms.get("baseline_deterministic") or {}).get("candidate_ready_count"),
            "reform_candidate_ready_count": (arms.get("generator_reform_only") or {}).get("candidate_ready_count"),
            "llm_candidate_arm_status": (arms.get("generator_reform_plus_guarded_llm_candidate") or {}).get("arm_status"),
            "reason_codes": summary.get("reason_codes") or [],
        }

    def _eval_evidence(
        self,
        queue: Dict[str, Any],
        eval_run: Dict[str, Any],
        eval_import: Dict[str, Any],
        external_eval_authorization_status: str,
    ) -> Dict[str, Any]:
        queue_summary = queue.get("summary") or {}
        import_summary = eval_import.get("summary") or {}
        command_records = eval_run.get("command_records") or []
        inspected_text = self._eval_run_inspected_text(eval_run)
        connection_failed = any(
            "All connection attempts failed" in str(record.get("stderr_excerpt") or "")
            or "All connection attempts failed" in str(record.get("stdout_excerpt") or "")
            for record in command_records
        ) or "All connection attempts failed" in inspected_text
        import_status = eval_import.get("import_status")
        clean_completed = import_status == "ready_for_closeout" and int(import_summary.get("complete_pair_count") or 0) > 0
        return {
            "queue_item_count": queue_summary.get("queue_item_count"),
            "prepared_item_count": queue_summary.get("prepared_item_count"),
            "paired_case_count": queue_summary.get("paired_case_count"),
            "attempted_run_status": eval_run.get("run_status") if eval_run else None,
            "attempted_case_id": eval_run.get("case_id") if eval_run else None,
            "attempted_model": eval_run.get("model") if eval_run else None,
            "external_connection_failed": connection_failed,
            "external_eval_authorization_status": external_eval_authorization_status,
            "external_eval_import_status": import_status,
            "external_eval_import_complete_pair_count": import_summary.get("complete_pair_count"),
            "external_eval_import_mean_delta": import_summary.get("mean_reform_minus_baseline_delta"),
            "clean_paired_eval_completed": clean_completed,
        }

    def _eval_run_inspected_text(self, eval_run: Dict[str, Any]) -> str:
        snippets: List[str] = []
        for inspection in eval_run.get("output_inspections") or []:
            if not isinstance(inspection, dict):
                continue
            for sample in inspection.get("sample_files") or []:
                sample_path = Path(str(sample))
                if not sample_path.exists() or sample_path.is_dir():
                    continue
                try:
                    snippets.append(sample_path.read_text(encoding="utf-8", errors="replace")[:20000])
                except Exception:
                    continue
        return "\n".join(snippets)

    def _production_evidence(
        self,
        dashboard: Dict[str, Any],
        readiness: Dict[str, Any],
    ) -> Dict[str, Any]:
        summary = dashboard.get("summary") or {}
        return {
            "case_count": summary.get("case_count"),
            "candidate_ready_count": summary.get("candidate_ready_count"),
            "production_ready_count": summary.get("production_ready_count"),
            "review_required_count": summary.get("review_required_count"),
            "blocked_count": summary.get("blocked_count"),
            "release_readiness_status": readiness.get("readiness_status"),
            "release_blocking_reasons": readiness.get("blocking_reasons") or [],
            "release_review_reasons": readiness.get("review_reasons") or [],
        }

    def _recommendation(
        self,
        deterministic: Dict[str, Any],
        eval_evidence: Dict[str, Any],
        production: Dict[str, Any],
    ) -> PromotionRecommendation:
        if production.get("blocked_count"):
            return "rollback_reform_experiment"
        if eval_evidence.get("clean_paired_eval_completed") and production.get("production_ready_count"):
            return "promote_reform_to_default"
        if deterministic.get("reform_candidate_ready_count"):
            return "keep_experiment_flag_only"
        return "rollback_reform_experiment"

    def _required_before_promotion(
        self,
        eval_evidence: Dict[str, Any],
        production: Dict[str, Any],
    ) -> List[str]:
        required = []
        if not eval_evidence.get("clean_paired_eval_completed"):
            required.append("complete clean paired eval for matched baseline/reform cases")
        if not production.get("production_ready_count"):
            required.append("obtain explicit production QA approval or reviewer promotion policy for reform cases")
        if production.get("release_readiness_status") != "release_ready":
            required.append("resolve release readiness blockers and review reasons before release packaging")
        return required

    def _phase15_decision(self, proposal: Phase15PromotionProposal) -> Phase15Decision:
        if proposal.recommendation == "promote_reform_to_default":
            return "success"
        if proposal.recommendation == "keep_experiment_flag_only":
            return "still_open"
        return "blocked"

    def _postmortem_recommendation(self, proposal: Phase15PromotionProposal) -> str:
        if proposal.recommendation == "keep_experiment_flag_only":
            return "Keep Phase 15 reform isolated behind the experiment flag; request explicit approval before external clean paired eval."
        if proposal.recommendation == "rollback_reform_experiment":
            return "Rollback or redesign the reform experiment before further eval."
        return "Promote the reform through the governed default-chain review path."

    def _completed_steps(
        self,
        deterministic: Dict[str, Any],
        eval_evidence: Dict[str, Any],
        production: Dict[str, Any],
    ) -> List[str]:
        steps = [
            "15.0 baseline and decision boundary",
            "15.1 LLM shadow review and adoption gate",
            "15.2 generated task gap autopsy",
            "15.3 GDPVal productive complexity pattern library",
            "15.4 generator reform design",
            "15.5 guarded LLM candidate layer",
        ]
        if deterministic.get("clean_paired_eval_ready_arm_count", 0) >= 2:
            steps.append("15.6 controlled deterministic A/B scaffold")
        if eval_evidence.get("prepared_item_count"):
            steps.append("15.7 clean eval queue preparation")
        if eval_evidence.get("clean_paired_eval_completed"):
            steps.append("15.7 clean paired eval imported evidence")
        if production.get("case_count"):
            steps.append("15.8 deterministic production impact check")
        steps.append("15.9 promotion/rollback proposal")
        return steps

    def _still_open_steps(
        self,
        eval_evidence: Dict[str, Any],
        production: Dict[str, Any],
    ) -> List[str]:
        steps = []
        if not eval_evidence.get("clean_paired_eval_completed"):
            steps.append("15.7 clean paired eval execution")
        if not production.get("production_ready_count"):
            steps.append("15.8 governed production approval after eval")
        steps.append("15.10 final success postmortem after eval evidence")
        return steps

    def _blocking_reasons(
        self,
        eval_evidence: Dict[str, Any],
        production: Dict[str, Any],
    ) -> List[str]:
        reasons = []
        if eval_evidence.get("external_connection_failed") and not eval_evidence.get("clean_paired_eval_completed"):
            reasons.append("external_eval_connection_failed_in_sandbox")
        if eval_evidence.get("external_eval_authorization_status") in {"approval_rejected", "requires_explicit_user_approval"}:
            reasons.append("external_eval_authorization_not_available")
        if eval_evidence.get("external_eval_authorization_status") == "tenant_policy_denied" and not eval_evidence.get("clean_paired_eval_completed"):
            reasons.append("external_eval_tenant_policy_denied")
        if not eval_evidence.get("clean_paired_eval_completed"):
            reasons.append("clean_paired_eval_not_completed")
        if production.get("release_readiness_status") != "release_ready":
            reasons.append("release_not_ready_without_reviewed_promotion")
        return reasons

    def _load_optional(self, path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {}
        resolved = Path(path)
        if not resolved.exists():
            return {}
        return load_json_file(str(resolved))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
