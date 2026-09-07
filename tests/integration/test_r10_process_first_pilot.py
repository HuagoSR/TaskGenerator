import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Test"))
import run_r10_process_first_pilot as pilot
import r10_process_first_tools as remote


def test_budget_uses_remaining_time(monkeypatch):
    monkeypatch.setattr(pilot.time, "monotonic", lambda: 100)
    assert pilot.remaining(10000) == 1800
    assert pilot.remaining(121) == 21
    with pytest.raises(TimeoutError):
        pilot.remaining(100)


def test_anonymous_materials_exclude_factory_records(tmp_path):
    public = tmp_path / "public"
    pilot.write(public / "public_context.json", {"role": "buyer"})
    for name in ("professional_rules.json", "sources.json", "work_seed.json"):
        pilot.write(public / name, {})
    generated = tmp_path / "results/generate_A"
    pilot.write(generated / "candidate/record.json", {"public": 1})
    pilot.write(generated / "hidden/world.json", {"hidden": "DO_NOT_LEAK"})
    pilot.write(tmp_path / "results/mine_A/task.json", {"natural_task": True})
    pilot.write(tmp_path / "results/mine_A/deliverable_contract.json", {})
    (tmp_path / "results/mine_A/candidate_task.md").write_text("task")
    for stage in ("mine", "review"):
        target = tmp_path / stage
        pilot.stage_inputs(tmp_path, stage, "A", target)
        assert "DO_NOT_LEAK" not in "".join(p.read_text() for p in target.rglob("*") if p.is_file())
        assert not (target / "hidden").exists()
        assert not (target / "work_seed.json").exists()
    assert pilot.prompt("mine", "A") == pilot.prompt("mine", "B")
    assert pilot.prompt("review", "A") == pilot.prompt("review", "B")


def test_existing_directory_and_terminal_scope_never_overwritten(tmp_path):
    pilot.write(tmp_path / "receipt.json", {"status": "incomplete", "sessions": [], "first_failure": "original"})
    before = pilot.tree(tmp_path)
    with pytest.raises(FileExistsError):
        pilot.prepare(tmp_path)
    with pytest.raises(ValueError, match="no_resume"):
        pilot.execute(tmp_path)
    assert before == pilot.tree(tmp_path)


def test_binding_failure_retained_without_network(tmp_path, monkeypatch):
    pilot.write(tmp_path / "receipt.json", {"status": "ready", "sessions": [], "first_failure": None})
    def bad_binding(root):
        raise ValueError("input_changed")
    monkeypatch.setattr(pilot, "check_bindings", bad_binding)
    monkeypatch.setattr(pilot, "_ssh", lambda *a, **k: pytest.fail("unexpected network"))
    result = pilot.execute(tmp_path)
    assert result["status"] == "incomplete"
    assert result["first_failure"] == "input_changed"
    with pytest.raises(ValueError):
        pilot.execute(tmp_path)
    assert pilot.read(tmp_path / "receipt.json")["first_failure"] == "input_changed"


def test_process_freeze_requires_no_materials_and_is_write_once(tmp_path):
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "process.md").write_text("events and purposes")
    remote.freeze(tmp_path)
    with pytest.raises(FileExistsError):
        remote.freeze(tmp_path)
    pilot.write(tmp_path / "candidate/first.json", {})
    with pytest.raises(ValueError, match="precedes"):
        remote.freeze(tmp_path)


@pytest.mark.parametrize("relative", ["../hidden/secret.md", "/tmp/x", "C:/secret", "x\\y", "missing.md"])
def test_evidence_paths_cannot_escape(tmp_path, relative):
    with pytest.raises(ValueError):
        pilot.check_reference(tmp_path, relative)


def test_no_solver_judge_and_offline_environment():
    assert pilot.STAGES == [(s, a) for s in ("generate", "mine", "review") for a in ("A", "B")]
    for stage in ("generate", "mine", "review"):
        script = pilot.agent_script(stage)
        assert "grade_schema" not in script and "docx_office_check" not in script
        assert "/deps/site" in script
        assert "agent.jsonl" not in script
    assert "--network" in pilot.docker_base("unused")
    source = Path(pilot.__file__).read_text(encoding="utf-8")
    assert 'f"{stage_remote}/workspace:/workspace:ro"' in source
    assert "_execute_solver(" not in source and "_execute_judge(" not in source


def test_false_natural_task_is_valid_and_no_contract_created(tmp_path):
    pilot.write(tmp_path / "task.json", {"natural_task": False, "rationale": "No visible trigger"})
    pilot.validate_result("mine", tmp_path)
    assert not (tmp_path / "deliverable_contract.json").exists()


def test_usage_does_not_fabricate_request_count(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 42}}) + "\n")
    result = pilot.usage(path)
    assert result["completed"] and result["model_request_count"] is None
    assert result["reported_usage_events"][0]["usage"]["input_tokens"] == 42


def test_process_file_alone_does_not_prove_order(tmp_path):
    (tmp_path / "hidden").mkdir()
    (tmp_path / "hidden/process.md").write_text("process")
    remote.freeze(tmp_path)
    log = tmp_path / "events.jsonl"
    log.write_text("")
    assert pilot.process_protocol(tmp_path, log) == "unverified"


def test_review_accepts_task_and_rule_evidence_from_its_frozen_inputs(tmp_path):
    pilot.write(tmp_path / "candidate/material.json", {})
    for name in ("candidate_task.md", "task.json", "deliverable_contract.json", "professional_rules.json", "sources.json", "public_context.json"):
        pilot.write(tmp_path / name, {})
        pilot.check_review_reference(tmp_path, "../" + name)
    pilot.check_review_reference(tmp_path, "material.json")


@pytest.mark.parametrize("relative", ["../../TASK.md", "../hidden/world.md", "../unlisted.json", "/tmp/secret", "C:/secret", "../missing.json"])
def test_review_still_rejects_non_input_evidence(tmp_path, relative):
    pilot.write(tmp_path / "candidate/material.json", {})
    pilot.write(tmp_path / "unlisted.json", {})
    pilot.write(tmp_path.parent / "TASK.md", {})
    with pytest.raises(ValueError):
        pilot.check_review_reference(tmp_path, relative)


def test_continuation_only_executes_missing_review():
    assert pilot.execution_order({'continuation': 'frozen_review_B', 'order': [['review', 'B']], 'max_sessions': 1}) == [('review', 'B')]
    with pytest.raises(ValueError):
        pilot.execution_order({'continuation': 'frozen_review_B', 'order': pilot.STAGES, 'max_sessions': 6})
    with pytest.raises(ValueError):
        pilot.execution_order({'order': [['review', 'B']], 'max_sessions': 1})


def test_review_context_basename_is_exact_and_unambiguous(tmp_path):
    pilot.write(tmp_path / 'candidate/material.json', {})
    pilot.write(tmp_path / 'candidate_task.md', {})
    pilot.check_review_reference(tmp_path, 'candidate_task.md')
    pilot.write(tmp_path / 'candidate/candidate_task.md', {})
    with pytest.raises(ValueError, match='ambiguous'):
        pilot.check_review_reference(tmp_path, 'candidate_task.md')
    pilot.check_review_reference(tmp_path, '../candidate_task.md')
    with pytest.raises(ValueError):
        pilot.check_review_reference(tmp_path, 'candidate_task.m')
