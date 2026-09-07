"""Contracts and policy helpers for the fixed R10.12 Stirrup calibration.

This module deliberately does not implement a generic benchmark harness.  It
only binds the small, pre-registered R10.12 model panel, solver receipts, and
strict single-submission grading diagnostics.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.evaluation.independent_rubric_grader import (
    IndependentRubricGradeDraftV1,
    IndependentRubricGradeV1,
    canonical_json_sha256,
)


Tier = Literal["strong", "middle", "weak"]
PreflightStatus = Literal["passed", "technical_failure", "semantic_failure"]
AttemptState = Literal[
    "succeeded",
    "technical_failure_before_semantic_turn",
    "semantic_or_delivery_failure",
]
DeliveryStatus = Literal["complete", "invalid", "missing"]

PRIMARY_MODELS: dict[Tier, str] = {
    "strong": "gpt-5.4-mini",
    "middle": "gpt-5-mini",
    "weak": "gpt-4o-mini",
}
FALLBACK_MODELS: dict[Tier, str | None] = {
    "strong": None,
    "middle": None,
    "weak": None,
}


class StirrupPreflightResultV1(ScenarioFirstModel):
    preflight_version: Literal["r10.stirrup_preflight.1"] = "r10.stirrup_preflight.1"
    tier: Tier
    model_id: str = Field(min_length=1)
    candidate_role: Literal["primary", "fallback"]
    status: PreflightStatus
    attempt_count: StrictInt = Field(ge=1, le=2)
    first_failure_preserved: StrictBool = True
    evidence_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def registered_candidate(self) -> "StirrupPreflightResultV1":
        expected = PRIMARY_MODELS[self.tier] if self.candidate_role == "primary" else FALLBACK_MODELS[self.tier]
        if expected is None or self.model_id != expected:
            raise ValueError("r10_12_unregistered_preflight_candidate")
        return self


class FrozenStirrupPanelV1(ScenarioFirstModel):
    panel_version: Literal["r10.frozen_stirrup_panel.1"] = "r10.frozen_stirrup_panel.1"
    provider_id: Literal["tuzi_chat_completions"] = "tuzi_chat_completions"
    strong: str
    middle: str
    weak: str
    preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def freeze_model_panel(results: list[StirrupPreflightResultV1]) -> FrozenStirrupPanelV1:
    """Select only the registered primary or fixed fallback before task runs."""

    selected: dict[Tier, str] = {}
    for tier in ("strong", "middle", "weak"):
        rows = [row for row in results if row.tier == tier]
        primary = [row for row in rows if row.candidate_role == "primary"]
        fallback = [row for row in rows if row.candidate_role == "fallback"]
        if len(primary) != 1:
            raise ValueError("r10_12_primary_preflight_missing_or_duplicate")
        if primary[0].status == "passed":
            if fallback:
                raise ValueError("r10_12_fallback_probed_after_primary_pass")
            selected[tier] = primary[0].model_id
            continue
        expected_fallback = FALLBACK_MODELS[tier]
        if expected_fallback is None or len(fallback) != 1 or fallback[0].status != "passed":
            raise ValueError("r10_12_model_tier_unavailable")
        selected[tier] = fallback[0].model_id
    return FrozenStirrupPanelV1(
        strong=selected["strong"],
        middle=selected["middle"],
        weak=selected["weak"],
        preflight_sha256=canonical_json_sha256(results),
    )


class StirrupSolverAttemptV1(ScenarioFirstModel):
    attempt_number: StrictInt = Field(ge=1, le=2)
    state: AttemptState
    semantic_phase_started: StrictBool
    technical_recovery_of: StrictInt | None = Field(default=None, ge=1, le=1)
    evidence_path: str = Field(min_length=1)
    failure_type: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def failure_semantics(self) -> "StirrupSolverAttemptV1":
        technical = self.state == "technical_failure_before_semantic_turn"
        if technical == self.semantic_phase_started:
            raise ValueError("r10_12_attempt_state_semantic_marker_conflict")
        if self.attempt_number == 1 and self.technical_recovery_of is not None:
            raise ValueError("r10_12_initial_attempt_cannot_be_recovery")
        if self.attempt_number == 2 and self.technical_recovery_of != 1:
            raise ValueError("r10_12_recovery_must_link_first_attempt")
        return self


class StirrupSolverReceiptV1(ScenarioFirstModel):
    receipt_version: Literal["r10.stirrup_solver_receipt.1"] = "r10.stirrup_solver_receipt.1"
    task_id: str = Field(min_length=1)
    solver_id: str = Field(min_length=1)
    tier: Tier
    provider_id: Literal["tuzi_chat_completions"] = "tuzi_chat_completions"
    harness_id: Literal["stirrup"] = "stirrup"
    harness_version: Literal["0.1.8"] = "0.1.8"
    e2b_sdk_version: Literal["2.20.0"] = "2.20.0"
    e2b_template_alias: Literal["rw-task-sandbox:stable"] = "rw-task-sandbox:stable"
    e2b_template_build_id: Literal["c9cf3369-49c8-4bff-8f81-8ad9ce9cc252"] = (
        "c9cf3369-49c8-4bff-8f81-8ad9ce9cc252"
    )
    max_turns: Literal[100] = 100
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_status: DeliveryStatus
    delivery_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    attempts: list[StirrupSolverAttemptV1] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def valid_attempt_chain_and_delivery(self) -> "StirrupSolverReceiptV1":
        if [row.attempt_number for row in self.attempts] != list(range(1, len(self.attempts) + 1)):
            raise ValueError("r10_12_attempt_sequence_invalid")
        if len(self.attempts) == 2:
            first = self.attempts[0]
            if first.state != "technical_failure_before_semantic_turn" or first.semantic_phase_started:
                raise ValueError("r10_12_semantic_attempt_not_rerunnable")
        complete = self.delivery_status == "complete"
        if complete != (self.delivery_sha256 is not None):
            raise ValueError("r10_12_delivery_hash_status_conflict")
        if complete and self.attempts[-1].state != "succeeded":
            raise ValueError("r10_12_complete_delivery_requires_success")
        return self


def strict_grading_system_prompt() -> str:
    return """You independently grade one anonymous professional work product against a fixed rubric.
