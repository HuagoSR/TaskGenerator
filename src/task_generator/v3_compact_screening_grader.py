from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_codex_local_solver import (
    CodexLocalCampaignManifestV1,
    CodexLocalProcessOutcomeV1,
    _atomic_json,
    _now,
    _sha_file,
)
from task_generator.v3_matched_screening import (
    MatchedScreeningAnalyzer,
    MatchedScreeningResultV1,
    RUBRIC_WEIGHTS,
    ScreeningTaskObservationV1,
)
from task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
)
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_source_fingerprint import governed_source_fingerprint
from task_generator.v3_validity_utility import UtilityProfileV1, ValidityVectorV1


CRITERION_IDS = tuple(RUBRIC_WEIGHTS)
CRITERION_SHORT_NAMES = {
    "criterion_factual_accuracy": "factual_accuracy",
    "criterion_evidence_traceability": "evidence_traceability",
    "criterion_method_process": "method_process",
    "criterion_exception_handling": "exception_handling",
    "criterion_reproducibility": "reproducibility",
    "criterion_structural_usability": "structural_usability",
    "criterion_professional_expression": "professional_expression",
}


class CompactScoreVectorV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factual_accuracy: int = Field(ge=0, le=4)
    evidence_traceability: int = Field(ge=0, le=4)
    method_process: int = Field(ge=0, le=4)
    exception_handling: int = Field(ge=0, le=4)
    reproducibility: int = Field(ge=0, le=4)
    structural_usability: int = Field(ge=0, le=4)
    professional_expression: int = Field(ge=0, le=4)

    def by_criterion_id(self) -> Dict[str, int]:
        values = self.model_dump()
        return {
            criterion_id: values[short_name]
            for criterion_id, short_name in CRITERION_SHORT_NAMES.items()
        }


class CompactFindingV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: Literal[
        "criterion_factual_accuracy",
        "criterion_evidence_traceability",
        "criterion_method_process",
        "criterion_exception_handling",
        "criterion_reproducibility",
        "criterion_structural_usability",
        "criterion_professional_expression",
    ]
    severity: Literal["minor", "material", "major"]
    locator: str = Field(min_length=3, max_length=120)
    issue: str = Field(min_length=8, max_length=240)


class CompactExceptionalEvidenceV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: Literal[
        "criterion_factual_accuracy",
        "criterion_evidence_traceability",
        "criterion_method_process",
        "criterion_exception_handling",
        "criterion_reproducibility",
        "criterion_structural_usability",
        "criterion_professional_expression",
    ]
    locator: str = Field(min_length=3, max_length=120)
    evidence: str = Field(min_length=8, max_length=180)


class CompactGraderDraftV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    scores: CompactScoreVectorV2
    findings: List[CompactFindingV2] = Field(default_factory=list, max_length=5)
    exceptional_evidence: List[CompactExceptionalEvidenceV2] = Field(
        default_factory=list, max_length=2
    )
    major_defect: bool
    route_identity_seen: Literal[False] = False

    @model_validator(mode="after")
    def validate_calibration_contract(self) -> "CompactGraderDraftV2":
        scores = self.scores.by_criterion_id()
        finding_ids = {item.criterion_id for item in self.findings}
        exceptional_ids = [
            item.criterion_id for item in self.exceptional_evidence
        ]
        if len(exceptional_ids) != len(set(exceptional_ids)):
            raise ValueError("compact_grader_exceptional_evidence_duplicate")
        for criterion_id, score in scores.items():
            if score <= 2 and criterion_id not in finding_ids:
                raise ValueError("compact_grader_deduction_without_finding")
            if score == 4 and criterion_id not in exceptional_ids:
                raise ValueError(
                    "compact_grader_exceptional_score_without_evidence"
                )
            if score != 4 and criterion_id in exceptional_ids:
                raise ValueError(
                    "compact_grader_exceptional_evidence_score_mismatch"
                )
        if self.major_defect and not any(
            item.severity == "major" for item in self.findings
        ):
            raise ValueError("compact_grader_major_defect_without_finding")
        if not self.major_defect and any(
            item.severity == "major" for item in self.findings
        ):
            raise ValueError("compact_grader_major_finding_without_defect")
        return self


