from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_codex_local_solver import (
    CodexLocalCLIIdentityV1,
    CodexLocalTooling,
    _atomic_json,
    _build_command,
    _now,
    _projection_tree,
    _sanitized_environment,
    _sha_file,
    _terminate_process_tree,
    parse_codex_jsonl,
)
from task_generator.v3_compact_screening_grader import (
    CompactGraderBindingV2,
    CompactGraderDraftV2,
    CompactGraderReviewV2,
    RepresentativeDomainSummaryV1,
    RepresentativeRouteSummaryV1,
    RepresentativeScreeningObservationV1,
    RepresentativeScreeningResultV1,
)
from task_generator.v3_matched_screening import (
    RUBRIC_WEIGHTS,
    ScreeningTaskObservationV1,
)
from task_generator.v3_source_fingerprint import governed_source_fingerprint
from task_generator.v3_validity_utility import (
    UtilityProfileV1,
    ValidityVectorV1,
)


class CodexLocalGraderScopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_version: Literal["v3.codex_local_grader_scope.1"] = (
        "v3.codex_local_grader_scope.1"
    )
    campaign_id: str
    upstream_compact_scope_path: str
    upstream_compact_scope_sha256: str = Field(
        min_length=64, max_length=64
    )
    solver_manifest_sha256: str = Field(min_length=64, max_length=64)
    parity_report_path: str
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    cli: CodexLocalCLIIdentityV1
    model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    evidence_kind: Literal["same_model_behavioral_proxy"] = (
        "same_model_behavioral_proxy"
    )
    timeout_seconds_per_task: Literal[1800] = 1800
    attempts_per_task: Literal[1] = 1
    bindings: List[CompactGraderBindingV2] = Field(
        min_length=24, max_length=24
    )
    independent_model_evidence: Literal[False] = False
    expert_evidence_present: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_matrix(self) -> "CodexLocalGraderScopeV1":
        if len({item.blind_task_id for item in self.bindings}) != 24:
            raise ValueError("codex_local_grader_requires_unique_tasks")
        cells = {
            (
                item.domain,
                item.route_id,
                item.motif,
                item.replicate_id,
            )
            for item in self.bindings
        }
        if len(cells) != 24 or any(
            item.domain is None for item in self.bindings
        ):
            raise ValueError("codex_local_grader_matrix_incomplete")
        return self


class CodexLocalGradeRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    status: Literal[
        "not_started",
        "running",
        "completed",
        "interrupted",
        "infrastructure_failed",
        "grading_failed",
    ] = "not_started"
    attempt_count: int = Field(ge=0, le=1)
    workspace_path: Optional[str] = None
    jsonl_path: Optional[str] = None
    stderr_path: Optional[str] = None
    raw_grade_path: Optional[str] = None
    review_path: Optional[str] = None
    review_sha256: Optional[str] = None
    duration_seconds: Optional[float] = None
    first_failure: Optional[str] = None


class CodexLocalGraderManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.codex_local_grader_manifest.1"] = (
        "v3.codex_local_grader_manifest.1"
    )
    scope_path: str
    scope_sha256: str = Field(min_length=64, max_length=64)
    status: Literal["prepared", "running", "completed", "incomplete"]
    records: Dict[str, CodexLocalGradeRecordV1]
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: str
    updated_at: str


class CodexLocalGraderOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_version: Literal["v3.codex_local_grader_outcome.1"] = (
        "v3.codex_local_grader_outcome.1"
    )
    campaign_id: str
    evidence_kind: Literal["same_model_behavioral_proxy"] = (
        "same_model_behavioral_proxy"
    )
    completed_grades: int
    infrastructure_failed_grades: int
    grading_failed_grades: int
    total_process_seconds: float
    score_distribution: Dict[str, int]
    screening_result: RepresentativeScreeningResultV1
    independent_model_evidence: Literal[False] = False
    expert_evidence_present: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class RouteConvergenceMetricsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    task_count: Literal[12] = 12
    mean_weighted_score: float
    minimum_weighted_score: float
    maximum_weighted_score: float
    matched_pair_wins: int = Field(ge=0, le=12)
    matched_pair_losses: int = Field(ge=0, le=12)
    matched_pair_ties: int = Field(ge=0, le=12)
    candidate_workbook_count: int = Field(ge=1)
    candidate_workbook_bytes: int = Field(ge=1)
    candidate_projection_sha256: str = Field(min_length=64, max_length=64)


class RepresentativeRouteConvergenceReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.representative_route_convergence.1"] = (
        "v3.representative_route_convergence.1"
    )
    campaign_id: str
    grader_outcome_sha256: str = Field(min_length=64, max_length=64)
    grader_manifest_sha256: str = Field(min_length=64, max_length=64)
    solver_manifest_sha256: str = Field(min_length=64, max_length=64)
    representative_campaign_sha256: str = Field(
        min_length=64, max_length=64
    )
    evidence_kind: Literal["same_model_behavioral_proxy"] = (
        "same_model_behavioral_proxy"
    )
    quality_comparable: Literal[True] = True
    score_mean_gap: float
    matched_pair_count: Literal[12] = 12
    routes: List[RouteConvergenceMetricsV1] = Field(
        min_length=2, max_length=2
    )
    recommendation: Literal["llm_led_hybrid"]
    challenger: Literal["skill_guided_llm"]
    rationale_codes: List[
        Literal[
            "both_routes_pass_absolute_gates",
            "score_gap_within_0_025",
            "matched_wins_near_even",
            "llm_led_candidate_workbooks_at_least_25_percent_lower",
            "llm_led_candidate_bytes_at_least_25_percent_lower",
        ]
    ] = Field(min_length=5, max_length=5)
    professional_validity: Literal[
        "provisional_ai_assumed_sufficient_for_pilot"
    ] = "provisional_ai_assumed_sufficient_for_pilot"
    default_generator_change_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    release_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class CandidateDataAdmissionRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    route_role: Literal["production_candidate", "challenger_control"]
    domain: Literal["audit_compliance", "procurement_operations"]
    motif: str
    replicate_id: Literal["a", "b"]
    package_fingerprint: str = Field(min_length=64, max_length=64)
    candidate_tree_sha256: str = Field(min_length=64, max_length=64)
    reality_evidence_sha256: str = Field(min_length=64, max_length=64)
    delivery_sha256: str = Field(min_length=64, max_length=64)
    grader_review_sha256: str = Field(min_length=64, max_length=64)
    weighted_score: float = Field(ge=0.0, le=1.0)
    source_bound: Literal[True] = True
    candidate_teacher_isolated: Literal[True] = True
    reality_screened: Literal[True] = True
    exact_delivery_valid: Literal[True] = True
    structured_grade_valid: Literal[True] = True
    admission_status: Literal["candidate_pool_admitted"] = (
        "candidate_pool_admitted"
    )


class CandidateDataAdmissionManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.candidate_data_admission.1"] = (
        "v3.candidate_data_admission.1"
    )
    campaign_id: str
    representative_campaign_sha256: str = Field(
        min_length=64, max_length=64
    )
    grader_outcome_sha256: str = Field(min_length=64, max_length=64)
    grader_manifest_sha256: str = Field(min_length=64, max_length=64)
    route_convergence_report_sha256: str = Field(
        min_length=64, max_length=64
    )
    package_readiness_sha256: str = Field(min_length=64, max_length=64)
    reality_result_sha256: str = Field(min_length=64, max_length=64)
    solver_manifest_sha256: str = Field(min_length=64, max_length=64)
    admitted_record_count: Literal[24] = 24
    production_candidate_record_count: Literal[12] = 12
    challenger_control_record_count: Literal[12] = 12
    records: List[CandidateDataAdmissionRecordV1] = Field(
        min_length=24, max_length=24
    )
    permitted_future_export_components: List[
        Literal[
            "candidate_prompt",
            "candidate_reference_files",
            "solver_deliverable",
            "structured_grader_feedback",
        ]
    ] = Field(min_length=4, max_length=4)
    prohibited_export_components: List[
        Literal[
            "teacher_only_rubric",
            "deterministic_fact_anchors",
            "codex_jsonl",
            "hidden_reasoning",
            "authentication_material",
        ]
    ] = Field(min_length=5, max_length=5)
    evidence_kind: Literal["same_model_behavioral_proxy"] = (
        "same_model_behavioral_proxy"
    )
    professional_validity: Literal[
        "provisional_ai_assumed_sufficient_for_pilot"
    ] = "provisional_ai_assumed_sufficient_for_pilot"
    human_expert_review_present: Literal[False] = False
    exported_training_example_count: Literal[0] = 0
    dataset_export_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    training_started: Literal[False] = False
    release_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_admission_matrix(self) -> "CandidateDataAdmissionManifestV1":
        if (
            len({item.blind_task_id for item in self.records}) != 24
            or sum(
                item.route_role == "production_candidate"
                for item in self.records
            )
            != 12
            or sum(
                item.route_role == "challenger_control"
                for item in self.records
            )
            != 12
            or any(
                (
                    item.route_id == "llm_led_hybrid"
                    and item.route_role != "production_candidate"
                )
                or (
                    item.route_id == "skill_guided_llm"
                    and item.route_role != "challenger_control"
                )
                for item in self.records
            )
        ):
            raise ValueError("candidate_data_admission_matrix_invalid")
        return self


