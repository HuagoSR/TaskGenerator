import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_12_stirrup_supplement_b", ROOT / "Test/run_r10_12_stirrup_supplement_b.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_prepare_binds_diagnostic_s1_evidence_and_exact_budget(tmp_path, monkeypatch):
    diagnostic = tmp_path / "diagnostic"
    s1 = tmp_path / "s1"
    diagnostic.mkdir()
    s1.mkdir()
    RUNNER._write(diagnostic / "summary.json", {
        "selected_judge_transport": "gpt-5.6-terra@chatgpt_codex"
    })
    hashes = {task: RUNNER.base._task_hashes(task) for task in RUNNER.base.TASKS}
    RUNNER._write(s1 / "scope.json", {"task_hashes": hashes})
    for relative in ("route_snapshot.json", "protocol_preflight/results.json", "frozen_panel.json"):
        RUNNER._write(s1 / relative, {"fixed": True})
    monkeypatch.setattr(RUNNER, "DIAGNOSTIC", diagnostic)
    monkeypatch.setattr(RUNNER, "S1_ROOT", s1)
    monkeypatch.setattr(RUNNER.base, "_r10_11_expected_hashes", lambda: hashes)
    scope = RUNNER.prepare(tmp_path / "s1b")
    assert scope["requested_panel"] == RUNNER.SUPPLEMENT_MODELS
    assert scope["selected_check_judge"] == "gpt-5.6-terra@chatgpt_codex"
    dry = json.loads((tmp_path / "s1b/dry_run.json").read_text(encoding="utf-8"))
    assert (dry["route_health_calls"], dry["solver_normal_sessions"]) == (4, 12)
    assert (dry["primary_normal"], dry["primary_format_recoveries"]) == (12, 2)
    assert (dry["check_normal"], dry["check_format_recoveries"]) == (4, 1)


def test_route_health_stops_after_first_failure(tmp_path, monkeypatch):
    run_root = tmp_path / "s1b"
    run_root.mkdir()
    RUNNER._write(run_root / "scope.json", {"scope": True})
    monkeypatch.setattr(RUNNER.base, "_solver_environment", lambda: ({
        "AGENT_BASE_URL": "https://example.invalid/v1", "AGENT_API_KEY": "secret"
    }, []))

    def fail(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(RUNNER.urllib.request, "urlopen", fail)
    result = RUNNER.route_health(run_root)
    assert result["all_passed"] is False and len(result["rows"]) == 1
    assert json.loads((run_root / "summary.json").read_text(encoding="utf-8"))["status"] == "incomplete"


def test_delivery_only_partition_does_not_use_scores():
    assert RUNNER._delivery_only("Deliver an openable .xlsx file")
    assert not RUNNER._delivery_only("Document the analysis and conclusion in the .xlsx file")


def test_solver_metadata_hashes_only_sanitized_progress(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    rows = [
        {"event": "provider_response_metadata", "request_number": 1, "requested_model": "m"},
        {"event": "model_request_completed", "request_number": 1, "tool_calls": ["code_exec"]},
        {"event": "session_run_started", "secret": "must-not-enter-receipt-hash-input"},
    ]
    (output / "progress.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    digest, count, tools = RUNNER._solver_metadata(output)
    assert digest and count == 1 and tools == ["code_exec"]


def test_recovery_only_accepts_recorded_coverage_failure(tmp_path):
    run_root = tmp_path / "s1b"
    run_root.mkdir()
    RUNNER._write(run_root / "scope.json", {"scope": True})
    RUNNER._write(run_root / "summary.json", {"stop_reason": "some_other_failure"})
    try:
        RUNNER.recover_grade(run_root)
    except RuntimeError as exc:
        assert "not_authorized" in str(exc)
    else:
        raise AssertionError("unregistered failure must not resume")


def test_closeout_writes_incomplete_receipt_once(tmp_path):
    run_root = tmp_path / "s1b"
    run_root.mkdir()
    RUNNER._write(run_root / "scope.json", {"scope": True})
    RUNNER._write(run_root / "summary.json", {
        "status": "incomplete", "evidence_level": "grading", "stop_reason": "format_budget"
    })
    RUNNER.closeout(run_root)
    receipt = json.loads((run_root / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "incomplete" and receipt["primary_provider_attempts"] == 0
