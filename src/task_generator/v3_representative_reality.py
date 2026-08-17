from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_external_model_policy import enforce_external_model_policy
from task_generator.v3_representative_production_pilot import (
    RepresentativePilotPackageReadinessV1,
    _sha_file,
    _tree_sha,
    _write_json,
)
from task_generator.v3_route_comparison import RouteBlindPackageStager
from task_generator.v3_rubric_recalibration_campaign import (
    RubricRecalibrationCampaign,
)
from task_generator.v3_rubric_scoring_audit import RubricScoringAuthorityAuditor
from task_generator.v3_semantic_review_executor import SemanticReviewExecutor
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_source_fingerprint import governed_source_fingerprint
from task_generator.v3_validity_utility import (
    CandidateBlindRealityReviewV2,
    RealityReviewCallEvidenceV2,
    RubricFocusRealityReviewV4,
    RubricScoringAuthorityAuditV1,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_safe(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Freeze the exact JSON-safe payload sent to the provider."""
    return json.loads(
        json.dumps(payload, ensure_ascii=False, default=str)
    )


class RepresentativeRealityCaseScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    package_fingerprint: str
    candidate_tree_sha256: str
    rubric_input_sha256: str
    scoring_audit_path: str
    scoring_audit_sha256: str
    scoring_semantic_signature: str


class RepresentativeRealityScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_version: Literal["v3.representative_reality_scope.1"] = (
        "v3.representative_reality_scope.1"
    )
    cohort_id: str
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    package_readiness_path: str
    package_readiness_sha256: str
    blind_staging_report_path: str
    blind_staging_report_sha256: str
    parity_report_path: str
    parity_report_sha256: str
    source_fingerprint: str
    maximum_provider_calls: Literal[96] = 96
    maximum_attempts_per_stage: Literal[2] = 2
    maximum_input_tokens_per_call: Literal[24000] = 24000
    maximum_completion_tokens_per_call: Literal[4000] = 4000
    provider_sdk_retries: Literal[0] = 0
    external_upload_authorized: Literal[True] = True
    expert_review_claim_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    standing_authorization_basis: str = Field(min_length=24)
    cases: List[RepresentativeRealityCaseScopeV1] = Field(
        min_length=24, max_length=24
    )

    @model_validator(mode="after")
    def validate_cases(self) -> "RepresentativeRealityScopeV1":
        if len({item.case_id for item in self.cases}) != 24:
            raise ValueError("representative_reality_case_id_duplicate")
        if len({item.package_fingerprint for item in self.cases}) != 24:
            raise ValueError("representative_reality_package_duplicate")
        return self


class RepresentativeRealityCaseResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    candidate_review: CandidateBlindRealityReviewV2
    rubric_review: RubricFocusRealityReviewV4
    call_evidence: List[RealityReviewCallEvidenceV2] = Field(
        min_length=2, max_length=2
    )
    scoring_semantic_signature: str
    overall_decision: Literal["pass", "revise", "blocked"]

    @model_validator(mode="after")
    def validate_case_result(self) -> "RepresentativeRealityCaseResultV1":
        if (
            self.candidate_review.case_id != self.case_id
            or self.rubric_review.case_id != self.case_id
        ):
            raise ValueError("representative_reality_case_id_mismatch")
        if [item.stage for item in self.call_evidence] != [
            "candidate_blind",
            "rubric_focus",
        ]:
            raise ValueError("representative_reality_call_order_invalid")
        decisions = [
            item.decision for item in self.candidate_review.dimensions
        ] + [self.rubric_review.decision]
        expected = (
            "blocked"
            if "blocked" in decisions
            else "revise"
            if "revise" in decisions
            else "pass"
        )
        if self.overall_decision != expected:
            raise ValueError("representative_reality_case_decision_mismatch")
        return self


class RepresentativeRealityResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["v3.representative_reality_result.1"] = (
        "v3.representative_reality_result.1"
    )
    cohort_id: str
    reviewer_kind: Literal["llm_proxy"] = "llm_proxy"
    professional_validity: Literal[
        "provisional_ai_assumed_sufficient_for_pilot"
    ] = "provisional_ai_assumed_sufficient_for_pilot"
    cases: List[RepresentativeRealityCaseResultV1]
    reviewer_inconsistency_signatures: List[str] = Field(default_factory=list)
    decision: Literal[
        "screening_ready",
        "revise_before_screening",
        "redesign_required",
        "incomplete",
    ]
    screening_eligible: bool
    training_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_result(self) -> "RepresentativeRealityResultV1":
        complete = len(self.cases) == 24 and len(
            {item.case_id for item in self.cases}
        ) == 24
        if not complete:
            expected = "incomplete"
        elif self.reviewer_inconsistency_signatures:
            expected = "incomplete"
        else:
            decisions = {item.overall_decision for item in self.cases}
            expected = (
                "redesign_required"
                if "blocked" in decisions
                else "revise_before_screening"
                if "revise" in decisions
                else "screening_ready"
            )
        if self.decision != expected:
            raise ValueError("representative_reality_result_decision_mismatch")
        if self.screening_eligible != (expected == "screening_ready"):
            raise ValueError(
                "representative_reality_screening_eligibility_mismatch"
            )
        return self


class RepresentativeRealityExecutionManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.representative_reality_execution.1"] = (
        "v3.representative_reality_execution.1"
    )
    cohort_id: str
    scope_sha256: str
    status: Literal["running", "completed", "incomplete"]
    provider_calls_made: int = Field(default=0, ge=0, le=96)
    controlled_retries_used: int = Field(default=0, ge=0, le=48)
    completed_candidate_stages: int = Field(default=0, ge=0, le=24)
    completed_rubric_stages: int = Field(default=0, ge=0, le=24)
    first_failure: Optional[str] = None
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: str
    updated_at: str


class RepresentativeRealityCampaign:
    RETRY_CODES = {
        "transport_timeout",
        "transport_http_408",
        "transport_http_429",
        "transport_http_5xx",
        "empty_content",
        "truncated_output",
        "invalid_json",
        "schema_contract_failure",
    }

    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.governance = self.root / "governance" / "reality"
        self.scope_path = self.governance / "scope.json"
        self.staging_root = self.root / "reality" / "blind_staging"

    def compile_scope(
        self,
        *,
        package_readiness_path: str | Path,
        parity_report_path: str | Path,
        repository_root: str | Path,
    ) -> RepresentativeRealityScopeV1:
        if self.scope_path.exists() or self.staging_root.exists():
            raise FileExistsError("representative_reality_scope_exists")
        readiness_path = Path(package_readiness_path).resolve()
        readiness = RepresentativePilotPackageReadinessV1.model_validate_json(
            readiness_path.read_text(encoding="utf-8")
        )
        if readiness.decision != "packages_ready" or len(readiness.packages) != 24:
            raise ValueError("representative_reality_requires_24_ready_packages")
        parity_path = Path(parity_report_path).resolve()
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
        source_fingerprint = governed_source_fingerprint(repository_root)
        if not (
            parity.get("passed") is True
            and parity.get("network_mode") == "none"
            and parity.get("read_only_root") is True
            and parity.get("provider_credentials_mounted") is False
            and parity.get("cleanup_returncode") == 0
            and parity.get("source_fingerprint") == source_fingerprint
        ):
            raise ValueError("representative_reality_parity_invalid")
        assignments = [
            SimpleNamespace(
                blind_task_id=item.blind_task_id,
                brief_id=item.brief_id,
                route_id=item.route_id,
                package_root=item.package_root,
            )
            for item in readiness.packages
        ]
        for item in readiness.packages:
            if _tree_sha(Path(item.package_root)) != item.package_fingerprint:
                raise ValueError("representative_reality_package_drift")
        staging = RouteBlindPackageStager().stage(
            SimpleNamespace(
                comparison_id=readiness.campaign_id,
                assignments=assignments,
            ),
            self.staging_root,
        )
        if staging.decision != "pass" or staging.package_count != 24:
            raise ValueError("representative_reality_blind_staging_failed")
        staging_path = (
            self.staging_root / "governance" / "route_blind_staging_report.json"
        )
        audit_root = self.governance / "rubric_audits"
        cases: List[RepresentativeRealityCaseScopeV1] = []
        for item in sorted(readiness.packages, key=lambda value: value.blind_task_id):
            package_root = Path(item.package_root)
            teacher = package_root / "teacher"
            audit = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=teacher / "rubric_plan_v2.json",
                rubric_binding_plan_path=teacher / "rubric_binding_plan.json",
                case_id=item.blind_task_id,
            )
            if audit.decision != "pass":
                raise ValueError("representative_reality_rubric_audit_blocked")
            audit_path = audit_root / f"{item.blind_task_id}.json"
            _write_json(audit_path, audit.model_dump(mode="json"))
            candidate_root = (
                self.staging_root / "candidate_packages" / item.blind_task_id
            )
            cases.append(
                RepresentativeRealityCaseScopeV1(
                    case_id=item.blind_task_id,
                    package_fingerprint=item.package_fingerprint,
                    candidate_tree_sha256=_tree_sha(candidate_root),
                    rubric_input_sha256=_json_sha(
                        [
                            _sha_file(teacher / "rubric_plan_v2.json"),
                            _sha_file(teacher / "rubric_binding_plan.json"),
                        ]
                    ),
                    scoring_audit_path=str(audit_path.resolve()),
                    scoring_audit_sha256=_sha_file(audit_path),
                    scoring_semantic_signature=audit.scoring_semantic_signature,
                )
            )
        scope = RepresentativeRealityScopeV1(
            cohort_id=readiness.campaign_id,
            package_readiness_path=str(readiness_path),
            package_readiness_sha256=_sha_file(readiness_path),
            blind_staging_report_path=str(staging_path.resolve()),
            blind_staging_report_sha256=_sha_file(staging_path),
            parity_report_path=str(parity_path),
            parity_report_sha256=_sha_file(parity_path),
            source_fingerprint=source_fingerprint,
            standing_authorization_basis=(
                "The user authorized unrestricted project-scoped external model "
                "calls and private task-package uploads in this conversation."
            ),
            cases=cases,
        )
        _write_json(self.scope_path, scope.model_dump(mode="json"))
        return scope

    def execute(
        self,
        *,
        provider_config: ProviderConfig,
        output_root: str | Path,
        repository_root: str | Path,
    ) -> RepresentativeRealityExecutionManifestV1:
        scope = self._validate_scope(repository_root)
        enforce_external_model_policy(
            provider_config.provider_name, provider_config.model
        )
        if (
            provider_config.provider_name != scope.provider
            or provider_config.model != scope.model
        ):
            raise PermissionError("representative_reality_provider_mismatch")
        destination = Path(output_root).resolve()
        manifest_path = destination / "execution_manifest.json"
        if manifest_path.exists():
            raise PermissionError("representative_reality_scope_consumed")
        manifest = RepresentativeRealityExecutionManifestV1(
            cohort_id=scope.cohort_id,
            scope_sha256=_sha_file(self.scope_path),
            status="running",
            created_at=_now(),
            updated_at=_now(),
        )
        _write_json(manifest_path, manifest.model_dump(mode="json"))
        reviewer = SemanticReviewExecutor(
            provider_config,
            max_tokens=scope.maximum_completion_tokens_per_call,
            input_token_hard_limit=scope.maximum_input_tokens_per_call,
            max_retries=0,
        )
        candidate: Dict[
            str, tuple[CandidateBlindRealityReviewV2, RealityReviewCallEvidenceV2]
        ] = {}
        rubric: Dict[
            str, tuple[RubricFocusRealityReviewV4, RealityReviewCallEvidenceV2]
        ] = {}
        try:
            for stage in ("candidate_blind", "rubric_focus_v4_compact"):
                for case in scope.cases:
                    payload = (
                        self._candidate_payload(case.case_id, reviewer)
                        if stage == "candidate_blind"
                        else self._rubric_payload(case)
                    )
                    parsed, evidence = self._call_stage(
                        reviewer=reviewer,
                        scope=scope,
                        case=case,
                        stage=stage,
                        payload=payload,
                        destination=destination,
                        manifest=manifest,
                        manifest_path=manifest_path,
                    )
                    if stage == "candidate_blind":
                        candidate[case.case_id] = (parsed, evidence)
                        manifest.completed_candidate_stages += 1
                    else:
                        rubric[case.case_id] = (parsed, evidence)
                        manifest.completed_rubric_stages += 1
                    manifest.updated_at = _now()
                    _write_json(manifest_path, manifest.model_dump(mode="json"))
            result = self._aggregate(scope, candidate, rubric)
            result_path = destination / "reality_result.json"
            _write_json(result_path, result.model_dump(mode="json"))
            manifest.status = (
                "completed" if result.decision != "incomplete" else "incomplete"
            )
            manifest.result_path = str(result_path.resolve())
            manifest.result_sha256 = _sha_file(result_path)
        except Exception as exc:
            manifest.status = "incomplete"
            manifest.first_failure = f"{type(exc).__name__}:{str(exc)[:300]}"
        manifest.updated_at = _now()
        _write_json(manifest_path, manifest.model_dump(mode="json"))
        return manifest

    def _call_stage(
        self,
        *,
        reviewer: SemanticReviewExecutor,
        scope: RepresentativeRealityScopeV1,
        case: RepresentativeRealityCaseScopeV1,
        stage: str,
        payload: Dict[str, Any],
        destination: Path,
        manifest: RepresentativeRealityExecutionManifestV1,
        manifest_path: Path,
    ):
        first_failure_sha = None
        feedback = None
        payload = _json_safe(payload)
        for attempt in (1, 2):
            if manifest.provider_calls_made >= scope.maximum_provider_calls:
                raise RuntimeError("representative_reality_call_ceiling")
            call_root = (
                destination
                / "calls"
                / f"{manifest.provider_calls_made + 1:03d}_{case.case_id}_{stage}_attempt_{attempt}"
            )
            _write_json(call_root / "input.json", payload)
            reviewer.last_diagnostics = {}
            reviewer.last_raw_response_content = ""
            try:
                parsed = (
                    reviewer.review_reality_candidate_blind(
                        payload, format_feedback=feedback
                    )
                    if stage == "candidate_blind"
                    else reviewer.review_reality_rubric_focus_v4(
                        payload, format_feedback=feedback
                    )
                )
                if stage != "candidate_blind":
                    audit = RubricScoringAuthorityAuditV1.model_validate_json(
                        Path(case.scoring_audit_path).read_text(encoding="utf-8")
                    )
                    RubricRecalibrationCampaign._validate_review_against_audit(
                        parsed, audit
                    )
            except Exception as exc:
                manifest.provider_calls_made += 1
                diagnostics = dict(reviewer.last_diagnostics)
                failure_code = getattr(exc, "failure_code", "provider_failure")
                diagnostics.update(
                    {
                        "attempt": attempt,
                        "failure_type": type(exc).__name__,
                        "failure_message": str(exc)[:300],
                        "failure_code": failure_code,
                        "retry_eligible": bool(
                            getattr(exc, "retry_eligible", False)
                        ),
                    }
                )
                (call_root / "raw_response.json").write_text(
                    reviewer.last_raw_response_content,
                    encoding="utf-8",
                )
                _write_json(call_root / "diagnostics.json", diagnostics)
                if first_failure_sha is None:
                    first_failure_sha = _tree_sha(call_root)
                    feedback = f"{failure_code}:{type(exc).__name__}"
                manifest.updated_at = _now()
                _write_json(manifest_path, manifest.model_dump(mode="json"))
                if (
                    attempt == 1
                    and diagnostics["retry_eligible"]
                    and failure_code in self.RETRY_CODES
                ):
                    manifest.controlled_retries_used += 1
                    continue
                raise
            manifest.provider_calls_made += 1
            (call_root / "raw_response.json").write_text(
                reviewer.last_raw_response_content,
                encoding="utf-8",
            )
            _write_json(
                call_root / "parsed_review.json", parsed.model_dump(mode="json")
            )
            _write_json(call_root / "diagnostics.json", reviewer.last_diagnostics)
            evidence = RealityReviewCallEvidenceV2(
                stage=(
                    "candidate_blind"
                    if stage == "candidate_blind"
                    else "rubric_focus"
                ),
                attempt_count=2 if first_failure_sha else 1,
                first_attempt_failure_sha256=first_failure_sha,
                input_sha256=_sha_file(call_root / "input.json"),
                raw_output_sha256=_sha_file(call_root / "raw_response.json"),
                parsed_output_sha256=_sha_file(call_root / "parsed_review.json"),
                prompt_tokens=int(
                    reviewer.last_diagnostics.get("prompt_tokens") or 0
                ),
                completion_tokens=int(
                    reviewer.last_diagnostics.get("completion_tokens") or 0
                ),
                duration_seconds=float(
                    reviewer.last_diagnostics.get("duration_seconds") or 0
                ),
            )
            return parsed, evidence
        raise RuntimeError("representative_reality_stage_incomplete")

    def _candidate_payload(
        self, case_id: str, reviewer: SemanticReviewExecutor
    ) -> Dict[str, Any]:
        root = self.staging_root / "candidate_packages" / case_id
        return {
            "case_id": case_id,
            "dataset_row": json.loads(
                (root / "dataset_row.json").read_text(encoding="utf-8")
            ),
            "deliverable_contract": json.loads(
                (root / "deliverable_contract.json").read_text(encoding="utf-8")
            ),
            "reference_contents": [
                reviewer._reference_content(path)
                for path in sorted((root / "reference_files").glob("*"))
            ],
        }

    def _rubric_payload(
        self, case: RepresentativeRealityCaseScopeV1
    ) -> Dict[str, Any]:
        readiness = RepresentativePilotPackageReadinessV1.model_validate_json(
            Path(
                RepresentativeRealityScopeV1.model_validate_json(
                    self.scope_path.read_text(encoding="utf-8")
                ).package_readiness_path
            ).read_text(encoding="utf-8")
        )
        package = next(
            item for item in readiness.packages if item.blind_task_id == case.case_id
        )
        teacher = Path(package.package_root) / "teacher"
        audit = json.loads(
            Path(case.scoring_audit_path).read_text(encoding="utf-8")
        )
        compact_audit = {
            key: audit[key]
            for key in (
                "audit_version",
                "case_id",
                "final_scoring_criterion_ids",
                "final_scoring_criteria_count",
                "annotation_binding_ids",
                "annotation_bindings_count",
                "annotation_bindings_non_scoring",
                "structure_signature",
                "scoring_semantic_signature",
                "duplicate_criterion_ids",
                "duplicate_failure_signals",
                "duplicate_observable_behaviors",
                "weight_sum_valid",
                "criterion_count_valid",
                "rubric_metadata_valid",
                "binding_authority_valid",
                "decision",
                "blocking_reasons",
            )
        }
        compact_audit["shared_evidence_pairs"] = [
            {
                "criterion_a": item["criterion_a"],
                "criterion_b": item["criterion_b"],
            }
            for item in audit["pair_audits"]
            if item["shared_evidence_or_judgment_ids"]
        ]
        blind = self.staging_root / "candidate_packages" / case.case_id
        return {
            "case_id": case.case_id,
            "candidate_requirements": json.loads(
                (blind / "deliverable_contract.json").read_text(encoding="utf-8")
            ),
            "rubric_plan": json.loads(
                (teacher / "rubric_plan_v2.json").read_text(encoding="utf-8")
            ),
            "rubric_binding_plan": json.loads(
                (teacher / "rubric_binding_plan.json").read_text(encoding="utf-8")
            ),
            "scoring_authority_audit": compact_audit,
        }

    def _aggregate(self, scope, candidate, rubric):
        cases = []
        signatures: Dict[str, set[tuple]] = {}
        for case in scope.cases:
            candidate_review, candidate_evidence = candidate[case.case_id]
            rubric_review, rubric_evidence = rubric[case.case_id]
            decisions = [
                item.decision for item in candidate_review.dimensions
            ] + [rubric_review.decision]
            overall = (
                "blocked"
                if "blocked" in decisions
                else "revise"
                if "revise" in decisions
                else "pass"
            )
            cases.append(
                RepresentativeRealityCaseResultV1(
                    case_id=case.case_id,
                    candidate_review=candidate_review,
                    rubric_review=rubric_review,
                    call_evidence=[candidate_evidence, rubric_evidence],
                    scoring_semantic_signature=case.scoring_semantic_signature,
                    overall_decision=overall,
                )
            )
            signatures.setdefault(case.scoring_semantic_signature, set()).add(
                (
                    rubric_review.decision,
                    tuple(
                        (
                            item.criterion_a,
                            item.criterion_b,
                            item.assessment,
                        )
                        for item in rubric_review.pair_assessments
                    ),
                )
            )
        inconsistent = sorted(
            signature for signature, values in signatures.items() if len(values) > 1
        )
        decision = (
            "incomplete"
            if inconsistent
            else "redesign_required"
            if any(item.overall_decision == "blocked" for item in cases)
            else "revise_before_screening"
            if any(item.overall_decision == "revise" for item in cases)
            else "screening_ready"
        )
        return RepresentativeRealityResultV1(
            cohort_id=scope.cohort_id,
            cases=cases,
            reviewer_inconsistency_signatures=inconsistent,
            decision=decision,
            screening_eligible=decision == "screening_ready",
        )

    def _validate_scope(
        self, repository_root: str | Path
    ) -> RepresentativeRealityScopeV1:
        scope = RepresentativeRealityScopeV1.model_validate_json(
            self.scope_path.read_text(encoding="utf-8")
        )
        if governed_source_fingerprint(repository_root) != scope.source_fingerprint:
            raise PermissionError("representative_reality_source_fingerprint_drift")
        for path, expected in (
            (scope.package_readiness_path, scope.package_readiness_sha256),
            (scope.blind_staging_report_path, scope.blind_staging_report_sha256),
            (scope.parity_report_path, scope.parity_report_sha256),
        ):
            if _sha_file(Path(path)) != expected:
                raise PermissionError("representative_reality_scope_input_drift")
        readiness = RepresentativePilotPackageReadinessV1.model_validate_json(
            Path(scope.package_readiness_path).read_text(encoding="utf-8")
        )
        for case in scope.cases:
            package = next(
                item
                for item in readiness.packages
                if item.blind_task_id == case.case_id
            )
            package_root = Path(package.package_root)
            teacher = package_root / "teacher"
            candidate_root = (
                self.staging_root / "candidate_packages" / case.case_id
            )
            if (
                _tree_sha(package_root) != case.package_fingerprint
                or case.package_fingerprint != package.package_fingerprint
                or _tree_sha(candidate_root) != case.candidate_tree_sha256
                or _sha_file(Path(case.scoring_audit_path))
                != case.scoring_audit_sha256
                or _json_sha(
                    [
                        _sha_file(teacher / "rubric_plan_v2.json"),
                        _sha_file(teacher / "rubric_binding_plan.json"),
                    ]
                )
                != case.rubric_input_sha256
            ):
                raise PermissionError("representative_reality_case_input_drift")
        return scope
