"""Run the fixed four-route R10.12-S1 uniform Chat/Stirrup supplement."""

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
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

import run_r10_12_stirrup_calibration as base
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.independent_rubric_grader import (
    IndependentRubricGradeDraftV1,
    IndependentRubricGradeV1,
    adapt_gdpval_rubric,
    canonical_json_sha256,
    tree_sha256,
)
from task_generator.evaluation.stirrup_calibration import StirrupSolverAttemptV1
from task_generator.evaluation.stirrup_supplement import (
    SUPPLEMENT_MODELS,
    FrozenStirrupSupplementPanelV1,
    StirrupSupplementProtocolProbeV1,
    StirrupSupplementSolverReceiptV1,
    classify_supplement_result,
    freeze_supplement_panel,
)


RUN_ID = "r10_12_model_supplement_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
SLOTS = tuple(SUPPLEMENT_MODELS)
PREFLIGHT_TIMEOUT_SECONDS = 900
FORMAL_TIMEOUT_SECONDS = 7200
MAX_SOLVER_TECHNICAL_RECOVERIES = 4
MAX_PRIMARY_FORMAT_RECOVERIES = 2
MAX_CHECK_FORMAT_RECOVERIES = 1
PRIMARY_JUDGE = "deepseek-v4-pro@official_api"
CHECK_JUDGE = "gpt-5.6-terra@tuzi_chat_completions"
SENTINELS = {
    (base.TASKS[0], "strong_primary"),
    (base.TASKS[1], "strong_check"),
    (base.TASKS[2], "cross_family"),
    (base.TASKS[1], "lower_anchor"),
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    base._write(path, value)


def _file_sha256(path: Path) -> str:
    return base._file_sha256(path)


def _campaign_id(run_root: Path) -> str:
    value = run_root.name
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None:
        raise ValueError("r10_12_s1_invalid_campaign_id")
    return value


def assignments() -> list[dict[str, str]]:
    rows = []
    for task_id in base.TASKS:
        for slot, model in SUPPLEMENT_MODELS.items():
            identity = {"task_id": task_id, "slot": slot, "solver_id": model}
            rows.append(identity | {"assignment_id": canonical_json_sha256(identity)[:24]})
    return rows


def prepare(run_root: Path) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError(f"r10_12_s1_run_root_exists:{run_root}")
    old_hashes = base._r10_11_expected_hashes()
    hashes = {task_id: base._task_hashes(task_id) for task_id in base.TASKS}
    if hashes != old_hashes:
        raise ValueError("r10_12_s1_r10_11_input_or_rubric_hash_drift")
    for task_id in base.TASKS:
        base._stage_case(run_root / "cases" / task_id, task_id)
    scope = {
        "scope_version": "r10.stirrup_supplement_scope.1",
        "campaign_id": _campaign_id(run_root),
        "created_at": _now(),
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True,
        ).stdout.strip(),
        "purpose": "distinguish_route_panel_selection_from_task_or_grading_ceiling",
        "provider": "tuzi_chat_completions",
        "endpoint": "/v1/chat/completions",
        "requested_panel": SUPPLEMENT_MODELS,
        "model_identity_claim": False,
        "fallbacks": False,
        "solver_assignments": assignments(),
        "task_hashes": hashes,
        "preflight": {
            "normal_sessions": 4,
            "minimum_completed_model_requests": 2,
            "required_tools": ["code_exec", "finish"],
            "attempt_timeout_seconds": PREFLIGHT_TIMEOUT_SECONDS,
            "technical_recovery": "one_per_model_only_before_semantic_start",
        },
        "solver": {
            "normal_sessions": 12,
            "serial": True,
            "max_turns": 100,
            "context_window_tokens": 64000,
            "max_completion_tokens": 8192,
            "attempt_timeout_seconds": FORMAL_TIMEOUT_SECONDS,
            "campaign_technical_recovery_limit": MAX_SOLVER_TECHNICAL_RECOVERIES,
        },
        "grading": {
            "judge_probe_normal_limit": 1,
            "judge_probe_format_recovery_limit": 1,
            "primary": {"judge_id": PRIMARY_JUDGE, "normal_call_limit": 12,
                        "format_recovery_limit": MAX_PRIMARY_FORMAT_RECOVERIES},
            "checks": {"judge_id": CHECK_JUDGE, "normal_call_limit": 4,
                       "format_recovery_limit": MAX_CHECK_FORMAT_RECOVERIES,
                       "sentinels": sorted(f"{task}:{slot}" for task, slot in SENTINELS)},
            "pairwise": False, "holistic": False, "downward_audit": False,
        },
        "environment": {
            "harness": "stirrup", "harness_version": "0.1.8",
            "e2b_sdk_version": "2.20.0", "e2b_template_alias": "rw-task-sandbox:stable",
            "e2b_template_build_id": "c9cf3369-49c8-4bff-8f81-8ad9ce9cc252",
        },
        "credential_sources": ["local_rw_task_env", "local_e2b_key_file",
                               "server_deepseek_secret", "server_tuzi_secret"],
        "no_gemini": True,
        "semantic_redraw": False,
        "automatic_generator_feedback": False,
    }
    _write(run_root / "scope.json", scope)
    _write(run_root / "dry_run.json", {
        "dry_run_version": "r10.stirrup_supplement_dry_run.1",
        "campaign_id": scope["campaign_id"], "provider_calls": 0,
        "preflight_models": list(SUPPLEMENT_MODELS.values()),
        "solver_assignments": scope["solver_assignments"],
        "task_hashes": hashes, "endpoint": scope["endpoint"],
        "e2b_template_build_id": scope["environment"]["e2b_template_build_id"],
        "call_limits": {"preflight_sessions": 4, "solver_sessions": 12,
                        "preflight_technical_recoveries": 4,
                        "solver_technical_recoveries": MAX_SOLVER_TECHNICAL_RECOVERIES,
                        "judge_probe_normal": 1, "judge_probe_format_recoveries": 1,
                        "primary_grades": 12,
                        "primary_format_recoveries": MAX_PRIMARY_FORMAT_RECOVERIES,
                        "check_grades": 4,
                        "check_format_recoveries": MAX_CHECK_FORMAT_RECOVERIES},
    })
    return scope


