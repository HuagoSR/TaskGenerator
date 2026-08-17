from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_behavioral_validation import SolverToolPreflightReportV1
from task_generator.v3_validity_utility import (
    EvaluationCalibrationContractV1,
)


SolverStratum = Literal["weak", "medium", "strong"]
ProfessionalDecision = Literal[
    "not_evaluated",
    "provisional",
    "pass",
    "revise",
    "blocked",
]


class SolverPanelMemberV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solver_model: str
    stratum: SolverStratum
    preflight_report_path: str
    preflight_report: SolverToolPreflightReportV1
    provider: str
    maximum_cost_per_task_usd: float = Field(gt=0.0)
    selected_before_formal_results: Literal[True] = True

    @model_validator(mode="after")
    def validate_preflight_identity(self) -> "SolverPanelMemberV1":
        if self.preflight_report.solver_model != self.solver_model:
            raise ValueError("solver_panel_preflight_model_mismatch")
        return self


class FrozenSolverPanelV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    panel_version: Literal["v3.frozen_solver_panel.1"] = (
        "v3.frozen_solver_panel.1"
    )
    panel_id: str
    members: List[SolverPanelMemberV1]
    decision: Literal["pass", "blocked"]
    blocking_reasons: List[str] = Field(default_factory=list)
    frozen_before_formal_results: Literal[True] = True
    external_execution_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class GraderScoreObservationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    solver_model: str
    grader_model: str
    repeat_index: int = Field(ge=1)
    overall_score_ratio: float = Field(ge=0.0, le=1.0)
    dimension_score_ratios: Dict[str, float] = Field(default_factory=dict)
    valid_delivery: bool
    grader_output_path: str
    grader_output_sha256: str

    @model_validator(mode="after")
    def validate_dimensions(self) -> "GraderScoreObservationV1":
        if any(value < 0.0 or value > 1.0 for value in self.dimension_score_ratios.values()):
            raise ValueError("grader_dimension_score_out_of_range")
        return self


class GraderPairStabilityV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    solver_model: str
    grader_model: str
    repeat_count: int
    overall_score_spread: float
    maximum_dimension_spread: float
    stable: bool


class GraderStabilityReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.grader_stability.1"] = (
        "v3.grader_stability.1"
    )
    calibration_contract: EvaluationCalibrationContractV1
    decision: Literal["not_evaluated", "pass", "blocked"]
    observation_count: int
    repeated_pair_count: int
    stable_pair_count: int
    grader_disagreement_rate: Optional[float] = None
    score_saturation_rate: Optional[float] = None
    informative_case_rate: Optional[float] = None
    pair_records: List[GraderPairStabilityV1] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ProfessionalValidityReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_version: Literal["v3.professional_validity_review.1"] = (
        "v3.professional_validity_review.1"
    )
    blind_task_id: str
    reviewer_type: Literal["llm_proxy", "independent_expert"]
    reviewer_id: str
    generator_independent: bool
    decision: ProfessionalDecision
    evidence_paths: List[str] = Field(min_length=1)
    realism_findings: List[str] = Field(default_factory=list)
    workflow_findings: List[str] = Field(default_factory=list)
    deliverable_findings: List[str] = Field(default_factory=list)
    material_defects: List[str] = Field(default_factory=list)
    rationale: str = Field(min_length=12)
    training_admission_authority: bool = False

    @model_validator(mode="after")
    def enforce_evidence_ceiling(self) -> "ProfessionalValidityReviewV1":
        if self.reviewer_type == "llm_proxy":
            if self.decision not in {
                "not_evaluated",
                "provisional",
                "revise",
                "blocked",
            }:
                raise ValueError("llm_proxy_cannot_issue_professional_pass")
            if self.training_admission_authority:
                raise ValueError("llm_proxy_has_no_training_admission_authority")
        if self.reviewer_type == "independent_expert":
            if not self.generator_independent:
                raise ValueError("expert_review_must_be_generator_independent")
            if self.training_admission_authority and self.decision != "pass":
                raise ValueError(
                    "training_admission_authority_requires_expert_pass"
                )
        return self


