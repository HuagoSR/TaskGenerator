from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_codex_local_solver import _atomic_json, _now, _sha_file
from task_generator.v3_compact_screening_grader import (
    CRITERION_IDS,
    CompactGraderBindingV2,
    CompactGraderDraftV2,
    CompactGraderReviewV2,
    CompactGraderScopeV2,
    CompactScreeningOutcomeV2,
    _compact_rubric,
)
from task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
)
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_source_fingerprint import governed_source_fingerprint


CALIBRATION_REPLICATE_BY_CELL = {
    ("skill_guided_llm", "fan_in_reconciliation"): "a",
    ("skill_guided_llm", "cross_check_validation"): "b",
    ("skill_guided_llm", "policy_application"): "b",
    ("llm_led_hybrid", "fan_in_reconciliation"): "b",
    ("llm_led_hybrid", "cross_check_validation"): "a",
    ("llm_led_hybrid", "policy_application"): "a",
}


class ProfessionalCalibrationBindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    motif: Literal[
        "fan_in_reconciliation",
        "cross_check_validation",
        "policy_application",
    ]
    replicate_id: Literal["a", "b"]
    candidate_package_path: str
    teacher_package_path: str
    delivery_path: str
    delivery_sha256: str = Field(min_length=64, max_length=64)
    rubric_sha256: str = Field(min_length=64, max_length=64)
    fact_anchors_sha256: str = Field(min_length=64, max_length=64)
    compact_review_path: str
    compact_review_sha256: str = Field(min_length=64, max_length=64)


class ProfessionalCalibrationScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_version: Literal["v3.professional_calibration_scope.1"] = (
        "v3.professional_calibration_scope.1"
    )
    campaign_id: str
    compact_scope_path: str
    compact_scope_sha256: str = Field(min_length=64, max_length=64)
    compact_outcome_path: str
    compact_outcome_sha256: str = Field(min_length=64, max_length=64)
    parity_report_path: str
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    provider: Literal["tuzi"] = "tuzi"
    model: Literal["gemini-3.1-pro-preview"] = "gemini-3.1-pro-preview"
    reviewer_kind: Literal["llm_proxy"] = "llm_proxy"
    prior_review_visible_to_provider: Literal[False] = False
    maximum_input_tokens_per_call: Literal[20000] = 20000
    maximum_completion_tokens_per_call: Literal[2500] = 2500
    maximum_attempts_per_task: Literal[2] = 2
    sdk_retries: Literal[0] = 0
    bindings: List[ProfessionalCalibrationBindingV1] = Field(
        min_length=6, max_length=6
    )
    training_authorized: Literal[False] = False
    confirmation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_stratification(self) -> "ProfessionalCalibrationScopeV1":
        if len({item.blind_task_id for item in self.bindings}) != 6:
            raise ValueError("professional_calibration_requires_six_unique_tasks")
        if {
            (item.route_id, item.motif) for item in self.bindings
        } != set(CALIBRATION_REPLICATE_BY_CELL):
            raise ValueError("professional_calibration_strata_incomplete")
        return self


class ProfessionalCalibrationComparisonV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    independent_scores: Dict[str, int]
    compact_scores: Dict[str, int]
    criterion_deltas: Dict[str, int]
    exact_dimension_agreement_count: int = Field(ge=0, le=7)
    mean_absolute_delta: float = Field(ge=0.0, le=4.0)
    maximum_absolute_delta: int = Field(ge=0, le=4)
    independent_professional_plausibility: Literal["pass", "fail"]
    compact_professional_plausibility: Literal["pass", "fail"]
    professional_plausibility_agrees: bool
    independent_major_defect: bool
    compact_major_defect: bool
    major_defect_agrees: bool


class ProfessionalCalibrationRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    status: Literal[
        "not_started",
        "running",
        "completed",
        "infrastructure_failed",
        "interrupted",
    ]
    attempt_count: int = Field(ge=0, le=2)
    independent_review_path: Optional[str] = None
    independent_review_sha256: Optional[str] = None
    comparison_path: Optional[str] = None
    comparison_sha256: Optional[str] = None
    first_failure: Optional[Dict[str, object]] = None
    attempt_artifacts: Dict[str, str] = Field(default_factory=dict)


class ProfessionalCalibrationManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.professional_calibration_manifest.1"] = (
        "v3.professional_calibration_manifest.1"
    )
    scope_path: str
    scope_sha256: str = Field(min_length=64, max_length=64)
    status: Literal["running", "completed", "incomplete"]
    task_records: Dict[str, ProfessionalCalibrationRecordV1]
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: str
    updated_at: str


class ProfessionalCalibrationResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["v3.professional_calibration_result.1"] = (
        "v3.professional_calibration_result.1"
    )
    campaign_id: str
    completed_reviews: int
    infrastructure_failed_reviews: int
    provider_calls: int
    controlled_format_retries: int
    professional_plausibility_agreement_count: int
    major_defect_agreement_count: int
    exact_dimension_agreement_count: int
    total_dimension_comparisons: Literal[42] = 42
    mean_absolute_criterion_delta: float
    maximum_absolute_criterion_delta: int
    decision: Literal[
        "calibration_consistent",
        "calibration_divergent",
        "incomplete",
    ]
    reviewer_kind: Literal["llm_proxy"] = "llm_proxy"
    professional_validity_status: Literal["provisional"] = "provisional"
    training_authorized: Literal[False] = False
    confirmation_authorized: Literal[False] = False


def _weighted_score(review: CompactGraderDraftV2) -> float:
    weights = {
        "criterion_factual_accuracy": 0.20,
        "criterion_evidence_traceability": 0.15,
        "criterion_method_process": 0.15,
        "criterion_exception_handling": 0.15,
        "criterion_reproducibility": 0.15,
        "criterion_structural_usability": 0.10,
        "criterion_professional_expression": 0.10,
    }
    values = review.scores.by_criterion_id()
    return round(
        sum((values[key] / 4.0) * weight for key, weight in weights.items()),
        6,
    )


