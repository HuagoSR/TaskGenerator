from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


CandidateLayerStatus = Literal[
    "blocked",
    "diagnostic_only",
    "candidate_experiment_ready",
    "needs_more_review",
]


class LlmCandidateLayerRequest(BaseModel):
    adoption_gate_path: str
    reform_spec_path: str
    output_dir: str


class LlmCandidateRoleDecision(BaseModel):
    role: str
    gate_recommendation: str
    layer_status: CandidateLayerStatus
    allowed_operations: List[str] = Field(default_factory=list)
    blocked_operations: List[str] = Field(default_factory=list)
    required_validation: List[str] = Field(default_factory=list)
    rationale: List[str] = Field(default_factory=list)


class LlmCandidateLayerReport(BaseModel):
    report_version: str = "v3.phase15_llm_candidate_layer.1"
    created_at: str
    diagnostic_only: bool = True
    request: LlmCandidateLayerRequest
    target_motif: str
    candidate_mode_default_enabled: bool = False
    experiment_candidate_enabled: bool = False
    approved_candidate_roles: List[str] = Field(default_factory=list)
    diagnostic_only_roles: List[str] = Field(default_factory=list)
    blocked_roles: List[str] = Field(default_factory=list)
    role_decisions: List[LlmCandidateRoleDecision] = Field(default_factory=list)
    experiment_policy: Dict[str, Any] = Field(default_factory=dict)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class LlmCandidateLayerBuilder:
    """Convert Phase 15 LLM adoption evidence into an explicit candidate-layer contract."""

    def build(self, request: LlmCandidateLayerRequest) -> LlmCandidateLayerReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        adoption_gate = load_json_file(request.adoption_gate_path)
        reform_spec = load_json_file(request.reform_spec_path)
        role_recommendations = adoption_gate.get("role_recommendations") or {}
        optional_changes = reform_spec.get("optional_llm_candidate_changes") or []

        role_decisions = [
            self._role_decision(role, str(recommendation), optional_changes)
            for role, recommendation in sorted(role_recommendations.items())
        ]
        approved = [item.role for item in role_decisions if item.layer_status == "candidate_experiment_ready"]
        diagnostics = [item.role for item in role_decisions if item.layer_status == "diagnostic_only"]
        blocked = [item.role for item in role_decisions if item.layer_status == "blocked"]
        needs_review = [item.role for item in role_decisions if item.layer_status == "needs_more_review"]

        report = LlmCandidateLayerReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            target_motif=str(reform_spec.get("target_motif") or "unknown"),
            candidate_mode_default_enabled=False,
            experiment_candidate_enabled=bool(approved),
            approved_candidate_roles=approved,
            diagnostic_only_roles=diagnostics,
            blocked_roles=blocked,
            role_decisions=role_decisions,
            experiment_policy=self._experiment_policy(approved, diagnostics, needs_review),
            next_actions=self._next_actions(approved, diagnostics, needs_review),
            notes=[
                "This layer does not call an LLM and does not mutate generated task artifacts.",
                "Candidate Mode remains disabled by default until a role reaches candidate_experiment_ready.",
                "Diagnostic-only LLM signals may be attached to experiment reports, but they must not replace deterministic truth, rubrics, or evidence mappings.",
            ],
        )
        (output_dir / "llm_candidate_layer_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _role_decision(
        self,
        role: str,
        recommendation: str,
        optional_changes: List[Dict[str, Any]],
    ) -> LlmCandidateRoleDecision:
        if recommendation == "adopt_candidate":
            return LlmCandidateRoleDecision(
                role=role,
                gate_recommendation=recommendation,
                layer_status="candidate_experiment_ready",
                allowed_operations=["write_candidate_sidecar_only", "no_artifact_mutation"],
                blocked_operations=["primary_truth_generation", "rubric_score_mutation", "evidence_id_mutation"],
                required_validation=[
                    "unsupported_claim_check",
                    "candidate_visible_leakage_check",
                    "evidence_reference_integrity_check",
                ],
                rationale=["Role passed the conservative adoption gate for a guarded sidecar experiment."],
            )
        if recommendation == "shadow_only":
            return LlmCandidateRoleDecision(
                role=role,
                gate_recommendation=recommendation,
                layer_status="diagnostic_only",
                allowed_operations=self._diagnostic_operations(role, optional_changes),
                blocked_operations=[
                    "artifact_mutation",
                    "readiness_promotion",
                    "primary_truth_generation",
                    "rubric_score_mutation",
                ],
                required_validation=["report_only_consumption", "human_review_before_promotion"],
                rationale=["Gate recommends shadow_only; keep signal as review prioritization evidence."],
            )
        if recommendation == "needs_more_review":
            return LlmCandidateRoleDecision(
                role=role,
                gate_recommendation=recommendation,
                layer_status="needs_more_review",
                allowed_operations=["offline_shadow_review_only"],
                blocked_operations=["candidate_mode", "artifact_mutation", "readiness_promotion"],
                required_validation=["manual_metric_alignment_review", "additional_shadow_cases"],
                rationale=["Role has possible value but insufficient evidence for Candidate Mode."],
            )
        return LlmCandidateRoleDecision(
            role=role,
            gate_recommendation=recommendation,
            layer_status="blocked",
            allowed_operations=[],
            blocked_operations=["candidate_mode", "artifact_mutation", "readiness_promotion"],
            required_validation=["new_shadow_evidence_before_reconsideration"],
            rationale=[f"Gate recommendation is {recommendation}; Phase 15 keeps this role blocked."],
        )

    def _diagnostic_operations(
        self,
        role: str,
        optional_changes: List[Dict[str, Any]],
    ) -> List[str]:
        operations = ["write_diagnostic_sidecar", "attach_review_findings"]
        if role == "realism_critic":
            operations.append("flag_thin_scenario_density")
        if any(str(change.get("change_id") or "").startswith("llm_reference") for change in optional_changes):
            if role == "reference_narrative":
                operations.append("suggest_reference_narrative_for_review")
        return sorted(set(operations))

    def _experiment_policy(
        self,
        approved: List[str],
        diagnostics: List[str],
        needs_review: List[str],
    ) -> Dict[str, Any]:
        return {
            "default_chain_mutation_allowed": False,
            "llm_primary_truth_allowed": False,
            "candidate_sidecar_allowed": bool(approved),
            "diagnostic_sidecar_allowed": bool(diagnostics),
            "approved_candidate_roles": approved,
            "diagnostic_only_roles": diagnostics,
            "roles_requiring_more_review": needs_review,
            "artifact_mutation_policy": "forbidden_without_later_promotion_record",
        }

    def _next_actions(
        self,
        approved: List[str],
        diagnostics: List[str],
        needs_review: List[str],
    ) -> List[str]:
        if approved:
            return [
                "Run a one-by-one guarded candidate sidecar experiment for approved roles only.",
                "Validate every candidate sidecar against unsupported-claim, leakage, and evidence-reference checks.",
                "Keep deterministic baseline and reform-only arms as the comparison anchor.",
            ]
        actions = [
            "Do not enable generator_reform_plus_guarded_llm_candidate as an artifact-mutating arm yet.",
            "Use diagnostic-only LLM roles as sidecar review signals if the controlled experiment needs them.",
        ]
        if diagnostics:
            actions.append("Prioritize realism_critic-style diagnostics because they do not write truth or scoring artifacts.")
        if needs_review:
            actions.append("Review needs_more_review roles manually before any future candidate-sidecar run.")
        return actions
