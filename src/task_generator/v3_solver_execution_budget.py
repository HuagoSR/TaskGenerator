from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SolverExecutionBudgetV1(BaseModel):
    """Fail-closed limits for one governed solver process.

    Request bytes are a conservative pre-call upper bound for input tokens: a
    tokenizer cannot emit more non-empty tokens than the UTF-8 bytes supplied.
    Contract cost is therefore reserved before every call from request bytes
    plus the configured completion cap. It is not represented as provider
    billing telemetry.
    """

    model_config = ConfigDict(extra="forbid")

    budget_version: Literal["v3.solver_execution_budget.1"] = (
        "v3.solver_execution_budget.1"
    )
    solver_model: str
    maximum_provider_calls: int = Field(ge=1, le=32)
    maximum_agent_turns: int = Field(ge=1, le=32)
    maximum_request_bytes_per_call: int = Field(ge=1024)
    maximum_completion_tokens_per_call: int = Field(ge=256, le=32768)
    maximum_context_tokens: int = Field(default=64000, ge=4096, le=1_000_000)
    maximum_consecutive_empty_assistant_responses: int = Field(
        default=2, ge=1, le=2
    )
    maximum_provider_input_tokens: int = Field(ge=1)
    maximum_provider_output_tokens: int = Field(ge=1)
    input_cost_usd_per_million_tokens: float = Field(ge=0)
    output_cost_usd_per_million_tokens: float = Field(ge=0)
    maximum_contract_cost_usd: float = Field(gt=0)
    provider_sdk_retries: Literal[0] = 0
    runner_retries: Literal[0] = 0
    require_finish_signal: Literal[True] = True
    require_nonempty_deliverable: Literal[True] = True

    @model_validator(mode="after")
    def validate_turn_call_relation(self) -> "SolverExecutionBudgetV1":
        if self.maximum_agent_turns > self.maximum_provider_calls:
            raise ValueError("agent_turns_exceed_provider_call_ceiling")
        if self.maximum_context_tokens < self.maximum_completion_tokens_per_call:
            raise ValueError("context_window_below_completion_ceiling")
        return self


class SolverExecutionUsageV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_calls: int = 0
    request_bytes_upper_bound: int = 0
    provider_input_tokens: int = 0
    provider_output_tokens: int = 0
    contract_cost_usd: float = 0.0


class SolverProtocolObservationV1(BaseModel):
    """Sanitized per-call shape metadata; never stores prompt or response text."""

    model_config = ConfigDict(extra="forbid")

    provider_call: int = Field(ge=1)
    has_content: bool
    has_tool_calls: bool
    has_reasoning: bool
    input_tokens: int = Field(ge=0)
    answer_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    consecutive_empty_responses: int = Field(ge=0)
    disposition: Literal["substantive", "empty_protocol_shape"]


class SolverExecutionBudgetDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "blocked"]
    reason: Optional[str] = None
    reserved_contract_cost_usd: float = 0.0


