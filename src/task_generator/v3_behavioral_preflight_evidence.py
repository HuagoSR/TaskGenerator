from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_behavioral_preflight_execution import (
    BehavioralPreflightExecutionManifestV1,
)
from task_generator.v3_solver_execution_budget import SolverProcessOutcomeV1


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha(deliverable_root: Path) -> Optional[str]:
    files = sorted(item for item in deliverable_root.rglob("*") if item.is_file())
    if not files:
        return None
    aggregate = hashlib.sha256()
    for file in files:
        aggregate.update(file.relative_to(deliverable_root).as_posix().encode())
        aggregate.update(b"\0")
        aggregate.update(hashlib.sha256(file.read_bytes()).digest())
    return aggregate.hexdigest()


class BehavioralEvidenceIntegrityRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solver_model: str
    decision: Literal["pass", "blocked"]
    budget_sha256_valid: bool
    outcome_sha256_valid: bool
    stdout_sha256_valid: bool
    stderr_sha256_valid: bool
    output_tree_sha256_valid: bool
    identity_valid: bool
    blocking_reasons: List[str] = Field(default_factory=list)


class BehavioralEvidenceIntegrityReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_version: Literal["v3.behavioral_evidence_integrity.1"] = (
        "v3.behavioral_evidence_integrity.1"
    )
    comparison_id: str
    authorization_request_sha256: str
    execution_manifest_path: str
    execution_manifest_sha256: str
    record_count: int
    records: List[BehavioralEvidenceIntegrityRecordV1]
    decision: Literal["pass", "blocked"]
    blocking_reasons: List[str] = Field(default_factory=list)
    external_calls_made: Literal[False] = False


class BehavioralPreflightEvidenceAuditor:
    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()

    def audit(
        self, execution_manifest_path: str | Path
    ) -> BehavioralEvidenceIntegrityReportV1:
        manifest_path = Path(execution_manifest_path).resolve()
        self._require_inside_campaign(manifest_path)
        manifest = BehavioralPreflightExecutionManifestV1.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        records: list[BehavioralEvidenceIntegrityRecordV1] = []
        global_reasons: list[str] = []
        for record in manifest.records:
            reasons: list[str] = []
            budget_path = self._evidence_path(
                record.budget_contract_path, "budget", reasons
            )
            outcome_path = self._evidence_path(record.outcome_path, "outcome", reasons)
            stdout_path = self._evidence_path(
                record.process_stdout_path, "stdout", reasons
            )
            stderr_path = self._evidence_path(
                record.process_stderr_path, "stderr", reasons
            )
            budget_sha_valid = self._hash_valid(
                budget_path, record.budget_contract_sha256, "budget", reasons
            )
            outcome_sha_valid = self._hash_valid(
                outcome_path, record.outcome_sha256, "outcome", reasons
            )
            stdout_sha_valid = self._hash_valid(
                stdout_path, record.process_stdout_sha256, "stdout", reasons
            )
            stderr_sha_valid = self._hash_valid(
                stderr_path, record.process_stderr_sha256, "stderr", reasons
            )
            identity_valid = False
            tree_valid = False
            if outcome_sha_valid and outcome_path is not None:
                try:
                    outcome = SolverProcessOutcomeV1.model_validate_json(
                        outcome_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    reasons.append("outcome_schema_invalid")
                else:
                    status_valid = (
                        record.status == "succeeded"
                        and outcome.process_status == "succeeded"
                    ) or (
                        record.status == "failed"
                        and outcome.process_status in {"failed", "blocked", "timeout"}
                    )
                    identity_valid = (
                        outcome.solver_model == record.solver_model
                        and outcome.budget.solver_model == record.solver_model
                        and status_valid
                    )
                    if not identity_valid:
                        reasons.append("outcome_identity_mismatch")
                    actual_tree = _tree_sha(
                        Path(record.output_root).resolve()
                        / "run_solver_tool_preflight"
                        / "deliverable_files"
                    )
                    tree_valid = actual_tree == outcome.output_tree_sha256
                    if not tree_valid:
                        reasons.append("output_tree_sha256_mismatch")
            decision: Literal["pass", "blocked"] = (
                "pass" if not reasons else "blocked"
            )
            records.append(
                BehavioralEvidenceIntegrityRecordV1(
                    solver_model=record.solver_model,
                    decision=decision,
                    budget_sha256_valid=budget_sha_valid,
                    outcome_sha256_valid=outcome_sha_valid,
                    stdout_sha256_valid=stdout_sha_valid,
                    stderr_sha256_valid=stderr_sha_valid,
                    output_tree_sha256_valid=tree_valid,
                    identity_valid=identity_valid,
                    blocking_reasons=reasons,
                )
            )
            global_reasons.extend(
                f"{record.solver_model}:{reason}" for reason in reasons
            )
        return BehavioralEvidenceIntegrityReportV1(
            comparison_id=manifest.comparison_id,
            authorization_request_sha256=manifest.authorization_request_sha256,
            execution_manifest_path=str(manifest_path),
            execution_manifest_sha256=_sha(manifest_path),
            record_count=len(records),
            records=records,
            decision="pass" if not global_reasons else "blocked",
            blocking_reasons=global_reasons,
        )

    def _evidence_path(
        self, value: str | None, label: str, reasons: list[str]
    ) -> Path | None:
        if not value:
            reasons.append(f"{label}_path_missing")
            return None
        path = Path(value).resolve()
        try:
            self._require_inside_campaign(path)
        except ValueError:
            reasons.append(f"{label}_outside_campaign")
            return None
        if not path.is_file():
            reasons.append(f"{label}_file_missing")
            return None
        return path

    @staticmethod
    def _hash_valid(
        path: Path | None,
        expected: str | None,
        label: str,
        reasons: list[str],
    ) -> bool:
        valid = path is not None and expected is not None and _sha(path) == expected
        if not valid:
            reasons.append(f"{label}_sha256_mismatch")
        return valid

    def _require_inside_campaign(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("behavioral_evidence_outside_campaign") from exc
