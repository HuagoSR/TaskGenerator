from pathlib import Path

import pytest

from task_generator.evaluation.independent_rubric_grader import (
    FrozenRubricItemV1,
    IndependentRubricGradeDraftV1,
    finalize_independent_grade,
)
from task_generator.evaluation.stirrup_calibration import (
    StirrupPreflightResultV1,
    StirrupSolverAttemptV1,
    StirrupSolverReceiptV1,
    build_shadow_downward_diagnostic,
    freeze_model_panel,
    strict_grading_system_prompt,
)


HASH = "a" * 64


def _preflight(tier, model, role="primary", status="passed"):
    return StirrupPreflightResultV1(
        tier=tier, model_id=model, candidate_role=role, status=status,
        attempt_count=1, evidence_path=f"preflight/{tier}/{role}",
    )


def test_user_selected_no_gemini_panel_is_frozen():
    panel = freeze_model_panel([
        _preflight("strong", "gpt-5.4-mini"),
        _preflight("middle", "gpt-5-mini"),
        _preflight("weak", "gpt-4o-mini"),
    ])
    assert (panel.strong, panel.middle, panel.weak) == (
        "gpt-5.4-mini", "gpt-5-mini", "gpt-4o-mini",
    )


def test_unregistered_or_unavailable_fallback_is_rejected():
    with pytest.raises(ValueError, match="unregistered"):
        _preflight("middle", "gpt-5.6-luna", role="fallback")
    with pytest.raises(ValueError, match="unavailable"):
        freeze_model_panel([
            _preflight("strong", "gpt-5.4-mini"),
            _preflight("middle", "gpt-5-mini"),
            _preflight("weak", "gpt-4o-mini", status="semantic_failure"),
        ])


def test_solver_receipt_allows_only_pre_semantic_technical_recovery():
    receipt = StirrupSolverReceiptV1(
        task_id="task", solver_id="model", tier="strong", input_sha256=HASH,
        rubric_sha256="b" * 64, delivery_status="complete", delivery_sha256="c" * 64,
        attempts=[
            StirrupSolverAttemptV1(
                attempt_number=1, state="technical_failure_before_semantic_turn",
                semantic_phase_started=False, evidence_path="attempts/1",
            ),
            StirrupSolverAttemptV1(
                attempt_number=2, state="succeeded", semantic_phase_started=True,
                technical_recovery_of=1, evidence_path="attempts/2",
            ),
        ],
    )
    assert receipt.max_turns == 100
    bad = receipt.model_dump(mode="python")
    bad["attempts"][0]["state"] = "semantic_or_delivery_failure"
    bad["attempts"][0]["semantic_phase_started"] = True
    with pytest.raises(ValueError, match="not_rerunnable"):
        StirrupSolverReceiptV1.model_validate(bad)


def _primary(tmp_path: Path):
    (tmp_path / "candidate_task.md").write_text("task", encoding="utf-8")
    (tmp_path / "reference_files").mkdir()
    (tmp_path / "anonymous_submission").mkdir()
    (tmp_path / "anonymous_submission/result.txt").write_text("result", encoding="utf-8")
    rubric = [FrozenRubricItemV1(rubric_item_id="R", max_score=4, criterion="Professional result")]
    draft = IndependentRubricGradeDraftV1.model_validate({
        "material_status": "complete", "material_notes": "All material is readable.",
        "assessments": [{"rubric_item_id": "R", "awarded": 4, "applicability": "applicable",
                         "evidence_paths": ["anonymous_submission/result.txt"],
                         "rationale": "Direct evidence supports the result."}],
    })
    return finalize_independent_grade(
        task_id="task", submission_id="model", judge_id="judge", rubric_items=rubric,
        draft=draft, staging_root=tmp_path, input_sha256=HASH, delivery_sha256="b" * 64,
    )


def test_shadow_audit_is_separate_and_cannot_increase(tmp_path):
    primary = _primary(tmp_path)
    audit = IndependentRubricGradeDraftV1.model_validate({
        "material_status": "complete", "material_notes": "Shadow diagnostic only.",
        "assessments": [{"rubric_item_id": "R", "awarded": 2, "applicability": "applicable",
                         "evidence_paths": ["anonymous_submission/result.txt"],
                         "rationale": "Only partial direct evidence was found."}],
    })
    diagnostic = build_shadow_downward_diagnostic(primary, audit)
    assert diagnostic.total_reduction == 2
    assert diagnostic.primary_score_unchanged is True
    assert primary.total_score == 4
    audit.assessments[0].awarded = 5
    with pytest.raises(ValueError, match="cannot_increase"):
        build_shadow_downward_diagnostic(primary, audit)


def test_strict_prompt_requires_direct_evidence_without_hidden_penalty():
    prompt = strict_grading_system_prompt()
    assert "explicit, complete, direct" in prompt
    assert "Never\nadd criteria" in prompt
    assert "penalize a high aggregate score" in prompt
