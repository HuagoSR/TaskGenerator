"""Run the immutable R10.12-S1B four-route Stirrup calibration."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

import run_r10_12_stirrup_calibration as base
import run_r10_12_stirrup_supplement as s1
from r10_12_remote_strict_grader import MAX_TOTAL_CHARS, STRICT_SYSTEM, _extract
from run_r10_behavioral_pilot import CHATGPT_CODEX_STACK, _run_remote
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
    StrictGradePacketV1,
    StirrupSupplementSolverReceiptV1,
    classify_supplement_result,
)


RUN_ID = "r10_12_model_supplement_b_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
DIAGNOSTIC = ROOT / "artifacts/r10/r10_12_terra_transport_diagnostic_20260904"
S1_ROOT = ROOT / "artifacts/r10/r10_12_model_supplement_20260904"
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
FORMAL_TIMEOUT_SECONDS = 7200
MAX_SOLVER_RECOVERIES = 4
MAX_PRIMARY_FORMAT_RECOVERIES = 2
MAX_CHECK_FORMAT_RECOVERIES = 1
PRIMARY_JUDGE = "deepseek-v4-pro@official_api"
CHECK_JUDGE = "gpt-5.6-terra@chatgpt_codex"
SENTINELS = s1.SENTINELS


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    base._write(path, value)


def _sha(path: Path) -> str:
    return base._file_sha256(path)


def _freeze(run_root: Path, stage: str, reason: str) -> dict[str, Any]:
    if (run_root / "summary.json").exists():
        summary = json.loads((run_root / "summary.json").read_text(encoding="utf-8"))
    else:
        summary = {
            "summary_version": "r10.stirrup_supplement_b_summary.1", "status": "incomplete",
            "evidence_level": stage, "stop_reason": reason,
            "formal_solver_started": (run_root / "solver_sessions").exists(),
            "model_identity_claim": False, "model_ranking_claim": False,
            "automatic_generator_feedback": False,
        }
        _write(run_root / "summary.json", summary)
    receipt = run_root / "receipt.json"
    if not receipt.exists() and (run_root / "scope.json").is_file():
        solver_count = 0
        if (run_root / "solver_receipts.json").is_file():
            solver_count = len(json.loads((run_root / "solver_receipts.json").read_text(encoding="utf-8")))
        _write(receipt, {
            "receipt_version": "r10.stirrup_supplement_b_receipt.1",
            "scope_sha256": _sha(run_root / "scope.json"), "status": "incomplete",
            "stop_stage": summary.get("evidence_level", stage),
            "stop_reason": summary.get("stop_reason", reason), "solver_sessions": solver_count,
            "primary_provider_attempts": len(list((run_root / "grading/primary").glob("*/attempts/attempt_*"))),
            "primary_grades": len(list((run_root / "grading/primary").glob("*/review.json"))),
            "check_provider_attempts": len(list((run_root / "grading/checks").glob("*/attempts/attempt_*"))),
            "check_grades": len(list((run_root / "grading/checks").glob("*/review.json"))),
            "completed_at": _now(),
        })
    return summary


def assignments() -> list[dict[str, str]]:
    return s1.assignments()


def _delivery_only(criterion: str) -> bool:
    value = criterion.casefold()
    content_terms = ("analysis", "conclusion", "explain", "identify", "document", "support",
                     "calculate", "compare", "assess", "recommend", "rationale")
    file_terms = ("deliver", "file", ".xlsx", ".docx", ".pdf", ".pptx", "openable")
    return any(term in value for term in file_terms) and not any(term in value for term in content_terms)


def prepare(run_root: Path) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError(f"r10_12_s1b_run_root_exists:{run_root}")
    diagnostic = json.loads((DIAGNOSTIC / "summary.json").read_text(encoding="utf-8"))
    if diagnostic.get("selected_judge_transport") != CHECK_JUDGE:
        raise RuntimeError("r10_12_s1b_codex_judge_not_selected")
    hashes = {task: base._task_hashes(task) for task in base.TASKS}
    if hashes != base._r10_11_expected_hashes():
        raise ValueError("r10_12_s1b_r10_11_hash_drift")
    s1_scope = json.loads((S1_ROOT / "scope.json").read_text(encoding="utf-8"))
    if hashes != s1_scope["task_hashes"]:
        raise ValueError("r10_12_s1b_s1_hash_drift")
    evidence_files = [S1_ROOT / "route_snapshot.json", S1_ROOT / "protocol_preflight/results.json",
                      S1_ROOT / "frozen_panel.json"]
    for path in evidence_files:
        if not path.is_file():
            raise FileNotFoundError(f"r10_12_s1b_evidence_missing:{path.name}")
    for task in base.TASKS:
        base._stage_case(run_root / "cases" / task, task)
    item_classes = {}
    for task in base.TASKS:
        item_classes[task] = {
            row.rubric_item_id: "delivery_only" if _delivery_only(row.criterion) else "professional"
            for row in adapt_gdpval_rubric(base._binding(task))
        }
    scope = {
        "scope_version": "r10.stirrup_supplement_b_scope.1", "campaign_id": run_root.name,
        "created_at": _now(), "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True,
        ).stdout.strip(), "purpose": "fixed_four_route_formal_supplement",
        "provider": "tuzi_chat_completions", "endpoint": "/v1/chat/completions",
        "requested_panel": SUPPLEMENT_MODELS, "fallbacks": False, "solver_assignments": assignments(),
        "task_hashes": hashes, "selected_check_judge": CHECK_JUDGE,
        "diagnostic_summary_sha256": _sha(DIAGNOSTIC / "summary.json"),
        "s1_protocol_evidence": {path.relative_to(S1_ROOT).as_posix(): _sha(path) for path in evidence_files},
        "rubric_item_classes": item_classes,
        "solver": {"normal_sessions": 12, "serial": True, "max_turns": 100,
                   "context_window_tokens": 64000, "max_completion_tokens": 8192,
                   "attempt_timeout_seconds": FORMAL_TIMEOUT_SECONDS,
                   "campaign_technical_recovery_limit": MAX_SOLVER_RECOVERIES},
        "grading": {"primary": {"judge_id": PRIMARY_JUDGE, "normal": 12, "format_recoveries": 2},
                    "checks": {"judge_id": CHECK_JUDGE, "normal": 4, "format_recoveries": 1},
                    "pairwise": False, "holistic": False, "downward_audit": False},
        "model_identity_claim": False, "semantic_redraw": False,
        "automatic_generator_feedback": False,
    }
    _write(run_root / "scope.json", scope)
    _write(run_root / "dry_run.json", {
        "dry_run_version": "r10.stirrup_supplement_b_dry_run.1", "provider_calls": 0,
        "route_health_calls": 4, "solver_normal_sessions": 12, "solver_technical_recoveries": 4,
        "primary_normal": 12, "primary_format_recoveries": 2,
        "check_normal": 4, "check_format_recoveries": 1,
        "assignments": scope["solver_assignments"], "task_hashes": hashes,
        "e2b_template_build_id": "c9cf3369-49c8-4bff-8f81-8ad9ce9cc252",
        "output_directory": run_root.as_posix(),
    })
    return scope


def route_health(run_root: Path) -> dict[str, Any]:
    target = run_root / "route_health.json"
    if target.exists():
        raise FileExistsError("r10_12_s1b_route_health_exists")
    env, _ = base._solver_environment()
    url = env["AGENT_BASE_URL"].strip().rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    rows = []
    for slot, model in SUPPLEMENT_MODELS.items():
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly OK."}],
                "temperature": 0, "max_tokens": 64, "stream": False}
        request = urllib.request.Request(url + "/chat/completions",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
            "Authorization": f"Bearer {env['AGENT_API_KEY'].strip()}"}, method="POST")
        row = {"slot": slot, "requested_model": model, "endpoint": "/v1/chat/completions",
               "normal_call_count": 1, "retry_count": 0, "status": "failed"}
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                provider = json.loads(response.read().decode("utf-8"))
                content = provider["choices"][0]["message"].get("content")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty_route_health_content")
                usage = provider.get("usage") or {}
                row.update({"status": "passed", "http_status": response.status,
                            "response_model": provider.get("model"), "response_object": provider.get("object"),
                            "request_id": response.headers.get("x-request-id"),
                            "usage": {key: usage.get(key) for key in
                                      ("prompt_tokens", "completion_tokens", "total_tokens")}})
        except urllib.error.HTTPError as exc:
            row.update({"http_status": exc.code, "failure_type": "http_failure"})
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            row.update({"failure_type": type(exc).__name__})
        rows.append(row)
        if row["status"] != "passed":
            break
    result = {"health_version": "r10.stirrup_supplement_b_route_health.1", "rows": rows,
              "all_passed": len(rows) == 4 and all(row["status"] == "passed" for row in rows),
              "completed_at": _now()}
    _write(target, result)
    if not result["all_passed"]:
        _freeze(run_root, "route_health", "fixed_route_health_failed")
    return result


def _systemic_presemantic(attempt: Path) -> bool:
    text = (attempt / "stderr.txt").read_text(encoding="utf-8", errors="replace").casefold()
    return any(marker in text for marker in
               ("401", "403", "unauthorized", "forbidden", "model not found", "unknown model", "endpoint"))


def _solver_metadata(output: Path) -> tuple[str | None, int, list[str]]:
    progress = output / "progress.jsonl"
    if not progress.is_file():
        return None, 0, []
    events = [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines() if line]
    safe = [row for row in events if row.get("event") in
            {"provider_response_metadata", "model_request_completed"}]
    completed = [row for row in safe if row.get("event") == "model_request_completed"]
    tools = sorted({name for row in completed for name in row.get("tool_calls", [])})
    return canonical_json_sha256(safe), len(completed), tools


def solve(run_root: Path) -> list[StirrupSupplementSolverReceiptV1]:
    health = json.loads((run_root / "route_health.json").read_text(encoding="utf-8"))
    if not health.get("all_passed") or (run_root / "summary.json").exists():
        raise RuntimeError("r10_12_s1b_route_health_gate_failed")
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    receipts, recoveries = [], 0
    for row in assignments():
        session = run_root / "solver_sessions" / row["assignment_id"]
        if session.exists():
            raise FileExistsError(f"r10_12_s1b_solver_exists:{row['assignment_id']}")
        session.mkdir(parents=True)
        attempts, delivery_status, delivery_sha = [], "missing", None
        systemic = False
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
                systemic = _systemic_presemantic(attempt)
                state = "technical_failure_before_semantic_turn"
            else:
                state, delivery_status = "semantic_or_delivery_failure", status
            attempts.append(StirrupSolverAttemptV1(
                attempt_number=number, state=state, semantic_phase_started=semantic,
                technical_recovery_of=1 if number == 2 else None,
                evidence_path=attempt.relative_to(run_root).as_posix(),
                failure_type=None if state == "succeeded" else
                    ("systemic_provider_failure" if systemic else "solver_or_delivery_failure"),
            ))
            if state != "technical_failure_before_semantic_turn" or systemic or recoveries >= MAX_SOLVER_RECOVERIES:
                break
            recoveries += 1
        metadata_sha, completed_requests, tool_names = _solver_metadata(
            session / "attempts" / f"attempt_{len(attempts)}" / "output"
        )
        receipt = StirrupSupplementSolverReceiptV1(
            task_id=row["task_id"], solver_id=row["solver_id"], slot=row["slot"],
            input_sha256=scope["task_hashes"][row["task_id"]]["input_sha256"],
            rubric_sha256=scope["task_hashes"][row["task_id"]]["rubric_sha256"],
            delivery_status=delivery_status, delivery_sha256=delivery_sha,
            provider_metadata_sha256=metadata_sha, completed_model_requests=completed_requests,
            observed_tool_names=tool_names, attempts=attempts,
        )
        _write(session / "receipt.json", receipt)
        receipts.append(receipt)
        _write(run_root / "solver_receipts.json", receipts)
        if systemic:
            _freeze(run_root, "solver", "systemic_provider_failure_before_semantic_turn")
            break
    return receipts


def _successful_output(run_root: Path, assignment_id: str) -> Path:
    receipt = StirrupSupplementSolverReceiptV1.model_validate_json(
        (run_root / "solver_sessions" / assignment_id / "receipt.json").read_text(encoding="utf-8")
    )
    attempt = next(row for row in receipt.attempts if row.state == "succeeded")
    return run_root / attempt.evidence_path / "output"


def _materials(workspace: Path) -> str:
    files = [workspace / "candidate_task.md"]
    files += sorted(path for path in (workspace / "reference_files").rglob("*") if path.is_file())
    files += sorted(path for path in (workspace / "anonymous_submission").rglob("*") if path.is_file())
    parts, used = [], 0
    for path in files:
        text = _extract(path)
        available = MAX_TOTAL_CHARS - used
        if available <= 0:
            raise RuntimeError("r10_12_s1b_material_text_budget_exceeded")
        text = text[:available]
        parts.append(f"\n===== {path.relative_to(workspace).as_posix()} =====\n{text}")
        used += len(text)
    return "".join(parts)


def _stage_grade(run_root: Path, workspace: Path, solver: dict[str, str]) -> tuple[dict[str, str], str]:
    hashes = s1._stage_grade(workspace, run_root, solver, "primary", "deepseek_official")
    rubric = adapt_gdpval_rubric(base._binding(solver["task_id"]))
    packet = StrictGradePacketV1(
        task_id=solver["task_id"], strict_system=STRICT_SYSTEM,
        rubric_items=[row.model_dump(mode="json") for row in rubric],
        required_evidence_path_roots=["candidate_task.md", "reference_files/", "anonymous_submission/"],
        materials=_materials(workspace),
        output_schema=_strict_output_schema(IndependentRubricGradeDraftV1.model_json_schema()),
    )
    _write(workspace / "strict_grade_packet.json", packet)
    shutil.copy2(ROOT / "Test/r10_12_remote_packet_grader.py", workspace / "r10_12_remote_strict_grader.py")
    return hashes, packet.canonical_sha256()


def _grade_once(run_root: Path, session: Path, solver: dict[str, str], provider: str,
                judge_id: str, budget: dict[str, int], *, resume: bool = False) -> tuple[IndependentRubricGradeV1, str]:
    if session.exists() and not resume:
        raise FileExistsError("r10_12_s1b_grade_session_exists")
    session.mkdir(parents=True, exist_ok=resume)
    existing = sorted((session / "attempts").glob("attempt_*")) if (session / "attempts").exists() else []
    attempt = len(existing)
    if existing:
        if budget["remaining"] <= 0:
            raise RuntimeError("r10_12_s1b_format_recovery_budget_exhausted")
        budget["remaining"] -= 1
    while True:
        attempt += 1
        workspace = session / "attempts" / f"attempt_{attempt}"
        hashes, packet_sha = _stage_grade(run_root, workspace, solver)
        if provider == "deepseek_official":
            _write(workspace / "grade_request.json", {"provider": "deepseek_official"})
            code, error = base._remote_grade_call(
                workspace, f"{base.REMOTE_ROOT}/{run_root.name}/{session.name}/attempt_{attempt}", provider,
            )
        else:
            packet = json.loads((workspace / "strict_grade_packet.json").read_text(encoding="utf-8"))
            _write(workspace / "grade_schema.json", packet["output_schema"])
            (workspace / "TASK.md").write_text(
                "Read only strict_grade_packet.json. Apply strict_system to rubric_items and materials. "
                "Return exactly one JSON object matching grade_schema.json; do not inspect other files or add criteria.\n",
                encoding="utf-8",
            )
            code, _, error = _run_remote(
                host=base.HOST, remote=f"{base.REMOTE_ROOT}/{run_root.name}/{session.name}/attempt_{attempt}",
                local=workspace, stack=CHATGPT_CODEX_STACK, grade=True, image=base.IMAGE,
                codex_auth_dir=CODEX_AUTH_DIR, timeout_seconds=1800,
                codex_reasoning_effort="medium", model_override="gpt-5.6-terra",
            )
        if code:
            _write(workspace / "failure.json", {"type": "provider_or_transport_failure", "detail": error[-300:]})
            raise ConnectionError("r10_12_s1b_grade_provider_failure")
        try:
            grade = base._finalize_grade(workspace, solver, hashes, judge_id)
            _write(session / "review.json", grade)
            _write(session / "packet_receipt.json", {"strict_grade_packet_sha256": packet_sha})
            return grade, packet_sha
        except (FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            _write(workspace / "failure.json", {"type": type(exc).__name__, "detail": str(exc)[:300]})
            if budget["remaining"] <= 0:
                raise
            budget["remaining"] -= 1


def grade(run_root: Path, *, resume: bool = False) -> dict[str, Any]:
    if not resume and ((run_root / "grading").exists() or (run_root / "summary.json").exists()):
        raise FileExistsError("r10_12_s1b_grading_or_summary_exists")
    receipts = [StirrupSupplementSolverReceiptV1.model_validate(row) for row in json.loads(
        (run_root / "solver_receipts.json").read_text(encoding="utf-8")
    )]
    by_receipt = {(row.task_id, row.slot): row for row in receipts}
    primary_budget, check_budget = {"remaining": 2}, {"remaining": 1}
    primary, checks, primary_packet = {}, {}, {}
    try:
        for solver in assignments():
            key = (solver["task_id"], solver["slot"])
            if key not in by_receipt or by_receipt[key].delivery_status != "complete":
                continue
            session = run_root / "grading/primary" / solver["assignment_id"]
            if (session / "review.json").is_file():
                grade_value = IndependentRubricGradeV1.model_validate_json(
                    (session / "review.json").read_text(encoding="utf-8")
                )
                packet_sha = json.loads((session / "packet_receipt.json").read_text(encoding="utf-8"))[
                    "strict_grade_packet_sha256"
                ]
            else:
                grade_value, packet_sha = _grade_once(
                    run_root, session, solver, "deepseek_official", PRIMARY_JUDGE,
                    primary_budget, resume=resume and session.exists(),
                )
            primary[key], primary_packet[key] = grade_value, packet_sha
        for solver in assignments():
            key = (solver["task_id"], solver["slot"])
            if key not in SENTINELS or key not in primary:
                continue
            session = run_root / "grading/checks" / solver["assignment_id"]
            if (session / "review.json").is_file():
                grade_value = IndependentRubricGradeV1.model_validate_json(
                    (session / "review.json").read_text(encoding="utf-8")
                )
                packet_sha = json.loads((session / "packet_receipt.json").read_text(encoding="utf-8"))[
                    "strict_grade_packet_sha256"
                ]
            else:
                grade_value, packet_sha = _grade_once(
                    run_root, session, solver, "codex", CHECK_JUDGE,
                    check_budget, resume=resume and session.exists(),
                )
            if packet_sha != primary_packet[key]:
                raise ValueError("r10_12_s1b_cross_judge_packet_drift")
            checks[key] = grade_value
    except Exception as exc:
        return _freeze(run_root, "grading", f"{type(exc).__name__}:{str(exc)[:120]}")
    all_deliveries = len(receipts) == 12 and all(row.delivery_status == "complete" for row in receipts)
    structural = len(primary) == sum(row.delivery_status == "complete" for row in receipts) and all(
        row.material_status == "complete" and row.total_score == sum(item.awarded for item in row.items)
        for row in primary.values()
    )
    sentinel_rows = []
    for key, check in checks.items():
        main = primary[key]
        main_items = {row.rubric_item_id: row for row in main.items}
        high = max(row.max_score for row in main.items)
        extreme = any(row.max_score == high and
                      {row.awarded, main_items[row.rubric_item_id].awarded} == {0, high} for row in check.items)
        sentinel_rows.append({"task_id": key[0], "slot": key[1],
            "normalized_delta": round(abs(check.normalized_score - main.normalized_score), 6),
            "high_weight_extreme_conflict": extreme})
    sentinel_ok = len(sentinel_rows) == 4 and all(
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
    item_classes = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))["rubric_item_classes"]
    professional = {model: False for model in ("gpt-5.5", "gpt-5.6-sol")}
    for task in base.TASKS:
        lower = primary.get((task, "lower_anchor"))
        if lower is None:
            continue
        lower_items = {row.rubric_item_id: row for row in lower.items}
        for slot, model in (("strong_primary", "gpt-5.5"), ("strong_check", "gpt-5.6-sol")):
            strong = primary.get((task, slot))
            if strong and any(item_classes[task][row.rubric_item_id] == "professional" and
                              row.awarded > lower_items[row.rubric_item_id].awarded for row in strong.items):
                professional[model] = True
    classification = classify_supplement_result(
        all_deliveries_valid=all_deliveries, primary_structural_valid=structural,
        sentinel_acceptance=sentinel_ok, means=means, task_scores=task_scores,
        professional_item_gap_present=all(professional.values()),
    )
    summary = {"summary_version": "r10.stirrup_supplement_b_summary.1", "status": classification,
        "evidence_level": "provisional_llm_proxy", "solver_receipts": len(receipts),
        "all_deliveries_valid": all_deliveries, "primary_grades_completed": len(primary),
        "primary_structural_valid": structural, "sentinel_grades_completed": len(checks),
        "sentinel_acceptance": sentinel_ok, "sentinels": sentinel_rows,
        "model_means": means, "task_scores": task_scores,
        "professional_gap_by_strong_route": professional,
        "model_identity_claim": False, "model_ranking_claim": False,
        "automatic_generator_feedback": False}
    _write(run_root / "summary.json", summary)
    _write(run_root / "receipt.json", {"receipt_version": "r10.stirrup_supplement_b_receipt.1",
        "scope_sha256": _sha(run_root / "scope.json"), "status": classification,
        "solver_sessions": len(receipts), "primary_grades": len(primary), "check_grades": len(checks),
        "primary_format_recoveries": 2 - primary_budget["remaining"],
        "check_format_recoveries": 1 - check_budget["remaining"], "completed_at": _now()})
    return summary


def recover_grade(run_root: Path) -> dict[str, Any]:
    summary_path = run_root / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError("r10_12_s1b_recovery_summary_missing")
    previous = json.loads(summary_path.read_text(encoding="utf-8"))
    if previous.get("stop_reason") != "ValueError:independent_grade_rubric_coverage_mismatch":
        raise RuntimeError("r10_12_s1b_recovery_not_authorized_for_failure")
    archived = run_root / "controller_failure_summary.json"
    if archived.exists():
        raise FileExistsError("r10_12_s1b_controller_failure_already_archived")
    summary_path.replace(archived)
    _write(run_root / "scope_amendment.json", {
        "amendment_version": "r10.stirrup_supplement_b_scope_amendment.1",
        "original_scope_sha256": _sha(run_root / "scope.json"),
        "controller_failure_summary_sha256": _sha(archived),
        "reason": "controller_omitted_rubric_coverage_mismatch_from_pure_format_recovery",
        "provider_input_changed": False, "semantic_prompt_changed": False,
        "completed_reviews_reused": True, "format_recovery_authorized": True,
        "recorded_at": _now(),
    })
    return grade(run_root, resume=True)


def closeout(run_root: Path) -> dict[str, Any]:
    summary = json.loads((run_root / "summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "incomplete":
        raise RuntimeError("r10_12_s1b_closeout_requires_incomplete")
    return _freeze(run_root, summary.get("evidence_level", "unknown"), summary.get("stop_reason", "unknown"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "health", "solve", "grade", "recover-grade", "closeout"))
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    result = {"prepare": prepare, "health": route_health, "solve": solve,
              "grade": grade, "recover-grade": recover_grade, "closeout": closeout}[args.command](args.run_root)
    if isinstance(result, list):
        result = [row.model_dump(mode="json") for row in result]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
