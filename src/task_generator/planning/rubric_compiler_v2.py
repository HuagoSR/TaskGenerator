"""Requirement-grounded rubric authoring, not a new evaluator pipeline.

The frozen task remains authoritative. V2 is a separately versioned output;
it does not alter the V1 decision matrix, teacher truth or historical grades.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel, TaskDecisionMatrixV1


class RubricBasisV2(ScenarioFirstModel):
    path: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    explanation: str = Field(min_length=5)


class RubricScoreBoundaryV2(ScenarioFirstModel):
    awarded: StrictInt = Field(ge=0)
    description: str = Field(min_length=5)


class TaskSpecificRubricItemV2(ScenarioFirstModel):
    criterion_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    decision_id: str = Field(min_length=1)
    requirement: str = Field(min_length=5)
    max_points: StrictInt = Field(ge=1)
    score_boundaries: list[RubricScoreBoundaryV2] = Field(min_length=2)
    requirement_basis: list[RubricBasisV2] = Field(min_length=1)
    evidence_paths: list[str] = Field(min_length=1)
    applicability: str = Field(min_length=5)
    acceptable_alternatives: str = Field(min_length=5)
    verification: str = Field(min_length=10)

    @model_validator(mode="after")
    def complete_score_scale(self):
        scores = [row.awarded for row in self.score_boundaries]
        if len(scores) != len(set(scores)) or set(scores) != set(range(self.max_points + 1)):
            raise ValueError("rubric_score_boundaries_incomplete_or_duplicate")
        if len(self.evidence_paths) != len(set(self.evidence_paths)):
            raise ValueError("rubric_evidence_paths_duplicate")
        return self


class TaskSpecificRubricV2(ScenarioFirstModel):
    rubric_version: Literal["r10.task_specific_rubric.2"] = "r10.task_specific_rubric.2"
    task_id: str = Field(min_length=1)
    criteria: list[TaskSpecificRubricItemV2] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [row.criterion_id for row in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("rubric_duplicate_criterion")
        # This catches exact repetition only. Semantic overlap is reviewed by Agent.
        requirements = [" ".join(row.requirement.casefold().split()) for row in self.criteria]
        if len(requirements) != len(set(requirements)):
            raise ValueError("rubric_exact_duplicate_requirement")
        return self

    @property
    def total_points(self) -> int:
        return sum(row.max_points for row in self.criteria)


class RubricCompilationV2(ScenarioFirstModel):
    result_version: Literal["r10.rubric_compilation.2"] = "r10.rubric_compilation.2"
    task_id: str
    status: Literal["compiled", "upstream_issue"]
    rubric: TaskSpecificRubricV2 | None
    upstream_issues: list[str]
    summary_zh: str = Field(min_length=10)

    @model_validator(mode="after")
    def result_consistency(self):
        if self.status == "compiled":
            if self.rubric is None or self.upstream_issues or self.rubric.task_id != self.task_id:
                raise ValueError("rubric_compilation_result_mismatch")
        elif self.rubric is not None or not self.upstream_issues:
            raise ValueError("rubric_upstream_issue_must_not_mask_with_rubric")
        return self


REVIEW_CHECKS = {
    "requirement_alignment", "no_double_counting", "evidence_support",
    "conditional_exceptions", "equivalent_expression", "verification_coverage",
    "supervision_consistency",
}


class RubricReviewCheckV2(ScenarioFirstModel):
    check: Literal["requirement_alignment", "no_double_counting", "evidence_support",
                   "conditional_exceptions", "equivalent_expression", "verification_coverage",
                   "supervision_consistency"]
    status: Literal["pass", "issue", "uncertain"]
    criterion_ids: list[str]
    evidence: list[RubricBasisV2] = Field(min_length=1)
    rationale_zh: str = Field(min_length=10)


class RubricAuthorReviewV2(ScenarioFirstModel):
    review_version: Literal["r10.rubric_author_review.2"] = "r10.rubric_author_review.2"
    task_id: str
    decision: Literal["pass", "revision_required", "upstream_issue"]
    checks: list[RubricReviewCheckV2]
    summary_zh: str = Field(min_length=10)

    @model_validator(mode="after")
    def complete_review(self):
        names = [row.check for row in self.checks]
        if len(names) != len(REVIEW_CHECKS) or set(names) != REVIEW_CHECKS:
            raise ValueError("rubric_review_checks_incomplete")
        all_pass = all(row.status == "pass" for row in self.checks)
        if (self.decision == "pass") != all_pass:
            raise ValueError("rubric_review_conclusion_mismatch")
        return self


def _visible_file(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
            or not (name in {"candidate_task.md", "deliverable_contract.json"}
                    or name.startswith("reference_files/"))):
        raise ValueError("rubric_basis_not_candidate_visible")
    full = root / name
    if not full.is_file() or full.is_symlink() or not full.resolve().is_relative_to(root.resolve()):
        raise ValueError("rubric_basis_file_missing_or_unsafe")
    return full


def validate_rubric(rubric: TaskSpecificRubricV2, matrix: TaskDecisionMatrixV1, root: Path) -> None:
    expected = {row.decision_id for row in matrix.decision_points}
    actual = {row.decision_id for row in rubric.criteria}
    if not expected <= actual or not actual <= expected | {"deliverable_structure"}:
        raise ValueError("rubric_decision_coverage_invalid")
    for row in rubric.criteria:
        if row.decision_id == "deliverable_structure":
            # A declared delivery requirement is not a new professional decision.
            # Its support must be exclusively the visible task and single contract.
            public_contract = {"candidate_task.md", "deliverable_contract.json"}
            basis = {item.path for item in row.requirement_basis}
            contract = json.loads(_visible_file(root, "deliverable_contract.json").read_text(encoding="utf-8"))
            declared = {item["relative_path"] for item in contract.get("deliverables", [])}
            for name in declared:
                path = PurePosixPath(name)
                if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                        or not name.startswith("deliverable_files/")):
                    raise ValueError("rubric_delivery_contract_path_unsafe")
            if ("deliverable_contract.json" not in basis or not basis <= public_contract
                    or not set(row.evidence_paths) <= public_contract | declared):
                raise ValueError("rubric_delivery_group_requires_visible_contract")
            # Prospective deliverables are verification targets, not existing inputs.
            # Only exact paths already declared by the frozen contract are allowed.
            existing_evidence = [name for name in row.evidence_paths if name not in declared]
        else:
            existing_evidence = row.evidence_paths
        for name in existing_evidence + [basis.path for basis in row.requirement_basis]:
            _visible_file(root, name)


def validate_review(review: RubricAuthorReviewV2, rubric: TaskSpecificRubricV2, root: Path) -> None:
    ids = {row.criterion_id for row in rubric.criteria}
    if review.task_id != rubric.task_id:
        raise ValueError("rubric_review_task_mismatch")
    for check in review.checks:
        if len(check.criterion_ids) != len(set(check.criterion_ids)) or not set(check.criterion_ids) <= ids:
            raise ValueError("rubric_review_unknown_or_duplicate_criterion")
        # Every dimension reviews the entire rubric, not a cherry-picked sample.
        if set(check.criterion_ids) != ids:
            raise ValueError("rubric_review_coverage_incomplete")
        for basis in check.evidence:
            if basis.path in {"new_rubric.json", "teacher_truth.json", "decision_matrix.json"}:
                file = root / basis.path
                if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
                    raise ValueError("rubric_review_source_missing_or_unsafe")
            else:
                _visible_file(root, basis.path)


def sum_rubric_points(rubric: TaskSpecificRubricV2, awarded: dict[str, int]) -> float:
    """Future single-submission scoring: no preference, veto or extra penalties."""
    if set(awarded) != {row.criterion_id for row in rubric.criteria}:
        raise ValueError("rubric_awards_incomplete")
    for row in rubric.criteria:
        score = awarded[row.criterion_id]
        if type(score) is not int or not 0 <= score <= row.max_points:
            raise ValueError("rubric_award_out_of_bounds")
    return sum(awarded.values()) / rubric.total_points


def rubric_compiler_prompt(task_id: str) -> str:
    return f"""You are the task factory's rubric compiler, NOT a Solver or grader.
