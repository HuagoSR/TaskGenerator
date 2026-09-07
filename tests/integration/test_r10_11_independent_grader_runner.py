import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_11_independent_grader", ROOT / "Test/run_r10_11_independent_grader.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_fixed_assignment_matrix_and_sentinels():
    rows = RUNNER.assignments()
    primary = [row for row in rows if row["role"] == "primary"]
    checks = [row for row in rows if row["role"] == "check"]
    assert len(rows) == 21
    assert len(primary) == 17
    assert len(checks) == 4
    assert len({row["assignment_id"] for row in rows}) == 21
    assert {(row["task_id"], row["submission_id"]) for row in checks} == set(RUNNER.SENTINELS)


def test_prepare_is_provider_free_and_binds_every_input(tmp_path, monkeypatch):
    monkeypatch.setattr(RUNNER, "_primary_call", lambda *_: (_ for _ in ()).throw(AssertionError("provider")))
    monkeypatch.setattr(RUNNER, "_run_remote", lambda **_: (_ for _ in ()).throw(AssertionError("provider")))
    scope = RUNNER.prepare(tmp_path / "campaign")
    assert len(scope["hashes"]) == 21
    assert scope["primary"]["normal_call_limit"] == 17
    assert scope["primary"]["campaign_recovery_limit"] == 3
    assert scope["checks"]["normal_call_limit"] == 4
    assert scope["checks"]["campaign_recovery_limit"] == 1
    assert "semantic_redraw" in scope["excluded_actions"]
    assert "downward_audit" in scope["excluded_actions"]
    for hashes in scope["hashes"].values():
        assert set(hashes) == {"input_sha256", "rubric_sha256", "delivery_sha256"}
        assert all(len(value) == 64 for value in hashes.values())
    schema = __import__("json").loads(next((tmp_path / "campaign/sessions").glob("*/workspace/grade_schema.json")).read_text())
    assert set(schema["required"]) == set(schema["properties"])
    assessment = schema["$defs"]["IndependentRubricItemAssessmentV1"]
    assert set(assessment["required"]) == set(assessment["properties"])


def test_summary_rejects_large_sentinel_delta():
    rows = []
    for task_id, submission_id in RUNNER.SENTINELS:
        item = {"rubric_item_id": "R", "max_score": 10, "awarded": 10,
                "applicability": "applicable", "evidence_paths": ["candidate_task.md"], "rationale": "ok"}
        common = {"task_id": task_id, "submission_id": submission_id, "material_status": "complete",
                  "total_score": 10, "max_possible_score": 10, "items": [item]}
        rows.append(common | {"judge_id": RUNNER.PRIMARY_JUDGE, "normalized_score": 1.0})
        rows.append(common | {"judge_id": RUNNER.CHECK_JUDGE, "normalized_score": .8,
                              "items": [item | {"awarded": 8}], "total_score": 8})
    # Add the other 13 primary identities so only the sentinel gate fails.
    for spec in RUNNER.assignments():
        key = (spec["task_id"], spec["submission_id"])
        if spec["role"] == "primary" and key not in {(row["task_id"], row["submission_id"]) for row in rows}:
            rows.append({"task_id": spec["task_id"], "submission_id": spec["submission_id"],
                         "judge_id": RUNNER.PRIMARY_JUDGE, "material_status": "complete",
                         "total_score": 10, "max_possible_score": 10, "normalized_score": 1.0,
                         "items": [{"rubric_item_id": "R", "max_score": 10, "awarded": 10,
                                    "applicability": "applicable", "evidence_paths": ["candidate_task.md"],
                                    "rationale": "ok"}]})
    summary = RUNNER.summarize(rows, {"assignments": RUNNER.assignments()})
    assert summary["structural_valid"] is True
    assert summary["sentinel_acceptance"] is False
    assert summary["status"] == "incomplete"


def test_parse_finalize_accepts_scope_hash_bundle(tmp_path):
    row = RUNNER.assignments()[0]
    workspace = tmp_path / "workspace"
    hashes = RUNNER._stage(workspace, row)
    _, _, rubric = RUNNER._sources(row)
    draft = {
        "material_status": "complete", "material_notes": "All files were readable.",
        "assessments": [
            {"rubric_item_id": item.rubric_item_id, "awarded": item.max_score,
             "applicability": "applicable", "evidence_paths": ["candidate_task.md"],
             "rationale": "The visible task and submission satisfy this item."}
            for item in rubric
        ],
    }
    (workspace / "grade.raw.json").write_text(__import__("json").dumps(draft), encoding="utf-8")
    grade = RUNNER._parse_finalize(workspace, row, hashes)
    assert grade.total_score == grade.max_possible_score


def test_invalid_delivery_is_rejected_before_semantic_staging(tmp_path):
    row = RUNNER.assignments()[0]
    task, _, _ = RUNNER._sources(row)
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    expected = __import__("json").loads(
        (task / "binding.json").read_text(encoding="utf-8")
    )["expected_deliverables"][0]
    (delivery / expected).write_bytes(b"not-an-ooxml-package")
    import pytest
    with pytest.raises(ValueError, match="invalid_delivery"):
        RUNNER._validate_delivery_root(task, delivery, row)