class CompactGraderReviewV2(CompactGraderDraftV2):
    review_version: Literal["v3.compact_screening_grader_review.2"] = (
        "v3.compact_screening_grader_review.2"
    )
    weighted_score: float = Field(ge=0.0, le=1.0)
    professional_plausibility: Literal["pass", "fail"]
    effective_rubric_dimensions: Literal[7] = 7

    @model_validator(mode="after")
    def validate_programmed_fields(self) -> "CompactGraderReviewV2":
        scores = self.scores.by_criterion_id()
        expected = round(
            sum(
                (scores[criterion_id] / 4.0) * weight
                for criterion_id, weight in RUBRIC_WEIGHTS.items()
            ),
            6,
        )
        if abs(expected - self.weighted_score) > 1e-6:
            raise ValueError("compact_grader_weighted_score_mismatch")
        expected_plausibility = (
            "pass"
            if expected >= 0.625 and not self.major_defect
            else "fail"
        )
        if self.professional_plausibility != expected_plausibility:
            raise ValueError(
                "compact_grader_professional_plausibility_mismatch"
            )
        return self


class CompactGraderBindingV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    motif: str
    replicate_id: Literal["a", "b"]
    domain: Optional[
        Literal["audit_compliance", "procurement_operations"]
    ] = None
    candidate_package_path: str
    teacher_package_path: str
    solver_outcome_sha256: str = Field(min_length=64, max_length=64)
    delivery_path: str
    delivery_sha256: str = Field(min_length=64, max_length=64)
    rubric_sha256: str = Field(min_length=64, max_length=64)
    fact_anchors_sha256: str = Field(min_length=64, max_length=64)


class CompactGraderScopeV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_version: Literal[
        "v3.compact_screening_grader_scope.2",
        "v3.compact_screening_grader_scope.2.1",
        "v3.compact_screening_grader_scope.3",
        "v3.compact_screening_grader_scope.3.1",
    ] = (
        "v3.compact_screening_grader_scope.2.1"
    )
    campaign_id: str
    cohort_kind: Literal[
        "matched_screening",
        "representative_production_pilot",
    ] = "matched_screening"
    solver_manifest_path: str
    solver_manifest_sha256: str = Field(min_length=64, max_length=64)
    parity_report_path: str
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    deepseek_reasoning_mode: Literal["high", "disabled"] = "high"
    output_contract: Literal[
        "compact_scores_findings_v2",
        "compact_scores_findings_v2_1",
    ] = (
        "compact_scores_findings_v2_1"
    )
    maximum_input_tokens_per_call: Literal[20000] = 20000
    maximum_completion_tokens_per_call: Literal[2000, 4000] = 4000
    maximum_attempts_per_task: Literal[2] = 2
    sdk_retries: Literal[0] = 0
    substantive_regrading_for_low_score: Literal[False] = False
    authorized_by_standing_user_permission: Literal[True] = True
    bindings: List[CompactGraderBindingV2] = Field(
        min_length=12, max_length=24
    )
    training_authorized: Literal[False] = False
    confirmation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_scope(self) -> "CompactGraderScopeV2":
        version_contract = (
            self.scope_version,
            self.output_contract,
            self.maximum_completion_tokens_per_call,
        )
        if version_contract not in {
            (
                "v3.compact_screening_grader_scope.2",
                "compact_scores_findings_v2",
                2000,
            ),
            (
                "v3.compact_screening_grader_scope.2.1",
                "compact_scores_findings_v2_1",
                4000,
            ),
            (
                "v3.compact_screening_grader_scope.3",
                "compact_scores_findings_v2_1",
                4000,
            ),
            (
                "v3.compact_screening_grader_scope.3.1",
                "compact_scores_findings_v2_1",
                4000,
            ),
        }:
            raise ValueError("compact_grader_scope_version_contract_mismatch")
        expected = (
            24
            if self.cohort_kind == "representative_production_pilot"
            else 12
        )
        if len(self.bindings) != expected or len(
            {item.blind_task_id for item in self.bindings}
        ) != expected:
            raise ValueError("compact_grader_task_matrix_size_mismatch")
        if self.cohort_kind == "matched_screening":
            cells = {
                (item.route_id, item.motif, item.replicate_id)
                for item in self.bindings
            }
            if self.scope_version in {
                "v3.compact_screening_grader_scope.3",
                "v3.compact_screening_grader_scope.3.1",
            }:
                raise ValueError("compact_grader_scope_v3_requires_representative")
            if len(cells) != 12 or any(
                item.domain is not None for item in self.bindings
            ):
                raise ValueError("compact_grader_matched_cells_incomplete")
            if self.deepseek_reasoning_mode != "high":
                raise ValueError(
                    "compact_grader_matched_reasoning_mismatch"
                )
        else:
            cells = {
                (
                    item.domain,
                    item.route_id,
                    item.motif,
                    item.replicate_id,
                )
                for item in self.bindings
            }
            if (
                self.scope_version not in {
                    "v3.compact_screening_grader_scope.3",
                    "v3.compact_screening_grader_scope.3.1",
                }
                or len(cells) != 24
                or any(item.domain is None for item in self.bindings)
            ):
                raise ValueError(
                    "compact_grader_representative_cells_incomplete"
                )
            expected_reasoning = (
                "disabled"
                if self.scope_version
                == "v3.compact_screening_grader_scope.3.1"
                else "high"
            )
            if self.deepseek_reasoning_mode != expected_reasoning:
                raise ValueError(
                    "compact_grader_representative_reasoning_mismatch"
                )
        return self


