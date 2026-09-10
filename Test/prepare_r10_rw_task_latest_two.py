"""Prepare the two latest R10 candidate packages for legacy rw-task diagnostics.

This is deliberately separate from task production.  It derives a candidate-only
GDPval-like input batch, records immutable source hashes, and can make four small
compatibility probes.  It never runs a task, grades a task, or starts E2B.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RW_TASK_ROOT = ROOT.parent / "rw-task"
DEFAULT_ROOT = ROOT / "artifacts/r10/r10_rw_task_latest_two_20260911"
SOURCE_ROOT = ROOT / "artifacts/r10/r10_task_factory_quality_development_v1_20260910_v2/cases"
ADAPTER_VERSION = "r10.legacy_rw_task_adapter.1"
MODELS = ("gpt-5.6-terra", "gemini-3.5-flash-lite", "gpt-5.4-mini")
GRADER_MODEL = "gemini-3-pro-preview"

CASES = (
    {
        "source": "r10_task_factory_quality_development_v1_20260910_v2_quality_procurement_price_02",
        "target": "Task_procurement_price_02",
        "task_id": "r10_procurement_price_02_legacy_rw_task",
        "expected_max": 18,
    },
    {
        "source": "r10_task_factory_quality_development_v1_20260910_v2_quality_audit_reliability_02",
        "target": "Task_audit_reliability_02",
        "task_id": "r10_audit_reliability_02_legacy_rw_task",
        "expected_max": 25,
    },
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise ValueError(f"unsafe_relative_path:{value}")
    return path.as_posix()


def _criterion_text(row: dict[str, Any]) -> str:
    sections = (
        ("Requirement", row.get("requirement")),
        ("Full-credit condition", row.get("full_credit_condition")),
        ("Applicability", row.get("applicability")),
        ("Acceptable alternatives", row.get("acceptable_alternatives")),
        ("Tolerance", row.get("tolerance")),
        ("Verification", row.get("verification")),
    )
    return "\n".join(f"{name}: {value}" for name, value in sections if str(value or "").strip())


def _legacy_rubric(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int]:
    raw = source.get("rubric_json")
    if not isinstance(raw, str):
        raise ValueError("source_rubric_json_string_required")
    criteria = json.loads(raw)
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("source_atomic_rubric_list_required")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    text_rows: list[str] = []
    for original in criteria:
        if not isinstance(original, dict):
            raise ValueError("source_atomic_rubric_row_required")
        criterion_id = str(original.get("criterion_id") or "").strip()
        points = original.get("max_points")
        if not criterion_id or criterion_id in seen or isinstance(points, bool) or not isinstance(points, int) or points <= 0:
            raise ValueError(f"source_atomic_rubric_invalid:{criterion_id}")
        seen.add(criterion_id)
        converted = dict(original)
        converted.update(
            score=points,
            criterion=_criterion_text(original),
            required=None,
            rubric_item_id=criterion_id,
            author_type="model",
            tags=["outcome"],
        )
        result.append(converted)
        text_rows.append(f"[+{points}] {converted['criterion']}")
    return result, "\n\n".join(text_rows), sum(row["score"] for row in result)


def _candidate_row(source: dict[str, Any], case: dict[str, Any]) -> tuple[dict[str, Any], int]:
    references = source.get("reference_files")
    deliverables = source.get("deliverable_files")
    if not isinstance(references, list) or not isinstance(deliverables, list):
        raise ValueError("source_paths_list_required")
    legacy_rubric, rubric_text, total = _legacy_rubric(source)
    output = {
        key: source[key]
        for key in ("title", "sector", "occupation", "prompt")
        if key in source
    }
    output.update(
        task_id=case["task_id"],
        reference_files=[_safe_relative(str(item)) for item in references],
        deliverable_files=[_safe_relative(str(item)) for item in deliverables],
        rubric=rubric_text,
        rubric_json=json.dumps(legacy_rubric, ensure_ascii=False),
    )
    return output, total


def _validate_case(case_root: Path, expected: int) -> dict[str, Any]:
    row_path = case_root / "dataset_row.json"
    row = _read_json(row_path)
    refs = row.get("reference_files")
    deliveries = row.get("deliverable_files")
    if not isinstance(refs, list) or not isinstance(deliveries, list):
        raise ValueError("legacy_paths_list_required")
    missing = [path for path in refs if not (case_root / _safe_relative(str(path))).is_file()]
    if missing:
        raise ValueError(f"reference_files_missing:{','.join(missing)}")
    delivery_root = case_root / "deliverable_files"
    if not delivery_root.is_dir() or any(path.is_file() for path in delivery_root.rglob("*")):
        raise ValueError("candidate_delivery_directory_not_empty")
    data = json.loads(str(row["rubric_json"]))
    if not isinstance(data, list):
        raise ValueError("legacy_rubric_list_required")
    ids = [str(item.get("rubric_item_id") or "") for item in data if isinstance(item, dict)]
    total = sum(item.get("score", 0) for item in data if isinstance(item, dict) and isinstance(item.get("score"), int))
    if not ids or len(ids) != len(set(ids)) or total != expected:
        raise ValueError(f"legacy_rubric_invalid:total={total}:expected={expected}")
    prompt = str(row.get("prompt") or "")
    absent = [PurePosixPath(path).name for path in deliveries if PurePosixPath(path).name not in prompt]
    if absent:
        raise ValueError(f"deliverable_not_named_in_prompt:{','.join(absent)}")
    unexpected = sorted(path.name for path in case_root.iterdir() if path.name not in {"dataset_row.json", "reference_files", "deliverable_files"})
    if unexpected:
        raise ValueError(f"unexpected_candidate_files:{','.join(unexpected)}")
    return {
        "task_id": row["task_id"], "reference_count": len(refs), "deliverable_count": len(deliveries),
        "rubric_count": len(data), "max_score": total, "row_sha256": _sha256(row_path),
        "candidate_file_hashes": _file_hashes(case_root),
    }


def _run_plan(output_root: Path) -> dict[str, Any]:
    batch = output_root / "input/batch_run_r10_latest_two"
    python = r"D:\miniconda3\envs\real-world-task\python.exe"
    entries = []
    for model in MODELS:
        output = output_root / "planned_runs" / model
        entries.append({
            "model": model,
            "solver_command": [python, "-m", "bench_standalone.stirrup_batch", str(batch), "--output", str(output), "-w", "1", "--model", model, "--e2b-template", "rw-task-sandbox:stable"],
            "grader_command": [python, "-m", "bench_standalone.grade_deliverables", str(output), "--strictness", "strict", "--out-dir", str(output_root / "planned_grades" / model)],
        })
    return {"runner": "legacy_rw_task", "concurrency": 1, "e2b_template": "rw-task-sandbox:stable", "models": entries,
            "note": "Commands are planned only. This preparation scope must not execute solver or grader runs."}


def prepare(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError("legacy_rw_task_prepare_root_exists")
    batch = output_root / "input/batch_run_r10_latest_two"
    manifest_cases = []
    for case in CASES:
        package = SOURCE_ROOT / case["source"] / "package"
        source_row_path = package / "dataset_row.json"
        source_row = _read_json(source_row_path)
        target = batch / case["target"]
        target.mkdir(parents=True)
        row, source_total = _candidate_row(source_row, case)
        if source_total != case["expected_max"]:
            raise ValueError(f"source_max_mismatch:{case['target']}:{source_total}")
        source_refs = package / "reference_files"
        if not source_refs.is_dir():
            raise FileNotFoundError(f"source_references_missing:{source_refs}")
        shutil.copytree(source_refs, target / "reference_files")
        (target / "deliverable_files").mkdir()
        _write_json(target / "dataset_row.json", row)
        validation = _validate_case(target, case["expected_max"])
        manifest_cases.append({
            "target": case["target"], "source_package": str(package), "source_dataset_row_sha256": _sha256(source_row_path),
            "source_reference_hashes": _file_hashes(source_refs), "validation": validation,
        })
    scope = {
        "scope_version": "r10.legacy_rw_task_prepare_scope.1", "created_at": _now(), "adapter_version": ADAPTER_VERSION,
        "purpose": "prepare_only_legacy_rw_task_diagnostic", "models": list(MODELS), "grader_model": GRADER_MODEL,
        "probe_budget": {"requests": 4, "per_request_timeout_seconds": 60, "max_output_tokens": 128, "retries": 0, "e2b": "not_started"},
        "cases": manifest_cases,
    }
    _write_json(output_root / "scope.json", scope)
    _write_json(output_root / "validation.json", {"passed": True, "cases": [case["validation"] for case in manifest_cases]})
    _write_json(output_root / "run_plan.json", _run_plan(output_root))
    return status(output_root)


def _dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _request(url: str, key: str, body: dict[str, Any], timeout: int) -> tuple[int, dict[str, Any], float]:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return response.status, json.loads(raw.decode("utf-8")), round(time.monotonic() - started, 3)


def _model_catalog(base_url: str, key: str, wanted: set[str]) -> list[dict[str, Any]]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.loads(response.read().decode("utf-8")).get("data", [])
    return [{field: row.get(field) for field in ("id", "owned_by", "supported_endpoint_types")} for row in rows if isinstance(row, dict) and row.get("id") in wanted]


def _solver_probe(model: str, base_url: str, key: str) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Call the supplied no-op function exactly once with status equal to ok."}],
        "tools": [{"type": "function", "function": {"name": "record_ready", "description": "No-op compatibility probe.", "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["ok"]}}, "required": ["status"], "additionalProperties": False}}}],
        "tool_choice": {"type": "function", "function": {"name": "record_ready"}},
        "max_completion_tokens": 128,
    }
    result: dict[str, Any] = {"model": model, "kind": "solver_tool_call", "endpoint": "chat_completions"}
    try:
        status_code, response, elapsed = _request(f"{base_url.rstrip('/')}/chat/completions", key, body, 60)
        message = ((response.get("choices") or [{}])[0].get("message") or {}) if isinstance(response, dict) else {}
        calls = message.get("tool_calls") if isinstance(message, dict) else None
        valid = isinstance(calls, list) and len(calls) == 1 and ((calls[0].get("function") or {}).get("name") == "record_ready")
        result.update(status="pass" if valid else "failed", http_status=status_code, elapsed_seconds=elapsed,
                      finish_reason=((response.get("choices") or [{}])[0].get("finish_reason")), tool_call_valid=valid,
                      usage=response.get("usage") if isinstance(response, dict) else None)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
        result.update(status="failed", error=f"{type(error).__name__}:{error}")
    return result


def _grader_probe(base_url: str, key: str) -> dict[str, Any]:
    body = {
        "model": GRADER_MODEL,
        "messages": [
            {"role": "system", "content": "Return only valid JSON with keys total_score, max_possible_score, per_criterion, grading_notes."},
            {"role": "user", "content": "Return a one-row score report for a synthetic one-point criterion."},
        ],
        "temperature": 0.4,
        "max_tokens": 128,
    }
    result: dict[str, Any] = {"model": GRADER_MODEL, "kind": "legacy_grader_json", "endpoint": "chat_completions"}
    try:
        status_code, response, elapsed = _request(f"{base_url.rstrip('/')}/chat/completions", key, body, 60)
        raw = str(((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        parsed = json.loads(raw)
        valid = isinstance(parsed, dict) and {"total_score", "max_possible_score", "per_criterion", "grading_notes"}.issubset(parsed)
        result.update(status="pass" if valid else "failed", http_status=status_code, elapsed_seconds=elapsed,
                      finish_reason=((response.get("choices") or [{}])[0].get("finish_reason")), json_valid=valid,
                      usage=response.get("usage") if isinstance(response, dict) else None)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
        result.update(status="failed", error=f"{type(error).__name__}:{error}")
    return result


def probe(output_root: Path) -> dict[str, Any]:
    scope = _read_json(output_root / "scope.json")
    receipt_path = output_root / "compatibility_probe/receipt.json"
    if receipt_path.exists():
        raise FileExistsError("compatibility_probe_already_recorded")
    env = _dotenv(RW_TASK_ROOT / ".env")
    required = ("AGENT_API_KEY", "AGENT_BASE_URL", "GRADER_API_KEY", "GRADER_BASE_URL")
    if any(not env.get(name) for name in required):
        raise ValueError("compatibility_probe_credentials_missing")
    catalog = {
        "solver": _model_catalog(env["AGENT_BASE_URL"], env["AGENT_API_KEY"], set(MODELS)),
        "grader": _model_catalog(env["GRADER_BASE_URL"], env["GRADER_API_KEY"], {GRADER_MODEL}),
    }
    receipt: dict[str, Any] = {"scope_sha256": _sha256(output_root / "scope.json"), "started_at": _now(), "budget": scope["probe_budget"], "catalog": catalog, "attempts": []}
    _write_json(receipt_path, receipt)
    for model in MODELS:
        receipt["attempts"].append(_solver_probe(model, env["AGENT_BASE_URL"], env["AGENT_API_KEY"]))
        _write_json(receipt_path, receipt)
    receipt["attempts"].append(_grader_probe(env["GRADER_BASE_URL"], env["GRADER_API_KEY"]))
    solver_ok = [item["model"] for item in receipt["attempts"] if item["kind"] == "solver_tool_call" and item["status"] == "pass"]
    grader_ok = any(item["kind"] == "legacy_grader_json" and item["status"] == "pass" for item in receipt["attempts"])
    receipt.update(completed_at=_now(), solver_models_ready=solver_ok, grader_ready=grader_ok,
                   legacy_rw_task_ready=bool(solver_ok) and grader_ok)
    _write_json(receipt_path, receipt)
    return receipt


def status(output_root: Path) -> dict[str, Any]:
    scope = _read_json(output_root / "scope.json")
    validation = _read_json(output_root / "validation.json")
    receipt_path = output_root / "compatibility_probe/receipt.json"
    receipt = _read_json(receipt_path) if receipt_path.exists() else None
    return {"purpose": scope["purpose"], "adapter_version": scope["adapter_version"], "validation_passed": validation.get("passed") is True,
            "cases": validation.get("cases"), "probe_status": None if receipt is None else receipt.get("legacy_rw_task_ready"),
            "ready_models": [] if receipt is None else receipt.get("solver_models_ready", []),
            "grader_ready": None if receipt is None else receipt.get("grader_ready"), "run_plan": str(output_root / "run_plan.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "probe", "status"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.output_root.resolve()
    if args.action == "prepare":
        result = prepare(root)
    elif args.action == "probe":
        result = probe(root)
    else:
        result = status(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
