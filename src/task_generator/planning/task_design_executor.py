from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from task_generator.substrate.skill_extractor import ProviderConfig
from task_generator.core.provider_deadline import run_provider_exchange
from task_generator.core.external_model_policy import enforce_external_model_policy
from task_generator.planning.task_design_frontend import (
    CapabilityBriefV1,
    DesignRouteId,
    TaskDesignFrontend,
    TaskDesignProposalV1,
)
from task_generator.planning.task_design_normalizer import (
    TaskDesignProposalNormalizer,
    TaskDesignSemanticDraftProposalV1,
    TaskDesignSemanticProposalV1,
)


ExecutionStatus = Literal[
    "completed",
    "proposal_blocked",
    "semantic_proposal_blocked",
    "provider_failed",
    "contract_failed",
]
ProviderFailureCategory = Literal[
    "timeout",
    "transport",
    "http_408",
    "http_429",
    "http_5xx",
    "empty_output",
    "truncated_output",
    "invalid_json",
    "other",
]


class TaskDesignExecutionRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal["v3.task_design_execution_request.1"] = (
        "v3.task_design_execution_request.1"
    )
    capability_brief_path: str
    output_dir: str
    route_id: DesignRouteId = "llm_led_hybrid"
    model: str = "gpt-5.6-sol"
    allow_external_provider: bool = False
    allow_expensive_model: bool = False
    timeout_seconds: int = Field(default=900, ge=30, le=3600)
    max_tokens: int = Field(default=16000, ge=1000, le=24000)
    input_token_hard_limit: int = Field(default=30000, ge=2000, le=60000)
    overwrite_completed: bool = False
    repair_from_execution_report_path: Optional[str] = None


class TaskDesignProviderDiagnosticsV1(BaseModel):
    diagnostics_version: Literal["v3.task_design_provider_diagnostics.1"] = (
        "v3.task_design_provider_diagnostics.1"
    )
    provider: str
    model: str
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    duration_seconds: float = 0.0
    response_char_count: int = 0
    response_sha256: Optional[str] = None
    raw_response_included: Literal[False] = False


class TaskDesignExecutionReportV1(BaseModel):
    report_version: Literal["v3.task_design_execution.1"] = "v3.task_design_execution.1"
    status: ExecutionStatus
    request: TaskDesignExecutionRequestV1
    brief_id: Optional[str] = None
    proposal_id: Optional[str] = None
    proposal_interface_mode: Optional[
        Literal["strict_v2", "semantic_normalized_v1"]
    ] = None
    semantic_proposal_path: Optional[str] = None
    normalization_report_path: Optional[str] = None
    proposal_path: Optional[str] = None
    validation_report_path: Optional[str] = None
    binding_report_path: Optional[str] = None
    design_authority_report_path: Optional[str] = None
    provider_diagnostics_path: Optional[str] = None
    materialization_triggered: Literal[False] = False
    registry_mutation_triggered: Literal[False] = False
    promotion_triggered: Literal[False] = False
    failure_type: Optional[str] = None
    provider_failure_category: Optional[ProviderFailureCategory] = None
    contract_validation_findings: list[Dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TaskDesignRepairReadinessCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prior_execution_report_path: str
    prior_execution_report_sha256: str
    brief_id: str
    route_id: DesignRouteId
    prior_status: ExecutionStatus
    initial_prompt_sha256: str
    repair_prompt_sha256: str
    prompt_changed: bool
    repair_marker_present: bool
    prior_proposal_included: bool
    blocking_validation_finding_count: int
    authority_blocking_reason_count: int
    canonical_bound_element_id_count: int
    decision: Literal["pass", "blocked"]
    blocking_reasons: List[str] = Field(default_factory=list)


class TaskDesignRepairReadinessReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.task_design_repair_readiness.1"] = (
        "v3.task_design_repair_readiness.1"
    )
    decision: Literal["pass", "blocked"]
    case_count: int = Field(ge=1)
    passed_case_count: int = Field(ge=0)
    cases: List[TaskDesignRepairReadinessCaseV1]
    evidence_mode: Literal[
        "external_paths",
        "portable_bundle",
    ] = "external_paths"
    bundle_root: Optional[str] = None
    bundle_file_sha256: Dict[str, str] = Field(default_factory=dict)
    external_provider_calls_made: Literal[False] = False
    materialization_triggered: Literal[False] = False
    registry_mutation_triggered: Literal[False] = False
    promotion_triggered: Literal[False] = False


class TaskDesignRepairReadinessVerificationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal[
        "v3.task_design_repair_readiness_verification.1"
    ] = "v3.task_design_repair_readiness_verification.1"
    decision: Literal["pass", "blocked"]
    readiness_report_path: str
    readiness_report_sha256: str
    case_count: int = Field(ge=1)
    replayed_case_count: int = Field(ge=0)
    blocking_reasons: List[str] = Field(default_factory=list)
    external_provider_calls_made: Literal[False] = False
    materialization_triggered: Literal[False] = False
    registry_mutation_triggered: Literal[False] = False
    promotion_triggered: Literal[False] = False


class TaskDesignProposalExecutor:
    EXPENSIVE_MODEL_BLOCKLIST = {"claude-sonnet-4-6", "claude_sonnet_4_6"}

    def run(
        self,
        request: TaskDesignExecutionRequestV1,
        config: ProviderConfig,
    ) -> TaskDesignExecutionReportV1:
        enforce_external_model_policy(config.provider_name, config.model)
        if not request.allow_external_provider:
            raise PermissionError("task_design_external_provider_not_authorized")
        normalized_model = request.model.strip().lower()
        if (
            normalized_model in self.EXPENSIVE_MODEL_BLOCKLIST
            and not request.allow_expensive_model
        ):
            raise PermissionError("expensive_task_design_model_not_authorized")
        if config.model != request.model:
            raise ValueError("provider_config_model_mismatch")

        brief_path = Path(request.capability_brief_path)
        output_root = Path(request.output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        report_path = output_root / "task_design_execution_report.json"
        if report_path.exists() and not request.overwrite_completed:
            existing = TaskDesignExecutionReportV1.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
            if existing.status in {
                "completed",
                "proposal_blocked",
                "semantic_proposal_blocked",
            }:
                return existing

        brief = CapabilityBriefV1.model_validate_json(
            brief_path.read_text(encoding="utf-8")
        )
        frontend = TaskDesignFrontend()
        repair_context = self._load_repair_context(request, brief)
        prompt = frontend.compile_route_proposal_prompt(
            brief,
            request.route_id,
            repair_context=repair_context,
        )
        estimated_input_tokens = (len(prompt) + 3) // 4
        if estimated_input_tokens > request.input_token_hard_limit:
            report = self._failure_report(
                request,
                brief.brief_id,
                "contract_failed",
                "task_design_prompt_budget_exceeded",
            )
            self._atomic_json(report_path, report.model_dump(mode="json"))
            return report

        # Persist the exact submitted prompt for every provider attempt,
        # including provider/schema/normalization failures. This makes a
        # later repair provably feedback-conditioned instead of relying on
        # a prompt reconstructed after the fact.
        (output_root / "task_design_proposal_prompt.md").write_text(
            prompt,
            encoding="utf-8",
        )

        diagnostics_path = output_root / "task_design_provider_diagnostics.json"
        try:
            payload, diagnostics = self._call_provider(
                prompt=prompt,
                config=config,
                max_tokens=request.max_tokens,
                timeout_seconds=request.timeout_seconds,
            )
        except Exception as exc:
            report = self._failure_report(
                request,
                brief.brief_id,
                "provider_failed",
                type(exc).__name__,
                provider_failure_category=self._provider_failure_category(exc),
            )
            self._atomic_json(report_path, report.model_dump(mode="json"))
            return report
        self._atomic_json(
            diagnostics_path,
            diagnostics.model_dump(mode="json"),
        )
        proposal: Optional[TaskDesignProposalV1] = None
        interface_mode: Literal[
            "strict_v2", "semantic_normalized_v1"
        ] = "strict_v2"
        semantic_proposal_path: Optional[Path] = None
        normalization_report_path: Optional[Path] = None
        strict_failure: Optional[Exception] = None
        try:
            strict_proposal = TaskDesignProposalV1.model_validate(payload)
            if strict_proposal.proposal_version != "v3.task_design_proposal.2":
                raise ValueError("provider_proposal_v2_required")
            proposal = strict_proposal
        except Exception as exc:
            strict_failure = exc

        if proposal is None:
            interface_mode = "semantic_normalized_v1"
            normalizer = TaskDesignProposalNormalizer()
            proposal, normalization = normalizer.normalize_payload(
                payload,
                brief,
            )
            normalization_report_path = (
                output_root / "task_design_normalization_report.json"
            )
            self._atomic_json(
                normalization_report_path,
                normalization.model_dump(mode="json"),
            )
            if proposal is not None and normalization.decision == "pass":
                semantic_proposal = TaskDesignSemanticProposalV1.model_validate(
                    payload
                )
                semantic_proposal_path = (
                    output_root / "task_design_semantic_proposal.json"
                )
                self._atomic_json(
                    semantic_proposal_path,
                    semantic_proposal.model_dump(mode="json"),
                )
            else:
                semantic_draft: Optional[
                    TaskDesignSemanticDraftProposalV1
                ] = None
                try:
                    semantic_draft = (
                        TaskDesignSemanticDraftProposalV1.model_validate(
                            payload
                        )
                    )
                except Exception:
                    # A broadly schema-invalid response remains a contract
                    # failure and cannot consume repair authority.
                    semantic_draft = None
                if semantic_draft is not None:
                    semantic_proposal_path = (
                        output_root / "task_design_semantic_proposal.json"
                    )
                    self._atomic_json(
                        semantic_proposal_path,
                        semantic_draft.model_dump(mode="json"),
                    )
                findings = [
                    {
                        "location": item.location,
                        "type": item.finding_type,
                        "message": item.message,
                    }
                    for item in normalization.findings
                ]
                if not findings and strict_failure is not None:
                    findings = self._sanitized_contract_findings(
                        strict_failure
                    )
                for reason in normalization.blocking_reasons:
                    findings.append(
                        {
                            "location": [],
                            "type": "normalization_blocked",
                            "message": reason,
                        }
                    )
                report = self._failure_report(
                    request,
                    brief.brief_id,
                    (
                        "semantic_proposal_blocked"
                        if semantic_draft is not None
                        else "contract_failed"
                    ),
                    "TaskDesignSemanticNormalizationBlocked",
                    provider_diagnostics_path=str(diagnostics_path),
                    proposal_interface_mode=interface_mode,
                    proposal_id=(
                        semantic_draft.proposal_id
                        if semantic_draft is not None
                        else None
                    ),
                    semantic_proposal_path=(
                        str(semantic_proposal_path)
                        if semantic_proposal_path is not None
                        else None
                    ),
                    normalization_report_path=str(normalization_report_path),
                    contract_validation_findings=findings,
                )
                self._atomic_json(report_path, report.model_dump(mode="json"))
                return report

        if proposal is None:  # pragma: no cover - guarded by normalization result
            report = self._failure_report(
                request,
                brief.brief_id,
                "contract_failed",
                "task_design_proposal_missing_after_normalization",
                provider_diagnostics_path=str(diagnostics_path),
            )
            self._atomic_json(report_path, report.model_dump(mode="json"))
            return report

        proposal_path = output_root / "task_design_proposal.json"
        validation = frontend.write_frontend_artifacts(
            brief=brief,
            output_dir=output_root,
            proposal=proposal,
            route_id=request.route_id,
            compiled_prompt=prompt,
        )
        authority_report = frontend.validate_design_authority(
            brief,
            proposal,
            request.route_id,
        )
        status: ExecutionStatus = (
            "completed"
            if validation.decision == "pass"
            and authority_report.decision == "pass"
            else "proposal_blocked"
        )
        report = TaskDesignExecutionReportV1(
            status=status,
            request=request,
            brief_id=brief.brief_id,
            proposal_id=proposal.proposal_id,
            proposal_interface_mode=interface_mode,
            semantic_proposal_path=(
                str(semantic_proposal_path)
                if semantic_proposal_path is not None
                else None
            ),
            normalization_report_path=(
                str(normalization_report_path)
                if normalization_report_path is not None
                else None
            ),
            proposal_path=str(proposal_path),
            validation_report_path=str(
                output_root / "task_design_validation_report.json"
            ),
            binding_report_path=str(output_root / "source_skill_binding_report.json"),
            design_authority_report_path=str(
                output_root / "design_authority_validation_report.json"
            ),
            provider_diagnostics_path=str(diagnostics_path),
            notes=[
                "This executor is proposal-only and never invokes materialization.",
                "Raw provider response content is not persisted.",
                "A passing proposal still requires deterministic R3 materialization and downstream gates.",
            ],
        )
        self._atomic_json(report_path, report.model_dump(mode="json"))
        return report

    def replay_persisted_proposal(
        self,
        *,
        capability_brief_path: str | Path,
        proposal_path: str | Path,
        output_dir: str | Path,
        route_id: DesignRouteId,
    ) -> TaskDesignExecutionReportV1:
        """Revalidate a strict persisted proposal without any provider call."""
        brief_path = Path(capability_brief_path).resolve()
        source_proposal_path = Path(proposal_path).resolve()
        output_root = Path(output_dir).resolve()
        if output_root.exists():
            raise FileExistsError("task_design_offline_replay_output_exists")

        brief = CapabilityBriefV1.model_validate_json(
            brief_path.read_text(encoding="utf-8")
        )
        proposal = TaskDesignProposalV1.model_validate_json(
            source_proposal_path.read_text(encoding="utf-8")
        )
        if proposal.proposal_version != "v3.task_design_proposal.2":
            raise ValueError("task_design_offline_replay_requires_v2_proposal")
        if proposal.brief_id != brief.brief_id:
            raise ValueError("task_design_offline_replay_brief_id_mismatch")

        frontend = TaskDesignFrontend()
        prompt = frontend.compile_route_proposal_prompt(brief, route_id)
        validation = frontend.write_frontend_artifacts(
            brief=brief,
            output_dir=output_root,
            proposal=proposal,
            route_id=route_id,
            compiled_prompt=prompt,
        )
        authority_report = frontend.validate_design_authority(
            brief,
            proposal,
            route_id,
        )
        status: ExecutionStatus = (
            "completed"
            if validation.decision == "pass"
            and authority_report.decision == "pass"
            else "proposal_blocked"
        )
        request = TaskDesignExecutionRequestV1(
            capability_brief_path=str(brief_path),
            output_dir=str(output_root),
            route_id=route_id,
            model="offline-persisted-proposal-replay",
            allow_external_provider=False,
        )
        report = TaskDesignExecutionReportV1(
            status=status,
            request=request,
            brief_id=brief.brief_id,
            proposal_id=proposal.proposal_id,
            proposal_interface_mode="strict_v2",
            proposal_path=str(output_root / "task_design_proposal.json"),
            validation_report_path=str(
                output_root / "task_design_validation_report.json"
            ),
            binding_report_path=str(
                output_root / "source_skill_binding_report.json"
            ),
            design_authority_report_path=str(
                output_root / "design_authority_validation_report.json"
            ),
            failure_type=(
                "OfflineProposalValidationBlocked"
                if status == "proposal_blocked"
                else None
            ),
            notes=[
                "This report was compiled by deterministic offline replay of a persisted strict V2 proposal.",
                "No external provider was called and no provider diagnostics exist.",
                "Offline replay never invokes materialization, registry mutation, or promotion.",
            ],
        )
        self._atomic_json(
            output_root / "task_design_execution_report.json",
            report.model_dump(mode="json"),
        )
        return report

    def compile_repair_readiness(
        self,
        prior_execution_report_paths: List[str | Path],
        output_path: str | Path,
        portable_bundle_dir: str | Path | None = None,
    ) -> TaskDesignRepairReadinessReportV1:
        if not prior_execution_report_paths:
            raise ValueError("task_design_repair_readiness_requires_cases")
        frontend = TaskDesignFrontend()
        cases: List[TaskDesignRepairReadinessCaseV1] = []
        output = Path(output_path).resolve()
        bundle_root = (
            Path(portable_bundle_dir).resolve()
            if portable_bundle_dir is not None
            else None
        )
        if bundle_root is not None:
            if bundle_root.exists():
                raise FileExistsError(
                    "task_design_repair_bundle_root_exists"
                )
            bundle_root.mkdir(parents=True)
        for case_index, raw_path in enumerate(
            prior_execution_report_paths,
            start=1,
        ):
            source_prior_path = Path(raw_path).resolve()
            prior_path = (
                self._freeze_repair_case(
                    source_prior_path,
                    bundle_root / f"case_{case_index:02d}",
                )
                if bundle_root is not None
                else source_prior_path
            )
            prior_report = TaskDesignExecutionReportV1.model_validate_json(
                prior_path.read_text(encoding="utf-8")
            )
            brief_path = Path(
                prior_report.request.capability_brief_path
            ).resolve()
            brief = CapabilityBriefV1.model_validate_json(
                brief_path.read_text(encoding="utf-8")
            )
            repair_request = prior_report.request.model_copy(
                update={
                    "repair_from_execution_report_path": str(prior_path),
                    "allow_external_provider": False,
                    "output_dir": str(Path(output_path).resolve().parent),
                }
            )
            repair_context = self._load_repair_context(
                repair_request,
                brief,
            )
            initial_prompt = frontend.compile_route_proposal_prompt(
                brief,
                prior_report.request.route_id,
            )
            repair_prompt = frontend.compile_route_proposal_prompt(
                brief,
                prior_report.request.route_id,
                repair_context=repair_context,
            )
            blocking_reasons: List[str] = []
            if initial_prompt == repair_prompt:
                blocking_reasons.append(
                    "repair_prompt_identical_to_initial_prompt"
                )
            if "Governed repair attempt:" not in repair_prompt:
                blocking_reasons.append("repair_marker_missing")
            if not repair_context or not (
                "prior_proposal" in repair_context
                or "prior_semantic_proposal" in repair_context
            ):
                blocking_reasons.append("prior_proposal_missing")
            blocking_findings = (
                repair_context.get("blocking_validation_findings", [])
                if repair_context
                else []
            )
            authority_reasons = (
                repair_context.get("design_authority_blocking_reasons", [])
                if repair_context
                else []
            )
            canonical_ids = (
                repair_context.get(
                    "valid_bound_element_ids_from_prior_proposal",
                    [],
                )
                if repair_context
                else []
            )
            if not blocking_findings and not authority_reasons:
                blocking_reasons.append("repair_failure_feedback_missing")
            if not canonical_ids:
                blocking_reasons.append(
                    "repair_canonical_bound_element_ids_missing"
                )
            cases.append(
                TaskDesignRepairReadinessCaseV1(
                    prior_execution_report_path=str(prior_path),
                    prior_execution_report_sha256=hashlib.sha256(
                        prior_path.read_bytes()
                    ).hexdigest(),
                    brief_id=brief.brief_id,
                    route_id=prior_report.request.route_id,
                    prior_status=prior_report.status,
                    initial_prompt_sha256=hashlib.sha256(
                        initial_prompt.encode("utf-8")
                    ).hexdigest(),
                    repair_prompt_sha256=hashlib.sha256(
                        repair_prompt.encode("utf-8")
                    ).hexdigest(),
                    prompt_changed=initial_prompt != repair_prompt,
                    repair_marker_present=(
                        "Governed repair attempt:" in repair_prompt
                    ),
                    prior_proposal_included=(
                        bool(repair_context)
                        and (
                            "prior_proposal" in repair_context
                            or "prior_semantic_proposal" in repair_context
                        )
                    ),
                    blocking_validation_finding_count=len(
                        blocking_findings
                    ),
                    authority_blocking_reason_count=len(authority_reasons),
                    canonical_bound_element_id_count=len(canonical_ids),
                    decision=(
                        "pass" if not blocking_reasons else "blocked"
                    ),
                    blocking_reasons=blocking_reasons,
                )
            )
        report = TaskDesignRepairReadinessReportV1(
            decision=(
                "pass"
                if all(item.decision == "pass" for item in cases)
                else "blocked"
            ),
            case_count=len(cases),
            passed_case_count=sum(
                item.decision == "pass" for item in cases
            ),
            cases=cases,
            evidence_mode=(
                "portable_bundle"
                if bundle_root is not None
                else "external_paths"
            ),
            bundle_root=(
                str(bundle_root) if bundle_root is not None else None
            ),
            bundle_file_sha256=(
                self._bundle_file_hashes(bundle_root)
                if bundle_root is not None
                else {}
            ),
        )
        self._atomic_json(
            output,
            report.model_dump(mode="json"),
        )
        return report

    @classmethod
    def _freeze_repair_case(
        cls,
        source_report_path: Path,
        case_root: Path,
    ) -> Path:
        source_report = TaskDesignExecutionReportV1.model_validate_json(
            source_report_path.read_text(encoding="utf-8")
        )
        repairable_strict = (
            source_report.status == "proposal_blocked"
            and bool(source_report.proposal_path)
        )
        repairable_semantic = (
            source_report.status == "semantic_proposal_blocked"
            and bool(source_report.semantic_proposal_path)
        )
        if not repairable_strict and not repairable_semantic:
            raise ValueError(
                "task_design_repair_bundle_requires_persisted_blocked_proposal"
            )
        case_root.mkdir(parents=True)

        brief_source = Path(
            source_report.request.capability_brief_path
        ).resolve()
        brief_target = case_root / "capability_brief.json"
        shutil.copy2(brief_source, brief_target)
        request = source_report.request.model_copy(
            update={
                "capability_brief_path": str(brief_target.resolve()),
                "output_dir": str(case_root.resolve()),
                "repair_from_execution_report_path": None,
            }
        )
        updates: Dict[str, object] = {"request": request}
        linked = {
            "semantic_proposal_path": "task_design_semantic_proposal.json",
            "normalization_report_path": "task_design_normalization_report.json",
            "proposal_path": "task_design_proposal.json",
            "validation_report_path": "task_design_validation_report.json",
            "binding_report_path": "source_skill_binding_report.json",
            "design_authority_report_path": (
                "design_authority_validation_report.json"
            ),
        }
        for field_name, filename in linked.items():
            source_value = getattr(source_report, field_name)
            if not source_value:
                continue
            source_path = Path(source_value).resolve()
            if not source_path.is_file():
                raise FileNotFoundError(
                    f"task_design_repair_bundle_dependency_missing:{field_name}"
                )
            target_path = case_root / filename
            shutil.copy2(source_path, target_path)
            updates[field_name] = str(target_path.resolve())
        updates["provider_diagnostics_path"] = None
        frozen_report = source_report.model_copy(update=updates)
        frozen_report_path = case_root / "prior_execution_report.json"
        cls._atomic_json(
            frozen_report_path,
            frozen_report.model_dump(mode="json"),
        )
        return frozen_report_path

    @staticmethod
    def _bundle_file_hashes(bundle_root: Path) -> Dict[str, str]:
        return {
            path.relative_to(bundle_root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(
                item for item in bundle_root.rglob("*") if item.is_file()
            )
        }

    def verify_repair_readiness(
        self,
        readiness_report_path: str | Path,
        output_path: str | Path | None = None,
    ) -> TaskDesignRepairReadinessVerificationV1:
        report_path = Path(readiness_report_path).resolve()
        report = TaskDesignRepairReadinessReportV1.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
        blocking_reasons: List[str] = []
        replayed_count = 0
        if report.decision != "pass":
            blocking_reasons.append("repair_readiness_decision_not_pass")
        if report.passed_case_count != report.case_count:
            blocking_reasons.append(
                "repair_readiness_passed_case_count_mismatch"
            )
        if len(report.cases) != report.case_count:
            blocking_reasons.append("repair_readiness_case_count_mismatch")
        if report.evidence_mode == "portable_bundle":
            if not report.bundle_root:
                blocking_reasons.append("repair_bundle_root_missing")
            else:
                bundle_root = Path(report.bundle_root).resolve()
                if not bundle_root.is_dir():
                    blocking_reasons.append(
                        "repair_bundle_root_not_found"
                    )
                else:
                    observed_hashes = self._bundle_file_hashes(
                        bundle_root
                    )
                    if observed_hashes != report.bundle_file_sha256:
                        blocking_reasons.append(
                            "repair_bundle_file_hashes_mismatch"
                        )
                    for case in report.cases:
                        try:
                            Path(
                                case.prior_execution_report_path
                            ).resolve().relative_to(bundle_root)
                        except ValueError:
                            blocking_reasons.append(
                                "repair_case_outside_bundle_root"
                            )
        elif report.bundle_root or report.bundle_file_sha256:
            blocking_reasons.append(
                "external_readiness_must_not_claim_bundle"
            )

        for index, expected in enumerate(report.cases):
            prefix = f"case_{index + 1}"
            prior_path = Path(
                expected.prior_execution_report_path
            ).resolve()
            if not prior_path.is_file():
                blocking_reasons.append(
                    f"{prefix}:prior_execution_report_missing"
                )
                continue
            observed_prior_sha = hashlib.sha256(
                prior_path.read_bytes()
            ).hexdigest()
            if observed_prior_sha != expected.prior_execution_report_sha256:
                blocking_reasons.append(
                    f"{prefix}:prior_execution_report_sha256_mismatch"
                )
                continue
            try:
                replay_path = (
                    Path(output_path).resolve().parent
                    / f".{prefix}_replay.json"
                    if output_path is not None
                    else report_path.parent / f".{prefix}_replay.json"
                )
                replay = self.compile_repair_readiness(
                    [prior_path],
                    replay_path,
                ).cases[0]
                replay_path.unlink(missing_ok=True)
            except Exception as exc:
                blocking_reasons.append(
                    f"{prefix}:replay_failed:{type(exc).__name__}"
                )
                continue
            replayed_count += 1
            compared_fields = [
                "brief_id",
                "route_id",
                "prior_status",
                "initial_prompt_sha256",
                "repair_prompt_sha256",
                "prompt_changed",
                "repair_marker_present",
                "prior_proposal_included",
                "blocking_validation_finding_count",
                "authority_blocking_reason_count",
                "canonical_bound_element_id_count",
                "decision",
                "blocking_reasons",
            ]
            for field_name in compared_fields:
                if getattr(replay, field_name) != getattr(
                    expected,
                    field_name,
                ):
                    blocking_reasons.append(
                        f"{prefix}:{field_name}_mismatch"
                    )
        verification = TaskDesignRepairReadinessVerificationV1(
            decision="pass" if not blocking_reasons else "blocked",
            readiness_report_path=str(report_path),
            readiness_report_sha256=hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest(),
            case_count=report.case_count,
            replayed_case_count=replayed_count,
            blocking_reasons=blocking_reasons,
        )
        if output_path is not None:
            self._atomic_json(
                Path(output_path),
                verification.model_dump(mode="json"),
            )
        return verification

    @staticmethod
    def _load_repair_context(
        request: TaskDesignExecutionRequestV1,
        brief: CapabilityBriefV1,
    ) -> Optional[Dict[str, object]]:
        if not request.repair_from_execution_report_path:
            return None
        prior_report_path = Path(request.repair_from_execution_report_path)
        if not prior_report_path.is_file():
            raise FileNotFoundError("task_design_repair_report_not_found")
        prior_report = TaskDesignExecutionReportV1.model_validate_json(
            prior_report_path.read_text(encoding="utf-8")
        )
        strict_repair = (
            prior_report.status == "proposal_blocked"
            and bool(prior_report.proposal_path)
        )
        semantic_repair = (
            prior_report.status == "semantic_proposal_blocked"
            and bool(prior_report.semantic_proposal_path)
        )
        if not strict_repair and not semantic_repair:
            raise ValueError(
                "task_design_repair_requires_persisted_blocked_proposal"
            )
        if prior_report.brief_id != brief.brief_id:
            raise ValueError("task_design_repair_brief_mismatch")
        if prior_report.request.route_id != request.route_id:
            raise ValueError("task_design_repair_route_mismatch")

        context: Dict[str, object] = {
            "repair_contract": "v3.task_design_proposal_repair.1",
            "prior_status": prior_report.status,
            "prior_failure_type": prior_report.failure_type,
            "prior_execution_report_sha256": hashlib.sha256(
                prior_report_path.read_bytes()
            ).hexdigest(),
        }
        if strict_repair and prior_report.proposal_path:
            proposal_path = Path(prior_report.proposal_path)
            proposal = TaskDesignProposalV1.model_validate_json(
                proposal_path.read_text(encoding="utf-8")
            )
            if proposal.brief_id != brief.brief_id:
                raise ValueError("task_design_repair_proposal_brief_mismatch")
            valid_bound_element_ids = sorted(
                {item.node_id for item in proposal.evidence_nodes}
                | {item.relation_id for item in proposal.evidence_relations}
                | {item.judgment_id for item in proposal.required_judgments}
                | {
                    f"deliverable:{section}"
                    for section in (
                        proposal.deliverable_intent.required_sections_or_views
                    )
                }
            )
            context["prior_proposal"] = proposal.model_dump(mode="json")
            context["valid_bound_element_ids_from_prior_proposal"] = (
                valid_bound_element_ids
            )
            context["prior_proposal_interface"] = "strict_v2"
        elif semantic_repair and prior_report.semantic_proposal_path:
            semantic_path = Path(prior_report.semantic_proposal_path)
            semantic = TaskDesignSemanticDraftProposalV1.model_validate_json(
                semantic_path.read_text(encoding="utf-8")
            )
            if semantic.brief_id != brief.brief_id:
                raise ValueError(
                    "task_design_repair_proposal_brief_mismatch"
                )
            valid_bound_element_ids = sorted(
                {item.node_id for item in semantic.evidence_nodes}
                | {
                    item.relation_id
                    for item in semantic.evidence_relations
                }
                | {
                    item.judgment_id
                    for item in semantic.required_judgments
                }
                | {
                    f"deliverable:{section}"
                    for section in (
                        semantic.deliverable_intent.required_sections_or_views
                    )
                }
            )
            context["prior_semantic_proposal"] = semantic.model_dump(
                mode="json"
            )
            context["valid_bound_element_ids_from_prior_proposal"] = (
                valid_bound_element_ids
            )
            context["prior_proposal_interface"] = (
                "semantic_normalized_v1"
            )
        if prior_report.validation_report_path:
            validation_payload = json.loads(
                Path(prior_report.validation_report_path).read_text(
                    encoding="utf-8"
                )
            )
            context["blocking_validation_findings"] = [
                item
                for item in validation_payload.get("findings", [])
                if item.get("severity") == "blocking"
                and not item.get("passed", False)
            ]
        elif semantic_repair and prior_report.normalization_report_path:
            normalization_payload = json.loads(
                Path(prior_report.normalization_report_path).read_text(
                    encoding="utf-8"
                )
            )
            normalization_findings = [
                {
                    "severity": "blocking",
                    "passed": False,
                    "location": item.get("location", []),
                    "type": item.get("finding_type", "normalization_blocked"),
                    "message": item.get("message", "invalid semantic contract"),
                }
                for item in normalization_payload.get("findings", [])
            ]
            normalization_findings.extend(
                {
                    "severity": "blocking",
                    "passed": False,
                    "location": [],
                    "type": "normalization_blocked",
                    "message": reason,
                }
                for reason in normalization_payload.get(
                    "blocking_reasons", []
                )
            )
            context["blocking_validation_findings"] = (
                normalization_findings
            )
        if prior_report.design_authority_report_path:
            authority_payload = json.loads(
                Path(prior_report.design_authority_report_path).read_text(
                    encoding="utf-8"
                )
            )
            context["design_authority_blocking_reasons"] = (
                authority_payload.get("blocking_reasons", [])
            )
        return context

    def _call_provider(
        self,
        prompt: str,
        config: ProviderConfig,
        max_tokens: int,
        timeout_seconds: int,
    ) -> tuple[Dict[str, Any], TaskDesignProviderDiagnosticsV1]:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("openai_sdk_unavailable") from exc
        schema = TaskDesignSemanticProposalV1.model_json_schema()
        started = time.monotonic()
        # The SDK timeout is an I/O timeout, rather than an end-to-end call
        # deadline, and its default retries can extend a stuck provider call.
        # Production runs on Linux, where an interval timer can interrupt the
        # blocking SDK request at the contract deadline.  Non-Linux callers
        # retain the finite SDK timeout (the server path is the governed one).
        def exchange() -> Dict[str, Any]:
            response = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=timeout_seconds,
                max_retries=0,
            ).chat.completions.create(
                model=config.model,
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return exactly one JSON object matching this schema. Do not include "
                            "Markdown or explanatory prose: "
                            + json.dumps(schema, ensure_ascii=False)
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            usage = getattr(response, "usage", None)
            return {
                "content": response.choices[0].message.content or "",
                "finish_reason": str(response.choices[0].finish_reason or ""),
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
        response_data = run_provider_exchange(exchange, timeout_seconds)
        content = response_data["content"]
        finish_reason = response_data["finish_reason"]
        diagnostics = TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason=finish_reason,
            prompt_tokens=response_data["prompt_tokens"],
            completion_tokens=response_data["completion_tokens"],
            total_tokens=response_data["total_tokens"],
            duration_seconds=round(time.monotonic() - started, 3),
            response_char_count=len(content),
            response_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
        if not content:
            raise RuntimeError("task_design_provider_empty_output")
        if finish_reason.lower() == "length":
            raise RuntimeError("task_design_provider_truncated_output")
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("task_design_provider_output_not_object")
        return payload, diagnostics

    @staticmethod
    def _failure_report(
        request: TaskDesignExecutionRequestV1,
        brief_id: str,
        status: ExecutionStatus,
        failure_type: str,
        provider_diagnostics_path: Optional[str] = None,
        proposal_id: Optional[str] = None,
        proposal_interface_mode: Optional[
            Literal["strict_v2", "semantic_normalized_v1"]
        ] = None,
        semantic_proposal_path: Optional[str] = None,
        normalization_report_path: Optional[str] = None,
        contract_validation_findings: Optional[list[Dict[str, Any]]] = None,
        provider_failure_category: Optional[ProviderFailureCategory] = None,
    ) -> TaskDesignExecutionReportV1:
        return TaskDesignExecutionReportV1(
            status=status,
            request=request,
            brief_id=brief_id,
            proposal_id=proposal_id,
            failure_type=failure_type,
            provider_failure_category=provider_failure_category,
            provider_diagnostics_path=provider_diagnostics_path,
            proposal_interface_mode=proposal_interface_mode,
            semantic_proposal_path=semantic_proposal_path,
            normalization_report_path=normalization_report_path,
            contract_validation_findings=contract_validation_findings or [],
            notes=[
                "Failure is preserved without provider fallback or synthetic success.",
                "No materialization, registry mutation, or promotion was triggered.",
            ],
        )

    @staticmethod
    def _provider_failure_category(exc: Exception) -> ProviderFailureCategory:
        text = str(exc).lower()
        status = getattr(exc, "status_code", None)
        if status == 408 or " 408" in text:
            return "http_408"
        if status == 429 or " 429" in text:
            return "http_429"
        if isinstance(status, int) and 500 <= status <= 599:
            return "http_5xx"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "connection" in text or "network" in text or "transport" in text:
            return "transport"
        if "empty_output" in text or "empty output" in text:
            return "empty_output"
        if "truncated_output" in text or "truncated output" in text:
            return "truncated_output"
        if isinstance(exc, json.JSONDecodeError):
            return "invalid_json"
        return "other"

    @staticmethod
    def _sanitized_contract_findings(exc: Exception) -> list[Dict[str, Any]]:
        """Persist schema locations and messages without provider field values."""
        if isinstance(exc, ValidationError):
            return [
                {
                    "location": [str(part) for part in error.get("loc", ())],
                    "type": str(error.get("type", "validation_error")),
                    "message": str(error.get("msg", "invalid value")),
                }
                for error in exc.errors(include_url=False, include_input=False)
            ]
        return [
            {
                "location": [],
                "type": type(exc).__name__,
                "message": str(exc)[:240],
            }
        ]

    @staticmethod
    def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
