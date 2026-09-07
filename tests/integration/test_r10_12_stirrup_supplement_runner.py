import importlib.util
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_12_stirrup_supplement", ROOT / "Test/run_r10_12_stirrup_supplement.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_provider_free_prepare_binds_exact_four_route_matrix(tmp_path, monkeypatch):
    monkeypatch.setattr(RUNNER.base, "_run_solver_attempt", lambda *_: (_ for _ in ()).throw(AssertionError("provider")))
    monkeypatch.setattr(RUNNER.base, "_remote_grade_call", lambda *_: (_ for _ in ()).throw(AssertionError("provider")))
    scope = RUNNER.prepare(tmp_path / "r10_12_model_supplement_test")
    assert scope["requested_panel"] == RUNNER.SUPPLEMENT_MODELS
    assert scope["endpoint"] == "/v1/chat/completions"
    assert len(scope["solver_assignments"]) == 12
    assert scope["preflight"]["normal_sessions"] == 4
    assert scope["solver"]["max_turns"] == 100
    assert scope["solver"]["context_window_tokens"] == 64000
    assert scope["solver"]["max_completion_tokens"] == 8192
    assert scope["grading"]["primary"]["normal_call_limit"] == 12
    assert scope["grading"]["checks"]["normal_call_limit"] == 4
    assert scope["grading"]["downward_audit"] is False
    dry_run = json.loads((tmp_path / "r10_12_model_supplement_test/dry_run.json").read_text(encoding="utf-8"))
    assert dry_run["call_limits"] == {
        "preflight_sessions": 4,
        "solver_sessions": 12,
        "preflight_technical_recoveries": 4,
        "solver_technical_recoveries": 4,
        "judge_probe_normal": 1,
        "judge_probe_format_recoveries": 1,
        "primary_grades": 12,
        "primary_format_recoveries": 2,
        "check_grades": 4,
        "check_format_recoveries": 1,
    }
    serialized = json.dumps(scope).casefold()
    assert '"api_key"' not in serialized and '"token"' not in serialized


def test_protocol_preflight_requires_metadata_two_turns_tools_and_delivery(tmp_path, monkeypatch):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    RUNNER._write(run_root / "route_snapshot.json", {"all_selected_visible": True, "all_chat_declared": True})

    def fake_attempt(case, output, model, max_turns, timeout_seconds):
        output.mkdir(parents=True)
        delivery = output / "deliverable_files/hash"
        delivery.mkdir(parents=True)
        (delivery / "preflight.txt").write_text("R10.12-S1-STIRRUP-OK\n", encoding="utf-8")
        events = [
            {"event": "provider_response_metadata", "request_number": 1, "endpoint": "/v1/chat/completions",
             "requested_model": model, "response_model": model, "response_object": "chat.completion",
             "request_id": "request", "usage": {}, "at": "now"},
            {"event": "model_request_completed", "request_number": 1, "tool_calls": ["code_exec"]},
            {"event": "provider_response_metadata", "request_number": 2, "endpoint": "/v1/chat/completions",
             "requested_model": model, "response_model": model, "response_object": "chat.completion",
             "request_id": "request", "usage": {}, "at": "now"},
            {"event": "model_request_completed", "request_number": 2, "tool_calls": ["finish"]},
        ]
        (output / "progress.jsonl").write_text("\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
        RUNNER._write(output / "phase.json", {"semantic_phase_started": True})
        return 0, True

    monkeypatch.setattr(RUNNER.base, "_run_solver_attempt", fake_attempt)
    probes = RUNNER.protocol_preflight(run_root)
    assert len(probes) == 4 and all(row.status == "passed" for row in probes)
    assert (run_root / "frozen_panel.json").is_file()


def test_protocol_failure_freezes_before_formal_solver(tmp_path, monkeypatch):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    RUNNER._write(run_root / "route_snapshot.json", {"all_selected_visible": True, "all_chat_declared": True})

    def failing_attempt(case, output, model, max_turns, timeout_seconds):
        output.mkdir(parents=True)
        RUNNER._write(output / "phase.json", {"semantic_phase_started": True})
        (output / "progress.jsonl").write_text(
            json.dumps({"event": "model_request_completed", "request_number": 1, "tool_calls": ["code_exec"]}) + "\n",
            encoding="utf-8",
        )
        return 1, True

    monkeypatch.setattr(RUNNER.base, "_run_solver_attempt", failing_attempt)
    probes = RUNNER.protocol_preflight(run_root)
    assert all(row.status == "protocol_or_semantic_failure" for row in probes)
    assert json.loads((run_root / "summary.json").read_text(encoding="utf-8"))["status"] == "incomplete"
    assert not (run_root / "solver_sessions").exists()


def test_judge_probe_failure_classifies_downloaded_http_401():
    assert RUNNER._judge_probe_failure_type("HTTP Error 401: Unauthorized") == "http_401_unauthorized"
    assert RUNNER._judge_probe_failure_type("connection reset") == "provider_or_transport_failure"


def test_solve_runs_twelve_serial_first_results_and_rejects_fake_office(tmp_path, monkeypatch):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    RUNNER._write(run_root / "frozen_panel.json", RUNNER.FrozenStirrupSupplementPanelV1(
        models=RUNNER.SUPPLEMENT_MODELS, probe_sha256="a" * 64,
    ))
    RUNNER._write(run_root / "judge_probe/result.json", {"status": "passed"})
    calls = []

    def fake_attempt(case, output, model, max_turns, timeout_seconds):
        calls.append(model)
        output.mkdir(parents=True)
        task_id = json.loads((case / "dataset_row.json").read_text(encoding="utf-8"))["task_id"]
        delivery = output / "deliverable_files/hash"
        delivery.mkdir(parents=True)
        suffix = Path(RUNNER.base._binding(task_id).expected_deliverables[0]).suffix
        path = delivery / f"submitted{suffix}"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        RUNNER._write(output / "phase.json", {"semantic_phase_started": True})
        return 0, True

    monkeypatch.setattr(RUNNER.base, "_run_solver_attempt", fake_attempt)
    receipts = RUNNER.solve(run_root)
    assert len(calls) == len(receipts) == 12
    assert all(row.delivery_status == "complete" and len(row.attempts) == 1 for row in receipts)
