from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_behavioral_authorization import (
    BehavioralAgentProtocolProbeAuthorizationRequestV1,
    BehavioralAuthorizationManager,
    BehavioralPreflightAuthorizationRequestV2,
    BehavioralPreflightAuthorizationRequestV3,
)
from task_generator.v3_solver_execution_budget import SolverProcessOutcomeV1
from task_generator.v3_source_fingerprint import governed_source_fingerprint


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


class BehavioralPreflightExecutionRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solver_model: str
    status: Literal[
        "pending", "running", "succeeded", "failed", "blocked_indeterminate"
    ] = "pending"
    attempt_count: int = Field(default=0, ge=0, le=1)
    command: List[str]
    budget_contract_path: str
    budget_contract_sha256: str
    output_root: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    returncode: Optional[int] = None
    outcome_path: Optional[str] = None
    outcome_sha256: Optional[str] = None
    first_failure: Optional[str] = None
    process_stdout_path: Optional[str] = None
    process_stdout_sha256: Optional[str] = None
    process_stderr_path: Optional[str] = None
    process_stderr_sha256: Optional[str] = None


class BehavioralPreflightExecutionManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["v3.behavioral_preflight_execution.1"] = (
        "v3.behavioral_preflight_execution.1"
    )
    comparison_id: str
    authorization_request_sha256: str
    authorization_receipt_sha256: str
    fixture_contract: Literal["create_copy_edit_save_submit_xlsx_v1"]
    public_fixture_only: Literal[True] = True
    task_packages_uploaded: Literal[False] = False
    business_tasks_executed: Literal[False] = False
    grader_calls_made: Literal[False] = False
    run_external: bool
    status: Literal[
        "dry_run_ready", "running", "completed", "blocked", "indeterminate"
    ]
    records: List[BehavioralPreflightExecutionRecordV1]
    created_at: str
    updated_at: str


def behavioral_preflight_exit_code(
    manifest: BehavioralPreflightExecutionManifestV1,
) -> int:
    """Make shell automation fail closed when governed execution did not pass."""

    return 0 if manifest.status in {"dry_run_ready", "completed"} else 1


def behavioral_request_timeout_seconds(request: object) -> int:
    """Resolve timeout across panel and one-model protocol request contracts."""
    if isinstance(request, BehavioralAgentProtocolProbeAuthorizationRequestV1):
        return request.timeout_seconds
    return int(getattr(request, "timeout_seconds_per_model"))