class EvaluationCalibrationCompiler:
    def freeze_solver_panel(
        self,
        *,
        panel_id: str,
        members: List[SolverPanelMemberV1],
    ) -> FrozenSolverPanelV1:
        reasons: List[str] = []
        strata = [item.stratum for item in members]
        models = [item.solver_model for item in members]
        if sorted(strata) != ["medium", "strong", "weak"]:
            reasons.append("solver_panel_requires_one_weak_medium_strong")
        if len(models) != len(set(models)):
            reasons.append("solver_panel_models_must_be_distinct")
        for member in members:
            report = member.preflight_report
            preflight_path = Path(member.preflight_report_path)
            if not preflight_path.is_file():
                reasons.append(
                    f"solver_preflight_evidence_missing:{member.solver_model}"
                )
            else:
                try:
                    persisted_report = SolverToolPreflightReportV1.model_validate_json(
                        preflight_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    reasons.append(
                        f"solver_preflight_evidence_invalid:{member.solver_model}"
                    )
                else:
                    if persisted_report != report:
                        reasons.append(
                            f"solver_preflight_evidence_mismatch:{member.solver_model}"
                        )
            if report.status != "pass":
                reasons.append(
                    f"solver_preflight_not_pass:{member.solver_model}"
                )
            if not report.eligible_for_business_eval:
                reasons.append(
                    f"solver_not_business_eligible:{member.solver_model}"
                )
        return FrozenSolverPanelV1(
            panel_id=panel_id,
            members=members,
            decision="pass" if not reasons else "blocked",
            blocking_reasons=sorted(set(reasons)),
            notes=[
                "Panel membership and strata are frozen before formal route results.",
                "A frozen panel does not authorize external solver execution.",
            ],
        )

    def analyze_grader_stability(
        self,
        *,
        observations: List[GraderScoreObservationV1],
        calibration_contract: Optional[
            EvaluationCalibrationContractV1
        ] = None,
    ) -> GraderStabilityReportV1:
        contract = calibration_contract or EvaluationCalibrationContractV1()
        if not observations:
            return GraderStabilityReportV1(
                calibration_contract=contract,
                decision="not_evaluated",
                observation_count=0,
                repeated_pair_count=0,
                stable_pair_count=0,
                blocking_reasons=["grader_observations_missing"],
                notes=[
                    "No score or stability claim is made without repeated grader observations."
                ],
            )
        artifact_failures = []
        for item in observations:
            output_path = Path(item.grader_output_path)
            if not output_path.is_file():
                artifact_failures.append(
                    f"grader_output_missing:{item.blind_task_id}:{item.solver_model}:"
                    f"{item.grader_model}:{item.repeat_index}"
                )
                continue
            actual_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
            if actual_sha256 != item.grader_output_sha256:
                artifact_failures.append(
                    f"grader_output_sha256_mismatch:{item.blind_task_id}:"
                    f"{item.solver_model}:{item.grader_model}:{item.repeat_index}"
                )
        if artifact_failures:
            return GraderStabilityReportV1(
                calibration_contract=contract,
                decision="blocked",
                observation_count=len(observations),
                repeated_pair_count=0,
                stable_pair_count=0,
                blocking_reasons=sorted(set(artifact_failures)),
                notes=[
                    "Grader observations are accepted only when their persisted output "
                    "artifacts exist and match the declared SHA256."
                ],
            )
        if any(not item.valid_delivery for item in observations):
            return GraderStabilityReportV1(
                calibration_contract=contract,
                decision="blocked",
                observation_count=len(observations),
                repeated_pair_count=0,
                stable_pair_count=0,
                blocking_reasons=[
                    "grader_observation_contains_invalid_delivery"
                ],
                notes=[
                    "Invalid deliveries must not enter grader calibration."
                ],
            )
        grouped: Dict[
            Tuple[str, str, str],
            List[GraderScoreObservationV1],
        ] = defaultdict(list)
        for item in observations:
            grouped[
                (
                    item.blind_task_id,
                    item.solver_model,
                    item.grader_model,
                )
            ].append(item)
        pairs: List[GraderPairStabilityV1] = []
        incomplete_pairs = 0
        for (task_id, solver, grader), records in sorted(grouped.items()):
            if len(records) < 2:
                incomplete_pairs += 1
                continue
            scores = [item.overall_score_ratio for item in records]
            dimensions = {
                dimension
                for item in records
                for dimension in item.dimension_score_ratios
            }
            dimension_spreads = []
            for dimension in dimensions:
                values = [
                    item.dimension_score_ratios[dimension]
                    for item in records
                    if dimension in item.dimension_score_ratios
                ]
                if len(values) >= 2:
                    dimension_spreads.append(max(values) - min(values))
            overall_spread = max(scores) - min(scores)
            max_dimension_spread = max(dimension_spreads or [0.0])
            stable = (
                overall_spread
                <= contract.grader_disagreement_absolute_threshold
                and max_dimension_spread
                <= contract.grader_disagreement_absolute_threshold
            )
            pairs.append(
                GraderPairStabilityV1(
                    blind_task_id=task_id,
                    solver_model=solver,
                    grader_model=grader,
                    repeat_count=len(records),
                    overall_score_spread=round(overall_spread, 4),
                    maximum_dimension_spread=round(
                        max_dimension_spread,
                        4,
                    ),
                    stable=stable,
                )
            )
        disagreement_rate = (
            sum(not item.stable for item in pairs) / len(pairs)
            if pairs
            else 1.0
        )
        saturation_rate = (
            sum(
                item.overall_score_ratio
                >= contract.score_saturation_score_threshold
                for item in observations
            )
            / len(observations)
        )
        task_solver_scores: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for item in observations:
            task_solver_scores[item.blind_task_id][item.solver_model].append(
                item.overall_score_ratio
            )
        task_spreads = []
        for solver_scores in task_solver_scores.values():
            means = [
                sum(values) / len(values)
                for values in solver_scores.values()
                if values
            ]
            if len(means) >= 2:
                task_spreads.append(max(means) - min(means))
        informative_rate = (
            sum(
                spread >= contract.informative_case_min_score_spread
                for spread in task_spreads
            )
            / len(task_spreads)
            if task_spreads
            else 0.0
        )
        blocking = []
        if incomplete_pairs:
            blocking.append("grader_repeat_pairs_incomplete")
        if not pairs:
            blocking.append("grader_repeat_pairs_missing")
        if (
            disagreement_rate
            > contract.maximum_grader_disagreement_rate
        ):
            blocking.append("grader_disagreement_above_threshold")
        if (
            saturation_rate
            > contract.score_saturation_ratio_threshold
        ):
            blocking.append("score_saturation_above_threshold")
        if not task_spreads:
            blocking.append("informative_case_comparison_missing")
        return GraderStabilityReportV1(
            calibration_contract=contract,
            decision="pass" if not blocking else "blocked",
            observation_count=len(observations),
            repeated_pair_count=len(pairs),
            stable_pair_count=sum(item.stable for item in pairs),
            grader_disagreement_rate=round(disagreement_rate, 4),
            score_saturation_rate=round(saturation_rate, 4),
            informative_case_rate=round(informative_rate, 4),
            pair_records=pairs,
            blocking_reasons=blocking,
            notes=[
                "Validity failures and invalid delivery are excluded rather than encoded as low scores.",
                "Thresholds come from the pre-result calibration contract.",
            ],
        )
