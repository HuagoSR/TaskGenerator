"""Safe, read-only projections of a deliberately small set of R10 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class UnsupportedArtifactError(ValueError):
    """The path is not one of the documented read-only input shapes."""


def inspect_path(path: Path) -> dict[str, Any]:
    path = _regular_path(path)
    if path.is_dir() and (path / "dataset_row.json").is_file():
        return _candidate_pack(path)
    if path.is_dir() and ((path / "receipt.json").is_file() or (path / "scope.json").is_file()):
        return _r10_scope(path)
    if path.is_file() and path.name == "report.json":
        return _legacy_report(path)
    if path.is_dir() and (path / "report.json").is_file():
        return _legacy_report(path / "report.json")
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
            candidate = current
            if candidate not in seen:
                try:
                    found.append(_compact(inspect_path(candidate)))
                    seen.add(candidate)
                except UnsupportedArtifactError:
                    pass
    return sorted(found, key=lambda item: item["path"])


def markdown_report(projection: dict[str, Any]) -> str:
    lines = [f"# TaskGenerator read-only report", "", f"- 类型：`{projection['kind']}`", f"- 路径：`{projection['path']}`"]
    identity = projection.get("identity", {})
    for key in ("task_id", "scope_id", "protocol"):
        if identity.get(key) is not None:
            lines.append(f"- {key}：`{identity[key]}`")
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


def _candidate_pack(root: Path) -> dict[str, Any]:
    row = _json_object(root / "dataset_row.json")
    references = _regular_files(root / "reference_files")
    deliverables = _regular_files(root / "deliverable_files")
    rubric = row.get("rubric")
    return {
        "kind": "candidate_pack",
        "path": str(root),
        "identity": {"task_id": row.get("task_id"), "sector": row.get("sector"), "occupation": row.get("occupation")},
        "status": {
            "native_execution": "not_applicable",
            "collection_acceptance": "not_applicable",
            "delivery_validity": "not_produced",
            "legacy_scoring": "not_produced",
            "formal_atomic_score": "not_produced",
            "original_review": "unavailable",
            "researcher_admission": "unavailable",
            "controller_intervention": "unavailable",
        },
        "metrics": {"reference_file_count": len(references), "deliverable_file_count": len(deliverables), "rubric_item_count": len(rubric) if isinstance(rubric, list) else "unavailable"},
        "files": {"reference_files": references, "deliverable_files": deliverables},
    }


def _r10_scope(root: Path) -> dict[str, Any]:
    scope = _optional_json(root / "scope.json")
    receipt = _optional_json(root / "receipt.json")
    if not scope and not receipt:
        raise UnsupportedArtifactError("R10 scope requires scope.json or receipt.json")
    return {
        "kind": "r10_scope",
        "path": str(root),
        "identity": {"scope_id": _first(scope, receipt, "scope_id", "run_id", "batch_id"), "protocol": _first(scope, receipt, "protocol", "purpose")},
        "status": {
            "native_execution": _first(receipt, scope, "native_execution", "status", "state") or "unavailable",
            "collection_acceptance": _first(receipt, scope, "acceptance_status", "collection_status") or "unavailable",
            "delivery_validity": _first(receipt, scope, "delivery_validity") or "unavailable",
            "legacy_scoring": "not_produced",
            "formal_atomic_score": _first(receipt, scope, "formal_atomic_score") or "not_produced",
            "original_review": _first(receipt, scope, "review_quality", "review_status") or "unavailable",
            "researcher_admission": _first(receipt, scope, "researcher_admission", "admission_status") or "unavailable",
            "controller_intervention": _first(receipt, scope, "controller_intervention", "intervention") or "unavailable",
        },
        "metrics": {"attempts_recorded": _first(receipt, scope, "attempts", "launches"), "wall_clock_seconds": _first(receipt, scope, "wall_clock_seconds", "elapsed_seconds")},
        "evidence": {"scope_json": (root / "scope.json").is_file(), "receipt_json": (root / "receipt.json").is_file()},
    }


def _legacy_report(path: Path) -> dict[str, Any]:
    report = _json_object(path)
    if not _looks_like_legacy(report):
        raise UnsupportedArtifactError("report.json is not a supported legacy rw-task diagnostic report")
    scores = _collect_scores(report)
    item_scores = [item for item in scores if item.get("item_id") is not None]
    declared_total = _find(report, "total_score")
    item_total = sum(item["score"] for item in item_scores) if item_scores else None
    score_consistency = (
        "conflict" if isinstance(declared_total, (int, float)) and isinstance(item_total, (int, float)) and declared_total != item_total
        else "consistent" if isinstance(declared_total, (int, float)) and isinstance(item_total, (int, float))
        else "unavailable"
    )
    return {
        "kind": "legacy_rw_task_diagnostic",
        "path": str(path),
        "identity": {"scope_id": _find(report, "scope_id"), "protocol": "legacy rw-task diagnostic"},
        "status": {
            "native_execution": _find(report, "native_execution") or _find(report, "status") or "unavailable",
            "collection_acceptance": _find(report, "acceptance_status") or "unavailable",
            "delivery_validity": _find(report, "delivery_validity") or "unavailable",
            "legacy_scoring": "produced" if scores else "unavailable",
            "formal_atomic_score": "not_produced",
            "original_review": "not_applicable",
            "researcher_admission": _find(report, "researcher_admission") or "unavailable",
            "controller_intervention": _find(report, "controller_intervention") or "unavailable",
        },
        "metrics": {"legacy_scores": scores, "score_count": len(scores), "declared_total": declared_total, "item_total": item_total, "legacy_score_consistency": score_consistency},
    }


def _looks_like_legacy(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False).lower()
    return "legacy" in text or "rw_task" in text or "rw-task" in text


def _collect_scores(payload: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("score"), (int, float)):
            results.append({"score": payload["score"], "max_score": payload.get("max_score"), "item_id": payload.get("rubric_item_id")})
        for value in payload.values():
            results.extend(_collect_scores(value))
    elif isinstance(payload, list):
        for value in payload:
            results.extend(_collect_scores(value))
    return results


def _find(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find(value, key)
            if found is not None:
                return found
    return None


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
