from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_hybrid_task_materializer import HybridTaskMaterializer
from task_generator.v3_route_comparison import (
    RouteBlindPackageStager,
    RouteComparisonAnalyzer,
    RouteComparisonManifestBuilder,
    RouteComparisonManifestV1,
    RouteId,
)
from task_generator.v3_route_evidence_compiler import (
    RouteComparisonEvidenceCompiler,
    RouteComparisonEvidenceCompileReportV1,
    RouteComparisonEvidenceInputManifestV1,
    RouteTaskEvidenceInputV1,
)
from task_generator.v3_evaluation_calibration import FrozenSolverPanelV1
from task_generator.v3_formal_brief_admission import (
    FormalBriefCohortAdmissionReportV1,
)
from task_generator.v3_route_generation import StrictTemplateProposalCompiler
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_task_design_executor import (
    TaskDesignExecutionRequestV1,
    TaskDesignExecutionReportV1,
    TaskDesignProposalExecutor,
    TaskDesignRepairReadinessReportV1,
    TaskDesignRepairReadinessVerificationV1,
)
from task_generator.v3_task_design_frontend import CapabilityBriefV1
from task_generator.v3_task_design_frontend import TaskDesignProposalV1


class ActiveAuthorizationRequestMismatchError(ValueError):
    """A receipt is valid historically but does not bind the active request."""


CampaignStatus = Literal[
    "authorization_required",
    "provider_generation_ready",
    "package_generation_in_progress",
    "packages_ready",
    "evaluation_ready",
    "completed",
    "blocked",
]
AssignmentStage = Literal[
    "pending",
    "proposal_completed",
    "materialized",
    "blind_staged",
    "solver_completed",
    "grader_completed",
    "professional_review_completed",
    "blocked",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _copy_immutable(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256_file(destination) != _sha256_file(source):
            raise FileExistsError("immutable_governance_record_conflict")
        return
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)


class RouteExecutionPolicyV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: RouteId
    proposal_mode: Literal[
        "program_strict_template",
        "skill_guided_llm",
        "llm_led_hybrid",
    ]
    provider_required: bool
    design_model: Optional[str] = None
    proposal_executor: str
    materialization_backend: Literal["HybridTaskMaterializer"]
    maximum_provider_attempts_per_assignment: int = Field(ge=0, le=2)
    maximum_completion_tokens_per_attempt: int = Field(ge=0, le=24000)
    provider_cost_ceiling_per_attempt_usd: float = Field(ge=0.0)


class ComparisonExecutionPolicyV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_version: Literal["v3.route_comparison_execution_policy.1"] = (
        "v3.route_comparison_execution_policy.1"
    )
    design_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    hard_blocked_models: List[str] = Field(
        default_factory=lambda: [
            "claude-sonnet-4-6",
            "claude_sonnet_4_6",
            "gpt-5.4-pro",
        ]
    )
    routes: List[RouteExecutionPolicyV1]
    maximum_total_provider_cost_usd: float = Field(gt=0.0)
    maximum_retry_count: Literal[1] = 1
    proposal_second_attempt_mode: Literal[
        "feedback_conditioned_repair"
    ] = "feedback_conditioned_repair"
    repair_requires_prior_execution_report: Literal[True] = True
    bound_element_namespace_version: Literal[
        "v3.canonical_bound_element.1"
    ] = "v3.canonical_bound_element.1"
    provider_fallback_allowed: Literal[False] = False
    raw_provider_response_persisted: Literal[False] = False
    external_execution_authorized: Literal[False] = False
    production_release_mutation_authorized: Literal[False] = False
    canonical_registry_mutation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_routes_and_models(self) -> "ComparisonExecutionPolicyV1":
        expected = {
            "strict_template",
            "skill_guided_llm",
            "llm_led_hybrid",
        }
        route_ids = [item.route_id for item in self.routes]
        if set(route_ids) != expected or len(route_ids) != 3:
            raise ValueError("campaign_policy_requires_three_routes")
        blocked = {item.lower() for item in self.hard_blocked_models}
        for route in self.routes:
            if route.design_model and route.design_model.lower() in blocked:
                raise ValueError("campaign_policy_uses_hard_blocked_model")
            if route.provider_required and not route.design_model:
                raise ValueError("provider_route_requires_design_model")
            if not route.provider_required and route.design_model:
                raise ValueError("offline_route_must_not_define_design_model")
        worst_case = sum(
            4
            * route.maximum_provider_attempts_per_assignment
            * route.provider_cost_ceiling_per_attempt_usd
            for route in self.routes
        )
        if worst_case > self.maximum_total_provider_cost_usd:
            raise ValueError("campaign_worst_case_cost_exceeds_policy_budget")
        return self


class CampaignAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.route_comparison_authorization.1"] = (
        "v3.route_comparison_authorization.1"
    )
    comparison_id: str
    authorization_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$"
    )
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    route_comparison_manifest_sha256: str = Field(min_length=64, max_length=64)
    execution_policy_sha256: str = Field(min_length=64, max_length=64)
    source_snapshot_sha256: str = Field(min_length=64, max_length=64)
    brief_admission_report_sha256: str = Field(min_length=64, max_length=64)
    authorized_scopes: List[
        Literal[
            "provider_proposal_generation",
            "solver_execution",
            "grader_execution",
            "professional_review",
        ]
    ]
    authorized_models: List[str]
    authorized_blind_task_ids: List[str] = Field(min_length=1)
    maximum_provider_cost_usd: float = Field(gt=0.0)
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: Optional[str] = None
    release_activation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False


class CampaignAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal["v3.route_comparison_authorization_request.1"] = (
        "v3.route_comparison_authorization_request.1"
    )
    comparison_id: str
    requested_scope: Literal["provider_proposal_generation"] = (
        "provider_proposal_generation"
    )
    requested_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    requested_blind_task_ids: List[str] = Field(min_length=1)
    requested_brief_id: str
    requested_routes: List[RouteId] = Field(min_length=1)
    maximum_provider_cost_usd: float = Field(gt=0.0)
    maximum_attempts_per_assignment: int = Field(ge=1, le=2)
    second_attempt_mode: Literal["feedback_conditioned_repair"] = (
        "feedback_conditioned_repair"
    )
    repair_requires_prior_execution_report: Literal[True] = True
    bound_element_namespace_version: Literal[
        "v3.canonical_bound_element.1"
    ] = "v3.canonical_bound_element.1"
    campaign_manifest_sha256: str
    route_comparison_manifest_sha256: str
    execution_policy_sha256: str
    source_snapshot_sha256: str
    brief_admission_report_sha256: str
    repair_readiness_report_sha256: str
    repair_readiness_verification_sha256: str
    excluded_authorities: List[str] = Field(default_factory=list)
    user_action_required: str
    external_calls_made: Literal[False] = False


class CampaignStageAttemptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str
    attempt: int = Field(ge=1, le=2)
    decision: Literal["pass", "failed"]
    evidence_path: str
    evidence_sha256: str
    recorded_at: str
    failure_type: Optional[str] = None


class CampaignAssignmentRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    brief_id: str
    route_id: RouteId
    package_root: str
    stage: AssignmentStage = "pending"
    attempts: List[CampaignStageAttemptV1] = Field(default_factory=list)
    first_failure_evidence_path: Optional[str] = None
    first_failure_evidence_sha256: Optional[str] = None
    package_fingerprint: Optional[str] = None


class RouteComparisonCampaignManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_version: Literal["v3.route_comparison_campaign.1"] = (
        "v3.route_comparison_campaign.1"
    )
    comparison_id: str
    status: CampaignStatus
    created_at: str
    updated_at: str
    route_comparison_manifest_path: str
    route_comparison_manifest_sha256: str
    source_snapshot_path: str
    source_snapshot_sha256: str
    input_class: Literal["contract_only", "formal_public_source"] = "contract_only"
    brief_admission_report_path: Optional[str] = None
    brief_admission_report_sha256: Optional[str] = None
    repair_readiness_report_path: Optional[str] = None
    repair_readiness_report_sha256: Optional[str] = None
    repair_readiness_verification_path: Optional[str] = None
    repair_readiness_verification_sha256: Optional[str] = None
    frozen_brief_paths: Dict[str, str]
    frozen_brief_sha256: Dict[str, str]
    execution_policy_path: str
    execution_policy_sha256: str
    assignments: List[CampaignAssignmentRecordV1]
    authorization_receipt_path: Optional[str] = None
    authorization_receipt_sha256: Optional[str] = None
    external_provider_calls_made: bool = False
    solver_calls_made: bool = False
    grader_calls_made: bool = False
    provider_attempt_count: int = 0
    provider_cost_ceiling_reserved_usd: float = 0.0
    provider_cost_ceiling_reserved_by_authorization_usd: Dict[str, float] = (
        Field(default_factory=dict)
    )
    promotion_authorized: Literal[False] = False
    release_mutation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class CampaignPreflightReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.route_comparison_campaign_preflight.3"] = (
        "v3.route_comparison_campaign_preflight.3"
    )
    comparison_id: str
    structural_decision: Literal["pass", "blocked"]
    execution_decision: Literal["authorization_required", "ready", "blocked"]
    blocking_reasons: List[str] = Field(default_factory=list)
    assignment_count: int
    strict_template_materialized_count: int
    provider_assignment_count: int
    strict_v2_semantic_controls_pass: bool
    strict_motif_signature_count: int
    hard_blocked_models_absent: bool
    manifest_fingerprints_match: bool
    external_calls_made: bool


class ProviderScreeningRouteSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: RouteId
    assignment_count: int
    materialized_count: int
    blocked_count: int
    provider_attempt_count: int
    materialization_rate: float


class ProviderScreeningOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.provider_screening_outcome.2"] = (
        "v3.provider_screening_outcome.2"
    )
    comparison_id: str
    decision: Literal[
        "proceed_to_behavioral_evaluation",
        "awaiting_provider_completion",
        "redesign_again",
    ]
    reason_codes: List[str]
    campaign_manifest_sha256: str
    strict_control_count: int
    provider_assignment_count: int
    provider_materialized_count: int
    provider_blocked_count: int
    provider_attempt_count: int
    feedback_conditioned_retry_count: int
    unconditioned_retry_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider_duration_seconds: float
    provider_cost_ceiling_reserved_usd: float
    route_summaries: List[ProviderScreeningRouteSummaryV1]
    solver_calls_made: bool
    grader_calls_made: bool
    behavioral_evaluation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    release_mutation_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class RouteComparisonCampaign:
    MANIFEST_NAME = "campaign_manifest.json"

    def __init__(self, campaign_root: str | Path) -> None:
        self.root = Path(campaign_root)
        self.manifest_path = self.root / self.MANIFEST_NAME

    def prepare(
        self,
        *,
        comparison_id: str,
        brief_paths: List[str | Path],
        source_snapshot_path: str | Path,
        environment_contract_id: str,
        solver_preflight_contract_path: str,
        grader_calibration_contract_path: str,
        timeout_seconds: int = 1800,
        maximum_provider_cost_usd: float = 100.0,
        input_class: Literal["contract_only", "formal_public_source"] = "contract_only",
        brief_admission_report_path: str | Path | None = None,
        repair_readiness_report_path: str | Path | None = None,
    ) -> RouteComparisonCampaignManifestV1:
        if self.root.exists():
            raise FileExistsError("route_comparison_campaign_root_exists")
        if len(brief_paths) != 4:
            raise ValueError("campaign_requires_four_brief_paths")
        source_path = Path(source_snapshot_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError("campaign_source_snapshot_missing")
        briefs = [
            CapabilityBriefV1.model_validate_json(
                Path(path).read_text(encoding="utf-8")
            )
            for path in brief_paths
        ]
        brief_ids = [item.brief_id for item in briefs]
        if len(brief_ids) != len(set(brief_ids)):
            raise ValueError("campaign_brief_ids_must_be_unique")
        admission_path: Optional[Path] = None
        admission_sha256: Optional[str] = None
        repair_path: Optional[Path] = None
        repair_sha256: Optional[str] = None
        repair_verification = None
        repair_verification_path: Optional[Path] = None
        repair_verification_sha256: Optional[str] = None
        if input_class == "formal_public_source":
            if brief_admission_report_path is None:
                raise ValueError("formal_campaign_requires_brief_admission_report")
            admission_path = Path(brief_admission_report_path).resolve()
            if not admission_path.is_file():
                raise FileNotFoundError("brief_admission_report_missing")
            admission = FormalBriefCohortAdmissionReportV1.model_validate_json(
                admission_path.read_text(encoding="utf-8")
            )
            if admission.decision != "pass":
                raise ValueError("brief_admission_report_not_pass")
            if set(admission.admitted_brief_ids) != set(brief_ids):
                raise ValueError("brief_admission_identity_mismatch")
            admission_sha256 = _sha256_file(admission_path)
            if repair_readiness_report_path is None:
                raise ValueError(
                    "formal_campaign_requires_repair_readiness_report"
                )
            repair_path = Path(repair_readiness_report_path).resolve()
            if not repair_path.is_file():
                raise FileNotFoundError("repair_readiness_report_missing")
            repair_readiness = (
                TaskDesignRepairReadinessReportV1.model_validate_json(
                    repair_path.read_text(encoding="utf-8")
                )
            )
            if (
                repair_readiness.decision != "pass"
                or repair_readiness.passed_case_count
                != repair_readiness.case_count
                or repair_readiness.external_provider_calls_made
                or repair_readiness.evidence_mode != "portable_bundle"
                or not repair_readiness.bundle_root
                or not repair_readiness.bundle_file_sha256
            ):
                raise ValueError("repair_readiness_report_not_pass")
            repair_sha256 = _sha256_file(repair_path)
            repair_verification = (
                TaskDesignProposalExecutor().verify_repair_readiness(
                    repair_path,
                )
            )
            if repair_verification.decision != "pass":
                raise ValueError(
                    "repair_readiness_replay_verification_not_pass"
                )
        elif brief_admission_report_path is not None:
            raise ValueError("contract_only_campaign_cannot_claim_formal_admission")
        elif repair_readiness_report_path is not None:
            raise ValueError(
                "contract_only_campaign_cannot_claim_repair_readiness"
            )

        governance = self.root / "governance"
        frozen_brief_root = governance / "briefs"
        frozen_brief_root.mkdir(parents=True)
        if repair_verification is not None:
            repair_verification_path = (
                governance
                / "repair_readiness_verification_report.json"
            )
            _atomic_json(
                repair_verification_path,
                repair_verification.model_dump(mode="json"),
            )
            repair_verification_sha256 = _sha256_file(
                repair_verification_path
            )
        frozen_paths: Dict[str, str] = {}
        frozen_hashes: Dict[str, str] = {}
        for brief in briefs:
            path = frozen_brief_root / f"{brief.brief_id}.json"
            _atomic_json(path, brief.model_dump(mode="json"))
            frozen_paths[brief.brief_id] = str(path.resolve())
            frozen_hashes[brief.brief_id] = _sha256_file(path)

        package_roots = {
            brief.brief_id: {
                route: str(
                    (
                        self.root
                        / "route_packages"
                        / brief.brief_id
                        / route
                    ).resolve()
                )
                for route in RouteComparisonManifestBuilder.ROUTES
            }
            for brief in briefs
        }
        comparison_manifest = RouteComparisonManifestBuilder().build(
            comparison_id=comparison_id,
            briefs=briefs,
            source_snapshot_sha256=_sha256_file(source_path),
            package_roots=package_roots,
            code_fingerprint=self._code_fingerprint(),
            environment_contract_id=environment_contract_id,
            solver_preflight_contract_path=solver_preflight_contract_path,
            grader_calibration_contract_path=grader_calibration_contract_path,
            timeout_seconds=timeout_seconds,
            maximum_provider_cost_usd=maximum_provider_cost_usd,
        )
        comparison_path = governance / "route_comparison_manifest.json"
        RouteComparisonManifestBuilder.write(
            comparison_manifest,
            comparison_path,
        )
        policy = self._execution_policy(maximum_provider_cost_usd)
        policy_path = governance / "execution_policy.json"
        _atomic_json(policy_path, policy.model_dump(mode="json"))
        campaign = RouteComparisonCampaignManifestV1(
            comparison_id=comparison_id,
            status="authorization_required",
            created_at=_utc_now(),
            updated_at=_utc_now(),
            route_comparison_manifest_path=str(comparison_path.resolve()),
            route_comparison_manifest_sha256=_sha256_file(comparison_path),
            source_snapshot_path=str(source_path),
            source_snapshot_sha256=_sha256_file(source_path),
            input_class=input_class,
            brief_admission_report_path=(
                str(admission_path) if admission_path is not None else None
            ),
            brief_admission_report_sha256=admission_sha256,
            repair_readiness_report_path=(
                str(repair_path) if repair_path is not None else None
            ),
            repair_readiness_report_sha256=repair_sha256,
            repair_readiness_verification_path=(
                str(repair_verification_path.resolve())
                if repair_verification_path is not None
                else None
            ),
            repair_readiness_verification_sha256=(
                repair_verification_sha256
            ),
            frozen_brief_paths=frozen_paths,
            frozen_brief_sha256=frozen_hashes,
            execution_policy_path=str(policy_path.resolve()),
            execution_policy_sha256=_sha256_file(policy_path),
            assignments=[
                CampaignAssignmentRecordV1(
                    blind_task_id=item.blind_task_id,
                    brief_id=item.brief_id,
                    route_id=item.route_id,
                    package_root=item.package_root,
                )
                for item in comparison_manifest.assignments
            ],
            notes=[
                "Preparation freezes inputs, routes, thresholds and model policy without external calls.",
                "claude-sonnet-4-6 is hard-blocked for this campaign with no campaign override.",
                "Provider, solver and grader execution require a separate user-authored receipt.",
                (
                    "Formal public-source admission is frozen and fingerprinted."
                    if input_class == "formal_public_source"
                    else "Contract-only campaign; not eligible for formal provider execution."
                ),
            ],
        )
        self._write(campaign)
        return campaign

    def read(self) -> RouteComparisonCampaignManifestV1:
        return RouteComparisonCampaignManifestV1.model_validate_json(
            self.manifest_path.read_text(encoding="utf-8")
        )

    def materialize_strict_template_controls(
        self,
    ) -> RouteComparisonCampaignManifestV1:
        campaign = self.read()
        briefs = self._load_frozen_briefs(campaign)
        for record in campaign.assignments:
            if record.route_id != "strict_template":
                continue
            if record.stage == "materialized":
                continue
            output_root = Path(record.package_root)
            if output_root.exists():
                raise FileExistsError(
                    f"strict_template_package_root_exists:{record.brief_id}"
                )
            brief = briefs[record.brief_id]
            proposal = StrictTemplateProposalCompiler().compile(brief)
            report = HybridTaskMaterializer().materialize(
                brief,
                proposal,
                output_root,
            )
            report_path = output_root / "hybrid_materialization_report.json"
            if report.decision != "pass":
                self.record_stage_result(
                    blind_task_id=record.blind_task_id,
                    stage="strict_template_materialization",
                    decision="failed",
                    evidence_path=report_path,
                    failure_type="strict_template_materialization_blocked",
                )
                raise RuntimeError(
                    f"strict_template_materialization_blocked:{record.brief_id}"
                )
            record.stage = "materialized"
            record.package_fingerprint = self._tree_fingerprint(output_root)
            record.attempts.append(
                CampaignStageAttemptV1(
                    stage="strict_template_materialization",
                    attempt=1,
                    decision="pass",
                    evidence_path=str(report_path.resolve()),
                    evidence_sha256=_sha256_file(report_path),
                    recorded_at=_utc_now(),
                )
            )
        campaign.updated_at = _utc_now()
        self._write(campaign)
        return campaign

    def write_provider_smoke_authorization_request(
        self,
        *,
        brief_id: str,
        maximum_provider_cost_usd: float = 8.0,
    ) -> CampaignAuthorizationRequestV1:
        campaign = self.read()
        if campaign.input_class != "formal_public_source":
            raise PermissionError(
                "contract_only_campaign_authorization_request_forbidden"
            )
        provider_assignments = [
            item
            for item in campaign.assignments
            if item.brief_id == brief_id
            and item.route_id in {"skill_guided_llm", "llm_led_hybrid"}
        ]
        if len(provider_assignments) != 2:
            raise ValueError("provider_smoke_requires_exact_route_pair")
        if any(
            item.stage == "materialized" or item.package_fingerprint
            for item in provider_assignments
        ):
            raise ValueError("provider_smoke_brief_already_materialized")
        policy = ComparisonExecutionPolicyV1.model_validate_json(
            Path(campaign.execution_policy_path).read_text(encoding="utf-8")
        )
        route_policy = {
            item.route_id: item for item in policy.routes
        }
        if (
            policy.proposal_second_attempt_mode
            != "feedback_conditioned_repair"
            or not policy.repair_requires_prior_execution_report
        ):
            raise ValueError("provider_smoke_repair_policy_not_ready")
        required_reservation = sum(
            route_policy[item.route_id].provider_cost_ceiling_per_attempt_usd
            * route_policy[item.route_id].maximum_provider_attempts_per_assignment
            for item in provider_assignments
        )
        if maximum_provider_cost_usd < required_reservation:
            raise ValueError("provider_smoke_budget_below_worst_case_reservation")
        if maximum_provider_cost_usd > policy.maximum_total_provider_cost_usd:
            raise ValueError("provider_smoke_budget_exceeds_campaign_policy")
        request = CampaignAuthorizationRequestV1(
            comparison_id=campaign.comparison_id,
            requested_blind_task_ids=sorted(
                item.blind_task_id for item in provider_assignments
            ),
            requested_brief_id=brief_id,
            requested_routes=sorted(
                (item.route_id for item in provider_assignments)
            ),
            maximum_provider_cost_usd=maximum_provider_cost_usd,
            maximum_attempts_per_assignment=max(
                route_policy[item.route_id].maximum_provider_attempts_per_assignment
                for item in provider_assignments
            ),
            second_attempt_mode=policy.proposal_second_attempt_mode,
            repair_requires_prior_execution_report=(
                policy.repair_requires_prior_execution_report
            ),
            bound_element_namespace_version=(
                policy.bound_element_namespace_version
            ),
            campaign_manifest_sha256=_sha256_file(self.manifest_path),
            route_comparison_manifest_sha256=(
                campaign.route_comparison_manifest_sha256
            ),
            execution_policy_sha256=campaign.execution_policy_sha256,
            source_snapshot_sha256=campaign.source_snapshot_sha256,
            brief_admission_report_sha256=(
                campaign.brief_admission_report_sha256 or ""
            ),
            repair_readiness_report_sha256=(
                campaign.repair_readiness_report_sha256 or ""
            ),
            repair_readiness_verification_sha256=(
                campaign.repair_readiness_verification_sha256 or ""
            ),
            excluded_authorities=[
                "solver_execution",
                "grader_execution",
                "professional_review",
                "registry_mutation",
                "release_activation",
                "promotion",
            ],
            user_action_required=(
                "The user must explicitly approve this exact comparison ID, "
                "model, blind-task pair and budget before a separate executable "
                "authorization receipt may be created."
            ),
        )
        governance = self.root / "governance"
        current_request_path = (
            governance / "provider_smoke_authorization_request.json"
        )
        _atomic_json(current_request_path, request.model_dump(mode="json"))
        request_sha256 = _sha256_file(current_request_path)
        immutable_request_path = (
            governance
            / "authorization_requests"
            / f"{request_sha256}.json"
        )
        _copy_immutable(current_request_path, immutable_request_path)
        return request

    def compile_authorization_receipt(
        self,
        *,
        authorization_request_path: str | Path,
        authorization_id: str,
        authorization_statement: str,
        expires_at: str,
        output_path: str | Path,
    ) -> CampaignAuthorizationReceiptV1:
        """Compile, but do not accept or execute, an exact request-bound receipt."""
        campaign = self.read()
        if campaign.input_class != "formal_public_source":
            raise PermissionError(
                "contract_only_campaign_authorization_receipt_forbidden"
            )
        if campaign.status not in {
            "authorization_required",
            "package_generation_in_progress",
        }:
            raise PermissionError(
                "campaign_not_waiting_for_authorization_receipt"
            )
        if not self._fingerprints_match(campaign):
            raise ValueError(
                "campaign_authorization_receipt_fingerprint_mismatch"
            )

        request_path = Path(authorization_request_path).resolve()
        authorization_requests_root = (
            self.root / "governance" / "authorization_requests"
        ).resolve()
        if request_path.parent != authorization_requests_root:
            raise ValueError(
                "authorization_receipt_requires_immutable_request_path"
            )
        request_sha256 = _sha256_file(request_path)
        if request_path.name != f"{request_sha256}.json":
            raise ValueError("authorization_request_filename_hash_mismatch")
        request = CampaignAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        if request.comparison_id != campaign.comparison_id:
            raise ValueError("authorization_request_comparison_id_mismatch")
        if request.campaign_manifest_sha256 != _sha256_file(
            self.manifest_path
        ):
            raise ValueError("authorization_request_campaign_state_mismatch")

        issued_at = _utc_now()
        receipt = CampaignAuthorizationReceiptV1(
            comparison_id=campaign.comparison_id,
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha256,
            route_comparison_manifest_sha256=(
                request.route_comparison_manifest_sha256
            ),
            execution_policy_sha256=request.execution_policy_sha256,
            source_snapshot_sha256=request.source_snapshot_sha256,
            brief_admission_report_sha256=(
                request.brief_admission_report_sha256
            ),
            authorized_scopes=[request.requested_scope],
            authorized_models=[request.requested_model],
            authorized_blind_task_ids=sorted(
                request.requested_blind_task_ids
            ),
            maximum_provider_cost_usd=request.maximum_provider_cost_usd,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        policy = ComparisonExecutionPolicyV1.model_validate_json(
            Path(campaign.execution_policy_path).read_text(encoding="utf-8")
        )
        self._validate_authorization(campaign, policy, receipt)

        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError(
                "authorization_receipt_output_already_exists"
            )
        _atomic_json(destination, receipt.model_dump(mode="json"))
        return receipt

    def generate_provider_routes(
        self,
        *,
        config: ProviderConfig,
        executor: Optional[TaskDesignProposalExecutor] = None,
        blind_task_ids: Optional[List[str]] = None,
        maximum_assignments: Optional[int] = None,
    ) -> RouteComparisonCampaignManifestV1:
        campaign = self.read()
        if campaign.input_class != "formal_public_source":
            raise PermissionError(
                "contract_only_campaign_provider_generation_forbidden"
            )
        if campaign.status not in {
            "provider_generation_ready",
            "package_generation_in_progress",
        }:
            raise PermissionError(
                "campaign_provider_generation_not_authorized"
            )
        if not campaign.authorization_receipt_path:
            raise PermissionError("campaign_authorization_receipt_missing")
        receipt_path = Path(campaign.authorization_receipt_path)
        if (
            not campaign.authorization_receipt_sha256
            or not receipt_path.is_file()
            or _sha256_file(receipt_path)
            != campaign.authorization_receipt_sha256
        ):
            raise PermissionError("campaign_authorization_receipt_tampered")
        receipt = CampaignAuthorizationReceiptV1.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        policy = ComparisonExecutionPolicyV1.model_validate_json(
            Path(campaign.execution_policy_path).read_text(encoding="utf-8")
        )
        self._validate_authorization(campaign, policy, receipt)
        route_policies = {item.route_id: item for item in policy.routes}
        if config.model != policy.design_model:
            raise ValueError("campaign_provider_model_mismatch")
        if config.model.lower() in {
            item.lower() for item in policy.hard_blocked_models
        }:
            raise PermissionError("campaign_hard_blocked_model")
        proposal_executor = executor or TaskDesignProposalExecutor()
        briefs = self._load_frozen_briefs(campaign)
        selected_ids = set(blind_task_ids or [])
        authorized_ids = set(receipt.authorized_blind_task_ids)
        if not selected_ids:
            selected_ids = authorized_ids
        elif not selected_ids <= authorized_ids:
            raise PermissionError(
                "campaign_assignment_outside_authorized_scope"
            )
        if selected_ids:
            known_provider_ids = {
                item.blind_task_id
                for item in campaign.assignments
                if item.route_id != "strict_template"
            }
            unknown = sorted(selected_ids - known_provider_ids)
            if unknown:
                raise ValueError(
                    "campaign_unknown_provider_assignment:"
                    + ",".join(unknown)
                )
        if maximum_assignments is not None and maximum_assignments < 1:
            raise ValueError("campaign_maximum_assignments_must_be_positive")
        campaign.status = "package_generation_in_progress"
        campaign.updated_at = _utc_now()
        self._write(campaign)

        processed_count = 0
        for assignment in list(campaign.assignments):
            if assignment.route_id == "strict_template":
                continue
            if selected_ids and assignment.blind_task_id not in selected_ids:
                continue
            if (
                maximum_assignments is not None
                and processed_count >= maximum_assignments
            ):
                break
            if assignment.stage == "materialized":
                continue
            policy_record = route_policies[assignment.route_id]
            prior_attempts = [
                item
                for item in assignment.attempts
                if item.stage == "provider_proposal"
            ]
            if len(prior_attempts) >= (
                policy_record.maximum_provider_attempts_per_assignment
            ):
                continue
            if prior_attempts:
                prior_report = TaskDesignExecutionReportV1.model_validate_json(
                    Path(prior_attempts[-1].evidence_path).read_text(
                        encoding="utf-8"
                    )
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
                    # The governed second attempt is proposal repair, not an
                    # unconditional retry for provider or schema failures.
                    continue
            processed_count += 1
            campaign = self.read()
            authorization_reserved = (
                campaign.provider_cost_ceiling_reserved_by_authorization_usd.get(
                    receipt.authorization_id,
                    0.0,
                )
            )
            next_authorization_reserved = (
                authorization_reserved
                + policy_record.provider_cost_ceiling_per_attempt_usd
            )
            if (
                next_authorization_reserved
                > receipt.maximum_provider_cost_usd
            ):
                raise RuntimeError(
                    "campaign_authorized_provider_cost_exhausted"
                )
            next_total_reserved = (
                campaign.provider_cost_ceiling_reserved_usd
                + policy_record.provider_cost_ceiling_per_attempt_usd
            )
            if next_total_reserved > policy.maximum_total_provider_cost_usd:
                raise RuntimeError("campaign_policy_provider_cost_exhausted")
            proposal_root = (
                self.root
                / "provider_runs"
                / assignment.brief_id
                / assignment.route_id
                / f"attempt_{len(prior_attempts) + 1:02d}"
            )
            campaign.external_provider_calls_made = True
            campaign.provider_attempt_count += 1
            campaign.provider_cost_ceiling_reserved_usd = round(
                next_total_reserved,
                4,
            )
            campaign.provider_cost_ceiling_reserved_by_authorization_usd[
                receipt.authorization_id
            ] = round(next_authorization_reserved, 4)
            campaign.updated_at = _utc_now()
            self._write(campaign)
            report = proposal_executor.run(
                TaskDesignExecutionRequestV1(
                    capability_brief_path=campaign.frozen_brief_paths[
                        assignment.brief_id
                    ],
                    output_dir=str(proposal_root),
                    route_id=assignment.route_id,
                    model=policy.design_model,
                    allow_external_provider=True,
                    allow_expensive_model=False,
                    timeout_seconds=900,
                    max_tokens=(
                        policy_record.maximum_completion_tokens_per_attempt
                    ),
                    repair_from_execution_report_path=(
                        prior_attempts[-1].evidence_path
                        if prior_attempts
                        else None
                    ),
                ),
                config,
            )
            report_path = (
                proposal_root / "task_design_execution_report.json"
            )
            if report.status != "completed":
                self.record_stage_result(
                    blind_task_id=assignment.blind_task_id,
                    stage="provider_proposal",
                    decision="failed",
                    evidence_path=report_path,
                    failure_type=report.failure_type or report.status,
                )
                continue
            self.record_stage_result(
                blind_task_id=assignment.blind_task_id,
                stage="provider_proposal",
                decision="pass",
                evidence_path=report_path,
            )
            proposal = TaskDesignProposalV1.model_validate_json(
                Path(report.proposal_path or "").read_text(encoding="utf-8")
            )
            package_root = Path(assignment.package_root)
            materialization = HybridTaskMaterializer().materialize(
                briefs[assignment.brief_id],
                proposal,
                package_root,
            )
            materialization_path = (
                package_root / "hybrid_materialization_report.json"
            )
            if materialization.decision != "pass":
                self.record_stage_result(
                    blind_task_id=assignment.blind_task_id,
                    stage="hybrid_materialization",
                    decision="failed",
                    evidence_path=materialization_path,
                    failure_type="hybrid_materialization_blocked",
                )
                continue
            campaign = self.read()
            current = next(
                item
                for item in campaign.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            current.stage = "materialized"
            current.package_fingerprint = self._tree_fingerprint(
                package_root
            )
            current.attempts.append(
                CampaignStageAttemptV1(
                    stage="hybrid_materialization",
                    attempt=1,
                    decision="pass",
                    evidence_path=str(materialization_path.resolve()),
                    evidence_sha256=_sha256_file(materialization_path),
                    recorded_at=_utc_now(),
                )
            )
            campaign.updated_at = _utc_now()
            self._write(campaign)
        campaign = self.read()
        if all(item.stage == "materialized" for item in campaign.assignments):
            campaign.status = "packages_ready"
            campaign.updated_at = _utc_now()
            self._write(campaign)
        return campaign

    def write_provider_screening_outcome(
        self,
    ) -> ProviderScreeningOutcomeV1:
        campaign = self.read()
        if not self._fingerprints_match(campaign):
            raise ValueError(
                "provider_screening_frozen_input_fingerprint_mismatch"
            )
        provider_assignments = [
            item
            for item in campaign.assignments
            if item.route_id != "strict_template"
        ]
        materialized_count = sum(
            item.stage == "materialized" for item in provider_assignments
        )
        blocked_count = sum(
            item.stage == "blocked" for item in provider_assignments
        )
        pending_count = sum(
            item.stage == "pending" for item in provider_assignments
        )
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        duration_seconds = 0.0
        feedback_conditioned_retry_count = 0
        unconditioned_retry_count = 0
        binding_namespace_failure_observed = False
        binding_cardinality_failure_observed = False
        binding_causal_failure_observed = False

        for assignment in provider_assignments:
            provider_attempts = [
                item
                for item in assignment.attempts
                if item.stage == "provider_proposal"
            ]
            prompts: List[str] = []
            for attempt in provider_attempts:
                execution_path = Path(attempt.evidence_path)
                execution_payload = json.loads(
                    execution_path.read_text(encoding="utf-8")
                )
                diagnostics_path = execution_payload.get(
                    "provider_diagnostics_path"
                )
                if diagnostics_path and Path(diagnostics_path).is_file():
                    diagnostics = json.loads(
                        Path(diagnostics_path).read_text(encoding="utf-8")
                    )
                    prompt_tokens += int(
                        diagnostics.get("prompt_tokens") or 0
                    )
                    completion_tokens += int(
                        diagnostics.get("completion_tokens") or 0
                    )
                    total_tokens += int(diagnostics.get("total_tokens") or 0)
                    duration_seconds += float(
                        diagnostics.get("duration_seconds") or 0.0
                    )
                prompt_path = (
                    execution_path.parent
                    / "task_design_proposal_prompt.md"
                )
                if prompt_path.is_file():
                    prompts.append(prompt_path.read_text(encoding="utf-8"))
                validation_path = execution_payload.get(
                    "validation_report_path"
                )
                if validation_path and Path(validation_path).is_file():
                    validation = json.loads(
                        Path(validation_path).read_text(encoding="utf-8")
                    )
                    for finding in validation.get("findings", []):
                        if (
                            finding.get("check_name")
                            != "skill_causal_binding"
                            or finding.get("passed", False)
                        ):
                            continue
                        details = finding.get("details") or {}
                        if details.get("invalid_bound_element_ids_by_skill"):
                            binding_namespace_failure_observed = True
                        if details.get("duplicate_binding_skills"):
                            binding_cardinality_failure_observed = True
                        if (
                            details.get("missing_or_decorative_skill_ids")
                            or details.get("unknown_skill_ids")
                        ):
                            binding_causal_failure_observed = True
            if len(prompts) >= 2:
                if (
                    prompts[0] != prompts[1]
                    and "Governed repair attempt:" in prompts[1]
                ):
                    feedback_conditioned_retry_count += 1
                else:
                    unconditioned_retry_count += 1

        route_summaries: List[ProviderScreeningRouteSummaryV1] = []
        for route_id in [
            "strict_template",
            "skill_guided_llm",
            "llm_led_hybrid",
        ]:
            assignments = [
                item
                for item in campaign.assignments
                if item.route_id == route_id
            ]
            route_materialized = sum(
                item.stage == "materialized" for item in assignments
            )
            route_summaries.append(
                ProviderScreeningRouteSummaryV1(
                    route_id=route_id,
                    assignment_count=len(assignments),
                    materialized_count=route_materialized,
                    blocked_count=sum(
                        item.stage == "blocked" for item in assignments
                    ),
                    provider_attempt_count=sum(
                        attempt.stage == "provider_proposal"
                        for item in assignments
                        for attempt in item.attempts
                    ),
                    materialization_rate=round(
                        route_materialized / len(assignments), 4
                    )
                    if assignments
                    else 0.0,
                )
            )

        reason_codes: List[str] = []
        if pending_count:
            reason_codes.append(
                "provider_campaign_incomplete"
            )
        elif materialized_count != len(provider_assignments):
            reason_codes.append(
                "provider_package_completion_below_contract"
            )
        if not pending_count and any(
            item.route_id != "strict_template"
            and item.materialization_rate < 1.0
            for item in route_summaries
        ):
            reason_codes.append(
                "provider_route_cross_brief_instability"
            )
        if unconditioned_retry_count:
            reason_codes.append(
                "proposal_retry_not_feedback_conditioned"
            )
        if binding_namespace_failure_observed:
            reason_codes.append(
                "bound_element_reference_contract_underspecified"
            )
        if binding_cardinality_failure_observed:
            reason_codes.append(
                "skill_binding_cardinality_contract_underspecified"
            )
        if binding_causal_failure_observed:
            reason_codes.append(
                "skill_causal_binding_contract_unsatisfied"
            )
        redesign_reasons = set(reason_codes) - {"provider_campaign_incomplete"}
        if redesign_reasons:
            decision = "redesign_again"
        elif pending_count:
            decision = "awaiting_provider_completion"
        else:
            decision = "proceed_to_behavioral_evaluation"
        outcome = ProviderScreeningOutcomeV1(
            comparison_id=campaign.comparison_id,
            decision=decision,
            reason_codes=reason_codes,
            campaign_manifest_sha256=_sha256_file(self.manifest_path),
            strict_control_count=sum(
                item.route_id == "strict_template"
                and item.stage == "materialized"
                for item in campaign.assignments
            ),
            provider_assignment_count=len(provider_assignments),
            provider_materialized_count=materialized_count,
            provider_blocked_count=blocked_count,
            provider_attempt_count=sum(
                attempt.stage == "provider_proposal"
                for item in provider_assignments
                for attempt in item.attempts
            ),
            feedback_conditioned_retry_count=(
                feedback_conditioned_retry_count
            ),
            unconditioned_retry_count=unconditioned_retry_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            provider_duration_seconds=round(duration_seconds, 3),
            provider_cost_ceiling_reserved_usd=(
                campaign.provider_cost_ceiling_reserved_usd
            ),
            route_summaries=route_summaries,
            solver_calls_made=campaign.solver_calls_made,
            grader_calls_made=campaign.grader_calls_made,
            notes=[
                "This is a provider-screening decision, not a behavioral route comparison.",
                "Incomplete matched packages prohibit route-superiority claims and solver/grader execution.",
                "Observed initial provider failures are classified from persisted validation finding details; a later repair does not erase the first failure.",
            ],
        )
        _atomic_json(
            self.root / "governance" / "provider_screening_outcome.json",
            outcome.model_dump(mode="json"),
        )
        return outcome

    def preflight(
        self,
        authorization_receipt_path: str | Path | None = None,
    ) -> CampaignPreflightReportV1:
        campaign = self.read()
        reasons: List[str] = []
        fingerprints_match = self._fingerprints_match(campaign)
        if not fingerprints_match:
            reasons.append("campaign_frozen_input_fingerprint_mismatch")
        if len(campaign.assignments) != 12:
            reasons.append("campaign_assignment_count_mismatch")
        strict_count = sum(
            item.route_id == "strict_template"
            and item.stage == "materialized"
            for item in campaign.assignments
        )
        if strict_count != 4:
            reasons.append("strict_template_controls_incomplete")
        strict_v2_semantic_controls_pass = True
        strict_motif_signatures = set()
        for assignment in (
            item
            for item in campaign.assignments
            if item.route_id == "strict_template"
            and item.stage == "materialized"
        ):
            package_root = Path(assignment.package_root)
            try:
                materialization = json.loads(
                    (package_root / "hybrid_materialization_report.json").read_text(
                        encoding="utf-8"
                    )
                )
                proposal = TaskDesignProposalV1.model_validate_json(
                    (
                        package_root
                        / "governance"
                        / "task_design_proposal.json"
                    ).read_text(
                        encoding="utf-8"
                    )
                )
                node_signatures = {
                    tuple(
                        field.field_name
                        for field in node.artifact_spec.fields
                    )
                    for node in proposal.evidence_nodes
                    if node.artifact_spec is not None
                }
                if len(node_signatures) != 1:
                    raise ValueError("strict_control_node_schema_inconsistent")
                strict_motif_signatures.update(node_signatures)
                if not (
                    proposal.proposal_version == "v3.task_design_proposal.2"
                    and materialization.get("decision") == "pass"
                    and materialization.get("materialization_backend")
                    == "hybrid_semantic_artifact_v2"
                    and materialization.get("evidence_content_quality_decision")
                    == "pass"
                    and materialization.get("visual_validation_pass") is True
                    and materialization.get("validity_overall_status")
                    == "provisional"
                    and materialization.get("utility_profile_status")
                    == "provisional"
                ):
                    raise ValueError("strict_control_semantic_gate_failed")
            except Exception:
                strict_v2_semantic_controls_pass = False
        if not strict_v2_semantic_controls_pass:
            reasons.append("strict_v2_semantic_controls_failed")
        if strict_count == 4 and len(strict_motif_signatures) != 4:
            reasons.append("strict_motif_semantic_signatures_not_distinct")
        policy = ComparisonExecutionPolicyV1.model_validate_json(
            Path(campaign.execution_policy_path).read_text(encoding="utf-8")
        )
        blocked = {item.lower() for item in policy.hard_blocked_models}
        hard_blocked_absent = all(
            not route.design_model
            or route.design_model.lower() not in blocked
            for route in policy.routes
        )
        if not hard_blocked_absent:
            reasons.append("hard_blocked_model_selected")
        provider_completion_budgets = [
            route.maximum_completion_tokens_per_attempt
            for route in policy.routes
            if route.provider_required
        ]
        if any(budget < 16000 for budget in provider_completion_budgets):
            reasons.append("provider_completion_budget_below_semantic_v2_floor")
        structural = "pass" if not reasons else "blocked"

        if structural == "blocked":
            execution = "blocked"
        elif authorization_receipt_path is None:
            execution = "authorization_required"
        elif campaign.input_class != "formal_public_source":
            reasons.append("contract_only_campaign_not_executable")
            execution = "blocked"
        else:
            try:
                receipt = CampaignAuthorizationReceiptV1.model_validate_json(
                    Path(authorization_receipt_path).read_text(encoding="utf-8")
                )
                active_request_path = (
                    self.root
                    / "governance"
                    / "provider_smoke_authorization_request.json"
                )
                if active_request_path.is_file():
                    active_request_sha256 = _sha256_file(active_request_path)
                    if (
                        receipt.authorization_request_sha256
                        != active_request_sha256
                    ):
                        raise ActiveAuthorizationRequestMismatchError(
                            "authorization_receipt_active_request_mismatch"
                        )
                self._validate_authorization(campaign, policy, receipt)
            except ActiveAuthorizationRequestMismatchError:
                reasons.append(
                    "authorization_receipt_active_request_mismatch"
                )
                execution = "blocked"
            except Exception as exc:
                reasons.append(
                    f"authorization_receipt_invalid:{type(exc).__name__}"
                )
                execution = "blocked"
            else:
                supplied_receipt_path = Path(
                    authorization_receipt_path
                ).resolve()
                receipt_sha256 = _sha256_file(supplied_receipt_path)
                immutable_receipt_path = (
                    self.root
                    / "governance"
                    / "authorization_receipts"
                    / f"{receipt.authorization_id}_{receipt_sha256}.json"
                )
                _copy_immutable(
                    supplied_receipt_path,
                    immutable_receipt_path,
                )
                campaign.authorization_receipt_path = str(
                    immutable_receipt_path.resolve()
                )
                campaign.authorization_receipt_sha256 = receipt_sha256
                campaign.status = "provider_generation_ready"
                campaign.updated_at = _utc_now()
                self._write(campaign)
                execution = "ready"
        report = CampaignPreflightReportV1(
            comparison_id=campaign.comparison_id,
            structural_decision=structural,
            execution_decision=execution,
            blocking_reasons=reasons,
            assignment_count=len(campaign.assignments),
            strict_template_materialized_count=strict_count,
            provider_assignment_count=sum(
                item.route_id != "strict_template"
                for item in campaign.assignments
            ),
            strict_v2_semantic_controls_pass=(
                strict_v2_semantic_controls_pass
            ),
            strict_motif_signature_count=len(strict_motif_signatures),
            hard_blocked_models_absent=hard_blocked_absent,
            manifest_fingerprints_match=fingerprints_match,
            external_calls_made=campaign.external_provider_calls_made,
        )
        _atomic_json(
            self.root / "governance" / "campaign_preflight_report.json",
            report.model_dump(mode="json"),
        )
        return report

    def stage_route_blind_packages(
        self,
    ) -> RouteComparisonCampaignManifestV1:
        campaign = self.read()
        if campaign.status not in {"packages_ready", "evaluation_ready"}:
            raise RuntimeError("campaign_packages_not_ready_for_blind_staging")
        if campaign.status == "evaluation_ready":
            return campaign
        comparison_manifest = RouteComparisonManifestV1.model_validate_json(
            Path(campaign.route_comparison_manifest_path).read_text(
                encoding="utf-8"
            )
        )
        staging_root = self.root / "blind_staging"
        report = RouteBlindPackageStager().stage(
            comparison_manifest,
            staging_root,
        )
        if report.decision != "pass" or report.package_count != 12:
            raise RuntimeError("campaign_route_blind_staging_blocked")
        staged_by_id = {
            item.blind_task_id: item for item in report.records
        }
        for assignment in campaign.assignments:
            record = staged_by_id.get(assignment.blind_task_id)
            if record is None:
                raise RuntimeError("campaign_blind_staging_assignment_missing")
            assignment.stage = "blind_staged"
            assignment.attempts.append(
                CampaignStageAttemptV1(
                    stage="route_blind_staging",
                    attempt=1,
                    decision="pass",
                    evidence_path=str(
                        (
                            staging_root
                            / "governance"
                            / "route_blind_staging_report.json"
                        ).resolve()
                    ),
                    evidence_sha256=_sha256_file(
                        staging_root
                        / "governance"
                        / "route_blind_staging_report.json"
                    ),
                    recorded_at=_utc_now(),
                )
            )
        campaign.status = "evaluation_ready"
        campaign.updated_at = _utc_now()
        self._write(campaign)
        return campaign

    def compile_and_analyze_evidence(
        self,
        evidence_input_path: str | Path,
    ) -> RouteComparisonEvidenceCompileReportV1:
        campaign = self.read()
        if campaign.status != "evaluation_ready":
            raise RuntimeError(
                "campaign_not_ready_for_evidence_compilation"
            )
        if not self._fingerprints_match(campaign):
            raise ValueError(
                "campaign_evidence_frozen_input_fingerprint_mismatch"
            )
        input_path = Path(evidence_input_path)
        evidence_input = RouteComparisonEvidenceInputManifestV1.model_validate_json(
            input_path.read_text(encoding="utf-8")
        )
        if (
            Path(evidence_input.comparison_manifest_path).resolve()
            != Path(campaign.route_comparison_manifest_path).resolve()
        ):
            raise ValueError(
                "campaign_evidence_comparison_manifest_mismatch"
            )
        assignment_fingerprints = {
            item.blind_task_id: item.package_fingerprint
            for item in campaign.assignments
        }
        for task in evidence_input.tasks:
            if (
                not assignment_fingerprints.get(task.blind_task_id)
                or task.package_fingerprint
                != assignment_fingerprints[task.blind_task_id]
            ):
                raise ValueError(
                    "campaign_evidence_package_fingerprint_mismatch"
                )
        report = RouteComparisonEvidenceCompiler().compile(evidence_input)
        governance = self.root / "governance"
        compile_path = governance / "route_evidence_compile_report.json"
        _atomic_json(compile_path, report.model_dump(mode="json"))
        if report.decision != "pass":
            return report
        comparison = RouteComparisonManifestV1.model_validate_json(
            Path(campaign.route_comparison_manifest_path).read_text(
                encoding="utf-8"
            )
        )
        comparison_report = RouteComparisonAnalyzer().analyze(
            comparison,
            report.evidence,
        )
        comparison_report.comparison_manifest_path = str(
            Path(campaign.route_comparison_manifest_path).resolve()
        )
        comparison_report.comparison_manifest_sha256 = _sha256_file(
            Path(campaign.route_comparison_manifest_path)
        )
        comparison_report.evidence_compile_report_path = str(
            compile_path.resolve()
        )
        comparison_report.evidence_compile_report_sha256 = _sha256_file(
            compile_path
        )
        _atomic_json(
            governance / "route_comparison_report.json",
            comparison_report.model_dump(mode="json"),
        )
        campaign.status = "completed"
        campaign.updated_at = _utc_now()
        campaign.notes.append(
            "Comparison analysis completed without promotion authority."
        )
        self._write(campaign)
        return report

    def write_evidence_input_template(
        self,
        *,
        frozen_solver_panel_path: str | Path,
        grader_observations_path: str | Path,
        output_path: str | Path,
    ) -> RouteComparisonEvidenceInputManifestV1:
        campaign = self.read()
        if campaign.status != "evaluation_ready":
            raise RuntimeError(
                "campaign_not_ready_for_evidence_template"
            )
        panel_path = Path(frozen_solver_panel_path).resolve()
        panel = FrozenSolverPanelV1.model_validate_json(
            panel_path.read_text(encoding="utf-8")
        )
        if panel.decision != "pass":
            raise ValueError("evidence_template_requires_passing_panel")
        evaluation_root = self.root / "evaluation"
        template = RouteComparisonEvidenceInputManifestV1(
            comparison_manifest_path=(
                campaign.route_comparison_manifest_path
            ),
            route_blind_staging_report_path=str(
                (
                    self.root
                    / "blind_staging"
                    / "governance"
                    / "route_blind_staging_report.json"
                ).resolve()
            ),
            frozen_solver_panel_path=str(panel_path),
            grader_observations_path=str(
                Path(grader_observations_path).resolve()
            ),
            tasks=[
                RouteTaskEvidenceInputV1(
                    blind_task_id=assignment.blind_task_id,
                    package_root=assignment.package_root,
                    package_fingerprint=(
                        assignment.package_fingerprint
                        or self._tree_fingerprint(Path(assignment.package_root))
                    ),
                    behavioral_report_paths=[
                        str(
                            (
                                evaluation_root
                                / assignment.blind_task_id
                                / "behavioral"
                                / f"{member.solver_model}.json"
                            ).resolve()
                        )
                        for member in panel.members
                    ],
                    professional_review_path=str(
                        (
                            evaluation_root
                            / assignment.blind_task_id
                            / "professional_review.json"
                        ).resolve()
                    ),
                )
                for assignment in campaign.assignments
            ],
        )
        _atomic_json(
            Path(output_path),
            template.model_dump(mode="json"),
        )
        return template

    def freeze_evidence_input(
        self,
        *,
        template_path: str | Path,
        output_path: str | Path,
    ) -> RouteComparisonEvidenceInputManifestV1:
        campaign = self.read()
        if campaign.status != "evaluation_ready":
            raise RuntimeError(
                "campaign_not_ready_for_evidence_freeze"
            )
        if not self._fingerprints_match(campaign):
            raise ValueError(
                "campaign_evidence_freeze_fingerprint_mismatch"
            )
        template = RouteComparisonEvidenceInputManifestV1.model_validate_json(
            Path(template_path).read_text(encoding="utf-8")
        )
        frozen = RouteComparisonEvidenceCompiler().freeze(template)
        if (
            Path(frozen.comparison_manifest_path).resolve()
            != Path(campaign.route_comparison_manifest_path).resolve()
        ):
            raise ValueError(
                "campaign_evidence_freeze_comparison_manifest_mismatch"
            )
        assignment_fingerprints = {
            item.blind_task_id: item.package_fingerprint
            for item in campaign.assignments
        }
        for task in frozen.tasks:
            if (
                not assignment_fingerprints.get(task.blind_task_id)
                or task.package_fingerprint
                != assignment_fingerprints[task.blind_task_id]
            ):
                raise ValueError(
                    "campaign_evidence_freeze_package_fingerprint_mismatch"
                )
        _atomic_json(
            Path(output_path),
            frozen.model_dump(mode="json"),
        )
        return frozen

    def record_stage_result(
        self,
        *,
        blind_task_id: str,
        stage: str,
        decision: Literal["pass", "failed"],
        evidence_path: str | Path,
        failure_type: Optional[str] = None,
    ) -> RouteComparisonCampaignManifestV1:
        campaign = self.read()
        record = next(
            (
                item
                for item in campaign.assignments
                if item.blind_task_id == blind_task_id
            ),
            None,
        )
        if record is None:
            raise KeyError("campaign_assignment_not_found")
        evidence = Path(evidence_path)
        if not evidence.is_file():
            raise FileNotFoundError("campaign_stage_evidence_missing")
        prior = [item for item in record.attempts if item.stage == stage]
        if any(item.decision == "pass" for item in prior):
            raise RuntimeError("completed_campaign_stage_is_immutable")
        if len(prior) >= 2:
            raise RuntimeError("campaign_stage_retry_limit_reached")
        attempt = CampaignStageAttemptV1(
            stage=stage,
            attempt=len(prior) + 1,
            decision=decision,
            evidence_path=str(evidence.resolve()),
            evidence_sha256=_sha256_file(evidence),
            recorded_at=_utc_now(),
            failure_type=failure_type,
        )
        record.attempts.append(attempt)
        if decision == "failed":
            record.stage = "blocked"
            if record.first_failure_evidence_path is None:
                first_failure_root = self.root / "first_failures"
                first_failure_root.mkdir(parents=True, exist_ok=True)
                preserved = (
                    first_failure_root
                    / f"{record.blind_task_id}_{stage}{evidence.suffix}"
                )
                shutil.copy2(evidence, preserved)
                record.first_failure_evidence_path = str(preserved.resolve())
                record.first_failure_evidence_sha256 = _sha256_file(preserved)
        campaign.updated_at = _utc_now()
        self._write(campaign)
        return campaign

    def _load_frozen_briefs(
        self,
        campaign: RouteComparisonCampaignManifestV1,
    ) -> Dict[str, CapabilityBriefV1]:
        return {
            brief_id: CapabilityBriefV1.model_validate_json(
                Path(path).read_text(encoding="utf-8")
            )
            for brief_id, path in campaign.frozen_brief_paths.items()
        }

    def _fingerprints_match(
        self,
        campaign: RouteComparisonCampaignManifestV1,
    ) -> bool:
        try:
            route_manifest = RouteComparisonManifestV1.model_validate_json(
                Path(campaign.route_comparison_manifest_path).read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            return False
        if route_manifest.code_fingerprint != self._code_fingerprint():
            return False
        records = [
            (
                Path(campaign.route_comparison_manifest_path),
                campaign.route_comparison_manifest_sha256,
            ),
            (
                Path(campaign.source_snapshot_path),
                campaign.source_snapshot_sha256,
            ),
            (
                Path(campaign.execution_policy_path),
                campaign.execution_policy_sha256,
            ),
        ]
        if campaign.input_class == "formal_public_source":
            if not (
                campaign.brief_admission_report_path
                and campaign.brief_admission_report_sha256
                and campaign.repair_readiness_report_path
                and campaign.repair_readiness_report_sha256
                and campaign.repair_readiness_verification_path
                and campaign.repair_readiness_verification_sha256
            ):
                return False
            records.append(
                (
                    Path(campaign.brief_admission_report_path),
                    campaign.brief_admission_report_sha256,
                )
            )
            records.append(
                (
                    Path(campaign.repair_readiness_verification_path),
                    campaign.repair_readiness_verification_sha256,
                )
            )
            records.append(
                (
                    Path(campaign.repair_readiness_report_path),
                    campaign.repair_readiness_report_sha256,
                )
            )
        records.extend(
            (
                Path(path),
                campaign.frozen_brief_sha256[brief_id],
            )
            for brief_id, path in campaign.frozen_brief_paths.items()
        )
        if not all(
            path.is_file() and _sha256_file(path) == expected
            for path, expected in records
        ):
            return False
        if campaign.input_class == "formal_public_source":
            try:
                replay = (
                    TaskDesignProposalExecutor().verify_repair_readiness(
                        campaign.repair_readiness_report_path or ""
                    )
                )
                frozen_replay = (
                    TaskDesignRepairReadinessVerificationV1.model_validate_json(
                        Path(
                            campaign.repair_readiness_verification_path or ""
                        ).read_text(encoding="utf-8")
                    )
                )
            except Exception:
                return False
            if (
                replay.decision != "pass"
                or replay.model_dump(mode="json")
                != frozen_replay.model_dump(mode="json")
            ):
                return False
        for assignment in campaign.assignments:
            if assignment.package_fingerprint:
                package_root = Path(assignment.package_root)
                if (
                    not package_root.is_dir()
                    or self._tree_fingerprint(package_root)
                    != assignment.package_fingerprint
                ):
                    return False
            for attempt in assignment.attempts:
                evidence_path = Path(attempt.evidence_path)
                if (
                    not evidence_path.is_file()
                    or _sha256_file(evidence_path)
                    != attempt.evidence_sha256
                ):
                    return False
            if assignment.first_failure_evidence_path:
                first_failure_path = Path(
                    assignment.first_failure_evidence_path
                )
                if (
                    not assignment.first_failure_evidence_sha256
                    or not first_failure_path.is_file()
                    or _sha256_file(first_failure_path)
                    != assignment.first_failure_evidence_sha256
                ):
                    return False
        return True

    @staticmethod
    def _validate_authorization(
        campaign: RouteComparisonCampaignManifestV1,
        policy: ComparisonExecutionPolicyV1,
        receipt: CampaignAuthorizationReceiptV1,
    ) -> None:
        if receipt.comparison_id != campaign.comparison_id:
            raise ValueError("authorization_comparison_id_mismatch")
        governance_root = Path(campaign.route_comparison_manifest_path).parent
        immutable_request_path = (
            governance_root
            / "authorization_requests"
            / f"{receipt.authorization_request_sha256}.json"
        )
        legacy_request_path = (
            governance_root / "provider_smoke_authorization_request.json"
        )
        authorization_request_path = (
            immutable_request_path
            if immutable_request_path.is_file()
            else legacy_request_path
        )
        if (
            not authorization_request_path.is_file()
            or receipt.authorization_request_sha256
            != _sha256_file(authorization_request_path)
        ):
            raise ValueError("authorization_request_fingerprint_mismatch")
        authorization_request = CampaignAuthorizationRequestV1.model_validate_json(
            authorization_request_path.read_text(encoding="utf-8")
        )
        if authorization_request.comparison_id != campaign.comparison_id:
            raise ValueError("authorization_request_comparison_id_mismatch")
        if (
            authorization_request.route_comparison_manifest_sha256
            != campaign.route_comparison_manifest_sha256
            or authorization_request.execution_policy_sha256
            != campaign.execution_policy_sha256
            or authorization_request.source_snapshot_sha256
            != campaign.source_snapshot_sha256
            or authorization_request.brief_admission_report_sha256
            != campaign.brief_admission_report_sha256
            or authorization_request.repair_readiness_report_sha256
            != campaign.repair_readiness_report_sha256
            or authorization_request.repair_readiness_verification_sha256
            != campaign.repair_readiness_verification_sha256
        ):
            raise ValueError("authorization_request_frozen_input_mismatch")
        if set(receipt.authorized_blind_task_ids) != set(
            authorization_request.requested_blind_task_ids
        ):
            raise ValueError("authorization_exceeds_requested_assignments")
        if set(receipt.authorized_models) != {
            authorization_request.requested_model
        }:
            raise ValueError("authorization_exceeds_requested_models")
        if set(receipt.authorized_scopes) != {
            authorization_request.requested_scope
        }:
            raise ValueError("authorization_exceeds_requested_scopes")
        if (
            receipt.maximum_provider_cost_usd
            > authorization_request.maximum_provider_cost_usd
        ):
            raise ValueError("authorization_exceeds_requested_budget")
        if (
            receipt.route_comparison_manifest_sha256
            != campaign.route_comparison_manifest_sha256
        ):
            raise ValueError(
                "authorization_route_manifest_fingerprint_mismatch"
            )
        if receipt.execution_policy_sha256 != campaign.execution_policy_sha256:
            raise ValueError("authorization_policy_fingerprint_mismatch")
        if receipt.source_snapshot_sha256 != campaign.source_snapshot_sha256:
            raise ValueError("authorization_source_fingerprint_mismatch")
        if (
            receipt.brief_admission_report_sha256
            != campaign.brief_admission_report_sha256
        ):
            raise ValueError("authorization_admission_fingerprint_mismatch")
        if "provider_proposal_generation" not in receipt.authorized_scopes:
            raise ValueError("provider_generation_scope_missing")
        provider_assignment_ids = {
            item.blind_task_id
            for item in campaign.assignments
            if item.route_id != "strict_template"
        }
        authorized_ids = set(receipt.authorized_blind_task_ids)
        if len(authorized_ids) != len(receipt.authorized_blind_task_ids):
            raise ValueError("authorization_assignment_ids_not_unique")
        if not authorized_ids <= provider_assignment_ids:
            raise ValueError("authorization_assignment_scope_invalid")
        required_models = {
            route.design_model
            for route in policy.routes
            if route.provider_required and route.design_model
        }
        if not required_models <= set(receipt.authorized_models):
            raise ValueError("authorization_model_coverage_missing")
        blocked = {item.lower() for item in policy.hard_blocked_models}
        if any(model.lower() in blocked for model in receipt.authorized_models):
            raise ValueError("authorization_contains_hard_blocked_model")
        if (
            receipt.maximum_provider_cost_usd
            > policy.maximum_total_provider_cost_usd
        ):
            raise ValueError("authorization_cost_exceeds_frozen_policy")
        issued_at = RouteComparisonCampaign._parse_timestamp(receipt.issued_at)
        now = datetime.now(timezone.utc)
        if issued_at > now:
            raise ValueError("authorization_issued_at_in_future")
        if receipt.expires_at is not None:
            expires_at = RouteComparisonCampaign._parse_timestamp(
                receipt.expires_at
            )
            if expires_at <= issued_at:
                raise ValueError("authorization_expiry_not_after_issue")
            if expires_at <= now:
                raise ValueError("authorization_expired")

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("authorization_timestamp_requires_timezone")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _execution_policy(
        maximum_provider_cost_usd: float,
    ) -> ComparisonExecutionPolicyV1:
        return ComparisonExecutionPolicyV1(
            routes=[
                RouteExecutionPolicyV1(
                    route_id="strict_template",
                    proposal_mode="program_strict_template",
                    provider_required=False,
                    proposal_executor="StrictTemplateProposalCompiler",
                    materialization_backend="HybridTaskMaterializer",
                    maximum_provider_attempts_per_assignment=0,
                    maximum_completion_tokens_per_attempt=0,
                    provider_cost_ceiling_per_attempt_usd=0.0,
                ),
                RouteExecutionPolicyV1(
                    route_id="skill_guided_llm",
                    proposal_mode="skill_guided_llm",
                    provider_required=True,
                    design_model="gpt-5.6-sol",
                    proposal_executor="TaskDesignProposalExecutor",
                    materialization_backend="HybridTaskMaterializer",
                    maximum_provider_attempts_per_assignment=2,
                    maximum_completion_tokens_per_attempt=16000,
                    provider_cost_ceiling_per_attempt_usd=2.0,
                ),
                RouteExecutionPolicyV1(
                    route_id="llm_led_hybrid",
                    proposal_mode="llm_led_hybrid",
                    provider_required=True,
                    design_model="gpt-5.6-sol",
                    proposal_executor="TaskDesignProposalExecutor",
                    materialization_backend="HybridTaskMaterializer",
                    maximum_provider_attempts_per_assignment=2,
                    maximum_completion_tokens_per_attempt=16000,
                    provider_cost_ceiling_per_attempt_usd=2.0,
                ),
            ],
            maximum_total_provider_cost_usd=maximum_provider_cost_usd,
        )

    @staticmethod
    def _tree_fingerprint(root: Path) -> str:
        records = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            records.append(
                f"{path.relative_to(root).as_posix()}:{_sha256_file(path)}"
            )
        return hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()

    @staticmethod
    def _code_fingerprint() -> str:
        root = Path(__file__).resolve().parents[2]
        included = [
            root / "src" / "task_generator",
            root / "Test",
            root / "deploy",
            root / "pyproject.toml",
        ]
        records = []
        for item in included:
            paths = [item] if item.is_file() else item.rglob("*")
            for path in sorted(
                candidate
                for candidate in paths
                if candidate.is_file()
                and "__pycache__" not in candidate.parts
                and "v2_outputs" not in candidate.parts
            ):
                records.append(
                    f"{path.relative_to(root).as_posix()}:{_sha256_file(path)}"
                )
        return hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()

    def _write(
        self,
        campaign: RouteComparisonCampaignManifestV1,
    ) -> None:
        _atomic_json(
            self.manifest_path,
            campaign.model_dump(mode="json"),
        )