Read candidate_task.md, deliverable_contract.json, all reference_files/, teacher_truth.json
and decision_matrix.json. Preserve all inputs byte-for-byte. Task ID: {task_id}.
Compile a new TaskSpecificRubricV2; return RubricCompilationV2 matching grade_schema.json.
Use concise Chinese for requirements, anchors, explanations and summary; preserve source filenames and exact citations.
Keep the existing professional decisions. A decision may have several independently observable scoring items.
An explicitly requested deliverable-structure item may use decision_id deliverable_structure, grounded
only in candidate_task.md and deliverable_contract.json; this is not a new professional decision.
Choose items and positive integer maxima for this actual task; no fixed item count or mechanical 50/30/20 split.
Every allowed integer from zero through max_points needs a concrete boundary. Binary items need 0 and 1 only.
Each requirement must follow from the candidate's requested work or a candidate-visible professional basis.
Hidden teacher preferences cannot create obligations. Cite requirement_basis with exact input-relative path,
visible section/cell locator and explanation. teacher_truth.json is NOT a candidate-visible requirement basis.
State applicability, explicit exceptions and acceptable equivalent forms. If a prerequisite demonstrably does
not apply, award full row credit with explanation; unreadable or unresolved applicability means incomplete,
not guessed points. Do not require exact headings or wording unless candidate instructions actually do.
One item evaluates one observable result. Shared evidence is fine; double-counting the same mistake is not.
Verification must specify required scope and concrete evidence: all periods/rows when requested, not only
the final balance; actual formulas/values and reconciliations, not merely the presence of a spreadsheet.
For narrative judgments accept supportable conditional conclusions, and distinguish omission from incorrectness.
Do not introduce holistic preference, independent major-error veto or arbitrary formatting penalties.
If frozen prompt/truth/matrix cannot support a fair rubric, return status upstream_issue, rubric null,
and explain the exact contradiction; do not repair facts or change the candidate instructions.
Read actual files using installed tools. Do not access external sites, other runs, model answers or scores.
Do not create task evidence or a candidate deliverable. Return the final JSON, not a score.
"""


def rubric_review_prompt(task_id: str) -> str:
    return f"""Independently review the task factory's new_rubric.json for task {task_id}.
This is rubric quality review, NOT scoring any Solver submission. Read candidate_task.md, contract,
all reference_files/, teacher_truth.json and decision_matrix.json; preserve all inputs.
Return RubricAuthorReviewV2 matching grade_schema.json, in Chinese.
Check every criterion under each of the seven review dimensions; list all criterion IDs in each check.
Ground findings in actual candidate file paths and section/cell locators. Do not accept a hidden teacher
claim as sufficient basis for a new candidate obligation. Independently check arithmetic and explicit scope.
Check requirement alignment, double counting, evidence support, exceptions, equivalent expressions,
complete verification scope, and consistency of frozen supervision. Mention exact offending IDs in rationale.
Reasonable professional gray areas are allowed; do not demand identical phrasing or a single professional method.
Do not propose extra quality obligations absent from the assignment, or force an uncertain fact to be certain.
If any dimension is issue/uncertain, do not pass. Use upstream_issue for genuine frozen prompt/truth problems.
Do not rewrite the rubric, task or answers. Do not access other runs, Solver submissions, grades or rankings.
"""
