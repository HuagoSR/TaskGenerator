from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_behavioral_validation import (
    BehavioralExecutionReportV1,
    SolverToolPreflight,
)
from task_generator.v3_evaluation_calibration import (
    EvaluationCalibrationCompiler,
    FrozenSolverPanelV1,
    GraderScoreObservationV1,
    ProfessionalValidityReviewV1,
)
from task_generator.v3_route_comparison import (
    RouteBlindPackageRecordV1,
    RouteBlindStagingReportV1,
    RouteComparisonManifestV1,
    RouteTaskEvidenceV1,
)
from task_generator.v3_validity_utility import (
    R5GovernanceBundleV1,
    RubricPlanV2,
    UtilityProfileV1,
    ValidityVectorV1,
)


class RouteTaskEvidenceInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    package_root: str
    package_fingerprint: str = Field(min_length=64, max_length=64)
    behavioral_report_paths: List[str] = Field(min_length=3, max_length=3)
    behavioral_report_sha256: Dict[str, str] = Field(default_factory=dict)
    professional_review_path: str
    professional_review_sha256: Optional[str] = None
    professional_support_sha256: Dict[str, str] = Field(default_factory=dict)
    provider_cost_usd: float = Field(default=0.0, ge=0.0)
    runtime_seconds: float = Field(default=0.0, ge=0.0)
    review_minutes: float = Field(default=0.0, ge=0.0)
    implementation_complexity_points: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_unique_behavior_paths(self) -> "RouteTaskEvidenceInputV1":
        if len(set(self.behavioral_report_paths)) != 3:
            raise ValueError("task_evidence_requires_three_unique_behavior_reports")
        return self


class RouteComparisonEvidenceInputManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.route_comparison_evidence_input.2"] = (
        "v3.route_comparison_evidence_input.2"
    )
    comparison_manifest_path: str
    comparison_manifest_sha256: Optional[str] = None
    route_blind_staging_report_path: str
    route_blind_staging_report_sha256: Optional[str] = None
    frozen_solver_panel_path: str
    frozen_solver_panel_sha256: Optional[str] = None
    grader_observations_path: str
    grader_observations_sha256: Optional[str] = None
    tasks: List[RouteTaskEvidenceInputV1] = Field(min_length=12, max_length=12)
    evidence_frozen: bool = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_unique_tasks(self) -> "RouteComparisonEvidenceInputManifestV1":
        ids = [item.blind_task_id for item in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_route_evidence_task")
        return self


class RouteComparisonEvidenceCompileReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.route_comparison_evidence_compile.1"] = (
        "v3.route_comparison_evidence_compile.1"
    )
    comparison_id: str
    decision: Literal["pass", "blocked"]
    evidence_count: int
    evidence: List[RouteTaskEvidenceV1] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    task_blocking_reasons: Dict[str, List[str]] = Field(default_factory=dict)
    invalid_delivery_excluded_from_grading: Literal[True] = True
    panel_rule: Literal[
        "exact_delivery_requires_strong_and_two_of_three"
    ] = "exact_delivery_requires_strong_and_two_of_three"
    systemic_failure_rule: Literal[
        "fewer_than_two_valid_deliveries_or_same_failure_in_two_solvers"
    ] = "fewer_than_two_valid_deliveries_or_same_failure_in_two_solvers"
    promotion_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_release(
        self,
    ) -> "RouteComparisonEvidenceCompileReportV1":
        if self.decision == "pass":
            if self.evidence_count != 12 or len(self.evidence) != 12:
                raise ValueError(
                    "passing_route_evidence_requires_twelve_records"
                )
        elif self.evidence_count != 0 or self.evidence:
            raise ValueError(
                "blocked_route_evidence_must_not_release_partial_records"
            )
        return self