class CompactGraderRecordV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    status: Literal[
        "not_started",
        "running",
        "completed",
        "infrastructure_failed",
        "interrupted",
    ] = "not_started"
    attempt_count: int = Field(ge=0, le=2)
    review_path: Optional[str] = None
    review_sha256: Optional[str] = None
    first_failure_path: Optional[str] = None
    attempt_artifacts: Dict[str, str] = Field(default_factory=dict)


class CompactGraderManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.compact_screening_grader_manifest.2"] = (
        "v3.compact_screening_grader_manifest.2"
    )
    scope_path: str
    scope_sha256: str
    status: Literal["prepared", "running", "completed", "incomplete"]
    task_records: Dict[str, CompactGraderRecordV2]
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: str
    updated_at: str


class RepresentativeScreeningObservationV1(
    ScreeningTaskObservationV1
):
    domain: Literal["audit_compliance", "procurement_operations"]


class RepresentativeRouteSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    task_count: Literal[12] = 12
    offline_validity_count: int = Field(ge=0, le=12)
    exact_valid_delivery_count: int = Field(ge=0, le=12)
    major_defect_count: int = Field(ge=0, le=12)
    professional_plausibility_count: int = Field(ge=0, le=12)
    productive_complexity_count: int = Field(ge=0, le=12)
    skill_causal_count: int = Field(ge=0, le=12)
    saturation_count: int = Field(ge=0, le=12)
    absolute_gate_pass: bool


class RepresentativeDomainSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Literal["audit_compliance", "procurement_operations"]
    task_count: Literal[12] = 12
    completed_grade_count: int = Field(ge=0, le=12)
    professional_plausibility_count: int = Field(ge=0, le=12)
    major_defect_count: int = Field(ge=0, le=12)
    mean_weighted_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )


class RepresentativeScreeningResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal[
        "v3.representative_screening_result.1"
    ] = "v3.representative_screening_result.1"
    campaign_id: str
    observations: List[RepresentativeScreeningObservationV1] = Field(
        min_length=24, max_length=24
    )
    route_summaries: List[RepresentativeRouteSummaryV1] = Field(
        min_length=2, max_length=2
    )
    domain_summaries: List[RepresentativeDomainSummaryV1] = Field(
        min_length=2, max_length=2
    )
    comparable_pair_count: int = Field(ge=0, le=12)
    decision: Literal[
        "production_candidate_both",
        "single_route_production_candidate",
        "redesign_required",
        "incomplete",
    ]
    professional_validity_status: Literal[
        "provisional_ai_assumed_sufficient_for_pilot"
    ] = "provisional_ai_assumed_sufficient_for_pilot"
    expert_evidence_present: Literal[False] = False
    training_admission_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class CompactScreeningOutcomeV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_version: Literal["v3.compact_screening_outcome.2"] = (
        "v3.compact_screening_outcome.2"
    )
    campaign_id: str
    completed_grades: int
    infrastructure_failed_grades: int
    provider_calls: int
    score_distribution: Dict[str, int]
    screening_result: Union[
        MatchedScreeningResultV1, RepresentativeScreeningResultV1
    ]
    professional_validity_status: Literal["provisional"] = "provisional"
    expert_evidence_present: Literal[False] = False
    training_authorized: Literal[False] = False
    confirmation_authorized: Literal[False] = False


def _compact_rubric(path: Path) -> dict:
    rubric = json.loads(path.read_text(encoding="utf-8"))
    criteria = rubric.get("criteria") or rubric.get("rubric_plan", {}).get(
        "criteria", []
    )
    return {
        "criteria": [
            {
                key: item.get(key)
                for key in (
                    "criterion_id",
                    "weight",
                    "observable_behavior",
                    "independent_failure_signal",
                    "evidence_requirements",
                    "partial_score_bands",
                )
                if item.get(key) is not None
            }
            for item in criteria
        ]
    }


