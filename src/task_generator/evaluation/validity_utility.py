from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.evaluation.behavioral_validation import BehavioralExecutionReportV1
from task_generator.planning.task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignProposalV1,
    TaskDesignValidationReportV1,
)


EvidenceDecision = Literal[
    "not_evaluated",
    "provisional",
    "pass",
    "revise",
    "blocked",
]
EvidenceTier = Literal[
    "none",
    "structural_proxy",
    "deterministic",
    "executed_behavior",
    "llm_proxy",
    "expert_review",
]
ValidityDimension = Literal[
    "factual_validity",
    "semantic_validity",
    "contract_validity",
    "behavioral_validity",
    "professional_validity",
]
UtilityDimension = Literal[
    "evidence_integration",
    "planning",
    "judgment",
    "audit_trail",
    "deliverable_design",
]
RubricDimension = Literal[
    "factual_accuracy",
    "evidence_traceability",
    "method_process",
    "exception_handling",
    "reproducibility",
    "structural_usability",
    "professional_expression",
]
RealityReviewDimension = Literal[
    "role_realism",
    "information_sufficiency",
    "natural_difficulty",
    "professional_judgment",
    "deliverable_realism",
    "rubric_focus",
]


class RealityDimensionReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: RealityReviewDimension
    decision: Literal["pass", "revise", "blocked", "not_evaluated"]
    evidence_paths: List[str] = Field(default_factory=list)
    rationale: str = Field(min_length=12)