class RouteComparisonEvidenceCompiler:
    def freeze(
        self,
        template: RouteComparisonEvidenceInputManifestV1,
    ) -> RouteComparisonEvidenceInputManifestV1:
        payload = template.model_dump(mode="json")
        for path_field, sha_field in (
            ("comparison_manifest_path", "comparison_manifest_sha256"),
            (
                "route_blind_staging_report_path",
                "route_blind_staging_report_sha256",
            ),
            ("frozen_solver_panel_path", "frozen_solver_panel_sha256"),
            ("grader_observations_path", "grader_observations_sha256"),
        ):
            path = Path(payload[path_field])
            if not path.is_file():
                raise FileNotFoundError(f"evidence_freeze_missing:{path_field}")
            payload[sha_field] = self._sha256_file(path)
        for task in payload["tasks"]:
            behavioral_hashes = {}
            for path_text in task["behavioral_report_paths"]:
                path = Path(path_text)
                if not path.is_file():
                    raise FileNotFoundError(
                        f"evidence_freeze_missing_behavioral_report:{path}"
                    )
                behavioral_hashes[path_text] = self._sha256_file(path)
            task["behavioral_report_sha256"] = behavioral_hashes
            review_path = Path(task["professional_review_path"])
            if not review_path.is_file():
                raise FileNotFoundError(
                    f"evidence_freeze_missing_professional_review:{review_path}"
                )
            task["professional_review_sha256"] = self._sha256_file(review_path)
            review = ProfessionalValidityReviewV1.model_validate_json(
                review_path.read_text(encoding="utf-8")
            )
            support_hashes = {}
            for evidence_path in review.evidence_paths:
                support = self._resolve_support_path(
                    review_path,
                    evidence_path,
                )
                if not support.is_file():
                    raise FileNotFoundError(
                        f"evidence_freeze_missing_professional_support:{support}"
                    )
                support_hashes[evidence_path] = self._sha256_file(support)
            task["professional_support_sha256"] = support_hashes
        payload["evidence_frozen"] = True
        return RouteComparisonEvidenceInputManifestV1.model_validate(payload)

    def compile(
        self,
        manifest: RouteComparisonEvidenceInputManifestV1,
    ) -> RouteComparisonEvidenceCompileReportV1:
        if not manifest.evidence_frozen:
            return self._blocked(
                "unknown",
                ["route_evidence_input_not_frozen"],
            )
        global_hashes = (
            (
                manifest.comparison_manifest_path,
                manifest.comparison_manifest_sha256,
                "comparison_manifest",
            ),
            (
                manifest.route_blind_staging_report_path,
                manifest.route_blind_staging_report_sha256,
                "route_blind_staging_report",
            ),
            (
                manifest.frozen_solver_panel_path,
                manifest.frozen_solver_panel_sha256,
                "frozen_solver_panel",
            ),
            (
                manifest.grader_observations_path,
                manifest.grader_observations_sha256,
                "grader_observations",
            ),
        )
        hash_failures = self._hash_failures(global_hashes)
        if hash_failures:
            return self._blocked("unknown", hash_failures)
        comparison = RouteComparisonManifestV1.model_validate_json(
            Path(manifest.comparison_manifest_path).read_text(encoding="utf-8")
        )
        staging = RouteBlindStagingReportV1.model_validate_json(
            Path(manifest.route_blind_staging_report_path).read_text(
                encoding="utf-8"
            )
        )
        panel = FrozenSolverPanelV1.model_validate_json(
            Path(manifest.frozen_solver_panel_path).read_text(encoding="utf-8")
        )
        observations = self._load_observations(
            Path(manifest.grader_observations_path)
        )
        blocking: List[str] = []
        if staging.decision != "pass":
            blocking.append("route_blind_staging_not_pass")
        if staging.comparison_id != comparison.comparison_id:
            blocking.append("route_blind_staging_comparison_id_mismatch")
        staging_by_task = {
            item.blind_task_id: item for item in staging.records
        }
        if (
            len(staging.records) != 12
            or len(staging_by_task) != 12
        ):
            blocking.append("route_blind_staging_requires_twelve_unique_records")
        recomputed_panel = EvaluationCalibrationCompiler().freeze_solver_panel(
            panel_id=panel.panel_id,
            members=panel.members,
        )
        if recomputed_panel.decision != "pass":
            blocking.extend(recomputed_panel.blocking_reasons)
        if panel.decision != "pass":
            blocking.append("frozen_solver_panel_not_pass")
        assignments = {
            item.blind_task_id: item for item in comparison.assignments
        }
        supplied = {item.blind_task_id: item for item in manifest.tasks}
        missing = sorted(set(assignments) - set(supplied))
        unknown = sorted(set(supplied) - set(assignments))
        if missing:
            blocking.append("route_evidence_tasks_missing")
        if unknown:
            blocking.append("route_evidence_tasks_unknown")
        panel_models = {item.solver_model for item in panel.members}
        panel_environments = {
            item.preflight_report.environment_id for item in panel.members
        }
        if len(panel_environments) != 1:
            blocking.append("frozen_panel_environment_mismatch")
        strong_models = {
            item.solver_model
            for item in panel.members
            if item.stratum == "strong"
        }
        if len(strong_models) != 1:
            blocking.append("frozen_panel_strong_model_invalid")
        observation_by_task: Dict[
            str, List[GraderScoreObservationV1]
        ] = defaultdict(list)
        for observation in observations:
            grader_output = Path(observation.grader_output_path)
            if not grader_output.is_file():
                blocking.append("grader_output_artifact_missing")
                continue
            if (
                hashlib.sha256(grader_output.read_bytes()).hexdigest()
                != observation.grader_output_sha256
            ):
                blocking.append("grader_output_artifact_sha256_mismatch")
                continue
            if observation.blind_task_id not in assignments:
                blocking.append("grader_observation_unknown_task")
                continue
            if observation.solver_model not in panel_models:
                blocking.append("grader_observation_unknown_solver")
                continue
            if not observation.valid_delivery:
                blocking.append(
                    "grader_observation_contains_invalid_delivery"
                )
                continue
            observation_by_task[observation.blind_task_id].append(
                observation
            )
        if blocking:
            return self._blocked(comparison.comparison_id, blocking)

        evidence: List[RouteTaskEvidenceV1] = []
        task_blocking: Dict[str, List[str]] = {}
        for task_id, assignment in assignments.items():
            try:
                record = self._compile_task(
                    task_input=supplied[task_id],
                    assignment=assignment,
                    staging_record=staging_by_task[task_id],
                    panel=panel,
                    strong_model=next(iter(strong_models)),
                    panel_environment=next(iter(panel_environments)),
                    observations=observation_by_task.get(task_id, []),
                    disagreement_threshold=(
                        comparison.thresholds.grader_disagreement_absolute_threshold
                    ),
                    informative_spread_threshold=(
                        comparison.thresholds.informative_case_min_score_spread
                    ),
                )
            except Exception as exc:
                task_blocking.setdefault(task_id, []).append(
                    f"{type(exc).__name__}:{exc}"
                )
            else:
                evidence.append(record)
        if task_blocking:
            return RouteComparisonEvidenceCompileReportV1(
                comparison_id=comparison.comparison_id,
                decision="blocked",
                evidence_count=0,
                blocking_reasons=["task_evidence_compilation_blocked"],
                task_blocking_reasons=task_blocking,
                notes=[
                    "No partial evidence list is released when any matched task is incomplete."
                ],
            )
        return RouteComparisonEvidenceCompileReportV1(
            comparison_id=comparison.comparison_id,
            decision="pass",
            evidence_count=len(evidence),
            evidence=evidence,
            notes=[
                "Offline, behavioral, grader and professional evidence are compiled on separate axes.",
                "Only valid deliveries may contribute grader observations.",
                "A passing compile report authorizes analysis only, never promotion.",
            ],
        )

    def _compile_task(
        self,
        *,
        task_input: RouteTaskEvidenceInputV1,
        assignment,
        staging_record: RouteBlindPackageRecordV1,
        panel: FrozenSolverPanelV1,
        strong_model: str,
        panel_environment: str,
        observations: List[GraderScoreObservationV1],
        disagreement_threshold: float,
        informative_spread_threshold: float,
    ) -> RouteTaskEvidenceV1:
        package_root = Path(task_input.package_root)
        if package_root.resolve() != Path(assignment.package_root).resolve():
            raise ValueError("package_root_assignment_mismatch")
        if self._directory_fingerprint(package_root) != task_input.package_fingerprint:
            raise ValueError("assignment_package_fingerprint_mismatch")
        source_export_root = Path(staging_record.source_export_root)
        staged_export_root = Path(staging_record.staged_export_root)
        if not self._is_within(source_export_root, package_root):
            raise ValueError("staging_source_export_outside_governance_package")
        if (
            self._directory_fingerprint(source_export_root)
            != staging_record.source_package_fingerprint
        ):
            raise ValueError("staging_source_package_fingerprint_mismatch")
        if (
            self._directory_fingerprint(staged_export_root)
            != staging_record.staged_package_fingerprint
        ):
            raise ValueError("staged_candidate_package_fingerprint_mismatch")
        brief_path = package_root / "governance" / "capability_brief.json"
        validity_path = package_root / "governance" / "validity_vector.json"
        utility_path = package_root / "governance" / "utility_profile.json"
        rubric_path = package_root / "teacher" / "rubric_plan_v2.json"
        bundle_path = package_root / "governance" / "r5_governance_bundle.json"
        validity = ValidityVectorV1.model_validate_json(
            validity_path.read_text(encoding="utf-8")
        )
        utility = UtilityProfileV1.model_validate_json(
            utility_path.read_text(encoding="utf-8")
        )
        rubric = RubricPlanV2.model_validate_json(
            rubric_path.read_text(encoding="utf-8")
        )
        bundle = R5GovernanceBundleV1.model_validate_json(
            bundle_path.read_text(encoding="utf-8")
        )
        brief_payload = json.loads(brief_path.read_text(encoding="utf-8"))
        if brief_payload.get("brief_id") != assignment.brief_id:
            raise ValueError("package_brief_identity_mismatch")
        # Package governance retains the source case identity; the blind task
        # identity appears only in staged candidate/evaluation artifacts.
        if validity.case_id == task_input.blind_task_id:
            pass
        elif not validity.case_id:
            raise ValueError("validity_case_identity_missing")
        if (
            utility.case_id != validity.case_id
            or rubric.case_id != validity.case_id
            or bundle.validity_vector.case_id != validity.case_id
        ):
            raise ValueError("package_governance_case_identity_mismatch")

        if set(task_input.behavioral_report_sha256) != set(
            task_input.behavioral_report_paths
        ):
            raise ValueError("behavioral_report_hash_coverage_mismatch")
        behavioral = []
        for path_text in task_input.behavioral_report_paths:
            path = Path(path_text)
            if (
                not path.is_file()
                or self._sha256_file(path)
                != task_input.behavioral_report_sha256[path_text]
            ):
                raise ValueError("behavioral_report_sha256_mismatch")
            behavioral.append(
                BehavioralExecutionReportV1.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            )
        models = [item.solver_model for item in behavioral]
        panel_models = {item.solver_model for item in panel.members}
        if set(models) != panel_models or len(models) != len(set(models)):
            raise ValueError("behavioral_reports_do_not_exactly_cover_panel")
        if any(item.case_id != task_input.blind_task_id for item in behavioral):
            raise ValueError("behavioral_blind_task_identity_mismatch")
        environment_ids = {item.environment_id for item in behavioral}
        if environment_ids != {panel_environment}:
            raise ValueError("behavioral_environment_mismatch")
        panel_by_model = {
            item.solver_model: item for item in panel.members
        }
        for report in behavioral:
            if (
                not report.input_package_root
                or report.input_package_fingerprint
                != staging_record.staged_package_fingerprint
                or SolverToolPreflight.tree_fingerprint(
                    SolverToolPreflight.output_fingerprints(
                        report.input_package_root
                    )
                )
                != staging_record.staged_package_fingerprint
            ):
                raise ValueError("behavioral_input_package_mismatch")
            current_output_fingerprints = (
                SolverToolPreflight.output_fingerprints(
                    report.output_root or ""
                )
            )
            if (
                report.output_fingerprints != current_output_fingerprints
                or report.output_tree_fingerprint
                != SolverToolPreflight.tree_fingerprint(
                    current_output_fingerprints
                )
            ):
                raise ValueError("behavioral_output_fingerprint_mismatch")
            member = panel_by_model[report.solver_model]
            member_preflight_path = Path(member.preflight_report_path)
            if (
                not report.solver_preflight_report_path
                or not report.solver_preflight_report_sha256
                or self._sha256_file(
                    Path(report.solver_preflight_report_path)
                )
                != report.solver_preflight_report_sha256
                or not member_preflight_path.is_file()
                or self._sha256_file(member_preflight_path)
                != report.solver_preflight_report_sha256
            ):
                raise ValueError("behavioral_preflight_evidence_mismatch")
            if report.delivery_inspection_path:
                delivery_path = Path(report.delivery_inspection_path)
                if (
                    not report.delivery_inspection_sha256
                    or not delivery_path.is_file()
                    or self._sha256_file(delivery_path)
                    != report.delivery_inspection_sha256
                ):
                    raise ValueError(
                        "behavioral_delivery_inspection_sha256_mismatch"
                    )
            elif report.delivery_status != "not_evaluated":
                raise ValueError(
                    "behavioral_delivery_inspection_evidence_missing"
                )

        review_path = Path(task_input.professional_review_path)
        if (
            not task_input.professional_review_sha256
            or not review_path.is_file()
            or self._sha256_file(review_path)
            != task_input.professional_review_sha256
        ):
            raise ValueError("professional_review_sha256_mismatch")
        review = ProfessionalValidityReviewV1.model_validate_json(
            review_path.read_text(
                encoding="utf-8"
            )
        )
        if review.blind_task_id != task_input.blind_task_id:
            raise ValueError("professional_review_task_identity_mismatch")
        if set(task_input.professional_support_sha256) != set(
            review.evidence_paths
        ):
            raise ValueError("professional_support_hash_coverage_mismatch")
        for evidence_path in review.evidence_paths:
            supporting_evidence = self._resolve_support_path(
                review_path,
                evidence_path,
            )
            if (
                not supporting_evidence.is_file()
                or self._sha256_file(supporting_evidence)
                != task_input.professional_support_sha256[evidence_path]
            ):
                raise ValueError("professional_review_support_sha256_mismatch")
        valid_reports = [
            item
            for item in behavioral
            if item.process_status == "succeeded"
            and item.delivery_status == "valid"
            and item.file_validity_status == "pass"
            and item.preflight_status == "pass"
            and item.grader_eligible
            and item.grader_executed
        ]
        valid_models = {item.solver_model for item in valid_reports}
        exact_valid_delivery = (
            len(valid_reports) >= 2 and strong_model in valid_models
        )
        failures = Counter(
            item.failure_category
            for item in behavioral
            if item.failure_category not in {"none", "not_evaluated"}
        )
        systemic_failure = (
            len(valid_reports) < 2
            or any(count >= 2 for count in failures.values())
        )
        valid_business_failures = sum(
            item.business_validity_status == "fail"
            for item in valid_reports
        )
        major_defect = (
            bundle.offline_decision != "pass"
            or valid_business_failures >= 2
            or bool(review.material_defects)
            or review.decision in {"revise", "blocked"}
        )
        professional_status = (
            "pass"
            if review.reviewer_type == "independent_expert"
            and review.decision == "pass"
            and not review.material_defects
            else "fail"
            if review.decision in {"revise", "blocked"}
            or bool(review.material_defects)
            else "provisional"
        )
        if not observations:
            raise ValueError("grader_observations_missing")
        observation_models = {item.solver_model for item in observations}
        if observation_models != valid_models:
            raise ValueError("grader_observation_without_valid_delivery")
        grouped_scores: Dict[str, List[float]] = defaultdict(list)
        pair_groups: Dict[tuple[str, str], List[GraderScoreObservationV1]] = (
            defaultdict(list)
        )
        for item in observations:
            grouped_scores[item.solver_model].append(
                item.overall_score_ratio
            )
            pair_groups[(item.solver_model, item.grader_model)].append(item)
        if any(
            len(records) < 2
            or len({item.repeat_index for item in records}) != len(records)
            for records in pair_groups.values()
        ):
            raise ValueError("grader_repeat_pair_incomplete")
        means = [
            sum(scores) / len(scores) for scores in grouped_scores.values()
        ]
        comparable_pair = (
            len(means) >= 2
            and max(means) - min(means) >= informative_spread_threshold
        )
        disagreement = False
        for records in pair_groups.values():
            overall = [item.overall_score_ratio for item in records]
            dimensions = {
                key
                for item in records
                for key in item.dimension_score_ratios
            }
            max_dimension_spread = max(
                [
                    max(
                        item.dimension_score_ratios[key]
                        for item in records
                    )
                    - min(
                        item.dimension_score_ratios[key]
                        for item in records
                    )
                    for key in dimensions
                    if all(key in item.dimension_score_ratios for item in records)
                ]
                or [0.0]
            )
            if (
                max(overall) - min(overall) > disagreement_threshold
                or max_dimension_spread > disagreement_threshold
            ):
                disagreement = True
        score_ratio = sum(
            item.overall_score_ratio for item in observations
        ) / len(observations)
        offline_validity = (
            bundle.offline_decision == "pass"
            and rubric.decision == "pass"
            and all(
                next(
                    dimension
                    for dimension in validity.dimensions
                    if dimension.dimension == name
                ).status
                in {"pass", "provisional"}
                for name in (
                    "factual_validity",
                    "semantic_validity",
                    "contract_validity",
                )
            )
        )
        output_fingerprints = sorted(
            {
                fingerprint
                for report in behavioral
                for fingerprint in report.output_fingerprints
            }
        )
        behavioral_index_path = str(
            Path(task_input.behavioral_report_paths[0]).parent
        )
        return RouteTaskEvidenceV1(
            blind_task_id=task_input.blind_task_id,
            brief_id=assignment.brief_id,
            route_id=assignment.route_id,
            offline_validity_pass=offline_validity,
            solver_preflight_pass=all(
                item.preflight_status == "pass" for item in behavioral
            ),
            exact_valid_delivery=exact_valid_delivery,
            systemic_task_failure=systemic_failure,
            major_defect=major_defect,
            professional_plausibility=professional_status,
            productive_complexity_coverage=(
                utility.productive_complexity_coverage
            ),
            skill_causal_coverage=utility.skill_causal_coverage,
            effective_rubric_dimensions=rubric.effective_dimension_count,
            score_ratio=round(score_ratio, 4),
            grader_disagreement=disagreement,
            comparable_model_pair=comparable_pair,
            provider_cost_usd=task_input.provider_cost_usd,
            runtime_seconds=task_input.runtime_seconds,
            review_minutes=task_input.review_minutes,
            implementation_complexity_points=(
                task_input.implementation_complexity_points
            ),
            validity_vector_path=str(validity_path.resolve()),
            utility_profile_path=str(utility_path.resolve()),
            behavioral_execution_report_path=behavioral_index_path,
            output_fingerprints=output_fingerprints,
        )

    @staticmethod
    def _load_observations(
        path: Path,
    ) -> List[GraderScoreObservationV1]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("observations")
        if not isinstance(payload, list):
            raise ValueError("grader_observations_must_be_list")
        return [
            GraderScoreObservationV1.model_validate(item) for item in payload
        ]

    @staticmethod
    def _directory_fingerprint(root: Path) -> str:
        if not root.is_dir():
            raise FileNotFoundError("assignment_package_root_missing")
        records = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            records.append(
                f"{path.relative_to(root).as_posix()}:"
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}"
            )
        return hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _hash_failures(
        cls,
        records,
    ) -> List[str]:
        failures = []
        for path_text, expected, label in records:
            path = Path(path_text)
            if not expected:
                failures.append(f"{label}_sha256_missing")
            elif not path.is_file():
                failures.append(f"{label}_missing")
            elif cls._sha256_file(path) != expected:
                failures.append(f"{label}_sha256_mismatch")
        return failures

    @staticmethod
    def _resolve_support_path(
        review_path: Path,
        evidence_path: str,
    ) -> Path:
        support = Path(evidence_path)
        if not support.is_absolute():
            support = review_path.parent / support
        return support.resolve()

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            return False
        return True

    @staticmethod
    def _blocked(
        comparison_id: str,
        reasons: List[str],
    ) -> RouteComparisonEvidenceCompileReportV1:
        return RouteComparisonEvidenceCompileReportV1(
            comparison_id=comparison_id,
            decision="blocked",
            evidence_count=0,
            blocking_reasons=sorted(set(reasons)),
            notes=[
                "Global identity or calibration failures prevent any partial comparison evidence release."
            ],
        )