def compile_compact_grader_scope(
    *,
    campaign_root: str | Path,
    solver_execution_root: str | Path,
    output_root: str | Path,
    parity_report_path: str | Path,
    repository_root: str | Path,
    deepseek_reasoning_mode: Literal["high", "disabled"] = "high",
) -> tuple[CompactGraderScopeV2, Path, str]:
    campaign_dir = Path(campaign_root).resolve()
    solver_root = Path(solver_execution_root).resolve()
    destination = Path(output_root).resolve()
    parity_path = Path(parity_report_path).resolve()
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    fingerprint = governed_source_fingerprint(repository_root)
    if (
        not parity.get("passed")
        or parity.get("source_fingerprint") != fingerprint
        or parity.get("network_mode") != "none"
        or not parity.get("read_only_root")
        or parity.get("provider_credentials_mounted")
    ):
        raise ValueError("compact_grader_parity_not_eligible")
    representative_path = (
        campaign_dir / "representative_codex_campaign.json"
    )
    if representative_path.exists():
        campaign_path = representative_path
        cohort_kind = "representative_production_pilot"
        expected_tasks = 24
        candidate_base = (
            campaign_dir
            / "reality"
            / "blind_staging"
            / "candidate_packages"
        )
    else:
        campaign_path = campaign_dir / "matched_screening_campaign.json"
        cohort_kind = "matched_screening"
        expected_tasks = 12
        candidate_base = (
            campaign_dir / "blind_staging" / "candidate_packages"
        )
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    solver_manifest_path = solver_root / "codex_local_campaign_manifest.json"
    solver_manifest = CodexLocalCampaignManifestV1.model_validate_json(
        solver_manifest_path.read_text(encoding="utf-8")
    )
    if len(solver_manifest.task_outcome_paths) != expected_tasks:
        raise ValueError("compact_grader_solver_outcomes_incomplete")
    assignments = {
        item["blind_task_id"]: item for item in campaign["assignments"]
    }
    bindings: List[CompactGraderBindingV2] = []
    for task_id in sorted(assignments):
        assignment = assignments[task_id]
        outcome_path = Path(solver_manifest.task_outcome_paths[task_id])
        outcome = CodexLocalProcessOutcomeV1.model_validate_json(
            outcome_path.read_text(encoding="utf-8")
        )
        if outcome.status != "pass" or not outcome.delivery.valid:
            raise ValueError("compact_grader_delivery_not_eligible")
        delivery = Path(outcome.workspace_path) / outcome.delivery.relative_path
        if _sha_file(delivery) != outcome.delivery.sha256:
            raise ValueError("compact_grader_delivery_drift")
        teacher_root = Path(assignment["package_root"]).resolve()
        candidate_root = (candidate_base / task_id).resolve()
        rubric_path = teacher_root / "teacher" / "rubric_plan_v2.json"
        anchors_path = (
            teacher_root / "teacher" / "deterministic_fact_anchors.json"
        )
        bindings.append(
            CompactGraderBindingV2(
                blind_task_id=task_id,
                route_id=assignment["route_id"],
                motif=assignment["motif"],
                replicate_id=assignment["replicate_id"],
                domain=assignment.get("domain"),
                candidate_package_path=str(candidate_root),
                teacher_package_path=str(teacher_root),
                solver_outcome_sha256=_sha_file(outcome_path),
                delivery_path=str(delivery),
                delivery_sha256=_sha_file(delivery),
                rubric_sha256=_sha_file(rubric_path),
                fact_anchors_sha256=_sha_file(anchors_path),
            )
        )
    scope = CompactGraderScopeV2(
        scope_version=(
            (
                "v3.compact_screening_grader_scope.3.1"
                if deepseek_reasoning_mode == "disabled"
                else "v3.compact_screening_grader_scope.3"
            )
            if cohort_kind == "representative_production_pilot"
            else "v3.compact_screening_grader_scope.2.1"
        ),
        campaign_id=campaign["campaign_id"],
        cohort_kind=cohort_kind,
        deepseek_reasoning_mode=deepseek_reasoning_mode,
        solver_manifest_path=str(solver_manifest_path),
        solver_manifest_sha256=_sha_file(solver_manifest_path),
        parity_report_path=str(parity_path),
        parity_report_sha256=_sha_file(parity_path),
        source_fingerprint=fingerprint,
        bindings=bindings,
    )
    payload = (
        json.dumps(
            scope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    scope_path = destination / "governance" / "scopes" / f"{digest}.json"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    if scope_path.exists() and scope_path.read_bytes() != payload:
        raise ValueError("compact_grader_scope_immutable_collision")
    scope_path.write_bytes(payload)
    manifest_path = destination / "compact_grader_manifest.json"
    if not manifest_path.exists():
        manifest = CompactGraderManifestV2(
            scope_path=str(scope_path),
            scope_sha256=digest,
            status="prepared",
            task_records={
                item.blind_task_id: CompactGraderRecordV2(
                    blind_task_id=item.blind_task_id, attempt_count=0
                )
                for item in bindings
            },
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
    return scope, scope_path, digest


class CompactScreeningGraderV2:
    SYSTEM_PROMPT = (
        "You are grading a route-blind professional XLSX. Return only the "
        "compact JSON schema. Score all seven dimensions 0-4. Use 3 for a "
        "professionally adequate deliverable that meets the explicit contract. "
        "Use 4 only for exceptional value beyond the explicit contract; "
        "completeness or matching fact anchors alone never earns 4, and every "
        "4 requires one exceptional_evidence entry. Use 2 when material rework "
        "is needed, 1 for a major deficiency, and 0 when absent or wrong. "
        "Every score <=2 requires a concise finding. Return at most five "
        "findings and at most two exceptional_evidence entries. Do not write "
        "per-criterion rationales, a total score, professional plausibility, "
        "or route identity."
    )

    def __init__(
        self,
        *,
        scope_path: str | Path,
        output_root: str | Path,
        provider_config: ProviderConfig,
        grader_call=None,
    ) -> None:
        self.scope_path = Path(scope_path).resolve()
        self.output = Path(output_root).resolve()
        self.scope = CompactGraderScopeV2.model_validate_json(
            self.scope_path.read_text(encoding="utf-8")
        )
        if _sha_file(self.scope_path) != self.scope_path.stem:
            raise PermissionError("compact_grader_scope_hash_mismatch")
        self.config = provider_config
        self.grader_call = grader_call
        if (
            provider_config.provider_name != self.scope.provider
            or provider_config.model != self.scope.model
            or provider_config.reasoning_mode
            != self.scope.deepseek_reasoning_mode
        ):
            raise PermissionError("compact_grader_provider_mismatch")

    def execute(self) -> tuple[CompactScreeningOutcomeV2, Path]:
        manifest_path = self.output / "compact_grader_manifest.json"
        manifest = CompactGraderManifestV2.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if manifest.scope_sha256 != self.scope_path.stem:
            raise PermissionError("compact_grader_manifest_scope_mismatch")
        if _sha_file(Path(self.scope.solver_manifest_path)) != (
            self.scope.solver_manifest_sha256
        ):
            raise PermissionError("compact_grader_solver_manifest_drift")
        if governed_source_fingerprint(
            Path(__file__).resolve().parents[2]
        ) != self.scope.source_fingerprint:
            raise PermissionError("compact_grader_source_fingerprint_drift")
        for record in manifest.task_records.values():
            if record.status == "running":
                record.status = "interrupted"
                manifest.status = "incomplete"
                manifest.updated_at = _now()
                _atomic_json(manifest_path, manifest.model_dump(mode="json"))
                raise PermissionError("compact_grader_interrupted_task_frozen")
        if manifest.status not in {"prepared", "running"}:
            if not manifest.result_path:
                raise PermissionError("compact_grader_terminal_without_result")
            outcome = CompactScreeningOutcomeV2.model_validate_json(
                Path(manifest.result_path).read_text(encoding="utf-8")
            )
            return outcome, Path(manifest.result_path)
        manifest.status = "running"
        manifest.updated_at = _now()
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        provider_calls = 0
        by_task = {item.blind_task_id: item for item in self.scope.bindings}
        for task_id in sorted(by_task):
            record = manifest.task_records[task_id]
            if record.status == "completed":
                continue
            if record.status != "not_started":
                continue
            record.status = "running"
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
            record, calls = self._grade_one(by_task[task_id])
            provider_calls += calls
            manifest.task_records[task_id] = record
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        outcome = self._aggregate(manifest, provider_calls)
        result_path = self.output / "compact_screening_outcome_v2.json"
        _atomic_json(result_path, outcome.model_dump(mode="json"))
        manifest.result_path = str(result_path)
        manifest.result_sha256 = _sha_file(result_path)
        manifest.status = (
            "incomplete"
            if outcome.screening_result.decision == "incomplete"
            else "completed"
        )
        manifest.updated_at = _now()
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        return outcome, result_path

    def _validate_binding(self, binding: CompactGraderBindingV2) -> None:
        teacher_root = Path(binding.teacher_package_path)
        if _sha_file(Path(binding.delivery_path)) != binding.delivery_sha256:
            raise PermissionError("compact_grader_delivery_drift")
        if _sha_file(
            teacher_root / "teacher" / "rubric_plan_v2.json"
        ) != binding.rubric_sha256:
            raise PermissionError("compact_grader_rubric_drift")
        if _sha_file(
            teacher_root / "teacher" / "deterministic_fact_anchors.json"
        ) != binding.fact_anchors_sha256:
            raise PermissionError("compact_grader_fact_anchors_drift")

    def _payload(self, binding: CompactGraderBindingV2) -> dict:
        self._validate_binding(binding)
        candidate_root = Path(binding.candidate_package_path)
        teacher_root = Path(binding.teacher_package_path)
        executor = SemanticReviewExecutor(
            self.config,
            max_tokens=self.scope.maximum_completion_tokens_per_call,
            input_token_hard_limit=self.scope.maximum_input_tokens_per_call,
            max_retries=0,
        )
        return {
            "blind_task_id": binding.blind_task_id,
            "candidate_prompt": json.loads(
                (candidate_root / "dataset_row.json").read_text(
                    encoding="utf-8"
                )
            )["prompt"],
            "scoring_anchors": {
                "0": "absent or wrong",
                "1": "major deficiency",
                "2": "material rework required",
                "3": "professionally adequate and contract-complete",
                "4": "exceptional value beyond the explicit contract",
            },
            "rubric": _compact_rubric(
                teacher_root / "teacher" / "rubric_plan_v2.json"
            ),
            "fact_anchors": json.loads(
                (
                    teacher_root
                    / "teacher"
                    / "deterministic_fact_anchors.json"
                ).read_text(encoding="utf-8")
            ),
            "deliverable": executor._xlsx_content(
                Path(binding.delivery_path)
            ),
        }

    def _grade_one(
        self, binding: CompactGraderBindingV2
    ) -> tuple[CompactGraderRecordV2, int]:
        executor = SemanticReviewExecutor(
            self.config,
            max_tokens=self.scope.maximum_completion_tokens_per_call,
            input_token_hard_limit=self.scope.maximum_input_tokens_per_call,
            max_retries=0,
        )
        payload = self._payload(binding)
        record = CompactGraderRecordV2(
            blind_task_id=binding.blind_task_id,
            status="running",
            attempt_count=0,
        )
        provider_calls = 0
        feedback = None
        for attempt in (1, 2):
            record.attempt_count = attempt
            attempt_root = self.output / "grader" / binding.blind_task_id
            raw_path = attempt_root / f"attempt_{attempt}.raw.txt"
            diagnostics_path = (
                attempt_root / f"attempt_{attempt}.diagnostics.json"
            )
            try:
                if self.grader_call:
                    draft = self.grader_call(
                        payload, self.SYSTEM_PROMPT, feedback
                    )
                    if not isinstance(draft, CompactGraderDraftV2):
                        draft = CompactGraderDraftV2.model_validate(draft)
                    raw = draft.model_dump_json()
                    diagnostics = {"mock": True}
                else:
                    draft = executor._call(
                        self.SYSTEM_PROMPT,
                        payload,
                        CompactGraderDraftV2,
                        {"blind_task_id": binding.blind_task_id},
                        format_feedback=feedback,
                    )
                    raw = executor.last_raw_response_content
                    diagnostics = executor.last_diagnostics
                provider_calls += 1
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(raw, encoding="utf-8")
                _atomic_json(diagnostics_path, diagnostics)
                record.attempt_artifacts[str(raw_path)] = _sha_file(raw_path)
                record.attempt_artifacts[str(diagnostics_path)] = _sha_file(
                    diagnostics_path
                )
                by_id = draft.scores.by_criterion_id()
                weighted = round(
                    sum(
                        (by_id[criterion_id] / 4.0) * weight
                        for criterion_id, weight in RUBRIC_WEIGHTS.items()
                    ),
                    6,
                )
                review = CompactGraderReviewV2(
                    **draft.model_dump(mode="json"),
                    weighted_score=weighted,
                    professional_plausibility=(
                        "pass"
                        if weighted >= 0.625 and not draft.major_defect
                        else "fail"
                    ),
                )
                review_path = attempt_root / "review.json"
                _atomic_json(review_path, review.model_dump(mode="json"))
                record.status = "completed"
                record.review_path = str(review_path)
                record.review_sha256 = _sha_file(review_path)
                return record, provider_calls
            except Exception as exc:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                if not raw_path.exists():
                    raw_path.write_text(
                        getattr(executor, "last_raw_response_content", ""),
                        encoding="utf-8",
                    )
                diagnostics = {
                    "error_type": type(exc).__name__,
                    "failure_code": getattr(
                        exc, "failure_code", "schema_failure"
                    ),
                    **getattr(executor, "last_diagnostics", {}),
                }
                _atomic_json(diagnostics_path, diagnostics)
                record.attempt_artifacts[str(raw_path)] = _sha_file(raw_path)
                record.attempt_artifacts[str(diagnostics_path)] = _sha_file(
                    diagnostics_path
                )
                if getattr(exc, "failure_code", None) != "input_token_ceiling":
                    provider_calls += 1
                if attempt == 1:
                    record.first_failure_path = str(diagnostics_path)
                eligible = isinstance(
                    exc, (SemanticReviewExecutionError, ValueError)
                ) and (
                    not isinstance(exc, SemanticReviewExecutionError)
                    or exc.retry_eligible
                    or exc.failure_code
                    in {
                        "invalid_json",
                        "schema_failure",
                        "empty_response",
                        "truncated_response",
                    }
                )
                if attempt == 1 and eligible:
                    feedback = (
                        "Return only compact valid JSON. Keep the same "
                        "substantive scores and findings; satisfy every "
                        "score/finding/exceptional-evidence invariant."
                    )
                    continue
                record.status = "infrastructure_failed"
                return record, provider_calls
        raise AssertionError("unreachable")

    def _aggregate(
        self, manifest: CompactGraderManifestV2, provider_calls: int
    ) -> CompactScreeningOutcomeV2:
        bindings = {item.blind_task_id: item for item in self.scope.bindings}
        observations: List[ScreeningTaskObservationV1] = []
        score_distribution: Dict[str, int] = {}
        for task_id in sorted(bindings):
            binding = bindings[task_id]
            record = manifest.task_records[task_id]
            teacher_root = Path(binding.teacher_package_path)
            validity = ValidityVectorV1.model_validate_json(
                (
                    teacher_root / "governance" / "validity_vector.json"
                ).read_text(encoding="utf-8")
            )
            utility = UtilityProfileV1.model_validate_json(
                (
                    teacher_root / "governance" / "utility_profile.json"
                ).read_text(encoding="utf-8")
            )
            review = (
                CompactGraderReviewV2.model_validate_json(
                    Path(record.review_path).read_text(encoding="utf-8")
                )
                if record.review_path
                else None
            )
            if review:
                bucket = f"{review.weighted_score:.3f}"
                score_distribution[bucket] = (
                    score_distribution.get(bucket, 0) + 1
                )
            observations.append(
                ScreeningTaskObservationV1(
                    blind_task_id=task_id,
                    route_id=binding.route_id,
                    motif=binding.motif,
                    replicate_id=binding.replicate_id,
                    infrastructure_complete=record.status == "completed",
                    offline_validity_pass=validity.overall_status != "blocked",
                    exact_valid_delivery=True,
                    major_defect=review.major_defect if review else False,
                    professional_plausibility_pass=(
                        review.professional_plausibility == "pass"
                        if review
                        else False
                    ),
                    productive_complexity_pass=(
                        utility.productive_complexity_coverage == 1.0
                        and all(
                            item.status != "blocked"
                            for item in utility.productive_complexity
                        )
                    ),
                    skill_causal_pass=utility.skill_causal_coverage == 1.0,
                    effective_rubric_dimensions=(
                        review.effective_rubric_dimensions if review else 0
                    ),
                    weighted_score=review.weighted_score if review else None,
                )
            )
        screening = (
            self._analyze_representative(observations)
            if self.scope.cohort_kind == "representative_production_pilot"
            else MatchedScreeningAnalyzer().analyze(
                self.scope.campaign_id, observations
            )
        )
        completed = sum(
            item.status == "completed"
            for item in manifest.task_records.values()
        )
        return CompactScreeningOutcomeV2(
            campaign_id=self.scope.campaign_id,
            completed_grades=completed,
            infrastructure_failed_grades=len(self.scope.bindings) - completed,
            provider_calls=provider_calls,
            score_distribution=score_distribution,
            screening_result=screening,
        )

    def _analyze_representative(
        self, observations: List[ScreeningTaskObservationV1]
    ) -> RepresentativeScreeningResultV1:
        bindings = {
            item.blind_task_id: item for item in self.scope.bindings
        }
        rows = [
            RepresentativeScreeningObservationV1(
                **item.model_dump(mode="json"),
                domain=bindings[item.blind_task_id].domain,
            )
            for item in observations
        ]
        if len(rows) != 24 or len(
            {item.blind_task_id for item in rows}
        ) != 24:
            raise ValueError(
                "representative_screening_requires_twenty_four_tasks"
            )
        route_summaries: List[RepresentativeRouteSummaryV1] = []
        route_passes: Dict[str, bool] = {}
        for route in ("skill_guided_llm", "llm_led_hybrid"):
            route_rows = [item for item in rows if item.route_id == route]
            if len(route_rows) != 12:
                raise ValueError(
                    "representative_screening_requires_twelve_per_route"
                )
            saturation = sum(
                item.weighted_score is not None
                and item.weighted_score >= 0.9
                for item in route_rows
            )
            gate = (
                sum(item.offline_validity_pass for item in route_rows) == 12
                and sum(item.exact_valid_delivery for item in route_rows)
                >= 10
                and sum(item.major_defect for item in route_rows) == 0
                and sum(
                    item.professional_plausibility_pass
                    for item in route_rows
                )
                >= 10
                and sum(
                    item.productive_complexity_pass
                    for item in route_rows
                )
                >= 10
                and sum(item.skill_causal_pass for item in route_rows) == 12
                and all(
                    item.effective_rubric_dimensions >= 5
                    for item in route_rows
                    if item.exact_valid_delivery
                )
                and saturation <= 8
            )
            route_passes[route] = gate
            route_summaries.append(
                RepresentativeRouteSummaryV1(
                    route_id=route,
                    offline_validity_count=sum(
                        item.offline_validity_pass for item in route_rows
                    ),
                    exact_valid_delivery_count=sum(
                        item.exact_valid_delivery for item in route_rows
                    ),
                    major_defect_count=sum(
                        item.major_defect for item in route_rows
                    ),
                    professional_plausibility_count=sum(
                        item.professional_plausibility_pass
                        for item in route_rows
                    ),
                    productive_complexity_count=sum(
                        item.productive_complexity_pass
                        for item in route_rows
                    ),
                    skill_causal_count=sum(
                        item.skill_causal_pass for item in route_rows
                    ),
                    saturation_count=saturation,
                    absolute_gate_pass=gate,
                )
            )
        domain_summaries: List[RepresentativeDomainSummaryV1] = []
        for domain in ("audit_compliance", "procurement_operations"):
            domain_rows = [item for item in rows if item.domain == domain]
            scores = [
                item.weighted_score
                for item in domain_rows
                if item.infrastructure_complete
                and item.weighted_score is not None
            ]
            if len(domain_rows) != 12:
                raise ValueError(
                    "representative_screening_requires_twelve_per_domain"
                )
            domain_summaries.append(
                RepresentativeDomainSummaryV1(
                    domain=domain,
                    completed_grade_count=sum(
                        item.infrastructure_complete for item in domain_rows
                    ),
                    professional_plausibility_count=sum(
                        item.professional_plausibility_pass
                        for item in domain_rows
                    ),
                    major_defect_count=sum(
                        item.major_defect for item in domain_rows
                    ),
                    mean_weighted_score=(
                        round(sum(scores) / len(scores), 6)
                        if scores
                        else None
                    ),
                )
            )
        pairs: Dict[tuple[str, str, str], set[str]] = {}
        for item in rows:
            if item.infrastructure_complete and item.weighted_score is not None:
                pairs.setdefault(
                    (item.domain, item.motif, item.replicate_id), set()
                ).add(item.route_id)
        comparable = sum(
            routes == {"skill_guided_llm", "llm_led_hybrid"}
            for routes in pairs.values()
        )
        if any(not item.infrastructure_complete for item in rows):
            decision = "incomplete"
        else:
            passing = sum(route_passes.values())
            if passing == 2 and comparable >= 10:
                decision = "production_candidate_both"
            elif passing == 1:
                decision = "single_route_production_candidate"
            else:
                decision = "redesign_required"
        return RepresentativeScreeningResultV1(
            campaign_id=self.scope.campaign_id,
            observations=rows,
            route_summaries=route_summaries,
            domain_summaries=domain_summaries,
            comparable_pair_count=comparable,
            decision=decision,
        )
