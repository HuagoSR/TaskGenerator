from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.core.external_model_policy import enforce_external_model_policy
from task_generator.planning.brief_admission import (
    FormalBriefCohortAdmission,
    FormalMatchedBriefCohortAdmissionReportV2,
    SourceProvenanceLedgerV1,
)
from task_generator.core.source_fingerprint import governed_source_fingerprint
from task_generator.generation.hybrid_materializer import HybridTaskMaterializer
from task_generator.evaluation.reality_review import (
    RealityReviewSelectionCaseV1,
    RealityReviewSelectionV1,
)
from task_generator.evaluation.route_comparison import RouteBlindPackageStager
from task_generator.generation.rw_task_export_validator import RwTaskExportValidator
from task_generator.substrate.skill_extractor import ProviderConfig
from task_generator.evaluation.solver_budget import SolverExecutionBudgetV1
from task_generator.evaluation.behavioral_validation import SolverToolPreflight
from task_generator.planning.task_design_executor import (
    TaskDesignExecutionReportV1,
    TaskDesignExecutionRequestV1,
    TaskDesignProposalExecutor,
)
from task_generator.planning.task_design_frontend import CapabilityBriefV1
from task_generator.planning.task_design_frontend import TaskDesignProposalV1


RouteV2 = Literal["skill_guided_llm", "llm_led_hybrid"]
ReplicateId = Literal["a", "b"]
AssignmentStatus = Literal[
    "retained_reality_pass",
    "pending_generation",
    "materialized",
    "reality_pass",
    "solver_completed",
    "grader_completed",
    "blocked",
]
ScreeningDecision = Literal[
    "confirmation_ready_both",
    "single_route_confirmation_candidate",
    "redesign_required",
    "incomplete",
]

MOTIFS = (
    "fan_in_reconciliation",
    "cross_check_validation",
    "policy_application",
)
ROUTES: tuple[RouteV2, ...] = ("skill_guided_llm", "llm_led_hybrid")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _tree_sha(root: Path) -> str:
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        records.append(f"{relative}:{_sha_file(path)}")
    return hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def validate_public_solver_fixture(root: str | Path) -> Path:
    dataset = Path(root).resolve()
    rows = list(dataset.glob("*/dataset_row.json"))
    if len(rows) != 1:
        raise ValueError("deepseek_preflight_requires_one_public_fixture")
    row = json.loads(rows[0].read_text(encoding="utf-8"))
    case = rows[0].parent
    observed = {
        item.relative_to(case).as_posix() for item in case.rglob("*") if item.is_file()
    }
    expected = {
        "dataset_row.json", "deliverable_contract.json", "prompt.md",
        "reference_files/copy_template.xlsx",
    }
    extra = row.get("extra", {})
    if (
        observed != expected
        or row.get("task_id") != "solver_tool_preflight"
        or row.get("reference_files") != ["reference_files/copy_template.xlsx"]
        or sorted(row.get("deliverable_files", [])) != [
            "deliverable_files/created_workbook.xlsx",
            "deliverable_files/edited_template.xlsx",
        ]
        or extra.get("tool_only_preflight") is not True
        or extra.get("business_task") is not False
        or extra.get("grader_authorized") is not False
    ):
        raise ValueError("deepseek_preflight_public_fixture_invalid")
    return case


class MatchedBriefRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief_id: str
    motif: Literal[
        "fan_in_reconciliation", "cross_check_validation", "policy_application"
    ]
    replicate_id: ReplicateId
    brief_path: str
    brief_sha256: str = Field(min_length=64, max_length=64)
    source_group_ids: List[str] = Field(min_length=1, max_length=1)
    paired_brief_id: str


class MatchedScreeningAssignmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    brief_id: str
    motif: str
    replicate_id: ReplicateId
    route_id: RouteV2
    package_root: str
    package_fingerprint: Optional[str] = None
    reality_evidence_sha256: Optional[str] = None
    retained_reality_case_id: Optional[str] = None
    status: AssignmentStatus
    attempt_paths: List[str] = Field(default_factory=list)
    first_failure_path: Optional[str] = None


class MatchedScreeningCampaignV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_version: Literal["v3.matched_screening_campaign.1"] = (
        "v3.matched_screening_campaign.1"
    )
    campaign_id: str
    created_at: str
    source_ledger_path: str
    source_ledger_sha256: str
    admission_report_path: str
    admission_report_sha256: str
    retained_reality_result_path: str
    retained_reality_result_sha256: str
    retained_campaign_manifest_path: str
    retained_campaign_manifest_sha256: str
    repair_readiness_report_path: str
    repair_readiness_report_sha256: str
    source_fingerprint: str
    briefs: List[MatchedBriefRecordV1] = Field(min_length=6, max_length=6)
    assignments: List[MatchedScreeningAssignmentV1] = Field(min_length=12, max_length=12)
    generation_calls_made: bool = False
    generation_provider_call_count: int = Field(default=0, ge=0, le=12)
    generation_reserved_cost_usd: float = Field(default=0.0, ge=0.0, le=24.0)
    solver_calls_made: bool = False
    grader_calls_made: bool = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_shape(self) -> "MatchedScreeningCampaignV1":
        if Counter(item.motif for item in self.briefs) != Counter({motif: 2 for motif in MOTIFS}):
            raise ValueError("matched_screening_brief_motif_shape_invalid")
        if len({item.brief_id for item in self.briefs}) != 6:
            raise ValueError("matched_screening_brief_ids_not_unique")
        expected = {
            (brief.brief_id, route)
            for brief in self.briefs
            for route in ROUTES
        }
        observed = {(item.brief_id, item.route_id) for item in self.assignments}
        if observed != expected or len({item.blind_task_id for item in self.assignments}) != 12:
            raise ValueError("matched_screening_assignment_shape_invalid")
        for item in self.assignments:
            if item.replicate_id == "a" and not item.retained_reality_case_id:
                raise ValueError("replicate_a_reality_case_binding_missing")
            if item.replicate_id == "b" and item.retained_reality_case_id is not None:
                raise ValueError("replicate_b_cannot_reuse_reality_case")
        return self


class MatchedGenerationAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal["v3.matched_generation_authorization_request.1"] = (
        "v3.matched_generation_authorization_request.1"
    )
    campaign_id: str
    requested_scope: Literal["provider_proposal_generation"] = "provider_proposal_generation"
    provider: Literal["tuzi"] = "tuzi"
    model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    requested_blind_task_ids: List[str] = Field(min_length=6, max_length=6)
    requested_routes: List[RouteV2] = Field(min_length=2, max_length=2)
    maximum_attempts_per_assignment: Literal[2] = 2
    maximum_provider_calls: Literal[12] = 12
    maximum_completion_tokens_per_attempt: Literal[16000] = 16000
    maximum_total_cost_usd: float = Field(gt=0, le=24.0)
    retry_mode: Literal["feedback_conditioned_repair_only"] = (
        "feedback_conditioned_repair_only"
    )
    campaign_manifest_sha256: str
    source_ledger_sha256: str
    admission_report_sha256: str
    repair_readiness_report_sha256: str
    source_fingerprint: str
    parity_report_path: str
    parity_report_sha256: str
    excluded_authorities: List[str]
    external_calls_made: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> "MatchedGenerationAuthorizationRequestV1":
        enforce_external_model_policy(self.provider, self.model)
        if sorted(self.requested_routes) != sorted(ROUTES):
            raise ValueError("matched_generation_requires_two_reconstructed_routes")
        if len(set(self.requested_blind_task_ids)) != 6:
            raise ValueError("matched_generation_requires_six_unique_assignments")
        required_exclusions = {
            "solver_execution",
            "grader_execution",
            "professional_review",
            "training",
            "registry_mutation",
            "release_activation",
            "promotion",
        }
        if not required_exclusions <= set(self.excluded_authorities):
            raise ValueError("matched_generation_authority_exclusions_incomplete")
        return self


class MatchedGenerationAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.matched_generation_authorization_receipt.1"] = (
        "v3.matched_generation_authorization_receipt.1"
    )
    campaign_id: str
    authorization_id: str
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    authorized_provider: Literal["tuzi"] = "tuzi"
    authorized_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    authorized_blind_task_ids: List[str] = Field(min_length=6, max_length=6)
    maximum_provider_calls: Literal[12] = 12
    maximum_total_cost_usd: float = Field(gt=0, le=24.0)
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: str
    solver_authorized: Literal[False] = False
    grader_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class MatchedGenerationRecoveryAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal["v3.matched_generation_recovery_request.1"] = (
        "v3.matched_generation_recovery_request.1"
    )
    campaign_id: str
    requested_scope: Literal["single_assignment_replacement_generation"] = (
        "single_assignment_replacement_generation"
    )
    blind_task_id: str
    provider: Literal["tuzi"] = "tuzi"
    model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    recovery_reason: Literal["unusable_schema_response_without_persisted_draft"] = (
        "unusable_schema_response_without_persisted_draft"
    )
    maximum_provider_calls: Literal[1] = 1
    maximum_completion_tokens: Literal[16000] = 16000
    maximum_total_cost_usd: float = Field(gt=0, le=2.0)
    sdk_retries: Literal[0] = 0
    prior_failure_report_sha256: str = Field(min_length=64, max_length=64)
    consumed_request_sha256: str = Field(min_length=64, max_length=64)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    parity_report_path: str
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    excluded_authorities: List[str]
    external_calls_made: Literal[False] = False

    @model_validator(mode="after")
    def validate_scope(self) -> "MatchedGenerationRecoveryAuthorizationRequestV1":
        enforce_external_model_policy(self.provider, self.model)
        required = {
            "other_assignments", "reality_review", "solver_execution",
            "grader_execution", "training", "registry_mutation",
            "release_activation", "promotion",
        }
        if not required <= set(self.excluded_authorities):
            raise ValueError("generation_recovery_exclusions_incomplete")
        return self


class MatchedGenerationRecoveryReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.matched_generation_recovery_receipt.1"] = (
        "v3.matched_generation_recovery_receipt.1"
    )
    campaign_id: str
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    authorized_blind_task_id: str
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: str
    maximum_provider_calls: Literal[1] = 1
    maximum_total_cost_usd: float = Field(gt=0, le=2.0)
    reality_authorized: Literal[False] = False
    solver_authorized: Literal[False] = False
    grader_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class SolverSelectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection_version: Literal["v3.matched_screening_solver_selection.1"] = (
        "v3.matched_screening_solver_selection.1"
    )
    selected_provider: Literal["deepseek", "tuzi"]
    selected_model: Literal["deepseek-v4-pro", "gemini-3.1-pro-preview"]
    selection_reason: Literal["deepseek_preflight_pass", "retained_gemini_fallback"]
    preflight_report_path: str
    preflight_report_sha256: str
    deepseek_failure_path: Optional[str] = None
    deepseek_failure_sha256: Optional[str] = None
    gpt_5_6_solver_allowed: Literal[False] = False


class DeepSeekSolverPreflightAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal[
        "v3.deepseek_solver_preflight_authorization_request.1"
    ] = "v3.deepseek_solver_preflight_authorization_request.1"
    campaign_id: str
    requested_scope: Literal["public_solver_tool_preflight"] = (
        "public_solver_tool_preflight"
    )
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    endpoint: Literal["https://api.deepseek.com"] = "https://api.deepseek.com"
    thinking_mode: Literal["disabled"] = "disabled"
    fixture_tree_sha256: str
    solver_budget: SolverExecutionBudgetV1
    maximum_provider_calls: Literal[8] = 8
    maximum_total_cost_usd: Literal[1.0] = 1.0
    provider_sdk_retries: Literal[0] = 0
    runner_retries: Literal[0] = 0
    campaign_manifest_sha256: str
    parity_report_path: str
    parity_report_sha256: str
    source_fingerprint: str
    private_packages_uploaded: Literal[False] = False
    grader_authorized: Literal[False] = False
    external_calls_made: Literal[False] = False

    @model_validator(mode="after")
    def validate_preflight(self) -> "DeepSeekSolverPreflightAuthorizationRequestV1":
        enforce_external_model_policy(self.provider, self.model)
        budget = self.solver_budget
        if (
            budget.solver_model != self.model
            or budget.maximum_provider_calls != 8
            or budget.maximum_agent_turns != 8
            or budget.maximum_completion_tokens_per_call != 4096
            or budget.maximum_context_tokens != 64000
            or budget.maximum_contract_cost_usd != 1.0
            or budget.provider_sdk_retries != 0
            or budget.runner_retries != 0
        ):
            raise ValueError("deepseek_preflight_budget_mismatch")
        return self


RUBRIC_WEIGHTS = {
    "criterion_factual_accuracy": 0.20,
    "criterion_evidence_traceability": 0.15,
    "criterion_method_process": 0.15,
    "criterion_exception_handling": 0.15,
    "criterion_reproducibility": 0.15,
    "criterion_structural_usability": 0.10,
    "criterion_professional_expression": 0.10,
}


class ScreeningCriterionGradeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: Literal[
        "criterion_factual_accuracy",
        "criterion_evidence_traceability",
        "criterion_method_process",
        "criterion_exception_handling",
        "criterion_reproducibility",
        "criterion_structural_usability",
        "criterion_professional_expression",
    ]
    score: Literal[0.0, 0.5, 1.0]
    rationale: str = Field(min_length=8, max_length=1200)
    evidence_locators: List[str] = Field(min_length=1, max_length=6)


class ScreeningGraderReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_version: Literal["v3.matched_screening_grader_review.1"] = (
        "v3.matched_screening_grader_review.1"
    )
    blind_task_id: str
    criteria: List[ScreeningCriterionGradeV1] = Field(min_length=7, max_length=7)
    major_defect: bool
    major_defect_reason: Optional[str] = None
    professional_plausibility: Literal["pass", "fail"]
    effective_rubric_dimensions: int = Field(ge=0, le=7)
    weighted_score: float = Field(ge=0.0, le=1.0)
    route_identity_seen: Literal[False] = False

    @model_validator(mode="after")
    def validate_grades(self) -> "ScreeningGraderReviewV1":
        by_id = {item.criterion_id: item.score for item in self.criteria}
        if set(by_id) != set(RUBRIC_WEIGHTS) or len(by_id) != 7:
            raise ValueError("screening_grader_criteria_identity_mismatch")
        computed = round(sum(by_id[key] * weight for key, weight in RUBRIC_WEIGHTS.items()), 6)
        if abs(computed - self.weighted_score) > 1e-6:
            raise ValueError("screening_grader_weighted_score_mismatch")
        if self.major_defect and not self.major_defect_reason:
            raise ValueError("screening_grader_major_defect_reason_missing")
        return self


class MatchedBusinessAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal["v3.matched_business_authorization_request.1"] = (
        "v3.matched_business_authorization_request.1"
    )
    campaign_id: str
    requested_scope: Literal["matched_solver_and_single_grader_screening"] = (
        "matched_solver_and_single_grader_screening"
    )
    selected_solver: SolverSelectionV1
    blind_package_fingerprints: Dict[str, str]
    candidate_tree_sha256: Dict[str, str]
    reality_evidence_sha256: Dict[str, str]
    solver_budget_per_task: SolverExecutionBudgetV1
    solver_task_count: Literal[12] = 12
    solver_attempts_per_task: Literal[1] = 1
    solver_total_cost_ceiling_usd: float = Field(gt=0.0, le=24.0)
    grader_provider: Literal["deepseek"] = "deepseek"
    grader_model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    grader_thinking: Literal["enabled_high"] = "enabled_high"
    grader_maximum_input_tokens_per_call: Literal[20000] = 20000
    grader_maximum_completion_tokens_per_call: Literal[4000] = 4000
    grader_maximum_provider_calls: Literal[24] = 24
    grader_maximum_total_cost_usd: Literal[0.5] = 0.5
    grader_substantive_scores_per_valid_delivery: Literal[1] = 1
    grader_retry_mode: Literal["format_or_transport_only"] = "format_or_transport_only"
    provider_sdk_retries: Literal[0] = 0
    runner_retries: Literal[0] = 0
    campaign_manifest_sha256: str
    staging_report_sha256: str
    solver_selection_sha256: str
    parity_report_path: str
    parity_report_sha256: str
    source_fingerprint: str
    professional_validity_status: Literal["provisional"] = "provisional"
    expert_review_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    external_calls_made: Literal[False] = False

    @model_validator(mode="after")
    def validate_business_scope(self) -> "MatchedBusinessAuthorizationRequestV1":
        expected = set(self.blind_package_fingerprints)
        if len(expected) != 12 or set(self.candidate_tree_sha256) != expected or set(self.reality_evidence_sha256) != expected:
            raise ValueError("matched_business_twelve_package_binding_mismatch")
        budget = self.solver_budget_per_task
        if (
            budget.solver_model != self.selected_solver.selected_model
            or budget.maximum_provider_calls != 12
            or budget.maximum_agent_turns != 12
            or budget.maximum_context_tokens != 64000
            or budget.maximum_completion_tokens_per_call != 8000
            or budget.provider_sdk_retries != 0
            or budget.runner_retries != 0
        ):
            raise ValueError("matched_business_solver_budget_mismatch")
        expected_cap = 12.0 if self.selected_solver.selected_provider == "deepseek" else 24.0
        if self.solver_total_cost_ceiling_usd != expected_cap:
            raise ValueError("matched_business_solver_cost_mismatch")
        return self


class ScreeningTaskObservationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    route_id: RouteV2
    motif: str
    replicate_id: ReplicateId
    infrastructure_complete: bool
    offline_validity_pass: bool
    exact_valid_delivery: bool
    major_defect: bool
    professional_plausibility_pass: bool
    productive_complexity_pass: bool
    skill_causal_pass: bool
    effective_rubric_dimensions: int = Field(ge=0, le=7)
    weighted_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ScreeningRouteSummaryV1(BaseModel):
    route_id: RouteV2
    task_count: int
    offline_validity_count: int
    exact_valid_delivery_count: int
    major_defect_count: int
    professional_plausibility_count: int
    productive_complexity_count: int
    skill_causal_count: int
    saturation_count: int
    absolute_gate_pass: bool


class MatchedScreeningResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["v3.matched_screening_result.1"] = (
        "v3.matched_screening_result.1"
    )
    campaign_id: str
    observations: List[ScreeningTaskObservationV1] = Field(min_length=12, max_length=12)
    route_summaries: List[ScreeningRouteSummaryV1] = Field(min_length=2, max_length=2)
    comparable_pair_count: int = Field(ge=0, le=6)
    decision: ScreeningDecision
    professional_validity_status: Literal["provisional"] = "provisional"
    expert_evidence_present: Literal[False] = False
    training_admission_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class MatchedScreeningAnalyzer:
    def analyze(
        self, campaign_id: str, observations: List[ScreeningTaskObservationV1]
    ) -> MatchedScreeningResultV1:
        if len(observations) != 12 or len({item.blind_task_id for item in observations}) != 12:
            raise ValueError("matched_screening_requires_twelve_unique_observations")
        if any(not item.infrastructure_complete for item in observations):
            decision: ScreeningDecision = "incomplete"
        else:
            decision = "redesign_required"
        summaries: List[ScreeningRouteSummaryV1] = []
        route_passes: Dict[str, bool] = {}
        for route in ROUTES:
            rows = [item for item in observations if item.route_id == route]
            if len(rows) != 6:
                raise ValueError("matched_screening_requires_six_tasks_per_route")
            saturation = sum(
                item.weighted_score is not None and item.weighted_score >= 0.9
                for item in rows
            )
            gate = (
                sum(item.offline_validity_pass for item in rows) == 6
                and sum(item.exact_valid_delivery for item in rows) >= 5
                and sum(item.major_defect for item in rows) == 0
                and sum(item.professional_plausibility_pass for item in rows) >= 5
                and sum(item.productive_complexity_pass for item in rows) >= 5
                and sum(item.skill_causal_pass for item in rows) == 6
                and all(
                    item.effective_rubric_dimensions >= 5
                    for item in rows
                    if item.exact_valid_delivery
                )
                and saturation <= 4
            )
            route_passes[route] = gate
            summaries.append(
                ScreeningRouteSummaryV1(
                    route_id=route,
                    task_count=6,
                    offline_validity_count=sum(item.offline_validity_pass for item in rows),
                    exact_valid_delivery_count=sum(item.exact_valid_delivery for item in rows),
                    major_defect_count=sum(item.major_defect for item in rows),
                    professional_plausibility_count=sum(item.professional_plausibility_pass for item in rows),
                    productive_complexity_count=sum(item.productive_complexity_pass for item in rows),
                    skill_causal_count=sum(item.skill_causal_pass for item in rows),
                    saturation_count=saturation,
                    absolute_gate_pass=gate,
                )
            )
        pairs: Dict[tuple[str, str], set[str]] = {}
        for item in observations:
            if item.infrastructure_complete and item.weighted_score is not None:
                pairs.setdefault((item.motif, item.replicate_id), set()).add(item.route_id)
        comparable = sum(routes == set(ROUTES) for routes in pairs.values())
        if all(item.infrastructure_complete for item in observations):
            passing = sum(route_passes.values())
            if passing == 2 and comparable >= 5:
                decision = "confirmation_ready_both"
            elif passing == 1:
                decision = "single_route_confirmation_candidate"
            else:
                decision = "redesign_required"
        return MatchedScreeningResultV1(
            campaign_id=campaign_id,
            observations=observations,
            route_summaries=summaries,
            comparable_pair_count=comparable,
            decision=decision,
        )


