import importlib.util
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_12_stirrup_calibration", ROOT / "Test/run_r10_12_stirrup_calibration.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_provider_free_prepare_binds_nine_runs_and_prior_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(RUNNER, "_run_solver_attempt", lambda *_: (_ for _ in ()).throw(AssertionError("provider")))
    monkeypatch.setattr(RUNNER, "_remote_grade_call", lambda *_: (_ for _ in ()).throw(AssertionError("provider")))
    scope = RUNNER.prepare(tmp_path / "campaign")
    assert scope["campaign_id"] == "campaign"
    assert len(scope["solver_assignments"]) == 9
    assert scope["solver"]["max_turns"] == 100
    assert scope["solver"]["max_completion_tokens"] == 8192
    assert scope["solver"]["context_window_tokens"] == 64000
    assert scope["solver"]["attempt_timeout_seconds"] == 7200
    assert scope["preflight"]["attempt_timeout_seconds"] == 600
    assert scope["solver"]["campaign_technical_recovery_limit"] == 3
    assert scope["grading"]["primary"]["normal_call_limit"] == 9
    assert scope["grading"]["checks"]["normal_call_limit"] == 3
    assert scope["grading"]["shadow"]["changes_primary_score"] is False
    assert set(scope["task_hashes"]) == set(RUNNER.TASKS)
    assert all(set(value) == {"input_sha256", "rubric_sha256"} for value in scope["task_hashes"].values())
    serialized = json.dumps(scope).casefold()
    assert '"api_key"' not in serialized and '"token"' not in serialized


def test_campaign_identity_is_derived_from_new_run_root(tmp_path):
    scope = RUNNER.prepare(tmp_path / "r10_12_stirrup_retry_20260904")
    assert scope["campaign_id"] == "r10_12_stirrup_retry_20260904"


def test_provider_free_gpt54mini_diagnostic_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(RUNNER, "_run_solver_attempt", lambda *_: (_ for _ in ()).throw(AssertionError("provider")))
    scope = RUNNER.prepare_diagnostic(tmp_path / "gpt54mini_probe")
    assert scope["model_id"] == "gpt-5.4-mini"
    assert scope["normal_call_limit"] == 1
    assert scope["technical_recovery_limit"] == 0
    assert scope["attempt_timeout_seconds"] == 10800
    assert scope["context_window_tokens"] == 64000
    assert scope["grading_authorized"] is False


def test_solve_is_serial_and_produces_complete_receipts(tmp_path, monkeypatch):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    panel = RUNNER.FrozenStirrupPanelV1(
        strong="gpt-5.6-sol", middle="deepseek-v4-flash", weak="gpt-4o-mini",
        preflight_sha256="a" * 64,
    )
    RUNNER._write(run_root / "frozen_panel.json", panel)
    calls = []

    def fake_solver(case, output, model, max_turns, timeout_seconds):
        calls.append((json.loads((case / "dataset_row.json").read_text(encoding="utf-8"))["task_id"], model, max_turns))
        assert timeout_seconds == 7200
        output.mkdir(parents=True)
        delivery = output / "deliverable_files" / "hash"
        delivery.mkdir(parents=True)
        task_id = json.loads((case / "dataset_row.json").read_text(encoding="utf-8"))["task_id"]
        name = RUNNER._binding(task_id).expected_deliverables[0]
        with zipfile.ZipFile(delivery / name, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        RUNNER._write(output / "phase.json", {"semantic_phase_started": True})
        return 0, True

    monkeypatch.setattr(RUNNER, "_run_solver_attempt", fake_solver)
    receipts = RUNNER.solve(run_root)
    assert len(calls) == len(receipts) == 9
    assert all(call[2] == 100 for call in calls)
    assert all(row.delivery_status == "complete" and len(row.attempts) == 1 for row in receipts)
    retry_scope = RUNNER.prepare_grading_retry(run_root)
    assert retry_scope["valid_submission_count"] == 9
    assert retry_scope["max_output_tokens"] == 16384
    assert retry_scope["solver_rerun"] is False


def test_invalid_delivery_is_not_semantically_graded_in_summary():
    specs = [
        {"task_id": task, "tier": tier, "solver_id": f"{tier}-model", "assignment_id": f"{task}-{tier}"}
        for task in RUNNER.TASKS for tier in RUNNER.TIERS
    ]
    receipts = [
        {"task_id": row["task_id"], "tier": row["tier"],
         "delivery_status": "invalid" if row["tier"] == "weak" else "complete"}
        for row in specs
    ]
    summary = RUNNER.summarize(receipts, [], [], [], specs)
    assert summary["status"] == "incomplete"
    assert summary["all_deliveries_valid"] is False


def test_gdpval_delivery_accepts_equivalent_submitted_basename(tmp_path):
    task_id = RUNNER.TASKS[0]
    delivery = tmp_path / "deliverable_files/hash"
    delivery.mkdir(parents=True)
    with zipfile.ZipFile(delivery / "solver_chosen_name.xlsx", "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    assert RUNNER._validate_delivery(task_id, tmp_path / "deliverable_files") == "complete"


def test_preflight_controller_failure_closes_without_model_claim(tmp_path):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    session = run_root / "preflight/strong_primary_gpt-5.4-mini"
    for attempt in (1, 2):
        output = session / f"attempt_{attempt}/output"
        output.mkdir(parents=True)
        RUNNER._write(output / "phase.json", {"semantic_phase_started": False})
        (output.parent / "stderr.txt").write_text("UnicodeEncodeError: local console", encoding="utf-8")
    result = RUNNER.StirrupPreflightResultV1(
        tier="strong", model_id="gpt-5.4-mini", candidate_role="primary",
        status="technical_failure", attempt_count=2, evidence_path="preflight/strong_primary_gpt-5.4-mini",
    )
    RUNNER._write(session / "result.json", result)
    summary = RUNNER.close_preflight_failure(run_root)
    assert summary["status"] == "incomplete"
    assert summary["model_availability_conclusion"] == "not_tested"
    receipt = json.loads((run_root / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["provider_calls"] == 0
    assert receipt["formal_solver_calls"] == 0


def test_formal_solver_timeout_closeout_preserves_started_session(tmp_path):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    attempt = run_root / "solver_sessions/assignment/attempts/attempt_1"
    output = attempt / "output"
    output.mkdir(parents=True)
    RUNNER._write(output / "phase.json", {"semantic_phase_started": True})
    RUNNER._write(attempt / "timeout.json", {"timeout_seconds": 2400})
    summary = RUNNER.close_solver_failure(run_root)
    assert summary["status"] == "incomplete"
    assert summary["stop_reason"] == "formal_solver_attempt_timeout_after_semantic_start"


def test_formal_solver_closeout_does_not_invent_timeout(tmp_path):
    run_root = tmp_path / "campaign"
    RUNNER.prepare(run_root)
    output = run_root / "solver_sessions/assignment/attempts/attempt_1/output"
    output.mkdir(parents=True)
    RUNNER._write(output / "phase.json", {"semantic_phase_started": True})
    summary = RUNNER.close_solver_failure(run_root)
    assert summary["stop_reason"] == "formal_solver_controller_failure"