Assess every rubric item exactly once and award an integer from zero through max_score. Full credit is rare:
award it only when explicit, complete, direct candidate-visible evidence satisfies the entire criterion. Partial,
ambiguous, indirect, or incomplete evidence receives partial credit rather than default full credit. For a
highest-weight item, require strong direct evidence for full credit. When uncertain between two defensible scores,
choose the lower score unless the higher score is clearly justified. Cite actual candidate-visible files. Never
add criteria, apply a holistic preference or veto, infer authorship, penalize a high aggregate score, or perform a
second downward audit. Unsupported claims reduce only rubric items they directly affect. If a visible prerequisite
did not trigger, mark not_triggered and award full item credit. If material cannot be read or applicability cannot
be established, mark unresolved and material_status incomplete; do not guess. Explicit format and structure
requirements remain requirements. Return only JSON matching the supplied schema; do not output totals."""


class ShadowItemReductionV1(ScenarioFirstModel):
    rubric_item_id: str
    max_score: StrictInt = Field(gt=0)
    primary_awarded: StrictInt = Field(ge=0)
    audited_awarded: StrictInt = Field(ge=0)
    reduction: StrictInt = Field(ge=0)


class ShadowDownwardAuditDiagnosticV1(ScenarioFirstModel):
    diagnostic_version: Literal["r10.shadow_downward_audit.1"] = "r10.shadow_downward_audit.1"
    task_id: str
    submission_id: str
    primary_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_draft_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reductions: list[ShadowItemReductionV1]
    total_reduction: StrictInt = Field(ge=0)
    primary_score_unchanged: Literal[True] = True


def build_shadow_downward_diagnostic(
    primary: IndependentRubricGradeV1,
    audit: IndependentRubricGradeDraftV1,
) -> ShadowDownwardAuditDiagnosticV1:
    if primary.material_status != "complete" or primary.total_score is None:
        raise ValueError("r10_12_shadow_requires_complete_primary")
    original = {row.rubric_item_id: row for row in primary.items}
    audited = {row.rubric_item_id: row for row in audit.assessments}
    if set(original) != set(audited):
        raise ValueError("r10_12_shadow_rubric_coverage_mismatch")
    reductions = []
    for item in primary.items:
        candidate = audited[item.rubric_item_id]
        if candidate.awarded > item.awarded:
            raise ValueError("r10_12_shadow_audit_cannot_increase")
        reductions.append(ShadowItemReductionV1(
            rubric_item_id=item.rubric_item_id,
            max_score=item.max_score,
            primary_awarded=item.awarded,
            audited_awarded=candidate.awarded,
            reduction=item.awarded - candidate.awarded,
        ))
    return ShadowDownwardAuditDiagnosticV1(
        task_id=primary.task_id,
        submission_id=primary.submission_id,
        primary_review_sha256=primary.review_sha256,
        audit_draft_sha256=canonical_json_sha256(audit),
        reductions=reductions,
        total_reduction=sum(row.reduction for row in reductions),
    )
