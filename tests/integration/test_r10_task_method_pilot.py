import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Test"))
import run_r10_task_method_pilot as pilot
from task_generator.production import task_method_pilot as method


def test_budget_survives_restart_and_caps_every_call(monkeypatch):
    monkeypatch.setattr(pilot.time, "time", lambda: 100)
    assert pilot.seconds_left({"deadline_epoch": 150}) == 50
    assert pilot.seconds_left({"deadline_epoch": 10000}) == 1800
    with pytest.raises(RuntimeError, match="budget"):
        pilot.seconds_left({"deadline_epoch": 100})


def test_closed_stage_and_recovery_budget_cannot_redraw():
    receipt = {"sessions": [{"case": "dev_01", "stage": "generate", "status": "incomplete"}], "recoveries_used": 0}
    with pytest.raises(ValueError):
        pilot.count_session(receipt, "dev_01", "generate")
    with pytest.raises(ValueError):
        pilot.count_session(receipt, "dev_01", "generate", True)
    receipt["sessions"][0]["status"] = "presemantic_transport_failure"
    pilot.count_session(receipt, "dev_01", "generate", True)
    assert receipt["recoveries_used"] == 1
    receipt["recoveries_used"] = 2
    with pytest.raises(ValueError):
        pilot.count_session(receipt, "dev_01", "generate", True)


def test_24_attempts_is_hard_limit():
    with pytest.raises(RuntimeError, match="session_budget"):
        pilot.count_session({"sessions": [{"case": "a", "stage": "b"}] * 24}, "new", "generate")


def test_stage_isolation_and_solver_has_no_supervision(tmp_path):
    spec = method.CASES[0]
    public = tmp_path / "public/dev_01"
    for name in ("public_context.json", "professional_rules.json", "sources.json", "work_seed.json"):
        pilot.write(public / name, {"public": True})
    results = tmp_path / "results/dev_01"
    pilot.write(results / "generate/raw/candidate/source.json", {})
    pilot.write(results / "generate/raw/hidden/world.json", {"secret": "HIDDEN_MARKER"})
    for name in ("candidate_task.md", "deliverable_contract.json"):
        pilot.write(results / "mine/derived" / name, {})
    pilot.write(results / "mine/raw/task.json", {})
    for name in ("supervision.json", "new_rubric.json"):
        pilot.write(results / "compile/raw" / name, {"teacher": "TEACHER_MARKER"})
    for stage in ("mine", "compile", "review", "solve"):
        target = tmp_path / stage
        pilot.stage_inputs(tmp_path, spec, stage, target)
        text = "".join(p.read_text() for p in target.rglob("*") if p.is_file())
        assert "HIDDEN_MARKER" not in text
        assert ("TEACHER_MARKER" in text) == (stage == "review")
    assert set(pilot.tree(tmp_path / "solve")) == {"reference_files/source.json", "candidate_task.md", "deliverable_contract.json"}


@pytest.mark.parametrize("value", ["../hidden/world.md", "/etc/passwd", "C:/auth.json", "reference_files/../../hidden/x", "work_seed.json", "reference_files\\x"])
def test_exact_reference_allowlist(tmp_path, value):
    with pytest.raises(ValueError):
        method.reference(tmp_path, value)


def test_compilation_cannot_create_obligation_from_teacher(tmp_path):
    pilot.write(tmp_path / "supervision.json", {})
    with pytest.raises(ValueError):
        method.reference(tmp_path, "supervision.json", candidate_only=True)
    assert method.reference(tmp_path, "supervision.json").is_file()


def test_deliverable_contract_supports_multiple_formats(tmp_path):
    pilot.write(tmp_path / "inputs/reference_files/source.txt", {})
    task = {"natural_task": True, "rationale": "visible work", "title": "Review", "prompt": "Prepare a useful analysis.",
            "requirements": [{"id": "r1", "requirement": "Analyze", "expected_work_product": "analysis", "basis": [{"path": "reference_files/source.txt", "locator": "line 1", "explanation": "the work request"}]}],
            "deliverables": [{"file_name": name, "relative_path": "deliverable_files/" + name, "format": fmt} for name, fmt in (("analysis.xlsx", "xlsx"), ("memo.docx", "docx"))]}
    pilot.write(tmp_path / "raw/task.json", task)
    result = method.task_result(tmp_path / "raw", tmp_path / "inputs")
    assert len(result["contract"]["deliverables"]) == 2
    assert "deliverable_files/analysis.xlsx" in result["candidate_task"]
    assert "deliverable_files/memo.docx" in result["candidate_task"]


