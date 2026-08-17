from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_external_model_policy import enforce_external_model_policy
from task_generator.v3_reality_review_campaign import (
    RealityReviewSelectionV1,
    _atomic,
    _json_sha,
    _sha,
    _tree_sha,
)
from task_generator.v3_rubric_scoring_audit import RubricScoringAuthorityAuditor
from task_generator.v3_semantic_review_executor import SemanticReviewExecutionError, SemanticReviewExecutor
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_source_fingerprint import governed_source_fingerprint
from task_generator.v3_validity_utility import (
    CandidateBlindRealityReviewV2,
    RealityReviewCallEvidenceV2,
    RubricFocusRealityReviewV3,
    RubricFocusRealityReviewV4,
    RubricScoringAuthorityAuditV1,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_reviewer_inconsistency(cases: list[Any]) -> list[str]:
    inconsistent: list[str] = []
    for signature in sorted({item.scoring_semantic_signature for item in cases}):
        comparable = [
            item for item in cases if item.scoring_semantic_signature == signature
        ]
        decision_and_pairs = {
            (
                item.overall_decision,
                tuple(
                    (
                        pair.criterion_a,
                        pair.criterion_b,
                        pair.assessment,
                    )
                    for pair in item.rubric_review.pair_assessments
                ),
            )
            for item in comparable
        }
        if len(decision_and_pairs) > 1:
            inconsistent.append(signature)
    return inconsistent


class RubricRecalibrationAuthorizationRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_version: Literal[
        "v3.rubric_recalibration_authorization_request.1",
        "v3.rubric_recalibration_authorization_request.2",
    ] = "v3.rubric_recalibration_authorization_request.2"
    cohort_id: str
    requested_scope: Literal[
        "rubric_focus_recalibration",
        "rubric_focus_recalibration_compact_v4",
    ] = "rubric_focus_recalibration_compact_v4"
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    selected_case_ids: list[str]
    authorized_stage_keys: list[str]
    prior_completed_manifest_path: str
    prior_completed_manifest_sha256: str = Field(min_length=64, max_length=64)
    prior_cohort_result_path: str
    prior_cohort_result_sha256: str = Field(min_length=64, max_length=64)
    retained_candidate_call_tree_sha256: dict[str, str]
    retained_candidate_review_sha256: dict[str, str]
    rubric_input_sha256: dict[str, str]
    scoring_audit_path: dict[str, str]
    scoring_audit_sha256: dict[str, str]
    scoring_structure_signature: dict[str, str]
    scoring_semantic_signature: dict[str, str]
    selection_manifest_path: str
    selection_manifest_sha256: str = Field(min_length=64, max_length=64)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    container_parity_report_path: str
    container_parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    maximum_provider_calls: Literal[12] = 12
    maximum_attempts_per_stage: Literal[2] = 2
    maximum_input_tokens_per_call: Literal[12000] = 12000
    maximum_completion_tokens_per_call: Literal[4000] = 4000
    maximum_cost_per_call_usd: Literal[0.01] = 0.01
    maximum_total_cost_usd: Literal[0.13] = 0.13
    retry_eligible_failure_codes: list[str] = Field(default_factory=lambda: [
        "transport_timeout", "transport_http_408", "transport_http_429",
        "transport_http_5xx", "empty_content", "truncated_output",
        "invalid_json", "schema_contract_failure",
    ])
    provider_sdk_retries: Literal[0] = 0
    candidate_review_execution_authorized: Literal[False] = False
    rubric_mutation_authorized: Literal[False] = False
    solver_execution_authorized: Literal[False] = False
    grader_execution_authorized: Literal[False] = False
    screening_execution_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    external_calls_made: Literal[False] = False
    user_action_required: str = Field(min_length=24)

    @model_validator(mode="after")
    def validate_scope(self) -> "RubricRecalibrationAuthorizationRequestV1":
        ids = set(self.selected_case_ids)
        if len(ids) != 6 or len(self.selected_case_ids) != 6:
            raise ValueError("rubric_recalibration_requires_six_cases")
        stage = (
            "rubric_focus_v4_compact"
            if self.request_version.endswith(".2")
            else "rubric_focus_v3"
        )
        expected_scope = (
            "rubric_focus_recalibration_compact_v4"
            if self.request_version.endswith(".2")
            else "rubric_focus_recalibration"
        )
        if self.requested_scope != expected_scope:
            raise ValueError("rubric_recalibration_requested_scope_mismatch")
        expected_stages = {f"{case_id}:{stage}" for case_id in ids}
        if set(self.authorized_stage_keys) != expected_stages:
            raise ValueError("rubric_recalibration_stage_scope_mismatch")
        maps = [
            self.retained_candidate_call_tree_sha256,
            self.retained_candidate_review_sha256,
            self.rubric_input_sha256,
            self.scoring_audit_path,
            self.scoring_audit_sha256,
            self.scoring_structure_signature,
            self.scoring_semantic_signature,
        ]
        if any(set(item) != ids for item in maps):
            raise ValueError("rubric_recalibration_case_binding_mismatch")
        if self.maximum_provider_calls * self.maximum_cost_per_call_usd > self.maximum_total_cost_usd:
            raise ValueError("rubric_recalibration_reserved_cost_ceiling_mismatch")
        return self


class RubricRecalibrationAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.rubric_recalibration_authorization_receipt.1"] = "v3.rubric_recalibration_authorization_receipt.1"
    authorization_id: str
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    cohort_id: str
    authorized_case_ids: list[str]
    authorized_model: Literal["deepseek-v4-pro"]
    maximum_provider_calls: Literal[12]
    maximum_total_cost_usd: Literal[0.13]
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: Optional[str] = None
    candidate_review_execution_authorized: Literal[False] = False
    rubric_mutation_authorized: Literal[False] = False
    screening_execution_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class RubricRecalibrationCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    structure_signature: str = Field(min_length=64, max_length=64)
    scoring_semantic_signature: str = Field(min_length=64, max_length=64)
    retained_candidate_review: CandidateBlindRealityReviewV2
    retained_candidate_call_tree_sha256: str = Field(min_length=64, max_length=64)
    rubric_review: Union[RubricFocusRealityReviewV3, RubricFocusRealityReviewV4]
    rubric_call_evidence: RealityReviewCallEvidenceV2
    overall_decision: Literal["pass", "revise", "blocked"]

    @model_validator(mode="after")
    def validate_case(self) -> "RubricRecalibrationCaseV1":
        if self.retained_candidate_review.case_id != self.case_id or self.rubric_review.case_id != self.case_id:
            raise ValueError("rubric_recalibration_case_identity_mismatch")
        if any(item.decision != "pass" for item in self.retained_candidate_review.dimensions):
            raise ValueError("rubric_recalibration_requires_retained_candidate_pass")
        if self.overall_decision != self.rubric_review.decision:
            raise ValueError("rubric_recalibration_case_decision_mismatch")
        return self


class RubricRecalibrationCohortV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["v3.rubric_recalibration_cohort.1"] = "v3.rubric_recalibration_cohort.1"
    cohort_id: str
    cases: list[RubricRecalibrationCaseV1]
    reviewer_inconsistency_signatures: list[str] = Field(default_factory=list)
    decision: Literal["screening_ready", "revise_before_screening", "redesign_required", "incomplete"]
    screening_eligible: bool
    professional_validity_status: Literal["provisional"] = "provisional"
    expert_evidence_present: Literal[False] = False
    training_admission_authorized: Literal[False] = False
    screening_execution_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_result(self) -> "RubricRecalibrationCohortV1":
        complete = len(self.cases) == 6 and len({item.case_id for item in self.cases}) == 6
        expected = (
            "incomplete" if not complete or self.reviewer_inconsistency_signatures
            else "redesign_required" if any(item.overall_decision == "blocked" for item in self.cases)
            else "revise_before_screening" if any(item.overall_decision == "revise" for item in self.cases)
            else "screening_ready"
        )
        if self.decision != expected or self.screening_eligible != (expected == "screening_ready"):
            raise ValueError("rubric_recalibration_cohort_decision_mismatch")
        return self


class RubricRecalibrationManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.rubric_recalibration_campaign.1"] = "v3.rubric_recalibration_campaign.1"
    cohort_id: str
    authorization_request_sha256: str
    authorization_receipt_sha256: str
    status: Literal["running", "completed", "incomplete"]
    completed_stages: int = Field(ge=0, le=6)
    provider_calls_made: int = Field(ge=0, le=12)
    controlled_retries_used: int = Field(ge=0, le=6)
    reserved_cost_ceiling_usd: float = Field(ge=0.0, le=0.13, default=0.0)
    first_attempt_failure: Optional[str] = None
    first_failure: Optional[str] = None
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: str
    updated_at: str


class RubricRecalibrationCampaign:
    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.governance = self.root / "governance" / "rubric_recalibration"
        self.audit_root = self.governance / "scoring_audits"
        self.current_request = self.governance / "authorization_request.json"
        self.immutable_requests = self.governance / "authorization_requests"

    def compile_audits(self, *, selection_path: str | Path) -> dict[str, RubricScoringAuthorityAuditV1]:
        selection = RealityReviewSelectionV1.model_validate_json(Path(selection_path).read_text(encoding="utf-8"))
        assignments = self._assignments()
        auditor = RubricScoringAuthorityAuditor()
        results: dict[str, RubricScoringAuthorityAuditV1] = {}
        for case_id in sorted(item.case_id for item in selection.cases):
            teacher = Path(assignments[case_id]["package_root"]) / "teacher"
            audit = auditor.compile(
                rubric_plan_path=teacher / "rubric_plan_v2.json",
                rubric_binding_plan_path=teacher / "rubric_binding_plan.json",
                case_id=case_id,
            )
            if audit.decision != "pass":
                raise ValueError(f"rubric_scoring_authority_audit_blocked:{case_id}")
            path = self.audit_root / f"{case_id}.json"
            _atomic(path, audit.model_dump(mode="json"))
            results[case_id] = audit
        return results

    def compile_request(
        self,
        *,
        selection_path: str | Path,
        prior_manifest_path: str | Path,
        parity_path: str | Path,
    ) -> RubricRecalibrationAuthorizationRequestV1:
        selection_file = Path(selection_path).resolve()
        prior_manifest = Path(prior_manifest_path).resolve()
        parity_file = Path(parity_path).resolve()
        selection = RealityReviewSelectionV1.model_validate_json(selection_file.read_text(encoding="utf-8"))
        prior = json.loads(prior_manifest.read_text(encoding="utf-8"))
        if prior.get("status") != "completed" or int(prior.get("completed_calls", -1)) != 12:
            raise ValueError("rubric_recalibration_requires_completed_prior_cohort")
        prior_result = Path(prior["result_path"]).resolve()
        prior_payload = json.loads(prior_result.read_text(encoding="utf-8"))
        prior_cases = {item["case_id"]: item for item in prior_payload["cases"]}
        parity = json.loads(parity_file.read_text(encoding="utf-8"))
        if not (parity.get("passed") is True and parity.get("network_mode") == "none" and parity.get("read_only_root") is True and parity.get("provider_credentials_mounted") is False and parity.get("cleanup_returncode") == 0):
            raise ValueError("rubric_recalibration_parity_invalid")
        if governed_source_fingerprint(Path(__file__).resolve().parents[2]) != parity.get("source_fingerprint"):
            raise ValueError("rubric_recalibration_parity_source_drift")
        assignments = self._assignments()
        candidate_trees: dict[str, str] = {}
        candidate_reviews: dict[str, str] = {}
        rubric_hashes: dict[str, str] = {}
        audit_paths: dict[str, str] = {}
        audit_hashes: dict[str, str] = {}
        signatures: dict[str, str] = {}
        semantic_signatures: dict[str, str] = {}
        case_ids = sorted(item.case_id for item in selection.cases)
        for case_id in case_ids:
            case = prior_cases.get(case_id)
            if case is None or any(item["decision"] != "pass" for item in case["candidate_review"]["dimensions"]):
                raise ValueError("rubric_recalibration_candidate_evidence_not_pass")
            review_sha = _json_sha(case["candidate_review"])
            matches = list((prior_manifest.parent / "calls").glob(f"*_{case_id}_candidate_blind_attempt_*"))
            if len(matches) != 1 or not (matches[0] / "parsed_review.json").is_file():
                raise ValueError("rubric_recalibration_candidate_call_tree_missing")
            if _json_sha(json.loads((matches[0] / "parsed_review.json").read_text(encoding="utf-8"))) != review_sha:
                raise ValueError("rubric_recalibration_candidate_review_drift")
            teacher = Path(assignments[case_id]["package_root"]) / "teacher"
            audit_path = (self.audit_root / f"{case_id}.json").resolve()
            audit = RubricScoringAuthorityAuditV1.model_validate_json(audit_path.read_text(encoding="utf-8"))
            if audit.decision != "pass":
                raise ValueError("rubric_recalibration_audit_not_pass")
            candidate_trees[case_id] = _tree_sha(matches[0])
            candidate_reviews[case_id] = review_sha
            rubric_hashes[case_id] = _json_sha([
                _sha(teacher / "rubric_plan_v2.json"),
                _sha(teacher / "rubric_binding_plan.json"),
            ])
            audit_paths[case_id] = str(audit_path)
            audit_hashes[case_id] = _sha(audit_path)
            signatures[case_id] = audit.structure_signature
            semantic_signatures[case_id] = audit.scoring_semantic_signature
        request = RubricRecalibrationAuthorizationRequestV1(
            cohort_id=selection.cohort_id,
            selected_case_ids=case_ids,
            authorized_stage_keys=[
                f"{case_id}:rubric_focus_v4_compact" for case_id in case_ids
            ],
            prior_completed_manifest_path=str(prior_manifest),
            prior_completed_manifest_sha256=_sha(prior_manifest),
            prior_cohort_result_path=str(prior_result),
            prior_cohort_result_sha256=_sha(prior_result),
            retained_candidate_call_tree_sha256=candidate_trees,
            retained_candidate_review_sha256=candidate_reviews,
            rubric_input_sha256=rubric_hashes,
            scoring_audit_path=audit_paths,
            scoring_audit_sha256=audit_hashes,
            scoring_structure_signature=signatures,
            scoring_semantic_signature=semantic_signatures,
            selection_manifest_path=str(selection_file),
            selection_manifest_sha256=_sha(selection_file),
            campaign_manifest_sha256=_sha(self.root / "campaign_manifest.json"),
            container_parity_report_path=str(parity_file),
            container_parity_report_sha256=_sha(parity_file),
            source_fingerprint=parity["source_fingerprint"],
            user_action_required="The user must explicitly authorize this exact six-rubric compact V4 DeepSeek recalibration request SHA before any external call.",
        )
        _atomic(self.current_request, request.model_dump(mode="json"))
        request_sha = _sha(self.current_request)
        immutable = self.immutable_requests / f"{request_sha}.json"
        if not immutable.exists():
            _atomic(immutable, request.model_dump(mode="json"))
        return request

    def compile_receipt(self, *, request_path: str | Path, authorization_id: str, authorization_statement: str, expires_at: str, output_path: str | Path) -> RubricRecalibrationAuthorizationReceiptV1:
        path = Path(request_path).resolve()
        request_sha = _sha(path)
        if path.parent != self.immutable_requests.resolve() or path.name != f"{request_sha}.json":
            raise ValueError("rubric_recalibration_receipt_requires_immutable_request")
        request = RubricRecalibrationAuthorizationRequestV1.model_validate_json(path.read_text(encoding="utf-8"))
        self._validate_request(request)
        receipt = RubricRecalibrationAuthorizationReceiptV1(
            authorization_id=authorization_id,
            authorization_request_sha256=request_sha,
            cohort_id=request.cohort_id,
            authorized_case_ids=request.selected_case_ids,
            authorized_model=request.model,
            maximum_provider_calls=request.maximum_provider_calls,
            maximum_total_cost_usd=request.maximum_total_cost_usd,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_now(), expires_at=expires_at,
        )
        output = Path(output_path)
        if output.exists():
            raise FileExistsError("rubric_recalibration_receipt_exists")
        _atomic(output, receipt.model_dump(mode="json"))
        return receipt

    def execute(self, *, receipt_path: str | Path, provider_config: ProviderConfig, output_root: str | Path) -> RubricRecalibrationManifestV1:
        request = RubricRecalibrationAuthorizationRequestV1.model_validate_json(self.current_request.read_text(encoding="utf-8"))
        request_sha = _sha(self.current_request)
        receipt_path = Path(receipt_path).resolve()
        receipt = RubricRecalibrationAuthorizationReceiptV1.model_validate_json(receipt_path.read_text(encoding="utf-8"))
        self._validate_request(request)
        self._validate_receipt(request, request_sha, receipt)
        enforce_external_model_policy(provider_config.provider_name, provider_config.model)
        if provider_config.provider_name != request.provider or provider_config.model != request.model:
            raise PermissionError("rubric_recalibration_provider_scope_mismatch")
        destination = Path(output_root).resolve()
        manifest_path = destination / "campaign_manifest.json"
        if manifest_path.exists():
            raise PermissionError("rubric_recalibration_receipt_already_consumed")
        manifest = RubricRecalibrationManifestV1(
            cohort_id=request.cohort_id,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=_sha(receipt_path),
            status="running", completed_stages=0, provider_calls_made=0,
            controlled_retries_used=0, created_at=_now(), updated_at=_now(),
        )
        _atomic(manifest_path, manifest.model_dump(mode="json"))
        try:
            result = self._execute_reviews(request, provider_config, destination, manifest, manifest_path)
            result_path = destination / "rubric_recalibration_cohort.json"
            _atomic(result_path, result.model_dump(mode="json"))
            manifest.status = "completed" if result.decision != "incomplete" else "incomplete"
            manifest.result_path = str(result_path)
            manifest.result_sha256 = _sha(result_path)
            if result.decision == "incomplete":
                manifest.first_failure = "reviewer_inconsistency"
        except Exception as exc:
            manifest.status = "incomplete"
            manifest.first_failure = f"{type(exc).__name__}:{exc}"
        manifest.updated_at = _now()
        _atomic(manifest_path, manifest.model_dump(mode="json"))
        return manifest

    def _execute_reviews(self, request: RubricRecalibrationAuthorizationRequestV1, config: ProviderConfig, destination: Path, manifest: RubricRecalibrationManifestV1, manifest_path: Path) -> RubricRecalibrationCohortV1:
        prior = json.loads(Path(request.prior_cohort_result_path).read_text(encoding="utf-8"))
        prior_cases = {item["case_id"]: item for item in prior["cases"]}
        reviewer = SemanticReviewExecutor(config, max_tokens=request.maximum_completion_tokens_per_call, input_token_hard_limit=request.maximum_input_tokens_per_call, max_retries=0)
        compact_v4 = request.request_version.endswith(".2")
        stage_name = "rubric_focus_v4_compact" if compact_v4 else "rubric_focus_v3"
        cases: list[RubricRecalibrationCaseV1] = []
        for case_id in request.selected_case_ids:
            payload = self._rubric_payload(case_id, request)
            estimated_tokens = (
                reviewer.estimate_reality_rubric_focus_v4_input_tokens(payload)
                if compact_v4
                else reviewer.estimate_reality_rubric_focus_v3_input_tokens(payload)
            )
            if estimated_tokens > request.maximum_input_tokens_per_call:
                raise ValueError("rubric_recalibration_estimated_input_token_ceiling")
            audit = RubricScoringAuthorityAuditV1.model_validate_json(
                Path(request.scoring_audit_path[case_id]).read_text(encoding="utf-8")
            )
            parsed = None
            success_root: Optional[Path] = None
            first_failure_sha: Optional[str] = None
            first_feedback: Optional[str] = None
            for attempt in (1, 2):
                if manifest.provider_calls_made >= request.maximum_provider_calls:
                    raise RuntimeError("rubric_recalibration_provider_call_ceiling")
                next_reserved = round(
                    (manifest.provider_calls_made + 1)
                    * request.maximum_cost_per_call_usd,
                    6,
                )
                if next_reserved > request.maximum_total_cost_usd:
                    raise RuntimeError("rubric_recalibration_reserved_cost_ceiling")
                call_root = destination / "calls" / f"{manifest.provider_calls_made + 1:02d}_{case_id}_{stage_name}_attempt_{attempt}"
                _atomic(call_root / "input.json", payload)
                reviewer.last_diagnostics = {}
                reviewer.last_raw_response_content = ""
                try:
                    parsed = (
                        reviewer.review_reality_rubric_focus_v4(
                            payload,
                            format_feedback=first_feedback if attempt == 2 else None,
                        )
                        if compact_v4
                        else reviewer.review_reality_rubric_focus_v3(
                            payload,
                            format_feedback=first_feedback if attempt == 2 else None,
                        )
                    )
                    self._validate_review_against_audit(parsed, audit)
                except Exception as exc:
                    manifest.provider_calls_made += 1
                    manifest.reserved_cost_ceiling_usd = next_reserved
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
                    if first_failure_sha is None:
                        first_failure_sha = _tree_sha(call_root)
                        first_feedback = (
                            f"{diagnostics['failure_code']}:"
                            f"{str(exc)[:160]}"
                        )
                    if manifest.first_attempt_failure is None:
                        manifest.first_attempt_failure = first_feedback
                    manifest.updated_at = _now()
                    _atomic(manifest_path, manifest.model_dump(mode="json"))
                    eligible = diagnostics["retry_eligible"] and diagnostics["failure_code"] in request.retry_eligible_failure_codes
                    if attempt == 1 and eligible:
                        manifest.controlled_retries_used += 1
                        continue
                    raise
                manifest.provider_calls_made += 1
                manifest.reserved_cost_ceiling_usd = next_reserved
                success_root = call_root
                break
            if parsed is None or success_root is None:
                raise RuntimeError("rubric_recalibration_stage_not_completed")
            (success_root / "raw_response.json").write_text(reviewer.last_raw_response_content, encoding="utf-8")
            _atomic(success_root / "parsed_review.json", parsed.model_dump(mode="json"))
            _atomic(success_root / "diagnostics.json", reviewer.last_diagnostics)
            diagnostics = reviewer.last_diagnostics
            if int(diagnostics.get("prompt_tokens") or 0) > request.maximum_input_tokens_per_call or int(diagnostics.get("completion_tokens") or 0) > request.maximum_completion_tokens_per_call:
                raise RuntimeError("rubric_recalibration_reported_token_ceiling")
            evidence = RealityReviewCallEvidenceV2(
                stage="rubric_focus", attempt_count=2 if first_failure_sha else 1,
                first_attempt_failure_sha256=first_failure_sha,
                input_sha256=_sha(success_root / "input.json"),
                raw_output_sha256=_sha(success_root / "raw_response.json"),
                parsed_output_sha256=_sha(success_root / "parsed_review.json"),
                prompt_tokens=int(diagnostics.get("prompt_tokens") or 0),
                completion_tokens=int(diagnostics.get("completion_tokens") or 0),
                duration_seconds=float(diagnostics.get("duration_seconds") or 0),
            )
            candidate = CandidateBlindRealityReviewV2.model_validate(prior_cases[case_id]["candidate_review"])
            cases.append(RubricRecalibrationCaseV1(
                case_id=case_id,
                structure_signature=request.scoring_structure_signature[case_id],
                scoring_semantic_signature=request.scoring_semantic_signature[case_id],
                retained_candidate_review=candidate,
                retained_candidate_call_tree_sha256=request.retained_candidate_call_tree_sha256[case_id],
                rubric_review=parsed,
                rubric_call_evidence=evidence,
                overall_decision=parsed.decision,
            ))
            manifest.completed_stages += 1
            manifest.updated_at = _now()
            _atomic(manifest_path, manifest.model_dump(mode="json"))
        inconsistent = detect_reviewer_inconsistency(cases)
        decision = (
            "incomplete" if inconsistent
            else "redesign_required" if any(item.overall_decision == "blocked" for item in cases)
            else "revise_before_screening" if any(item.overall_decision == "revise" for item in cases)
            else "screening_ready"
        )
        return RubricRecalibrationCohortV1(
            cohort_id=request.cohort_id, cases=cases,
            reviewer_inconsistency_signatures=inconsistent,
            decision=decision, screening_eligible=decision == "screening_ready",
        )

    def _rubric_payload(self, case_id: str, request: RubricRecalibrationAuthorizationRequestV1) -> dict[str, Any]:
        assignment = self._assignments()[case_id]
        teacher = Path(assignment["package_root"]) / "teacher"
        blind = self.root / "blind_staging" / "candidate_packages" / case_id
        audit = json.loads(Path(request.scoring_audit_path[case_id]).read_text(encoding="utf-8"))
        compact_audit = {
            key: audit[key]
            for key in (
                "audit_version", "case_id", "final_scoring_criterion_ids",
                "final_scoring_criteria_count", "annotation_binding_ids",
                "annotation_bindings_count", "annotation_bindings_non_scoring",
                "structure_signature", "scoring_semantic_signature",
                "duplicate_criterion_ids",
                "duplicate_failure_signals", "duplicate_observable_behaviors",
                "weight_sum_valid", "criterion_count_valid",
                "rubric_metadata_valid", "binding_authority_valid", "decision",
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
        return {
            "case_id": case_id,
            "candidate_requirements": json.loads((blind / "deliverable_contract.json").read_text(encoding="utf-8")),
            "rubric_plan": json.loads((teacher / "rubric_plan_v2.json").read_text(encoding="utf-8")),
            "rubric_binding_plan": json.loads((teacher / "rubric_binding_plan.json").read_text(encoding="utf-8")),
            "scoring_authority_audit": compact_audit,
        }

    def _validate_request(self, request: RubricRecalibrationAuthorizationRequestV1) -> None:
        enforce_external_model_policy(request.provider, request.model)
        if governed_source_fingerprint(Path(__file__).resolve().parents[2]) != request.source_fingerprint:
            raise PermissionError("rubric_recalibration_source_fingerprint_drift")
        paths = [
            (Path(request.prior_completed_manifest_path), request.prior_completed_manifest_sha256),
            (Path(request.prior_cohort_result_path), request.prior_cohort_result_sha256),
            (Path(request.selection_manifest_path), request.selection_manifest_sha256),
            (self.root / "campaign_manifest.json", request.campaign_manifest_sha256),
            (Path(request.container_parity_report_path), request.container_parity_report_sha256),
        ]
        if any(not path.is_file() or _sha(path) != expected for path, expected in paths):
            raise PermissionError("rubric_recalibration_frozen_input_drift")
        parity = json.loads(Path(request.container_parity_report_path).read_text(encoding="utf-8"))
        if parity.get("source_fingerprint") != request.source_fingerprint:
            raise PermissionError("rubric_recalibration_parity_drift")
        prior_root = Path(request.prior_completed_manifest_path).parent
        prior_result = json.loads(Path(request.prior_cohort_result_path).read_text(encoding="utf-8"))
        prior_cases = {item["case_id"]: item for item in prior_result["cases"]}
        assignments = self._assignments()
        for case_id in request.selected_case_ids:
            matches = list((prior_root / "calls").glob(f"*_{case_id}_candidate_blind_attempt_*"))
            if len(matches) != 1 or _tree_sha(matches[0]) != request.retained_candidate_call_tree_sha256[case_id]:
                raise PermissionError("rubric_recalibration_retained_candidate_drift")
            prior_case = prior_cases.get(case_id)
            if prior_case is None or _json_sha(prior_case["candidate_review"]) != request.retained_candidate_review_sha256[case_id]:
                raise PermissionError("rubric_recalibration_retained_candidate_review_drift")
            audit_path = Path(request.scoring_audit_path[case_id])
            audit = RubricScoringAuthorityAuditV1.model_validate_json(audit_path.read_text(encoding="utf-8"))
            if audit.case_id != case_id or _sha(audit_path) != request.scoring_audit_sha256[case_id] or audit.structure_signature != request.scoring_structure_signature[case_id] or audit.decision != "pass":
                raise PermissionError("rubric_recalibration_audit_drift")
            if audit.scoring_semantic_signature != request.scoring_semantic_signature[case_id]:
                raise PermissionError("rubric_recalibration_semantic_signature_drift")
            teacher = Path(assignments[case_id]["package_root"]) / "teacher"
            rubric_hash = _json_sha([_sha(teacher / "rubric_plan_v2.json"), _sha(teacher / "rubric_binding_plan.json")])
            if rubric_hash != request.rubric_input_sha256[case_id]:
                raise PermissionError("rubric_recalibration_rubric_drift")

    @staticmethod
    def _validate_receipt(request: RubricRecalibrationAuthorizationRequestV1, request_sha: str, receipt: RubricRecalibrationAuthorizationReceiptV1) -> None:
        if receipt.authorization_request_sha256 != request_sha or receipt.cohort_id != request.cohort_id or receipt.authorized_case_ids != request.selected_case_ids or receipt.authorized_model != request.model or receipt.maximum_provider_calls != request.maximum_provider_calls or receipt.maximum_total_cost_usd != request.maximum_total_cost_usd:
            raise PermissionError("rubric_recalibration_receipt_scope_mismatch")
        if receipt.expires_at and datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise PermissionError("rubric_recalibration_receipt_expired")

    def _assignments(self) -> dict[str, dict[str, Any]]:
        campaign = json.loads((self.root / "campaign_manifest.json").read_text(encoding="utf-8"))
        return {item["blind_task_id"]: item for item in campaign["assignments"]}

    @staticmethod
    def _validate_review_against_audit(
        review: Union[RubricFocusRealityReviewV3, RubricFocusRealityReviewV4],
        audit: RubricScoringAuthorityAuditV1,
    ) -> None:
        if review.final_scoring_criterion_ids != audit.final_scoring_criterion_ids:
            raise SemanticReviewExecutionError(
                "Rubric review criterion identity does not match the frozen audit.",
                retry_eligible=True,
                failure_code="schema_contract_failure",
            )
        audit_pairs = {
            (item.criterion_a, item.criterion_b): item for item in audit.pair_audits
        }
        for pair in review.pair_assessments:
            key = (pair.criterion_a, pair.criterion_b)
            authority = audit_pairs[key]
            has_shared_evidence = bool(authority.shared_evidence_or_judgment_ids)
            if (
                pair.assessment == "shared_evidence_distinct_behavior"
                and not has_shared_evidence
            ) or (
                pair.assessment == "distinct" and has_shared_evidence
            ):
                raise SemanticReviewExecutionError(
                    "Rubric review shared-evidence classification conflicts with the frozen audit.",
                    retry_eligible=True,
                    failure_code="schema_contract_failure",
                )
        if isinstance(review, RubricFocusRealityReviewV4):
            detailed = review.risk_findings
        else:
            detailed = review.pair_assessments
        for finding in detailed:
            cited = " ".join([finding.rationale, *finding.evidence_locators])
            if finding.criterion_a not in cited or finding.criterion_b not in cited:
                raise SemanticReviewExecutionError(
                    "Rubric review pair evidence must cite both criterion IDs.",
                    retry_eligible=True,
                    failure_code="schema_contract_failure",
                )