class RealityCaseReviewV1(BaseModel):
    """Independent human-facing review for one reality-cohort task."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    motif: str
    reviewer_id: str
    reviewer_independent_from_generator: bool
    dimensions: List[RealityDimensionReviewV1]
    overall_decision: Literal["pass", "revise", "blocked", "not_evaluated"]
    training_admission_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_review(self) -> "RealityCaseReviewV1":
        required = {
            "role_realism",
            "information_sufficiency",
            "natural_difficulty",
            "professional_judgment",
            "deliverable_realism",
            "rubric_focus",
        }
        observed = [item.dimension for item in self.dimensions]
        if len(observed) != len(required) or set(observed) != required:
            raise ValueError("reality_review_requires_exactly_six_dimensions")
        decisions = {item.decision for item in self.dimensions}
        expected = (
            "blocked"
            if "blocked" in decisions
            else "revise"
            if "revise" in decisions
            else "not_evaluated"
            if "not_evaluated" in decisions
            else "pass"
        )
        if self.overall_decision != expected:
            raise ValueError("reality_review_overall_decision_mismatch")
        if self.overall_decision == "pass" and not self.reviewer_independent_from_generator:
            raise ValueError("reality_review_pass_requires_independent_reviewer")
        return self


class RealityCohortReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort_version: Literal["v3.reality_cohort_review.1"] = (
        "v3.reality_cohort_review.1"
    )
    cohort_id: str
    cases: List[RealityCaseReviewV1]
    decision: Literal["pass", "revise", "blocked", "not_evaluated"]
    protocol_merge_eligible: bool = False
    training_admission_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_cohort(self) -> "RealityCohortReviewV1":
        if len(self.cases) != 6 or len({item.case_id for item in self.cases}) != 6:
            raise ValueError("reality_cohort_requires_six_unique_cases")
        decisions = {item.overall_decision for item in self.cases}
        expected = (
            "blocked"
            if "blocked" in decisions
            else "revise"
            if "revise" in decisions
            else "not_evaluated"
            if "not_evaluated" in decisions
            else "pass"
        )
        if self.decision != expected:
            raise ValueError("reality_cohort_decision_mismatch")
        expected_merge = expected == "pass"
        if self.protocol_merge_eligible != expected_merge:
            raise ValueError("reality_cohort_protocol_merge_eligibility_mismatch")
        return self


class RealityReviewDimensionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: RealityReviewDimension
    decision: Literal["pass", "revise", "blocked"]
    rationale: str = Field(min_length=12)
    evidence_locators: List[str] = Field(min_length=1)


class CandidateBlindRealityReviewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_version: Literal["v3.candidate_blind_reality_review.2"] = (
        "v3.candidate_blind_reality_review.2"
    )
    case_id: str
    dimensions: List[RealityReviewDimensionV2]

    @model_validator(mode="after")
    def validate_candidate_dimensions(self) -> "CandidateBlindRealityReviewV2":
        required = {
            "role_realism",
            "information_sufficiency",
            "natural_difficulty",
            "professional_judgment",
            "deliverable_realism",
        }
        observed = [item.dimension for item in self.dimensions]
        if len(observed) != 5 or set(observed) != required:
            raise ValueError("candidate_reality_review_requires_five_dimensions")
        return self


class RubricFocusRealityReviewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_version: Literal["v3.rubric_focus_reality_review.2"] = (
        "v3.rubric_focus_reality_review.2"
    )
    case_id: str
    dimension: RealityReviewDimensionV2

    @model_validator(mode="after")
    def validate_rubric_dimension(self) -> "RubricFocusRealityReviewV2":
        if self.dimension.dimension != "rubric_focus":
            raise ValueError("rubric_reality_review_requires_rubric_focus")
        return self


class RealityReviewCallEvidenceV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["candidate_blind", "rubric_focus"]
    reviewer_kind: Literal["llm_proxy"] = "llm_proxy"
    evidence_tier: Literal["llm_proxy"] = "llm_proxy"
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    route_blind: Literal[True] = True
    generator_independent_model: Literal[True] = True
    attempt_count: int = Field(default=1, ge=1, le=2)
    first_attempt_failure_sha256: Optional[str] = None
    input_sha256: str = Field(min_length=64, max_length=64)
    raw_output_sha256: str = Field(min_length=64, max_length=64)
    parsed_output_sha256: str = Field(min_length=64, max_length=64)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)


class RealityCaseReviewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_version: Literal["v3.reality_case_review.2"] = (
        "v3.reality_case_review.2"
    )
    case_id: str
    motif: str
    candidate_review: CandidateBlindRealityReviewV2
    rubric_review: RubricFocusRealityReviewV2
    call_evidence: List[RealityReviewCallEvidenceV2]
    overall_decision: Literal["pass", "revise", "blocked"]
    professional_validity_status: Literal["provisional"] = "provisional"
    expert_evidence_present: Literal[False] = False
    training_admission_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_case_review(self) -> "RealityCaseReviewV2":
        if (
            self.candidate_review.case_id != self.case_id
            or self.rubric_review.case_id != self.case_id
        ):
            raise ValueError("reality_case_review_case_id_mismatch")
        if [item.stage for item in self.call_evidence] != [
            "candidate_blind",
            "rubric_focus",
        ]:
            raise ValueError("reality_case_review_requires_two_ordered_calls")
        decisions = [
            item.decision for item in self.candidate_review.dimensions
        ] + [self.rubric_review.dimension.decision]
        expected = (
            "blocked" if "blocked" in decisions
            else "revise" if "revise" in decisions
            else "pass"
        )
        if self.overall_decision != expected:
            raise ValueError("reality_case_review_decision_mismatch")
        return self


class RealityCohortReviewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort_version: Literal["v3.reality_cohort_review.2"] = (
        "v3.reality_cohort_review.2"
    )
    cohort_id: str
    cases: List[RealityCaseReviewV2]
    decision: Literal[
        "screening_ready",
        "revise_before_screening",
        "redesign_required",
        "incomplete",
    ]
    screening_eligible: bool
    professional_validity_status: Literal["provisional"] = "provisional"
    expert_evidence_present: Literal[False] = False
    training_admission_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    blocking_reasons: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cohort_review(self) -> "RealityCohortReviewV2":
        complete = len(self.cases) == 6 and len(
            {item.case_id for item in self.cases}
        ) == 6
        if not complete:
            expected = "incomplete"
        else:
            decisions = {item.overall_decision for item in self.cases}
            expected = (
                "redesign_required" if "blocked" in decisions
                else "revise_before_screening" if "revise" in decisions
                else "screening_ready"
            )
        if self.decision != expected:
            raise ValueError("reality_cohort_v2_decision_mismatch")
        if self.screening_eligible != (expected == "screening_ready"):
            raise ValueError("reality_cohort_v2_screening_eligibility_mismatch")
        return self


class ValidityDimensionEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: ValidityDimension
    status: EvidenceDecision
    evidence_tier: EvidenceTier
    evidence_paths: List[str] = Field(default_factory=list)
    finding_owner: str
    decision_authority: str
    independent_from_generator: bool = False
    rationale: str


class ValidityVectorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vector_version: Literal["v3.validity_vector.1"] = "v3.validity_vector.1"
    case_id: str
    dimensions: List[ValidityDimensionEvidenceV1]
    overall_status: EvidenceDecision
    training_admission_eligible: bool = False
    unresolved_dimensions: List[ValidityDimension] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "ValidityVectorV1":
        dimensions = [item.dimension for item in self.dimensions]
        required = {
            "factual_validity",
            "semantic_validity",
            "contract_validity",
            "behavioral_validity",
            "professional_validity",
        }
        if set(dimensions) != required or len(dimensions) != len(required):
            raise ValueError("validity_vector_requires_exactly_five_dimensions")
        return self


class AccidentalDifficultyFindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_code: Literal[
        "missing_candidate_field",
        "wrong_submission_path",
        "tool_incompatible_format",
        "hidden_primary_truth",
        "grader_instability",
    ]
    status: Literal["clear", "blocked", "not_evaluated"]
    evidence_paths: List[str] = Field(default_factory=list)
    rationale: str


class ProductiveComplexityDimensionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: UtilityDimension
    status: EvidenceDecision
    structural_signal_count: int = Field(ge=0)
    evidence_element_ids: List[str] = Field(default_factory=list)
    evidence_paths: List[str] = Field(default_factory=list)
    evidence_tier: EvidenceTier = "structural_proxy"
    rationale: str


class SkillCausalContributionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str
    contribution_status: Literal["causal", "decorative", "missing"]
    bound_element_ids: List[str] = Field(default_factory=list)
    ablation_changed_element_ids: List[str] = Field(default_factory=list)
    required_capability_ids: List[str] = Field(default_factory=list)
    rationale: str


class UtilityProfileV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_version: Literal["v3.utility_profile.1"] = "v3.utility_profile.1"
    case_id: str
    proposal_id: str
    profile_status: EvidenceDecision
    productive_complexity: List[ProductiveComplexityDimensionV1]
    skill_contributions: List[SkillCausalContributionV1]
    accidental_difficulty_findings: List[AccidentalDifficultyFindingV1]
    productive_complexity_coverage: float = Field(ge=0.0, le=1.0)
    skill_causal_coverage: float = Field(ge=0.0, le=1.0)
    training_admission_eligible: Literal[False] = False
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "UtilityProfileV1":
        dimensions = [item.dimension for item in self.productive_complexity]
        required = {
            "evidence_integration",
            "planning",
            "judgment",
            "audit_trail",
            "deliverable_design",
        }
        if set(dimensions) != required or len(dimensions) != len(required):
            raise ValueError("utility_profile_requires_exactly_five_dimensions")
        return self


class PartialScoreBandV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score_ratio: Literal[0.0, 0.5, 1.0]
    meaning: str = Field(min_length=12)


class RubricCriterionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str
    dimension: RubricDimension
    axis: Literal["validity", "utility"]
    weight: float = Field(gt=0.0, le=1.0)
    observable_behavior: str = Field(min_length=12)
    independent_failure_signal: str = Field(min_length=8)
    evidence_requirements: List[str] = Field(min_length=1)
    evidence_or_judgment_ids: List[str] = Field(default_factory=list)
    skill_ids: List[str] = Field(default_factory=list)
    capability_ids: List[str] = Field(default_factory=list)
    partial_score_bands: List[PartialScoreBandV1]
    professional_evidence_ceiling: Literal[
        "deterministic",
        "structural_proxy",
        "llm_proxy_provisional",
        "expert_review",
    ]

    @model_validator(mode="after")
    def validate_score_bands(self) -> "RubricCriterionV2":
        ratios = [item.score_ratio for item in self.partial_score_bands]
        if ratios != [0.0, 0.5, 1.0]:
            raise ValueError("rubric_score_bands_must_be_0_05_1")
        return self


class RubricPlanV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_version: Literal["v3.rubric_plan.2"] = "v3.rubric_plan.2"
    case_id: str
    proposal_id: str
    criteria: List[RubricCriterionV2]
    decision: Literal["pass", "blocked"]
    total_weight: float
    factual_weight_ratio: float
    effective_dimension_count: int
    duplicate_fact_anchor_assignments: List[str] = Field(default_factory=list)
    duplicate_failure_signals: List[str] = Field(default_factory=list)
    final_weights_frozen_before_results: Literal[True] = True
    notes: List[str] = Field(default_factory=list)


class RubricCriterionPairAuditV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_a: str
    criterion_b: str
    shared_skill_ids: List[str] = Field(default_factory=list)
    shared_capability_ids: List[str] = Field(default_factory=list)
    shared_evidence_or_judgment_ids: List[str] = Field(default_factory=list)
    observable_behavior_exact_match: bool
    independent_failure_signal_exact_match: bool
    deterministic_class: Literal[
        "distinct", "shared_trace_evidence", "duplicate_scoring"
    ]

    @model_validator(mode="after")
    def validate_pair(self) -> "RubricCriterionPairAuditV1":
        if self.criterion_a >= self.criterion_b:
            raise ValueError("rubric_pair_ids_must_be_sorted")
        expected = (
            "duplicate_scoring"
            if self.observable_behavior_exact_match
            or self.independent_failure_signal_exact_match
            else "shared_trace_evidence"
            if self.shared_evidence_or_judgment_ids
            else "distinct"
        )
        if self.deterministic_class != expected:
            raise ValueError("rubric_pair_deterministic_class_mismatch")
        return self


class RubricScoringAuthorityAuditV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_version: Literal["v3.rubric_scoring_authority_audit.1"] = (
        "v3.rubric_scoring_authority_audit.1"
    )
    case_id: str
    final_scoring_criterion_ids: List[str]
    final_scoring_criteria_count: int
    annotation_binding_ids: List[str]
    annotation_bindings_count: int
    annotation_bindings_non_scoring: bool
    pair_audits: List[RubricCriterionPairAuditV1]
    structure_signature: str = Field(min_length=64, max_length=64)
    scoring_semantic_signature: str = Field(min_length=64, max_length=64)
    duplicate_criterion_ids: List[str] = Field(default_factory=list)
    duplicate_failure_signals: List[str] = Field(default_factory=list)
    duplicate_observable_behaviors: List[str] = Field(default_factory=list)
    weight_sum_valid: bool
    criterion_count_valid: bool
    rubric_metadata_valid: bool
    binding_authority_valid: bool
    decision: Literal["pass", "blocked"]
    blocking_reasons: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_authority_audit(self) -> "RubricScoringAuthorityAuditV1":
        ids = self.final_scoring_criterion_ids
        if self.final_scoring_criteria_count != len(ids):
            raise ValueError("rubric_authority_final_count_mismatch")
        if self.annotation_bindings_count != len(self.annotation_binding_ids):
            raise ValueError("rubric_authority_binding_count_mismatch")
        observed_pairs = {(item.criterion_a, item.criterion_b) for item in self.pair_audits}
        unique_ids = sorted(set(ids))
        required_pairs = {
            (a, b)
            for index, a in enumerate(unique_ids)
            for b in unique_ids[index + 1 :]
        }
        structurally_valid = len(ids) == 7 and len(unique_ids) == 7
        if len(self.pair_audits) != len(observed_pairs):
            raise ValueError("rubric_authority_pair_coverage_mismatch")
        if structurally_valid and observed_pairs != required_pairs:
            raise ValueError("rubric_authority_pair_coverage_mismatch")
        if not structurally_valid and not observed_pairs.issubset(required_pairs):
            raise ValueError("rubric_authority_pair_coverage_mismatch")
        blocked = bool(
            self.duplicate_criterion_ids
            or self.duplicate_failure_signals
            or self.duplicate_observable_behaviors
            or not self.weight_sum_valid
            or not self.criterion_count_valid
            or not self.rubric_metadata_valid
            or not self.binding_authority_valid
            or not self.annotation_bindings_non_scoring
        )
        if self.decision != ("blocked" if blocked else "pass"):
            raise ValueError("rubric_authority_decision_mismatch")
        return self


class RubricPairAssessmentV3(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_a: str
    criterion_b: str
    assessment: Literal[
        "distinct",
        "shared_evidence_distinct_behavior",
        "potential_duplicate",
        "duplicate",
    ]
    rationale: str = Field(min_length=12)
    evidence_locators: List[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "RubricPairAssessmentV3":
        if self.criterion_a >= self.criterion_b:
            raise ValueError("rubric_review_pair_ids_must_be_sorted")
        return self


class RubricFocusRealityReviewV3(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_version: Literal["v3.rubric_focus_reality_review.3"] = (
        "v3.rubric_focus_reality_review.3"
    )
    case_id: str
    final_scoring_criterion_ids: List[str]
    final_scoring_criteria_count: int
    annotation_bindings_recognized_non_scoring: Literal[True]
    pair_assessments: List[RubricPairAssessmentV3]
    decision: Literal["pass", "revise", "blocked"]
    rationale: str = Field(min_length=12)

    @model_validator(mode="after")
    def validate_review(self) -> "RubricFocusRealityReviewV3":
        ids = self.final_scoring_criterion_ids
        if ids != sorted(ids) or len(ids) != 7 or len(set(ids)) != 7 or self.final_scoring_criteria_count != 7:
            raise ValueError("rubric_v3_requires_seven_final_criteria")
        expected = {(a, b) for index, a in enumerate(ids) for b in ids[index + 1 :]}
        observed = {(item.criterion_a, item.criterion_b) for item in self.pair_assessments}
        if len(self.pair_assessments) != 21 or observed != expected:
            raise ValueError("rubric_v3_requires_all_21_pairs")
        risky = [item for item in self.pair_assessments if item.assessment in {"potential_duplicate", "duplicate"}]
        expected_decision = "blocked" if any(item.assessment == "duplicate" for item in risky) else "revise" if risky else "pass"
        if self.decision != expected_decision:
            raise ValueError("rubric_v3_decision_mismatch")
        return self


class RubricPairAssessmentV4(BaseModel):
    """Compact exhaustive classification; detailed prose lives only on risky pairs."""

    model_config = ConfigDict(extra="forbid")
    criterion_a: str
    criterion_b: str
    assessment: Literal[
        "distinct",
        "shared_evidence_distinct_behavior",
        "potential_duplicate",
        "duplicate",
    ]

    @model_validator(mode="after")
    def validate_pair(self) -> "RubricPairAssessmentV4":
        if self.criterion_a >= self.criterion_b:
            raise ValueError("rubric_review_pair_ids_must_be_sorted")
        return self


class RubricPairRiskFindingV4(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_a: str
    criterion_b: str
    assessment: Literal["potential_duplicate", "duplicate"]
    rationale: str = Field(min_length=12, max_length=600)
    evidence_locators: List[str] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def validate_pair(self) -> "RubricPairRiskFindingV4":
        if self.criterion_a >= self.criterion_b:
            raise ValueError("rubric_review_risk_pair_ids_must_be_sorted")
        return self


class RubricFocusRealityReviewV4(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_version: Literal["v3.rubric_focus_reality_review.4"] = (
        "v3.rubric_focus_reality_review.4"
    )
    case_id: str
    final_scoring_criterion_ids: List[str]
    final_scoring_criteria_count: int
    annotation_bindings_recognized_non_scoring: Literal[True]
    pair_assessments: List[RubricPairAssessmentV4]
    risk_findings: List[RubricPairRiskFindingV4] = Field(default_factory=list)
    decision: Literal["pass", "revise", "blocked"]
    summary: str = Field(min_length=12, max_length=600)

    @model_validator(mode="after")
    def validate_review(self) -> "RubricFocusRealityReviewV4":
        ids = self.final_scoring_criterion_ids
        if (
            ids != sorted(ids)
            or len(ids) != 7
            or len(set(ids)) != 7
            or self.final_scoring_criteria_count != 7
        ):
            raise ValueError("rubric_v4_requires_seven_final_criteria")
        expected = {
            (a, b) for index, a in enumerate(ids) for b in ids[index + 1 :]
        }
        observed = {
            (item.criterion_a, item.criterion_b) for item in self.pair_assessments
        }
        if len(self.pair_assessments) != 21 or observed != expected:
            raise ValueError("rubric_v4_requires_all_21_pairs")
        risky = {
            (item.criterion_a, item.criterion_b): item.assessment
            for item in self.pair_assessments
            if item.assessment in {"potential_duplicate", "duplicate"}
        }
        findings = {
            (item.criterion_a, item.criterion_b): item.assessment
            for item in self.risk_findings
        }
        if len(findings) != len(self.risk_findings) or findings != risky:
            raise ValueError("rubric_v4_risk_findings_must_match_risky_pairs")
        expected_decision = (
            "blocked"
            if "duplicate" in risky.values()
            else "revise"
            if risky
            else "pass"
        )
        if self.decision != expected_decision:
            raise ValueError("rubric_v4_decision_mismatch")
        return self


class EvaluationCalibrationContractV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["v3.evaluation_calibration_contract.1"] = (
        "v3.evaluation_calibration_contract.1"
    )
    solver_panel_strata: List[Literal["weak", "medium", "strong"]] = Field(
        default_factory=lambda: ["weak", "medium", "strong"]
    )
    solver_tool_preflight_required: Literal[True] = True
    score_saturation_ratio_threshold: float = 0.80
    score_saturation_score_threshold: float = 0.90
    grader_disagreement_absolute_threshold: float = 0.15
    maximum_grader_disagreement_rate: float = 0.20
    informative_case_min_score_spread: float = 0.20
    minimum_effective_rubric_dimensions: int = 5
    freeze_before_formal_results: Literal[True] = True
    model_assignments_frozen: bool = False
    grader_assignments_frozen: bool = False
    calibration_status: Literal["contract_frozen_models_pending"] = (
        "contract_frozen_models_pending"
    )
    notes: List[str] = Field(default_factory=list)


class R5GovernanceBundleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_version: Literal["v3.r5_governance_bundle.1"] = (
        "v3.r5_governance_bundle.1"
    )
    validity_vector: ValidityVectorV1
    utility_profile: UtilityProfileV1
    rubric_plan: RubricPlanV2
    calibration_contract: EvaluationCalibrationContractV1
    offline_decision: Literal["pass", "blocked"]
    promotion_authorized: Literal[False] = False
    training_admission_authorized: Literal[False] = False


class ValidityUtilityCompiler:
    RUBRIC_WEIGHTS: Dict[RubricDimension, float] = {
        "factual_accuracy": 0.20,
        "evidence_traceability": 0.15,
        "method_process": 0.15,
        "exception_handling": 0.15,
        "reproducibility": 0.15,
        "structural_usability": 0.10,
        "professional_expression": 0.10,
    }

    def compile(
        self,
        *,
        brief: CapabilityBriefV1,
        proposal: TaskDesignProposalV1,
        proposal_validation: TaskDesignValidationReportV1,
        deterministic_fact_anchors: Any,
        deliverable_contract_valid: bool,
        evidence_content_quality: Any = None,
        evidence_paths: Optional[Dict[str, str]] = None,
        behavioral_report: Optional[BehavioralExecutionReportV1] = None,
        professional_status: EvidenceDecision = "not_evaluated",
        professional_evidence_tier: EvidenceTier = "none",
        professional_review_path: Optional[str] = None,
    ) -> R5GovernanceBundleV1:
        paths = evidence_paths or {}
        anchors = self._items(deterministic_fact_anchors, "anchors")
        all_candidate_visible = bool(
            anchors
            and self._value(
                deterministic_fact_anchors,
                "all_inputs_candidate_visible",
                False,
            )
        )
        content_quality_decision = self._value(
            evidence_content_quality,
            "decision",
            "not_evaluated",
        )
        validity = self._validity_vector(
            case_id=brief.case_id,
            proposal_validation=proposal_validation,
            anchors=anchors,
            all_candidate_visible=all_candidate_visible,
            content_quality_decision=content_quality_decision,
            deliverable_contract_valid=deliverable_contract_valid,
            paths=paths,
            behavioral_report=behavioral_report,
            professional_status=professional_status,
            professional_evidence_tier=professional_evidence_tier,
            professional_review_path=professional_review_path,
        )
        utility = self._utility_profile(
            brief=brief,
            proposal=proposal,
            anchors=anchors,
            all_candidate_visible=all_candidate_visible,
            content_quality_decision=content_quality_decision,
            deliverable_contract_valid=deliverable_contract_valid,
            paths=paths,
        )
        rubric = self._rubric_plan(
            brief=brief,
            proposal=proposal,
            anchors=anchors,
        )
        calibration = EvaluationCalibrationContractV1(
            notes=[
                "Thresholds are frozen before any formal route-comparison result.",
                "Named solver and grader assignments remain pending explicit campaign authorization.",
            ]
        )
        offline_decision = (
            "pass"
            if rubric.decision == "pass"
            and not any(
                item.status == "blocked"
                for item in utility.accidental_difficulty_findings
            )
            and validity.overall_status != "blocked"
            else "blocked"
        )
        return R5GovernanceBundleV1(
            validity_vector=validity,
            utility_profile=utility,
            rubric_plan=rubric,
            calibration_contract=calibration,
            offline_decision=offline_decision,
        )

    def _validity_vector(
        self,
        *,
        case_id: str,
        proposal_validation: TaskDesignValidationReportV1,
        anchors: List[Any],
        all_candidate_visible: bool,
        content_quality_decision: str,
        deliverable_contract_valid: bool,
        paths: Dict[str, str],
        behavioral_report: Optional[BehavioralExecutionReportV1],
        professional_status: EvidenceDecision,
        professional_evidence_tier: EvidenceTier,
        professional_review_path: Optional[str],
    ) -> ValidityVectorV1:
        if (
            not anchors
            or not all_candidate_visible
            or content_quality_decision == "blocked"
        ):
            factual_status: EvidenceDecision = "blocked"
        else:
            factual_status = "provisional"
        semantic_status: EvidenceDecision = (
            "provisional"
            if proposal_validation.decision == "pass"
            else "blocked"
        )
        contract_status: EvidenceDecision = (
            "pass" if deliverable_contract_valid else "blocked"
        )
        if behavioral_report is None:
            behavioral_status: EvidenceDecision = "not_evaluated"
        elif (
            behavioral_report.process_status == "succeeded"
            and behavioral_report.delivery_status == "valid"
            and behavioral_report.file_validity_status == "pass"
        ):
            behavioral_status = "pass"
        else:
            behavioral_status = "blocked"
        dimensions = [
            ValidityDimensionEvidenceV1(
                dimension="factual_validity",
                status=factual_status,
                evidence_tier="deterministic",
                evidence_paths=self._path(paths, "fact_anchors"),
                finding_owner="deterministic_fact_anchor_compiler",
                decision_authority="program_recomputation",
                rationale=(
                    "Candidate-visible facts are deterministically recomputable, but "
                    "business grounding remains unresolved and cannot be upgraded by "
                    "generator-owned evidence alone."
                    if factual_status == "provisional"
                    else "Fact anchors are missing, non-candidate-visible, or the materialized content gate is blocked."
                ),
            ),
            ValidityDimensionEvidenceV1(
                dimension="semantic_validity",
                status=semantic_status,
                evidence_tier="structural_proxy",
                evidence_paths=self._path(paths, "proposal_validation"),
                finding_owner="task_design_frontend",
                decision_authority="proposal_contract_validator",
                rationale=(
                    "Proposal bindings pass structural semantic checks, but no independent "
                    "candidate-blind semantic review has been supplied."
                ),
            ),
            ValidityDimensionEvidenceV1(
                dimension="contract_validity",
                status=contract_status,
                evidence_tier="deterministic",
                evidence_paths=self._path(paths, "deliverable_contract_validation"),
                finding_owner="deliverable_contract_validator",
                decision_authority="program_contract_gate",
                rationale=(
                    "Prompt, export paths, and delivery inspection share one valid contract."
                    if contract_status == "pass"
                    else "The governed deliverable contract is invalid."
                ),
            ),
            ValidityDimensionEvidenceV1(
                dimension="behavioral_validity",
                status=behavioral_status,
                evidence_tier=(
                    "executed_behavior" if behavioral_report else "none"
                ),
                evidence_paths=(
                    self._path(paths, "behavioral_execution")
                    if behavioral_report
                    else []
                ),
                finding_owner="independent_behavioral_runner",
                decision_authority="executed_delivery_gate",
                independent_from_generator=behavioral_report is not None,
                rationale=(
                    "No solver execution evidence has been supplied."
                    if behavioral_report is None
                    else "Behavioral status is derived from process, exact delivery, and file validity."
                ),
            ),
            ValidityDimensionEvidenceV1(
                dimension="professional_validity",
                status=professional_status,
                evidence_tier=professional_evidence_tier,
                evidence_paths=[professional_review_path] if professional_review_path else [],
                finding_owner=(
                    "independent_expert"
                    if professional_evidence_tier == "expert_review"
                    else "professional_review_pending"
                ),
                decision_authority=(
                    "expert_review"
                    if professional_evidence_tier == "expert_review"
                    else "no_final_authority"
                ),
                independent_from_generator=professional_evidence_tier == "expert_review",
                rationale=(
                    "Professional validity is not upgraded from structural or LLM-only evidence."
                ),
            ),
        ]
        statuses = [item.status for item in dimensions]
        if "blocked" in statuses:
            overall: EvidenceDecision = "blocked"
        elif "revise" in statuses:
            overall = "revise"
        elif all(item == "pass" for item in statuses):
            overall = "pass"
        elif "provisional" in statuses:
            overall = "provisional"
        else:
            overall = "not_evaluated"
        unresolved = [
            item.dimension
            for item in dimensions
            if item.status != "pass"
        ]
        admission = (
            overall == "pass"
            and all(
                item.independent_from_generator
                for item in dimensions
                if item.dimension in {"behavioral_validity", "professional_validity"}
            )
        )
        return ValidityVectorV1(
            case_id=case_id,
            dimensions=dimensions,
            overall_status=overall,
            training_admission_eligible=admission,
            unresolved_dimensions=unresolved,
            notes=[
                "Validity dimensions are not averaged into a business score.",
                "Deterministic recomputability is necessary but does not establish business-grounded factual validity.",
                "Provisional or not-evaluated evidence cannot authorize training admission.",
            ],
        )

    def _utility_profile(
        self,
        *,
        brief: CapabilityBriefV1,
        proposal: TaskDesignProposalV1,
        anchors: List[Any],
        all_candidate_visible: bool,
        content_quality_decision: str,
        deliverable_contract_valid: bool,
        paths: Dict[str, str],
    ) -> UtilityProfileV1:
        inferred_relations = [
            item for item in proposal.evidence_relations if item.solver_must_infer
        ]
        judgment_ids = [item.judgment_id for item in proposal.required_judgments]
        audit_ids = [
            item.judgment_id
            for item in proposal.required_judgments
            if any(
                token in (item.description + " " + item.observable_output).lower()
                for token in ("trace", "audit", "reconcile", "evidence", "review")
            )
        ]
        if not audit_ids and anchors:
            audit_ids = [
                str(self._value(item, "anchor_id", ""))
                for item in anchors
                if self._value(item, "anchor_id", "")
            ]
        dimensions = [
            self._complexity_dimension(
                "evidence_integration",
                [item.relation_id for item in inferred_relations],
                paths,
                "The task requires the solver to infer relationships across evidence nodes.",
            ),
            self._complexity_dimension(
                "planning",
                list(proposal.productive_complexity),
                paths,
                "The task preserves a planning choice instead of prescribing all steps.",
            ),
            self._complexity_dimension(
                "judgment",
                judgment_ids,
                paths,
                "Required judgments map candidate evidence to observable outputs.",
            ),
            self._complexity_dimension(
                "audit_trail",
                audit_ids,
                paths,
                "The deliverable can expose evidence lineage or recomputable review support.",
            ),
            self._complexity_dimension(
                "deliverable_design",
                list(proposal.deliverable_intent.required_sections_or_views),
                paths,
                "The artifact has an audience, business use, and multiple governed views.",
            ),
        ]
        contributions = self._skill_contributions(brief, proposal)
        accidental = [
            AccidentalDifficultyFindingV1(
                finding_code="missing_candidate_field",
                status=(
                    "clear"
                    if content_quality_decision == "pass"
                    else (
                        "blocked"
                        if content_quality_decision == "blocked"
                        else "not_evaluated"
                    )
                ),
                evidence_paths=self._path(paths, "evidence_content_quality"),
                rationale=(
                    "Materialized candidate files, not proposal prose, determine whether required business fields are present."
                ),
            ),
            AccidentalDifficultyFindingV1(
                finding_code="wrong_submission_path",
                status="clear" if deliverable_contract_valid else "blocked",
                evidence_paths=self._path(paths, "deliverable_contract_validation"),
                rationale="Submission paths are governed by the compiled DeliverableContract.",
            ),
            AccidentalDifficultyFindingV1(
                finding_code="tool_incompatible_format",
                status=(
                    "clear"
                    if set(proposal.deliverable_intent.allowed_formats)
                    & set(brief.allowed_output_file_types)
                    else "blocked"
                ),
                rationale="The proposed artifact format must stay within the frozen tool-compatible brief.",
            ),
            AccidentalDifficultyFindingV1(
                finding_code="hidden_primary_truth",
                status="clear" if anchors and all_candidate_visible else "blocked",
                evidence_paths=self._path(paths, "fact_anchors"),
                rationale="Primary deterministic truth must be recomputable from candidate-visible inputs.",
            ),
            AccidentalDifficultyFindingV1(
                finding_code="grader_instability",
                status="not_evaluated",
                rationale="Grader stability requires an authorized repeated-grading calibration slice.",
            ),
        ]
        complexity_coverage = sum(
            item.status in {"pass", "provisional"} for item in dimensions
        ) / len(dimensions)
        causal_count = sum(
            item.contribution_status == "causal" for item in contributions
        )
        causal_coverage = (
            causal_count / len(contributions) if contributions else 0.0
        )
        profile_status: EvidenceDecision = (
            "blocked"
            if any(item.status == "blocked" for item in accidental)
            or any(item.contribution_status != "causal" for item in contributions)
            else "provisional"
        )
        return UtilityProfileV1(
            case_id=brief.case_id,
            proposal_id=proposal.proposal_id,
            profile_status=profile_status,
            productive_complexity=dimensions,
            skill_contributions=contributions,
            accidental_difficulty_findings=accidental,
            productive_complexity_coverage=round(complexity_coverage, 4),
            skill_causal_coverage=round(causal_coverage, 4),
            notes=[
                "Structural evidence can establish coverage but not final professional quality.",
                "All productive-complexity dimensions remain provisional until behavioral or expert evidence exists.",
            ],
        )

    def _skill_contributions(
        self,
        brief: CapabilityBriefV1,
        proposal: TaskDesignProposalV1,
    ) -> List[SkillCausalContributionV1]:
        binding_by_skill = {item.skill_id: item for item in proposal.skill_bindings}
        capability_by_skill = {
            item.skill_id: list(item.required_capability_ids)
            for item in brief.selected_skills
        }
        results: List[SkillCausalContributionV1] = []
        for skill in brief.selected_skills:
            binding = binding_by_skill.get(skill.skill_id)
            if binding is None:
                results.append(
                    SkillCausalContributionV1(
                        skill_id=skill.skill_id,
                        contribution_status="missing",
                        required_capability_ids=capability_by_skill[skill.skill_id],
                        rationale="No proposal binding exists for this selected skill.",
                    )
                )
                continue
            other_elements = {
                element
                for other in proposal.skill_bindings
                if other.skill_id != skill.skill_id
                for element in other.bound_element_ids
            }
            unique_elements = sorted(set(binding.bound_element_ids) - other_elements)
            other_capabilities = {
                capability
                for other_skill, capabilities in capability_by_skill.items()
                if other_skill != skill.skill_id
                for capability in capabilities
            }
            unique_capabilities = sorted(
                set(capability_by_skill[skill.skill_id]) - other_capabilities
            )
            changed = sorted(set(unique_elements + unique_capabilities))
            causal = bool(changed and binding.observable_behavior.strip())
            results.append(
                SkillCausalContributionV1(
                    skill_id=skill.skill_id,
                    contribution_status="causal" if causal else "decorative",
                    bound_element_ids=list(binding.bound_element_ids),
                    ablation_changed_element_ids=changed,
                    required_capability_ids=capability_by_skill[skill.skill_id],
                    rationale=(
                        "Removing the skill removes a unique bound task element or required capability."
                        if causal
                        else "Removing the skill leaves all bound elements and capabilities covered elsewhere."
                    ),
                )
            )
        return results

    def _rubric_plan(
        self,
        *,
        brief: CapabilityBriefV1,
        proposal: TaskDesignProposalV1,
        anchors: List[Any],
    ) -> RubricPlanV2:
        anchor_ids = [
            str(self._value(item, "anchor_id", ""))
            for item in anchors
            if self._value(item, "anchor_id", "")
        ]
        relation_ids = [item.relation_id for item in proposal.evidence_relations]
        judgment_ids = [item.judgment_id for item in proposal.required_judgments]
        skill_ids = [item.skill_id for item in brief.selected_skills]
        capability_ids = [item.capability_id for item in brief.required_capabilities]
        section_ids = [
            f"deliverable:{item}"
            for item in proposal.deliverable_intent.required_sections_or_views
        ]
        specifications = [
            (
                "factual_accuracy",
                "validity",
                "Deterministic conclusions match recomputed candidate-visible fact anchors.",
                "fact_anchor_mismatch",
                ["Recompute each assigned anchor from candidate-visible inputs."],
                anchor_ids,
                "deterministic",
            ),
            (
                "evidence_traceability",
                "utility",
                "Material conclusions identify the evidence relationship that supports them.",
                "conclusion_without_traceable_evidence",
                ["Inspect source references, relation links, and conclusion lineage."],
                relation_ids,
                "structural_proxy",
            ),
            (
                "method_process",
                "utility",
                "The work shows a coherent method that connects inputs, judgments, and outputs.",
                "method_missing_or_incoherent",
                ["Inspect intermediate reasoning artifacts and judgment sequence."],
                judgment_ids,
                "structural_proxy",
            ),
            (
                "exception_handling",
                "utility",
                "Conflicts, gaps, or exceptions are surfaced and handled without inventing facts.",
                "material_exception_ignored",
                ["Inspect exception flags, unresolved items, and stated assumptions."],
                judgment_ids,
                "llm_proxy_provisional",
            ),
            (
                "reproducibility",
                "utility",
                "A reviewer can reproduce material results from the submitted audit trail.",
                "result_not_reproducible",
                ["Reperform material checks using cited inputs and documented transformations."],
                anchor_ids + relation_ids,
                "structural_proxy",
            ),
            (
                "structural_usability",
                "utility",
                "The artifact is organized for its stated audience and business use.",
                "required_view_missing_or_unusable",
                ["Inspect required sections, navigation, labels, and decision-ready layout."],
                section_ids,
                "structural_proxy",
            ),
            (
                "professional_expression",
                "utility",
                "The artifact communicates conclusions, limitations, and next actions professionally.",
                "professional_communication_insufficient",
                ["Review clarity, audience fit, limitations, and actionable wording."],
                section_ids,
                "llm_proxy_provisional",
            ),
        ]
        criteria: List[RubricCriterionV2] = []
        for dimension, axis, behavior, signal, requirements, element_ids, ceiling in specifications:
            criteria.append(
                RubricCriterionV2(
                    criterion_id=f"criterion_{dimension}",
                    dimension=dimension,
                    axis=axis,
                    weight=self.RUBRIC_WEIGHTS[dimension],
                    observable_behavior=behavior,
                    independent_failure_signal=signal,
                    evidence_requirements=requirements,
                    evidence_or_judgment_ids=element_ids,
                    skill_ids=skill_ids if dimension != "factual_accuracy" else [],
                    capability_ids=capability_ids if dimension != "factual_accuracy" else [],
                    partial_score_bands=[
                        PartialScoreBandV1(
                            score_ratio=0.0,
                            meaning="The independent failure signal is present or required evidence is absent.",
                        ),
                        PartialScoreBandV1(
                            score_ratio=0.5,
                            meaning="The behavior is materially present but incomplete, inconsistent, or weakly evidenced.",
                        ),
                        PartialScoreBandV1(
                            score_ratio=1.0,
                            meaning="The behavior is complete, internally consistent, and supported by the required evidence.",
                        ),
                    ],
                    professional_evidence_ceiling=ceiling,
                )
            )
        signals = [item.independent_failure_signal for item in criteria]
        duplicate_signals = sorted(
            {item for item in signals if signals.count(item) > 1}
        )
        fact_assignments = [
            anchor
            for item in criteria
            if item.dimension == "factual_accuracy"
            for anchor in item.evidence_or_judgment_ids
        ]
        duplicate_fact_anchors = sorted(
            {item for item in fact_assignments if fact_assignments.count(item) > 1}
        )
        total_weight = round(sum(item.weight for item in criteria), 6)
        factual_weight = round(
            sum(item.weight for item in criteria if item.dimension == "factual_accuracy"),
            6,
        )
        effective_dimensions = len({item.dimension for item in criteria})
        decision = (
            "pass"
            if total_weight == 1.0
            and factual_weight <= 0.25
            and effective_dimensions == 7
            and not duplicate_signals
            and not duplicate_fact_anchors
            else "blocked"
        )
        return RubricPlanV2(
            case_id=brief.case_id,
            proposal_id=proposal.proposal_id,
            criteria=criteria,
            decision=decision,
            total_weight=total_weight,
            factual_weight_ratio=factual_weight,
            effective_dimension_count=effective_dimensions,
            duplicate_fact_anchor_assignments=duplicate_fact_anchors,
            duplicate_failure_signals=duplicate_signals,
            notes=[
                "Factual correctness is a validity anchor, not a repeated proxy for every quality dimension.",
                "LLM-only professional judgments remain provisional and cannot authorize training admission.",
            ],
        )

    def _complexity_dimension(
        self,
        dimension: UtilityDimension,
        elements: List[str],
        paths: Dict[str, str],
        rationale: str,
    ) -> ProductiveComplexityDimensionV1:
        clean = [str(item) for item in elements if str(item).strip()]
        return ProductiveComplexityDimensionV1(
            dimension=dimension,
            status="provisional" if clean else "blocked",
            structural_signal_count=len(clean),
            evidence_element_ids=clean,
            evidence_paths=self._path(paths, "proposal"),
            rationale=rationale,
        )

    @staticmethod
    def _items(value: Any, name: str) -> List[Any]:
        if isinstance(value, dict):
            result = value.get(name, [])
        else:
            result = getattr(value, name, [])
        return list(result or [])

    @staticmethod
    def _value(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _path(paths: Dict[str, str], name: str) -> List[str]:
        value = paths.get(name)
        return [value] if value else []