def _write_immutable_scope(
    scope: ProfessionalCalibrationScopeV1,
    destination: Path,
) -> tuple[Path, str]:
    payload = (
        json.dumps(
            scope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    path = destination / "governance" / "scopes" / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("professional_calibration_scope_immutable_collision")
    path.write_bytes(payload)
    return path, digest


def compile_professional_calibration_scope(
    *,
    compact_scope_path: str | Path,
    compact_outcome_path: str | Path,
    parity_report_path: str | Path,
    output_root: str | Path,
    repository_root: str | Path,
) -> tuple[ProfessionalCalibrationScopeV1, Path, str]:
    compact_scope_file = Path(compact_scope_path).resolve()
    compact_outcome_file = Path(compact_outcome_path).resolve()
    parity_file = Path(parity_report_path).resolve()
    destination = Path(output_root).resolve()
    compact_scope = CompactGraderScopeV2.model_validate_json(
        compact_scope_file.read_text(encoding="utf-8")
    )
    if compact_scope.scope_version != "v3.compact_screening_grader_scope.2.1":
        raise ValueError("professional_calibration_requires_compact_v2_1")
    compact_outcome = CompactScreeningOutcomeV2.model_validate_json(
        compact_outcome_file.read_text(encoding="utf-8")
    )
    if (
        compact_outcome.completed_grades != 12
        or compact_outcome.infrastructure_failed_grades != 0
        or compact_outcome.screening_result.decision
        != "confirmation_ready_both"
    ):
        raise ValueError("professional_calibration_compact_outcome_ineligible")
    parity = json.loads(parity_file.read_text(encoding="utf-8"))
    fingerprint = governed_source_fingerprint(repository_root)
    if (
        not parity.get("passed")
        or parity.get("source_fingerprint") != fingerprint
        or parity.get("network_mode") != "none"
        or not parity.get("read_only_root")
        or parity.get("provider_credentials_mounted")
    ):
        raise ValueError("professional_calibration_parity_not_eligible")
    by_cell = {
        (item.route_id, item.motif, item.replicate_id): item
        for item in compact_scope.bindings
    }
    review_paths = {
        item.blind_task_id: Path(
            compact_outcome_file.parent
            / "grader"
            / item.blind_task_id
            / "review.json"
        ).resolve()
        for item in compact_scope.bindings
    }
    bindings: List[ProfessionalCalibrationBindingV1] = []
    for (route, motif), replicate in CALIBRATION_REPLICATE_BY_CELL.items():
        item: CompactGraderBindingV2 = by_cell[(route, motif, replicate)]
        review_path = review_paths[item.blind_task_id]
        review = CompactGraderReviewV2.model_validate_json(
            review_path.read_text(encoding="utf-8")
        )
        if review.route_identity_seen:
            raise ValueError("professional_calibration_prior_route_leak")
        bindings.append(
            ProfessionalCalibrationBindingV1(
                blind_task_id=item.blind_task_id,
                route_id=item.route_id,
                motif=item.motif,
                replicate_id=item.replicate_id,
                candidate_package_path=item.candidate_package_path,
                teacher_package_path=item.teacher_package_path,
                delivery_path=item.delivery_path,
                delivery_sha256=item.delivery_sha256,
                rubric_sha256=item.rubric_sha256,
                fact_anchors_sha256=item.fact_anchors_sha256,
                compact_review_path=str(review_path),
                compact_review_sha256=_sha_file(review_path),
            )
        )
    if {
        (item.route_id, item.motif) for item in bindings
    } != set(CALIBRATION_REPLICATE_BY_CELL):
        raise ValueError("professional_calibration_strata_incomplete")
    scope = ProfessionalCalibrationScopeV1(
        campaign_id=compact_scope.campaign_id,
        compact_scope_path=str(compact_scope_file),
        compact_scope_sha256=_sha_file(compact_scope_file),
        compact_outcome_path=str(compact_outcome_file),
        compact_outcome_sha256=_sha_file(compact_outcome_file),
        parity_report_path=str(parity_file),
        parity_report_sha256=_sha_file(parity_file),
        source_fingerprint=fingerprint,
        bindings=sorted(bindings, key=lambda item: item.blind_task_id),
    )
    path, digest = _write_immutable_scope(scope, destination)
    return scope, path, digest


class ProfessionalCalibrationRunnerV1:
    SYSTEM_PROMPT = """
You are an independent route-blind professional reviewer of spreadsheet work.
Judge only the candidate requirements, frozen scoring anchors, fact anchors,
and actual workbook content supplied here. You have not been given another reviewer's scores.
Use 3 for professionally adequate, contract-complete work;
4 requires concrete value beyond the explicit contract; 2 or below requires
a concise finding. Return only the requested JSON. Never infer or name a
generation route. Do not provide a total score.
""".strip()

    def __init__(
        self,
        *,
        scope_path: str | Path,
        output_root: str | Path,
        provider_config: ProviderConfig,
    ) -> None:
        self.scope_path = Path(scope_path).resolve()
        self.output = Path(output_root).resolve()
        self.scope = ProfessionalCalibrationScopeV1.model_validate_json(
            self.scope_path.read_text(encoding="utf-8")
        )
        if _sha_file(self.scope_path) != self.scope_path.stem:
            raise PermissionError("professional_calibration_scope_sha_mismatch")
        if (
            provider_config.provider_name != self.scope.provider
            or provider_config.model != self.scope.model
        ):
            raise PermissionError("professional_calibration_provider_mismatch")
        repository_root = Path(__file__).resolve().parents[2]
        if governed_source_fingerprint(repository_root) != self.scope.source_fingerprint:
            raise PermissionError("professional_calibration_source_drift")
        if _sha_file(Path(self.scope.compact_scope_path)) != self.scope.compact_scope_sha256:
            raise PermissionError("professional_calibration_compact_scope_drift")
        if _sha_file(Path(self.scope.compact_outcome_path)) != self.scope.compact_outcome_sha256:
            raise PermissionError("professional_calibration_compact_outcome_drift")
        if _sha_file(Path(self.scope.parity_report_path)) != self.scope.parity_report_sha256:
            raise PermissionError("professional_calibration_parity_drift")
        parity = json.loads(
            Path(self.scope.parity_report_path).read_text(encoding="utf-8")
        )
        if (
            not parity.get("passed")
            or parity.get("source_fingerprint") != self.scope.source_fingerprint
            or parity.get("network_mode") != "none"
            or not parity.get("read_only_root")
            or parity.get("provider_credentials_mounted")
        ):
            raise PermissionError("professional_calibration_parity_ineligible")
        self.config = provider_config
        self.manifest_path = self.output / "professional_calibration_manifest.json"

    def _validate_binding(self, item: ProfessionalCalibrationBindingV1) -> None:
        teacher = Path(item.teacher_package_path)
        if _sha_file(Path(item.delivery_path)) != item.delivery_sha256:
            raise PermissionError("professional_calibration_delivery_drift")
        if _sha_file(teacher / "teacher" / "rubric_plan_v2.json") != item.rubric_sha256:
            raise PermissionError("professional_calibration_rubric_drift")
        if _sha_file(
            teacher / "teacher" / "deterministic_fact_anchors.json"
        ) != item.fact_anchors_sha256:
            raise PermissionError("professional_calibration_fact_anchors_drift")
        if _sha_file(Path(item.compact_review_path)) != item.compact_review_sha256:
            raise PermissionError("professional_calibration_review_drift")

    def _payload(
        self,
        item: ProfessionalCalibrationBindingV1,
        executor: SemanticReviewExecutor,
    ) -> Dict[str, object]:
        self._validate_binding(item)
        candidate = Path(item.candidate_package_path)
        teacher = Path(item.teacher_package_path)
        return {
            "blind_task_id": item.blind_task_id,
            "candidate_prompt": json.loads(
                (candidate / "dataset_row.json").read_text(encoding="utf-8")
            )["prompt"],
            "scoring_anchors": {
                "0": "absent or wrong",
                "1": "major deficiency",
                "2": "material rework required",
                "3": "professionally adequate and contract-complete",
                "4": "exceptional value beyond the explicit contract",
            },
            "rubric": _compact_rubric(
                teacher / "teacher" / "rubric_plan_v2.json"
            ),
            "fact_anchors": json.loads(
                (
                    teacher / "teacher" / "deterministic_fact_anchors.json"
                ).read_text(encoding="utf-8")
            ),
            "deliverable": executor._xlsx_content(Path(item.delivery_path)),
        }

    def _comparison(
        self,
        independent: CompactGraderDraftV2,
        compact: CompactGraderReviewV2,
    ) -> ProfessionalCalibrationComparisonV1:
        independent_scores = independent.scores.by_criterion_id()
        compact_scores = compact.scores.by_criterion_id()
        deltas = {
            key: independent_scores[key] - compact_scores[key]
            for key in CRITERION_IDS
        }
        independent_weighted = _weighted_score(independent)
        independent_plausibility = (
            "pass"
            if independent_weighted >= 0.625 and not independent.major_defect
            else "fail"
        )
        return ProfessionalCalibrationComparisonV1(
            blind_task_id=independent.blind_task_id,
            independent_scores=independent_scores,
            compact_scores=compact_scores,
            criterion_deltas=deltas,
            exact_dimension_agreement_count=sum(value == 0 for value in deltas.values()),
            mean_absolute_delta=round(
                sum(abs(value) for value in deltas.values()) / 7.0, 6
            ),
            maximum_absolute_delta=max(abs(value) for value in deltas.values()),
            independent_professional_plausibility=independent_plausibility,
            compact_professional_plausibility=compact.professional_plausibility,
            professional_plausibility_agrees=(
                independent_plausibility == compact.professional_plausibility
            ),
            independent_major_defect=independent.major_defect,
            compact_major_defect=compact.major_defect,
            major_defect_agrees=independent.major_defect == compact.major_defect,
        )

    def execute(self) -> tuple[ProfessionalCalibrationResultV1, Path]:
        if self.manifest_path.exists():
            prior = ProfessionalCalibrationManifestV1.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
            if prior.status != "running":
                raise PermissionError("professional_calibration_scope_already_consumed")
            for record in prior.task_records.values():
                if record.status == "running":
                    record.status = "interrupted"
                    prior.status = "incomplete"
                    prior.updated_at = _now()
                    _atomic_json(
                        self.manifest_path, prior.model_dump(mode="json")
                    )
                    raise PermissionError(
                        "professional_calibration_interrupted_task_frozen"
                    )
            manifest = prior
        else:
            now = _now()
            manifest = ProfessionalCalibrationManifestV1(
                scope_path=str(self.scope_path),
                scope_sha256=_sha_file(self.scope_path),
                status="running",
                task_records={
                    item.blind_task_id: ProfessionalCalibrationRecordV1(
                        blind_task_id=item.blind_task_id,
                        status="not_started",
                        attempt_count=0,
                    )
                    for item in self.scope.bindings
                },
                created_at=now,
                updated_at=now,
            )
            _atomic_json(self.manifest_path, manifest.model_dump(mode="json"))
        provider_calls = sum(
            record.attempt_count for record in manifest.task_records.values()
        )
        comparisons: List[ProfessionalCalibrationComparisonV1] = []
        for item in self.scope.bindings:
            record = manifest.task_records[item.blind_task_id]
            if record.status == "completed":
                comparisons.append(
                    ProfessionalCalibrationComparisonV1.model_validate_json(
                        Path(record.comparison_path).read_text(encoding="utf-8")
                    )
                )
                continue
            if record.status != "not_started":
                continue
            record.status = "running"
            manifest.updated_at = _now()
            _atomic_json(self.manifest_path, manifest.model_dump(mode="json"))
            executor = SemanticReviewExecutor(
                self.config,
                max_tokens=self.scope.maximum_completion_tokens_per_call,
                input_token_hard_limit=self.scope.maximum_input_tokens_per_call,
                max_retries=0,
            )
            payload = self._payload(item, executor)
            feedback = None
            completed = False
            for attempt in (1, 2):
                record.attempt_count = attempt
                task_root = self.output / "reviews" / item.blind_task_id
                raw_path = task_root / f"attempt_{attempt}.raw.txt"
                diagnostics_path = task_root / f"attempt_{attempt}.diagnostics.json"
                try:
                    independent = executor._call(
                        self.SYSTEM_PROMPT,
                        payload,
                        CompactGraderDraftV2,
                        {"blind_task_id": item.blind_task_id},
                        format_feedback=feedback,
                    )
                    provider_calls += 1
                    task_root.mkdir(parents=True, exist_ok=True)
                    raw_path.write_text(
                        executor.last_raw_response_content, encoding="utf-8"
                    )
                    _atomic_json(diagnostics_path, executor.last_diagnostics)
                    review_path = task_root / "independent_review.json"
                    _atomic_json(
                        review_path, independent.model_dump(mode="json")
                    )
                    compact = CompactGraderReviewV2.model_validate_json(
                        Path(item.compact_review_path).read_text(encoding="utf-8")
                    )
                    comparison = self._comparison(independent, compact)
                    comparison_path = task_root / "comparison.json"
                    _atomic_json(
                        comparison_path, comparison.model_dump(mode="json")
                    )
                    record.status = "completed"
                    record.independent_review_path = str(review_path)
                    record.independent_review_sha256 = _sha_file(review_path)
                    record.comparison_path = str(comparison_path)
                    record.comparison_sha256 = _sha_file(comparison_path)
                    comparisons.append(comparison)
                    completed = True
                    break
                except Exception as exc:
                    provider_calls += 1
                    task_root.mkdir(parents=True, exist_ok=True)
                    raw_path.write_text(
                        executor.last_raw_response_content or "",
                        encoding="utf-8",
                    )
                    diagnostics = dict(executor.last_diagnostics)
                    diagnostics.update(
                        {
                            "error_type": type(exc).__name__,
                            "failure_code": getattr(
                                exc, "failure_code", "schema_failure"
                            ),
                        }
                    )
                    _atomic_json(diagnostics_path, diagnostics)
                    if record.first_failure is None:
                        record.first_failure = {
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                            "failure_code": diagnostics["failure_code"],
                        }
                    retry_eligible = (
                        isinstance(exc, SemanticReviewExecutionError)
                        and exc.retry_eligible
                    ) or type(exc).__name__ == "ValidationError"
                    if attempt == 1 and retry_eligible:
                        feedback = (
                            "The previous response failed the required JSON "
                            "format. Return one complete schema-valid JSON object."
                        )
                        continue
                    record.status = "infrastructure_failed"
                    break
            record.attempt_artifacts = {
                str(path): _sha_file(path)
                for path in sorted(
                    (self.output / "reviews" / item.blind_task_id).glob(
                        "attempt_*.*"
                    )
                )
            }
            manifest.updated_at = _now()
            _atomic_json(self.manifest_path, manifest.model_dump(mode="json"))
            if not completed and record.status == "infrastructure_failed":
                continue
        completed_count = sum(
            record.status == "completed"
            for record in manifest.task_records.values()
        )
        failed_count = sum(
            record.status == "infrastructure_failed"
            for record in manifest.task_records.values()
        )
        if completed_count != 6 or failed_count:
            decision = "incomplete"
        else:
            plausibility_agreement = sum(
                item.professional_plausibility_agrees for item in comparisons
            )
            major_agreement = sum(
                item.major_defect_agrees for item in comparisons
            )
            mean_delta = sum(
                sum(abs(value) for value in item.criterion_deltas.values())
                for item in comparisons
            ) / 42.0
            maximum_delta = max(
                abs(value)
                for item in comparisons
                for value in item.criterion_deltas.values()
            )
            decision = (
                "calibration_consistent"
                if plausibility_agreement >= 5
                and major_agreement == 6
                and mean_delta <= 0.5
                and maximum_delta <= 1
                else "calibration_divergent"
            )
        result = ProfessionalCalibrationResultV1(
            campaign_id=self.scope.campaign_id,
            completed_reviews=completed_count,
            infrastructure_failed_reviews=failed_count,
            provider_calls=provider_calls,
            controlled_format_retries=sum(
                max(record.attempt_count - 1, 0)
                for record in manifest.task_records.values()
            ),
            professional_plausibility_agreement_count=sum(
                item.professional_plausibility_agrees for item in comparisons
            ),
            major_defect_agreement_count=sum(
                item.major_defect_agrees for item in comparisons
            ),
            exact_dimension_agreement_count=sum(
                item.exact_dimension_agreement_count for item in comparisons
            ),
            mean_absolute_criterion_delta=round(
                (
                    sum(
                        sum(
                            abs(value)
                            for value in item.criterion_deltas.values()
                        )
                        for item in comparisons
                    )
                    / 42.0
                )
                if comparisons
                else 0.0,
                6,
            ),
            maximum_absolute_criterion_delta=(
                max(
                    abs(value)
                    for item in comparisons
                    for value in item.criterion_deltas.values()
                )
                if comparisons
                else 0
            ),
            decision=decision,
        )
        result_path = self.output / "professional_calibration_result.json"
        _atomic_json(result_path, result.model_dump(mode="json"))
        manifest.status = "completed" if decision != "incomplete" else "incomplete"
        manifest.result_path = str(result_path)
        manifest.result_sha256 = _sha_file(result_path)
        manifest.updated_at = _now()
        _atomic_json(self.manifest_path, manifest.model_dump(mode="json"))
        return result, result_path