class MatchedScreeningCampaign:
    MANIFEST_NAME = "matched_screening_campaign.json"

    def __init__(self, campaign_root: str | Path) -> None:
        self.root = Path(campaign_root).resolve()
        self.manifest_path = self.root / self.MANIFEST_NAME

    @staticmethod
    def compile_replicate_b(brief_a: CapabilityBriefV1) -> CapabilityBriefV1:
        payload = brief_a.model_dump(mode="json")
        motif = brief_a.motif
        variants = {
            "fan_in_reconciliation": (
                "A quarter-end control-evidence refresh reveals conflicting owner, cadence, and support records.",
                "Reconcile the conflicting evidence into an exception-ready workpaper for manager review.",
            ),
            "cross_check_validation": (
                "An internal review challenges a preliminary operating-effectiveness conclusion.",
                "Test the conclusion through independent evidence paths and document unresolved discrepancies.",
            ),
            "policy_application": (
                "A revised finance-control procedure must be applied to the current governed evidence set.",
                "Map the stated requirements, classify deviations, and prioritize remediation without inventing policy.",
            ),
        }
        if motif not in variants:
            raise ValueError("replicate_b_forbidden_motif")
        payload["case_id"] = f"{brief_a.case_id}_replicate_b"
        payload["trigger_event"], payload["business_goal"] = variants[motif]
        payload["workflow_context"]["subgraph_id"] = (
            f"{brief_a.workflow_context.subgraph_id}_replicate_b"
        )
        payload["domain_and_safety_constraints"] = list(
            payload["domain_and_safety_constraints"]
        ) + [
            "Generate a fresh governed scenario whose record identifiers differ from replicate A; do not copy prior scenario records."
        ]
        seed = {
            "paired_brief_id": brief_a.brief_id,
            "motif": motif,
            "case_id": payload["case_id"],
            "trigger_event": payload["trigger_event"],
            "business_goal": payload["business_goal"],
        }
        payload["brief_id"] = "brief_" + _sha_json(seed)[:12]
        return CapabilityBriefV1.model_validate(payload)

    def prepare(
        self,
        *,
        campaign_id: str,
        replicate_a_brief_paths: List[str | Path],
        replicate_a_packages: Dict[str, Dict[RouteV2, str]],
        replicate_a_campaign_manifest_path: str | Path,
        source_ledger_path: str | Path,
        retained_reality_result_path: str | Path,
        repair_readiness_report_path: str | Path,
        repository_root: str | Path,
    ) -> MatchedScreeningCampaignV1:
        if self.root.exists():
            raise FileExistsError("matched_screening_campaign_root_exists")
        a_briefs = [
            CapabilityBriefV1.model_validate_json(Path(path).read_text(encoding="utf-8"))
            for path in replicate_a_brief_paths
        ]
        if {item.motif for item in a_briefs} != set(MOTIFS) or len(a_briefs) != 3:
            raise ValueError("replicate_a_requires_three_non_experimental_motifs")
        b_briefs = [self.compile_replicate_b(item) for item in a_briefs]
        ledger_path = Path(source_ledger_path).resolve()
        ledger = SourceProvenanceLedgerV1.model_validate_json(
            ledger_path.read_text(encoding="utf-8")
        )
        admission = FormalBriefCohortAdmission().evaluate_matched_screening(
            a_briefs + b_briefs, ledger
        )
        if admission.decision != "pass":
            raise ValueError("matched_screening_admission_blocked")
        reality_path = Path(retained_reality_result_path).resolve()
        reality = json.loads(reality_path.read_text(encoding="utf-8"))
        if reality.get("decision") != "screening_ready" or reality.get("screening_eligible") is not True:
            raise ValueError("retained_reality_evidence_not_screening_ready")
        retained_manifest_path = Path(replicate_a_campaign_manifest_path).resolve()
        retained_manifest = json.loads(retained_manifest_path.read_text(encoding="utf-8"))
        retained_assignments = {
            (item["brief_id"], item["route_id"]): item
            for item in retained_manifest.get("assignments", [])
            if item.get("route_id") in ROUTES
        }
        reality_case_ids = {item.get("case_id") for item in reality.get("cases", [])}
        repair_path = Path(repair_readiness_report_path).resolve()
        if not repair_path.is_file():
            raise FileNotFoundError("repair_readiness_report_missing")

        governance = self.root / "governance"
        brief_root = governance / "briefs"
        brief_root.mkdir(parents=True)
        admission_path = governance / "matched_brief_admission.json"
        _atomic_json(admission_path, admission.model_dump(mode="json"))
        records: List[MatchedBriefRecordV1] = []
        assignments: List[MatchedScreeningAssignmentV1] = []
        pairs = {a.motif: (a, b) for a, b in zip(a_briefs, b_briefs)}
        for motif in MOTIFS:
            a, b = pairs[motif]
            for replicate_id, brief, paired in (("a", a, b), ("b", b, a)):
                brief_path = brief_root / f"{brief.brief_id}.json"
                _atomic_json(brief_path, brief.model_dump(mode="json"))
                source_groups = sorted(
                    {
                        record.source_group_id
                        for record in ledger.records
                        if record.source_candidate_id
                        in {source.source_ref_id for source in brief.source_refs}
                        and record.source_group_id
                    }
                )
                records.append(
                    MatchedBriefRecordV1(
                        brief_id=brief.brief_id,
                        motif=motif,
                        replicate_id=replicate_id,
                        brief_path=str(brief_path.resolve()),
                        brief_sha256=_sha_file(brief_path),
                        source_group_ids=source_groups,
                        paired_brief_id=paired.brief_id,
                    )
                )
                for route in ROUTES:
                    blind_id = "ms_" + _sha_json(
                        {"campaign": campaign_id, "brief": brief.brief_id, "route": route}
                    )[:16]
                    if replicate_id == "a":
                        package = Path(replicate_a_packages[brief.brief_id][route]).resolve()
                        if not package.is_dir():
                            raise FileNotFoundError("retained_package_missing")
                        package_fingerprint = _tree_sha(package)
                        retained = retained_assignments.get((brief.brief_id, route))
                        if retained is None:
                            raise ValueError("retained_campaign_assignment_missing")
                        if retained.get("package_fingerprint") != package_fingerprint:
                            raise ValueError("retained_package_fingerprint_mismatch")
                        retained_case_id = retained.get("blind_task_id")
                        if retained_case_id not in reality_case_ids:
                            raise ValueError("retained_reality_case_binding_missing")
                        status: AssignmentStatus = "retained_reality_pass"
                        reality_sha = _sha_file(reality_path)
                    else:
                        package = self.root / "route_packages" / brief.brief_id / route
                        package_fingerprint = None
                        status = "pending_generation"
                        reality_sha = None
                        retained_case_id = None
                    assignments.append(
                        MatchedScreeningAssignmentV1(
                            blind_task_id=blind_id,
                            brief_id=brief.brief_id,
                            motif=motif,
                            replicate_id=replicate_id,
                            route_id=route,
                            package_root=str(package),
                            package_fingerprint=package_fingerprint,
                            reality_evidence_sha256=reality_sha,
                            retained_reality_case_id=retained_case_id,
                            status=status,
                        )
                    )
        campaign = MatchedScreeningCampaignV1(
            campaign_id=campaign_id,
            created_at=_now(),
            source_ledger_path=str(ledger_path),
            source_ledger_sha256=_sha_file(ledger_path),
            admission_report_path=str(admission_path.resolve()),
            admission_report_sha256=_sha_file(admission_path),
            retained_reality_result_path=str(reality_path),
            retained_reality_result_sha256=_sha_file(reality_path),
            retained_campaign_manifest_path=str(retained_manifest_path),
            retained_campaign_manifest_sha256=_sha_file(retained_manifest_path),
            repair_readiness_report_path=str(repair_path),
            repair_readiness_report_sha256=_sha_file(repair_path),
            source_fingerprint=governed_source_fingerprint(repository_root),
            briefs=records,
            assignments=assignments,
        )
        _atomic_json(self.manifest_path, campaign.model_dump(mode="json"))
        return campaign

    def compile_generation_request(
        self, *, parity_report_path: str | Path, maximum_total_cost_usd: float = 24.0
    ) -> tuple[MatchedGenerationAuthorizationRequestV1, Path, str]:
        campaign = MatchedScreeningCampaignV1.model_validate_json(
            self.manifest_path.read_text(encoding="utf-8")
        )
        parity_path = Path(parity_report_path).resolve()
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        checks = {
            "passed": parity.get("passed") is True,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "fingerprint": parity.get("source_fingerprint") == campaign.source_fingerprint,
        }
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError("matched_generation_parity_invalid:" + ",".join(failed))
        pending = [item for item in campaign.assignments if item.replicate_id == "b"]
        request = MatchedGenerationAuthorizationRequestV1(
            campaign_id=campaign.campaign_id,
            requested_blind_task_ids=sorted(item.blind_task_id for item in pending),
            requested_routes=list(ROUTES),
            maximum_total_cost_usd=maximum_total_cost_usd,
            campaign_manifest_sha256=_sha_file(self.manifest_path),
            source_ledger_sha256=campaign.source_ledger_sha256,
            admission_report_sha256=campaign.admission_report_sha256,
            repair_readiness_report_sha256=campaign.repair_readiness_report_sha256,
            source_fingerprint=campaign.source_fingerprint,
            parity_report_path=str(parity_path),
            parity_report_sha256=_sha_file(parity_path),
            excluded_authorities=[
                "solver_execution",
                "grader_execution",
                "professional_review",
                "training",
                "registry_mutation",
                "release_activation",
                "promotion",
            ],
        )
        current = self.root / "governance" / "generation_authorization_request.json"
        _atomic_json(current, request.model_dump(mode="json"))
        request_sha = _sha_file(current)
        immutable = self.root / "governance" / "generation_authorization_requests" / f"{request_sha}.json"
        immutable.parent.mkdir(parents=True, exist_ok=True)
        if immutable.exists() and _sha_file(immutable) != request_sha:
            raise FileExistsError("immutable_generation_request_conflict")
        if not immutable.exists():
            shutil.copy2(current, immutable)
        return request, immutable, request_sha

    def compile_generation_receipt(
        self,
        *,
        immutable_request_path: str | Path,
        authorization_id: str,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> MatchedGenerationAuthorizationReceiptV1:
        request_path = Path(immutable_request_path).resolve()
        immutable_root = (
            self.root / "governance" / "generation_authorization_requests"
        ).resolve()
        if request_path.parent != immutable_root:
            raise ValueError("generation_receipt_requires_immutable_request")
        request_sha = _sha_file(request_path)
        if request_path.name != f"{request_sha}.json":
            raise ValueError("generation_request_filename_hash_mismatch")
        request = MatchedGenerationAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_generation_request(request, request_sha)
        receipt = MatchedGenerationAuthorizationReceiptV1(
            campaign_id=request.campaign_id,
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            authorized_blind_task_ids=request.requested_blind_task_ids,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_now(),
            expires_at=expires_at,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("generation_receipt_already_exists")
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def execute_generation(
        self,
        *,
        receipt_path: str | Path,
        provider_config: ProviderConfig,
        executor: Optional[TaskDesignProposalExecutor] = None,
    ) -> MatchedScreeningCampaignV1:
        campaign = self.read()
        request_path = self.root / "governance" / "generation_authorization_request.json"
        request_sha = _sha_file(request_path)
        request = MatchedGenerationAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_generation_request(request, request_sha)
        receipt = MatchedGenerationAuthorizationReceiptV1.model_validate_json(
            Path(receipt_path).read_text(encoding="utf-8")
        )
        if (
            receipt.authorization_request_sha256 != request_sha
            or receipt.campaign_id != campaign.campaign_id
            or set(receipt.authorized_blind_task_ids)
            != set(request.requested_blind_task_ids)
        ):
            raise PermissionError("generation_receipt_scope_mismatch")
        if provider_config.provider_name != "tuzi" or provider_config.model != "gpt-5.6-sol":
            raise ValueError("generation_provider_config_mismatch")
        enforce_external_model_policy(provider_config.provider_name, provider_config.model)
        proposal_executor = executor or TaskDesignProposalExecutor()
        briefs = {
            item.brief_id: CapabilityBriefV1.model_validate_json(
                Path(item.brief_path).read_text(encoding="utf-8")
            )
            for item in campaign.briefs
        }
        for assignment in campaign.assignments:
            if assignment.blind_task_id not in receipt.authorized_blind_task_ids:
                continue
            if assignment.status == "materialized":
                continue
            prior_report: Optional[TaskDesignExecutionReportV1] = None
            for attempt in range(1, 3):
                if campaign.generation_provider_call_count >= receipt.maximum_provider_calls:
                    raise RuntimeError("matched_generation_call_ceiling_exhausted")
                if campaign.generation_reserved_cost_usd + 2.0 > receipt.maximum_total_cost_usd:
                    raise RuntimeError("matched_generation_cost_ceiling_exhausted")
                if prior_report is not None:
                    repairable = (
                        prior_report.status == "proposal_blocked" and prior_report.proposal_path
                    ) or (
                        prior_report.status == "semantic_proposal_blocked"
                        and prior_report.semantic_proposal_path
                    )
                    if not repairable:
                        break
                run_root = (
                    self.root
                    / "provider_runs"
                    / assignment.brief_id
                    / assignment.route_id
                    / f"attempt_{attempt:02d}"
                )
                campaign.generation_calls_made = True
                campaign.generation_provider_call_count += 1
                campaign.generation_reserved_cost_usd = round(
                    campaign.generation_reserved_cost_usd + 2.0, 4
                )
                self.write(campaign)
                report = proposal_executor.run(
                    TaskDesignExecutionRequestV1(
                        capability_brief_path=next(
                            item.brief_path
                            for item in campaign.briefs
                            if item.brief_id == assignment.brief_id
                        ),
                        output_dir=str(run_root),
                        route_id=assignment.route_id,
                        model="gpt-5.6-sol",
                        allow_external_provider=True,
                        allow_expensive_model=False,
                        timeout_seconds=900,
                        max_tokens=16000,
                        repair_from_execution_report_path=(
                            assignment.attempt_paths[-1]
                            if assignment.attempt_paths
                            else None
                        ),
                    ),
                    provider_config,
                )
                report_path = run_root / "task_design_execution_report.json"
                assignment.attempt_paths.append(str(report_path.resolve()))
                prior_report = report
                if report.status != "completed":
                    if assignment.first_failure_path is None:
                        assignment.first_failure_path = str(report_path.resolve())
                    self.write(campaign)
                    continue
                proposal = TaskDesignProposalV1.model_validate_json(
                    Path(report.proposal_path or "").read_text(encoding="utf-8")
                )
                package_root = Path(assignment.package_root)
                materialization = HybridTaskMaterializer().materialize(
                    briefs[assignment.brief_id], proposal, package_root
                )
                if materialization.decision != "pass":
                    assignment.status = "blocked"
                    self.write(campaign)
                    break
                package_sha = _tree_sha(package_root)
                paired_a = next(
                    item
                    for item in campaign.assignments
                    if item.motif == assignment.motif
                    and item.route_id == assignment.route_id
                    and item.replicate_id == "a"
                )
                if package_sha == paired_a.package_fingerprint:
                    assignment.status = "blocked"
                    assignment.first_failure_path = str(
                        (package_root / "hybrid_materialization_report.json").resolve()
                    )
                    self.write(campaign)
                    break
                assignment.package_fingerprint = package_sha
                assignment.status = "materialized"
                self.write(campaign)
                break
            if assignment.status == "pending_generation" and assignment.attempt_paths:
                assignment.status = "blocked"
                self.write(campaign)
        return self.read()

    def synchronize_source_fingerprint(self, repository_root: str | Path) -> str:
        campaign = self.read()
        campaign.source_fingerprint = governed_source_fingerprint(repository_root)
        self.write(campaign)
        return campaign.source_fingerprint

    def compile_generation_recovery_request(
        self,
        *,
        blind_task_id: str,
        consumed_request_sha256: str,
        parity_report_path: str | Path,
    ) -> tuple[MatchedGenerationRecoveryAuthorizationRequestV1, Path, str]:
        campaign = self.read()
        target = next(
            (item for item in campaign.assignments if item.blind_task_id == blind_task_id),
            None,
        )
        if target is None or target.replicate_id != "b" or target.status != "blocked":
            raise ValueError("generation_recovery_target_not_blocked")
        if len(target.attempt_paths) != 1:
            raise ValueError("generation_recovery_requires_one_frozen_attempt")
        failure_path = Path(target.attempt_paths[0]).resolve()
        failure = TaskDesignExecutionReportV1.model_validate_json(
            failure_path.read_text(encoding="utf-8")
        )
        if (
            failure.failure_type != "TaskDesignSemanticNormalizationBlocked"
            or failure.proposal_path
            or failure.semantic_proposal_path
        ):
            raise ValueError("generation_recovery_failure_not_eligible")
        consumed = (
            self.root / "governance" / "generation_authorization_requests"
            / f"{consumed_request_sha256}.json"
        )
        if not consumed.is_file() or _sha_file(consumed) != consumed_request_sha256:
            raise ValueError("generation_recovery_consumed_request_missing")
        parity_path = Path(parity_report_path).resolve()
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        current_fingerprint = governed_source_fingerprint(Path(__file__).resolve().parents[2])
        checks = (
            parity.get("passed") is True,
            parity.get("network_mode") == "none",
            parity.get("read_only_root") is True,
            parity.get("provider_credentials_mounted") is False,
            parity.get("cleanup_returncode") == 0,
            parity.get("source_fingerprint") == campaign.source_fingerprint == current_fingerprint,
        )
        if not all(checks):
            raise ValueError("generation_recovery_parity_invalid")
        request = MatchedGenerationRecoveryAuthorizationRequestV1(
            campaign_id=campaign.campaign_id,
            blind_task_id=blind_task_id,
            maximum_total_cost_usd=2.0,
            prior_failure_report_sha256=_sha_file(failure_path),
            consumed_request_sha256=consumed_request_sha256,
            campaign_manifest_sha256=_sha_file(self.manifest_path),
            source_fingerprint=campaign.source_fingerprint,
            parity_report_path=str(parity_path),
            parity_report_sha256=_sha_file(parity_path),
            excluded_authorities=[
                "other_assignments", "reality_review", "solver_execution",
                "grader_execution", "training", "registry_mutation",
                "release_activation", "promotion",
            ],
        )
        return self._write_request("generation_recovery", request.model_dump(mode="json"))

    def compile_generation_recovery_receipt(
        self,
        *,
        immutable_request_path: str | Path,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> MatchedGenerationRecoveryReceiptV1:
        request_path = Path(immutable_request_path).resolve()
        request_sha = _sha_file(request_path)
        if request_path.name != f"{request_sha}.json":
            raise ValueError("generation_recovery_request_filename_hash_mismatch")
        request = MatchedGenerationRecoveryAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        receipt = MatchedGenerationRecoveryReceiptV1(
            campaign_id=request.campaign_id,
            authorization_request_sha256=request_sha,
            authorized_blind_task_id=request.blind_task_id,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_now(),
            expires_at=expires_at,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("generation_recovery_receipt_exists")
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def execute_generation_recovery(
        self,
        *,
        receipt_path: str | Path,
        provider_config: ProviderConfig,
    ) -> MatchedScreeningCampaignV1:
        request_path = self.root / "governance" / "generation_recovery_authorization_request.json"
        request_sha = _sha_file(request_path)
        request = MatchedGenerationRecoveryAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        receipt = MatchedGenerationRecoveryReceiptV1.model_validate_json(
            Path(receipt_path).read_text(encoding="utf-8")
        )
        if (
            receipt.authorization_request_sha256 != request_sha
            or receipt.authorized_blind_task_id != request.blind_task_id
        ):
            raise PermissionError("generation_recovery_receipt_scope_mismatch")
        if provider_config.provider_name != "tuzi" or provider_config.model != "gpt-5.6-sol":
            raise ValueError("generation_recovery_provider_mismatch")
        campaign = self.read()
        if _sha_file(self.manifest_path) != request.campaign_manifest_sha256:
            raise ValueError("generation_recovery_campaign_drift")
        target = next(item for item in campaign.assignments if item.blind_task_id == request.blind_task_id)
        if target.status != "blocked":
            raise ValueError("generation_recovery_target_state_changed")
        run_root = self.root / "provider_recovery_runs" / target.brief_id / target.route_id / request_sha[:16]
        campaign.generation_calls_made = True
        campaign.generation_provider_call_count += 1
        campaign.generation_reserved_cost_usd = round(campaign.generation_reserved_cost_usd + 2.0, 4)
        self.write(campaign)
        report = TaskDesignProposalExecutor().run(
            TaskDesignExecutionRequestV1(
                capability_brief_path=next(item.brief_path for item in campaign.briefs if item.brief_id == target.brief_id),
                output_dir=str(run_root), route_id=target.route_id, model="gpt-5.6-sol",
                allow_external_provider=True, allow_expensive_model=False,
                timeout_seconds=900, max_tokens=16000,
            ),
            provider_config,
        )
        report_path = run_root / "task_design_execution_report.json"
        target.attempt_paths.append(str(report_path.resolve()))
        if report.status != "completed":
            target.status = "blocked"
            self.write(campaign)
            return self.read()
        proposal = TaskDesignProposalV1.model_validate_json(Path(report.proposal_path or "").read_text(encoding="utf-8"))
        brief = next(
            CapabilityBriefV1.model_validate_json(Path(item.brief_path).read_text(encoding="utf-8"))
            for item in campaign.briefs if item.brief_id == target.brief_id
        )
        package_root = self.root / "recovery_packages" / target.brief_id / target.route_id / request_sha[:16]
        materialization = HybridTaskMaterializer().materialize(brief, proposal, package_root)
        if materialization.decision != "pass":
            target.status = "blocked"
        else:
            target.package_root = str(package_root.resolve())
            target.package_fingerprint = _tree_sha(package_root)
            target.status = "materialized"
        self.write(campaign)
        return self.read()

    def stage_and_write_replicate_b_reality_selection(
        self,
    ) -> tuple[dict, RealityReviewSelectionV1]:
        campaign = self.read()
        if any(
            item.replicate_id == "b" and item.status != "materialized"
            for item in campaign.assignments
        ):
            raise ValueError("replicate_b_packages_not_materialized")
        output = self.root / "blind_staging"
        if output.exists():
            raise FileExistsError("matched_blind_staging_exists")
        packages_root = output / "candidate_packages"
        governance_root = output / "governance"
        packages_root.mkdir(parents=True)
        governance_root.mkdir(parents=True)
        stager = RouteBlindPackageStager()
        records = []
        for assignment in campaign.assignments:
            source = stager._resolve_export_root(assignment.package_root)
            stager._assert_candidate_only(source)
            target = packages_root / assignment.blind_task_id
            shutil.copytree(source, target)
            stager._sanitize_candidate_package(target, assignment.blind_task_id)
            validation = RwTaskExportValidator().validate(target)
            if validation.validation_status == "invalid":
                raise ValueError(
                    f"matched_blind_package_invalid:{assignment.blind_task_id}"
                )
            records.append(
                {
                    "blind_task_id": assignment.blind_task_id,
                    "brief_id": assignment.brief_id,
                    "route_id": assignment.route_id,
                    "replicate_id": assignment.replicate_id,
                    "source_export_root": str(source),
                    "staged_export_root": str(target),
                    "source_package_fingerprint": stager._directory_fingerprint(source),
                    "staged_package_fingerprint": stager._directory_fingerprint(target),
                    "validation_status": validation.validation_status,
                }
            )
        report = {
            "report_version": "v3.matched_route_blind_staging.1",
            "campaign_id": campaign.campaign_id,
            "decision": "pass",
            "package_count": 12,
            "records": records,
            "route_identity_candidate_visible": False,
            "external_calls_made": False,
        }
        report_path = governance_root / "route_blind_staging_report.json"
        _atomic_json(report_path, report)
        # RealityReviewCampaign reads a generic assignment list. This
        # compatibility manifest is generated from, and hash-bound to, the
        # authoritative matched manifest; it does not claim V31 semantics.
        compatibility = campaign.model_dump(mode="json")
        compatibility["authoritative_matched_manifest_path"] = str(self.manifest_path)
        compatibility["authoritative_matched_manifest_sha256"] = _sha_file(
            self.manifest_path
        )
        _atomic_json(self.root / "campaign_manifest.json", compatibility)
        selected = [item for item in campaign.assignments if item.replicate_id == "b"]
        selection = RealityReviewSelectionV1(
            manifest_version="v3.reality_cohort_selection.1",
            cohort_id=f"{campaign.campaign_id}_replicate_b_reality",
            selection_status="frozen",
            selection_rule="replicate_b_two_routes_three_non_experimental_motifs",
            case_count=6,
            routes=list(ROUTES),
            motifs=list(MOTIFS),
            experimental_evidence_to_deliverable_excluded=True,
            cases=[
                RealityReviewSelectionCaseV1(
                    case_id=item.blind_task_id,
                    brief_id=item.brief_id,
                    motif=item.motif,
                    route_id=item.route_id,
                    package_fingerprint=item.package_fingerprint or "",
                )
                for item in selected
            ],
            review_dimensions=[
                "role_realism",
                "information_sufficiency",
                "natural_difficulty",
                "professional_judgment",
                "deliverable_realism",
                "rubric_focus",
            ],
            reviewer_route_blinding_required=True,
            independent_reviewer_required=True,
            professional_review_executed=False,
            external_calls_made=False,
            training_admission_authorized=False,
            promotion_authorized=False,
        )
        selection_path = self.root / "governance" / "replicate_b_reality_selection.json"
        _atomic_json(selection_path, selection.model_dump(mode="json"))
        return report, selection

    def record_replicate_b_reality_result(
        self, result_path: str | Path
    ) -> MatchedScreeningCampaignV1:
        result_file = Path(result_path).resolve()
        result = json.loads(result_file.read_text(encoding="utf-8"))
        if result.get("decision") != "screening_ready" or result.get("screening_eligible") is not True:
            raise ValueError("replicate_b_reality_not_screening_ready")
        cases = result.get("cases", [])
        passed = {
            item.get("case_id")
            for item in cases
            if item.get("overall_decision") == "pass"
        }
        campaign = self.read()
        expected = {
            item.blind_task_id
            for item in campaign.assignments
            if item.replicate_id == "b"
        }
        if passed != expected:
            raise ValueError("replicate_b_reality_case_coverage_mismatch")
        evidence_sha = _sha_file(result_file)
        for item in campaign.assignments:
            if item.replicate_id == "b":
                item.reality_evidence_sha256 = evidence_sha
                item.status = "reality_pass"
        self.write(campaign)
        return campaign

    def compile_deepseek_preflight_request(
        self,
        *,
        fixture_root: str | Path,
        parity_report_path: str | Path,
    ) -> tuple[DeepSeekSolverPreflightAuthorizationRequestV1, Path, str]:
        campaign = self.read()
        fixture = Path(fixture_root).resolve()
        validate_public_solver_fixture(fixture)
        parity_path = Path(parity_report_path).resolve()
        self._validate_parity(parity_path, campaign.source_fingerprint)
        budget = SolverExecutionBudgetV1(
            solver_model="deepseek-v4-pro",
            maximum_provider_calls=8,
            maximum_agent_turns=8,
            maximum_request_bytes_per_call=131072,
            maximum_completion_tokens_per_call=4096,
            maximum_provider_input_tokens=131072,
            maximum_provider_output_tokens=8192,
            input_cost_usd_per_million_tokens=10.0,
            output_cost_usd_per_million_tokens=30.0,
            maximum_contract_cost_usd=1.0,
            provider_sdk_retries=0,
            runner_retries=0,
            require_finish_signal=True,
            require_nonempty_deliverable=True,
            maximum_context_tokens=64000,
        )
        request = DeepSeekSolverPreflightAuthorizationRequestV1(
            campaign_id=campaign.campaign_id,
            fixture_tree_sha256=_tree_sha(fixture),
            solver_budget=budget,
            campaign_manifest_sha256=_sha_file(self.manifest_path),
            parity_report_path=str(parity_path),
            parity_report_sha256=_sha_file(parity_path),
            source_fingerprint=campaign.source_fingerprint,
        )
        return self._write_request(
            "deepseek_preflight", request.model_dump(mode="json")
        )

    def prepare_deepseek_preflight_fixture(self, fixture_root: str | Path) -> Path:
        dataset = Path(fixture_root).resolve()
        if dataset.exists() and any(dataset.iterdir()):
            raise FileExistsError("deepseek_preflight_fixture_root_not_empty")
        case = dataset / "solver_tool_preflight"
        fixture = SolverToolPreflight().create_fixture(case)
        _atomic_json(
            case / "dataset_row.json",
            {
                "task_id": "solver_tool_preflight",
                "prompt": Path(fixture["prompt_path"]).read_text(encoding="utf-8"),
                "reference_files": ["reference_files/copy_template.xlsx"],
                "deliverable_files": [
                    "deliverable_files/created_workbook.xlsx",
                    "deliverable_files/edited_template.xlsx",
                ],
                "extra": {
                    "tool_only_preflight": True,
                    "business_task": False,
                    "grader_authorized": False,
                },
            },
        )
        validate_public_solver_fixture(dataset)
        return dataset

    def compile_business_request(
        self,
        *,
        solver_selection_path: str | Path,
        parity_report_path: str | Path,
    ) -> tuple[MatchedBusinessAuthorizationRequestV1, Path, str]:
        campaign = self.read()
        if any(
            item.status not in {"retained_reality_pass", "reality_pass"}
            for item in campaign.assignments
        ):
            raise ValueError("matched_business_requires_twelve_reality_passes")
        selection_path = Path(solver_selection_path).resolve()
        selection = SolverSelectionV1.model_validate_json(
            selection_path.read_text(encoding="utf-8")
        )
        parity_path = Path(parity_report_path).resolve()
        self._validate_parity(parity_path, campaign.source_fingerprint)
        staging_path = (
            self.root
            / "blind_staging"
            / "governance"
            / "route_blind_staging_report.json"
        )
        if not staging_path.is_file():
            raise FileNotFoundError("matched_business_staging_report_missing")
        candidate_root = self.root / "blind_staging" / "candidate_packages"
        solver_cost = 1.0 if selection.selected_provider == "deepseek" else 2.0
        budget = SolverExecutionBudgetV1(
            solver_model=selection.selected_model,
            maximum_provider_calls=12,
            maximum_agent_turns=12,
            maximum_request_bytes_per_call=262144,
            maximum_completion_tokens_per_call=8000,
            maximum_provider_input_tokens=524288,
            maximum_provider_output_tokens=96000,
            input_cost_usd_per_million_tokens=10.0,
            output_cost_usd_per_million_tokens=30.0,
            maximum_contract_cost_usd=solver_cost,
            provider_sdk_retries=0,
            runner_retries=0,
            require_finish_signal=True,
            require_nonempty_deliverable=True,
            maximum_context_tokens=64000,
        )
        request = MatchedBusinessAuthorizationRequestV1(
            campaign_id=campaign.campaign_id,
            selected_solver=selection,
            blind_package_fingerprints={
                item.blind_task_id: item.package_fingerprint or ""
                for item in campaign.assignments
            },
            candidate_tree_sha256={
                item.blind_task_id: _tree_sha(candidate_root / item.blind_task_id)
                for item in campaign.assignments
            },
            reality_evidence_sha256={
                item.blind_task_id: item.reality_evidence_sha256 or ""
                for item in campaign.assignments
            },
            solver_budget_per_task=budget,
            solver_total_cost_ceiling_usd=12.0 * solver_cost,
            campaign_manifest_sha256=_sha_file(self.manifest_path),
            staging_report_sha256=_sha_file(staging_path),
            solver_selection_sha256=_sha_file(selection_path),
            parity_report_path=str(parity_path),
            parity_report_sha256=_sha_file(parity_path),
            source_fingerprint=campaign.source_fingerprint,
        )
        return self._write_request("business_screening", request.model_dump(mode="json"))

    def read(self) -> MatchedScreeningCampaignV1:
        return MatchedScreeningCampaignV1.model_validate_json(
            self.manifest_path.read_text(encoding="utf-8")
        )

    def write(self, campaign: MatchedScreeningCampaignV1) -> None:
        _atomic_json(self.manifest_path, campaign.model_dump(mode="json"))

    def _validate_generation_request(
        self, request: MatchedGenerationAuthorizationRequestV1, request_sha: str
    ) -> None:
        campaign = self.read()
        immutable = (
            self.root
            / "governance"
            / "generation_authorization_requests"
            / f"{request_sha}.json"
        )
        checks = {
            "campaign": request.campaign_id == campaign.campaign_id,
            "manifest": request.campaign_manifest_sha256 == _sha_file(self.manifest_path),
            "source": request.source_ledger_sha256 == campaign.source_ledger_sha256,
            "admission": request.admission_report_sha256 == campaign.admission_report_sha256,
            "repair": request.repair_readiness_report_sha256
            == campaign.repair_readiness_report_sha256,
            "fingerprint": request.source_fingerprint == campaign.source_fingerprint,
            "immutable": immutable.is_file() and _sha_file(immutable) == request_sha,
        }
        parity_path = Path(request.parity_report_path)
        checks["parity"] = (
            parity_path.is_file()
            and _sha_file(parity_path) == request.parity_report_sha256
        )
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError("matched_generation_request_state_mismatch:" + ",".join(failed))

    def _validate_parity(self, parity_path: Path, fingerprint: str) -> None:
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        checks = {
            "passed": parity.get("passed") is True,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "fingerprint": parity.get("source_fingerprint") == fingerprint,
        }
        failed = sorted(key for key, passed in checks.items() if not passed)
        if failed:
            raise ValueError("matched_screening_parity_invalid:" + ",".join(failed))

    def _write_request(self, stem: str, payload: dict) -> tuple[object, Path, str]:
        if stem == "deepseek_preflight":
            model = DeepSeekSolverPreflightAuthorizationRequestV1.model_validate(payload)
        elif stem == "generation_recovery":
            model = MatchedGenerationRecoveryAuthorizationRequestV1.model_validate(payload)
        else:
            model = MatchedBusinessAuthorizationRequestV1.model_validate(payload)
        current = self.root / "governance" / f"{stem}_authorization_request.json"
        _atomic_json(current, model.model_dump(mode="json"))
        request_sha = _sha_file(current)
        immutable = (
            self.root
            / "governance"
            / f"{stem}_authorization_requests"
            / f"{request_sha}.json"
        )
        immutable.parent.mkdir(parents=True, exist_ok=True)
        if immutable.exists() and _sha_file(immutable) != request_sha:
            raise FileExistsError("immutable_matched_request_conflict")
        if not immutable.exists():
            shutil.copy2(current, immutable)
        return model, immutable, request_sha


def deepseek_solver_environment(base_environment: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Prepare child-only official DeepSeek agent settings without persisting a key."""

    environment = dict(base_environment or os.environ)
    key = environment.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("deepseek_solver_api_key_missing")
    environment["AGENT_API_KEY"] = key
    environment["AGENT_BASE_URL"] = "https://api.deepseek.com"
    environment["STIRRUP_OPENAI_API_KEY"] = key
    environment["STIRRUP_OPENAI_BASE_URL"] = "https://api.deepseek.com"
    return environment


def select_screening_solver(
    *,
    deepseek_preflight_path: str | Path,
    retained_gemini_preflight_path: str | Path,
) -> SolverSelectionV1:
    deepseek_path = Path(deepseek_preflight_path).resolve()
    gemini_path = Path(retained_gemini_preflight_path).resolve()
    deepseek = json.loads(deepseek_path.read_text(encoding="utf-8"))
    if deepseek.get("solver_model") == "deepseek-v4-pro" and deepseek.get("status") == "pass" and deepseek.get("eligible_for_business_eval") is True:
        return SolverSelectionV1(
            selected_provider="deepseek",
            selected_model="deepseek-v4-pro",
            selection_reason="deepseek_preflight_pass",
            preflight_report_path=str(deepseek_path),
            preflight_report_sha256=_sha_file(deepseek_path),
        )
    gemini = json.loads(gemini_path.read_text(encoding="utf-8"))
    if gemini.get("solver_model") != "gemini-3.1-pro-preview" or gemini.get("status") != "pass" or gemini.get("eligible_for_business_eval") is not True:
        raise ValueError("no_eligible_screening_solver")
    return SolverSelectionV1(
        selected_provider="tuzi",
        selected_model="gemini-3.1-pro-preview",
        selection_reason="retained_gemini_fallback",
        preflight_report_path=str(gemini_path),
        preflight_report_sha256=_sha_file(gemini_path),
        deepseek_failure_path=str(deepseek_path),
        deepseek_failure_sha256=_sha_file(deepseek_path),
    )