def _http_json(url: str, *, key: str | None = None, body: dict[str, Any] | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode("utf-8"),
        headers=headers, method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def snapshot_routes(run_root: Path) -> dict[str, Any]:
    target = run_root / "route_snapshot.json"
    if target.exists():
        raise FileExistsError("r10_12_s1_route_snapshot_exists")
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    environment, _ = base._solver_environment()
    key = environment["AGENT_API_KEY"]
    configured = environment["AGENT_BASE_URL"].rstrip("/")
    api_root = configured[:-3] if configured.endswith("/v1") else configured
    pricing = _http_json(api_root + "/api/pricing")
    catalog = {row["model_name"]: row for row in pricing["data"] if row.get("model_name") in SUPPLEMENT_MODELS.values()}
    metrics = _http_json(api_root + "/api/perf-metrics/batch", body={
        "models": list(SUPPLEMENT_MODELS.values()), "hours": 24, "resolution": "hourly",
    })
    visible = _http_json(api_root + "/v1/models", key=key)
    all_ids = sorted(str(row.get("id")) for row in visible.get("data", []) if row.get("id"))
    selected = {}
    for slot, model in SUPPLEMENT_MODELS.items():
        row = catalog.get(model, {})
        endpoint_values = row.get("endpoints") or {}
        selected[slot] = {
            "model_id": model,
            "visible_to_token": model in all_ids,
            "supported_endpoint_types": row.get("supported_endpoint_types") or [],
            "chat_endpoint_declared": any(
                isinstance(value, dict) and value.get("path") == "/v1/chat/completions"
                for value in endpoint_values.values()
            ),
            "hot_rank": row.get("hot_rank"), "hot_call_count": row.get("hot_call_count"),
        }
    metric_rows = {}
    for row in metrics.get("data", []):
        aggregate = row.get("aggregate") or {}
        metric_rows[row.get("model_name")] = {
            "has_samples": aggregate.get("has_samples"), "sample_level": aggregate.get("sample_level"),
            "success_rate": aggregate.get("success_rate"), "avg_latency_ms": aggregate.get("avg_latency_ms"),
            "avg_ttft_ms": aggregate.get("avg_ttft_ms"), "avg_tps": aggregate.get("avg_tps"),
            "latest_sample_ts": aggregate.get("latest_sample_ts"),
        }
    result = {
        "snapshot_version": "r10.stirrup_supplement_route_snapshot.1",
        "campaign_id": scope["campaign_id"], "captured_at": _now(),
        "runtime_truth_only": True, "model_identity_claim": False,
        "endpoint": "/v1/chat/completions", "selected_models": selected,
        "performance_24h": metric_rows,
        "visible_model_ids_sha256": canonical_json_sha256(all_ids),
        "all_selected_visible": all(row["visible_to_token"] for row in selected.values()),
        "all_chat_declared": all(row["chat_endpoint_declared"] for row in selected.values()),
    }
    _write(target, result)
    if not result["all_selected_visible"] or not result["all_chat_declared"]:
        _freeze_incomplete(run_root, "route_snapshot_gate", "selected_model_or_chat_endpoint_unavailable")
    return result


def _probe_case(run_root: Path) -> Path:
    case = run_root / "protocol_preflight/case"
    if not case.exists():
        case.mkdir(parents=True)
        _write(case / "dataset_row.json", {
            "task_id": "r10_12_s1_protocol_preflight",
            "prompt": "Create exactly one UTF-8 text file named preflight.txt containing exactly R10.12-S1-STIRRUP-OK, verify its contents with the code tool, then submit it with finish.",
            "reference_files": [], "deliverable_files": [], "rubric_json": "[]",
        })
    return case


def _probe_evidence(output: Path) -> dict[str, Any]:
    events = [json.loads(line) for line in (output / "progress.jsonl").read_text(encoding="utf-8").splitlines() if line]
    completed = [row for row in events if row.get("event") == "model_request_completed"]
    tool_calls = [name for row in completed for name in row.get("tool_calls", [])]
    files = sorted(path for path in (output / "deliverable_files").rglob("preflight.txt") if path.is_file())
    delivery_valid = len(files) == 1 and files[0].read_text(encoding="utf-8").strip() == "R10.12-S1-STIRRUP-OK"
    provider_rows = [row for row in events if row.get("event") == "provider_response_metadata"]
    metadata_safe = all(set(row) <= {
        "event", "request_number", "endpoint", "requested_model", "response_model",
        "response_object", "request_id", "usage", "at",
    } for row in provider_rows)
    return {
        "completed_model_requests": len(completed), "code_exec_observed": "code_exec" in tool_calls,
        "finish_observed": "finish" in tool_calls,
        "tool_result_roundtrip_observed": len(completed) >= 2 and "code_exec" in tool_calls,
        "delivery_valid": delivery_valid, "provider_metadata_rows": len(provider_rows),
        "provider_metadata_safe": metadata_safe,
    }


def protocol_preflight(run_root: Path) -> list[StirrupSupplementProtocolProbeV1]:
    if not (run_root / "route_snapshot.json").is_file():
        raise FileNotFoundError("r10_12_s1_route_snapshot_missing")
    if (run_root / "frozen_panel.json").exists() or (run_root / "protocol_preflight/results.json").exists():
        raise FileExistsError("r10_12_s1_protocol_preflight_exists")
    probes = []
    for slot, model in SUPPLEMENT_MODELS.items():
        session = run_root / "protocol_preflight" / f"{slot}_{model}"
        attempts = 0
        status = "technical_failure"
        evidence = {"completed_model_requests": 0, "code_exec_observed": False,
                    "finish_observed": False, "tool_result_roundtrip_observed": False,
                    "delivery_valid": False, "provider_metadata_rows": 0,
                    "provider_metadata_safe": True}
        for number in (1, 2):
            attempts = number
            attempt = session / f"attempt_{number}"
            attempt.mkdir(parents=True)
            code, semantic = base._run_solver_attempt(
                _probe_case(run_root), attempt / "output", model, 12, PREFLIGHT_TIMEOUT_SECONDS,
            )
            if (attempt / "output/progress.jsonl").is_file():
                evidence = _probe_evidence(attempt / "output")
            passed = code == 0 and all([
                evidence["completed_model_requests"] >= 2, evidence["code_exec_observed"],
                evidence["finish_observed"], evidence["tool_result_roundtrip_observed"],
                evidence["delivery_valid"], evidence["provider_metadata_safe"],
                evidence["provider_metadata_rows"] >= 2,
            ])
            if passed:
                status = "passed"
                break
            if semantic:
                status = "protocol_or_semantic_failure"
                break
        probe = StirrupSupplementProtocolProbeV1(
            slot=slot, requested_model=model, status=status, attempt_count=attempts,
            completed_model_requests=evidence["completed_model_requests"],
            code_exec_observed=evidence["code_exec_observed"],
            finish_observed=evidence["finish_observed"],
            tool_result_roundtrip_observed=evidence["tool_result_roundtrip_observed"],
            delivery_valid=evidence["delivery_valid"],
            evidence_path=session.relative_to(run_root).as_posix(),
        )
        _write(session / "result.json", probe)
        probes.append(probe)
    _write(run_root / "protocol_preflight/results.json", probes)
    try:
        panel = freeze_supplement_panel(probes)
    except ValueError:
        _freeze_incomplete(run_root, "protocol_preflight", "one_or_more_fixed_routes_failed_protocol_gate")
        return probes
    _write(run_root / "frozen_panel.json", panel)
    return probes


def sync_judge_secret(run_root: Path) -> dict[str, Any]:
    target = run_root / "judge_secret_sync_receipt.json"
    if target.exists():
        raise FileExistsError("r10_12_s1_judge_secret_sync_exists")
    values = base._dotenv(base.TUZI_ENV)
    key = values.get("AGENT_API_KEY") or values.get("STIRRUP_OPENAI_API_KEY") or values.get("OPENAI_API_KEY")
    url = values.get("AGENT_BASE_URL") or values.get("STIRRUP_OPENAI_BASE_URL") or values.get("OPENAI_BASE_URL")
    if not key or not url:
        raise RuntimeError("r10_12_s1_local_tuzi_secret_missing")
    content = f"TUZI_API_KEY={key.strip()}\nTUZI_BASE_URL={url.strip()}\n"
    local_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    remote_path = "/home/huagosr/taskgenerator-secrets/eval_tuzi.env"
    check = base._ssh(base.HOST, f"test -f '{remote_path}' && sha256sum '{remote_path}' | cut -d' ' -f1 || true",
                      timeout=120, check=False)
    before_sha = check.stdout.strip() or None
    updated = before_sha != local_sha
    if updated:
        with tempfile.TemporaryDirectory(prefix="r10-12-s1-secret-") as temporary:
            secret_file = Path(temporary) / "eval_tuzi.env"
            secret_file.write_text(content, encoding="utf-8", newline="\n")
            upload = base._scp(str(secret_file), f"{base.HOST}:{remote_path}.r10_12_s1_tmp")
            if upload.returncode:
                raise RuntimeError("r10_12_s1_judge_secret_upload_failed")
        base._ssh(base.HOST, f"install -m 600 '{remote_path}.r10_12_s1_tmp' '{remote_path}' && rm -f '{remote_path}.r10_12_s1_tmp'",
                  timeout=120)
    after = base._ssh(base.HOST, f"stat -c '%a' '{remote_path}'; sha256sum '{remote_path}' | cut -d' ' -f1",
                      timeout=120)
    lines = [line.strip() for line in after.stdout.splitlines() if line.strip()]
    result = {
        "receipt_version": "r10.stirrup_supplement_judge_secret_sync.1",
        "updated": updated, "before_sha256": before_sha, "after_sha256": lines[-1] if lines else None,
        "mode": lines[0] if len(lines) >= 2 else None, "secret_material_recorded": False, "completed_at": _now(),
    }
    _write(target, result)
    if result["after_sha256"] != local_sha or result["mode"] != "600":
        _freeze_incomplete(run_root, "judge_secret_sync", "judge_secret_hash_or_mode_mismatch")
    return result


def judge_probe(run_root: Path) -> dict[str, Any]:
    if not (run_root / "frozen_panel.json").is_file() or not (run_root / "judge_secret_sync_receipt.json").is_file():
        raise RuntimeError("r10_12_s1_judge_probe_prerequisite_missing")
    root = run_root / "judge_probe"
    if root.exists():
        raise FileExistsError("r10_12_s1_judge_probe_exists")
    root.mkdir(parents=True)
    attempts = 0
    status, failure_type = "failed", None
    for number in (1, 2):
        attempts = number
        workspace = root / f"attempt_{number}"
        workspace.mkdir()
        (workspace / "candidate_task.md").write_text("Create a note containing exactly OK.\n", encoding="utf-8")
        (workspace / "reference_files").mkdir()
        submission = workspace / "anonymous_submission"
        submission.mkdir()
        (submission / "note.txt").write_text("OK\n", encoding="utf-8")
        _write(workspace / "rubric_items.json", [{
            "rubric_item_id": "probe_item", "max_score": 1,
            "criterion": "The submitted note contains exactly OK.",
        }])
        _write(workspace / "grade_schema.json", _strict_output_schema(IndependentRubricGradeDraftV1.model_json_schema()))
        _write(workspace / "grade_request.json", {"mode": "check", "provider": "tuzi"})
        shutil.copy2(ROOT / "Test/r10_12_remote_strict_grader.py", workspace)
        code, error = base._remote_grade_call(
            workspace, f"{base.REMOTE_ROOT}/{_campaign_id(run_root)}/judge_probe/attempt_{number}", "tuzi",
        )
        if code:
            remote_error = error
            docker_stderr = workspace / "docker_stderr.txt"
            if docker_stderr.is_file():
                remote_error = docker_stderr.read_text(encoding="utf-8", errors="replace")
            failure_type = _judge_probe_failure_type(remote_error)
            _write(workspace / "failure.json", {"type": failure_type, "detail": remote_error[-500:]})
            break
        try:
            draft = IndependentRubricGradeDraftV1.model_validate_json(
                (workspace / "grade.raw.json").read_text(encoding="utf-8")
            )
            if len(draft.assessments) != 1 or draft.assessments[0].rubric_item_id != "probe_item":
                raise ValueError("judge_probe_item_coverage")
            status = "passed"
            break
        except (FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            failure_type = type(exc).__name__
            _write(workspace / "failure.json", {"type": failure_type, "detail": str(exc)[:500]})
            if number == 2:
                break
    result = {
        "probe_version": "r10.stirrup_supplement_judge_probe.1",
        "judge_id": CHECK_JUDGE, "status": status, "attempt_count": attempts,
        "format_recoveries": max(0, attempts - 1), "failure_type": failure_type,
        "semantic_redraw": False, "completed_at": _now(),
    }
    _write(root / "result.json", result)
    if status != "passed":
        _freeze_incomplete(run_root, "judge_probe", "cross_judge_contract_probe_failed")
    return result


def _judge_probe_failure_type(error: str) -> str:
    normalized = error.casefold()
    if "401" in normalized and ("unauthorized" in normalized or "http error" in normalized):
        return "http_401_unauthorized"
    return "provider_or_transport_failure"


def solve(run_root: Path) -> list[StirrupSupplementSolverReceiptV1]:
    FrozenStirrupSupplementPanelV1.model_validate_json((run_root / "frozen_panel.json").read_text(encoding="utf-8"))
    judge = json.loads((run_root / "judge_probe/result.json").read_text(encoding="utf-8"))
    if judge.get("status") != "passed":
        raise RuntimeError("r10_12_s1_judge_gate_not_passed")
    hashes = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))["task_hashes"]
    receipts, recoveries = [], 0
    for row in assignments():
        session = run_root / "solver_sessions" / row["assignment_id"]
        if session.exists():
            raise FileExistsError(f"r10_12_s1_solver_session_exists:{row['assignment_id']}")
        session.mkdir(parents=True)
        attempts, delivery_status, delivery_sha = [], "missing", None
        for number in (1, 2):
            attempt = session / "attempts" / f"attempt_{number}"
            attempt.mkdir(parents=True)
            code, semantic = base._run_solver_attempt(
                run_root / "cases" / row["task_id"], attempt / "output", row["solver_id"],
                100, FORMAL_TIMEOUT_SECONDS,
            )
            status = base._validate_delivery(row["task_id"], base._delivery_root(attempt / "output")) if code == 0 else "missing"
            if code == 0 and status == "complete":
                state, delivery_status = "succeeded", "complete"
                delivery_sha = tree_sha256(base._delivery_root(attempt / "output"))
            elif not semantic:
                state = "technical_failure_before_semantic_turn"
            else:
                state, delivery_status = "semantic_or_delivery_failure", status
            attempts.append(StirrupSolverAttemptV1(
                attempt_number=number, state=state, semantic_phase_started=semantic,
                technical_recovery_of=1 if number == 2 else None,
                evidence_path=attempt.relative_to(run_root).as_posix(),
                failure_type=None if state == "succeeded" else ("subprocess_failure" if code else "invalid_delivery"),
            ))
            if state != "technical_failure_before_semantic_turn" or recoveries >= MAX_SOLVER_TECHNICAL_RECOVERIES:
                break
            recoveries += 1
        receipt = StirrupSupplementSolverReceiptV1(
            task_id=row["task_id"], solver_id=row["solver_id"], slot=row["slot"],
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
    receipt = StirrupSupplementSolverReceiptV1.model_validate_json((session / "receipt.json").read_text(encoding="utf-8"))
    success = next(row for row in receipt.attempts if row.state == "succeeded")
    return run_root / success.evidence_path / "output"


def _stage_grade(workspace: Path, run_root: Path, solver: dict[str, str], mode: str, provider: str) -> dict[str, str]:
    if workspace.exists():
        raise FileExistsError("r10_12_s1_grade_workspace_exists")
    workspace.mkdir(parents=True)
    task = base.GDPVAL_DATA / "tasks" / solver["task_id"]
    shutil.copy2(task / "prompt.txt", workspace / "candidate_task.md")
    shutil.copytree(task / "reference_files", workspace / "reference_files")
    shutil.copytree(base._delivery_root(_successful_output(run_root, solver["assignment_id"])),
                    workspace / "anonymous_submission")
    rubric = adapt_gdpval_rubric(base._binding(solver["task_id"]))
    _write(workspace / "rubric_items.json", [row.model_dump(mode="json") for row in rubric])
    _write(workspace / "grade_schema.json", _strict_output_schema(IndependentRubricGradeDraftV1.model_json_schema()))
    _write(workspace / "grade_request.json", {"mode": mode, "provider": provider})
    shutil.copy2(ROOT / "Test/r10_12_remote_strict_grader.py", workspace)
    return {
        "input_sha256": base._candidate_input_sha256(workspace),
        "rubric_sha256": canonical_json_sha256(rubric),
        "delivery_sha256": tree_sha256(workspace / "anonymous_submission"),
    }


def _grade_once(run_root: Path, session: Path, solver: dict[str, str], provider: str,
                judge_id: str, recovery_budget: dict[str, int]) -> IndependentRubricGradeV1:
    if session.exists():
        raise FileExistsError("r10_12_s1_grade_session_exists")
    session.mkdir(parents=True)
    attempt = 0
    while True:
        attempt += 1
        workspace = session / "attempts" / f"attempt_{attempt}"
        hashes = _stage_grade(workspace, run_root, solver, "check" if provider == "tuzi" else "primary", provider)
        code, error = base._remote_grade_call(
            workspace, f"{base.REMOTE_ROOT}/{_campaign_id(run_root)}/{session.name}/attempt_{attempt}", provider,
        )
        if code:
            _write(workspace / "failure.json", {"type": "provider_or_transport_failure", "detail": error[-500:]})
            raise ConnectionError("r10_12_s1_grade_provider_or_transport_failure")
        try:
            grade = base._finalize_grade(workspace, solver, hashes, judge_id)
            _write(session / "review.json", grade)
            return grade
        except (FileNotFoundError, json.JSONDecodeError, ValidationError) as exc:
            _write(workspace / "failure.json", {"type": type(exc).__name__, "detail": str(exc)[:500]})
            if recovery_budget["remaining"] <= 0:
                raise
            recovery_budget["remaining"] -= 1


def _delivery_only(criterion: str) -> bool:
    normalized = criterion.casefold()
    return normalized.startswith("delivers ") and any(ext in normalized for ext in (".xlsx", ".docx", ".pdf", ".pptx"))


def grade(run_root: Path) -> dict[str, Any]:
    if (run_root / "grading").exists() or (run_root / "summary.json").exists():
        raise FileExistsError("r10_12_s1_grading_exists")
    receipts = [StirrupSupplementSolverReceiptV1.model_validate(row) for row in json.loads(
        (run_root / "solver_receipts.json").read_text(encoding="utf-8")
    )]
    receipt_by = {(row.task_id, row.slot): row for row in receipts}
    specs = assignments()
    primary_budget = {"remaining": MAX_PRIMARY_FORMAT_RECOVERIES}
    check_budget = {"remaining": MAX_CHECK_FORMAT_RECOVERIES}
    primary: dict[tuple[str, str], IndependentRubricGradeV1] = {}
    checks: dict[tuple[str, str], IndependentRubricGradeV1] = {}
    for solver in specs:
        if receipt_by[(solver["task_id"], solver["slot"])].delivery_status != "complete":
            continue
        primary[(solver["task_id"], solver["slot"])] = _grade_once(
            run_root, run_root / "grading/primary" / solver["assignment_id"], solver,
            "deepseek_official", PRIMARY_JUDGE, primary_budget,
        )
    for solver in specs:
        key = (solver["task_id"], solver["slot"])
        if key not in SENTINELS or key not in primary:
            continue
        checks[key] = _grade_once(
            run_root, run_root / "grading/checks" / solver["assignment_id"], solver,
            "tuzi", CHECK_JUDGE, check_budget,
        )
    all_deliveries_valid = len(receipts) == 12 and all(row.delivery_status == "complete" for row in receipts)
    structural = len(primary) == sum(row.delivery_status == "complete" for row in receipts) and all(
        row.material_status == "complete" and row.total_score == sum(item.awarded for item in row.items)
        for row in primary.values()
    )
    sentinel_rows = []
    for key, check in checks.items():
        main = primary[key]
        main_items = {row.rubric_item_id: row for row in main.items}
        high = max(row.max_score for row in main.items)
        extreme = any(
            row.max_score == high and {row.awarded, main_items[row.rubric_item_id].awarded} == {0, high}
            for row in check.items
        )
        sentinel_rows.append({
            "task_id": key[0], "slot": key[1],
            "normalized_delta": round(abs(check.normalized_score - main.normalized_score), 6),
            "high_weight_extreme_conflict": extreme,
        })
    sentinel_acceptance = len(sentinel_rows) == 4 and all(
        row["normalized_delta"] <= .10 and not row["high_weight_extreme_conflict"] for row in sentinel_rows
    )
    means, task_scores = {}, {}
    for slot, model in SUPPLEMENT_MODELS.items():
        values = [primary[(task, slot)].normalized_score for task in base.TASKS if (task, slot) in primary]
        if len(values) == 3:
            means[model] = round(sum(values) / 3, 6)
    for task in base.TASKS:
        values = {model: primary[(task, slot)].normalized_score for slot, model in SUPPLEMENT_MODELS.items()
                  if (task, slot) in primary}
        if len(values) == 4:
            task_scores[task] = values
    professional_by_strong = {model: False for model in ("gpt-5.5", "gpt-5.6-sol")}
    for task in base.TASKS:
        lower = primary.get((task, "lower_anchor"))
        if lower is None:
            continue
        lower_items = {row.rubric_item_id: row for row in lower.items}
        rubric = {row.rubric_item_id: row for row in adapt_gdpval_rubric(base._binding(task))}
        for slot, model in (("strong_primary", "gpt-5.5"), ("strong_check", "gpt-5.6-sol")):
            strong = primary.get((task, slot))
            if strong and any(
                row.awarded > lower_items[row.rubric_item_id].awarded
                and not _delivery_only(rubric[row.rubric_item_id].criterion)
                for row in strong.items
            ):
                professional_by_strong[model] = True
    professional_gap = all(professional_by_strong.values())
    classification = classify_supplement_result(
        all_deliveries_valid=all_deliveries_valid,
        primary_structural_valid=structural,
        sentinel_acceptance=sentinel_acceptance,
        means=means,
        task_scores=task_scores,
        professional_item_gap_present=professional_gap,
    )
    summary = {
        "summary_version": "r10.stirrup_supplement_summary.1",
        "status": classification, "evidence_level": "provisional_llm_proxy",
        "solver_receipts": len(receipts), "all_deliveries_valid": all_deliveries_valid,
        "primary_grades_completed": len(primary), "primary_structural_valid": structural,
        "sentinel_grades_completed": len(checks), "sentinel_acceptance": sentinel_acceptance,
        "sentinels": sentinel_rows, "model_means": means, "task_scores": task_scores,
        "professional_item_gap_present": professional_gap,
        "professional_gap_by_strong_route": professional_by_strong,
        "model_identity_claim": False, "model_ranking_claim": False,
        "automatic_generator_feedback": False,
    }
    _write(run_root / "summary.json", summary)
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_supplement_receipt.1",
        "scope_sha256": canonical_json_sha256(scope), "status": classification,
        "solver_sessions": len(receipts), "primary_grades": len(primary), "check_grades": len(checks),
        "primary_format_recoveries": MAX_PRIMARY_FORMAT_RECOVERIES - primary_budget["remaining"],
        "check_format_recoveries": MAX_CHECK_FORMAT_RECOVERIES - check_budget["remaining"],
        "completed_at": _now(),
    })
    return summary


def _freeze_incomplete(run_root: Path, stage: str, reason: str) -> dict[str, Any]:
    target = run_root / "summary.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    summary = {
        "summary_version": "r10.stirrup_supplement_summary.1",
        "status": "incomplete", "evidence_level": stage, "stop_reason": reason,
        "formal_solver_started": (run_root / "solver_sessions").exists(),
        "model_identity_claim": False, "model_ranking_claim": False,
        "automatic_generator_feedback": False,
    }
    _write(target, summary)
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.stirrup_supplement_receipt.1",
        "scope_sha256": canonical_json_sha256(scope), "status": "incomplete",
        "stop_stage": stage, "stop_reason": reason, "completed_at": _now(),
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "prepare", "snapshot", "preflight", "sync-judge-secret", "judge-probe", "solve", "grade",
    ))
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    functions = {
        "prepare": prepare, "snapshot": snapshot_routes, "preflight": protocol_preflight,
        "sync-judge-secret": sync_judge_secret, "judge-probe": judge_probe,
        "solve": solve, "grade": grade,
    }
    result = functions[args.command](args.run_root)
    if isinstance(result, list):
        result = [row.model_dump(mode="json") if hasattr(row, "model_dump") else row for row in result]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
