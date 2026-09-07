from pathlib import Path

import pytest
from pydantic import ValidationError

from task_generator.evaluation.independent_rubric_grader import (
    FrozenRubricItemV1,
    IndependentRubricGradeDraftV1,
    adapt_gdpval_rubric,
    adapt_r10_v1_rubric,
    finalize_independent_grade,
    tree_sha256,
)


HASH = "a" * 64


def _root(tmp_path: Path) -> Path:
    (tmp_path / "candidate_task.md").write_text("task", encoding="utf-8")
    (tmp_path / "reference_files").mkdir(exist_ok=True)
    (tmp_path / "reference_files/source.txt").write_text("source", encoding="utf-8")
    (tmp_path / "anonymous_submission").mkdir(exist_ok=True)
    (tmp_path / "anonymous_submission/result.txt").write_text("result", encoding="utf-8")
    return tmp_path


def _rubric():
    return [
        FrozenRubricItemV1(rubric_item_id="R1", max_score=6, criterion="First result"),
        FrozenRubricItemV1(rubric_item_id="R2", max_score=4, criterion="Second result"),
    ]


def _draft(**changes):
    value = {
        "material_status": "complete",
        "material_notes": "All required files were available.",
        "assessments": [
            {"rubric_item_id": "R1", "awarded": 5, "applicability": "applicable",
             "evidence_paths": ["anonymous_submission/result.txt#section 1"], "rationale": "Mostly correct."},
            {"rubric_item_id": "R2", "awarded": 4, "applicability": "not_triggered",
             "evidence_paths": ["reference_files/source.txt"], "rationale": "Condition did not occur."},
        ],
    }
    value.update(changes)
    return IndependentRubricGradeDraftV1.model_validate(value)


def _finalize(tmp_path: Path, draft=None):
    return finalize_independent_grade(
        task_id="task", submission_id="submission", judge_id="judge",
        rubric_items=_rubric(), draft=draft or _draft(), staging_root=_root(tmp_path),
        input_sha256=HASH, delivery_sha256="b" * 64,
    )


def test_program_recomputes_totals_and_hashes(tmp_path):
    grade = _finalize(tmp_path)
    assert grade.total_score == 9
    assert grade.max_possible_score == 10
    assert grade.normalized_score == .9
    assert len(grade.rubric_sha256) == len(grade.review_sha256) == 64


def test_duplicate_and_missing_items_are_rejected(tmp_path):
    duplicate = _draft().model_dump(mode="python")
    duplicate["assessments"][1]["rubric_item_id"] = "R1"
    with pytest.raises(ValidationError, match="duplicate_rubric_item"):
        IndependentRubricGradeDraftV1.model_validate(duplicate)
    missing = _draft(assessments=_draft().model_dump(mode="python")["assessments"][:1])
    with pytest.raises(ValueError, match="coverage_mismatch"):
        _finalize(tmp_path, missing)


def test_score_range_and_untriggered_rule_are_enforced(tmp_path):
    excessive = _draft().model_copy(deep=True)
    excessive.assessments[0].awarded = 7
    with pytest.raises(ValueError, match="out_of_range"):
        _finalize(tmp_path, excessive)
    penalized = _draft().model_copy(deep=True)
    penalized.assessments[1].awarded = 3
    with pytest.raises(ValueError, match="must_not_lose_points"):
        _finalize(tmp_path, penalized)


def test_incomplete_or_unresolved_has_no_semantic_total(tmp_path):
    draft = _draft(material_status="incomplete")
    draft.assessments[0].applicability = "unresolved"
    grade = _finalize(tmp_path, draft)
    assert grade.material_status == "incomplete"
    assert grade.total_score is None
    assert grade.normalized_score is None


@pytest.mark.parametrize("path", ["../secret.txt", "teacher_truth.json", "reference_files/missing.txt"])
def test_evidence_path_must_be_visible_and_existing(tmp_path, path):
    draft = _draft().model_copy(deep=True)
    draft.assessments[0].evidence_paths = [path]
    with pytest.raises(ValueError, match="evidence"):
        _finalize(tmp_path, draft)


def test_adapters_preserve_original_scales():
    gdpval = adapt_gdpval_rubric({"rubric_items": [
        {"rubric_item_id": "G1", "score": 2.0, "criterion": "Required file exists"}
    ]})
    assert gdpval[0].max_score == 2
    r10 = adapt_r10_v1_rubric({"criteria": [
        {"criterion_id": "A", "weight": .25, "description": "Audit conclusion"},
        {"criterion_id": "B", "weight": .25, "description": "Audit evidence"},
        {"criterion_id": "C", "weight": .30, "description": "Audit scope"},
        {"criterion_id": "D", "weight": .20, "description": "Audit follow-up"},
    ]})
    assert [row.max_score for row in r10] == [25, 25, 30, 20]


def test_tree_hash_binds_names_and_contents(tmp_path):
    first = _root(tmp_path)
    before = tree_sha256(first)
    (first / "anonymous_submission/result.txt").write_text("changed", encoding="utf-8")
    assert tree_sha256(first) != before
