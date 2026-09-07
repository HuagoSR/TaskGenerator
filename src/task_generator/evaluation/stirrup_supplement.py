"""Fixed contracts for the four-route R10.12-S1 Stirrup supplement."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.evaluation.independent_rubric_grader import canonical_json_sha256
from task_generator.evaluation.stirrup_calibration import (
    DeliveryStatus,
    StirrupSolverAttemptV1,
)


SupplementSlot = Literal["strong_primary", "strong_check", "cross_family", "lower_anchor"]

SUPPLEMENT_MODELS: dict[SupplementSlot, str] = {
    "strong_primary": "gpt-5.5",
    "strong_check": "gpt-5.6-sol",
    "cross_family": "glm-5.2",
    "lower_anchor": "gpt-5.4-mini",
}

TerraTransport = Literal["local_tuzi_chat", "server_tuzi_chat", "server_chatgpt_codex"]


class TerraTransportDiagnosticReceiptV1(ScenarioFirstModel):
    receipt_version: Literal["r10.terra_transport_diagnostic_receipt.1"] = (
        "r10.terra_transport_diagnostic_receipt.1"
    )
    transport: TerraTransport
    judge_id: Literal["gpt-5.6-terra"] = "gpt-5.6-terra"
    normal_call_count: Literal[1] = 1
    retry_count: Literal[0] = 0
    request_started: StrictBool
    status: Literal["passed", "http_failure", "protocol_failure", "format_failure", "semantic_failure"]
    environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    exit_code: StrictInt | None = None
    evidence_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def passed_has_output(self) -> "TerraTransportDiagnosticReceiptV1":
        if (self.status == "passed") != (self.output_sha256 is not None):
            raise ValueError("r10_12_d_output_status_conflict")
        return self


class StrictGradePacketV1(ScenarioFirstModel):
    packet_version: Literal["r10.strict_grade_packet.1"] = "r10.strict_grade_packet.1"
    task_id: str = Field(min_length=1)
    strict_system: str = Field(min_length=1)
    rubric_items: list[dict[str, Any]] = Field(min_length=1)
    required_evidence_path_roots: list[str] = Field(min_length=1)
    materials: str = Field(min_length=1)
    output_schema: dict[str, Any]


class StirrupSupplementProtocolProbeV1(ScenarioFirstModel):
    probe_version: Literal["r10.stirrup_supplement_protocol_probe.1"] = (
        "r10.stirrup_supplement_protocol_probe.1"
    )
    slot: SupplementSlot
    requested_model: str
    endpoint: Literal["/v1/chat/completions"] = "/v1/chat/completions"
    status: Literal["passed", "technical_failure", "protocol_or_semantic_failure"]
    attempt_count: StrictInt = Field(ge=1, le=2)
    completed_model_requests: StrictInt = Field(ge=0)
    code_exec_observed: StrictBool
    finish_observed: StrictBool
    tool_result_roundtrip_observed: StrictBool
    delivery_valid: StrictBool
    evidence_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def registered_and_complete(self) -> "StirrupSupplementProtocolProbeV1":
        if self.requested_model != SUPPLEMENT_MODELS[self.slot]:
            raise ValueError("r10_12_s1_unregistered_probe_model")
        passed = self.status == "passed"
        evidence_passed = (
            self.completed_model_requests >= 2
            and self.code_exec_observed
            and self.finish_observed
            and self.tool_result_roundtrip_observed
            and self.delivery_valid
        )
        if passed != evidence_passed:
            raise ValueError("r10_12_s1_probe_status_evidence_conflict")
        return self


class FrozenStirrupSupplementPanelV1(ScenarioFirstModel):
    panel_version: Literal["r10.frozen_stirrup_supplement_panel.1"] = (
        "r10.frozen_stirrup_supplement_panel.1"
    )
    provider_id: Literal["tuzi_chat_completions"] = "tuzi_chat_completions"
    endpoint: Literal["/v1/chat/completions"] = "/v1/chat/completions"
    models: dict[SupplementSlot, str]
    probe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_panel(self) -> "FrozenStirrupSupplementPanelV1":
        if self.models != SUPPLEMENT_MODELS:
            raise ValueError("r10_12_s1_panel_model_drift")
        return self


def freeze_supplement_panel(
    probes: list[StirrupSupplementProtocolProbeV1],
) -> FrozenStirrupSupplementPanelV1:
    by_slot = {row.slot: row for row in probes}
    if len(probes) != len(SUPPLEMENT_MODELS) or set(by_slot) != set(SUPPLEMENT_MODELS):
        raise ValueError("r10_12_s1_probe_coverage_invalid")
    if any(row.status != "passed" for row in probes):
        raise ValueError("r10_12_s1_protocol_gate_failed")
    return FrozenStirrupSupplementPanelV1(
        models=SUPPLEMENT_MODELS,
        probe_sha256=canonical_json_sha256(probes),
    )


class StirrupSupplementSolverReceiptV1(ScenarioFirstModel):
    receipt_version: Literal["r10.stirrup_supplement_solver_receipt.1"] = (
        "r10.stirrup_supplement_solver_receipt.1"
    )
    task_id: str = Field(min_length=1)
    solver_id: str = Field(min_length=1)
    slot: SupplementSlot
    provider_id: Literal["tuzi_chat_completions"] = "tuzi_chat_completions"
    endpoint: Literal["/v1/chat/completions"] = "/v1/chat/completions"
    harness_id: Literal["stirrup"] = "stirrup"
    harness_version: Literal["0.1.8"] = "0.1.8"
    e2b_sdk_version: Literal["2.20.0"] = "2.20.0"
    e2b_template_alias: Literal["rw-task-sandbox:stable"] = "rw-task-sandbox:stable"
    e2b_template_build_id: Literal["c9cf3369-49c8-4bff-8f81-8ad9ce9cc252"] = (
        "c9cf3369-49c8-4bff-8f81-8ad9ce9cc252"
    )
    max_turns: Literal[100] = 100
    context_window_tokens: Literal[64000] = 64000
    max_completion_tokens: Literal[8192] = 8192
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_status: DeliveryStatus
    delivery_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_metadata_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    completed_model_requests: StrictInt = Field(default=0, ge=0)
    observed_tool_names: list[str] = Field(default_factory=list)
    attempts: list[StirrupSolverAttemptV1] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def registered_model_and_delivery(self) -> "StirrupSupplementSolverReceiptV1":
        if self.solver_id != SUPPLEMENT_MODELS[self.slot]:
            raise ValueError("r10_12_s1_unregistered_solver_model")
        if [row.attempt_number for row in self.attempts] != list(range(1, len(self.attempts) + 1)):
            raise ValueError("r10_12_s1_attempt_sequence_invalid")
        if len(self.attempts) == 2 and self.attempts[0].state != "technical_failure_before_semantic_turn":
            raise ValueError("r10_12_s1_semantic_attempt_not_rerunnable")
        complete = self.delivery_status == "complete"
        if complete != (self.delivery_sha256 is not None):
            raise ValueError("r10_12_s1_delivery_hash_status_conflict")
        if complete and self.attempts[-1].state != "succeeded":
            raise ValueError("r10_12_s1_complete_delivery_requires_success")
        return self


def classify_supplement_result(
    *,
    all_deliveries_valid: bool,
    primary_structural_valid: bool,
    sentinel_acceptance: bool,
    means: dict[str, float],
    task_scores: dict[str, dict[str, float]],
    professional_item_gap_present: bool,
) -> str:
    """Apply only the pre-registered S1 interpretation rules."""

    if not all_deliveries_valid or not primary_structural_valid or not sentinel_acceptance:
        return "incomplete"
    if set(means) != set(SUPPLEMENT_MODELS.values()):
        return "incomplete"
    strong = (means["gpt-5.5"], means["gpt-5.6-sol"])
    lower = means["gpt-5.4-mini"]
    higher_counts = {
        model: sum(scores[model] > scores["gpt-5.4-mini"] for scores in task_scores.values())
        for model in ("gpt-5.5", "gpt-5.6-sol")
    }
    gaps = [value - lower for value in strong]
    if (
        all(value >= .75 for value in strong)
        and all(value >= .10 for value in gaps)
        and max(gaps) >= .15
        and all(value >= 2 for value in higher_counts.values())
        and professional_item_gap_present
    ):
        return "strong_anchor_separation_supported"
    mean_spread = max(means.values()) - min(means.values())
    narrow_tasks = sum(max(scores.values()) - min(scores.values()) <= .10 for scores in task_scores.values())
    if mean_spread <= .10 and narrow_tasks >= 2:
        return "tasks_likely_ceiling_limited"
    return "mixed_inconclusive"
