from __future__ import annotations

import json
from pathlib import Path

import pytest

from task_generator.cli.main import main


def invoke(args: list[str], capsys):
    try:
        main(args)
    except SystemExit as raised:
        return raised.code, capsys.readouterr()
    return 0, capsys.readouterr()


def candidate_pack(root: Path) -> Path:
    (root / "reference_files").mkdir(parents=True)
    (root / "deliverable_files").mkdir()
    (root / "reference_files" / "evidence.txt").write_text("evidence", encoding="utf-8")
    (root / "dataset_row.json").write_text(json.dumps({"task_id": "synthetic-task", "sector": "synthetic", "occupation": "tester", "rubric": [{"criterion": "x"}]}), encoding="utf-8")
    return root


def test_doctor_is_offline_and_json(capsys, monkeypatch):
    import socket

    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network")))
    code, captured = invoke(["doctor", "--json"], capsys)
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["capabilities"]["network"] == "not_used"


def test_candidate_inspect_and_report_are_read_only(tmp_path, capsys):
    pack = candidate_pack(tmp_path / "中文 空格")
    before = {item.relative_to(pack).as_posix(): item.read_bytes() for item in pack.rglob("*") if item.is_file()}
    code, captured = invoke(["inspect", str(pack), "--json"], capsys)
    assert code == 0
    assert json.loads(captured.out)["kind"] == "candidate_pack"
    code, captured = invoke(["report", str(pack), "--format", "markdown"], capsys)
    assert code == 0
    assert "candidate_pack" in captured.out
    after = {item.relative_to(pack).as_posix(): item.read_bytes() for item in pack.rglob("*") if item.is_file()}
    assert after == before


def test_report_refuses_overwrite_and_writes_only_explicit_new_target(tmp_path, capsys):
    pack = candidate_pack(tmp_path / "package")
    output = tmp_path / "report.md"
    code, _ = invoke(["report", str(pack), "--output", str(output)], capsys)
    assert code == 0 and output.is_file()
    code, captured = invoke(["report", str(pack), "--output", str(output)], capsys)
    assert code == 2
    assert "new regular file" in captured.err


def test_legacy_projection_never_becomes_formal_score(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"scope_id": "synthetic", "legacy": True, "status": "completed", "total_score": 18, "grades": [{"score": 15, "max_score": 18, "rubric_item_id": "criterion_1"}]}), encoding="utf-8")
    code, captured = invoke(["inspect", str(report), "--json"], capsys)
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["status"]["legacy_scoring"] == "produced"
    assert payload["status"]["formal_atomic_score"] == "not_produced"
    assert payload["metrics"]["legacy_score_consistency"] == "conflict"


def test_preview_does_not_create_scope_or_output(tmp_path, capsys):
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"version": 1, "protocol": "r10-task-factory", "input": {"path": "source.json"}, "models": ["synthetic"], "budget": {"max_launches": 1, "wall_clock_seconds": 60}, "order": ["prepare"], "output": {"path": "new-output"}}), encoding="utf-8")
    code, captured = invoke(["generate", "--spec", str(spec), "--dry-run", "--json"], capsys)
    assert code == 0
    assert json.loads(captured.out)["execution"] == "preview_only_no_scope_receipt_or_budget_created"
    assert not (tmp_path / "new-output").exists()


def test_config_and_spec_reject_unknown_or_parent_paths(tmp_path, capsys):
    config = tmp_path / "local.json"
    config.write_text(json.dumps({"version": 1, "token": "no"}), encoding="utf-8")
    code, captured = invoke(["doctor", "--config", str(config)], capsys)
    assert code == 2 and "unknown fields" in captured.err
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"version": 1, "protocol": "rw-legacy-diagnostic", "input": {"path": "../outside.json"}, "models": ["synthetic"], "budget": {"max_launches": 0, "wall_clock_seconds": 0}, "order": [], "output": {"path": "output"}}), encoding="utf-8")
    code, captured = invoke(["evaluate", "--spec", str(spec), "--dry-run"], capsys)
    assert code == 2 and "parent traversal" in captured.err


def test_runs_exposes_scope_status_without_modifying_it(tmp_path, capsys):
    scope = tmp_path / "scope"
    scope.mkdir()
    (scope / "scope.json").write_text(json.dumps({"scope_id": "scope-1", "protocol": "synthetic"}), encoding="utf-8")
    (scope / "receipt.json").write_text(json.dumps({"status": "completed", "acceptance_status": "accepted", "researcher_admission": "uncertain"}), encoding="utf-8")
    before = (scope / "receipt.json").read_bytes()
    code, captured = invoke(["runs", "--root", str(tmp_path), "--json"], capsys)
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["runs"][0]["status"]["researcher_admission"] == "uncertain"
    assert (scope / "receipt.json").read_bytes() == before


def test_tracked_public_examples_are_parseable(capsys):
    root = Path(__file__).resolve().parents[2]
    code, _ = invoke(["doctor", "--config", str(root / "data" / "cli" / "local.example.json")], capsys)
    assert code == 0
    code, _ = invoke(["generate", "--spec", str(root / "data" / "cli" / "generate.example.json"), "--dry-run"], capsys)
    assert code == 0
    code, _ = invoke(["evaluate", "--spec", str(root / "data" / "cli" / "evaluate.legacy.example.json"), "--dry-run"], capsys)
    assert code == 0
