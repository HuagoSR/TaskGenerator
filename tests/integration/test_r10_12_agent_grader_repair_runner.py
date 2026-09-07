import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_12_agent_grader_repair", ROOT / "Test/run_r10_12_agent_grader_repair.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_prepare_freezes_six_agent_sessions_and_no_solver(tmp_path):
    scope = RUNNER.prepare(tmp_path / "g2")
    dry = json.loads((tmp_path / "g2/dry_run.json").read_text(encoding="utf-8"))
    assert scope["normal_agent_sessions"] == 6
    assert scope["solver_calls"] == 0
    assert dry["provider_calls"] == 0
    assert len(dry["assignments"]) == 6
    assert {row["judge"] for row in dry["assignments"]} == {
        "gpt-5.6-terra@chatgpt_codex", "deepseek-v4-pro@official_opencode"
    }


def test_format_recovery_cannot_change_semantic_fields():
    original = {
        "material_status": "complete", "material_notes": "Readable.",
        "assessments": [{
            "rubric_item_id": "one", "awarded": 1, "satisfaction": "met",
            "coverage": "presence", "verification_methods": ["file_presence"],
            "evidence_refs": [{"relative_path": "candidate_task.md", "evidence_role": "support"}],
            "support": ["Present."], "defects": [], "rationale": "Direct evidence is present.",
        }],
    }
    recovered = RUNNER.AgentRubricGradeDraftV2.model_validate({
        **original, "assessments": [{**original["assessments"][0], "awarded": 0}]
    })
    try:
        RUNNER._validate_recovery_preserves_semantics(json.dumps(original), recovered)
    except ValueError as exc:
        assert "changed_semantics" in str(exc)
    else:
        raise AssertionError("semantic mutation was accepted")


@pytest.mark.parametrize("entry", ["direct", "cli"])
def test_paused_execution_stops_before_any_side_effect(tmp_path, monkeypatch, entry):
    def forbidden(*args, **kwargs):
        raise AssertionError("side effect reached")
    for name in ("prepare", "_write", "_build_evidence", "_run_judge", "_ssh", "_scp", "_run_remote"):
        monkeypatch.setattr(RUNNER, name, forbidden)
    target = tmp_path / "must_not_exist"
    if entry == "direct":
        with pytest.raises(RuntimeError, match="评分校准已暂停"):
            RUNNER.execute(target)
    else:
        monkeypatch.setattr(sys, "argv", ["runner", "--execute", "--run-root", str(target)])
        with pytest.raises(SystemExit) as error:
            RUNNER.main()
        assert error.value.code == 2
    assert not target.exists()


def test_existing_dry_run_is_read_only(tmp_path, monkeypatch, capsys):
    target = tmp_path / "prepared"
    RUNNER.prepare(target)
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    def forbidden(*args, **kwargs):
        raise AssertionError("write or execution reached")
    for name in ("prepare", "execute", "_write", "_ssh", "_scp", "_run_remote"):
        monkeypatch.setattr(RUNNER, name, forbidden)
    monkeypatch.setattr(sys, "argv", ["runner", "--run-root", str(target)])
    RUNNER.main()
    assert json.loads(capsys.readouterr().out)["provider_calls"] == 0
    assert before == {p.name: p.read_bytes() for p in target.iterdir()}


def test_read_only_cli_does_not_prepare_missing_directory(tmp_path, monkeypatch):
    target = tmp_path / "missing"
    monkeypatch.setattr(sys, "argv", ["runner", "--run-root", str(target)])
    with pytest.raises(RuntimeError, match="not_prepared"):
        RUNNER.main()
    assert not target.exists()