def test_no_natural_task_has_no_replacement(tmp_path):
    pilot.write(tmp_path / "task.json", {"natural_task": False, "rationale": "No visible work"})
    assert method.task_result(tmp_path, tmp_path)["status"] == "no_natural_task"


def test_mining_can_use_supplied_public_trigger_but_not_teacher(tmp_path):
    pilot.write(tmp_path / "inputs/public_context.json", {"role": "reviewer"})
    task = {"natural_task": True, "rationale": "public work trigger", "title": "Review", "prompt": "Prepare analysis for the reviewer.",
            "requirements": [{"id": "r1", "requirement": "Analyze", "expected_work_product": "analysis", "basis": [{"path": "public_context.json", "locator": "role", "explanation": "the visible work role"}]}],
            "deliverables": [{"file_name": "memo.docx", "relative_path": "deliverable_files/memo.docx", "format": "docx"}]}
    pilot.write(tmp_path / "raw/task.json", task)
    assert method.task_result(tmp_path / "raw", tmp_path / "inputs")["status"] == "completed"
    task["requirements"][0]["basis"][0]["path"] = "supervision.json"
    pilot.write(tmp_path / "inputs/supervision.json", {})
    pilot.write(tmp_path / "raw/task.json", task)
    with pytest.raises(ValueError):
        method.task_result(tmp_path / "raw", tmp_path / "inputs")


def test_local_recovery_does_not_repeat_a_completed_turn(tmp_path):
    receipt = {"sessions": [{"case": "dev_01", "stage": "generate", "ordinal": 1, "status": "completed", "outcome": {"status": "completed"}},
                            {"case": "dev_01", "stage": "mine", "ordinal": 2, "status": "incomplete"}],
               "controller_recovery": {"path": "recovery.json"}}
    pilot.write(tmp_path / "recovery.json", {"session": 2, "outcome": {"status": "completed"}})
    assert pilot.completed_outcome(tmp_path, receipt, "dev_01", "generate")["status"] == "completed"
    assert pilot.completed_outcome(tmp_path, receipt, "dev_01", "mine")["status"] == "completed"
    assert pilot.completed_outcome(tmp_path, receipt, "dev_01", "compile") is None
    receipt.pop("controller_recovery")
    with pytest.raises(ValueError):
        pilot.completed_outcome(tmp_path, receipt, "dev_01", "mine")


def test_trials_choose_first_pass_per_domain_only():
    cases = {"dev_01": {"status": "completed", "quality": "pass"}, "val_01": {"status": "completed", "quality": "uncertain"},
             "val_02": {"status": "completed", "quality": "pass"}, "val_03": {"status": "incomplete", "quality": "pass"},
             "val_04": {"status": "completed", "quality": "pass"}}
    assert method.select_trials(cases) == ["val_02", "val_04"]
    assert method.select_trials({}) == []


def test_no_grader_or_stirrup_entry_and_readonly_mounts():
    source = Path(pilot.__file__).read_text(encoding="utf-8")
    assert 'f"{remote}/workspace:/workspace:ro"' in source
    assert "_execute_judge(" not in source and "stirrup" not in source.lower()
    for stage in (*method.STAGES, "solve"):
        script = pilot.transport_script(stage)
        assert "docx_office_check" not in script and "grade_schema" not in script
    assert method.prompts()["solve"] == method.prompts()["solve"]


def test_existing_directory_rejected_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    root = tmp_path / "artifacts/r10/existing"
    pilot.write(root / "receipt.json", {"first_failure": "keep"})
    before = pilot.tree(root)
    with pytest.raises(FileExistsError):
        pilot.prepare(root, "development")
    assert pilot.tree(root) == before


