"""Minimal contracts for independent, item-by-item rubric grading.

The judge emits only item assessments.  Identity, score bounds, completeness,
totals, hashes, and evidence-path safety are enforced by the controller.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, StrictInt, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel


MaterialStatus = Literal["complete", "incomplete"]
Applicability = Literal["applicable", "not_triggered", "unresolved"]
Satisfaction = Literal["met", "partial", "not_met", "not_triggered", "unresolved"]
VerificationScope = Literal["presence", "sample", "all_rows", "formula", "style_metadata"]


def canonical_json_sha256(value: Any) -> str:
    if isinstance(value, ScenarioFirstModel):
        value = value.model_dump(mode="json", exclude_none=False)
    elif isinstance(value, (list, tuple)):
        value = [
            row.model_dump(mode="json", exclude_none=False)
            if isinstance(row, ScenarioFirstModel) else row
            for row in value
        ]
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    """Hash file names and contents, independent of the absolute root path."""
    digest = hashlib.sha256()
    for path in sorted((row for row in root.rglob("*") if row.is_file()), key=lambda row: row.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


class FrozenRubricItemV1(ScenarioFirstModel):
    rubric_item_id: str = Field(min_length=1)
    max_score: StrictInt = Field(gt=0)
    criterion: str = Field(min_length=3)


class IndependentRubricItemAssessmentV1(ScenarioFirstModel):
    rubric_item_id: str = Field(min_length=1)
    awarded: StrictInt = Field(ge=0)
    applicability: Applicability
    evidence_paths: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5, max_length=1600)


class IndependentRubricGradeDraftV1(ScenarioFirstModel):
    draft_version: Literal["r10.independent_rubric_grade_draft.1"] = (
        "r10.independent_rubric_grade_draft.1"
    )
    material_status: MaterialStatus
    material_notes: str = Field(min_length=1, max_length=1600)
    assessments: list[IndependentRubricItemAssessmentV1] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "IndependentRubricGradeDraftV1":
        identifiers = [row.rubric_item_id for row in self.assessments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("independent_grade_duplicate_rubric_item")
        return self


class IndependentRubricItemAssessmentV2(ScenarioFirstModel):
    """Evidence-disciplined item assessment for structured spreadsheet packets."""

    rubric_item_id: str = Field(min_length=1)
    awarded: StrictInt = Field(ge=0)
    satisfaction: Satisfaction
    verification_scope: VerificationScope
    evidence_paths: list[str] = Field(min_length=1)
    support: list[str] = Field(default_factory=list)
    defects: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=5, max_length=1600)


class IndependentRubricGradeDraftV2(ScenarioFirstModel):
    draft_version: Literal["r10.independent_rubric_grade_draft.2"] = (
        "r10.independent_rubric_grade_draft.2"
    )
    material_status: MaterialStatus
    material_notes: str = Field(min_length=1, max_length=1600)
    assessments: list[IndependentRubricItemAssessmentV2] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "IndependentRubricGradeDraftV2":
        identifiers = [row.rubric_item_id for row in self.assessments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("independent_grade_duplicate_rubric_item")
        return self


class IndependentRubricItemResultV1(ScenarioFirstModel):
    rubric_item_id: str
    max_score: StrictInt = Field(gt=0)
    awarded: StrictInt = Field(ge=0)
    applicability: Applicability
    evidence_paths: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5, max_length=1600)


class IndependentRubricGradeV1(ScenarioFirstModel):
    grade_version: Literal["r10.independent_rubric_grade.1"] = (
        "r10.independent_rubric_grade.1"
    )
    task_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    judge_id: str = Field(min_length=1)
    material_status: MaterialStatus
    material_notes: str
    items: list[IndependentRubricItemResultV1] = Field(min_length=1)
    total_score: StrictInt | None
    max_possible_score: StrictInt = Field(gt=0)
    normalized_score: float | None = Field(default=None, ge=0, le=1)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IndependentGradeIncomplete(ValueError):
    """The judge lacked material; this is a terminal semantic outcome."""


def _evidence_file(evidence: str) -> str:
    return evidence.split("#", 1)[0].strip().replace("\\", "/")


def validate_evidence_paths(evidence_paths: list[str], staging_root: Path) -> None:
    allowed_roots = {"candidate_task.md", "reference_files", "anonymous_submission"}
    root = staging_root.resolve()
    for evidence in evidence_paths:
        relative_text = _evidence_file(evidence)
        relative = PurePosixPath(relative_text)
        if not relative_text or relative.is_absolute() or ".." in relative.parts:
            raise ValueError("independent_grade_unsafe_evidence_path")
        if relative.parts[0] not in allowed_roots:
            raise ValueError("independent_grade_evidence_outside_candidate_material")
        resolved = (root / Path(*relative.parts)).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("independent_grade_unsafe_evidence_path") from exc
        if not resolved.is_file():
            raise ValueError("independent_grade_evidence_file_missing")


def finalize_independent_grade(
    *,
    task_id: str,
    submission_id: str,
    judge_id: str,
    rubric_items: list[FrozenRubricItemV1],
    draft: IndependentRubricGradeDraftV1,
    staging_root: Path,
    input_sha256: str,
    delivery_sha256: str,
) -> IndependentRubricGradeV1:
    rubric_by_id = {row.rubric_item_id: row for row in rubric_items}
    if len(rubric_by_id) != len(rubric_items):
        raise ValueError("independent_grade_duplicate_frozen_rubric_item")
    assessment_by_id = {row.rubric_item_id: row for row in draft.assessments}
    if set(assessment_by_id) != set(rubric_by_id):
        raise ValueError("independent_grade_rubric_coverage_mismatch")

    results: list[IndependentRubricItemResultV1] = []
    for rubric in rubric_items:
        assessment = assessment_by_id[rubric.rubric_item_id]
        if assessment.awarded > rubric.max_score:
            raise ValueError("independent_grade_awarded_out_of_range")
        if assessment.applicability == "not_triggered" and assessment.awarded != rubric.max_score:
            raise ValueError("independent_grade_untriggered_condition_must_not_lose_points")
        validate_evidence_paths(assessment.evidence_paths, staging_root)
        results.append(IndependentRubricItemResultV1(
            max_score=rubric.max_score,
            **assessment.model_dump(mode="python"),
        ))

    maximum = sum(row.max_score for row in results)
    incomplete = draft.material_status == "incomplete" or any(
        row.applicability == "unresolved" for row in results
    )
    total = None if incomplete else sum(row.awarded for row in results)
    normalized = None if total is None else round(total / maximum, 6)
    return IndependentRubricGradeV1(
        task_id=task_id,
        submission_id=submission_id,
        judge_id=judge_id,
        material_status="incomplete" if incomplete else "complete",
        material_notes=draft.material_notes,
        items=results,
        total_score=total,
        max_possible_score=maximum,
        normalized_score=normalized,
        input_sha256=input_sha256,
        rubric_sha256=canonical_json_sha256(rubric_items),
        delivery_sha256=delivery_sha256,
        review_sha256=canonical_json_sha256(draft),
    )


def finalize_independent_grade_v2(
    *,
    task_id: str,
    submission_id: str,
    judge_id: str,
    rubric_items: list[FrozenRubricItemV1],
    draft: IndependentRubricGradeDraftV2,
    staging_root: Path,
    input_sha256: str,
    delivery_sha256: str,
    validate_locator: Any,
) -> IndependentRubricGradeV1:
    """Finalize V2 while preserving the immutable V1 result contract."""
    rubric_by_id = {row.rubric_item_id: row for row in rubric_items}
    assessment_by_id = {row.rubric_item_id: row for row in draft.assessments}
    if len(rubric_by_id) != len(rubric_items) or set(assessment_by_id) != set(rubric_by_id):
        raise ValueError("independent_grade_rubric_coverage_mismatch")
    converted: list[IndependentRubricItemAssessmentV1] = []
    quantifier = re.compile(r"\b(all|every|each)\b", re.IGNORECASE)
    for rubric in rubric_items:
        assessment = assessment_by_id[rubric.rubric_item_id]
        if assessment.awarded > rubric.max_score:
            raise ValueError("independent_grade_awarded_out_of_range")
        if assessment.satisfaction == "met":
            if assessment.awarded != rubric.max_score or assessment.defects:
                raise ValueError("independent_grade_v2_met_score_conflict")
        elif assessment.satisfaction == "partial":
            if not assessment.support or not assessment.defects:
                raise ValueError("independent_grade_v2_partial_evidence_missing")
            if rubric.max_score == 1:
                if assessment.awarded != 0:
                    raise ValueError("independent_grade_v2_one_point_partial_must_zero")
            elif not 0 < assessment.awarded < rubric.max_score:
                raise ValueError("independent_grade_v2_partial_score_conflict")
        elif assessment.satisfaction == "not_met":
            if assessment.awarded != 0 or not assessment.defects:
                raise ValueError("independent_grade_v2_not_met_score_conflict")
        elif assessment.satisfaction == "not_triggered":
            if assessment.awarded != rubric.max_score:
                raise ValueError("independent_grade_untriggered_condition_must_not_lose_points")
        elif assessment.satisfaction == "unresolved" and assessment.awarded != 0:
            raise ValueError("independent_grade_v2_unresolved_must_zero")
        if assessment.awarded == rubric.max_score and quantifier.search(rubric.criterion):
            if assessment.verification_scope != "all_rows":
                raise ValueError("independent_grade_v2_quantified_full_requires_all_rows")
        for locator in assessment.evidence_paths:
            if "#sheet=" in locator:
                validate_locator(locator)
            else:
                validate_evidence_paths([locator], staging_root)
        applicability: Applicability = "unresolved" if assessment.satisfaction == "unresolved" else (
            "not_triggered" if assessment.satisfaction == "not_triggered" else "applicable"
        )
        converted.append(IndependentRubricItemAssessmentV1(
            rubric_item_id=assessment.rubric_item_id, awarded=assessment.awarded,
            applicability=applicability, evidence_paths=assessment.evidence_paths,
            rationale=assessment.rationale,
        ))
    return finalize_independent_grade(
        task_id=task_id, submission_id=submission_id, judge_id=judge_id,
        rubric_items=rubric_items,
        draft=IndependentRubricGradeDraftV1(
            material_status=draft.material_status, material_notes=draft.material_notes,
            assessments=converted,
        ), staging_root=staging_root, input_sha256=input_sha256, delivery_sha256=delivery_sha256,
    )


def adapt_gdpval_rubric(binding: Any) -> list[FrozenRubricItemV1]:
    rows = binding.rubric_items if hasattr(binding, "rubric_items") else binding["rubric_items"]
    result = []
    for row in rows:
        item = row.model_dump(mode="python") if hasattr(row, "model_dump") else row
        score = item["score"]
        if not float(score).is_integer():
            raise ValueError("independent_grade_gdpval_score_must_be_integer")
        result.append(FrozenRubricItemV1(
            rubric_item_id=item["rubric_item_id"],
            max_score=int(score),
            criterion=item["criterion"],
        ))
    return result


def adapt_r10_v1_rubric(rubric: Any) -> list[FrozenRubricItemV1]:
    rows = rubric.criteria if hasattr(rubric, "criteria") else rubric["criteria"]
    result = []
    for row in rows:
        item = row.model_dump(mode="python") if hasattr(row, "model_dump") else row
        points = round(float(item["weight"]) * 100)
        if points <= 0 or abs(points / 100 - float(item["weight"])) > 1e-9:
            raise ValueError("independent_grade_r10_weight_not_integer_percent")
        result.append(FrozenRubricItemV1(
            rubric_item_id=item["criterion_id"],
            max_score=points,
            criterion=item["description"],
        ))
    if sum(row.max_score for row in result) != 100:
        raise ValueError("independent_grade_r10_points_must_sum_to_100")
    return result
