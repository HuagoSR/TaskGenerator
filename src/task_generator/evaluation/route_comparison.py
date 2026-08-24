from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.planning.task_design_frontend import CapabilityBriefV1
from task_generator.generation.rw_task_export_validator import RwTaskExportValidator


RouteId = Literal[
    "strict_template",
    "skill_guided_llm",
    "llm_led_hybrid",
]
ComparisonDecision = Literal[
    "not_evaluated",
    "advance_two_routes",
    "hold",
    "redesign_again",
]


class RouteComparisonThresholdsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold_version: Literal["v3.route_comparison_thresholds.1"] = (
        "v3.route_comparison_thresholds.1"
    )
    minimum_offline_validity_rate: float = 0.90
    minimum_solver_preflight_rate: float = 1.00
    minimum_exact_valid_delivery_rate: float = 0.80
    maximum_systemic_failure_rate: float = 0.10
    maximum_major_defect_rate: float = 0.10
    minimum_professional_plausibility_rate: float = 0.70
    minimum_productive_complexity_coverage: float = 0.80
    minimum_skill_causal_coverage: float = 0.90
    minimum_effective_rubric_dimensions: float = 5.0
    maximum_score_saturation_rate: float = 0.80
    score_saturation_score_threshold: float = 0.90
    grader_disagreement_absolute_threshold: float = 0.15
    maximum_grader_disagreement_rate: float = 0.20
    informative_case_min_score_spread: float = 0.20
    minimum_comparable_model_pair_rate: float = 0.60
    frozen_before_results: Literal[True] = True


class FrozenComparisonBriefV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief_id: str
    case_id: str
    motif: str
    source_ref_ids: List[str]
    selected_skill_ids: List[str]
    required_capability_ids: List[str]
    allowed_input_file_types: List[str]
    allowed_output_file_types: List[str]
    source_snapshot_sha256: str
    brief_sha256: str


class RoutePackageAssignmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    brief_id: str
    route_id: RouteId
    package_root: str
    package_fingerprint: Optional[str] = None
    materialization_status: Literal["pending", "materialized"] = "pending"


class RouteComparisonManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.route_comparison_manifest.1"] = (
        "v3.route_comparison_manifest.1"
    )
    comparison_id: str
    stage: Literal["screening"] = "screening"
    comparison_status: Literal["frozen_pending_execution"] = (
        "frozen_pending_execution"
    )
    routes: List[RouteId]
    briefs: List[FrozenComparisonBriefV1]
    assignments: List[RoutePackageAssignmentV1]
    thresholds: RouteComparisonThresholdsV1
    code_fingerprint: str
    environment_contract_id: str
    solver_preflight_contract_path: str
    grader_calibration_contract_path: str
    timeout_seconds: int = Field(gt=0)
    maximum_retry_count: int = Field(ge=0, le=1)
    maximum_provider_cost_usd: float = Field(gt=0.0)
    route_blinding_enabled: Literal[True] = True
    gdpval_generation_use: Literal[False] = False
    promotion_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_matched_design(self) -> "RouteComparisonManifestV1":
        required_routes = {
            "strict_template",
            "skill_guided_llm",
            "llm_led_hybrid",
        }
        if set(self.routes) != required_routes or len(self.routes) != 3:
            raise ValueError("route_comparison_requires_three_frozen_routes")
        if len(self.briefs) != 4:
            raise ValueError("screening_requires_four_frozen_briefs")
        if len(self.assignments) != 12:
            raise ValueError("screening_requires_twelve_route_assignments")
        pairs = Counter(
            (item.brief_id, item.route_id) for item in self.assignments
        )
        expected = {
            (brief.brief_id, route)
            for brief in self.briefs
            for route in self.routes
        }
        if set(pairs) != expected or any(value != 1 for value in pairs.values()):
            raise ValueError("each_brief_must_have_one_assignment_per_route")
        task_ids = [item.blind_task_id for item in self.assignments]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("route_blind_task_ids_must_be_unique")
        return self


class RouteTaskEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    brief_id: str
    route_id: RouteId
    offline_validity_pass: bool
    solver_preflight_pass: bool
    exact_valid_delivery: bool
    systemic_task_failure: bool
    major_defect: bool
    professional_plausibility: Literal[
        "not_evaluated", "provisional", "pass", "fail"
    ]
    productive_complexity_coverage: float = Field(ge=0.0, le=1.0)
    skill_causal_coverage: float = Field(ge=0.0, le=1.0)
    effective_rubric_dimensions: int = Field(ge=0)
    score_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    grader_disagreement: Optional[bool] = None
    comparable_model_pair: bool = False
    provider_cost_usd: float = Field(default=0.0, ge=0.0)
    runtime_seconds: float = Field(default=0.0, ge=0.0)
    review_minutes: float = Field(default=0.0, ge=0.0)
    implementation_complexity_points: float = Field(default=0.0, ge=0.0)
    validity_vector_path: str
    utility_profile_path: str
    behavioral_execution_report_path: str
    output_fingerprints: List[str] = Field(default_factory=list)


class RouteAggregateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: RouteId
    task_count: int
    offline_validity_rate: float
    solver_preflight_rate: float
    exact_valid_delivery_rate: float
    systemic_failure_rate: float
    major_defect_rate: float
    professional_plausibility_rate: float
    productive_complexity_coverage: float
    skill_causal_coverage: float
    effective_rubric_dimensions: float
    score_saturation_rate: float
    grader_disagreement_rate: float
    comparable_model_pair_rate: float
    provider_cost_usd: float
    runtime_seconds: float
    review_minutes: float
    implementation_complexity_points: float
    absolute_gate_pass: bool
    failed_thresholds: List[str] = Field(default_factory=list)


class RouteComparisonReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.route_comparison_report.1"] = (
        "v3.route_comparison_report.1"
    )
    comparison_id: str
    stage: Literal["screening"] = "screening"
    decision: ComparisonDecision
    evidence_complete: bool
    route_aggregates: List[RouteAggregateV1] = Field(default_factory=list)
    confirmation_candidates: List[RouteId] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    thresholds_frozen_before_results: bool
    comparison_manifest_path: Optional[str] = None
    comparison_manifest_sha256: Optional[str] = None
    evidence_compile_report_path: Optional[str] = None
    evidence_compile_report_sha256: Optional[str] = None
    promotion_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class RouteBlindPackageRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    brief_id: str
    route_id: RouteId
    source_export_root: str
    staged_export_root: str
    source_package_fingerprint: str
    staged_package_fingerprint: str
    validation_status: str
    reference_file_count: int
    deliverable_file_count: int


class RouteBlindStagingReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.route_blind_staging.1"] = (
        "v3.route_blind_staging.1"
    )
    comparison_id: str
    decision: Literal["pass", "blocked"]
    package_count: int
    records: List[RouteBlindPackageRecordV1] = Field(default_factory=list)
    route_metadata_outside_candidate_packages: Literal[True] = True
    teacher_artifacts_included: Literal[False] = False
    promotion_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class RouteComparisonManifestBuilder:
    ROUTES: List[RouteId] = [
        "strict_template",
        "skill_guided_llm",
        "llm_led_hybrid",
    ]

    def build(
        self,
        *,
        comparison_id: str,
        briefs: List[CapabilityBriefV1],
        source_snapshot_sha256: str,
        package_roots: Dict[str, Dict[RouteId, str]],
        code_fingerprint: str,
        environment_contract_id: str,
        solver_preflight_contract_path: str,
        grader_calibration_contract_path: str,
        timeout_seconds: int,
        maximum_provider_cost_usd: float,
        maximum_retry_count: int = 1,
    ) -> RouteComparisonManifestV1:
        frozen_briefs = [
            FrozenComparisonBriefV1(
                brief_id=brief.brief_id,
                case_id=brief.case_id,
                motif=brief.motif,
                source_ref_ids=sorted(
                    item.source_ref_id for item in brief.source_refs
                ),
                selected_skill_ids=sorted(
                    item.skill_id for item in brief.selected_skills
                ),
                required_capability_ids=sorted(
                    item.capability_id
                    for item in brief.required_capabilities
                ),
                allowed_input_file_types=sorted(
                    brief.allowed_input_file_types
                ),
                allowed_output_file_types=sorted(
                    brief.allowed_output_file_types
                ),
                source_snapshot_sha256=source_snapshot_sha256,
                brief_sha256=self._fingerprint(
                    brief.model_dump(mode="json")
                ),
            )
            for brief in briefs
        ]
        assignments = []
        for brief in briefs:
            route_roots = package_roots.get(brief.brief_id, {})
            for route in self.ROUTES:
                if route not in route_roots:
                    raise ValueError(
                        f"missing_package_root:{brief.brief_id}:{route}"
                    )
                assignments.append(
                    RoutePackageAssignmentV1(
                        blind_task_id=self._blind_task_id(
                            comparison_id,
                            brief.brief_id,
                            route,
                        ),
                        brief_id=brief.brief_id,
                        route_id=route,
                        package_root=route_roots[route],
                    )
                )
        return RouteComparisonManifestV1(
            comparison_id=comparison_id,
            routes=list(self.ROUTES),
            briefs=frozen_briefs,
            assignments=assignments,
            thresholds=RouteComparisonThresholdsV1(),
            code_fingerprint=code_fingerprint,
            environment_contract_id=environment_contract_id,
            solver_preflight_contract_path=solver_preflight_contract_path,
            grader_calibration_contract_path=grader_calibration_contract_path,
            timeout_seconds=timeout_seconds,
            maximum_retry_count=maximum_retry_count,
            maximum_provider_cost_usd=maximum_provider_cost_usd,
            notes=[
                "This manifest freezes matched inputs and thresholds before execution.",
                "Creating the manifest does not authorize provider, solver, grader, or promotion calls.",
            ],
        )

    @staticmethod
    def write(
        manifest: RouteComparisonManifestV1,
        output_path: str | Path,
    ) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    @staticmethod
    def _blind_task_id(
        comparison_id: str,
        brief_id: str,
        route: RouteId,
    ) -> str:
        digest = hashlib.sha256(
            f"{comparison_id}|{brief_id}|{route}".encode("utf-8")
        ).hexdigest()[:16]
        return f"cmp_{digest}"

    @staticmethod
    def _fingerprint(payload: Dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class RouteBlindPackageStager:
    ROUTE_ONLY_EXTRA_KEYS = {
        "materialization_route",
        "task_design_proposal_id",
        "capability_brief_id",
        "rw_task_exporter",
        "route_id",
        "generator_route",
    }

    def stage(
        self,
        manifest: RouteComparisonManifestV1,
        output_dir: str | Path,
    ) -> RouteBlindStagingReportV1:
        output_root = Path(output_dir)
        if output_root.exists():
            raise FileExistsError("route_blind_staging_output_exists")
        resolved = [
            (assignment, self._resolve_export_root(assignment.package_root))
            for assignment in manifest.assignments
        ]
        for _, source_root in resolved:
            self._assert_candidate_only(source_root)

        packages_root = output_root / "candidate_packages"
        governance_root = output_root / "governance"
        packages_root.mkdir(parents=True)
        governance_root.mkdir(parents=True)
        records: List[RouteBlindPackageRecordV1] = []
        for assignment, source_root in resolved:
            target_root = packages_root / assignment.blind_task_id
            shutil.copytree(source_root, target_root)
            source_fingerprint = self._directory_fingerprint(source_root)
            self._sanitize_candidate_package(
                target_root,
                assignment.blind_task_id,
            )
            validation = RwTaskExportValidator().validate(target_root)
            if validation.validation_status == "invalid":
                raise ValueError(
                    f"route_blind_staged_package_invalid:{assignment.blind_task_id}"
                )
            records.append(
                RouteBlindPackageRecordV1(
                    blind_task_id=assignment.blind_task_id,
                    brief_id=assignment.brief_id,
                    route_id=assignment.route_id,
                    source_export_root=str(source_root),
                    staged_export_root=str(target_root),
                    source_package_fingerprint=source_fingerprint,
                    staged_package_fingerprint=(
                        self._directory_fingerprint(target_root)
                    ),
                    validation_status=validation.validation_status,
                    reference_file_count=validation.reference_file_count,
                    deliverable_file_count=validation.deliverable_file_count,
                )
            )
        report = RouteBlindStagingReportV1(
            comparison_id=manifest.comparison_id,
            decision="pass",
            package_count=len(records),
            records=records,
            notes=[
                "Candidate packages are named only by route-blind task IDs.",
                "Route mapping and source fingerprints exist only in this governance report.",
                "Staging does not execute providers, solvers, graders, or promotion.",
            ],
        )
        (governance_root / "route_blind_staging_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _resolve_export_root(self, package_root: str | Path) -> Path:
        root = Path(package_root)
        candidates = [
            root,
            root / "rw_task_export",
            root / "hybrid_materialization" / "rw_task_export",
        ]
        for candidate in candidates:
            if (candidate / "dataset_row.json").is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"comparison_export_missing:{root}")

    def _assert_candidate_only(self, source_root: Path) -> None:
        forbidden = [
            path
            for path in source_root.rglob("*")
            if any(
                part.lower() in {"teacher", "golden_run", "provider"}
                for part in path.relative_to(source_root).parts
            )
        ]
        if forbidden:
            raise ValueError(
                f"comparison_source_contains_teacher_or_provider_artifact:{source_root}"
            )

    def _sanitize_candidate_package(
        self,
        target_root: Path,
        blind_task_id: str,
    ) -> None:
        dataset_path = target_root / "dataset_row.json"
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        dataset["task_id"] = blind_task_id
        extra = dict(dataset.get("extra") or {})
        for key in self.ROUTE_ONLY_EXTRA_KEYS:
            extra.pop(key, None)
        extra["comparison_blind_contract"] = {
            "blind_task_id": blind_task_id,
            "route_metadata_visible": False,
            "promotion_authorized": False,
        }
        embedded_contract = extra.get("deliverable_contract")
        if isinstance(embedded_contract, dict):
            embedded_contract = dict(embedded_contract)
            embedded_contract["case_id"] = blind_task_id
            extra["deliverable_contract"] = embedded_contract
        dataset["extra"] = extra
        dataset_path.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        contract_path = target_root / "deliverable_contract.json"
        if contract_path.is_file():
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["case_id"] = blind_task_id
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        expected_path = (
            target_root
            / "deliverable_files"
            / "expected_deliverables.json"
        )
        if expected_path.is_file():
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
            expected["case_id"] = blind_task_id
            expected_path.write_text(
                json.dumps(expected, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (target_root / "rw_task_export_report.json").write_text(
            json.dumps(
                {
                    "export_version": "v3.route_blind_staging.1",
                    "case_id": blind_task_id,
                    "export_decision": "draft_exported",
                    "not_final_training_data": True,
                    "route_metadata_visible": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        validation_path = target_root / "rw_task_export_validation_report.json"
        if validation_path.exists():
            validation_path.unlink()

    @staticmethod
    def _directory_fingerprint(root: Path) -> str:
        records = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            records.append(f"{relative}:{digest}")
        return hashlib.sha256(
            "\n".join(records).encode("utf-8")
        ).hexdigest()


class RouteComparisonAnalyzer:
    def analyze(
        self,
        manifest: RouteComparisonManifestV1,
        evidence: List[RouteTaskEvidenceV1],
    ) -> RouteComparisonReportV1:
        expected = {
            item.blind_task_id: item for item in manifest.assignments
        }
        supplied_ids = [item.blind_task_id for item in evidence]
        unknown = sorted(set(supplied_ids) - set(expected))
        duplicates = sorted(
            {
                task_id
                for task_id in supplied_ids
                if supplied_ids.count(task_id) > 1
            }
        )
        missing = sorted(set(expected) - set(supplied_ids))
        mismatched = sorted(
            item.blind_task_id
            for item in evidence
            if item.blind_task_id in expected
            and (
                item.brief_id != expected[item.blind_task_id].brief_id
                or item.route_id != expected[item.blind_task_id].route_id
            )
        )
        blocking = []
        if unknown:
            blocking.append("unknown_task_evidence")
        if duplicates:
            blocking.append("duplicate_task_evidence")
        if missing:
            blocking.append("missing_task_evidence")
        if mismatched:
            blocking.append("route_or_brief_identity_mismatch")
        if blocking:
            return RouteComparisonReportV1(
                comparison_id=manifest.comparison_id,
                decision="not_evaluated",
                evidence_complete=False,
                blocking_reasons=blocking,
                thresholds_frozen_before_results=(
                    manifest.thresholds.frozen_before_results
                ),
                notes=[
                    "Incomplete or identity-mismatched evidence cannot be ranked."
                ],
            )

        aggregates = [
            self._aggregate(
                route,
                [item for item in evidence if item.route_id == route],
                manifest.thresholds,
            )
            for route in manifest.routes
        ]
        eligible = [item for item in aggregates if item.absolute_gate_pass]
        if not eligible:
            decision: ComparisonDecision = "redesign_again"
            candidates: List[RouteId] = []
        elif len(eligible) < 2:
            decision = "hold"
            candidates = [item.route_id for item in eligible]
        else:
            decision = "advance_two_routes"
            ranked = sorted(
                eligible,
                key=self._ranking_key,
                reverse=True,
            )
            candidates = [item.route_id for item in ranked[:2]]
        return RouteComparisonReportV1(
            comparison_id=manifest.comparison_id,
            decision=decision,
            evidence_complete=True,
            route_aggregates=aggregates,
            confirmation_candidates=candidates,
            thresholds_frozen_before_results=(
                manifest.thresholds.frozen_before_results
            ),
            notes=[
                "Relative ranking is applied only after absolute gates pass.",
                "Screening can advance routes to confirmation but cannot promote a default chain.",
            ],
        )

    def _aggregate(
        self,
        route: RouteId,
        records: List[RouteTaskEvidenceV1],
        thresholds: RouteComparisonThresholdsV1,
    ) -> RouteAggregateV1:
        count = len(records)
        ratio = lambda predicate: (
            sum(1 for item in records if predicate(item)) / count
            if count
            else 0.0
        )
        scored = [item for item in records if item.score_ratio is not None]
        saturation = (
            sum(
                item.score_ratio
                >= thresholds.score_saturation_score_threshold
                for item in scored
                if item.score_ratio is not None
            )
            / len(scored)
            if scored
            else 1.0
        )
        disagreement_records = [
            item for item in records if item.grader_disagreement is not None
        ]
        disagreement = (
            sum(bool(item.grader_disagreement) for item in disagreement_records)
            / len(disagreement_records)
            if disagreement_records
            else 1.0
        )
        values = {
            "offline_validity_rate": ratio(
                lambda item: item.offline_validity_pass
            ),
            "solver_preflight_rate": ratio(
                lambda item: item.solver_preflight_pass
            ),
            "exact_valid_delivery_rate": ratio(
                lambda item: item.exact_valid_delivery
            ),
            "systemic_failure_rate": ratio(
                lambda item: item.systemic_task_failure
            ),
            "major_defect_rate": ratio(lambda item: item.major_defect),
            "professional_plausibility_rate": ratio(
                lambda item: item.professional_plausibility == "pass"
            ),
            "productive_complexity_coverage": (
                sum(item.productive_complexity_coverage for item in records)
                / count
                if count
                else 0.0
            ),
            "skill_causal_coverage": (
                sum(item.skill_causal_coverage for item in records) / count
                if count
                else 0.0
            ),
            "effective_rubric_dimensions": (
                sum(item.effective_rubric_dimensions for item in records)
                / count
                if count
                else 0.0
            ),
            "score_saturation_rate": saturation,
            "grader_disagreement_rate": disagreement,
            "comparable_model_pair_rate": ratio(
                lambda item: item.comparable_model_pair
            ),
        }
        checks = {
            "offline_validity_rate": (
                values["offline_validity_rate"]
                >= thresholds.minimum_offline_validity_rate
            ),
            "solver_preflight_rate": (
                values["solver_preflight_rate"]
                >= thresholds.minimum_solver_preflight_rate
            ),
            "exact_valid_delivery_rate": (
                values["exact_valid_delivery_rate"]
                >= thresholds.minimum_exact_valid_delivery_rate
            ),
            "systemic_failure_rate": (
                values["systemic_failure_rate"]
                <= thresholds.maximum_systemic_failure_rate
            ),
            "major_defect_rate": (
                values["major_defect_rate"]
                <= thresholds.maximum_major_defect_rate
            ),
            "professional_plausibility_rate": (
                values["professional_plausibility_rate"]
                >= thresholds.minimum_professional_plausibility_rate
            ),
            "productive_complexity_coverage": (
                values["productive_complexity_coverage"]
                >= thresholds.minimum_productive_complexity_coverage
            ),
            "skill_causal_coverage": (
                values["skill_causal_coverage"]
                >= thresholds.minimum_skill_causal_coverage
            ),
            "effective_rubric_dimensions": (
                values["effective_rubric_dimensions"]
                >= thresholds.minimum_effective_rubric_dimensions
            ),
            "score_saturation_rate": (
                values["score_saturation_rate"]
                <= thresholds.maximum_score_saturation_rate
            ),
            "grader_disagreement_rate": (
                values["grader_disagreement_rate"]
                <= thresholds.maximum_grader_disagreement_rate
            ),
            "comparable_model_pair_rate": (
                values["comparable_model_pair_rate"]
                >= thresholds.minimum_comparable_model_pair_rate
            ),
        }
        return RouteAggregateV1(
            route_id=route,
            task_count=count,
            **{name: round(value, 4) for name, value in values.items()},
            provider_cost_usd=round(
                sum(item.provider_cost_usd for item in records),
                4,
            ),
            runtime_seconds=round(
                sum(item.runtime_seconds for item in records),
                4,
            ),
            review_minutes=round(
                sum(item.review_minutes for item in records),
                4,
            ),
            implementation_complexity_points=round(
                sum(item.implementation_complexity_points for item in records),
                4,
            ),
            absolute_gate_pass=all(checks.values()),
            failed_thresholds=sorted(
                name for name, passed in checks.items() if not passed
            ),
        )

    @staticmethod
    def _ranking_key(item: RouteAggregateV1) -> tuple[float, ...]:
        return (
            item.professional_plausibility_rate,
            item.productive_complexity_coverage,
            item.skill_causal_coverage,
            item.exact_valid_delivery_rate,
            -item.major_defect_rate,
            -item.provider_cost_usd,
            -item.review_minutes,
            -item.implementation_complexity_points,
        )
