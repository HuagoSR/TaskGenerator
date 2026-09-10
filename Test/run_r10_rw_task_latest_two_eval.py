"""Run the prepared R10 latest-two packages through legacy rw-task diagnostically.

This controller owns only an ignored execution scope.  It deliberately leaves
the legacy rw-task runner and grader unchanged, and never treats their integer
scores as the formal atomic-rubric result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RW_TASK = ROOT.parent / "rw-task"
PREPARED = ROOT / "artifacts/r10/r10_rw_task_latest_two_20260911"
DEFAULT_SCOPE = ROOT / "artifacts/r10/r10_rw_task_latest_two_eval_v1_20260911"
PYTHON = Path(r"D:\miniconda3\envs\real-world-task\python.exe")
MODELS = ("gpt-5.6-terra", "gemini-3.5-flash-lite", "gpt-5.4-mini")
TEMPLATE = "rw-task-sandbox:stable"
SOLVER_SECONDS = 30 * 60
SCOPE_SECONDS = 6 * 60 * 60
GRADER_MODEL = "gemini-3-pro-preview"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_relative(value: str) -> PurePosixPath:
    result = PurePosixPath(value)
    if result.is_absolute() or ".." in result.parts or not result.parts:
        raise ValueError(f"unsafe_relative_path:{value}")
    return result


def _env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("\"").strip("'")
    return result


def _legacy_fingerprints() -> dict[str, str]:
    files = (
        RW_TASK / "bench_standalone/stirrup_batch.py",
        RW_TASK / "bench_standalone/grade_deliverables.py",
        RW_TASK / "bench_standalone/openai_json.py",
    )
    return {str(path.relative_to(RW_TASK)).replace("\\", "/"): _hash(path) for path in files}


def _prepared_cases() -> list[dict[str, Any]]:
    status = _read(PREPARED / "validation.json")
    probe = _read(PREPARED / "compatibility_probe/receipt.json")
    if not status.get("passed") or not probe.get("grader_ready"):
        raise ValueError("prepared_input_or_grader_not_ready")
    if set(probe.get("solver_models_ready") or []) != set(MODELS):
        raise ValueError("prepared_solver_probe_not_complete")
    root = PREPARED / "input/batch_run_r10_latest_two"
    found = {path.name: path for path in root.iterdir() if path.is_dir() and (path / "dataset_row.json").is_file()}
    expected = ("Task_procurement_price_02", "Task_audit_reliability_02")
    if set(found) != set(expected):
        raise ValueError(f"prepared_case_set_invalid:{sorted(found)}")
    cases: list[dict[str, Any]] = []
    for name in expected:
        directory = found[name]
        row = _read(directory / "dataset_row.json")
        output_paths = row.get("deliverable_files")
        refs = row.get("reference_files")
        if not isinstance(output_paths, list) or not isinstance(refs, list) or len(output_paths) != 2:
            raise ValueError(f"prepared_contract_invalid:{name}")
        if sum(item.get("score", 0) for item in json.loads(row["rubric_json"])) not in (18, 25):
            raise ValueError(f"prepared_legacy_score_invalid:{name}")
        cases.append({
            "case_name": name,
            "task_id": row["task_id"],
            "source_directory": str(directory),
            "dataset_row_sha256": _hash(directory / "dataset_row.json"),
            "expected_deliverables": output_paths,
            "reference_files": refs,
        })
    return cases


def _template_build_id() -> str:
    env = _env(RW_TASK / ".env")
    if not env.get("E2B_API_KEY"):
        raise ValueError("e2b_key_missing")
    old = os.environ.get("E2B_API_KEY")
    os.environ["E2B_API_KEY"] = env["E2B_API_KEY"]
    try:
        from e2b import Template
        stable = [tag for tag in Template.get_tags("rw-task-sandbox") if getattr(tag, "tag", None) == "stable"]
        if len(stable) != 1 or not getattr(stable[0], "build_id", None):
            raise ValueError("e2b_stable_template_not_unique")
        return str(stable[0].build_id)
    finally:
        if old is None:
            os.environ.pop("E2B_API_KEY", None)
        else:
            os.environ["E2B_API_KEY"] = old


def _receipt_path(scope: Path) -> Path:
    return scope / "receipt.json"


def prepare(scope: Path) -> None:
    if scope.exists():
        raise FileExistsError(f"scope_exists:{scope}")
    if not PYTHON.is_file() or not RW_TASK.is_dir() or not PREPARED.is_dir():
        raise FileNotFoundError("required_environment_or_prepared_input_missing")
    cases = _prepared_cases()
    cells: list[dict[str, Any]] = []
    for model in MODELS:
        for case in cases:
            cell_id = f"{model}__{case['case_name']}"
            input_root = scope / "inputs" / cell_id / "batch"
            source = Path(case["source_directory"])
            target = input_root / case["case_name"]
            shutil.copytree(source, target)
            for file in target.rglob("*"):
                if file.is_file():
                    file.chmod(stat.S_IREAD)
            cells.append({
                "cell_id": cell_id,
                "model": model,
                "case_name": case["case_name"],
                "task_id": case["task_id"],
                "input_root": str(input_root),
                "input_case": str(target),
                "expected_deliverables": case["expected_deliverables"],
                "reference_files": case["reference_files"],
                "source_dataset_row_sha256": case["dataset_row_sha256"],
                "state": "pending",
            })
    manifest = {
        "scope_id": "r10_rw_task_latest_two_eval_v1_20260911",
        "purpose": "legacy_rw_task_diagnostic_only",
        "created_at": _now(),
        "prepared_scope_sha256": _hash(PREPARED / "scope.json"),
        "prepared_validation_sha256": _hash(PREPARED / "validation.json"),
        "prepared_probe_receipt_sha256": _hash(PREPARED / "compatibility_probe/receipt.json"),
        "legacy_sources": _legacy_fingerprints(),
        "python": str(PYTHON),
        "python_version": sys.version,
        "solver_models": list(MODELS),
        "grader_model": GRADER_MODEL,
        "route": "Tuzi OpenAI Chat Completions",
        "e2b_template": TEMPLATE,
        "e2b_build_id": _template_build_id(),
        "limits": {"scope_seconds": SCOPE_SECONDS, "solver_seconds": SOLVER_SECONDS, "concurrency": 1},
        "cells": cells,
        "legacy_scoring": {"strictness": "strict", "preserve_default_retries": True, "preserve_default_downward_audit": True},
    }
    _write(scope / "manifest.json", manifest)
    _write(_receipt_path(scope), {"scope_id": manifest["scope_id"], "state": "prepared", "created_at": _now(), "events": [], "cells": cells})
    _write(scope / "README.json", {"label": "legacy rw-task diagnostic only", "formal_atomic_rubric_score": "not_produced"})
    print(json.dumps({"scope": str(scope), "state": "prepared", "cells": len(cells)}, ensure_ascii=False))


def _terminate_tree(process: subprocess.Popen[str]) -> str:
    if process.poll() is not None:
        return "process_already_exited"
    try:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, text=True, timeout=30)
        return "local_process_tree_terminated; remote_e2b_cleanup_unknown"
    except Exception as error:
        process.kill()
        return f"local_process_killed_after_taskkill_error:{type(error).__name__}; remote_e2b_cleanup_unknown"


def _run(command: list[str], *, cwd: Path, log: Path, deadline: float) -> tuple[int | None, str | None]:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8", buffering=1) as fh:
        process = subprocess.Popen(command, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, text=True, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        while process.poll() is None:
            if time.monotonic() >= deadline:
                return None, _terminate_tree(process)
            time.sleep(1)
        return process.returncode, None


def _structural_validity(cell: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    nested_runs = [path for path in run_dir.glob("run_*") if path.is_dir()]
    if not (run_dir / "dataset_row.json").is_file():
        if len(nested_runs) != 1:
            return {"valid": False, "reason": "missing_or_ambiguous_output_run_directory"}
        run_dir = nested_runs[0]
    row_path = run_dir / "dataset_row.json"
    if not row_path.is_file():
        return {"valid": False, "reason": "missing_output_dataset_row"}
    row = _read(row_path)
    delivered = row.get("deliverable_files")
    if not isinstance(delivered, list) or len(delivered) != 2:
        return {"valid": False, "reason": "unexpected_deliverable_count"}
    expected = sorted(PurePosixPath(path).name for path in cell["expected_deliverables"])
    files: list[Path] = []
    for value in delivered:
        if not isinstance(value, str):
            return {"valid": False, "reason": "non_string_deliverable_path"}
        relative = _safe_relative(value)
        if not relative.parts or relative.parts[0] != "deliverable_files":
            return {"valid": False, "reason": "deliverable_outside_output_root"}
        path = run_dir.joinpath(*relative.parts)
        if not path.is_file():
            return {"valid": False, "reason": f"missing_deliverable:{value}"}
        files.append(path)
    if sorted(path.name for path in files) != expected:
        return {"valid": False, "reason": "deliverable_names_do_not_match_contract"}
    refs = { _hash(run_dir / rel) for rel in cell["reference_files"] if (run_dir / rel).is_file() }
    details: list[dict[str, str]] = []
    for path in files:
        if _hash(path) in refs:
            return {"valid": False, "reason": f"reference_file_reused:{path.name}"}
        if path.suffix.lower() not in {".docx", ".xlsx"}:
            return {"valid": False, "reason": f"unexpected_type:{path.name}"}
        try:
            with zipfile.ZipFile(path) as archive:
                bad = archive.testzip()
                if bad is not None:
                    return {"valid": False, "reason": f"invalid_office_archive:{path.name}:{bad}"}
        except (OSError, zipfile.BadZipFile) as error:
            return {"valid": False, "reason": f"unreadable_office_file:{path.name}:{type(error).__name__}"}
        details.append({"path": str(path.relative_to(run_dir)).replace("\\", "/"), "sha256": _hash(path)})
    return {"valid": True, "run_directory": str(run_dir), "deliverables": details, "output_dataset_row_sha256": _hash(row_path)}


def _save(scope: Path, receipt: dict[str, Any]) -> None:
    _write(_receipt_path(scope), receipt)


def execute(scope: Path) -> None:
    manifest = _read(scope / "manifest.json")
    receipt = _read(_receipt_path(scope))
    if receipt.get("state") != "prepared":
        raise ValueError(f"scope_not_executable:{receipt.get('state')}")
    receipt["state"] = "running"
    receipt.setdefault("started_at", _now())
    receipt.setdefault("deadline_monotonic", time.monotonic() + int(manifest["limits"]["scope_seconds"]))
    _save(scope, receipt)
    for index, cell in enumerate(receipt["cells"]):
        if cell.get("state") == "completed":
            continue
        if (scope / "STOP").exists():
            receipt.update(state="stopped", stop_reason="stop_requested_before_cell", stopped_at=_now())
            _save(scope, receipt)
            return
        if time.monotonic() >= receipt["deadline_monotonic"]:
            receipt.update(state="stopped", stop_reason="scope_time_exhausted", stopped_at=_now())
            _save(scope, receipt)
            return
        run_dir = scope / "runs" / cell["cell_id"]
        if cell.get("state") != "solver_completed_ungraded":
            cell.update(state="solver_running", solver_started_at=_now())
            receipt["events"].append({"at": _now(), "event": "solver_started", "cell": cell["cell_id"]})
            _save(scope, receipt)
            command = [str(PYTHON), "-m", "bench_standalone.stirrup_batch", cell["input_root"], "--output", str(run_dir), "-w", "1", "--model", cell["model"], "--e2b-template", TEMPLATE]
            solver_deadline = min(receipt["deadline_monotonic"], time.monotonic() + SOLVER_SECONDS)
            code, cleanup = _run(command, cwd=RW_TASK, log=scope / "logs" / f"{cell['cell_id']}.solver.log", deadline=solver_deadline)
            cell.update(solver_finished_at=_now(), solver_returncode=code, solver_cleanup=cleanup)
            if code is None:
                cell.update(state="solver_timeout")
                receipt.update(state="stopped", stop_reason="solver_timeout", stopped_at=_now(), failed_cell=cell["cell_id"])
                _save(scope, receipt)
                return
            if code != 0:
                cell.update(state="solver_failed")
                receipt.update(state="stopped", stop_reason="solver_failed", stopped_at=_now(), failed_cell=cell["cell_id"])
                _save(scope, receipt)
                return
        validity = _structural_validity(cell, run_dir)
        cell["delivery_validity"] = validity
        if not validity["valid"]:
            cell.update(state="delivery_invalid")
            receipt.update(state="stopped", stop_reason="delivery_invalid", stopped_at=_now(), failed_cell=cell["cell_id"])
            _save(scope, receipt)
            return
        cell.update(state="grading_running", grading_started_at=_now())
        _save(scope, receipt)
        grade_dir = scope / "grades" / cell["cell_id"]
        grade_command = [str(PYTHON), "-m", "bench_standalone.grade_deliverables", str(run_dir), "--strictness", "strict", "--out-dir", str(grade_dir)]
        code, cleanup = _run(grade_command, cwd=RW_TASK, log=scope / "logs" / f"{cell['cell_id']}.grader.log", deadline=receipt["deadline_monotonic"])
        cell.update(grading_finished_at=_now(), grading_returncode=code, grading_cleanup=cleanup)
        reports = sorted(grade_dir.glob("eval_*.json"))
        if code is None or code != 0 or len(reports) != 1:
            cell.update(state="grading_failed", grading_report_count=len(reports))
            receipt.update(state="stopped", stop_reason="grading_failed", stopped_at=_now(), failed_cell=cell["cell_id"])
            _save(scope, receipt)
            return
        grade = _read(reports[0])
        samples = grade.get("samples")
        if not isinstance(samples, list) or len(samples) != 1 or not samples[0].get("success"):
            cell.update(state="grading_invalid")
            receipt.update(state="stopped", stop_reason="grading_invalid", stopped_at=_now(), failed_cell=cell["cell_id"])
            _save(scope, receipt)
            return
        grading = samples[0].get("grading") or {}
        cell.update(state="completed", grading_report=str(reports[0]), grading_report_sha256=_hash(reports[0]), legacy_score=grading.get("total_score"), legacy_max=grading.get("max_possible_score"), audit_applied=grading.get("audit_applied"))
        receipt["events"].append({"at": _now(), "event": "cell_completed", "cell": cell["cell_id"]})
        _save(scope, receipt)
    receipt.update(state="completed", completed_at=_now())
    _save(scope, receipt)


def status(scope: Path) -> None:
    receipt = _read(_receipt_path(scope))
    print(json.dumps({"state": receipt.get("state"), "failed_cell": receipt.get("failed_cell"), "cells": [{key: cell.get(key) for key in ("cell_id", "state", "legacy_score", "legacy_max", "audit_applied")} for cell in receipt.get("cells", [])]}, ensure_ascii=False, indent=2))


def stop(scope: Path) -> None:
    if not scope.is_dir():
        raise FileNotFoundError(scope)
    (scope / "STOP").write_text("operator requested stop\n", encoding="utf-8")
    print(json.dumps({"scope": str(scope), "stop": "requested"}))


def recover_collection(scope: Path) -> None:
    receipt = _read(_receipt_path(scope))
    if receipt.get("state") != "stopped" or receipt.get("stop_reason") != "delivery_invalid":
        raise ValueError("recovery_only_permits_stopped_delivery_validation")
    failed = str(receipt.get("failed_cell") or "")
    matches = [cell for cell in receipt.get("cells", []) if cell.get("cell_id") == failed]
    if len(matches) != 1 or matches[0].get("solver_returncode") != 0:
        raise ValueError("recovery_requires_successful_solver_cell")
    cell = matches[0]
    validity = _structural_validity(cell, scope / "runs" / cell["cell_id"])
    if not validity.get("valid"):
        receipt.setdefault("recovery", []).append({"at": _now(), "result": "validation_still_failed", "cell": failed, "validity": validity})
        _save(scope, receipt)
        return
    cell.update(state="solver_completed_ungraded", delivery_validity=validity)
    receipt.update(state="prepared", stop_reason=None, failed_cell=None)
    receipt.setdefault("recovery", []).append({"at": _now(), "result": "accepted_existing_solver_output", "cell": failed, "reason": "legacy_runner_nested_run_directory", "controller_sha256": _hash(Path(__file__))})
    receipt.setdefault("events", []).append({"at": _now(), "event": "collection_recovered_without_solver_rerun", "cell": failed})
    _save(scope, receipt)
    print(json.dumps({"scope": str(scope), "recovery": "accepted_existing_solver_output", "cell": failed}, ensure_ascii=False))


def report(scope: Path) -> None:
    receipt = _read(_receipt_path(scope))
    rows = []
    for cell in receipt.get("cells", []):
        grade_summary: dict[str, Any] | None = None
        grade_path = Path(str(cell.get("grading_report") or ""))
        if grade_path.is_file():
            samples = _read(grade_path).get("samples") or []
            if len(samples) == 1 and isinstance(samples[0], dict):
                grade = samples[0].get("grading") or {}
                grade_summary = {key: grade.get(key) for key in ("total_score", "max_possible_score", "audit_applied", "audit_reduced_points", "audit_reduced_rows", "audit_skipped_reason", "expected_max_from_rubric_mismatch")}
        row = {key: cell.get(key) for key in ("cell_id", "model", "task_id", "state", "solver_started_at", "solver_finished_at", "grading_started_at", "grading_finished_at", "legacy_score", "legacy_max", "audit_applied", "delivery_validity", "grading_report_sha256")}
        row["legacy_grade_summary"] = grade_summary
        rows.append(row)
    manifest = _read(scope / "manifest.json")
    _write(scope / "report.json", {"label": "legacy rw-task diagnostic", "formal_atomic_rubric_score": "not_produced", "state": receipt.get("state"), "stop_reason": receipt.get("stop_reason"), "controller_recovery": receipt.get("recovery") or [], "cells": rows, "limits": manifest.get("limits"), "prepared_input_hashes": {key: manifest.get(key) for key in ("prepared_scope_sha256", "prepared_validation_sha256", "prepared_probe_receipt_sha256")}, "unknowns": ["Provider billing is unavailable.", "Legacy Solver logs retain provider usage but no normalized cross-provider token total is inferred."]})
    print(json.dumps({"report": str(scope / "report.json"), "state": receipt.get("state")}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "status", "stop", "recover-collection", "report"))
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.scope)
    elif args.action == "execute":
        execute(args.scope)
    elif args.action == "status":
        status(args.scope)
    elif args.action == "stop":
        stop(args.scope)
    elif args.action == "recover-collection":
        recover_collection(args.scope)
    else:
        report(args.scope)


if __name__ == "__main__":
    main()
