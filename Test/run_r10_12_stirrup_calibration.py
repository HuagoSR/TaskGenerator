"""Run the fixed R10.12 uniform-Stirrup GDPval calibration campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

from run_r10_behavioral_pilot import _scp, _ssh
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.independent_rubric_grader import (
    IndependentRubricGradeDraftV1,
    IndependentRubricGradeV1,
    adapt_gdpval_rubric,
    canonical_json_sha256,
    finalize_independent_grade,
    tree_sha256,
)
from task_generator.evaluation.r10_gdpval_validation import GDPvalTaskBindingV1
from task_generator.evaluation.stirrup_calibration import (
    FALLBACK_MODELS,
    PRIMARY_MODELS,
    FrozenStirrupPanelV1,
    StirrupPreflightResultV1,
    StirrupSolverAttemptV1,
    StirrupSolverReceiptV1,
    build_shadow_downward_diagnostic,
    freeze_model_panel,
    strict_grading_system_prompt,
)
from task_generator.production.campaign import atomic_json


RUN_ID = "r10_12_stirrup_calibration_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
GDPVAL_DATA = ROOT / "artifacts/r10/r10_10_gdpval_public_20260903"
R10_11_SCOPE = ROOT / "artifacts/r10/r10_11_independent_grader_20260904/scope.json"
RW_TASK_ROOT = ROOT.parent / "rw-task"
SOLVER_PYTHON = Path(r"D:\miniconda3\envs\real-world-task\python.exe")
TUZI_ENV = RW_TASK_ROOT / ".env"
E2B_KEY_FILE = ROOT.parent / "key/e2B.txt"
IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099"
IMAGE_SHA256 = "3c6c76324780a911ff7b47bf52629280b4f2a49f26248540de049a61b9129363"
HOST = "huago-cone"
REMOTE_ROOT = "/home/huagosr/taskgenerator-data/r10-12-stirrup"
PRIMARY_JUDGE = "deepseek-v4-pro@official_api"
CHECK_JUDGE = "gpt-5.6-terra@tuzi_chat_completions"
TASKS = (
    "7d7fc9a7-21a7-4b83-906f-416dea5ad04f",
    "1b1ade2d-f9f6-4a04-baa5-aa15012b53be",
    "36d567ba-e205-4313-9756-931c6e4691fe",
)
DIAGNOSTIC_TASK = TASKS[0]
DIAGNOSTIC_MODEL = "gpt-5.4-mini"
DIAGNOSTIC_TIMEOUT_SECONDS = 10_800
TIERS = ("strong", "middle", "weak")
MAX_SOLVER_TECHNICAL_RECOVERIES = 3
MAX_PRIMARY_FORMAT_RECOVERIES = 2
MAX_CHECK_FORMAT_RECOVERIES = 1
PREFLIGHT_ATTEMPT_TIMEOUT_SECONDS = 600
FORMAL_ATTEMPT_TIMEOUT_SECONDS = 7200


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _campaign_id(run_root: Path) -> str:
    value = run_root.name
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None:
        raise ValueError("r10_12_invalid_campaign_id")
    return value


def _write(path: Path, value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, (list, tuple)):
        value = [row.model_dump(mode="json") if hasattr(row, "model_dump") else row for row in value]
    atomic_json(path, value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_input_sha256(workspace: Path) -> str:
    digest = hashlib.sha256()
    paths = [workspace / "candidate_task.md"] + sorted(
        path for path in (workspace / "reference_files").rglob("*") if path.is_file()
    )
    for path in paths:
        relative = path.relative_to(workspace).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_file_sha256(path)))
    return digest.hexdigest()


def _binding(task_id: str) -> GDPvalTaskBindingV1:
    return GDPvalTaskBindingV1.model_validate_json(
        (GDPVAL_DATA / "tasks" / task_id / "binding.json").read_text(encoding="utf-8")
    )


def _task_hashes(task_id: str) -> dict[str, str]:
    task = GDPVAL_DATA / "tasks" / task_id
    with tempfile.TemporaryDirectory(prefix="r10-12-hash-") as temporary:
        workspace = Path(temporary)
        shutil.copy2(task / "prompt.txt", workspace / "candidate_task.md")
        shutil.copytree(task / "reference_files", workspace / "reference_files")
        input_sha = _candidate_input_sha256(workspace)
    rubric = adapt_gdpval_rubric(_binding(task_id))
    return {"input_sha256": input_sha, "rubric_sha256": canonical_json_sha256(rubric)}


def _r10_11_expected_hashes() -> dict[str, dict[str, str]]:
    scope = json.loads(R10_11_SCOPE.read_text(encoding="utf-8"))
    result = {}
    for task_id in TASKS:
        assignment = next(row for row in scope["assignments"] if row["task_id"] == task_id and row["role"] == "primary")
        old = scope["hashes"][assignment["assignment_id"]]
        result[task_id] = {"input_sha256": old["input_sha256"], "rubric_sha256": old["rubric_sha256"]}
    return result


def _stage_case(target: Path, task_id: str) -> None:
    if target.exists():
        raise FileExistsError(f"r10_12_case_exists:{target}")
    task = GDPVAL_DATA / "tasks" / task_id
    binding = _binding(task_id)
    target.mkdir(parents=True)
    shutil.copytree(task / "reference_files", target / "reference_files")
    rubric = [row.model_dump(mode="json") for row in binding.rubric_items]
    _write(target / "dataset_row.json", {
        "task_id": task_id,
        "prompt": (task / "prompt.txt").read_text(encoding="utf-8"),
        "reference_files": [f"reference_files/{name}" for name in binding.reference_files],
        "deliverable_files": [],
        "rubric_json": json.dumps(rubric, ensure_ascii=False),
    })


def solver_assignments() -> list[dict[str, str]]:
    rows = []
    for task_id in TASKS:
        for tier in TIERS:
            identity = {"task_id": task_id, "tier": tier}
            rows.append(identity | {"assignment_id": canonical_json_sha256(identity)[:24]})
    return rows


def prepare(run_root: Path) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError(f"r10_12_run_root_exists:{run_root}")
    campaign_id = _campaign_id(run_root)
    old_hashes = _r10_11_expected_hashes()
    hashes = {task_id: _task_hashes(task_id) for task_id in TASKS}
    if hashes != old_hashes:
        raise ValueError("r10_12_r10_11_input_or_rubric_hash_drift")
    for task_id in TASKS:
        _stage_case(run_root / "cases" / task_id, task_id)
    scope = {
        "scope_version": "r10.stirrup_calibration_scope.1",
        "campaign_id": campaign_id,
        "created_at": _now(),
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip(),
        "purpose": "gdpval_eval_calibration_only",
        "tasks": list(TASKS),
        "task_hashes": hashes,
        "requested_panel": PRIMARY_MODELS,
        "fixed_fallbacks": FALLBACK_MODELS,
        "panel_rationale": "user_selected_gpt54mini_no_gemini_after_tuzi_sol_latency_probe",
        "solver_assignments": solver_assignments(),
        "solver": {
            "provider": "tuzi_chat_completions", "harness": "stirrup", "harness_version": "0.1.8",
            "e2b_sdk_version": "2.20.0", "template_alias": "rw-task-sandbox:stable",
            "template_build_id": "c9cf3369-49c8-4bff-8f81-8ad9ce9cc252", "max_turns": 100,
            "context_window_tokens": 64000, "max_completion_tokens": 8192, "normal_call_limit": 9,
            "attempt_timeout_seconds": FORMAL_ATTEMPT_TIMEOUT_SECONDS,
            "campaign_technical_recovery_limit": 3, "serial": True,
        },
        "preflight": {"primary_normal_limit": 3, "per_primary_technical_recovery_limit": 1,
                      "fallback_normal_limit": 0, "formal_task_content_used": False,
                      "attempt_timeout_seconds": PREFLIGHT_ATTEMPT_TIMEOUT_SECONDS},
        "grading": {
            "primary": {"judge_id": PRIMARY_JUDGE, "normal_call_limit": 9,
                        "campaign_format_recovery_limit": 2, "policy": "strict_item_only"},
            "checks": {"judge_id": CHECK_JUDGE, "normal_call_limit": 3,
                       "campaign_format_recovery_limit": 1},
            "shadow": {"normal_call_limit": 3, "trigger_score_gte": .88,
                       "changes_primary_score": False},
            "strict_prompt_sha256": hashlib.sha256(strict_grading_system_prompt().encode()).hexdigest(),
        },
        "environment": {"controller": "local", "judge_host": HOST, "image": IMAGE,
                        "image_sha256": IMAGE_SHA256, "template_known_package_mismatches": 3,
                        "template_system_tools_ok": "19/19"},
        "credential_sources": ["local_rw_task_env", "local_e2b_key_file", "server_deepseek_secret", "server_tuzi_secret"],
        "excluded_actions": ["quality_redraw", "semantic_retry", "invalid_delivery_grading", "score_feedback",
                             "rl", "training", "test_v2_outputs_access", "downward_audit_changes_primary"],
    }
    run_root.mkdir(parents=True, exist_ok=True)
    _write(run_root / "scope.json", scope)
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_calibration_receipt.1", "scope_sha256": canonical_json_sha256(scope),
        "status": "prepared", "provider_calls": 0, "created_at": _now(),
    })
    return scope


def prepare_diagnostic(run_root: Path) -> dict[str, Any]:
    """Bind one gpt-5.4-mini latency/progress probe; no calibration claim."""

    if run_root.exists():
        raise FileExistsError(f"r10_12_run_root_exists:{run_root}")
    campaign_id = _campaign_id(run_root)
    hashes = _task_hashes(DIAGNOSTIC_TASK)
    if hashes != _r10_11_expected_hashes()[DIAGNOSTIC_TASK]:
        raise ValueError("r10_12_r10_11_input_or_rubric_hash_drift")
    _stage_case(run_root / "case", DIAGNOSTIC_TASK)
    scope = {
        "scope_version": "r10.stirrup_diagnostic_scope.1",
        "campaign_id": campaign_id, "created_at": _now(),
        "purpose": "stirrup_progress_and_latency_diagnostic_only",
        "task_id": DIAGNOSTIC_TASK, "task_hashes": hashes,
        "model_id": DIAGNOSTIC_MODEL, "provider_id": "tuzi_chat_completions",
        "harness": "stirrup", "harness_version": "0.1.8",
        "e2b_template_alias": "rw-task-sandbox:stable",
        "e2b_template_build_id": "c9cf3369-49c8-4bff-8f81-8ad9ce9cc252",
        "max_turns": 100, "context_window_tokens": 64000, "max_completion_tokens": 8192,
        "attempt_timeout_seconds": DIAGNOSTIC_TIMEOUT_SECONDS,
        "normal_call_limit": 1, "technical_recovery_limit": 0,
        "grading_authorized": False, "calibration_claim_authorized": False,
        "progress_events": ["session_run_started", "model_request_started",
                            "model_request_completed", "model_request_failed",
                            "session_run_completed"],
        "credential_sources": ["local_rw_task_env", "local_e2b_key_file"],
    }
    _write(run_root / "scope.json", scope)
    return scope


def diagnose_solver(run_root: Path) -> dict[str, Any]:
    if not (run_root / "scope.json").is_file():
        raise FileNotFoundError("r10_12_diagnostic_scope_missing")
    session = run_root / "session"
    if session.exists():
        raise FileExistsError("r10_12_diagnostic_session_exists")
    attempt = session / "attempt_1"
    attempt.mkdir(parents=True)
    code, semantic = _run_solver_attempt(
        run_root / "case", attempt / "output", DIAGNOSTIC_MODEL, 100,
        DIAGNOSTIC_TIMEOUT_SECONDS,
    )
    output = attempt / "output"
    delivery_status = _validate_delivery(DIAGNOSTIC_TASK, _delivery_root(output)) if code == 0 else "missing"
    progress_path = output / "progress.jsonl"
    events = []
    if progress_path.is_file():
        events = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines() if line]
    completed_requests = sum(row.get("event") == "model_request_completed" for row in events)
    started_requests = sum(row.get("event") == "model_request_started" for row in events)
    tool_calls = sum(len(row.get("tool_calls", [])) for row in events)
    status = "completed" if code == 0 and delivery_status == "complete" else "incomplete"
    summary = {
        "summary_version": "r10.stirrup_diagnostic_summary.1", "status": status,
        "task_id": DIAGNOSTIC_TASK, "model_id": DIAGNOSTIC_MODEL,
        "return_code": code, "semantic_phase_started": semantic,
        "delivery_status": delivery_status, "model_requests_started": started_requests,
        "model_requests_completed": completed_requests, "tool_calls_requested": tool_calls,
        "session_completed": any(row.get("event") == "session_run_completed" for row in events),
        "progress_evidence_path": progress_path.relative_to(run_root).as_posix(),
        "calibration_claim": False,
    }
    _write(run_root / "summary.json", summary)
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_diagnostic_receipt.1",
        "scope_sha256": canonical_json_sha256(scope), "status": status,
        "solver_calls": 1, "grader_calls": 0, "closed_at": _now(),
    })
    return summary


def close_diagnostic_failure(run_root: Path) -> dict[str, Any]:
    if (run_root / "summary.json").exists():
        raise FileExistsError("r10_12_diagnostic_summary_exists")
    progress_path = run_root / "session/attempt_1/output/progress.jsonl"
    if not progress_path.is_file():
        raise FileNotFoundError("r10_12_diagnostic_progress_missing")
    events = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines() if line]
    summary = {
        "summary_version": "r10.stirrup_diagnostic_summary.1", "status": "incomplete",
        "stop_reason": "controller_cancelled_after_context_output_budget_coupling_identified",
        "task_id": DIAGNOSTIC_TASK, "model_id": DIAGNOSTIC_MODEL,
        "semantic_phase_started": True, "delivery_status": "missing",
        "model_requests_started": sum(row.get("event") == "model_request_started" for row in events),
        "model_requests_completed": sum(row.get("event") == "model_request_completed" for row in events),
        "tool_calls_requested": sum(len(row.get("tool_calls", [])) for row in events),
        "session_completed": False,
        "progress_evidence_path": progress_path.relative_to(run_root).as_posix(),
        "calibration_claim": False,
    }
    _write(run_root / "summary.json", summary)
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_diagnostic_receipt.1",
        "scope_sha256": canonical_json_sha256(scope), "status": "incomplete",
        "solver_calls": 1, "grader_calls": 0, "closed_at": _now(),
        "stop_reason": summary["stop_reason"],
    })
    return summary


def revalidate_diagnostic_delivery(run_root: Path) -> dict[str, Any]:
    target = run_root / "delivery_revalidation.json"
    if target.exists():
        raise FileExistsError("r10_12_diagnostic_revalidation_exists")
    output = run_root / "session/attempt_1/output"
    status = _validate_delivery(DIAGNOSTIC_TASK, _delivery_root(output))
    result = {
        "revalidation_version": "r10.stirrup_delivery_revalidation.1",
        "original_summary_sha256": _file_sha256(run_root / "summary.json"),
        "original_policy": "exact_hidden_reference_basename",
        "corrected_policy": "legacy_rw_task_finish_paths_count_type_nonempty_openable",
        "delivery_status": status,
        "controller_only": True, "provider_calls": 0,
    }
    _write(target, result)
    return result


def _dotenv(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[name.strip()] = value
    return values


def _solver_environment() -> tuple[dict[str, str], list[str]]:
    values = _dotenv(TUZI_ENV)
    api_key = values.get("AGENT_API_KEY") or values.get("STIRRUP_OPENAI_API_KEY") or values.get("OPENAI_API_KEY")
    base_url = values.get("AGENT_BASE_URL") or values.get("STIRRUP_OPENAI_BASE_URL") or values.get("OPENAI_BASE_URL")
    e2b_key = E2B_KEY_FILE.read_text(encoding="utf-8").strip()
    if not api_key or not base_url or not e2b_key:
        raise RuntimeError("r10_12_solver_secret_missing")
    environment = os.environ.copy()
    environment.update({
        "AGENT_API_KEY": api_key,
        "AGENT_BASE_URL": base_url,
        "E2B_API_KEY": e2b_key,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
        "TERM": "dumb",
    })
    return environment, [api_key, e2b_key]


def _redact(value: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def _run_solver_attempt(
    case: Path, output: Path, model: str, max_turns: int, timeout_seconds: int
) -> tuple[int, bool]:
    environment, secrets = _solver_environment()
    command = [
        str(SOLVER_PYTHON), str(ROOT / "Test/r10_12_local_stirrup_solver.py"),
        "--case-dir", str(case), "--output-dir", str(output), "--model", model,
        "--rw-task-root", str(RW_TASK_ROOT), "--max-turns", str(max_turns),
    ]
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=environment, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout_seconds,
        )
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code = 124
        _write(output.parent / "timeout.json", {"timeout_seconds": timeout_seconds, "at": _now()})
    (output.parent / "stdout.txt").write_text(_redact(stdout, secrets), encoding="utf-8")
    (output.parent / "stderr.txt").write_text(_redact(stderr, secrets), encoding="utf-8")
    marker = output / "phase.json"
    semantic = marker.is_file() and json.loads(marker.read_text(encoding="utf-8")).get("semantic_phase_started") is True
    return code, semantic


def _preflight_case(run_root: Path) -> Path:
    case = run_root / "preflight/case"
    if not case.exists():
        case.mkdir(parents=True)
        _write(case / "dataset_row.json", {
            "task_id": "r10_12_stirrup_preflight",
            "prompt": "Create exactly one UTF-8 text file named preflight.txt containing exactly R10.12-STIRRUP-OK, then submit it.",
            "reference_files": [], "deliverable_files": [], "rubric_json": "[]",
        })
    return case


def _preflight_output_valid(output: Path) -> bool:
    matches = [path for path in (output / "deliverable_files").rglob("preflight.txt") if path.is_file()]
    return len(matches) == 1 and matches[0].read_text(encoding="utf-8").strip() == "R10.12-STIRRUP-OK"


def _preflight_candidate(run_root: Path, tier: str, model: str, role: str) -> StirrupPreflightResultV1:
    session = run_root / "preflight" / f"{tier}_{role}_{model.replace('/', '_')}"
    if session.exists():
        raise FileExistsError("r10_12_preflight_session_exists")
    session.mkdir(parents=True)
    status = "semantic_failure"
    attempts = 0
    for number in (1, 2):
        attempts = number
        attempt = session / f"attempt_{number}"
        attempt.mkdir()
        code, semantic = _run_solver_attempt(
            _preflight_case(run_root), attempt / "output", model, 8,
            PREFLIGHT_ATTEMPT_TIMEOUT_SECONDS,
        )
        if code == 0 and _preflight_output_valid(attempt / "output"):
            status = "passed"
            break
        if semantic:
            status = "semantic_failure"
            break
        status = "technical_failure"
        if number == 2:
            break
    result = StirrupPreflightResultV1(
        tier=tier, model_id=model, candidate_role=role, status=status, attempt_count=attempts,
        evidence_path=session.relative_to(run_root).as_posix(),
    )
    _write(session / "result.json", result)
    return result


def preflight(run_root: Path) -> FrozenStirrupPanelV1:
    if not (run_root / "scope.json").is_file():
        raise FileNotFoundError("r10_12_scope_missing")
    if (run_root / "frozen_panel.json").exists():
        raise FileExistsError("r10_12_panel_already_frozen")
    results: list[StirrupPreflightResultV1] = []
    for tier in TIERS:
        primary = _preflight_candidate(run_root, tier, PRIMARY_MODELS[tier], "primary")
        results.append(primary)
        if primary.status != "passed" and FALLBACK_MODELS[tier] is not None:
            results.append(_preflight_candidate(run_root, tier, FALLBACK_MODELS[tier], "fallback"))
    _write(run_root / "preflight/results.json", results)
    try:
        panel = freeze_model_panel(results)
    except ValueError as exc:
        _write(run_root / "summary.json", {
            "summary_version": "r10.stirrup_calibration_summary.1",
            "status": "incomplete", "stop_reason": str(exc),
            "evidence_level": "infrastructure_preflight",
            "preflight_results": [row.model_dump(mode="json") for row in results],
            "formal_solver_started": False,
        })
        raise
    _write(run_root / "frozen_panel.json", panel)
    return panel


def close_preflight_failure(run_root: Path) -> dict[str, Any]:
    """Freeze an exhausted preflight without issuing or authorizing new calls."""

    if (run_root / "frozen_panel.json").exists() or (run_root / "solver_sessions").exists():
        raise RuntimeError("r10_12_preflight_closeout_after_formal_start_forbidden")
    result_paths = sorted((run_root / "preflight").glob("*/result.json"))
    results = [StirrupPreflightResultV1.model_validate_json(path.read_text(encoding="utf-8")) for path in result_paths]
    if not results:
        raise FileNotFoundError("r10_12_preflight_results_missing")
    phase_paths = sorted((run_root / "preflight").glob("*/attempt_*/output/phase.json"))
    before_semantic = bool(phase_paths) and all(
        json.loads(path.read_text(encoding="utf-8")).get("semantic_phase_started") is not True
        for path in phase_paths
    )
    stderr_paths = sorted((run_root / "preflight").glob("*/attempt_*/stderr.txt"))
    console_encoding = bool(stderr_paths) and all(
        "UnicodeEncodeError" in path.read_text(encoding="utf-8", errors="replace") for path in stderr_paths
    )
    stop_reason = (
        "controller_console_encoding_failure_before_e2b_or_provider"
        if before_semantic and console_encoding else "model_panel_unavailable_after_fixed_preflight"
    )
    summary = {
        "summary_version": "r10.stirrup_calibration_summary.1", "status": "incomplete",
        "stop_reason": stop_reason, "evidence_level": "infrastructure_preflight",
        "preflight_results": [row.model_dump(mode="json") for row in results],
        "preflight_attempts": sum(row.attempt_count for row in results),
        "all_failures_before_semantic_phase": before_semantic,
        "formal_solver_started": False, "primary_grading_started": False,
        "model_availability_conclusion": "not_tested" if before_semantic else "inconclusive",
    }
    _write(run_root / "preflight/results.json", results)
    _write(run_root / "summary.json", summary)
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_calibration_receipt.1",
        "scope_sha256": canonical_json_sha256(scope), "status": "incomplete",
        "provider_calls": 0 if before_semantic else None,
        "formal_solver_calls": 0, "primary_grader_calls": 0,
        "closed_at": _now(), "stop_reason": stop_reason,
    })
    return summary


def close_solver_failure(run_root: Path) -> dict[str, Any]:
    """Freeze a formal Solver campaign that stopped before aggregate receipts."""

    if (run_root / "solver_receipts.json").exists() or (run_root / "grading").exists():
        raise RuntimeError("r10_12_solver_closeout_after_aggregate_or_grading_forbidden")
    sessions = sorted((run_root / "solver_sessions").glob("*"))
    sessions = [path for path in sessions if path.is_dir()]
    if not sessions:
        raise FileNotFoundError("r10_12_solver_sessions_missing")
    phase_paths = [
        phase for session in sessions
        for phase in session.glob("attempts/attempt_*/output/phase.json")
    ]
    semantic = any(
        json.loads(path.read_text(encoding="utf-8")).get("semantic_phase_started") is True
        for path in phase_paths
    )
    timed_out = any(
        path for session in sessions for path in session.glob("attempts/attempt_*/timeout.json")
    )
    stop_reason = (
        "formal_solver_attempt_timeout_after_semantic_start"
        if timed_out and semantic else "formal_solver_controller_failure"
    )
    summary = {
        "summary_version": "r10.stirrup_calibration_summary.1", "status": "incomplete",
        "stop_reason": stop_reason, "evidence_level": "solver_execution",
        "formal_solver_started": True, "started_solver_sessions": len(sessions),
        "semantic_phase_started": semantic, "primary_grading_started": False,
    }
    _write(run_root / "summary.json", summary)
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_calibration_receipt.1",
        "scope_sha256": canonical_json_sha256(scope), "status": "incomplete",
        "formal_solver_calls": len(sessions), "primary_grader_calls": 0,
        "closed_at": _now(), "stop_reason": stop_reason,
    })
    return summary


def _delivery_root(output: Path) -> Path:
    return output / "deliverable_files"


def _validate_delivery(task_id: str, delivery: Path) -> str:
    files = sorted(path for path in delivery.rglob("*") if path.is_file()) if delivery.is_dir() else []
    if not files:
        return "missing"
    # GDPval's deliverable_files names describe the reference submission shape;
    # the public prompt may not require those exact basenames. The legacy
    # rw-task collector accepts finish paths as submitted, so validate count,
    # file type, non-emptiness, and openability rather than hidden filenames.
    expected = list(_binding(task_id).expected_deliverables)
    if len(files) != len(expected) or sorted(path.suffix.casefold() for path in files) != sorted(
        Path(name).suffix.casefold() for name in expected
    ) or any(path.stat().st_size == 0 for path in files):
        return "invalid"
    for path in files:
        if path.suffix.casefold() in {".docx", ".xlsx", ".pptx"}:
            try:
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip() is not None:
                        return "invalid"
            except (OSError, zipfile.BadZipFile):
                return "invalid"
    return "complete"


def solve(run_root: Path) -> list[StirrupSolverReceiptV1]:
    panel = FrozenStirrupPanelV1.model_validate_json((run_root / "frozen_panel.json").read_text(encoding="utf-8"))
    hashes = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))["task_hashes"]
    model_by_tier = {tier: getattr(panel, tier) for tier in TIERS}
    receipts, recoveries = [], 0
    for row in solver_assignments():
        session = run_root / "solver_sessions" / row["assignment_id"]
        if session.exists():
            raise FileExistsError(f"r10_12_solver_session_exists:{row['assignment_id']}")
        session.mkdir(parents=True)
        attempts: list[StirrupSolverAttemptV1] = []
        delivery_status, delivery_sha = "missing", None
        for number in (1, 2):
            attempt = session / "attempts" / f"attempt_{number}"
            attempt.mkdir(parents=True)
            code, semantic = _run_solver_attempt(
                run_root / "cases" / row["task_id"], attempt / "output",
                model_by_tier[row["tier"]], 100, FORMAL_ATTEMPT_TIMEOUT_SECONDS,
            )
            status = _validate_delivery(row["task_id"], _delivery_root(attempt / "output")) if code == 0 else "missing"
            if code == 0 and status == "complete":
                state = "succeeded"
                delivery_status = "complete"
                delivery_sha = tree_sha256(_delivery_root(attempt / "output"))
            elif not semantic:
                state = "technical_failure_before_semantic_turn"
            else:
                state = "semantic_or_delivery_failure"
                delivery_status = status
            attempts.append(StirrupSolverAttemptV1(
                attempt_number=number, state=state, semantic_phase_started=semantic,
                technical_recovery_of=1 if number == 2 else None,
                evidence_path=attempt.relative_to(run_root).as_posix(),
                failure_type=None if state == "succeeded" else ("subprocess_failure" if code else "invalid_delivery"),
            ))
            if state == "succeeded" or state == "semantic_or_delivery_failure":
                break
            if recoveries >= MAX_SOLVER_TECHNICAL_RECOVERIES:
                break
            recoveries += 1
        receipt = StirrupSolverReceiptV1(
            task_id=row["task_id"], solver_id=model_by_tier[row["tier"]], tier=row["tier"],
            input_sha256=hashes[row["task_id"]]["input_sha256"],
            rubric_sha256=hashes[row["task_id"]]["rubric_sha256"],
            delivery_status=delivery_status, delivery_sha256=delivery_sha, attempts=attempts,
        )
        _write(session / "receipt.json", receipt)
        receipts.append(receipt)
    _write(run_root / "solver_receipts.json", receipts)
    return receipts


def _successful_output(run_root: Path, assignment_id: str) -> Path:
    session = run_root / "solver_sessions" / assignment_id
    receipt = StirrupSolverReceiptV1.model_validate_json((session / "receipt.json").read_text(encoding="utf-8"))
    success = next(row for row in receipt.attempts if row.state == "succeeded")
    return run_root / success.evidence_path / "output"


def _stage_grade(workspace: Path, run_root: Path, solver: dict[str, str], mode: str, provider: str,
                 primary_grade: dict[str, Any] | None = None) -> dict[str, str]:
    task_id = solver["task_id"]
    task = GDPVAL_DATA / "tasks" / task_id
    if workspace.exists():
        raise FileExistsError("r10_12_grade_workspace_exists")
    workspace.mkdir(parents=True)
    shutil.copy2(task / "prompt.txt", workspace / "candidate_task.md")
    shutil.copytree(task / "reference_files", workspace / "reference_files")
    output = _successful_output(run_root, solver["assignment_id"])
    shutil.copytree(_delivery_root(output), workspace / "anonymous_submission")
    rubric = adapt_gdpval_rubric(_binding(task_id))
    _write(workspace / "rubric_items.json", [row.model_dump(mode="json") for row in rubric])
    _write(workspace / "grade_schema.json", _strict_output_schema(IndependentRubricGradeDraftV1.model_json_schema()))
    _write(workspace / "grade_request.json", {"mode": mode, "provider": provider})
    shutil.copy2(ROOT / "Test/r10_12_remote_strict_grader.py", workspace)
    if primary_grade is not None:
        _write(workspace / "primary_grade.json", primary_grade)
    return {
        "input_sha256": _candidate_input_sha256(workspace),
        "rubric_sha256": canonical_json_sha256(rubric),
        "delivery_sha256": tree_sha256(workspace / "anonymous_submission"),
    }


def _remote_grade_call(workspace: Path, remote: str, provider: str) -> tuple[int, str]:
    if not re.fullmatch(r"/home/huagosr/taskgenerator-data/r10-12-stirrup/[A-Za-z0-9_./-]+", remote):
        raise ValueError("r10_12_remote_path_out_of_scope")
    _ssh(HOST, f"mkdir -p '{remote.rsplit('/', 1)[0]}' && rm -rf '{remote}'", timeout=120)
    upload = _scp(str(workspace), f"{HOST}:{remote}")
    if upload.returncode:
        return upload.returncode, "upload:" + upload.stderr[-2000:]
    if provider == "deepseek_official":
        secret_mount = "-v /home/huagosr/taskgenerator-secrets/deepseek_api_key:/run/secrets/deepseek_api_key:ro "
        secret_load = "export DEEPSEEK_API_KEY=\"$(cat /run/secrets/deepseek_api_key)\"; "
    else:
        secret_mount = "-v /home/huagosr/taskgenerator-secrets/eval_tuzi.env:/run/secrets/eval_tuzi_env:ro "
        secret_load = (
            "set -a; . /run/secrets/eval_tuzi_env; set +a; "
            "TUZI_API_KEY=$(printf '%s' \"$TUZI_API_KEY\" | tr -d '\\r\\n'); "
            "TUZI_BASE_URL=$(printf '%s' \"$TUZI_BASE_URL\" | tr -d '\\r\\n'); export TUZI_API_KEY TUZI_BASE_URL; "
        )
    command = (
        "set -u; workspace='" + remote + "'; timeout --preserve-status 1200 docker run --rm --init --read-only "
        "--cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 --memory 3g --cpus 2 "
        "--pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=512m -v \"$workspace:/workspace:rw\" "
        + secret_mount + "-w /workspace --entrypoint /bin/sh " + IMAGE + " -lc '" + secret_load
        + "python3 /workspace/r10_12_remote_strict_grader.py' > \"$workspace/docker_stdout.txt\" "
        "2> \"$workspace/docker_stderr.txt\""
    )
    result = _ssh(HOST, command, timeout=1300, check=False)
    with tempfile.TemporaryDirectory(prefix="r10-12-return-", dir=workspace.parent) as temporary:
        returned = Path(temporary) / "returned"
        download = _scp(f"{HOST}:{remote}", str(returned), timeout=180)
        if download.returncode:
            return download.returncode, "download:" + download.stderr[-2000:]
        nested = returned / Path(remote).name
        source = nested if nested.is_dir() else returned
        for name in ("grade.raw.json", "provider_response.json", "provider_status.json",
                     "strict_grade_packet_v2.json", "docker_stdout.txt", "docker_stderr.txt"):
            if (source / name).is_file():
                shutil.copy2(source / name, workspace / name)
    return result.returncode, result.stderr[-2000:]


def _finalize_grade(workspace: Path, solver: dict[str, str], hashes: dict[str, str], judge_id: str):
    draft = IndependentRubricGradeDraftV1.model_validate_json((workspace / "grade.raw.json").read_text(encoding="utf-8"))
    if draft.material_status == "incomplete" or any(row.applicability == "unresolved" for row in draft.assessments):
        raise RuntimeError("r10_12_material_incomplete")
    rubric = adapt_gdpval_rubric(_binding(solver["task_id"]))
    return finalize_independent_grade(
        task_id=solver["task_id"], submission_id=solver["solver_id"], judge_id=judge_id,
        rubric_items=rubric, draft=draft, staging_root=workspace,
        input_sha256=hashes["input_sha256"], delivery_sha256=hashes["delivery_sha256"],
    )


def _grade_once(run_root: Path, session: Path, solver: dict[str, str], mode: str, provider: str,
                judge_id: str, recovery_budget: dict[str, int], primary_grade: dict[str, Any] | None = None):
    if session.exists():
        raise FileExistsError("r10_12_grade_session_exists")
    session.mkdir(parents=True)
    attempt = 0
    while True:
        attempt += 1
        workspace = session / "attempts" / f"attempt_{attempt}"
        hashes = _stage_grade(workspace, run_root, solver, mode, provider, primary_grade)
        code, error = _remote_grade_call(
            workspace, f"{REMOTE_ROOT}/{_campaign_id(run_root)}/{session.name}/attempt_{attempt}", provider
        )
        try:
            if code:
                raise ConnectionError(f"r10_12_grade_transport:{code}:{error}")
            if mode == "shadow":
                return IndependentRubricGradeDraftV1.model_validate_json(
                    (workspace / "grade.raw.json").read_text(encoding="utf-8")
                )
            grade = _finalize_grade(workspace, solver, hashes, judge_id)
            _write(session / "review.json", grade)
            return grade
        except (ConnectionError, FileNotFoundError, json.JSONDecodeError, ValidationError) as exc:
            _write(workspace / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
            if recovery_budget["remaining"] <= 0:
                raise
            recovery_budget["remaining"] -= 1


def _solver_specs(run_root: Path) -> list[dict[str, str]]:
    panel = FrozenStirrupPanelV1.model_validate_json((run_root / "frozen_panel.json").read_text(encoding="utf-8"))
    models = {tier: getattr(panel, tier) for tier in TIERS}
    return [row | {"solver_id": models[row["tier"]]} for row in solver_assignments()]


def prepare_grading_retry(run_root: Path) -> dict[str, Any]:
    target = run_root / "grading_retry_1_scope.json"
    if target.exists() or (run_root / "grading_retry_1").exists():
        raise FileExistsError("r10_12_grading_retry_exists")
    receipts = [
        StirrupSolverReceiptV1.model_validate(value) for value in json.loads(
            (run_root / "solver_receipts.json").read_text(encoding="utf-8")
        )
    ]
    valid = [row for row in receipts if row.delivery_status == "complete"]
    scope = {
        "scope_version": "r10.strict_grading_format_retry_scope.1",
        "campaign_id": _campaign_id(run_root) + "_grading_retry_1", "created_at": _now(),
        "purpose": "same_input_format_recovery_after_length_truncation",
        "source_scope_sha256": _file_sha256(run_root / "scope.json"),
        "solver_receipts_sha256": _file_sha256(run_root / "solver_receipts.json"),
        "valid_submission_count": len(valid),
        "delivery_sha256": {f"{row.task_id}:{row.tier}": row.delivery_sha256 for row in valid},
        "judge_id": PRIMARY_JUDGE, "policy": "strict_item_only_concise",
        "max_output_tokens": 16384, "normal_call_limit": len(valid),
        "primary_format_recovery_limit": 1, "check_format_recovery_limit": 1,
        "grader_script_sha256": _file_sha256(ROOT / "Test/r10_12_remote_strict_grader.py"),
        "semantic_redraw": False, "solver_rerun": False,
    }
    _write(target, scope)
    return scope


def close_grading_retry_failure(run_root: Path) -> dict[str, Any]:
    summary_path = run_root / "grading_retry_1_summary.json"
    if summary_path.exists():
        raise FileExistsError("r10_12_grading_retry_summary_exists")
    grading_root = run_root / "grading_retry_1"
    reviews = [
        IndependentRubricGradeV1.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((grading_root / "primary").glob("*/review.json"))
    ]
    receipts = [
        StirrupSolverReceiptV1.model_validate(value) for value in json.loads(
            (run_root / "solver_receipts.json").read_text(encoding="utf-8")
        )
    ]
    specs = _solver_specs(run_root)
    summary = summarize(
        [row.model_dump(mode="json") for row in receipts],
        [row.model_dump(mode="json") for row in reviews], [], [], specs,
    )
    summary.update({
        "stop_reason": "weak_delivery_failures_and_sentinel_tuzi_authentication_failure",
        "primary_grades_completed": len(reviews), "sentinel_grades_completed": 0,
        "sentinel_failure_type": "HTTP_401_Unauthorized",
    })
    _write(summary_path, summary)
    retry_scope = json.loads((run_root / "grading_retry_1_scope.json").read_text(encoding="utf-8"))
    _write(run_root / "grading_retry_1_receipt.json", {
        "receipt_version": "r10.stirrup_calibration_receipt.1",
        "scope_sha256": canonical_json_sha256(retry_scope), "status": "incomplete",
        "primary_grades_completed": len(reviews), "sentinel_grades_completed": 0,
        "closed_at": _now(), "stop_reason": summary["stop_reason"],
    })
    return summary


def grade(
    run_root: Path, *, grading_name: str = "grading", summary_name: str = "summary.json",
    receipt_name: str = "receipt.json", scope_name: str = "scope.json",
    primary_recovery_limit: int = MAX_PRIMARY_FORMAT_RECOVERIES,
    check_recovery_limit: int = MAX_CHECK_FORMAT_RECOVERIES,
) -> dict[str, Any]:
    receipts = {
        (row.task_id, row.tier): row
        for row in [StirrupSolverReceiptV1.model_validate(value) for value in json.loads(
            (run_root / "solver_receipts.json").read_text(encoding="utf-8")
        )]
    }
    grading_root = run_root / grading_name
    if grading_root.exists():
        raise FileExistsError("r10_12_grading_root_exists")
    primary_budget = {"remaining": primary_recovery_limit}
    check_budget = {"remaining": check_recovery_limit}
    primary, checks, shadows = {}, [], []
    specs = _solver_specs(run_root)
    for solver in specs:
        receipt = receipts[(solver["task_id"], solver["tier"])]
        if receipt.delivery_status != "complete":
            continue
        review = _grade_once(
            run_root, grading_root / "primary" / solver["assignment_id"], solver,
            "primary", "deepseek_official", PRIMARY_JUDGE, primary_budget,
        )
        primary[(solver["task_id"], solver["tier"])] = review
    sentinel_keys = {(TASKS[0], "strong"), (TASKS[1], "middle"), (TASKS[2], "weak")}
    for solver in specs:
        key = (solver["task_id"], solver["tier"])
        if key not in sentinel_keys or key not in primary:
            continue
        review = _grade_once(
            run_root, grading_root / "checks" / solver["assignment_id"], solver,
            "check", "tuzi", CHECK_JUDGE, check_budget,
        )
        checks.append(review)
    for solver in specs:
        key = (solver["task_id"], solver["tier"])
        review = primary.get(key)
        if solver["task_id"] != TASKS[2] or review is None or review.normalized_score < .88:
            continue
        draft = _grade_once(
            run_root, grading_root / "shadow" / solver["assignment_id"], solver,
            "shadow", "deepseek_official", PRIMARY_JUDGE, {"remaining": 0},
            primary_grade=review.model_dump(mode="json"),
        )
        diagnostic = build_shadow_downward_diagnostic(review, draft)
        _write(grading_root / "shadow" / solver["assignment_id"] / "diagnostic.json", diagnostic)
        shadows.append(diagnostic)
    summary = summarize(
        [row.model_dump(mode="json") for row in receipts.values()],
        [row.model_dump(mode="json") for row in primary.values()],
        [row.model_dump(mode="json") for row in checks],
        [row.model_dump(mode="json") for row in shadows],
        specs,
    )
    _write(run_root / summary_name, summary)
    _write(run_root / receipt_name, {
        "receipt_version": "r10.stirrup_calibration_receipt.1",
        "scope_sha256": canonical_json_sha256(json.loads((run_root / scope_name).read_text(encoding="utf-8"))),
        "status": summary["status"], "primary_format_recoveries": primary_recovery_limit - primary_budget["remaining"],
        "check_format_recoveries": check_recovery_limit - check_budget["remaining"], "completed_at": _now(),
    })
    return summary


def _delivery_only(criterion: str) -> bool:
    normalized = criterion.casefold()
    return normalized.startswith("delivers ") and any(ext in normalized for ext in (".xlsx", ".docx", ".pdf", ".pptx"))


def summarize(receipts: list[dict[str, Any]], primary: list[dict[str, Any]], checks: list[dict[str, Any]],
              shadows: list[dict[str, Any]], specs: list[dict[str, str]]) -> dict[str, Any]:
    receipt_by = {(row["task_id"], row["tier"]): row for row in receipts}
    primary_by = {(row["task_id"], next(spec["tier"] for spec in specs if spec["task_id"] == row["task_id"] and
                                       spec["solver_id"] == row["submission_id"])): row for row in primary}
    check_rows = []
    for check in checks:
        spec = next(row for row in specs if row["task_id"] == check["task_id"] and row["solver_id"] == check["submission_id"])
        main = primary_by[(check["task_id"], spec["tier"])]
        main_items = {row["rubric_item_id"]: row for row in main["items"]}
        high = max(row["max_score"] for row in main["items"])
        extreme = any(row["max_score"] == high and {row["awarded"], main_items[row["rubric_item_id"]]["awarded"]} == {0, high}
                      for row in check["items"])
        check_rows.append({"task_id": check["task_id"], "tier": spec["tier"],
                           "normalized_delta": round(abs(check["normalized_score"] - main["normalized_score"]), 6),
                           "high_weight_extreme_conflict": extreme})
    all_deliveries_valid = len(receipt_by) == 9 and all(row["delivery_status"] == "complete" for row in receipts)
    structural = len(primary) == sum(row["delivery_status"] == "complete" for row in receipts) and all(
        row["material_status"] == "complete" and row["total_score"] == sum(item["awarded"] for item in row["items"])
        for row in primary
    )
    sentinel_ok = len(check_rows) == 3 and all(row["normalized_delta"] <= .10 and not row["high_weight_extreme_conflict"]
                                               for row in check_rows)
    means = {}
    for tier in TIERS:
        values = [primary_by[(task, tier)]["normalized_score"] for task in TASKS if (task, tier) in primary_by]
        if len(values) == 3:
            means[tier] = round(sum(values) / 3, 6)
    positive_tasks = sum(
        primary_by[(task, "strong")]["normalized_score"] > primary_by[(task, "weak")]["normalized_score"]
        for task in TASKS if (task, "strong") in primary_by and (task, "weak") in primary_by
    )
    mean_gap = round(means.get("strong", 0) - means.get("weak", 0), 6) if {"strong", "weak"} <= means.keys() else None
    professional_gap = False
    if all((task, tier) in primary_by for task in TASKS for tier in ("strong", "weak")):
        for task in TASKS:
            rubric = {row.rubric_item_id: row for row in adapt_gdpval_rubric(_binding(task))}
            strong_items = {row["rubric_item_id"]: row for row in primary_by[(task, "strong")]["items"]}
            weak_items = {row["rubric_item_id"]: row for row in primary_by[(task, "weak")]["items"]}
            if any(strong_items[item_id]["awarded"] > weak_items[item_id]["awarded"] and not _delivery_only(item.criterion)
                   for item_id, item in rubric.items()):
                professional_gap = True
                break
    if not structural or not sentinel_ok:
        status = "incomplete"
    elif not all_deliveries_valid:
        status = "inconclusive"
    elif mean_gap is not None and mean_gap >= .15 and positive_tasks >= 2 and professional_gap:
        status = "supported"
    else:
        status = "rejected"
    return {
        "summary_version": "r10.stirrup_calibration_summary.1", "status": status,
        "evidence_level": "provisional_llm_proxy", "solver_receipts": len(receipts),
        "all_deliveries_valid": all_deliveries_valid, "primary_structural_valid": structural,
        "sentinel_acceptance": sentinel_ok, "sentinels": check_rows, "primary_means": means,
        "strong_weak_mean_gap": mean_gap, "strong_above_weak_task_count": positive_tasks,
        "professional_item_gap_present": professional_gap, "shadow_diagnostics": shadows,
        "model_ranking_claim": False, "automatic_generator_feedback": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("prepare", "prepare-diagnostic", "diagnose", "close-diagnostic",
                 "revalidate-diagnostic", "preflight", "close-preflight", "close-solver",
                 "solve", "prepare-grading-retry", "grade", "grade-retry",
                 "close-grading-retry"),
    )
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.run_root)
    elif args.command == "prepare-diagnostic":
        result = prepare_diagnostic(args.run_root)
    elif args.command == "diagnose":
        result = diagnose_solver(args.run_root)
    elif args.command == "close-diagnostic":
        result = close_diagnostic_failure(args.run_root)
    elif args.command == "revalidate-diagnostic":
        result = revalidate_diagnostic_delivery(args.run_root)
    elif args.command == "preflight":
        result = preflight(args.run_root).model_dump(mode="json")
    elif args.command == "close-preflight":
        result = close_preflight_failure(args.run_root)
    elif args.command == "close-solver":
        result = close_solver_failure(args.run_root)
    elif args.command == "solve":
        result = [row.model_dump(mode="json") for row in solve(args.run_root)]
    elif args.command == "prepare-grading-retry":
        result = prepare_grading_retry(args.run_root)
    elif args.command == "grade-retry":
        result = grade(
            args.run_root, grading_name="grading_retry_1",
            summary_name="grading_retry_1_summary.json",
            receipt_name="grading_retry_1_receipt.json",
            scope_name="grading_retry_1_scope.json",
            primary_recovery_limit=1, check_recovery_limit=1,
        )
    elif args.command == "close-grading-retry":
        result = close_grading_retry_failure(args.run_root)
    else:
        result = grade(args.run_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
