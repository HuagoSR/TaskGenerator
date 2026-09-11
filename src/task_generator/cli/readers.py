"""Safe, read-only projections of documented public artifact shapes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class UnsupportedArtifactError(ValueError):
    """The path is not one of the documented read-only input shapes."""


LEGACY_LABEL = "legacy rw-task diagnostic"


def inspect_path(path: Path) -> dict[str, Any]:
    path = _regular_path(path)
    if path.is_dir() and (path / "dataset_row.json").is_file():
        return _candidate_pack(path)
    # Legacy scopes also have receipts: prefer their explicit report format.
    if path.is_dir() and (path / "report.json").is_file() and _is_legacy_file(path / "report.json"):
        return _legacy_report(path / "report.json", path)
    if path.is_file() and path.name == "report.json":
        return _legacy_report(path, path.parent)
    if path.is_dir() and ((path / "receipt.json").is_file() or (path / "scope.json").is_file()):
        return _r10_scope(path)
    raise UnsupportedArtifactError("supported inputs are a GDPval-shaped package, R10 scope, or legacy report.json")


def discover(root: Path) -> list[dict[str, Any]]:
    root = _regular_path(root)
    if not root.is_dir():
        raise UnsupportedArtifactError("runs root must be a directory")
    found: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for current, directories, files in _walk_without_links(root):
        names = set(files)
        if "dataset_row.json" in names or "receipt.json" in names or "scope.json" in names or "report.json" in names:
            if current not in seen:
                try:
                    found.append(_compact(inspect_path(current)))
                    seen.add(current)
                except UnsupportedArtifactError:
                    pass
    return sorted(found, key=lambda item: item["path"])


def markdown_report(projection: dict[str, Any]) -> str:
    lines = ["# TaskGenerator read-only report", "", f"- 类型：`{projection['kind']}`", f"- 路径：`{projection['path']}`"]
    identity = projection.get("identity", {})
    for key in ("task_id", "scope_id", "protocol"):
        if identity.get(key) is not None:
            lines.append(f"- {key}：`{identity[key]}`")
    if projection["kind"] == "legacy_rw_task_diagnostic":
        return _legacy_markdown(lines, projection)
    lines.extend(["", "## 状态"])
    for key, value in projection.get("status", {}).items():
        lines.append(f"- {key}：{_inline(value)}")
    lines.extend(["", "## 计量"])
    metrics = projection.get("metrics", {})
    if metrics:
        for key, value in metrics.items():
            lines.append(f"- {key}：{_inline(value)}")
    else:
        lines.append("- unavailable")
    return "\n".join(lines) + "\n"


def _legacy_markdown(lines: list[str], projection: dict[str, Any]) -> str:
    status = projection["status"]
    lines.extend(["", "## 概览"])
    for key in ("batch_schedule", "formal_atomic_score", "researcher_admission", "controller_intervention"):
        lines.append(f"- {key}：{_inline(status.get(key))}")
    lines.extend(["", "## 模型 × 任务", "", "| 模型 | 任务 | cell | 执行 | 交付 | legacy 分数 | 审计 |", "| --- | --- | --- | --- | --- | --- |"])
    for cell in projection.get("cells", []):
        score = "未产出" if cell["legacy_score"] is None else f"{cell['legacy_score']}/{cell['legacy_max'] if cell['legacy_max'] is not None else '?'}"
        audit = cell["audit_summary"].get("audit_applied")
        lines.append(f"| {cell['model'] or 'unknown'} | {cell['task_id'] or 'unknown'} | {cell['cell_id'] or 'unknown'} | {cell['native_execution']} | {cell['delivery_validity']} | {score} | {audit if audit is not None else '未核验'} |")
    lines.extend(["", "## 核验边界", "", f"- 逐项评分：{status['itemized_verification']}", f"- legacy 评分：{status['legacy_scoring']}；正式原子评分：{status['formal_atomic_score']}。"])
    recovery = projection.get("recovery", [])
    if recovery:
        lines.extend(["", "## 控制器恢复记录", ""])
        for index, item in enumerate(recovery, 1):
            lines.append(f"- {index}. {_inline(item)}")
    return "\n".join(lines) + "\n"


def _candidate_pack(root: Path) -> dict[str, Any]:
    row = _json_object(root / "dataset_row.json")
    references = _regular_files(root / "reference_files")
    deliverables = _regular_files(root / "deliverable_files")
    rubric = row.get("rubric")
    return {"kind": "candidate_pack", "path": str(root), "identity": {"task_id": row.get("task_id"), "sector": row.get("sector"), "occupation": row.get("occupation")}, "status": {"native_execution": "not_applicable", "collection_acceptance": "not_applicable", "delivery_validity": "not_produced", "legacy_scoring": "not_produced", "formal_atomic_score": "not_produced", "original_review": "unavailable", "researcher_admission": "unavailable", "controller_intervention": "unavailable"}, "metrics": {"reference_file_count": len(references), "deliverable_file_count": len(deliverables), "rubric_item_count": len(rubric) if isinstance(rubric, list) else "unavailable"}, "files": {"reference_files": references, "deliverable_files": deliverables}}


def _r10_scope(root: Path) -> dict[str, Any]:
    scope, receipt = _optional_json(root / "scope.json"), _optional_json(root / "receipt.json")
    if not scope and not receipt:
        raise UnsupportedArtifactError("R10 scope requires scope.json or receipt.json")
    return {"kind": "r10_scope", "path": str(root), "identity": {"scope_id": _first(scope, receipt, "scope_id", "run_id", "batch_id"), "protocol": _first(scope, receipt, "protocol", "purpose")}, "status": {"native_execution": _first(receipt, scope, "native_execution") or "unavailable", "batch_schedule": _first(receipt, scope, "status", "state") or "unavailable", "collection_acceptance": _first(receipt, scope, "acceptance_status", "collection_status") or "unavailable", "delivery_validity": _first(receipt, scope, "delivery_validity") or "unavailable", "legacy_scoring": "not_produced", "formal_atomic_score": _first(receipt, scope, "formal_atomic_score") or "not_produced", "original_review": _first(receipt, scope, "review_quality", "review_status") or "unavailable", "researcher_admission": _first(receipt, scope, "researcher_admission", "admission_status") or "unavailable", "controller_intervention": _first(receipt, scope, "controller_intervention", "intervention") or "unavailable"}, "metrics": {"attempts_recorded": _first(receipt, scope, "attempts", "launches"), "wall_clock_seconds": _first(receipt, scope, "wall_clock_seconds", "elapsed_seconds")}, "evidence": {"scope_json": (root / "scope.json").is_file(), "receipt_json": (root / "receipt.json").is_file()}}


def _legacy_report(path: Path, scope_root: Path) -> dict[str, Any]:
    report = _json_object(path)
    if not _looks_like_legacy(report):
        raise UnsupportedArtifactError("report.json is not a supported legacy rw-task diagnostic report")
    receipt = _optional_json(scope_root / "receipt.json")
    cells = [_legacy_cell(cell) for cell in report["cells"] if isinstance(cell, dict)]
    report_state, receipt_state = report.get("state"), receipt.get("state")
    conflicts = [] if not report_state or not receipt_state or report_state == receipt_state else [{"field": "batch_schedule", "report": report_state, "receipt": receipt_state}]
    recovery = report.get("controller_recovery") if isinstance(report.get("controller_recovery"), list) else []
    if not recovery and isinstance(receipt.get("recovery"), list):
        recovery = receipt["recovery"]
    return {"kind": "legacy_rw_task_diagnostic", "path": str(path), "identity": {"scope_id": receipt.get("scope_id") or receipt.get("run_id") or report.get("scope_id"), "protocol": LEGACY_LABEL}, "status": {"batch_schedule": report_state or receipt_state or "unavailable", "native_execution": "per_cell", "collection_acceptance": "per_cell", "delivery_validity": "per_cell", "legacy_scoring": "produced" if any(cell["legacy_score"] is not None for cell in cells) else "not_produced", "formal_atomic_score": report.get("formal_atomic_rubric_score", "not_produced"), "itemized_verification": "not_completed", "original_review": "not_applicable", "researcher_admission": report.get("researcher_admission", "unavailable"), "controller_intervention": "recorded" if recovery else "not_recorded"}, "metrics": {"cell_count": len(cells), "legacy_score_count": sum(cell["legacy_score"] is not None for cell in cells)}, "cells": cells, "recovery": recovery, "evidence": {"report_json": True, "receipt_json": bool(receipt), "itemized_scores": False, "prepared_input_hashes": report.get("prepared_input_hashes", "unavailable")}, "conflicts": conflicts}


def _legacy_cell(cell: dict[str, Any]) -> dict[str, Any]:
    summary = cell.get("legacy_grade_summary") if isinstance(cell.get("legacy_grade_summary"), dict) else {}
    return {"cell_id": cell.get("cell_id"), "model": cell.get("model"), "task_id": cell.get("task_id"), "cell_state": cell.get("state", "unavailable"), "native_execution": cell.get("state", "unavailable"), "collection_acceptance": cell.get("collection_acceptance", "unavailable"), "delivery_validity": cell.get("delivery_validity", "unavailable"), "legacy_score": cell.get("legacy_score"), "legacy_max": cell.get("legacy_max"), "audit_summary": {key: summary.get(key, cell.get(key) if key == "audit_applied" else None) for key in ("audit_applied", "audit_reduced_points", "audit_reduced_rows", "audit_skipped_reason", "expected_max_from_rubric_mismatch")}, "grading_summary": {key: summary.get(key) for key in ("total_score", "max_possible_score")}, "evidence": {"grading_report_sha256": cell.get("grading_report_sha256"), "grading_summary_available": bool(summary)}}


def _is_legacy_file(path: Path) -> bool:
    try:
        return _looks_like_legacy(_json_object(path))
    except UnsupportedArtifactError:
        return False


def _looks_like_legacy(payload: dict[str, Any]) -> bool:
    return payload.get("label") == LEGACY_LABEL and payload.get("formal_atomic_rubric_score") == "not_produced" and isinstance(payload.get("cells"), list)


def _first(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> Any:
    for source in (primary, secondary):
        for key in keys:
            if key in source:
                return source[key]
    return None


def _compact(projection: dict[str, Any]) -> dict[str, Any]:
    return {"path": projection["path"], "kind": projection["kind"], "identity": projection["identity"], "status": projection["status"]}


def _json_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise UnsupportedArtifactError(f"regular JSON file required: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UnsupportedArtifactError(f"invalid UTF-8 JSON: {path.name}") from exc
    if not isinstance(payload, dict):
        raise UnsupportedArtifactError(f"JSON object required: {path.name}")
    return payload


def _optional_json(path: Path) -> dict[str, Any]:
    return _json_object(path) if path.is_file() else {}


def _regular_path(path: Path) -> Path:
    if path.is_symlink() or not path.exists():
        raise UnsupportedArtifactError("existing non-symlink path required")
    return path.resolve()


def _regular_files(root: Path) -> list[str]:
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(str(item.relative_to(root).as_posix()) for item in root.rglob("*") if item.is_file() and not item.is_symlink())


def _walk_without_links(root: Path):
    for current, directories, files in __import__("os").walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if not (current_path / name).is_symlink() and name not in {".git", "__pycache__"}]
        yield current_path, directories, files


def _inline(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, (dict, list)):
        return "`" + json.dumps(value, ensure_ascii=False, sort_keys=True) + "`"
    return str(value)
