"""Strict, local-only configuration and preview-spec parsing for ``taskgen``.

The public CLI deliberately has no provider, SSH, or credential configuration.
It only needs local paths for read-only discovery and an optional report output
root.  Execution settings belong to a future, explicitly authorized scope.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CliInputError(ValueError):
    """A user-controlled CLI file is malformed or outside its allowed shape."""


LOCAL_CONFIG_KEYS = {"version", "artifact_roots", "report_output_root"}
PREVIEW_SPEC_KEYS = {"version", "protocol", "input", "models", "budget", "order", "output"}
SUPPORTED_PREVIEW_PROTOCOLS = {"r10-task-factory", "rw-legacy-diagnostic"}


@dataclass(frozen=True)
class LocalConfig:
    path: Path
    artifact_roots: tuple[Path, ...]
    report_output_root: Path | None


def load_local_config(path: Path | None) -> LocalConfig | None:
    if path is None:
        return None
    payload = _load_object(path, "local configuration")
    _reject_unknown(payload, LOCAL_CONFIG_KEYS, "local configuration")
    if payload.get("version", 1) != 1:
        raise CliInputError("local configuration: version must be 1")
    roots = payload.get("artifact_roots", [])
    if not isinstance(roots, list) or not all(isinstance(item, str) for item in roots):
        raise CliInputError("local configuration: artifact_roots must be a string array")
    report_root = payload.get("report_output_root")
    if report_root is not None and not isinstance(report_root, str):
        raise CliInputError("local configuration: report_output_root must be a string")
    base = path.parent.resolve()
    return LocalConfig(
        path=path.resolve(),
        artifact_roots=tuple(_resolve_from(base, item, "artifact_roots") for item in roots),
        report_output_root=_resolve_from(base, report_root, "report_output_root") if report_root else None,
    )


def load_preview_spec(path: Path, expected_kind: str) -> dict[str, Any]:
    payload = _load_object(path, f"{expected_kind} preview spec")
    _reject_unknown(payload, PREVIEW_SPEC_KEYS, f"{expected_kind} preview spec")
    required = {"version", "protocol", "input", "models", "budget", "order", "output"}
    missing = sorted(required - set(payload))
    if missing:
        raise CliInputError(f"{expected_kind} preview spec: missing {', '.join(missing)}")
    if payload["version"] != 1:
        raise CliInputError(f"{expected_kind} preview spec: version must be 1")
    if payload["protocol"] not in SUPPORTED_PREVIEW_PROTOCOLS:
        raise CliInputError(f"{expected_kind} preview spec: unsupported protocol {payload['protocol']!r}")
    if not isinstance(payload["input"], dict):
        raise CliInputError(f"{expected_kind} preview spec: input must be an object")
    if set(payload["input"]) - {"path", "sha256"} or not isinstance(payload["input"].get("path"), str):
        raise CliInputError(f"{expected_kind} preview spec: input accepts path and optional sha256")
    if not isinstance(payload["models"], list) or not payload["models"] or not all(isinstance(item, str) and item for item in payload["models"]):
        raise CliInputError(f"{expected_kind} preview spec: models must be a nonempty string array")
    if not isinstance(payload["budget"], dict) or set(payload["budget"]) != {"max_launches", "wall_clock_seconds"}:
        raise CliInputError(f"{expected_kind} preview spec: budget requires max_launches and wall_clock_seconds")
    if not all(isinstance(payload["budget"][key], int) and payload["budget"][key] >= 0 for key in payload["budget"]):
        raise CliInputError(f"{expected_kind} preview spec: budget values must be nonnegative integers")
    if not isinstance(payload["order"], list) or not all(isinstance(item, str) and item for item in payload["order"]):
        raise CliInputError(f"{expected_kind} preview spec: order must be a string array")
    if not isinstance(payload["output"], dict) or set(payload["output"]) != {"path"} or not isinstance(payload["output"].get("path"), str):
        raise CliInputError(f"{expected_kind} preview spec: output requires path")

    base = path.parent.resolve()
    input_path = _resolve_from(base, payload["input"]["path"], "input.path")
    output_path = _resolve_from(base, payload["output"]["path"], "output.path")
    input_state = {"path": str(input_path), "exists": input_path.is_file()}
    if input_path.is_file():
        actual_hash = sha256_file(input_path)
        input_state["sha256"] = actual_hash
        expected_hash = payload["input"].get("sha256")
        input_state["hash_matches"] = expected_hash is None or expected_hash == actual_hash
    else:
        input_state["hash_matches"] = False
    return {
        "kind": expected_kind,
        "spec_path": str(path.resolve()),
        "protocol": payload["protocol"],
        "input": input_state,
        "models": payload["models"],
        "budget": payload["budget"],
        "order": payload["order"],
        "output": {"path": str(output_path), "exists": output_path.exists()},
        "external_conditions": ["provider authentication not checked", "remote environment not checked"],
        "execution": "preview_only_no_scope_receipt_or_budget_created",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CliInputError(f"{label}: readable regular file required")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliInputError(f"{label}: invalid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise CliInputError(f"{label}: JSON object required")
    return payload


def _reject_unknown(payload: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CliInputError(f"{label}: unknown fields {', '.join(unknown)}")


def _resolve_from(base: Path, raw: str, field: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute() or raw.startswith("\\\\"):
        raise CliInputError(f"{field}: absolute and UNC paths are not allowed in JSON configuration")
    if any(part == ".." for part in candidate.parts):
        raise CliInputError(f"{field}: parent traversal is not allowed")
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise CliInputError(f"{field}: path escapes its JSON file directory") from exc
    return resolved
