from __future__ import annotations

import json
import io
from pathlib import Path

import pytest

from task_generator.cli.main import main
from task_generator.cli.main import _write_text


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


def legacy_report(root: Path, *, state: str = "completed") -> Path:
    cells = []
    for model in ("terra", "flash", "mini"):
        for task_id, score, maximum in (("procurement", 15, 18), ("audit", 25, 25)):
            cells.append({"cell_id": f"{model}-{task_id}", "model": model, "task_id": task_id, "state": "completed", "legacy_score": score, "legacy_max": maximum, "audit_applied": model == "terra", "delivery_validity": "valid", "grading_report_sha256": f"{model}-{task_id}-hash", "legacy_grade_summary": {"total_score": score, "max_possible_score": maximum, "audit_applied": model == "terra", "audit_reduced_points": 1 if model == "terra" else 0, "audit_reduced_rows": ["criterion_1"] if model == "terra" else []}})
    report = {"label": "legacy rw-task diagnostic", "formal_atomic_rubric_score": "not_produced", "state": state, "stop_reason": None, "controller_recovery": [{"action": "accepted_existing_solver_output"}], "cells": cells, "limits": {"max_cells": 6}, "prepared_input_hashes": {"prepared_scope_sha256": "synthetic"}, "unknowns": ["billing unavailable"]}
    path = root / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


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
    assert code == 3
    assert "new regular file" in captured.err


def test_legacy_projection_preserves_six_cells_without_cross_cell_scoring(tmp_path, capsys):
    report = legacy_report(tmp_path)
    (tmp_path / "receipt.json").write_text(json.dumps({"scope_id": "synthetic", "state": "completed", "recovery": [{"ignored": "report recovery remains authoritative"}]}), encoding="utf-8")
    code, captured = invoke(["inspect", str(report), "--json"], capsys)
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["status"]["legacy_scoring"] == "produced"
    assert payload["status"]["formal_atomic_score"] == "not_produced"
    assert payload["metrics"]["cell_count"] == 6
    assert payload["metrics"]["legacy_score_count"] == 6
    assert payload["status"]["itemized_verification"] == "not_completed"
    assert payload["cells"][0]["model"] == "terra"
    assert payload["cells"][0]["audit_summary"]["audit_reduced_points"] == 1
    assert payload["recovery"] == [{"action": "accepted_existing_solver_output"}]


def test_legacy_directory_and_report_have_same_core_projection(tmp_path, capsys):
    report = legacy_report(tmp_path)
    code, captured = invoke(["inspect", str(report), "--json"], capsys)
    assert code == 0
    direct = json.loads(captured.out)
    code, captured = invoke(["inspect", str(tmp_path), "--json"], capsys)
    assert code == 0
    directory = json.loads(captured.out)
    assert direct["kind"] == directory["kind"] == "legacy_rw_task_diagnostic"
    assert direct["cells"] == directory["cells"]


def test_legacy_markdown_is_a_human_table(tmp_path, capsys):
    report = legacy_report(tmp_path)
    code, captured = invoke(["report", str(report), "--format", "markdown"], capsys)
    assert code == 0
    assert "## 模型 × 任务" in captured.out
    assert "| terra | procurement |" in captured.out


def test_preview_does_not_create_scope_or_output(tmp_path, capsys):
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"version": 1, "protocol": "r10-task-factory", "input": {"path": "source.json"}, "models": ["synthetic"], "budget": {"max_launches": 1, "wall_clock_seconds": 60}, "order": ["prepare"], "output": {"path": "new-output"}}), encoding="utf-8")
    code, captured = invoke(["generate", "--spec", str(spec), "--dry-run", "--json"], capsys)
    assert code == 0
    assert json.loads(captured.out)["execution"] == "preview_only_no_scope_receipt_or_budget_created"
    assert not (tmp_path / "new-output").exists()


def test_preview_rejects_local_missing_input_hash_or_protocol_mismatch(tmp_path, capsys):
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    base = {"version": 1, "protocol": "r10-task-factory", "input": {"path": "missing.json"}, "models": ["synthetic"], "budget": {"max_launches": 1, "wall_clock_seconds": 60}, "order": ["prepare"], "output": {"path": "new-output"}}
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(base), encoding="utf-8")
    code, captured = invoke(["generate", "--spec", str(spec), "--dry-run"], capsys)
    assert code == 3 and "readable regular file" in captured.err
    base["input"] = {"path": "source.json", "sha256": "not-the-hash"}
    spec.write_text(json.dumps(base), encoding="utf-8")
    code, captured = invoke(["generate", "--spec", str(spec), "--dry-run"], capsys)
    assert code == 3 and "does not match" in captured.err
    base["protocol"] = "rw-legacy-diagnostic"
    spec.write_text(json.dumps(base), encoding="utf-8")
    code, captured = invoke(["generate", "--spec", str(spec), "--dry-run"], capsys)
    assert code == 2 and "protocol must be" in captured.err


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


def test_runs_uses_configured_roots_and_report_output_stays_inside_root(tmp_path, capsys):
    root = tmp_path / "中文 空格"
    root.mkdir()
    legacy_report(root)
    out_root = tmp_path / "reports"
    out_root.mkdir()
    config = tmp_path / "local.json"
    config.write_text(json.dumps({"version": 1, "artifact_roots": ["中文 空格"], "report_output_root": "reports"}), encoding="utf-8")
    code, captured = invoke(["runs", "--config", str(config), "--json"], capsys)
    assert code == 0 and len(json.loads(captured.out)["runs"]) == 1
    code, _ = invoke(["report", str(root / "report.json"), "--config", str(config), "--output", str(out_root / "safe.md")], capsys)
    assert code == 0
    code, captured = invoke(["report", str(root / "report.json"), "--config", str(config), "--output", str(tmp_path / "outside.md")], capsys)
    assert code == 2 and "report_output_root" in captured.err


def test_runs_requires_root_when_no_config_exists(capsys):
    code, captured = invoke(["runs"], capsys)
    assert code == 2 and "requires --root" in captured.err


def test_output_falls_back_to_json_safe_escapes_for_gbk_stream():
    class GbkStream(io.StringIO):
        encoding = "gbk"

        def write(self, text):
            text.encode("gbk")
            return super().write(text)

    stream = GbkStream()
    _write_text(stream, '{"message":"Unicode − 字符"}')
    payload = json.loads(stream.getvalue())
    assert payload["message"] == "Unicode − 字符"


def test_tracked_public_examples_are_parseable(capsys):
    root = Path(__file__).resolve().parents[2]
    code, _ = invoke(["doctor", "--config", str(root / "data" / "cli" / "local.example.json")], capsys)
    assert code == 0
    code, _ = invoke(["generate", "--spec", str(root / "data" / "cli" / "generate.example.json"), "--dry-run"], capsys)
    assert code == 0
    code, _ = invoke(["evaluate", "--spec", str(root / "data" / "cli" / "evaluate.legacy.example.json"), "--dry-run"], capsys)
    assert code == 0
