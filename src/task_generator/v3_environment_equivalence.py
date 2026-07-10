from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


EXPECTED_OFFLINE_METRICS = {
    "candidate_count": 4,
    "accepted_count": 4,
    "sample_ready_count": 3,
    "generated_case_count": 2,
    "candidate_ready_count": 2,
    "verifier_pass_count": 2,
    "export_compatible_count": 2,
    "qa_blocked_count": 0,
    "prepared_eval_count": 1,
    "executed_eval_count": 0,
}
EXPECTED_OFFLINE_FINGERPRINT = "722497164acf1138bbfccd4975e9a0ed75ddf7adbc463738b3c90b9ab6881173"
EXPECTED_STAGE_ORDER = [
    "source_to_skills",
    "registry_prepare",
    "task_generation",
    "production_review",
    "rw_task_eval",
]


class EquivalenceFinding(BaseModel):
    field: str
    local: Any = None
    remote: Any = None
    matches: bool


class EnvironmentEquivalenceReport(BaseModel):
    report_version: str = "v3.environment_equivalence.1"
    decision: str
    required_findings: list[EquivalenceFinding] = Field(default_factory=list)
    allowed_differences: list[str] = Field(default_factory=list)
    secret_or_windows_path_findings: list[str] = Field(default_factory=list)


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_environments(
    local_manifest_path: str | Path,
    remote_manifest_path: str | Path,
    *,
    local_acceptance_path: str | Path | None = None,
    remote_acceptance_path: str | Path | None = None,
    expected_image_id: str | None = None,
    expected_rw_task_snapshot: str | None = None,
) -> EnvironmentEquivalenceReport:
    local_manifest = load_json(local_manifest_path)
    remote_manifest = load_json(remote_manifest_path)
    local_acceptance = load_json(local_acceptance_path or Path(local_manifest_path).with_name("acceptance_report.json"))
    remote_acceptance = load_json(remote_acceptance_path or Path(remote_manifest_path).with_name("acceptance_report.json"))
    findings: list[EquivalenceFinding] = []

    def same(field: str, left: Any, right: Any) -> None:
        findings.append(EquivalenceFinding(field=field, local=left, remote=right, matches=left == right))

    same("manifest_version", local_manifest.get("end_to_end_manifest_version"), remote_manifest.get("end_to_end_manifest_version"))
    same("git_commit", local_manifest.get("git_commit"), remote_manifest.get("git_commit"))
    same("stage_order", list((local_manifest.get("stages") or {}).keys()), list((remote_manifest.get("stages") or {}).keys()))
    same("stage_order_contract", list((remote_manifest.get("stages") or {}).keys()), EXPECTED_STAGE_ORDER)
    same("profile", (local_manifest.get("request") or {}).get("profile"), (remote_manifest.get("request") or {}).get("profile"))
    same("input_fingerprints", local_manifest.get("input_fingerprints"), remote_manifest.get("input_fingerprints"))
    same("metrics", local_acceptance.get("metrics"), remote_acceptance.get("metrics"))
    same("expected_metrics", remote_acceptance.get("metrics"), EXPECTED_OFFLINE_METRICS)
    same("content_fingerprint", local_acceptance.get("content_fingerprint"), remote_acceptance.get("content_fingerprint"))
    same("expected_fingerprint", remote_acceptance.get("content_fingerprint"), EXPECTED_OFFLINE_FINGERPRINT)
    same("external_effects", local_acceptance.get("external_effects"), remote_acceptance.get("external_effects"))
    same(
        "canonical_registry_unchanged",
        remote_acceptance.get("canonical_registry_before_sha256"),
        remote_acceptance.get("canonical_registry_after_sha256"),
    )
    remote_container = (remote_manifest.get("runtime_summary") or {}).get("container") or {}
    if expected_image_id:
        same("image_id", remote_container.get("image_id"), expected_image_id)
    if expected_rw_task_snapshot:
        same("rw_task_snapshot", remote_container.get("rw_task_snapshot"), expected_rw_task_snapshot)

    remote_text = Path(remote_manifest_path).parent
    suspicious: list[str] = []
    for path in remote_text.rglob("*.json"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:\\", text):
            suspicious.append(f"windows_path:{path.name}")
        if re.search(r"(?i)(bearer\s+[a-z0-9._-]{12,}|api[_-]?key\s*[=:]\s*['\"]?[a-z0-9._-]{12,})", text):
            suspicious.append(f"possible_secret:{path.name}")

    passed = all(item.matches for item in findings) and not suspicious
    return EnvironmentEquivalenceReport(
        decision="equivalent" if passed else "not_equivalent",
        required_findings=findings,
        allowed_differences=["run_id", "timestamps", "durations", "runtime_paths", "platform_resource_statistics"],
        secret_or_windows_path_findings=sorted(set(suspicious)),
    )


def write_report(report: EnvironmentEquivalenceReport, output_path: str | Path) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
