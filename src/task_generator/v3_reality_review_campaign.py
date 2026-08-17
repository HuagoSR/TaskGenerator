from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
)
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_external_model_policy import enforce_external_model_policy
from task_generator.v3_source_fingerprint import governed_source_fingerprint
from task_generator.v3_validity_utility import (
    CandidateBlindRealityReviewV2,
    RealityCaseReviewV2,
    RealityCohortReviewV2,
    RealityReviewCallEvidenceV2,
    RubricFocusRealityReviewV2,
)

SUPERSEDED_GEMINI_CONTINUATION_SHA256 = "76c34304c2bd5dc42feb0c405a38de5507bb05a718f14d63afb662f835b3d554"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _tree_sha(root: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(file.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


class RealityReviewSelectionCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    brief_id: str
    motif: Literal["fan_in_reconciliation", "cross_check_validation", "policy_application"]
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    package_fingerprint: str = Field(min_length=64, max_length=64)


class RealityReviewSelectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.reality_cohort_selection.1"]
    cohort_id: str
    selection_status: str
    selection_rule: str
    case_count: Literal[6]
    routes: List[str]
    motifs: List[str]
    experimental_evidence_to_deliverable_excluded: Literal[True]
    cases: List[RealityReviewSelectionCaseV1]
    review_dimensions: List[str]
    reviewer_route_blinding_required: Literal[True]
    independent_reviewer_required: Literal[True]
    professional_review_executed: Literal[False]
    external_calls_made: Literal[False]
    training_admission_authorized: Literal[False]
    promotion_authorized: Literal[False]

    @model_validator(mode="after")
    def validate_selection(self) -> "RealityReviewSelectionV1":
        if len(self.cases) != 6 or len({item.case_id for item in self.cases}) != 6:
            raise ValueError("reality_review_selection_requires_six_unique_cases")
        if {item.motif for item in self.cases} != {
            "fan_in_reconciliation", "cross_check_validation", "policy_application"
        }:
            raise ValueError("reality_review_selection_motif_coverage_invalid")
        counts = {route: sum(item.route_id == route for item in self.cases) for route in self.routes}
        if counts != {"skill_guided_llm": 3, "llm_led_hybrid": 3}:
            raise ValueError("reality_review_selection_route_balance_invalid")
        return self


class RealityReviewAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal["v3.reality_review_authorization_request.1"] = "v3.reality_review_authorization_request.1"
    cohort_id: str
    requested_scope: Literal["llm_proxy_professional_review"] = "llm_proxy_professional_review"
    provider: Literal["tuzi", "deepseek"] = "deepseek"
    model: Literal["gemini-3.1-pro-preview", "deepseek-v4-pro"] = "deepseek-v4-pro"
    selected_case_ids: List[str]
    package_fingerprints: dict[str, str]
    candidate_input_tree_sha256: dict[str, str]
    rubric_input_sha256: dict[str, str]
    selection_manifest_path: str
    selection_manifest_sha256: str
    campaign_manifest_sha256: str
    blind_staging_report_sha256: str
    container_parity_report_path: str
    container_parity_report_sha256: str
    source_fingerprint: str
    request_mode: Literal["initial", "continuation"] = "initial"
    authorized_stage_keys: List[str] = Field(default_factory=list)
    prior_manifest_path: Optional[str] = None
    prior_manifest_sha256: Optional[str] = None
    prior_output_root: Optional[str] = None
    retained_call_sha256: dict[str, str] = Field(default_factory=dict)
    maximum_provider_calls: int = Field(ge=1, le=24, default=24)
    maximum_calls_per_case: Literal[2] = 2
    maximum_attempts_per_stage: Literal[1, 2] = 2
    maximum_input_tokens_per_call: Literal[12000] = 12000
    maximum_completion_tokens_per_call: Literal[4000] = 4000
    maximum_cost_per_call_usd: Literal[0.01, 1.0] = 0.01
    maximum_total_cost_usd: float = Field(gt=0.0, le=12.0, default=0.25)
    retry_eligible_failure_codes: List[str] = Field(default_factory=lambda: [
        "transport_timeout", "transport_http_408", "transport_http_429",
        "transport_http_5xx", "empty_content", "truncated_output",
        "invalid_json", "schema_contract_failure",
    ])
    provider_sdk_retries: Literal[0] = 0
    runner_retries: Literal[0] = 0
    candidate_package_upload_authorized: Literal[True] = True
    teacher_rubric_upload_authorized: Literal[True] = True
    solver_execution_authorized: Literal[False] = False
    grader_execution_authorized: Literal[False] = False
    expert_review_claim_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    external_calls_made: Literal[False] = False
    user_action_required: str = Field(min_length=24)

    @model_validator(mode="after")
    def validate_scope(self) -> "RealityReviewAuthorizationRequestV1":
        if len(self.selected_case_ids) != 6 or len(set(self.selected_case_ids)) != 6:
            raise ValueError("reality_review_request_requires_six_unique_cases")
        expected = set(self.selected_case_ids)
        if set(self.package_fingerprints) != expected or set(self.candidate_input_tree_sha256) != expected or set(self.rubric_input_sha256) != expected:
            raise ValueError("reality_review_request_case_binding_mismatch")
        all_stages = {
            f"{case_id}:{stage}"
            for stage in ("candidate_blind", "rubric_focus")
            for case_id in self.selected_case_ids
        }
        if not self.authorized_stage_keys:
            self.authorized_stage_keys = sorted(all_stages)
        if not set(self.authorized_stage_keys) <= all_stages:
            raise ValueError("reality_review_authorized_stage_invalid")
        if self.maximum_provider_calls > len(self.authorized_stage_keys) * self.maximum_attempts_per_stage:
            raise ValueError("reality_review_provider_call_ceiling_invalid")
        if self.model == "deepseek-v4-pro":
            if self.provider != "deepseek" or self.request_mode != "initial":
                raise ValueError("deepseek_reality_review_requires_fresh_initial_cohort")
            if set(self.authorized_stage_keys) != all_stages or self.retained_call_sha256:
                raise ValueError("deepseek_reality_review_cannot_mix_prior_evidence")
            if self.maximum_provider_calls != 24 or self.maximum_attempts_per_stage != 2 or self.maximum_total_cost_usd != 0.25:
                raise ValueError("deepseek_reality_review_budget_contract_mismatch")
        if self.request_mode == "continuation":
            if not all([self.prior_manifest_path, self.prior_manifest_sha256, self.prior_output_root, self.retained_call_sha256]):
                raise ValueError("reality_review_continuation_evidence_missing")
            if set(self.retained_call_sha256) | set(self.authorized_stage_keys) != all_stages:
                raise ValueError("reality_review_continuation_stage_partition_invalid")
            if set(self.retained_call_sha256) & set(self.authorized_stage_keys):
                raise ValueError("reality_review_continuation_stage_overlap")
        return self


class RealityReviewAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.reality_review_authorization_receipt.1"] = "v3.reality_review_authorization_receipt.1"
    authorization_id: str
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    cohort_id: str
    authorized_case_ids: List[str]
    authorized_model: Literal["gemini-3.1-pro-preview", "deepseek-v4-pro"]
    maximum_provider_calls: int = Field(ge=1, le=24)
    maximum_total_cost_usd: float = Field(gt=0.0, le=12.0)
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: Optional[str] = None
    solver_execution_authorized: Literal[False] = False
    grader_execution_authorized: Literal[False] = False
    expert_review_claim_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class RealityReviewCampaignManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.reality_review_campaign.1"] = "v3.reality_review_campaign.1"
    cohort_id: str
    authorization_request_sha256: str
    authorization_receipt_sha256: str
    status: Literal["running", "completed", "incomplete"]
    completed_calls: int = Field(ge=0, le=12)
    provider_calls_made: int = Field(default=0, ge=0, le=24)
    controlled_retries_used: int = Field(default=0, ge=0, le=12)
    first_attempt_failure: Optional[str] = None
    completed_case_ids: List[str] = Field(default_factory=list)
    first_failure: Optional[str] = None
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: str
    updated_at: str


class RealityReviewCampaign:
    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.governance = self.root / "governance" / "reality_review"
        self.current_request = self.governance / "authorization_request.json"
        self.immutable_requests = self.governance / "authorization_requests"

    def compile_request(self, *, selection_path: str | Path, parity_path: str | Path) -> RealityReviewAuthorizationRequestV1:
        selection_file = Path(selection_path).resolve()
        parity_file = Path(parity_path).resolve()
        selection = RealityReviewSelectionV1.model_validate_json(selection_file.read_text(encoding="utf-8"))
        parity = json.loads(parity_file.read_text(encoding="utf-8"))
        if not (parity.get("passed") is True and parity.get("network_mode") == "none" and parity.get("read_only_root") is True and parity.get("provider_credentials_mounted") is False and parity.get("cleanup_returncode") == 0):
            raise ValueError("reality_review_parity_invalid")
        source_root = Path(__file__).resolve().parents[2]
        if governed_source_fingerprint(source_root) != parity.get("source_fingerprint"):
            raise ValueError("reality_review_parity_source_fingerprint_drift")
        campaign_manifest = self.root / "campaign_manifest.json"
        staging_report = self.root / "blind_staging" / "governance" / "route_blind_staging_report.json"
        campaign = json.loads(campaign_manifest.read_text(encoding="utf-8"))
        by_id = {item["blind_task_id"]: item for item in campaign["assignments"]}
        blind_root = self.root / "blind_staging" / "candidate_packages"
        package_fingerprints: dict[str, str] = {}
        candidate_trees: dict[str, str] = {}
        rubric_hashes: dict[str, str] = {}
        for item in selection.cases:
            assignment = by_id.get(item.case_id)
            if assignment is None or assignment.get("package_fingerprint") != item.package_fingerprint:
                raise ValueError("reality_review_package_fingerprint_mismatch")
            candidate_root = blind_root / item.case_id
            if not candidate_root.is_dir():
                raise FileNotFoundError("reality_review_blind_package_missing")
            route_root = Path(assignment["package_root"])
            rubric_files = [route_root / "teacher" / "rubric_plan_v2.json", route_root / "teacher" / "rubric_binding_plan.json"]
            if not all(path.is_file() for path in rubric_files):
                raise FileNotFoundError("reality_review_rubric_input_missing")
            package_fingerprints[item.case_id] = item.package_fingerprint
            candidate_trees[item.case_id] = _tree_sha(candidate_root)
            rubric_hashes[item.case_id] = _json_sha([_sha(path) for path in rubric_files])
        request = RealityReviewAuthorizationRequestV1(
            cohort_id=selection.cohort_id,
            selected_case_ids=sorted(package_fingerprints),
            package_fingerprints=package_fingerprints,
            candidate_input_tree_sha256=candidate_trees,
            rubric_input_sha256=rubric_hashes,
            selection_manifest_path=str(selection_file),
            selection_manifest_sha256=_sha(selection_file),
            campaign_manifest_sha256=_sha(campaign_manifest),
            blind_staging_report_sha256=_sha(staging_report),
            container_parity_report_path=str(parity_file),
            container_parity_report_sha256=_sha(parity_file),
            source_fingerprint=parity["source_fingerprint"],
            user_action_required="The user must explicitly authorize this exact request SHA before up to twenty-four bounded official DeepSeek V4 Pro calls may upload the six bound packages and rubrics.",
        )
        _atomic(self.current_request, request.model_dump(mode="json"))
        request_sha = _sha(self.current_request)
        immutable = self.immutable_requests / f"{request_sha}.json"
        if immutable.exists() and _sha(immutable) != request_sha:
            raise FileExistsError("reality_review_immutable_request_collision")
        if not immutable.exists():
            _atomic(immutable, request.model_dump(mode="json"))
        return request

    def compile_receipt(self, *, request_path: str | Path, authorization_id: str, authorization_statement: str, expires_at: str, output_path: str | Path) -> RealityReviewAuthorizationReceiptV1:
        path = Path(request_path).resolve()
        request_sha = _sha(path)
        if path.parent != self.immutable_requests.resolve() or path.name != f"{request_sha}.json":
            raise ValueError("reality_review_receipt_requires_immutable_request")
        request = RealityReviewAuthorizationRequestV1.model_validate_json(path.read_text(encoding="utf-8"))
        if request_sha == SUPERSEDED_GEMINI_CONTINUATION_SHA256 or request.model != "deepseek-v4-pro":
            raise PermissionError("reality_review_request_superseded_model_change")
        self._validate_request(request)
        receipt = RealityReviewAuthorizationReceiptV1(
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            cohort_id=request.cohort_id,
            authorized_case_ids=request.selected_case_ids,
            authorized_model=request.model,
            maximum_provider_calls=request.maximum_provider_calls,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_now(),
            expires_at=expires_at,
        )
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError("reality_review_receipt_exists")
        _atomic(destination, receipt.model_dump(mode="json"))
        return receipt

    def compile_continuation_request(
        self,
        *,
        selection_path: str | Path,
        parity_path: str | Path,
        prior_manifest_path: str | Path,
    ) -> RealityReviewAuthorizationRequestV1:
        prior_path = Path(prior_manifest_path).resolve()
        prior = RealityReviewCampaignManifestV1.model_validate_json(
            prior_path.read_text(encoding="utf-8")
        )
        if prior.status != "incomplete":
            raise ValueError("reality_review_continuation_requires_incomplete_prior")
        prior_root = prior_path.parent
        retained: dict[str, str] = {}
        for parsed_path in sorted((prior_root / "calls").glob("*/parsed_review.json")):
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            case_id = parsed.get("case_id")
            version = parsed.get("review_version", "")
            stage = (
                "candidate_blind"
                if version == "v3.candidate_blind_reality_review.2"
                else "rubric_focus"
                if version == "v3.rubric_focus_reality_review.2"
                else None
            )
            call_root = parsed_path.parent
            if not case_id or stage is None or not all(
                (call_root / name).is_file()
                for name in ("input.json", "raw_response.json", "diagnostics.json")
            ):
                raise ValueError("reality_review_retained_call_incomplete")
            retained[f"{case_id}:{stage}"] = _tree_sha(call_root)
        if not retained:
            raise ValueError("reality_review_continuation_has_no_retained_calls")
        base = self.compile_request(
            selection_path=selection_path,
            parity_path=parity_path,
        )
        all_stages = {
            f"{case_id}:{stage}"
            for stage in ("candidate_blind", "rubric_focus")
            for case_id in base.selected_case_ids
        }
        pending = sorted(all_stages - set(retained))
        payload = base.model_dump(mode="json")
        payload.update(
            {
                "request_mode": "continuation",
                "authorized_stage_keys": pending,
                "prior_manifest_path": str(prior_path),
                "prior_manifest_sha256": _sha(prior_path),
                "prior_output_root": str(prior_root),
                "retained_call_sha256": retained,
                "maximum_provider_calls": len(pending),
                "maximum_total_cost_usd": float(len(pending)),
                "external_calls_made": False,
                "user_action_required": (
                    "The user must explicitly authorize this exact continuation "
                    "request SHA before the remaining Gemini review stages may run; "
                    "retained successful calls cannot be repeated."
                ),
            }
        )
        request = RealityReviewAuthorizationRequestV1.model_validate(payload)
        _atomic(self.current_request, request.model_dump(mode="json"))
        request_sha = _sha(self.current_request)
        immutable = self.immutable_requests / f"{request_sha}.json"
        if not immutable.exists():
            _atomic(immutable, request.model_dump(mode="json"))
        return request

    def execute(self, *, receipt_path: str | Path, provider_config: ProviderConfig, output_root: str | Path) -> RealityReviewCampaignManifestV1:
        request = RealityReviewAuthorizationRequestV1.model_validate_json(self.current_request.read_text(encoding="utf-8"))
        request_sha = _sha(self.current_request)
        if request_sha == SUPERSEDED_GEMINI_CONTINUATION_SHA256 or request.model != "deepseek-v4-pro":
            raise PermissionError("reality_review_request_superseded_model_change")
        receipt_file = Path(receipt_path).resolve()
        receipt = RealityReviewAuthorizationReceiptV1.model_validate_json(receipt_file.read_text(encoding="utf-8"))
        self._validate_request(request)
        self._validate_receipt(request, request_sha, receipt)
        enforce_external_model_policy(provider_config.provider_name, provider_config.model)
        if provider_config.provider_name != request.provider or provider_config.model != request.model:
            raise PermissionError("reality_review_provider_scope_mismatch")
        destination = Path(output_root).resolve()
        manifest_path = destination / "campaign_manifest.json"
        if manifest_path.exists():
            raise PermissionError("reality_review_receipt_already_consumed")
        manifest = RealityReviewCampaignManifestV1(
            cohort_id=request.cohort_id,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=_sha(receipt_file),
            status="running",
            completed_calls=0,
            created_at=_now(), updated_at=_now(),
        )
        _atomic(manifest_path, manifest.model_dump(mode="json"))
        try:
            cases = self._execute_calls(request, provider_config, destination, manifest, manifest_path)
            result = RealityCohortReviewV2(
                cohort_id=request.cohort_id,
                cases=cases,
                decision=("redesign_required" if any(item.overall_decision == "blocked" for item in cases) else "revise_before_screening" if any(item.overall_decision == "revise" for item in cases) else "screening_ready"),
                screening_eligible=all(item.overall_decision == "pass" for item in cases),
            )
            result_path = destination / "reality_cohort_review.json"
            _atomic(result_path, result.model_dump(mode="json"))
            manifest.status = "completed"
            manifest.result_path = str(result_path)
            manifest.result_sha256 = _sha(result_path)
        except Exception as exc:
            manifest.status = "incomplete"
            manifest.first_failure = f"{type(exc).__name__}:{exc}"
        manifest.updated_at = _now()
        _atomic(manifest_path, manifest.model_dump(mode="json"))
        return manifest

    def _execute_calls(self, request: RealityReviewAuthorizationRequestV1, config: ProviderConfig, destination: Path, manifest: RealityReviewCampaignManifestV1, manifest_path: Path) -> List[RealityCaseReviewV2]:
        selection = RealityReviewSelectionV1.model_validate_json(Path(request.selection_manifest_path).read_text(encoding="utf-8"))
        selected = {item.case_id: item for item in selection.cases}
        reviewer = SemanticReviewExecutor(
            config,
            max_tokens=request.maximum_completion_tokens_per_call,
            input_token_hard_limit=request.maximum_input_tokens_per_call,
            max_retries=request.provider_sdk_retries,
        )
        candidate_reviews: dict[str, tuple[CandidateBlindRealityReviewV2, RealityReviewCallEvidenceV2]] = {}
        rubric_reviews: dict[str, tuple[RubricFocusRealityReviewV2, RealityReviewCallEvidenceV2]] = {}
        if request.request_mode == "continuation":
            prior_root = Path(request.prior_output_root)
            for stage_key, expected_sha in request.retained_call_sha256.items():
                case_id, stage = stage_key.split(":", 1)
                matches = list((prior_root / "calls").glob(f"*_{case_id}_{stage}"))
                if len(matches) != 1 or _tree_sha(matches[0]) != expected_sha:
                    raise PermissionError("reality_review_retained_call_drift")
                call_root = matches[0]
                parsed_payload = json.loads(
                    (call_root / "parsed_review.json").read_text(encoding="utf-8")
                )
                diagnostics = json.loads(
                    (call_root / "diagnostics.json").read_text(encoding="utf-8")
                )
                evidence = RealityReviewCallEvidenceV2(
                    stage=stage,
                    input_sha256=_sha(call_root / "input.json"),
                    raw_output_sha256=_sha(call_root / "raw_response.json"),
                    parsed_output_sha256=_sha(call_root / "parsed_review.json"),
                    prompt_tokens=int(diagnostics.get("prompt_tokens") or 0),
                    completion_tokens=int(diagnostics.get("completion_tokens") or 0),
                    duration_seconds=float(diagnostics.get("duration_seconds") or 0),
                )
                if stage == "candidate_blind":
                    candidate_reviews[case_id] = (
                        CandidateBlindRealityReviewV2.model_validate(parsed_payload),
                        evidence,
                    )
                else:
                    rubric_reviews[case_id] = (
                        RubricFocusRealityReviewV2.model_validate(parsed_payload),
                        evidence,
                    )
        for stage in ("candidate_blind", "rubric_focus"):
            for case_id in request.selected_case_ids:
                stage_key = f"{case_id}:{stage}"
                if stage_key not in request.authorized_stage_keys:
                    continue
                payload = self._candidate_payload(case_id) if stage == "candidate_blind" else self._rubric_payload(case_id, selected[case_id])
                estimated_tokens = max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 3)
                if estimated_tokens > request.maximum_input_tokens_per_call:
                    raise ValueError("reality_review_estimated_input_token_ceiling")
                parsed = None
                successful_root = None
                first_failure_sha = None
                first_failure_feedback = None
                for attempt in range(1, request.maximum_attempts_per_stage + 1):
                    if manifest.provider_calls_made >= request.maximum_provider_calls:
                        raise RuntimeError("reality_review_provider_call_ceiling")
                    call_root = destination / "calls" / f"{manifest.provider_calls_made + 1:02d}_{case_id}_{stage}_attempt_{attempt}"
                    _atomic(call_root / "input.json", payload)
                    reviewer.last_diagnostics = {}
                    reviewer.last_raw_response_content = ""
                    feedback = None if attempt == 1 else first_failure_feedback
                    try:
                        if stage == "candidate_blind":
                            parsed = reviewer.review_reality_candidate_blind(payload, format_feedback=feedback)
                        else:
                            parsed = reviewer.review_reality_rubric_focus(payload, format_feedback=feedback)
                    except Exception as exc:
                        manifest.provider_calls_made += 1
                        diagnostics = dict(reviewer.last_diagnostics)
                        diagnostics.update({
                            "attempt": attempt,
                            "failure_type": type(exc).__name__,
                            "failure_message": str(exc),
                            "failure_code": getattr(exc, "failure_code", "provider_failure"),
                            "retry_eligible": bool(getattr(exc, "retry_eligible", False)),
                        })
                        (call_root / "raw_response.json").write_text(reviewer.last_raw_response_content, encoding="utf-8")
                        _atomic(call_root / "diagnostics.json", diagnostics)
                        failure_sha = _tree_sha(call_root)
                        if first_failure_sha is None:
                            first_failure_sha = failure_sha
                            first_failure_feedback = f"{diagnostics['failure_code']}:{type(exc).__name__}"
                        if manifest.first_attempt_failure is None:
                            manifest.first_attempt_failure = first_failure_feedback
                        manifest.updated_at = _now()
                        _atomic(manifest_path, manifest.model_dump(mode="json"))
                        eligible = diagnostics["retry_eligible"] and diagnostics["failure_code"] in request.retry_eligible_failure_codes
                        if attempt == 1 and eligible:
                            manifest.controlled_retries_used += 1
                            continue
                        raise
                    manifest.provider_calls_made += 1
                    successful_root = call_root
                    break
                if parsed is None or successful_root is None:
                    raise RuntimeError("reality_review_stage_not_completed")
                call_root = successful_root
                raw = reviewer.last_raw_response_content
                (call_root / "raw_response.json").write_text(raw, encoding="utf-8")
                _atomic(call_root / "parsed_review.json", parsed.model_dump(mode="json"))
                _atomic(call_root / "diagnostics.json", reviewer.last_diagnostics)
                diagnostics = reviewer.last_diagnostics
                if int(diagnostics.get("prompt_tokens") or 0) > request.maximum_input_tokens_per_call or int(diagnostics.get("completion_tokens") or 0) > request.maximum_completion_tokens_per_call:
                    raise RuntimeError("reality_review_reported_token_ceiling")
                evidence = RealityReviewCallEvidenceV2(
                    stage=stage,
                    attempt_count=2 if first_failure_sha else 1,
                    first_attempt_failure_sha256=first_failure_sha,
                    input_sha256=_sha(call_root / "input.json"),
                    raw_output_sha256=_sha(call_root / "raw_response.json"),
                    parsed_output_sha256=_sha(call_root / "parsed_review.json"),
                    prompt_tokens=int(diagnostics.get("prompt_tokens") or 0),
                    completion_tokens=int(diagnostics.get("completion_tokens") or 0),
                    duration_seconds=float(diagnostics.get("duration_seconds") or 0),
                )
                if stage == "candidate_blind":
                    candidate_reviews[case_id] = (parsed, evidence)
                else:
                    rubric_reviews[case_id] = (parsed, evidence)
                    manifest.completed_case_ids.append(case_id)
                manifest.completed_calls += 1
                manifest.updated_at = _now()
                _atomic(manifest_path, manifest.model_dump(mode="json"))
        results = []
        for case_id in request.selected_case_ids:
            candidate, candidate_evidence = candidate_reviews[case_id]
            rubric, rubric_evidence = rubric_reviews[case_id]
            decisions = [item.decision for item in candidate.dimensions] + [rubric.dimension.decision]
            overall = "blocked" if "blocked" in decisions else "revise" if "revise" in decisions else "pass"
            results.append(RealityCaseReviewV2(case_id=case_id, motif=selected[case_id].motif, candidate_review=candidate, rubric_review=rubric, call_evidence=[candidate_evidence, rubric_evidence], overall_decision=overall))
        return results

    def _candidate_payload(self, case_id: str) -> dict[str, Any]:
        root = self.root / "blind_staging" / "candidate_packages" / case_id
        extractor = SemanticReviewExecutor(ProviderConfig(provider_name="offline", model="offline", base_url="https://invalid", api_key="unused"))
        return {
            "case_id": case_id,
            "dataset_row": json.loads((root / "dataset_row.json").read_text(encoding="utf-8")),
            "deliverable_contract": json.loads((root / "deliverable_contract.json").read_text(encoding="utf-8")),
            "reference_contents": [extractor._reference_content(path) for path in sorted((root / "reference_files").glob("*"))],
        }

    def _rubric_payload(self, case_id: str, selected: RealityReviewSelectionCaseV1) -> dict[str, Any]:
        campaign = json.loads((self.root / "campaign_manifest.json").read_text(encoding="utf-8"))
        assignment = next(item for item in campaign["assignments"] if item["blind_task_id"] == case_id)
        route_root = Path(assignment["package_root"])
        blind_root = self.root / "blind_staging" / "candidate_packages" / case_id
        return {
            "case_id": case_id,
            "candidate_requirements": json.loads((blind_root / "deliverable_contract.json").read_text(encoding="utf-8")),
            "rubric_plan": json.loads((route_root / "teacher" / "rubric_plan_v2.json").read_text(encoding="utf-8")),
            "rubric_binding_plan": json.loads((route_root / "teacher" / "rubric_binding_plan.json").read_text(encoding="utf-8")),
        }

    def _validate_request(self, request: RealityReviewAuthorizationRequestV1) -> None:
        if _sha(Path(request.selection_manifest_path)) != request.selection_manifest_sha256 or _sha(self.root / "campaign_manifest.json") != request.campaign_manifest_sha256 or _sha(self.root / "blind_staging" / "governance" / "route_blind_staging_report.json") != request.blind_staging_report_sha256:
            raise PermissionError("reality_review_request_frozen_input_drift")
        parity = json.loads(Path(request.container_parity_report_path).read_text(encoding="utf-8"))
        if _sha(Path(request.container_parity_report_path)) != request.container_parity_report_sha256 or parity.get("source_fingerprint") != request.source_fingerprint:
            raise PermissionError("reality_review_request_parity_drift")
        if governed_source_fingerprint(Path(__file__).resolve().parents[2]) != request.source_fingerprint:
            raise PermissionError("reality_review_request_source_fingerprint_drift")
        selection = RealityReviewSelectionV1.model_validate_json(
            Path(request.selection_manifest_path).read_text(encoding="utf-8")
        )
        campaign = json.loads(
            (self.root / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        by_id = {item["blind_task_id"]: item for item in campaign["assignments"]}
        selected = {item.case_id: item for item in selection.cases}
        for case_id in request.selected_case_ids:
            assignment = by_id.get(case_id)
            selection_case = selected.get(case_id)
            if (
                assignment is None
                or selection_case is None
                or assignment.get("package_fingerprint")
                != request.package_fingerprints[case_id]
                or selection_case.package_fingerprint
                != request.package_fingerprints[case_id]
            ):
                raise PermissionError("reality_review_request_package_drift")
            candidate_root = (
                self.root / "blind_staging" / "candidate_packages" / case_id
            )
            if _tree_sha(candidate_root) != request.candidate_input_tree_sha256[case_id]:
                raise PermissionError("reality_review_request_candidate_tree_drift")
            rubric_root = Path(assignment["package_root"]) / "teacher"
            rubric_hash = _json_sha(
                [
                    _sha(rubric_root / "rubric_plan_v2.json"),
                    _sha(rubric_root / "rubric_binding_plan.json"),
                ]
            )
            if rubric_hash != request.rubric_input_sha256[case_id]:
                raise PermissionError("reality_review_request_rubric_drift")
        if request.request_mode == "continuation":
            prior_manifest = Path(request.prior_manifest_path)
            if (
                not prior_manifest.is_file()
                or _sha(prior_manifest) != request.prior_manifest_sha256
                or prior_manifest.parent != Path(request.prior_output_root)
            ):
                raise PermissionError("reality_review_prior_manifest_drift")
            for stage_key, expected_sha in request.retained_call_sha256.items():
                case_id, stage = stage_key.split(":", 1)
                matches = list(
                    (Path(request.prior_output_root) / "calls").glob(
                        f"*_{case_id}_{stage}"
                    )
                )
                if len(matches) != 1 or _tree_sha(matches[0]) != expected_sha:
                    raise PermissionError("reality_review_retained_evidence_drift")

    @staticmethod
    def _validate_receipt(request: RealityReviewAuthorizationRequestV1, request_sha: str, receipt: RealityReviewAuthorizationReceiptV1) -> None:
        if receipt.authorization_request_sha256 != request_sha or receipt.cohort_id != request.cohort_id or receipt.authorized_case_ids != request.selected_case_ids or receipt.authorized_model != request.model or receipt.maximum_provider_calls != request.maximum_provider_calls or receipt.maximum_total_cost_usd != request.maximum_total_cost_usd:
            raise PermissionError("reality_review_receipt_scope_mismatch")
        if receipt.expires_at and datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise PermissionError("reality_review_receipt_expired")