def _canonical_scope(scope: CodexLocalGraderScopeV1) -> bytes:
    return (
        json.dumps(
            scope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _candidate_projection(
    assignments: list[dict],
    route_id: str,
) -> tuple[int, int, str]:
    projection = []
    for assignment in assignments:
        if assignment["route_id"] != route_id:
            continue
        package_root = Path(assignment["package_root"]).resolve()
        reference_root = package_root / "candidate" / "reference_files"
        workbooks = sorted(reference_root.glob("*.xlsx"))
        if not workbooks:
            raise ValueError("route_convergence_candidate_workbooks_missing")
        for workbook in workbooks:
            projection.append(
                {
                    "blind_task_id": assignment["blind_task_id"],
                    "relative_path": workbook.relative_to(
                        package_root
                    ).as_posix(),
                    "sha256": _sha_file(workbook),
                    "bytes": workbook.stat().st_size,
                }
            )
    encoded = (
        json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return (
        len(projection),
        sum(item["bytes"] for item in projection),
        hashlib.sha256(encoded).hexdigest(),
    )


def compile_route_convergence_report(
    *,
    grader_outcome_path: str | Path,
    grader_manifest_path: str | Path,
    representative_campaign_path: str | Path,
    output_path: str | Path,
) -> tuple[RepresentativeRouteConvergenceReportV1, Path]:
    outcome_path = Path(grader_outcome_path).resolve()
    manifest_path = Path(grader_manifest_path).resolve()
    campaign_path = Path(representative_campaign_path).resolve()
    outcome = CodexLocalGraderOutcomeV1.model_validate_json(
        outcome_path.read_text(encoding="utf-8")
    )
    manifest = CodexLocalGraderManifestV1.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    assignments = campaign.get("assignments", [])
    observations = outcome.screening_result.observations
    if not (
        outcome.completed_grades == 24
        and outcome.infrastructure_failed_grades == 0
        and outcome.grading_failed_grades == 0
        and outcome.screening_result.decision == "production_candidate_both"
        and outcome.screening_result.comparable_pair_count == 12
        and len(observations) == 24
        and len(assignments) == 24
        and manifest.status == "completed"
        and manifest.result_sha256 == _sha_file(outcome_path)
        and {item.blind_task_id for item in observations}
        == {item["blind_task_id"] for item in assignments}
        and all(item.absolute_gate_pass for item in outcome.screening_result.route_summaries)
    ):
        raise ValueError("route_convergence_evidence_incomplete")
    scope = CodexLocalGraderScopeV1.model_validate_json(
        Path(manifest.scope_path).read_text(encoding="utf-8")
    )
    if manifest.scope_sha256 != _sha_file(Path(manifest.scope_path)):
        raise ValueError("route_convergence_scope_drift")

    by_cell: Dict[tuple[str, str, str], Dict[str, float]] = {}
    scores: Dict[str, List[float]] = {
        "skill_guided_llm": [],
        "llm_led_hybrid": [],
    }
    for item in observations:
        if item.weighted_score is None:
            raise ValueError("route_convergence_score_missing")
        scores[item.route_id].append(item.weighted_score)
        by_cell.setdefault(
            (item.domain, item.motif, item.replicate_id), {}
        )[item.route_id] = item.weighted_score
    if len(by_cell) != 12 or any(len(value) != 2 for value in by_cell.values()):
        raise ValueError("route_convergence_pairs_incomplete")

    wins = {"skill_guided_llm": 0, "llm_led_hybrid": 0}
    ties = 0
    for pair in by_cell.values():
        skill = pair["skill_guided_llm"]
        llm = pair["llm_led_hybrid"]
        if skill > llm:
            wins["skill_guided_llm"] += 1
        elif llm > skill:
            wins["llm_led_hybrid"] += 1
        else:
            ties += 1

    metrics = []
    for route_id in ("skill_guided_llm", "llm_led_hybrid"):
        workbook_count, workbook_bytes, projection_sha = (
            _candidate_projection(assignments, route_id)
        )
        route_scores = scores[route_id]
        metrics.append(
            RouteConvergenceMetricsV1(
                route_id=route_id,
                mean_weighted_score=round(
                    sum(route_scores) / len(route_scores), 6
                ),
                minimum_weighted_score=min(route_scores),
                maximum_weighted_score=max(route_scores),
                matched_pair_wins=wins[route_id],
                matched_pair_losses=12 - wins[route_id] - ties,
                matched_pair_ties=ties,
                candidate_workbook_count=workbook_count,
                candidate_workbook_bytes=workbook_bytes,
                candidate_projection_sha256=projection_sha,
            )
        )
    by_route = {item.route_id: item for item in metrics}
    score_gap = round(
        abs(
            by_route["skill_guided_llm"].mean_weighted_score
            - by_route["llm_led_hybrid"].mean_weighted_score
        ),
        6,
    )
    skill = by_route["skill_guided_llm"]
    llm = by_route["llm_led_hybrid"]
    if not (
        score_gap <= 0.025
        and abs(skill.matched_pair_wins - llm.matched_pair_wins) <= 2
        and llm.candidate_workbook_count <= skill.candidate_workbook_count * 0.75
        and llm.candidate_workbook_bytes <= skill.candidate_workbook_bytes * 0.75
    ):
        raise ValueError("route_convergence_tie_break_not_satisfied")
    report = RepresentativeRouteConvergenceReportV1(
        campaign_id=outcome.campaign_id,
        grader_outcome_sha256=_sha_file(outcome_path),
        grader_manifest_sha256=_sha_file(manifest_path),
        solver_manifest_sha256=scope.solver_manifest_sha256,
        representative_campaign_sha256=_sha_file(campaign_path),
        score_mean_gap=score_gap,
        routes=metrics,
        recommendation="llm_led_hybrid",
        challenger="skill_guided_llm",
        rationale_codes=[
            "both_routes_pass_absolute_gates",
            "score_gap_within_0_025",
            "matched_wins_near_even",
            "llm_led_candidate_workbooks_at_least_25_percent_lower",
            "llm_led_candidate_bytes_at_least_25_percent_lower",
        ],
    )
    destination = Path(output_path).resolve()
    _atomic_json(destination, report.model_dump(mode="json"))
    return report, destination


def compile_candidate_data_admission_manifest(
    *,
    grader_outcome_path: str | Path,
    grader_manifest_path: str | Path,
    representative_campaign_path: str | Path,
    route_convergence_report_path: str | Path,
    output_path: str | Path,
) -> tuple[CandidateDataAdmissionManifestV1, Path]:
    outcome_path = Path(grader_outcome_path).resolve()
    manifest_path = Path(grader_manifest_path).resolve()
    campaign_path = Path(representative_campaign_path).resolve()
    convergence_path = Path(route_convergence_report_path).resolve()
    outcome = CodexLocalGraderOutcomeV1.model_validate_json(
        outcome_path.read_text(encoding="utf-8")
    )
    grader_manifest = CodexLocalGraderManifestV1.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    grader_scope = CodexLocalGraderScopeV1.model_validate_json(
        Path(grader_manifest.scope_path).read_text(encoding="utf-8")
    )
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    convergence = RepresentativeRouteConvergenceReportV1.model_validate_json(
        convergence_path.read_text(encoding="utf-8")
    )
    if not (
        convergence.grader_outcome_sha256 == _sha_file(outcome_path)
        and convergence.grader_manifest_sha256 == _sha_file(manifest_path)
        and convergence.representative_campaign_sha256
        == _sha_file(campaign_path)
        and convergence.recommendation == "llm_led_hybrid"
        and outcome.screening_result.decision == "production_candidate_both"
        and outcome.completed_grades == 24
        and grader_manifest.status == "completed"
        and campaign.get("reality_decision") == "screening_ready"
        and campaign.get("training_authorized") is False
    ):
        raise ValueError("candidate_data_admission_upstream_invalid")
    assignments = {
        item["blind_task_id"]: item
        for item in campaign.get("assignments", [])
    }
    bindings = {
        item.blind_task_id: item for item in grader_scope.bindings
    }
    observations = {
        item.blind_task_id: item
        for item in outcome.screening_result.observations
    }
    if not (
        len(assignments) == len(bindings) == len(observations) == 24
        and set(assignments) == set(bindings) == set(observations)
    ):
        raise ValueError("candidate_data_admission_identity_mismatch")
    records = []
    for task_id in sorted(assignments):
        assignment = assignments[task_id]
        binding = bindings[task_id]
        observation = observations[task_id]
        grade_record = grader_manifest.records[task_id]
        package_root = Path(assignment["package_root"])
        candidate_manifest = json.loads(
            (
                package_root / "candidate" / "candidate_package_manifest.json"
            ).read_text(encoding="utf-8")
        )
        if not (
            candidate_manifest.get("teacher_artifacts_included") is False
            and candidate_manifest.get("reference_files")
            and grade_record.status == "completed"
            and grade_record.review_sha256
            and grade_record.review_path
            and _sha_file(Path(grade_record.review_path))
            == grade_record.review_sha256
            and _sha_file(Path(binding.delivery_path))
            == binding.delivery_sha256
            and observation.infrastructure_complete
            and observation.offline_validity_pass
            and observation.exact_valid_delivery
            and observation.professional_plausibility_pass
            and observation.productive_complexity_pass
            and observation.skill_causal_pass
            and not observation.major_defect
            and observation.weighted_score is not None
        ):
            raise ValueError("candidate_data_admission_record_invalid")
        records.append(
            CandidateDataAdmissionRecordV1(
                blind_task_id=task_id,
                route_id=assignment["route_id"],
                route_role=(
                    "production_candidate"
                    if assignment["route_id"] == "llm_led_hybrid"
                    else "challenger_control"
                ),
                domain=assignment["domain"],
                motif=assignment["motif"],
                replicate_id=assignment["replicate_id"],
                package_fingerprint=assignment["package_fingerprint"],
                candidate_tree_sha256=assignment["candidate_tree_sha256"],
                reality_evidence_sha256=assignment[
                    "reality_evidence_sha256"
                ],
                delivery_sha256=binding.delivery_sha256,
                grader_review_sha256=grade_record.review_sha256,
                weighted_score=observation.weighted_score,
            )
        )
    manifest = CandidateDataAdmissionManifestV1(
        campaign_id=outcome.campaign_id,
        representative_campaign_sha256=_sha_file(campaign_path),
        grader_outcome_sha256=_sha_file(outcome_path),
        grader_manifest_sha256=_sha_file(manifest_path),
        route_convergence_report_sha256=_sha_file(convergence_path),
        package_readiness_sha256=campaign["package_readiness_sha256"],
        reality_result_sha256=campaign["reality_result_sha256"],
        solver_manifest_sha256=grader_scope.solver_manifest_sha256,
        records=records,
        permitted_future_export_components=[
            "candidate_prompt",
            "candidate_reference_files",
            "solver_deliverable",
            "structured_grader_feedback",
        ],
        prohibited_export_components=[
            "teacher_only_rubric",
            "deterministic_fact_anchors",
            "codex_jsonl",
            "hidden_reasoning",
            "authentication_material",
        ],
    )
    destination = Path(output_path).resolve()
    _atomic_json(destination, manifest.model_dump(mode="json"))
    return manifest, destination


def compile_codex_local_grader_scope(
    *,
    upstream_compact_scope_path: str | Path,
    parity_report_path: str | Path,
    cli_identity: CodexLocalCLIIdentityV1,
    repository_root: str | Path,
    output_root: str | Path,
) -> tuple[CodexLocalGraderScopeV1, Path, str]:
    from task_generator.v3_compact_screening_grader import (
        CompactGraderScopeV2,
    )

    upstream_path = Path(upstream_compact_scope_path).resolve()
    upstream = CompactGraderScopeV2.model_validate_json(
        upstream_path.read_text(encoding="utf-8")
    )
    if (
        upstream.cohort_kind != "representative_production_pilot"
        or len(upstream.bindings) != 24
    ):
        raise ValueError("codex_local_grader_upstream_not_representative")
    parity_path = Path(parity_report_path).resolve()
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    fingerprint = governed_source_fingerprint(repository_root)
    if not (
        parity.get("passed") is True
        and parity.get("network_mode") == "none"
        and parity.get("read_only_root") is True
        and parity.get("provider_credentials_mounted") is False
        and parity.get("cleanup_returncode") == 0
        and parity.get("source_fingerprint") == fingerprint
    ):
        raise ValueError("codex_local_grader_parity_invalid")
    solver_manifest = Path(upstream.solver_manifest_path)
    if _sha_file(solver_manifest) != upstream.solver_manifest_sha256:
        raise ValueError("codex_local_grader_solver_manifest_drift")
    for binding in upstream.bindings:
        teacher = Path(binding.teacher_package_path)
        if (
            _sha_file(Path(binding.delivery_path))
            != binding.delivery_sha256
            or _sha_file(teacher / "teacher" / "rubric_plan_v2.json")
            != binding.rubric_sha256
            or _sha_file(
                teacher / "teacher" / "deterministic_fact_anchors.json"
            )
            != binding.fact_anchors_sha256
        ):
            raise ValueError("codex_local_grader_binding_drift")
    scope = CodexLocalGraderScopeV1(
        campaign_id=upstream.campaign_id,
        upstream_compact_scope_path=str(upstream_path),
        upstream_compact_scope_sha256=_sha_file(upstream_path),
        solver_manifest_sha256=upstream.solver_manifest_sha256,
        parity_report_path=str(parity_path),
        parity_report_sha256=_sha_file(parity_path),
        source_fingerprint=fingerprint,
        cli=cli_identity,
        bindings=upstream.bindings,
    )
    encoded = _canonical_scope(scope)
    import hashlib

    digest = hashlib.sha256(encoded).hexdigest()
    scope_path = (
        Path(output_root).resolve()
        / "governance"
        / "scopes"
        / f"{digest}.json"
    )
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    if scope_path.exists() and scope_path.read_bytes() != encoded:
        raise ValueError("codex_local_grader_scope_immutable_collision")
    scope_path.write_bytes(encoded)
    manifest_path = Path(output_root).resolve() / "grader_manifest.json"
    if not manifest_path.exists():
        manifest = CodexLocalGraderManifestV1(
            scope_path=str(scope_path),
            scope_sha256=digest,
            status="prepared",
            records={
                item.blind_task_id: CodexLocalGradeRecordV1(
                    blind_task_id=item.blind_task_id,
                    attempt_count=0,
                )
                for item in scope.bindings
            },
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
    return scope, scope_path, digest


def _grade_prompt(task_id: str, python_executable: Path) -> str:
    return f"""You are grading one route-blind professional XLSX work product.
Use shell commands and Python/openpyxl to inspect deliverable.xlsx. The Python executable is:
{python_executable}

Read candidate_prompt.json, rubric.json, fact_anchors.json and grade_schema.json.
Return only one JSON object matching grade_schema.json. The blind_task_id must be {task_id}.
Score all seven dimensions from 0 to 4. Score 3 means professionally adequate and contract-complete.
Score 4 is exceptional beyond the explicit contract and requires one exceptional_evidence entry for
that exact criterion. Every score 2 or lower requires a finding for that criterion. Keep every locator,
finding and exceptional-evidence string within the schema limits. Never infer or mention route identity.
Do not write or modify the XLSX.
"""


def _strict_output_schema(value):
    """Compile Pydantic JSON Schema into the strict Responses subset."""
    if isinstance(value, list):
        return [_strict_output_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {
        key: _strict_output_schema(item)
        for key, item in value.items()
        if key != "default"
    }
    properties = result.get("properties")
    if isinstance(properties, dict):
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


class CodexLocalGraderRunnerV1:
    def __init__(
        self,
        *,
        scope_path: str | Path,
        output_root: str | Path,
        codex_home: str | Path,
        python_executable: str | Path,
        popen_factory=subprocess.Popen,
    ) -> None:
        self.scope_path = Path(scope_path).resolve()
        self.output = Path(output_root).resolve()
        self.codex_home = Path(codex_home).resolve()
        self.python = Path(python_executable).resolve()
        self.popen_factory = popen_factory
        self.scope = CodexLocalGraderScopeV1.model_validate_json(
            self.scope_path.read_text(encoding="utf-8")
        )
        self._validate_static()

    def _validate_static(self) -> None:
        if _sha_file(self.scope_path) != self.scope_path.stem:
            raise PermissionError("codex_local_grader_scope_hash_mismatch")
        if governed_source_fingerprint(
            Path(__file__).resolve().parents[2]
        ) != self.scope.source_fingerprint:
            raise PermissionError(
                "codex_local_grader_source_fingerprint_drift"
            )
        executable = Path(self.scope.cli.executable_path)
        if (
            not executable.is_file()
            or _sha_file(executable) != self.scope.cli.executable_sha256
            or CodexLocalTooling(executable.parents[2]).freeze_identity()
            != self.scope.cli
        ):
            raise PermissionError("codex_local_grader_cli_drift")
        if not self.python.is_file():
            raise FileNotFoundError("codex_local_grader_python_missing")
        if _sha_file(Path(self.scope.upstream_compact_scope_path)) != (
            self.scope.upstream_compact_scope_sha256
        ):
            raise PermissionError("codex_local_grader_upstream_drift")
        for binding in self.scope.bindings:
            teacher = Path(binding.teacher_package_path)
            if (
                _sha_file(Path(binding.delivery_path))
                != binding.delivery_sha256
                or _sha_file(
                    teacher / "teacher" / "rubric_plan_v2.json"
                )
                != binding.rubric_sha256
                or _sha_file(
                    teacher
                    / "teacher"
                    / "deterministic_fact_anchors.json"
                )
                != binding.fact_anchors_sha256
            ):
                raise PermissionError("codex_local_grader_binding_drift")

    def execute(self) -> tuple[CodexLocalGraderOutcomeV1, Path]:
        manifest_path = self.output / "grader_manifest.json"
        manifest = CodexLocalGraderManifestV1.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        for record in manifest.records.values():
            if record.status == "running":
                record.status = "interrupted"
                manifest.status = "incomplete"
                manifest.updated_at = _now()
                _atomic_json(manifest_path, manifest.model_dump(mode="json"))
                raise PermissionError(
                    "codex_local_grader_interrupted_task_frozen"
                )
        if manifest.status not in {"prepared", "running"}:
            if not manifest.result_path:
                raise PermissionError(
                    "codex_local_grader_terminal_without_result"
                )
            return (
                CodexLocalGraderOutcomeV1.model_validate_json(
                    Path(manifest.result_path).read_text(encoding="utf-8")
                ),
                Path(manifest.result_path),
            )
        manifest.status = "running"
        manifest.updated_at = _now()
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        by_task = {
            item.blind_task_id: item for item in self.scope.bindings
        }
        for task_id in sorted(by_task):
            record = manifest.records[task_id]
            if record.status != "not_started":
                continue
            record.status = "running"
            record.attempt_count = 1
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
            manifest.records[task_id] = self._run_one(by_task[task_id])
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        outcome = self._aggregate(manifest)
        outcome_path = self.output / "codex_local_grader_outcome.json"
        _atomic_json(outcome_path, outcome.model_dump(mode="json"))
        manifest.status = (
            "completed"
            if outcome.screening_result.decision
            != "incomplete"
            else "incomplete"
        )
        manifest.result_path = str(outcome_path)
        manifest.result_sha256 = _sha_file(outcome_path)
        manifest.updated_at = _now()
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        return outcome, outcome_path

    def _workspace(self, binding: CompactGraderBindingV2) -> Path:
        workspace = self.output / "workspaces" / binding.blind_task_id
        workspace.mkdir(parents=True, exist_ok=True)
        candidate = Path(binding.candidate_package_path)
        teacher = Path(binding.teacher_package_path)
        _atomic_json(
            workspace / "candidate_prompt.json",
            {
                "blind_task_id": binding.blind_task_id,
                "prompt": json.loads(
                    (candidate / "dataset_row.json").read_text(
                        encoding="utf-8"
                    )
                )["prompt"],
            },
        )
        shutil.copy2(binding.delivery_path, workspace / "deliverable.xlsx")
        shutil.copy2(
            teacher / "teacher" / "rubric_plan_v2.json",
            workspace / "rubric.json",
        )
        shutil.copy2(
            teacher / "teacher" / "deterministic_fact_anchors.json",
            workspace / "fact_anchors.json",
        )
        _atomic_json(
            workspace / "grade_schema.json",
            _strict_output_schema(
                CompactGraderDraftV2.model_json_schema()
            ),
        )
        return workspace

    def _run_one(
        self, binding: CompactGraderBindingV2
    ) -> CodexLocalGradeRecordV1:
        workspace = self._workspace(binding)
        raw_grade = workspace / "grade.raw.json"
        command = _build_command(
            Path(self.scope.cli.executable_path), workspace
        )
        command[-1:-1] = [
            "--output-schema",
            str(workspace / "grade_schema.json"),
            "--output-last-message",
            str(raw_grade),
        ]
        started = time.monotonic()
        process = self.popen_factory(
            command,
            cwd=str(workspace),
            env=_sanitized_environment(self.codex_home),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
            start_new_session=os.name != "nt",
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(
                input=_grade_prompt(binding.blind_task_id, self.python),
                timeout=self.scope.timeout_seconds_per_task,
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            _terminate_process_tree(process)
            tail_out, tail_err = process.communicate()
            stdout = (exc.stdout or "") + (tail_out or "")
            stderr = (exc.stderr or "") + (tail_err or "")
        duration = round(time.monotonic() - started, 3)
        task_root = self.output / "grader" / binding.blind_task_id
        task_root.mkdir(parents=True, exist_ok=True)
        jsonl_path = task_root / "codex.jsonl"
        stderr_path = task_root / "stderr.txt"
        persisted_raw = task_root / "grade.raw.json"
        jsonl_path.write_text(stdout or "", encoding="utf-8")
        stderr_path.write_text(stderr or "", encoding="utf-8")
        if raw_grade.exists():
            shutil.copy2(raw_grade, persisted_raw)
        record = CodexLocalGradeRecordV1(
            blind_task_id=binding.blind_task_id,
            status="running",
            attempt_count=1,
            workspace_path=str(workspace),
            jsonl_path=str(jsonl_path),
            stderr_path=str(stderr_path),
            raw_grade_path=(
                str(persisted_raw) if persisted_raw.exists() else None
            ),
            duration_seconds=duration,
        )
        diagnostics = parse_codex_jsonl(stdout or "")
        combined = f"{stdout}\n{stderr}".lower()
        infrastructure = any(
            marker in combined
            for marker in (
                "authentication",
                "not logged in",
                "service unavailable",
                "connection refused",
                "failed to connect",
            )
        )
        if timed_out or infrastructure or (
            process.returncode not in (0, None) and not diagnostics.turn_seen
        ):
            record.status = "infrastructure_failed"
            record.first_failure = (
                "codex_local_grader_timeout"
                if timed_out
                else "codex_local_grader_infrastructure_failure"
            )
            return record
        if process.returncode != 0 or not persisted_raw.exists():
            record.status = "grading_failed"
            record.first_failure = "codex_local_grader_missing_grade"
            return record
        try:
            draft = CompactGraderDraftV2.model_validate_json(
                persisted_raw.read_text(encoding="utf-8")
            )
            if draft.blind_task_id != binding.blind_task_id:
                raise ValueError("codex_local_grader_task_identity_mismatch")
            scores = draft.scores.by_criterion_id()
            weighted = round(
                sum(
                    (scores[key] / 4.0) * RUBRIC_WEIGHTS[key]
                    for key in RUBRIC_WEIGHTS
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
            review_path = task_root / "review.json"
            _atomic_json(review_path, review.model_dump(mode="json"))
            record.status = "completed"
            record.review_path = str(review_path)
            record.review_sha256 = _sha_file(review_path)
        except Exception as exc:
            record.status = "grading_failed"
            record.first_failure = (
                f"codex_local_grader_schema_failure:{type(exc).__name__}"
            )
        return record

    def _aggregate(
        self, manifest: CodexLocalGraderManifestV1
    ) -> CodexLocalGraderOutcomeV1:
        bindings = {
            item.blind_task_id: item for item in self.scope.bindings
        }
        observations: List[RepresentativeScreeningObservationV1] = []
        score_distribution: Dict[str, int] = {}
        for task_id in sorted(bindings):
            binding = bindings[task_id]
            record = manifest.records[task_id]
            teacher = Path(binding.teacher_package_path)
            validity = ValidityVectorV1.model_validate_json(
                (
                    teacher / "governance" / "validity_vector.json"
                ).read_text(encoding="utf-8")
            )
            utility = UtilityProfileV1.model_validate_json(
                (
                    teacher / "governance" / "utility_profile.json"
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
                RepresentativeScreeningObservationV1(
                    blind_task_id=task_id,
                    route_id=binding.route_id,
                    motif=binding.motif,
                    replicate_id=binding.replicate_id,
                    domain=binding.domain,
                    infrastructure_complete=record.status == "completed",
                    offline_validity_pass=validity.overall_status
                    != "blocked",
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
                    weighted_score=(
                        review.weighted_score if review else None
                    ),
                )
            )
        screening = _analyze(self.scope.campaign_id, observations)
        return CodexLocalGraderOutcomeV1(
            campaign_id=self.scope.campaign_id,
            completed_grades=sum(
                item.status == "completed"
                for item in manifest.records.values()
            ),
            infrastructure_failed_grades=sum(
                item.status == "infrastructure_failed"
                for item in manifest.records.values()
            ),
            grading_failed_grades=sum(
                item.status == "grading_failed"
                for item in manifest.records.values()
            ),
            total_process_seconds=round(
                sum(
                    item.duration_seconds or 0.0
                    for item in manifest.records.values()
                ),
                3,
            ),
            score_distribution=score_distribution,
            screening_result=screening,
        )


def _analyze(
    campaign_id: str,
    rows: List[RepresentativeScreeningObservationV1],
) -> RepresentativeScreeningResultV1:
    route_summaries: List[RepresentativeRouteSummaryV1] = []
    route_passes: Dict[str, bool] = {}
    for route in ("skill_guided_llm", "llm_led_hybrid"):
        route_rows = [item for item in rows if item.route_id == route]
        saturation = sum(
            item.weighted_score is not None
            and item.weighted_score >= 0.9
            for item in route_rows
        )
        gate = (
            len(route_rows) == 12
            and sum(item.offline_validity_pass for item in route_rows) == 12
            and sum(item.exact_valid_delivery for item in route_rows) >= 10
            and sum(item.major_defect for item in route_rows) == 0
            and sum(
                item.professional_plausibility_pass for item in route_rows
            )
            >= 10
            and sum(item.productive_complexity_pass for item in route_rows)
            >= 10
            and sum(item.skill_causal_pass for item in route_rows) == 12
            and all(
                item.effective_rubric_dimensions >= 5
                for item in route_rows
                if item.infrastructure_complete
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
                    item.professional_plausibility_pass for item in route_rows
                ),
                productive_complexity_count=sum(
                    item.productive_complexity_pass for item in route_rows
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
        campaign_id=campaign_id,
        observations=rows,
        route_summaries=route_summaries,
        domain_summaries=domain_summaries,
        comparable_pair_count=comparable,
        decision=decision,
    )