class SolverExecutionBudgetLedger:
    def __init__(self, budget: SolverExecutionBudgetV1):
        self.budget = budget
        self.usage = SolverExecutionUsageV1()

    def before_call(self, request_payload: object) -> SolverExecutionBudgetDecisionV1:
        request_bytes = len(
            json.dumps(
                request_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
        if self.usage.provider_calls >= self.budget.maximum_provider_calls:
            return self._blocked("provider_call_ceiling_reached")
        if request_bytes > self.budget.maximum_request_bytes_per_call:
            return self._blocked("request_byte_ceiling_exceeded")
        if (
            self.usage.request_bytes_upper_bound + request_bytes
            > self.budget.maximum_provider_input_tokens
        ):
            return self._blocked("provider_input_token_upper_bound_exceeded")
        if (
            self.usage.provider_output_tokens
            + self.budget.maximum_completion_tokens_per_call
            > self.budget.maximum_provider_output_tokens
        ):
            return self._blocked("provider_output_token_reservation_exceeded")
        reserved = self._cost(
            input_tokens=request_bytes,
            output_tokens=self.budget.maximum_completion_tokens_per_call,
        )
        if self.usage.contract_cost_usd + reserved > (
            self.budget.maximum_contract_cost_usd + 1e-12
        ):
            return self._blocked("contract_cost_reservation_exceeded")
        self.usage.provider_calls += 1
        self.usage.request_bytes_upper_bound += request_bytes
        return SolverExecutionBudgetDecisionV1(
            decision="allow",
            reserved_contract_cost_usd=round(reserved, 12),
        )

    def after_call(self, *, input_tokens: int, output_tokens: int) -> None:
        self.usage.provider_input_tokens += max(0, int(input_tokens))
        self.usage.provider_output_tokens += max(0, int(output_tokens))
        self.usage.contract_cost_usd = round(
            self._cost(
                self.usage.provider_input_tokens,
                self.usage.provider_output_tokens,
            ),
            12,
        )
        if self.usage.provider_input_tokens > self.budget.maximum_provider_input_tokens:
            raise RuntimeError("provider_reported_input_token_ceiling_exceeded")
        if self.usage.provider_output_tokens > self.budget.maximum_provider_output_tokens:
            raise RuntimeError("provider_reported_output_token_ceiling_exceeded")
        if self.usage.contract_cost_usd > self.budget.maximum_contract_cost_usd:
            raise RuntimeError("provider_reported_contract_cost_ceiling_exceeded")

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.budget.input_cost_usd_per_million_tokens
            + output_tokens * self.budget.output_cost_usd_per_million_tokens
        ) / 1_000_000

    @staticmethod
    def _blocked(reason: str) -> SolverExecutionBudgetDecisionV1:
        return SolverExecutionBudgetDecisionV1(decision="blocked", reason=reason)


class SolverProcessOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_version: Literal["v3.solver_process_outcome.1"] = (
        "v3.solver_process_outcome.1"
    )
    solver_model: str
    process_status: Literal["succeeded", "failed", "timeout", "blocked"]
    finish_signal_received: bool
    deliverable_file_count: int
    budget: SolverExecutionBudgetV1
    usage: SolverExecutionUsageV1
    protocol_observations: list[SolverProtocolObservationV1] = Field(
        default_factory=list
    )
    first_failure: Optional[str] = None
    output_tree_sha256: Optional[str] = None


def inspect_solver_process_outcome(
    *,
    solver_model: str,
    output_root: str | Path,
    budget: SolverExecutionBudgetV1,
    usage: SolverExecutionUsageV1,
    finish_signal_received: bool,
    process_error: str | None = None,
    expected_deliverable_paths: Optional[list[str]] = None,
    deliverable_contract_path: str | Path | None = None,
    protocol_observations: Optional[list[SolverProtocolObservationV1]] = None,
) -> SolverProcessOutcomeV1:
    root = Path(output_root)
    deliverable_root = root / "deliverable_files"
    files = sorted(
        item for item in deliverable_root.rglob("*") if item.is_file()
    ) if deliverable_root.exists() else []
    failure = process_error
    if failure is None and budget.require_finish_signal and not finish_signal_received:
        failure = "finish_signal_missing"
    if failure is None and budget.require_nonempty_deliverable and not files:
        failure = "nonempty_deliverable_missing"
    if failure is None and expected_deliverable_paths is not None:
        observed = {item.relative_to(root).as_posix() for item in files}
        expected = set(expected_deliverable_paths)
        if observed != expected or any(item.stat().st_size == 0 for item in files):
            failure = "exact_deliverable_contract_not_satisfied"
    if failure is None and deliverable_contract_path is not None:
        from task_generator.v3_behavioral_validation import inspect_delivery
        from task_generator.v3_deliverable_contract import DeliverableContractV1

        contract = DeliverableContractV1.model_validate_json(
            Path(deliverable_contract_path).read_text(encoding="utf-8")
        )
        delivery = inspect_delivery(root, contract)
        if delivery.delivery_status != "valid":
            failure = "openable_deliverable_contract_not_satisfied"
    status: Literal["succeeded", "failed", "timeout", "blocked"] = (
        "succeeded" if failure is None else "blocked"
        if failure.startswith("budget:") else "failed"
    )
    digest = None
    if files:
        aggregate = hashlib.sha256()
        for file in files:
            aggregate.update(file.relative_to(deliverable_root).as_posix().encode())
            aggregate.update(b"\0")
            aggregate.update(hashlib.sha256(file.read_bytes()).digest())
        digest = aggregate.hexdigest()
    return SolverProcessOutcomeV1(
        solver_model=solver_model,
        process_status=status,
        finish_signal_received=finish_signal_received,
        deliverable_file_count=len(files),
        budget=budget,
        usage=usage,
        protocol_observations=protocol_observations or [],
        first_failure=failure,
        output_tree_sha256=digest,
    )