class BehavioralPreflightExecutor:
    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.manager = BehavioralAuthorizationManager(self.root)
        self.manifest_root = (
            self.root / "governance" / "behavioral_preflight_executions"
        )
        self.manifest_path = self.manifest_root / "unbound.json"
        self.budget_root = self.root / "governance" / "solver_execution_budgets"

    def execute(
        self,
        *,
        authorization_receipt_path: str | Path,
        input_root: str | Path,
        output_root: str | Path,
        real_world_python: str | Path,
        rw_task_root: str | Path,
        run_external: bool = False,
        command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> BehavioralPreflightExecutionManifestV1:
        receipt_path = Path(authorization_receipt_path).resolve()
        request_path = self.manager.current_request_path
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        request_version = request_payload.get("request_version")
        if request_version == "v3.behavioral_preflight_authorization_request.2":
            check = self.manager.check_v2(receipt_path)
            request = BehavioralPreflightAuthorizationRequestV2.model_validate(
                request_payload
            )
        elif request_version == "v3.behavioral_preflight_authorization_request.3":
            check = self.manager.check_replacement_v3(receipt_path)
            request = BehavioralPreflightAuthorizationRequestV3.model_validate(
                request_payload
            )
        elif request_version == "v3.behavioral_agent_protocol_probe_authorization_request.1":
            check = self.manager.check_agent_protocol_probe_v1(receipt_path)
            request = BehavioralAgentProtocolProbeAuthorizationRequestV1.model_validate(
                request_payload
            )
        else:
            raise ValueError("behavioral_execution_unsupported_request_version")
        if check.decision != "ready":
            raise PermissionError(
                "behavioral_authorization_not_ready:"
                + ",".join(check.blocking_reasons)
            )
        self.manifest_path = (
            self.manifest_root / f"{check.authorization_request_sha256}.json"
        )
        self.budget_root = (
            self.root
            / "governance"
            / "solver_execution_budgets"
            / check.authorization_request_sha256
        )
        source_root = Path(__file__).resolve().parents[2]
        if governed_source_fingerprint(source_root) != request.behavioral_code_fingerprint:
            raise PermissionError("behavioral_execution_source_fingerprint_drift")
        fixture_root = Path(input_root).resolve()
        try:
            fixture_root.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("behavioral_fixture_must_be_inside_campaign") from exc
        self._validate_public_fixture(fixture_root, request)
        python_path = Path(real_world_python).resolve()
        rw_root = Path(rw_task_root).resolve()
        if not python_path.is_file():
            raise FileNotFoundError("real_world_python_missing")
        if not rw_root.is_dir():
            raise FileNotFoundError("rw_task_root_missing")
        output = Path(output_root).resolve()
        try:
            output.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("behavioral_output_must_be_inside_campaign") from exc
        manifest: BehavioralPreflightExecutionManifestV1 | None = None
        if self.manifest_path.exists():
            prior = BehavioralPreflightExecutionManifestV1.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
            if prior.authorization_receipt_sha256 != _sha(receipt_path):
                raise PermissionError("behavioral_execution_manifest_receipt_mismatch")
            if run_external:
                if prior.status == "dry_run_ready" and all(
                    item.attempt_count == 0 and item.status == "pending"
                    for item in prior.records
                ):
                    prior.run_external = True
                    prior.status = "running"
                    prior.updated_at = _now()
                    manifest = prior
                else:
                    if any(item.status == "running" for item in prior.records):
                        prior.status = "indeterminate"
                        for item in prior.records:
                            if item.status == "running":
                                item.status = "blocked_indeterminate"
                                item.first_failure = "prior_external_attempt_state_indeterminate"
                        prior.updated_at = _now()
                        _atomic(self.manifest_path, prior.model_dump(mode="json"))
                    raise PermissionError("behavioral_authorization_receipt_already_consumed")
            else:
                return prior
        src_root = Path(__file__).resolve().parents[1]
        if manifest is None:
            records = []
            budgets = (
                [request.solver_execution_budget]
                if isinstance(request, BehavioralAgentProtocolProbeAuthorizationRequestV1)
                else request.solver_execution_budgets
            )
            for budget in budgets:
                budget_path = self.budget_root / f"{budget.solver_model}.json"
                _atomic(budget_path, budget.model_dump(mode="json"))
                model_output = output / budget.solver_model
                command = [
                    str(python_path),
                    "-m",
                    "task_generator.v3_rw_task_eval_stirrup_wrapper",
                    str(fixture_root),
                    "--output",
                    str(model_output),
                    "-w",
                    "1",
                    "--model",
                    budget.solver_model,
                    "--budget-contract",
                    str(budget_path),
                ]
                records.append(
                    BehavioralPreflightExecutionRecordV1(
                        solver_model=budget.solver_model,
                        command=command,
                        budget_contract_path=str(budget_path),
                        budget_contract_sha256=_sha(budget_path),
                        output_root=str(model_output),
                    )
                )
            now = _now()
            manifest = BehavioralPreflightExecutionManifestV1(
                comparison_id=request.comparison_id,
                authorization_request_sha256=_sha(request_path),
                authorization_receipt_sha256=_sha(receipt_path),
                fixture_contract=request.fixture_contract,
                run_external=run_external,
                status="running" if run_external else "dry_run_ready",
                records=records,
                created_at=now,
                updated_at=now,
            )
        _atomic(self.manifest_path, manifest.model_dump(mode="json"))
        if not run_external:
            return manifest
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        for record in manifest.records:
            record.status = "running"
            record.attempt_count = 1
            record.started_at = _now()
            manifest.updated_at = record.started_at
            _atomic(self.manifest_path, manifest.model_dump(mode="json"))
            try:
                completed = command_runner(
                    record.command,
                    cwd=str(rw_root),
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=behavioral_request_timeout_seconds(request),
                    check=False,
                )
                record.returncode = completed.returncode
            except subprocess.TimeoutExpired as exc:
                record.status = "failed"
                record.first_failure = "solver_process_timeout"
                self._persist_process_logs(
                    record,
                    stdout=exc.stdout or "",
                    stderr=exc.stderr or "",
                )
            else:
                self._persist_process_logs(
                    record,
                    stdout=completed.stdout or "",
                    stderr=completed.stderr or "",
                )
                outcome_path = (
                    Path(record.output_root)
                    / "run_solver_tool_preflight"
                    / "solver_process_outcome.json"
                )
                if not outcome_path.is_file():
                    record.status = "failed"
                    record.first_failure = "solver_process_outcome_missing"
                else:
                    outcome = SolverProcessOutcomeV1.model_validate_json(
                        outcome_path.read_text(encoding="utf-8")
                    )
                    record.outcome_path = str(outcome_path)
                    record.outcome_sha256 = _sha(outcome_path)
                    record.first_failure = outcome.first_failure
                    budgets = (
                        [request.solver_execution_budget]
                        if isinstance(
                            request,
                            BehavioralAgentProtocolProbeAuthorizationRequestV1,
                        )
                        else request.solver_execution_budgets
                    )
                    budget = next(
                        item for item in budgets
                        if item.solver_model == record.solver_model
                    )
                    identity_valid = (
                        outcome.solver_model == record.solver_model
                        and outcome.budget == budget
                    )
                    record.status = "succeeded" if (
                        completed.returncode == 0
                        and outcome.process_status == "succeeded"
                        and identity_valid
                    ) else "failed"
                    if not identity_valid:
                        record.first_failure = "solver_process_outcome_identity_mismatch"
            record.finished_at = _now()
            manifest.updated_at = record.finished_at
            _atomic(self.manifest_path, manifest.model_dump(mode="json"))
        manifest.status = (
            "completed"
            if all(item.status == "succeeded" for item in manifest.records)
            else "blocked"
        )
        manifest.updated_at = _now()
        _atomic(self.manifest_path, manifest.model_dump(mode="json"))
        return manifest

    def _persist_process_logs(
        self,
        record: BehavioralPreflightExecutionRecordV1,
        *,
        stdout: str | bytes,
        stderr: str | bytes,
    ) -> None:
        output_root = Path(record.output_root).resolve()
        process_log_root = output_root.parents[1] / "process_logs"
        stdout_path = process_log_root / f"{record.solver_model}.stdout.txt"
        stderr_path = process_log_root / f"{record.solver_model}.stderr.txt"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_text = (
            stdout.decode("utf-8", errors="replace")
            if isinstance(stdout, bytes)
            else stdout
        )
        stderr_text = (
            stderr.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes)
            else stderr
        )
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        record.process_stdout_path = str(stdout_path)
        record.process_stdout_sha256 = _sha(stdout_path)
        record.process_stderr_path = str(stderr_path)
        record.process_stderr_sha256 = _sha(stderr_path)

    @staticmethod
    def _validate_public_fixture(
        input_root: Path,
        request: BehavioralPreflightAuthorizationRequestV2
        | BehavioralPreflightAuthorizationRequestV3
        | BehavioralAgentProtocolProbeAuthorizationRequestV1,
    ) -> None:
        cases = sorted(input_root.glob("*/dataset_row.json"))
        if len(cases) != 1:
            raise ValueError("behavioral_execution_requires_one_public_fixture")
        row = json.loads(cases[0].read_text(encoding="utf-8"))
        case_root = cases[0].parent
        extra = row.get("extra", {})
        checks = {
            "task_id": row.get("task_id") == "solver_tool_preflight",
            "tool_only": extra.get("tool_only_preflight") is True,
            "not_business": extra.get("business_task") is False,
            "no_grader": extra.get("grader_authorized") is False,
            "references": row.get("reference_files")
            == ["reference_files/copy_template.xlsx"],
            "deliverables": sorted(row.get("deliverable_files", []))
            == [
                "deliverable_files/created_workbook.xlsx",
                "deliverable_files/edited_template.xlsx",
            ],
            "contract": (case_root / "deliverable_contract.json").is_file(),
            "template": (case_root / "reference_files" / "copy_template.xlsx").is_file(),
        }
        serialized = json.dumps(row, ensure_ascii=False)
        checks["no_blind_ids"] = not any(
            item and item in serialized for item in request.frozen_blind_task_ids
        )
        allowed_files = {
            "dataset_row.json",
            "deliverable_contract.json",
            "prompt.md",
            "reference_files/copy_template.xlsx",
        }
        observed_files = {
            item.relative_to(case_root).as_posix()
            for item in case_root.rglob("*")
            if item.is_file()
        }
        checks["exact_public_file_set"] = observed_files == allowed_files
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(
                "behavioral_execution_public_fixture_invalid:" + ",".join(failed)
            )
