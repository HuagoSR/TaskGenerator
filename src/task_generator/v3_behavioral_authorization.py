from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_solver_execution_budget import SolverExecutionBudgetV1


SolverStratum = Literal["weak", "medium", "strong"]
HARD_BLOCKED_MODELS = {"claude-sonnet-4-6", "claude_sonnet_4_6", "gpt-5.4-pro"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _copy_immutable(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256_file(destination) != _sha256_file(source):
            raise FileExistsError("immutable_behavioral_authorization_collision")
        return
    shutil.copy2(source, destination)


class BehavioralPreflightPanelMemberV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solver_model: str = Field(min_length=2)
    stratum: SolverStratum
    provider: str = Field(min_length=2)
    maximum_cost_usd: float = Field(gt=0.0)

    @model_validator(mode="after")
    def block_prohibited_models(self) -> "BehavioralPreflightPanelMemberV1":
        normalized = self.solver_model.lower()
        if normalized in HARD_BLOCKED_MODELS or (self.provider.lower() == "tuzi" and normalized.startswith("claude-")):
            raise ValueError("behavioral_preflight_hard_blocked_model")
        return self


class BehavioralPreflightAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal[
        "v3.behavioral_preflight_authorization_request.1"
    ] = "v3.behavioral_preflight_authorization_request.1"
    comparison_id: str
    requested_scope: Literal["solver_tool_preflight"] = "solver_tool_preflight"
    panel_members: List[BehavioralPreflightPanelMemberV1]
    environment_contract_id: str
    fixture_contract: Literal[
        "create_copy_edit_save_submit_xlsx_v1"
    ] = "create_copy_edit_save_submit_xlsx_v1"
    maximum_attempts_per_model: Literal[1] = 1
    timeout_seconds_per_model: int = Field(ge=60, le=1800)
    maximum_total_cost_usd: float = Field(gt=0.0)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    route_comparison_manifest_sha256: str = Field(min_length=64, max_length=64)
    provider_screening_report_sha256: str = Field(min_length=64, max_length=64)
    route_blind_staging_report_sha256: str = Field(min_length=64, max_length=64)
    container_parity_report_path: str
    container_parity_report_sha256: str = Field(min_length=64, max_length=64)
    behavioral_code_fingerprint: str = Field(min_length=64, max_length=64)
    container_parity_passed: Literal[True] = True
    container_network_mode: Literal["none"] = "none"
    container_read_only_root: Literal[True] = True
    provider_credentials_mounted: Literal[False] = False
    container_cleanup_passed: Literal[True] = True
    frozen_blind_task_ids: List[str] = Field(min_length=1)
    task_packages_uploaded: Literal[False] = False
    business_tasks_executed: Literal[False] = False
    grader_calls_authorized: Literal[False] = False
    professional_review_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    excluded_authorities: List[str]
    external_calls_made: Literal[False] = False
    user_action_required: str = Field(min_length=24)

    @model_validator(mode="after")
    def validate_panel_and_budget(self) -> "BehavioralPreflightAuthorizationRequestV1":
        if len(self.panel_members) != 3:
            raise ValueError("behavioral_preflight_requires_three_models")
        strata = sorted(member.stratum for member in self.panel_members)
        if strata != ["medium", "strong", "weak"]:
            raise ValueError("behavioral_preflight_requires_weak_medium_strong")
        models = [member.solver_model.lower() for member in self.panel_members]
        if len(models) != len(set(models)):
            raise ValueError("behavioral_preflight_models_must_be_distinct")
        reserved = sum(member.maximum_cost_usd for member in self.panel_members)
        if reserved > self.maximum_total_cost_usd:
            raise ValueError("behavioral_preflight_budget_below_reservation")
        return self


class BehavioralPreflightAuthorizationRequestV2(
    BehavioralPreflightAuthorizationRequestV1
):
    request_version: Literal[
        "v3.behavioral_preflight_authorization_request.2"
    ] = "v3.behavioral_preflight_authorization_request.2"
    solver_execution_budgets: List[SolverExecutionBudgetV1]
    cost_semantics: Literal[
        "pre_call_contract_upper_bound_not_provider_billing"
    ] = "pre_call_contract_upper_bound_not_provider_billing"
    pricing_schedule_source: str = Field(min_length=8)
    actual_provider_billing_claimed: Literal[False] = False

    @model_validator(mode="after")
    def validate_execution_budgets(self) -> "BehavioralPreflightAuthorizationRequestV2":
        members = {member.solver_model: member for member in self.panel_members}
        budgets = {budget.solver_model: budget for budget in self.solver_execution_budgets}
        if set(budgets) != set(members):
            raise ValueError("behavioral_budget_model_scope_mismatch")
        if len(budgets) != len(self.solver_execution_budgets):
            raise ValueError("behavioral_budget_models_must_be_distinct")
        for model, budget in budgets.items():
            if budget.maximum_contract_cost_usd > members[model].maximum_cost_usd:
                raise ValueError("behavioral_budget_exceeds_panel_member_ceiling")
        if sum(item.maximum_contract_cost_usd for item in budgets.values()) > (
            self.maximum_total_cost_usd + 1e-12
        ):
            raise ValueError("behavioral_budget_exceeds_total_ceiling")
        return self


class BehavioralRetainedPanelEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solver_model: str = Field(min_length=2)
    stratum: SolverStratum
    preflight_report_path: str
    preflight_report_sha256: str = Field(min_length=64, max_length=64)


class BehavioralPreflightAuthorizationRequestV3(BaseModel):
    """Exact authorization scope for replacing only failed panel members."""

    model_config = ConfigDict(extra="forbid")
    request_version: Literal[
        "v3.behavioral_preflight_authorization_request.3"
    ] = "v3.behavioral_preflight_authorization_request.3"
    request_mode: Literal["panel_replacement"] = "panel_replacement"
    comparison_id: str
    requested_scope: Literal["solver_tool_preflight"] = "solver_tool_preflight"
    panel_members: List[BehavioralPreflightPanelMemberV1]
    retained_evidence: List[BehavioralRetainedPanelEvidenceV1]
    solver_execution_budgets: List[SolverExecutionBudgetV1]
    environment_contract_id: str
    fixture_contract: Literal[
        "create_copy_edit_save_submit_xlsx_v1"
    ] = "create_copy_edit_save_submit_xlsx_v1"
    maximum_attempts_per_model: Literal[1] = 1
    timeout_seconds_per_model: int = Field(ge=60, le=1800)
    maximum_total_cost_usd: float = Field(gt=0.0)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    route_comparison_manifest_sha256: str = Field(min_length=64, max_length=64)
    provider_screening_report_sha256: str = Field(min_length=64, max_length=64)
    route_blind_staging_report_sha256: str = Field(min_length=64, max_length=64)
    admission_plan_path: str
    admission_plan_sha256: str = Field(min_length=64, max_length=64)
    replacement_boundary_path: str
    replacement_boundary_sha256: str = Field(min_length=64, max_length=64)
    retained_frozen_panel_path: str
    retained_frozen_panel_sha256: str = Field(min_length=64, max_length=64)
    retained_evidence_integrity_path: str
    retained_evidence_integrity_sha256: str = Field(min_length=64, max_length=64)
    container_parity_report_path: str
    container_parity_report_sha256: str = Field(min_length=64, max_length=64)
    behavioral_code_fingerprint: str = Field(min_length=64, max_length=64)
    container_parity_passed: Literal[True] = True
    container_network_mode: Literal["none"] = "none"
    container_read_only_root: Literal[True] = True
    provider_credentials_mounted: Literal[False] = False
    container_cleanup_passed: Literal[True] = True
    frozen_blind_task_ids: List[str] = Field(min_length=1)
    cost_semantics: Literal[
        "pre_call_contract_upper_bound_not_provider_billing"
    ] = "pre_call_contract_upper_bound_not_provider_billing"
    pricing_schedule_source: str = Field(min_length=8)
    actual_provider_billing_claimed: Literal[False] = False
    task_packages_uploaded: Literal[False] = False
    business_tasks_executed: Literal[False] = False
    grader_calls_authorized: Literal[False] = False
    professional_review_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    excluded_authorities: List[str]
    external_calls_made: Literal[False] = False
    user_action_required: str = Field(min_length=24)

    @model_validator(mode="after")
    def validate_replacement_scope(self) -> "BehavioralPreflightAuthorizationRequestV3":
        if len(self.panel_members) != 2:
            raise ValueError("behavioral_replacement_requires_two_models")
        replacement_models = [item.solver_model.lower() for item in self.panel_members]
        if len(replacement_models) != len(set(replacement_models)):
            raise ValueError("behavioral_replacement_models_must_be_distinct")
        replacement_strata = [item.stratum for item in self.panel_members]
        if len(replacement_strata) != len(set(replacement_strata)):
            raise ValueError("behavioral_replacement_strata_must_be_distinct")
        retained_models = [item.solver_model.lower() for item in self.retained_evidence]
        if not retained_models or len(retained_models) != len(set(retained_models)):
            raise ValueError("behavioral_retained_evidence_models_invalid")
        if set(replacement_models) & set(retained_models):
            raise ValueError("behavioral_replacement_must_not_rerun_retained_model")
        budgets = {item.solver_model: item for item in self.solver_execution_budgets}
        members = {item.solver_model: item for item in self.panel_members}
        if len(budgets) != len(self.solver_execution_budgets):
            raise ValueError("behavioral_budget_models_must_be_distinct")
        if set(budgets) != set(members):
            raise ValueError("behavioral_budget_model_scope_mismatch")
        for model, budget in budgets.items():
            if budget.maximum_contract_cost_usd > members[model].maximum_cost_usd:
                raise ValueError("behavioral_budget_exceeds_panel_member_ceiling")
        if sum(item.maximum_contract_cost_usd for item in budgets.values()) > (
            self.maximum_total_cost_usd + 1e-12
        ):
            raise ValueError("behavioral_budget_exceeds_total_ceiling")
        return self


class BehavioralAgentProtocolProbeAuthorizationRequestV1(BaseModel):
    """One-model, public-fixture authorization for adapter diagnosis only."""

    model_config = ConfigDict(extra="forbid")
    request_version: Literal[
        "v3.behavioral_agent_protocol_probe_authorization_request.1"
    ] = "v3.behavioral_agent_protocol_probe_authorization_request.1"
    request_mode: Literal["agent_protocol_probe"] = "agent_protocol_probe"
    comparison_id: str
    requested_scope: Literal["solver_tool_preflight"] = "solver_tool_preflight"
    panel_member: BehavioralPreflightPanelMemberV1
    solver_execution_budget: SolverExecutionBudgetV1
    environment_contract_id: str
    fixture_contract: Literal[
        "create_copy_edit_save_submit_xlsx_v1"
    ] = "create_copy_edit_save_submit_xlsx_v1"
    public_fixture_only: Literal[True] = True
    maximum_attempts: Literal[1] = 1
    timeout_seconds: int = Field(ge=60, le=900)
    maximum_total_cost_usd: float = Field(gt=0.0, le=1.0)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    route_comparison_manifest_sha256: str = Field(min_length=64, max_length=64)
    provider_screening_report_sha256: str = Field(min_length=64, max_length=64)
    route_blind_staging_report_sha256: str = Field(min_length=64, max_length=64)
    container_parity_report_path: str
    container_parity_report_sha256: str = Field(min_length=64, max_length=64)
    behavioral_code_fingerprint: str = Field(min_length=64, max_length=64)
    container_parity_passed: Literal[True] = True
    container_network_mode: Literal["none"] = "none"
    container_read_only_root: Literal[True] = True
    provider_credentials_mounted: Literal[False] = False
    container_cleanup_passed: Literal[True] = True
    frozen_blind_task_ids: List[str] = Field(min_length=1)
    pricing_schedule_source: str = Field(min_length=8)
    cost_semantics: Literal[
        "pre_call_contract_upper_bound_not_provider_billing"
    ] = "pre_call_contract_upper_bound_not_provider_billing"
    task_packages_uploaded: Literal[False] = False
    business_tasks_executed: Literal[False] = False
    grader_calls_authorized: Literal[False] = False
    professional_review_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    external_calls_made: Literal[False] = False
    user_action_required: str = Field(min_length=24)

    @model_validator(mode="after")
    def validate_probe_scope(self) -> "BehavioralAgentProtocolProbeAuthorizationRequestV1":
        if self.panel_member.solver_model != "gpt-5.6-sol":
            raise ValueError("agent_protocol_probe_requires_gpt_5_6_sol")
        if self.solver_execution_budget.solver_model != self.panel_member.solver_model:
            raise ValueError("agent_protocol_probe_budget_model_mismatch")
        if self.solver_execution_budget.maximum_provider_calls > 2:
            raise ValueError("agent_protocol_probe_call_ceiling_exceeded")
        if self.solver_execution_budget.maximum_agent_turns > 2:
            raise ValueError("agent_protocol_probe_turn_ceiling_exceeded")
        if self.solver_execution_budget.maximum_contract_cost_usd > self.maximum_total_cost_usd:
            raise ValueError("agent_protocol_probe_budget_exceeds_total")
        return self


class BehavioralPreflightAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal[
        "v3.behavioral_preflight_authorization_receipt.1"
    ] = "v3.behavioral_preflight_authorization_receipt.1"
    comparison_id: str
    authorization_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$"
    )
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    authorized_scope: Literal["solver_tool_preflight"] = "solver_tool_preflight"
    authorized_models: List[str]
    environment_contract_id: str
    maximum_attempts_per_model: Literal[1] = 1
    maximum_total_cost_usd: float = Field(gt=0.0)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    route_comparison_manifest_sha256: str = Field(min_length=64, max_length=64)
    provider_screening_report_sha256: str = Field(min_length=64, max_length=64)
    route_blind_staging_report_sha256: str = Field(min_length=64, max_length=64)
    container_parity_report_sha256: str = Field(min_length=64, max_length=64)
    behavioral_code_fingerprint: str = Field(min_length=64, max_length=64)
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: Optional[str] = None
    task_package_upload_authorized: Literal[False] = False
    business_task_execution_authorized: Literal[False] = False
    grader_execution_authorized: Literal[False] = False
    professional_review_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class BehavioralPreflightAuthorizationReceiptV2(
    BehavioralPreflightAuthorizationReceiptV1
):
    receipt_version: Literal[
        "v3.behavioral_preflight_authorization_receipt.2"
    ] = "v3.behavioral_preflight_authorization_receipt.2"
    solver_execution_budget_sha256: str = Field(min_length=64, max_length=64)
    cost_semantics: Literal[
        "pre_call_contract_upper_bound_not_provider_billing"
    ] = "pre_call_contract_upper_bound_not_provider_billing"
    actual_provider_billing_claimed: Literal[False] = False


class BehavioralPreflightAuthorizationReceiptV3(
    BehavioralPreflightAuthorizationReceiptV2
):
    receipt_version: Literal[
        "v3.behavioral_preflight_authorization_receipt.3"
    ] = "v3.behavioral_preflight_authorization_receipt.3"
    request_mode: Literal["panel_replacement"] = "panel_replacement"
    admission_plan_sha256: str = Field(min_length=64, max_length=64)
    replacement_boundary_sha256: str = Field(min_length=64, max_length=64)
    retained_frozen_panel_sha256: str = Field(min_length=64, max_length=64)
    retained_evidence_integrity_sha256: str = Field(min_length=64, max_length=64)


class BehavioralAgentProtocolProbeAuthorizationReceiptV1(
    BehavioralPreflightAuthorizationReceiptV2
):
    receipt_version: Literal[
        "v3.behavioral_agent_protocol_probe_authorization_receipt.1"
    ] = "v3.behavioral_agent_protocol_probe_authorization_receipt.1"
    request_mode: Literal["agent_protocol_probe"] = "agent_protocol_probe"


class BehavioralPreflightAuthorizationCheckV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal[
        "v3.behavioral_preflight_authorization_check.1"
    ] = "v3.behavioral_preflight_authorization_check.1"
    comparison_id: str
    decision: Literal["authorization_required", "ready", "blocked"]
    blocking_reasons: List[str] = Field(default_factory=list)
    authorization_request_sha256: str
    authorization_receipt_sha256: Optional[str] = None
    authorized_models: List[str] = Field(default_factory=list)
    solver_preflight_calls_made: Literal[False] = False
    business_task_calls_made: Literal[False] = False
    grader_calls_made: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class BehavioralAuthorizationManager:
    """Compile and validate exact authorization for tool-only solver preflight."""

    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.campaign_manifest_path = self.root / "campaign_manifest.json"
        self.route_manifest_path = (
            self.root / "governance" / "route_comparison_manifest.json"
        )
        self.screening_path = (
            self.root / "governance" / "provider_screening_outcome.json"
        )
        self.staging_path = (
            self.root
            / "blind_staging"
            / "governance"
            / "route_blind_staging_report.json"
        )
        self.current_request_path = (
            self.root
            / "governance"
            / "behavioral_preflight_authorization_request.json"
        )
        self.immutable_request_root = (
            self.root / "governance" / "behavioral_authorization_requests"
        )

    def write_preflight_request(
        self,
        *,
        panel_members: List[BehavioralPreflightPanelMemberV1],
        container_parity_report_path: str | Path,
        timeout_seconds_per_model: int = 900,
        maximum_total_cost_usd: float,
    ) -> BehavioralPreflightAuthorizationRequestV1:
        campaign, route_manifest, screening, staging = self._load_frozen_state()
        if campaign.get("status") != "evaluation_ready":
            raise PermissionError("behavioral_request_requires_evaluation_ready")
        if screening.get("decision") != "proceed_to_behavioral_evaluation":
            raise PermissionError("behavioral_request_requires_provider_screening_pass")
        if (
            staging.get("decision") != "pass"
            or staging.get("package_count") != 12
            or staging.get("teacher_artifacts_included") is not False
        ):
            raise PermissionError("behavioral_request_requires_blind_staging_pass")
        assignments = campaign.get("assignments", [])
        blind_ids = sorted(item.get("blind_task_id", "") for item in assignments)
        if len(blind_ids) != 12 or any(not item for item in blind_ids):
            raise ValueError("behavioral_request_requires_twelve_assignments")
        environment_id = route_manifest.get("environment_contract_id")
        if not environment_id:
            raise ValueError("behavioral_request_environment_contract_missing")
        parity_path = Path(container_parity_report_path).resolve()
        if not parity_path.is_file():
            raise FileNotFoundError("behavioral_request_container_parity_missing")
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        parity_checks = {
            "passed": parity.get("passed") is True,
            "returncode": parity.get("returncode") == 0,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "external_model": parity.get("external_model_execution_authorized")
            is False,
            "source_fingerprint": bool(parity.get("source_fingerprint")),
        }
        parity_failures = sorted(
            name for name, passed in parity_checks.items() if not passed
        )
        if parity_failures:
            raise ValueError(
                "behavioral_request_container_parity_not_governed:"
                + ",".join(parity_failures)
            )
        request = BehavioralPreflightAuthorizationRequestV1(
            comparison_id=campaign["comparison_id"],
            panel_members=panel_members,
            environment_contract_id=environment_id,
            timeout_seconds_per_model=timeout_seconds_per_model,
            maximum_total_cost_usd=maximum_total_cost_usd,
            campaign_manifest_sha256=_sha256_file(self.campaign_manifest_path),
            route_comparison_manifest_sha256=_sha256_file(self.route_manifest_path),
            provider_screening_report_sha256=_sha256_file(self.screening_path),
            route_blind_staging_report_sha256=_sha256_file(self.staging_path),
            container_parity_report_path=str(parity_path),
            container_parity_report_sha256=_sha256_file(parity_path),
            behavioral_code_fingerprint=parity["source_fingerprint"],
            container_parity_passed=True,
            container_network_mode=parity["network_mode"],
            container_read_only_root=parity["read_only_root"],
            provider_credentials_mounted=parity[
                "provider_credentials_mounted"
            ],
            container_cleanup_passed=parity["cleanup_returncode"] == 0,
            frozen_blind_task_ids=blind_ids,
            excluded_authorities=[
                "task_package_upload",
                "business_task_execution",
                "grader_execution",
                "professional_review",
                "registry_mutation",
                "release_activation",
                "promotion",
            ],
            user_action_required=(
                "The user must explicitly approve this exact request SHA before "
                "one tool-only solver preflight may run for each frozen model."
            ),
        )
        _atomic_json(self.current_request_path, request.model_dump(mode="json"))
        request_sha = _sha256_file(self.current_request_path)
        _copy_immutable(
            self.current_request_path,
            self.immutable_request_root / f"{request_sha}.json",
        )
        return request

    def write_preflight_request_v2(
        self,
        *,
        panel_members: List[BehavioralPreflightPanelMemberV1],
        solver_execution_budgets: List[SolverExecutionBudgetV1],
        pricing_schedule_source: str,
        container_parity_report_path: str | Path,
        timeout_seconds_per_model: int = 900,
        maximum_total_cost_usd: float,
    ) -> BehavioralPreflightAuthorizationRequestV2:
        campaign, route_manifest, screening, staging = self._load_frozen_state()
        if campaign.get("status") != "evaluation_ready":
            raise PermissionError("behavioral_request_requires_evaluation_ready")
        if screening.get("decision") != "proceed_to_behavioral_evaluation":
            raise PermissionError("behavioral_request_requires_provider_screening_pass")
        if (
            staging.get("decision") != "pass"
            or staging.get("package_count") != 12
            or staging.get("teacher_artifacts_included") is not False
        ):
            raise PermissionError("behavioral_request_requires_blind_staging_pass")
        assignments = campaign.get("assignments", [])
        blind_ids = sorted(item.get("blind_task_id", "") for item in assignments)
        if len(blind_ids) != 12 or any(not item for item in blind_ids):
            raise ValueError("behavioral_request_requires_twelve_assignments")
        environment_id = route_manifest.get("environment_contract_id")
        if not environment_id:
            raise ValueError("behavioral_request_environment_contract_missing")
        parity_path = Path(container_parity_report_path).resolve()
        if not parity_path.is_file():
            raise FileNotFoundError("behavioral_request_container_parity_missing")
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        parity_checks = {
            "passed": parity.get("passed") is True,
            "returncode": parity.get("returncode") == 0,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "external_model": parity.get("external_model_execution_authorized") is False,
            "source_fingerprint": bool(parity.get("source_fingerprint")),
        }
        failures = sorted(name for name, passed in parity_checks.items() if not passed)
        if failures:
            raise ValueError(
                "behavioral_request_container_parity_not_governed:"
                + ",".join(failures)
            )
        request = BehavioralPreflightAuthorizationRequestV2(
            comparison_id=campaign["comparison_id"],
            panel_members=panel_members,
            solver_execution_budgets=solver_execution_budgets,
            pricing_schedule_source=pricing_schedule_source,
            environment_contract_id=environment_id,
            timeout_seconds_per_model=timeout_seconds_per_model,
            maximum_total_cost_usd=maximum_total_cost_usd,
            campaign_manifest_sha256=_sha256_file(self.campaign_manifest_path),
            route_comparison_manifest_sha256=_sha256_file(self.route_manifest_path),
            provider_screening_report_sha256=_sha256_file(self.screening_path),
            route_blind_staging_report_sha256=_sha256_file(self.staging_path),
            container_parity_report_path=str(parity_path),
            container_parity_report_sha256=_sha256_file(parity_path),
            behavioral_code_fingerprint=parity["source_fingerprint"],
            frozen_blind_task_ids=blind_ids,
            excluded_authorities=[
                "task_package_upload",
                "business_task_execution",
                "grader_execution",
                "professional_review",
                "registry_mutation",
                "release_activation",
                "promotion",
            ],
            user_action_required=(
                "The user must explicitly approve this exact V2 request SHA before "
                "one budget-enforced public tool preflight may run per frozen model."
            ),
        )
        _atomic_json(self.current_request_path, request.model_dump(mode="json"))
        request_sha = _sha256_file(self.current_request_path)
        _copy_immutable(
            self.current_request_path,
            self.immutable_request_root / f"{request_sha}.json",
        )
        return request

    def write_replacement_request_v3(
        self,
        *,
        panel_members: List[BehavioralPreflightPanelMemberV1],
        retained_evidence: List[BehavioralRetainedPanelEvidenceV1],
        solver_execution_budgets: List[SolverExecutionBudgetV1],
        pricing_schedule_source: str,
        admission_plan_path: str | Path,
        replacement_boundary_path: str | Path,
        retained_frozen_panel_path: str | Path,
        retained_evidence_integrity_path: str | Path,
        container_parity_report_path: str | Path,
        timeout_seconds_per_model: int = 900,
        maximum_total_cost_usd: float,
    ) -> BehavioralPreflightAuthorizationRequestV3:
        from task_generator.v3_behavioral_preflight_evidence import (
            BehavioralEvidenceIntegrityReportV1,
        )
        from task_generator.v3_evaluation_calibration import FrozenSolverPanelV1
        from task_generator.v3_behavioral_validation import SolverToolPreflightReportV1
        from task_generator.v3_solver_panel_admission import (
            SolverPanelAdmissionPlanV1,
            SolverPanelReplacementBoundaryV1,
        )

        campaign, route_manifest, screening, staging = self._load_frozen_state()
        if campaign.get("status") != "evaluation_ready":
            raise PermissionError("behavioral_request_requires_evaluation_ready")
        if screening.get("decision") != "proceed_to_behavioral_evaluation":
            raise PermissionError("behavioral_request_requires_provider_screening_pass")
        if (
            staging.get("decision") != "pass"
            or staging.get("package_count") != 12
            or staging.get("teacher_artifacts_included") is not False
        ):
            raise PermissionError("behavioral_request_requires_blind_staging_pass")
        assignments = campaign.get("assignments", [])
        blind_ids = sorted(item.get("blind_task_id", "") for item in assignments)
        if len(blind_ids) != 12 or any(not item for item in blind_ids):
            raise ValueError("behavioral_request_requires_twelve_assignments")
        environment_id = route_manifest.get("environment_contract_id")
        if not environment_id:
            raise ValueError("behavioral_request_environment_contract_missing")

        admission_path = Path(admission_plan_path).resolve()
        boundary_path = Path(replacement_boundary_path).resolve()
        panel_path = Path(retained_frozen_panel_path).resolve()
        integrity_path = Path(retained_evidence_integrity_path).resolve()
        for path in (admission_path, boundary_path, panel_path, integrity_path):
            self._require_inside_campaign(path)
            if not path.is_file():
                raise FileNotFoundError("behavioral_replacement_evidence_missing")
        admission = SolverPanelAdmissionPlanV1.model_validate_json(
            admission_path.read_text(encoding="utf-8")
        )
        boundary = SolverPanelReplacementBoundaryV1.model_validate_json(
            boundary_path.read_text(encoding="utf-8")
        )
        panel = FrozenSolverPanelV1.model_validate_json(
            panel_path.read_text(encoding="utf-8")
        )
        integrity = BehavioralEvidenceIntegrityReportV1.model_validate_json(
            integrity_path.read_text(encoding="utf-8")
        )
        if admission.decision != "retain_passing_replace_failed":
            raise ValueError("behavioral_replacement_admission_not_ready")
        if boundary.admission_plan_sha256 != _sha256_file(admission_path):
            raise ValueError("behavioral_replacement_boundary_admission_mismatch")
        if admission.frozen_panel_sha256 != _sha256_file(panel_path):
            raise ValueError("behavioral_replacement_panel_hash_mismatch")
        if admission.evidence_integrity_sha256 != _sha256_file(integrity_path):
            raise ValueError("behavioral_replacement_integrity_hash_mismatch")
        if integrity.decision != "pass":
            raise ValueError("behavioral_replacement_retained_integrity_blocked")

        member_by_model = {item.solver_model: item for item in panel.members}
        integrity_by_model = {item.solver_model: item for item in integrity.records}
        retained_models = {item.solver_model for item in retained_evidence}
        if retained_models != set(boundary.retained_models):
            raise ValueError("behavioral_replacement_retained_scope_mismatch")
        for evidence in retained_evidence:
            report_path = Path(evidence.preflight_report_path).resolve()
            self._require_inside_campaign(report_path)
            member = member_by_model.get(evidence.solver_model)
            integrity_record = integrity_by_model.get(evidence.solver_model)
            if (
                member is None
                or member.stratum != evidence.stratum
                or member.preflight_report_path != evidence.preflight_report_path
                or not report_path.is_file()
                or evidence.preflight_report_sha256 != _sha256_file(report_path)
                or SolverToolPreflightReportV1.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                )
                != member.preflight_report
                or member.preflight_report.status != "pass"
                or not member.preflight_report.eligible_for_business_eval
                or integrity_record is None
                or integrity_record.decision != "pass"
            ):
                raise ValueError("behavioral_replacement_retained_evidence_invalid")

        slot_strata = {item.stratum for item in boundary.slots}
        candidate_strata = {item.stratum for item in panel_members}
        if candidate_strata != slot_strata:
            raise ValueError("behavioral_replacement_slot_scope_mismatch")
        prohibited = {item.lower() for item in boundary.prohibited_models}
        candidate_models = {item.solver_model.lower() for item in panel_members}
        if candidate_models & prohibited:
            raise ValueError("behavioral_replacement_prohibited_model")
        if len(panel_members) > boundary.maximum_external_models:
            raise ValueError("behavioral_replacement_model_ceiling_exceeded")

        parity_path = Path(container_parity_report_path).resolve()
        if not parity_path.is_file():
            raise FileNotFoundError("behavioral_request_container_parity_missing")
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        parity_checks = {
            "passed": parity.get("passed") is True,
            "returncode": parity.get("returncode") == 0,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "external_model": parity.get("external_model_execution_authorized") is False,
            "source_fingerprint": bool(parity.get("source_fingerprint")),
        }
        failures = sorted(name for name, passed in parity_checks.items() if not passed)
        if failures:
            raise ValueError(
                "behavioral_request_container_parity_not_governed:"
                + ",".join(failures)
            )
        request = BehavioralPreflightAuthorizationRequestV3(
            comparison_id=campaign["comparison_id"],
            panel_members=panel_members,
            retained_evidence=retained_evidence,
            solver_execution_budgets=solver_execution_budgets,
            pricing_schedule_source=pricing_schedule_source,
            environment_contract_id=environment_id,
            timeout_seconds_per_model=timeout_seconds_per_model,
            maximum_total_cost_usd=maximum_total_cost_usd,
            campaign_manifest_sha256=_sha256_file(self.campaign_manifest_path),
            route_comparison_manifest_sha256=_sha256_file(self.route_manifest_path),
            provider_screening_report_sha256=_sha256_file(self.screening_path),
            route_blind_staging_report_sha256=_sha256_file(self.staging_path),
            admission_plan_path=str(admission_path),
            admission_plan_sha256=_sha256_file(admission_path),
            replacement_boundary_path=str(boundary_path),
            replacement_boundary_sha256=_sha256_file(boundary_path),
            retained_frozen_panel_path=str(panel_path),
            retained_frozen_panel_sha256=_sha256_file(panel_path),
            retained_evidence_integrity_path=str(integrity_path),
            retained_evidence_integrity_sha256=_sha256_file(integrity_path),
            container_parity_report_path=str(parity_path),
            container_parity_report_sha256=_sha256_file(parity_path),
            behavioral_code_fingerprint=parity["source_fingerprint"],
            frozen_blind_task_ids=blind_ids,
            excluded_authorities=[
                "task_package_upload",
                "business_task_execution",
                "grader_execution",
                "professional_review",
                "registry_mutation",
                "release_activation",
                "promotion",
            ],
            user_action_required=(
                "The user must explicitly approve this exact V3 replacement request "
                "SHA before one public tool preflight may run for each replacement model."
            ),
        )
        _atomic_json(self.current_request_path, request.model_dump(mode="json"))
        request_sha = _sha256_file(self.current_request_path)
        _copy_immutable(
            self.current_request_path,
            self.immutable_request_root / f"{request_sha}.json",
        )
        return request

    def compile_replacement_receipt_v3(
        self,
        *,
        authorization_request_path: str | Path,
        authorization_id: str,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> BehavioralPreflightAuthorizationReceiptV3:
        request_path = Path(authorization_request_path).resolve()
        if request_path.parent != self.immutable_request_root.resolve():
            raise ValueError("behavioral_receipt_requires_immutable_request_path")
        request_sha = _sha256_file(request_path)
        if request_path.name != f"{request_sha}.json":
            raise ValueError("behavioral_request_filename_hash_mismatch")
        request = BehavioralPreflightAuthorizationRequestV3.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_replacement_request_state(request)
        budget_sha = _sha256_json(
            [item.model_dump(mode="json") for item in request.solver_execution_budgets]
        )
        receipt = BehavioralPreflightAuthorizationReceiptV3(
            comparison_id=request.comparison_id,
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            authorized_models=sorted(item.solver_model for item in request.panel_members),
            environment_contract_id=request.environment_contract_id,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            campaign_manifest_sha256=request.campaign_manifest_sha256,
            route_comparison_manifest_sha256=request.route_comparison_manifest_sha256,
            provider_screening_report_sha256=request.provider_screening_report_sha256,
            route_blind_staging_report_sha256=request.route_blind_staging_report_sha256,
            container_parity_report_sha256=request.container_parity_report_sha256,
            behavioral_code_fingerprint=request.behavioral_code_fingerprint,
            solver_execution_budget_sha256=budget_sha,
            admission_plan_sha256=request.admission_plan_sha256,
            replacement_boundary_sha256=request.replacement_boundary_sha256,
            retained_frozen_panel_sha256=request.retained_frozen_panel_sha256,
            retained_evidence_integrity_sha256=request.retained_evidence_integrity_sha256,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_utc_now(),
            expires_at=expires_at,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("behavioral_receipt_output_already_exists")
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def write_agent_protocol_probe_request_v1(
        self,
        *,
        panel_member: BehavioralPreflightPanelMemberV1,
        solver_execution_budget: SolverExecutionBudgetV1,
        pricing_schedule_source: str,
        container_parity_report_path: str | Path,
        timeout_seconds: int = 600,
        maximum_total_cost_usd: float,
    ) -> BehavioralAgentProtocolProbeAuthorizationRequestV1:
        campaign, route_manifest, screening, staging = self._load_frozen_state()
        if campaign.get("status") != "evaluation_ready":
            raise PermissionError("behavioral_request_requires_evaluation_ready")
        if screening.get("decision") != "proceed_to_behavioral_evaluation":
            raise PermissionError("behavioral_request_requires_provider_screening_pass")
        if staging.get("decision") != "pass":
            raise PermissionError("behavioral_request_requires_blind_staging_pass")
        parity_path = Path(container_parity_report_path).resolve()
        if not parity_path.is_file():
            raise FileNotFoundError("behavioral_request_container_parity_missing")
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        checks = {
            "passed": parity.get("passed") is True,
            "returncode": parity.get("returncode") == 0,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "external_model": parity.get("external_model_execution_authorized") is False,
            "source_fingerprint": bool(parity.get("source_fingerprint")),
        }
        failures = sorted(name for name, passed in checks.items() if not passed)
        if failures:
            raise ValueError(
                "behavioral_request_container_parity_not_governed:"
                + ",".join(failures)
            )
        request = BehavioralAgentProtocolProbeAuthorizationRequestV1(
            comparison_id=campaign["comparison_id"],
            panel_member=panel_member,
            solver_execution_budget=solver_execution_budget,
            environment_contract_id=route_manifest["environment_contract_id"],
            timeout_seconds=timeout_seconds,
            maximum_total_cost_usd=maximum_total_cost_usd,
            campaign_manifest_sha256=_sha256_file(self.campaign_manifest_path),
            route_comparison_manifest_sha256=_sha256_file(self.route_manifest_path),
            provider_screening_report_sha256=_sha256_file(self.screening_path),
            route_blind_staging_report_sha256=_sha256_file(self.staging_path),
            container_parity_report_path=str(parity_path),
            container_parity_report_sha256=_sha256_file(parity_path),
            behavioral_code_fingerprint=parity["source_fingerprint"],
            frozen_blind_task_ids=sorted(
                item.get("blind_task_id", "")
                for item in campaign.get("assignments", [])
                if item.get("blind_task_id")
            ),
            pricing_schedule_source=pricing_schedule_source,
            user_action_required=(
                "The user must explicitly approve this exact protocol-probe request "
                "SHA before one public-fixture attempt with at most two calls may run."
            ),
        )
        _atomic_json(self.current_request_path, request.model_dump(mode="json"))
        request_sha = _sha256_file(self.current_request_path)
        _copy_immutable(
            self.current_request_path,
            self.immutable_request_root / f"{request_sha}.json",
        )
        return request

    def compile_agent_protocol_probe_receipt_v1(
        self,
        *,
        authorization_request_path: str | Path,
        authorization_id: str,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> BehavioralAgentProtocolProbeAuthorizationReceiptV1:
        request_path = Path(authorization_request_path).resolve()
        if request_path.parent != self.immutable_request_root.resolve():
            raise ValueError("behavioral_receipt_requires_immutable_request_path")
        request_sha = _sha256_file(request_path)
        if request_path.name != f"{request_sha}.json":
            raise ValueError("behavioral_request_filename_hash_mismatch")
        request = BehavioralAgentProtocolProbeAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_agent_protocol_probe_request_state(request)
        budget_sha = _sha256_json(
            [request.solver_execution_budget.model_dump(mode="json")]
        )
        receipt = BehavioralAgentProtocolProbeAuthorizationReceiptV1(
            comparison_id=request.comparison_id,
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            authorized_models=[request.panel_member.solver_model],
            environment_contract_id=request.environment_contract_id,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            campaign_manifest_sha256=request.campaign_manifest_sha256,
            route_comparison_manifest_sha256=request.route_comparison_manifest_sha256,
            provider_screening_report_sha256=request.provider_screening_report_sha256,
            route_blind_staging_report_sha256=request.route_blind_staging_report_sha256,
            container_parity_report_sha256=request.container_parity_report_sha256,
            behavioral_code_fingerprint=request.behavioral_code_fingerprint,
            solver_execution_budget_sha256=budget_sha,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_utc_now(),
            expires_at=expires_at,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("behavioral_receipt_output_already_exists")
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def check_agent_protocol_probe_v1(
        self, authorization_receipt_path: str | Path | None = None
    ) -> BehavioralPreflightAuthorizationCheckV1:
        request_sha = _sha256_file(self.current_request_path)
        request = BehavioralAgentProtocolProbeAuthorizationRequestV1.model_validate_json(
            self.current_request_path.read_text(encoding="utf-8")
        )
        reasons: List[str] = []
        try:
            self._validate_agent_protocol_probe_request_state(request)
        except Exception as exc:
            reasons.append(f"behavioral_request_invalid:{type(exc).__name__}:{exc}")
        receipt_sha = None
        if authorization_receipt_path is not None:
            try:
                receipt_path = Path(authorization_receipt_path)
                receipt_sha = _sha256_file(receipt_path)
                receipt = BehavioralAgentProtocolProbeAuthorizationReceiptV1.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
                self._validate_agent_protocol_probe_receipt(
                    request, request_sha, receipt
                )
            except Exception as exc:
                reasons.append(
                    f"behavioral_receipt_invalid:{type(exc).__name__}:{exc}"
                )
        decision = (
            "blocked" if reasons else "ready"
            if authorization_receipt_path is not None
            else "authorization_required"
        )
        return BehavioralPreflightAuthorizationCheckV1(
            comparison_id=request.comparison_id,
            decision=decision,
            blocking_reasons=reasons,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=receipt_sha,
            authorized_models=[request.panel_member.solver_model],
            notes=[
                "This scope permits one public fixture, one model, one attempt and at most two provider calls.",
                "Blind packages, business execution, graders, review and mutation remain excluded.",
            ],
        )

    def check_replacement_v3(
        self, authorization_receipt_path: str | Path | None = None
    ) -> BehavioralPreflightAuthorizationCheckV1:
        if not self.current_request_path.is_file():
            raise FileNotFoundError("behavioral_preflight_request_missing")
        request_sha = _sha256_file(self.current_request_path)
        request = BehavioralPreflightAuthorizationRequestV3.model_validate_json(
            self.current_request_path.read_text(encoding="utf-8")
        )
        reasons: List[str] = []
        try:
            self._validate_replacement_request_state(request)
        except Exception as exc:
            reasons.append(f"behavioral_request_invalid:{type(exc).__name__}:{exc}")
        receipt_sha = None
        if authorization_receipt_path is not None:
            try:
                receipt_path = Path(authorization_receipt_path)
                receipt_sha = _sha256_file(receipt_path)
                receipt = BehavioralPreflightAuthorizationReceiptV3.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
                self._validate_replacement_receipt(request, request_sha, receipt)
            except Exception as exc:
                reasons.append(
                    f"behavioral_receipt_invalid:{type(exc).__name__}:{exc}"
                )
        decision = (
            "blocked" if reasons else "ready"
            if authorization_receipt_path is not None
            else "authorization_required"
        )
        return BehavioralPreflightAuthorizationCheckV1(
            comparison_id=request.comparison_id,
            decision=decision,
            blocking_reasons=reasons,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=receipt_sha,
            authorized_models=sorted(item.solver_model for item in request.panel_members),
            notes=[
                "V3 executes replacement slots only and reuses hash-bound passing evidence without a provider call.",
                "Blind packages, business execution, graders and mutation remain excluded.",
            ],
        )

    def compile_receipt_v2(
        self,
        *,
        authorization_request_path: str | Path,
        authorization_id: str,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> BehavioralPreflightAuthorizationReceiptV2:
        request_path = Path(authorization_request_path).resolve()
        if request_path.parent != self.immutable_request_root.resolve():
            raise ValueError("behavioral_receipt_requires_immutable_request_path")
        request_sha = _sha256_file(request_path)
        if request_path.name != f"{request_sha}.json":
            raise ValueError("behavioral_request_filename_hash_mismatch")
        request = BehavioralPreflightAuthorizationRequestV2.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_request_state(request)
        budget_sha = _sha256_json(
            [item.model_dump(mode="json") for item in request.solver_execution_budgets]
        )
        receipt = BehavioralPreflightAuthorizationReceiptV2(
            comparison_id=request.comparison_id,
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            authorized_models=sorted(item.solver_model for item in request.panel_members),
            environment_contract_id=request.environment_contract_id,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            campaign_manifest_sha256=request.campaign_manifest_sha256,
            route_comparison_manifest_sha256=request.route_comparison_manifest_sha256,
            provider_screening_report_sha256=request.provider_screening_report_sha256,
            route_blind_staging_report_sha256=request.route_blind_staging_report_sha256,
            container_parity_report_sha256=request.container_parity_report_sha256,
            behavioral_code_fingerprint=request.behavioral_code_fingerprint,
            solver_execution_budget_sha256=budget_sha,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_utc_now(),
            expires_at=expires_at,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("behavioral_receipt_output_already_exists")
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def check_v2(
        self, authorization_receipt_path: str | Path | None = None
    ) -> BehavioralPreflightAuthorizationCheckV1:
        if not self.current_request_path.is_file():
            raise FileNotFoundError("behavioral_preflight_request_missing")
        request_sha = _sha256_file(self.current_request_path)
        request = BehavioralPreflightAuthorizationRequestV2.model_validate_json(
            self.current_request_path.read_text(encoding="utf-8")
        )
        reasons: List[str] = []
        try:
            self._validate_request_state(request)
        except Exception as exc:
            reasons.append(f"behavioral_request_invalid:{type(exc).__name__}:{exc}")
        receipt_sha = None
        if authorization_receipt_path is not None:
            try:
                receipt_path = Path(authorization_receipt_path)
                receipt_sha = _sha256_file(receipt_path)
                receipt = BehavioralPreflightAuthorizationReceiptV2.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
                self._validate_receipt(request, request_sha, receipt)
                expected_budget_sha = _sha256_json(
                    [
                        item.model_dump(mode="json")
                        for item in request.solver_execution_budgets
                    ]
                )
                if receipt.solver_execution_budget_sha256 != expected_budget_sha:
                    raise ValueError("behavioral_receipt_budget_mismatch")
            except Exception as exc:
                reasons.append(
                    f"behavioral_receipt_invalid:{type(exc).__name__}:{exc}"
                )
        decision = (
            "blocked" if reasons else "ready"
            if authorization_receipt_path is not None
            else "authorization_required"
        )
        return BehavioralPreflightAuthorizationCheckV1(
            comparison_id=request.comparison_id,
            decision=decision,
            blocking_reasons=reasons,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=receipt_sha,
            authorized_models=sorted(item.solver_model for item in request.panel_members),
            notes=[
                "V2 ready binds per-model calls, turns, token ceilings and pre-call contract-cost reservations.",
                "Contract cost is not a claim about provider billing telemetry.",
                "Blind packages, business execution, graders and mutation remain excluded.",
            ],
        )

    def compile_receipt(
        self,
        *,
        authorization_request_path: str | Path,
        authorization_id: str,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> BehavioralPreflightAuthorizationReceiptV1:
        request_path = Path(authorization_request_path).resolve()
        if request_path.parent != self.immutable_request_root.resolve():
            raise ValueError("behavioral_receipt_requires_immutable_request_path")
        request_sha = _sha256_file(request_path)
        if request_path.name != f"{request_sha}.json":
            raise ValueError("behavioral_request_filename_hash_mismatch")
        request = BehavioralPreflightAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_request_state(request)
        receipt = BehavioralPreflightAuthorizationReceiptV1(
            comparison_id=request.comparison_id,
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            authorized_models=sorted(
                member.solver_model for member in request.panel_members
            ),
            environment_contract_id=request.environment_contract_id,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            campaign_manifest_sha256=request.campaign_manifest_sha256,
            route_comparison_manifest_sha256=(
                request.route_comparison_manifest_sha256
            ),
            provider_screening_report_sha256=(
                request.provider_screening_report_sha256
            ),
            route_blind_staging_report_sha256=(
                request.route_blind_staging_report_sha256
            ),
            container_parity_report_sha256=(
                request.container_parity_report_sha256
            ),
            behavioral_code_fingerprint=request.behavioral_code_fingerprint,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_utc_now(),
            expires_at=expires_at,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("behavioral_receipt_output_already_exists")
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def check(
        self, authorization_receipt_path: str | Path | None = None
    ) -> BehavioralPreflightAuthorizationCheckV1:
        if not self.current_request_path.is_file():
            raise FileNotFoundError("behavioral_preflight_request_missing")
        request_sha = _sha256_file(self.current_request_path)
        request = BehavioralPreflightAuthorizationRequestV1.model_validate_json(
            self.current_request_path.read_text(encoding="utf-8")
        )
        reasons: List[str] = []
        try:
            self._validate_request_state(request)
        except Exception as exc:
            reasons.append(f"behavioral_request_invalid:{type(exc).__name__}:{exc}")
        if authorization_receipt_path is None:
            return BehavioralPreflightAuthorizationCheckV1(
                comparison_id=request.comparison_id,
                decision="blocked" if reasons else "authorization_required",
                blocking_reasons=reasons,
                authorization_request_sha256=request_sha,
                authorized_models=sorted(
                    member.solver_model for member in request.panel_members
                ),
                notes=["No external execution occurs during authorization check."],
            )
        receipt_path = Path(authorization_receipt_path)
        receipt_sha: Optional[str] = None
        try:
            receipt_sha = _sha256_file(receipt_path)
            receipt = BehavioralPreflightAuthorizationReceiptV1.model_validate_json(
                receipt_path.read_text(encoding="utf-8")
            )
            self._validate_receipt(request, request_sha, receipt)
        except Exception as exc:
            reasons.append(f"behavioral_receipt_invalid:{type(exc).__name__}:{exc}")
        return BehavioralPreflightAuthorizationCheckV1(
            comparison_id=request.comparison_id,
            decision="blocked" if reasons else "ready",
            blocking_reasons=reasons,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=receipt_sha,
            authorized_models=sorted(
                member.solver_model for member in request.panel_members
            ),
            notes=[
                "Ready authorizes only the frozen file-tool preflight fixture.",
                "Task packages, business execution, graders and mutation remain excluded.",
            ],
        )

    def _load_frozen_state(self) -> tuple[dict, dict, dict, dict]:
        paths = [
            self.campaign_manifest_path,
            self.route_manifest_path,
            self.screening_path,
            self.staging_path,
        ]
        if any(not path.is_file() for path in paths):
            raise FileNotFoundError("behavioral_authorization_evidence_missing")
        return tuple(
            json.loads(path.read_text(encoding="utf-8")) for path in paths
        )  # type: ignore[return-value]

    def _validate_request_state(
        self, request: BehavioralPreflightAuthorizationRequestV1
    ) -> None:
        campaign, route_manifest, screening, staging = self._load_frozen_state()
        parity_path = Path(request.container_parity_report_path)
        checks = {
            "comparison_id": request.comparison_id == campaign.get("comparison_id"),
            "campaign_manifest": request.campaign_manifest_sha256
            == _sha256_file(self.campaign_manifest_path),
            "route_manifest": request.route_comparison_manifest_sha256
            == _sha256_file(self.route_manifest_path),
            "screening": request.provider_screening_report_sha256
            == _sha256_file(self.screening_path),
            "staging": request.route_blind_staging_report_sha256
            == _sha256_file(self.staging_path),
            "environment": request.environment_contract_id
            == route_manifest.get("environment_contract_id"),
            "campaign_status": campaign.get("status") == "evaluation_ready",
            "screening_decision": screening.get("decision")
            == "proceed_to_behavioral_evaluation",
            "staging_decision": staging.get("decision") == "pass",
            "container_parity_file": parity_path.is_file(),
            "container_parity_sha": parity_path.is_file()
            and request.container_parity_report_sha256
            == _sha256_file(parity_path),
        }
        if parity_path.is_file():
            parity = json.loads(parity_path.read_text(encoding="utf-8"))
            checks.update(
                {
                    "container_parity_pass": parity.get("passed") is True,
                    "container_network": parity.get("network_mode") == "none",
                    "container_read_only": parity.get("read_only_root") is True,
                    "container_credentials": parity.get(
                        "provider_credentials_mounted"
                    )
                    is False,
                    "container_cleanup": parity.get("cleanup_returncode") == 0,
                    "behavioral_code_fingerprint": parity.get(
                        "source_fingerprint"
                    )
                    == request.behavioral_code_fingerprint,
                }
            )
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(
                "behavioral_request_frozen_state_mismatch:" + ",".join(failed)
            )

    def _validate_replacement_request_state(
        self, request: BehavioralPreflightAuthorizationRequestV3
    ) -> None:
        from task_generator.v3_behavioral_preflight_evidence import (
            BehavioralEvidenceIntegrityReportV1,
        )
        from task_generator.v3_evaluation_calibration import FrozenSolverPanelV1
        from task_generator.v3_behavioral_validation import SolverToolPreflightReportV1
        from task_generator.v3_solver_panel_admission import (
            SolverPanelAdmissionPlanV1,
            SolverPanelReplacementBoundaryV1,
        )

        campaign, route_manifest, screening, staging = self._load_frozen_state()
        evidence_paths = {
            "admission": Path(request.admission_plan_path).resolve(),
            "boundary": Path(request.replacement_boundary_path).resolve(),
            "panel": Path(request.retained_frozen_panel_path).resolve(),
            "integrity": Path(request.retained_evidence_integrity_path).resolve(),
            "parity": Path(request.container_parity_report_path).resolve(),
        }
        expected_hashes = {
            "admission": request.admission_plan_sha256,
            "boundary": request.replacement_boundary_sha256,
            "panel": request.retained_frozen_panel_sha256,
            "integrity": request.retained_evidence_integrity_sha256,
            "parity": request.container_parity_report_sha256,
        }
        checks = {
            "comparison_id": request.comparison_id == campaign.get("comparison_id"),
            "campaign_manifest": request.campaign_manifest_sha256
            == _sha256_file(self.campaign_manifest_path),
            "route_manifest": request.route_comparison_manifest_sha256
            == _sha256_file(self.route_manifest_path),
            "screening": request.provider_screening_report_sha256
            == _sha256_file(self.screening_path),
            "staging": request.route_blind_staging_report_sha256
            == _sha256_file(self.staging_path),
            "environment": request.environment_contract_id
            == route_manifest.get("environment_contract_id"),
            "campaign_status": campaign.get("status") == "evaluation_ready",
            "screening_decision": screening.get("decision")
            == "proceed_to_behavioral_evaluation",
            "staging_decision": staging.get("decision") == "pass",
        }
        for label, path in evidence_paths.items():
            if label != "parity":
                try:
                    self._require_inside_campaign(path)
                    inside = True
                except ValueError:
                    inside = False
                checks[f"{label}_inside_campaign"] = inside
            checks[f"{label}_file"] = path.is_file()
            checks[f"{label}_sha"] = (
                path.is_file() and _sha256_file(path) == expected_hashes[label]
            )
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(
                "behavioral_replacement_frozen_state_mismatch:" + ",".join(failed)
            )

        admission = SolverPanelAdmissionPlanV1.model_validate_json(
            evidence_paths["admission"].read_text(encoding="utf-8")
        )
        boundary = SolverPanelReplacementBoundaryV1.model_validate_json(
            evidence_paths["boundary"].read_text(encoding="utf-8")
        )
        panel = FrozenSolverPanelV1.model_validate_json(
            evidence_paths["panel"].read_text(encoding="utf-8")
        )
        integrity = BehavioralEvidenceIntegrityReportV1.model_validate_json(
            evidence_paths["integrity"].read_text(encoding="utf-8")
        )
        parity = json.loads(evidence_paths["parity"].read_text(encoding="utf-8"))
        if (
            admission.decision != "retain_passing_replace_failed"
            or boundary.admission_plan_sha256 != request.admission_plan_sha256
            or admission.frozen_panel_sha256 != request.retained_frozen_panel_sha256
            or admission.evidence_integrity_sha256
            != request.retained_evidence_integrity_sha256
            or integrity.decision != "pass"
        ):
            raise ValueError("behavioral_replacement_governance_chain_mismatch")
        slot_strata = {item.stratum for item in boundary.slots}
        if {item.stratum for item in request.panel_members} != slot_strata:
            raise ValueError("behavioral_replacement_slot_scope_mismatch")
        candidate_models = {item.solver_model.lower() for item in request.panel_members}
        if candidate_models & {item.lower() for item in boundary.prohibited_models}:
            raise ValueError("behavioral_replacement_prohibited_model")
        if len(request.panel_members) > boundary.maximum_external_models:
            raise ValueError("behavioral_replacement_model_ceiling_exceeded")
        retained_by_model = {item.solver_model: item for item in request.retained_evidence}
        if set(retained_by_model) != set(boundary.retained_models):
            raise ValueError("behavioral_replacement_retained_scope_mismatch")
        panel_by_model = {item.solver_model: item for item in panel.members}
        integrity_by_model = {item.solver_model: item for item in integrity.records}
        for model, evidence in retained_by_model.items():
            report_path = Path(evidence.preflight_report_path).resolve()
            self._require_inside_campaign(report_path)
            member = panel_by_model.get(model)
            record = integrity_by_model.get(model)
            if (
                member is None
                or record is None
                or record.decision != "pass"
                or member.stratum != evidence.stratum
                or member.preflight_report_path != evidence.preflight_report_path
                or not report_path.is_file()
                or _sha256_file(report_path) != evidence.preflight_report_sha256
                or SolverToolPreflightReportV1.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                )
                != member.preflight_report
                or member.preflight_report.status != "pass"
                or not member.preflight_report.eligible_for_business_eval
            ):
                raise ValueError("behavioral_replacement_retained_evidence_invalid")
        parity_checks = {
            "passed": parity.get("passed") is True,
            "returncode": parity.get("returncode") == 0,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "external_model": parity.get("external_model_execution_authorized") is False,
            "fingerprint": parity.get("source_fingerprint")
            == request.behavioral_code_fingerprint,
        }
        parity_failed = sorted(
            name for name, passed in parity_checks.items() if not passed
        )
        if parity_failed:
            raise ValueError(
                "behavioral_replacement_container_parity_invalid:"
                + ",".join(parity_failed)
            )

    def _validate_agent_protocol_probe_request_state(
        self, request: BehavioralAgentProtocolProbeAuthorizationRequestV1
    ) -> None:
        campaign, route_manifest, screening, staging = self._load_frozen_state()
        parity_path = Path(request.container_parity_report_path).resolve()
        checks = {
            "comparison_id": request.comparison_id == campaign.get("comparison_id"),
            "campaign_manifest": request.campaign_manifest_sha256
            == _sha256_file(self.campaign_manifest_path),
            "route_manifest": request.route_comparison_manifest_sha256
            == _sha256_file(self.route_manifest_path),
            "screening": request.provider_screening_report_sha256
            == _sha256_file(self.screening_path),
            "staging": request.route_blind_staging_report_sha256
            == _sha256_file(self.staging_path),
            "environment": request.environment_contract_id
            == route_manifest.get("environment_contract_id"),
            "campaign_status": campaign.get("status") == "evaluation_ready",
            "screening_decision": screening.get("decision")
            == "proceed_to_behavioral_evaluation",
            "staging_decision": staging.get("decision") == "pass",
            "parity_file": parity_path.is_file(),
            "parity_sha": parity_path.is_file()
            and _sha256_file(parity_path) == request.container_parity_report_sha256,
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(
                "agent_protocol_probe_frozen_state_mismatch:" + ",".join(failed)
            )
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        parity_checks = {
            "passed": parity.get("passed") is True,
            "returncode": parity.get("returncode") == 0,
            "network": parity.get("network_mode") == "none",
            "read_only": parity.get("read_only_root") is True,
            "credentials": parity.get("provider_credentials_mounted") is False,
            "cleanup": parity.get("cleanup_returncode") == 0,
            "external_model": parity.get("external_model_execution_authorized") is False,
            "fingerprint": parity.get("source_fingerprint")
            == request.behavioral_code_fingerprint,
        }
        parity_failed = sorted(
            name for name, passed in parity_checks.items() if not passed
        )
        if parity_failed:
            raise ValueError(
                "agent_protocol_probe_container_parity_invalid:"
                + ",".join(parity_failed)
            )

    @staticmethod
    def _validate_agent_protocol_probe_receipt(
        request: BehavioralAgentProtocolProbeAuthorizationRequestV1,
        request_sha: str,
        receipt: BehavioralAgentProtocolProbeAuthorizationReceiptV1,
    ) -> None:
        expected_budget_sha = _sha256_json(
            [request.solver_execution_budget.model_dump(mode="json")]
        )
        pairs = [
            (receipt.authorization_request_sha256, request_sha),
            (receipt.comparison_id, request.comparison_id),
            (receipt.authorized_models, [request.panel_member.solver_model]),
            (receipt.environment_contract_id, request.environment_contract_id),
            (receipt.maximum_total_cost_usd, request.maximum_total_cost_usd),
            (receipt.campaign_manifest_sha256, request.campaign_manifest_sha256),
            (receipt.route_comparison_manifest_sha256, request.route_comparison_manifest_sha256),
            (receipt.provider_screening_report_sha256, request.provider_screening_report_sha256),
            (receipt.route_blind_staging_report_sha256, request.route_blind_staging_report_sha256),
            (receipt.container_parity_report_sha256, request.container_parity_report_sha256),
            (receipt.behavioral_code_fingerprint, request.behavioral_code_fingerprint),
            (receipt.solver_execution_budget_sha256, expected_budget_sha),
        ]
        if any(actual != expected for actual, expected in pairs):
            raise ValueError("agent_protocol_probe_receipt_scope_mismatch")
        if receipt.expires_at:
            expires = datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
            if expires <= datetime.now(timezone.utc):
                raise PermissionError("behavioral_receipt_expired")

    def _validate_replacement_receipt(
        self,
        request: BehavioralPreflightAuthorizationRequestV3,
        request_sha: str,
        receipt: BehavioralPreflightAuthorizationReceiptV3,
    ) -> None:
        if receipt.authorization_request_sha256 != request_sha:
            raise ValueError("behavioral_receipt_request_mismatch")
        if receipt.comparison_id != request.comparison_id:
            raise ValueError("behavioral_receipt_comparison_mismatch")
        if set(receipt.authorized_models) != {
            item.solver_model for item in request.panel_members
        }:
            raise ValueError("behavioral_receipt_model_scope_mismatch")
        expected_budget_sha = _sha256_json(
            [item.model_dump(mode="json") for item in request.solver_execution_budgets]
        )
        scalar_pairs = [
            (receipt.environment_contract_id, request.environment_contract_id),
            (receipt.maximum_total_cost_usd, request.maximum_total_cost_usd),
            (receipt.campaign_manifest_sha256, request.campaign_manifest_sha256),
            (receipt.route_comparison_manifest_sha256, request.route_comparison_manifest_sha256),
            (receipt.provider_screening_report_sha256, request.provider_screening_report_sha256),
            (receipt.route_blind_staging_report_sha256, request.route_blind_staging_report_sha256),
            (receipt.container_parity_report_sha256, request.container_parity_report_sha256),
            (receipt.behavioral_code_fingerprint, request.behavioral_code_fingerprint),
            (receipt.solver_execution_budget_sha256, expected_budget_sha),
            (receipt.admission_plan_sha256, request.admission_plan_sha256),
            (receipt.replacement_boundary_sha256, request.replacement_boundary_sha256),
            (receipt.retained_frozen_panel_sha256, request.retained_frozen_panel_sha256),
            (receipt.retained_evidence_integrity_sha256, request.retained_evidence_integrity_sha256),
        ]
        if any(actual != expected for actual, expected in scalar_pairs):
            raise ValueError("behavioral_receipt_frozen_scope_mismatch")
        if receipt.expires_at:
            expires = datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
            if expires <= datetime.now(timezone.utc):
                raise PermissionError("behavioral_receipt_expired")

    def _require_inside_campaign(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("behavioral_authorization_evidence_outside_campaign") from exc

    @staticmethod
    def _validate_receipt(
        request: BehavioralPreflightAuthorizationRequestV1,
        request_sha: str,
        receipt: BehavioralPreflightAuthorizationReceiptV1,
    ) -> None:
        if receipt.authorization_request_sha256 != request_sha:
            raise ValueError("behavioral_receipt_request_mismatch")
        if receipt.comparison_id != request.comparison_id:
            raise ValueError("behavioral_receipt_comparison_mismatch")
        if set(receipt.authorized_models) != {
            member.solver_model for member in request.panel_members
        }:
            raise ValueError("behavioral_receipt_model_scope_mismatch")
        scalar_pairs = [
            (receipt.environment_contract_id, request.environment_contract_id),
            (receipt.maximum_total_cost_usd, request.maximum_total_cost_usd),
            (receipt.campaign_manifest_sha256, request.campaign_manifest_sha256),
            (
                receipt.route_comparison_manifest_sha256,
                request.route_comparison_manifest_sha256,
            ),
            (
                receipt.provider_screening_report_sha256,
                request.provider_screening_report_sha256,
            ),
            (
                receipt.route_blind_staging_report_sha256,
                request.route_blind_staging_report_sha256,
            ),
            (
                receipt.container_parity_report_sha256,
                request.container_parity_report_sha256,
            ),
            (
                receipt.behavioral_code_fingerprint,
                request.behavioral_code_fingerprint,
            ),
        ]
        if any(actual != expected for actual, expected in scalar_pairs):
            raise ValueError("behavioral_receipt_frozen_scope_mismatch")
        if receipt.expires_at:
            expires = datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
            if expires <= datetime.now(timezone.utc):
                raise PermissionError("behavioral_receipt_expired")