def test_semantic_failure_skips_dependents_but_continues_independent_cases(tmp_path, monkeypatch):
    pilot.write(tmp_path / "receipt.json", {"status": "validation_prepared", "sessions": [], "cases": {}, "recoveries_used": 0, "first_failure": None, "task_level_manual_edits": 0})
    pilot.write(tmp_path / "readiness.json", {"code_hashes": {}, "tests_passed": True, "secret_diff_links_passed": True})
    monkeypatch.setattr(pilot, "verify_bindings", lambda *args: {})
    monkeypatch.setattr(pilot, "code_hashes", lambda: {})
    calls = []
    def run(root, spec, stage, phase, **kwargs):
        calls.append((spec["id"], stage))
        return {"status": "no_natural_task"}
    monkeypatch.setattr(pilot, "run_session", run)
    result = pilot.execute(tmp_path, "validation")
    assert calls == [(f"val_0{i}", "generate") for i in range(1, 5)]
    assert result["status"] == "validation_review_complete" and result["validation_first_pass"] == "0/4"


def test_business_unauthorized_language_is_not_authentication_failure():
    native = json.dumps({"type": "tool_use", "text": "unauthorized transactions, an HTTP 401 example in a record"})
    assert not pilot.authentication_failed(0, {"completed": True, "error_events": 0}, "", native)
    assert not pilot.authentication_failed(1, {"completed": False, "error_events": 0}, "timeout", native)
    error = json.dumps({"type": "error", "error": "HTTP 401 Unauthorized"})
    assert pilot.authentication_failed(1, {"completed": False, "error_events": 1}, "", error)


def test_documented_disagreement_withholds_but_never_promotes(tmp_path):
    pilot.write(tmp_path / "receipt.json", {})
    receipt = {"cases": {f"val_0{i}": {"status": "completed", "quality": "pass" if i == 1 else "issue"} for i in range(1, 5)}}
    admission = {f"val_0{i}": {"status": "uncertain" if i == 1 else "pass", "findings": [{"path": "receipt.json", "locator": f"cases.val_0{i}", "observation": "case evidence reviewed"}]} for i in range(1, 5)}
    result = pilot.apply_admission_review(tmp_path, receipt, admission)
    assert result["val_01"]["quality"] == "uncertain"
    assert all(result[f"val_0{i}"]["quality"] == "issue" for i in (2,3,4))
    assert method.select_trials(result) == []


def test_frozen_prompt_change_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "verify_master", lambda root: {})
    monkeypatch.setattr(pilot, "code_hashes", lambda: {})
    directory = tmp_path / "methods/development"
    pilot.write(directory / "mine.md", {"prompt": "original"})
    hashes = pilot.tree(directory)
    pilot.write(directory / "freeze.json", {"code_hashes": {}, "prompt_hashes": hashes})
    pilot.write(tmp_path / "receipt.json", {"freeze_hashes": {"development": pilot.sha(directory / "freeze.json")}})
    pilot.verify_bindings(tmp_path, "development")
    pilot.write(directory / "mine.md", {"prompt": "changed"})
    with pytest.raises(RuntimeError, match="method_changed"):
        pilot.verify_bindings(tmp_path, "development")


def test_review_cannot_pass_with_unresolved_dimension(tmp_path):
    pilot.write(tmp_path / "inputs/reference_files/a.txt", {})
    pilot.write(tmp_path / "inputs/task.json", {"requirements": [{"id": "r1"}]})
    pilot.write(tmp_path / "inputs/new_rubric.json", {"criteria": [{"criterion_id": "c1"}]})
    review = {"decision": "pass", "checks": [{"dimension": d, "status": "uncertain", "findings": [{"observation": "unclear", "path": "reference_files/a.txt", "locator": "line 1", "limitation": "not proved"}]} for d in method.DIMENSIONS],
              "requirement_coverage": [{"requirement_id": "r1", "status": "pass", "explanation": "checked"}], "rubric_coverage": [{"criterion_id": "c1", "status": "pass", "explanation": "checked"}]}
    pilot.write(tmp_path / "raw/review.json", review)
    with pytest.raises(ValueError, match="decision_mismatch"):
        method.review_result(tmp_path / "raw", tmp_path / "inputs")
