"""Agent-native, evidence-bound item grading for the R10.12-G2 calibration."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from openpyxl.utils.cell import range_boundaries
from pydantic import Field, StrictInt, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.evaluation.independent_rubric_grader import (
    Applicability,
    FrozenRubricItemV1,
    IndependentRubricGradeDraftV1,
    IndependentRubricGradeV1,
    IndependentRubricItemAssessmentV1,
    MaterialStatus,
    Satisfaction,
    VerificationScope,
    canonical_json_sha256,
    file_sha256,
    finalize_independent_grade,
)
from task_generator.evaluation.spreadsheet_evidence import SpreadsheetEvidenceV1


EvidenceRole = Literal["support", "defect"]
Coverage = Literal["presence", "sample", "all_rows"]
VerificationMethod = Literal[
    "file_presence",
    "value_comparison",
    "formula",
    "recalculated_value",
    "style_metadata",
]


class EvidenceRefV1(ScenarioFirstModel):
    relative_path: str = Field(min_length=1)
    sheet_name: str | None = Field(default=None, min_length=1)
    cell_range: str | None = Field(default=None, pattern=r"^[A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?$")
    evidence_role: EvidenceRole

    @model_validator(mode="after")
    def complete_spreadsheet_location(self) -> "EvidenceRefV1":
        if (self.sheet_name is None) != (self.cell_range is None):
            raise ValueError("agent_grade_partial_spreadsheet_location")
        if self.relative_path.casefold().endswith(".xlsx") and self.sheet_name is None:
            # A file-only XLSX citation is reserved for presence checks and is
            # validated against verification_scope by the controller.
            return self
        if self.sheet_name is not None and not self.relative_path.casefold().endswith(".xlsx"):
            raise ValueError("agent_grade_sheet_location_requires_xlsx")
        return self


class AgentRubricItemAssessmentV1(ScenarioFirstModel):
    rubric_item_id: str = Field(min_length=1)
    awarded: StrictInt = Field(ge=0)
    satisfaction: Satisfaction
    verification_scope: VerificationScope
    evidence_refs: list[EvidenceRefV1] = Field(min_length=1)
    support: list[str] = Field(default_factory=list)
    defects: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=5, max_length=1200)


class AgentRubricGradeDraftV1(ScenarioFirstModel):
    draft_version: Literal["r10.agent_rubric_grade_draft.1"] = "r10.agent_rubric_grade_draft.1"
    material_status: MaterialStatus
    material_notes: str = Field(min_length=1, max_length=1200)
    assessments: list[AgentRubricItemAssessmentV1] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "AgentRubricGradeDraftV1":
        identifiers = [row.rubric_item_id for row in self.assessments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("agent_grade_duplicate_rubric_item")
        return self


class AgentRubricItemAssessmentV2(ScenarioFirstModel):
    """Separates how much was checked from how it was checked."""

    rubric_item_id: str = Field(min_length=1)
    awarded: StrictInt = Field(ge=0)
    satisfaction: Satisfaction
    coverage: Coverage
    verification_methods: list[VerificationMethod] = Field(min_length=1)
    evidence_refs: list[EvidenceRefV1] = Field(min_length=1)
    support: list[str] = Field(default_factory=list)
    defects: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=5, max_length=1200)

    @model_validator(mode="after")
    def coherent_methods(self) -> "AgentRubricItemAssessmentV2":
        if len(self.verification_methods) != len(set(self.verification_methods)):
            raise ValueError("agent_grade_v2_duplicate_verification_method")
        if self.coverage == "presence" and any(
            method not in {"file_presence", "style_metadata"}
            for method in self.verification_methods
        ):
            raise ValueError("agent_grade_v2_presence_method_conflict")
        if self.coverage != "presence" and self.verification_methods == ["file_presence"]:
            raise ValueError("agent_grade_v2_nonpresence_requires_content_method")
        return self


class AgentRubricGradeDraftV2(ScenarioFirstModel):
    draft_version: Literal["r10.agent_rubric_grade_draft.2"] = "r10.agent_rubric_grade_draft.2"
    material_status: MaterialStatus
    material_notes: str = Field(min_length=1, max_length=1200)
    assessments: list[AgentRubricItemAssessmentV2] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "AgentRubricGradeDraftV2":
        identifiers = [row.rubric_item_id for row in self.assessments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("agent_grade_duplicate_rubric_item")
        return self


class CanonicalCitationV1(ScenarioFirstModel):
    citation_id: str = Field(pattern=r"^cite_[0-9a-f]{16}$")
    relative_path: str
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheet_name: str | None = None
    cell_range: str | None = None
    evidence_role: EvidenceRole
    locator: str


def _safe_file(root: Path, relative_text: str) -> Path:
    relative = PurePosixPath(relative_text.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("agent_grade_unsafe_evidence_path")
    if relative.parts[0] not in {"candidate_task.md", "reference_files", "anonymous_submission"}:
        raise ValueError("agent_grade_evidence_outside_candidate_material")
    resolved = (root / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("agent_grade_unsafe_evidence_path") from exc
    if not resolved.is_file():
        raise ValueError("agent_grade_evidence_file_missing")
    return resolved


def canonicalize_evidence_ref(
    ref: EvidenceRefV1,
    *,
    staging_root: Path,
    evidence: dict[str, SpreadsheetEvidenceV1],
    verification_scope: VerificationScope,
) -> CanonicalCitationV1:
    path = ref.relative_path.replace("\\", "/")
    resolved = _safe_file(staging_root, path)
    locator = path
    if ref.sheet_name is None:
        if resolved.suffix.casefold() == ".xlsx" and verification_scope != "presence":
            raise ValueError("agent_grade_xlsx_nonpresence_requires_range")
    else:
        workbook = evidence.get(path)
        if workbook is None:
            raise ValueError("agent_grade_spreadsheet_evidence_missing")
        sheet = next((row for row in workbook.sheets if row.name == ref.sheet_name), None)
        if sheet is None:
            raise ValueError("agent_grade_sheet_unknown")
        assert ref.cell_range is not None
        min_col, min_row, max_col, max_row = range_boundaries(ref.cell_range)
        if max_row > sheet.max_row or max_col > sheet.max_column:
            raise ValueError("agent_grade_range_outside_used_range")
        populated = False
        for cell in sheet.cells:
            col, row, _, _ = (*range_boundaries(cell.address),)
            if min_col <= col <= max_col and min_row <= row <= max_row:
                populated = True
                break
        if not populated:
            raise ValueError("agent_grade_evidence_range_empty")
        locator = f"{path}#sheet={ref.sheet_name}&range={ref.cell_range}"
    digest_input = {
        "locator": locator,
        "role": ref.evidence_role,
        "file_sha256": file_sha256(resolved),
    }
    citation_id = f"cite_{canonical_json_sha256(digest_input)[:16]}"
    return CanonicalCitationV1(
        citation_id=citation_id,
        relative_path=path,
        file_sha256=digest_input["file_sha256"],
        sheet_name=ref.sheet_name,
        cell_range=ref.cell_range,
        evidence_role=ref.evidence_role,
        locator=locator,
    )


def finalize_agent_rubric_grade(
    *,
    task_id: str,
    submission_id: str,
    judge_id: str,
    rubric_items: list[FrozenRubricItemV1],
    draft: AgentRubricGradeDraftV1,
    staging_root: Path,
    spreadsheet_evidence: dict[str, SpreadsheetEvidenceV1],
    input_sha256: str,
    delivery_sha256: str,
) -> tuple[IndependentRubricGradeV1, list[CanonicalCitationV1]]:
    rubric_by_id = {row.rubric_item_id: row for row in rubric_items}
    assessment_by_id = {row.rubric_item_id: row for row in draft.assessments}
    if len(rubric_by_id) != len(rubric_items) or set(assessment_by_id) != set(rubric_by_id):
        raise ValueError("agent_grade_rubric_coverage_mismatch")
    quantifier = re.compile(r"\b(all|every|each)\b", re.IGNORECASE)
    citations: list[CanonicalCitationV1] = []
    converted: list[IndependentRubricItemAssessmentV1] = []
    for rubric in rubric_items:
        row = assessment_by_id[rubric.rubric_item_id]
        if row.awarded > rubric.max_score:
            raise ValueError("agent_grade_awarded_out_of_range")
        roles = {ref.evidence_role for ref in row.evidence_refs}
        if row.satisfaction == "met":
            if row.awarded != rubric.max_score or row.defects or not row.support or "support" not in roles:
                raise ValueError("agent_grade_met_score_conflict")
        elif row.satisfaction == "partial":
            if not row.support or not row.defects or roles != {"support", "defect"}:
                raise ValueError("agent_grade_partial_evidence_missing")
            if rubric.max_score == 1 and row.awarded != 0:
                raise ValueError("agent_grade_one_point_partial_must_zero")
            if rubric.max_score > 1 and not 0 < row.awarded < rubric.max_score:
                raise ValueError("agent_grade_partial_score_conflict")
        elif row.satisfaction == "not_met":
            if row.awarded != 0 or not row.defects or "defect" not in roles:
                raise ValueError("agent_grade_not_met_score_conflict")
        elif row.satisfaction == "not_triggered":
            if row.awarded != rubric.max_score or not row.support:
                raise ValueError("agent_grade_not_triggered_score_conflict")
        elif row.satisfaction == "unresolved" and row.awarded != 0:
            raise ValueError("agent_grade_unresolved_must_zero")
        if row.awarded == rubric.max_score and quantifier.search(rubric.criterion):
            if row.verification_scope != "all_rows":
                raise ValueError("agent_grade_quantified_full_requires_all_rows")
            roots = {PurePosixPath(ref.relative_path).parts[0] for ref in row.evidence_refs if ref.sheet_name}
            if not {"reference_files", "anonymous_submission"}.issubset(roots):
                raise ValueError("agent_grade_quantified_full_requires_candidate_and_reference")
        item_citations = [
            canonicalize_evidence_ref(
                ref,
                staging_root=staging_root,
                evidence=spreadsheet_evidence,
                verification_scope=row.verification_scope,
            )
            for ref in row.evidence_refs
        ]
        citations.extend(item_citations)
        applicability: Applicability = "unresolved" if row.satisfaction == "unresolved" else (
            "not_triggered" if row.satisfaction == "not_triggered" else "applicable"
        )
        converted.append(IndependentRubricItemAssessmentV1(
            rubric_item_id=row.rubric_item_id,
            awarded=row.awarded,
            applicability=applicability,
            evidence_paths=[citation.locator for citation in item_citations],
            rationale=row.rationale,
        ))
    grade = finalize_independent_grade(
        task_id=task_id,
        submission_id=submission_id,
        judge_id=judge_id,
        rubric_items=rubric_items,
        draft=IndependentRubricGradeDraftV1(
            material_status=draft.material_status,
            material_notes=draft.material_notes,
            assessments=converted,
        ),
        staging_root=staging_root,
        input_sha256=input_sha256,
        delivery_sha256=delivery_sha256,
    )
    unique = {row.citation_id: row for row in citations}
    return grade, [unique[key] for key in sorted(unique)]


def finalize_agent_rubric_grade_v2(
    *,
    task_id: str,
    submission_id: str,
    judge_id: str,
    rubric_items: list[FrozenRubricItemV1],
    draft: AgentRubricGradeDraftV2,
    staging_root: Path,
    spreadsheet_evidence: dict[str, SpreadsheetEvidenceV1],
    input_sha256: str,
    delivery_sha256: str,
) -> tuple[IndependentRubricGradeV1, list[CanonicalCitationV1]]:
    """Apply the frozen scoring rules with orthogonal coverage and methods.

    V1 remains readable for the frozen G2 result. V2 maps only the coverage
    dimension into V1's historical verification_scope so `formula` can be a
    method while `all_rows` independently records full population coverage.
    """
    converted = []
    for row in draft.assessments:
        has_range = any(ref.sheet_name is not None for ref in row.evidence_refs)
        if any(method != "file_presence" for method in row.verification_methods) and not has_range:
            raise ValueError("agent_grade_v2_content_method_requires_range")
        converted.append(AgentRubricItemAssessmentV1(
            rubric_item_id=row.rubric_item_id,
            awarded=row.awarded,
            satisfaction=row.satisfaction,
            verification_scope=row.coverage,
            evidence_refs=row.evidence_refs,
            support=row.support,
            defects=row.defects,
            rationale=row.rationale,
        ))
    return finalize_agent_rubric_grade(
        task_id=task_id,
        submission_id=submission_id,
        judge_id=judge_id,
        rubric_items=rubric_items,
        draft=AgentRubricGradeDraftV1(
            material_status=draft.material_status,
            material_notes=draft.material_notes,
            assessments=converted,
        ),
        staging_root=staging_root,
        spreadsheet_evidence=spreadsheet_evidence,
        input_sha256=input_sha256,
        delivery_sha256=delivery_sha256,
    )
