from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_matched_screening import (
    DeepSeekSolverPreflightAuthorizationRequestV1,
    MatchedScreeningCampaign,
    deepseek_solver_environment,
    validate_public_solver_fixture,
)
from task_generator.v3_solver_execution_budget import SolverProcessOutcomeV1
from task_generator.v3_source_fingerprint import governed_source_fingerprint


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha(root: Path) -> str:
    rows = [
        f"{path.relative_to(root).as_posix()}:{_sha(path)}"
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


class DeepSeekSolverPreflightAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal[
        "v3.deepseek_solver_preflight_authorization_receipt.1"
    ] = "v3.deepseek_solver_preflight_authorization_receipt.1"
    campaign_id: str
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    authorized_provider: Literal["deepseek"] = "deepseek"
    authorized_model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    authorized_scope: Literal["public_solver_tool_preflight"] = (
        "public_solver_tool_preflight"
    )
    fixture_tree_sha256: str = Field(min_length=64, max_length=64)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    maximum_provider_calls: Literal[8] = 8
    maximum_total_cost_usd: Literal[1.0] = 1.0
    provider_sdk_retries: Literal[0] = 0
    runner_retries: Literal[0] = 0
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: str
    private_package_upload_authorized: Literal[False] = False
    grader_authorized: Literal[False] = False
    business_execution_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class DeepSeekSolverPreflightReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.deepseek_solver_preflight_report.1"] = (
        "v3.deepseek_solver_preflight_report.1"
    )
    campaign_id: str
    solver_model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    status: Literal["pass", "fail", "incomplete"]
    eligible_for_business_eval: bool
    authorization_request_sha256: str
    authorization_receipt_sha256: str
    fixture_tree_sha256: str
    attempt_count: Literal[1] = 1
    provider_sdk_retries: Literal[0] = 0
    runner_retries: Literal[0] = 0
    process_returncode: Optional[int] = None
    outcome_path: Optional[str] = None
    outcome_sha256: Optional[str] = None
    stdout_path: str
    stdout_sha256: str
    stderr_path: str
    stderr_sha256: str
    first_failure: Optional[str] = None
    provider_calls: int = Field(ge=0, le=8)
    contract_cost_usd: float = Field(ge=0.0, le=1.0)
    private_packages_uploaded: Literal[False] = False
    grader_calls_made: Literal[False] = False
    created_at: str


class MatchedSolverPreflightGovernance:
    """Exact authorization and single-attempt execution for the public fixture."""

    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.campaign = MatchedScreeningCampaign(self.root)
        self.current_request = (
            self.root / "governance" / "deepseek_preflight_authorization_request.json"
        )

    def compile_receipt(
        self,
        *,
        authorization_request_path: str | Path,
        authorization_statement: str,
        expires_at: str,
    ) -> tuple[DeepSeekSolverPreflightAuthorizationReceiptV1, Path]:
        request_path = Path(authorization_request_path).resolve()
        request_sha = _sha(request_path)
        expected_parent = (
            self.root / "governance" / "deepseek_preflight_authorization_requests"
        ).resolve()
        if request_path.parent != expected_parent or request_path.name != f"{request_sha}.json":
            raise ValueError("deepseek_preflight_receipt_requires_immutable_exact_request")
        request = DeepSeekSolverPreflightAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_request(request, request_sha)
        receipt = DeepSeekSolverPreflightAuthorizationReceiptV1(
            campaign_id=request.campaign_id,
            authorization_request_sha256=request_sha,
            fixture_tree_sha256=request.fixture_tree_sha256,
            campaign_manifest_sha256=request.campaign_manifest_sha256,
            parity_report_sha256=request.parity_report_sha256,
            source_fingerprint=request.source_fingerprint,
            authorized_by_user=True,
            authorization_statement=authorization_statement,
            issued_at=_now(),
            expires_at=expires_at,
        )
        path = self.root / "governance" / "deepseek_preflight_authorization_receipt.json"
        if path.exists():
            raise FileExistsError("deepseek_preflight_receipt_already_exists")
        _write(path, receipt.model_dump(mode="json"))
        return receipt, path

    def execute(
        self,
        *,
        receipt_path: str | Path,
        fixture_root: str | Path,
        output_root: str | Path,
        real_world_python: str | Path,
        rw_task_root: str | Path,
        command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> tuple[DeepSeekSolverPreflightReportV1, Path]:
        receipt_file = Path(receipt_path).resolve()
        receipt = DeepSeekSolverPreflightAuthorizationReceiptV1.model_validate_json(
            receipt_file.read_text(encoding="utf-8")
        )
        request_sha = receipt.authorization_request_sha256
        request_path = (
            self.root / "governance" / "deepseek_preflight_authorization_requests"
            / f"{request_sha}.json"
        )
        request = DeepSeekSolverPreflightAuthorizationRequestV1.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self._validate_request(request, request_sha)
        for key in (
            "campaign_id", "fixture_tree_sha256", "campaign_manifest_sha256",
            "parity_report_sha256", "source_fingerprint",
        ):
            if getattr(receipt, key) != getattr(request, key):
                raise PermissionError(f"deepseek_preflight_receipt_{key}_mismatch")
        expires = datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
        if expires <= datetime.now(timezone.utc):
            raise PermissionError("deepseek_preflight_receipt_expired")
        fixture = Path(fixture_root).resolve()
        if _tree_sha(fixture) != request.fixture_tree_sha256:
            raise PermissionError("deepseek_preflight_fixture_tree_drift")
        try:
            fixture.relative_to(self.root)
            output = Path(output_root).resolve()
            output.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("deepseek_preflight_paths_must_be_inside_campaign") from exc
        validate_public_solver_fixture(fixture)
        python_path = Path(real_world_python).resolve()
        rw_root = Path(rw_task_root).resolve()
        if not python_path.is_file() or not rw_root.is_dir():
            raise FileNotFoundError("deepseek_preflight_runtime_missing")
        run_root = output / request_sha
        report_path = run_root / "deepseek_solver_preflight_report.json"
        state_path = run_root / "execution_state.json"
        if state_path.exists() or report_path.exists():
            raise PermissionError("deepseek_preflight_receipt_already_consumed")
        _write(
            state_path,
            {
                "state_version": "v3.deepseek_solver_preflight_execution_state.1",
                "status": "running",
                "authorization_request_sha256": request_sha,
                "authorization_receipt_sha256": _sha(receipt_file),
                "attempt_count": 1,
                "started_at": _now(),
            },
        )
        budget_path = run_root / "solver_execution_budget.json"
        _write(budget_path, request.solver_budget.model_dump(mode="json"))
        solver_output = run_root / "solver"
        command = [
            str(python_path), "-m", "task_generator.v3_rw_task_eval_stirrup_wrapper",
            str(fixture), "--output", str(solver_output), "-w", "1",
            "--model", request.model, "--budget-contract", str(budget_path),
        ]
        src_root = Path(__file__).resolve().parents[1]
        env = deepseek_solver_environment()
        env["PYTHONPATH"] = str(src_root)
        stdout_path = run_root / "process.stdout.txt"
        stderr_path = run_root / "process.stderr.txt"
        returncode: Optional[int] = None
        failure: Optional[str] = None
        try:
            completed = command_runner(
                command, cwd=str(rw_root), env=env, text=True, encoding="utf-8",
                errors="replace", capture_output=True, timeout=900, check=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            failure = "solver_process_timeout"
        secret = env.get("AGENT_API_KEY", "")
        if secret:
            stdout = stdout.replace(secret, "[REDACTED]") if isinstance(stdout, str) else stdout
            stderr = stderr.replace(secret, "[REDACTED]") if isinstance(stderr, str) else stderr
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(stdout if isinstance(stdout, str) else stdout.decode("utf-8", "replace"), encoding="utf-8")
        stderr_path.write_text(stderr if isinstance(stderr, str) else stderr.decode("utf-8", "replace"), encoding="utf-8")
        outcome_path = solver_output / "run_solver_tool_preflight" / "solver_process_outcome.json"
        outcome = None
        if outcome_path.is_file():
            outcome = SolverProcessOutcomeV1.model_validate_json(
                outcome_path.read_text(encoding="utf-8")
            )
            if outcome.solver_model != request.model or outcome.budget != request.solver_budget:
                failure = "solver_process_outcome_identity_mismatch"
            elif outcome.process_status != "succeeded":
                failure = outcome.first_failure or "solver_process_failed"
        else:
            failure = failure or "solver_process_outcome_missing"
        if returncode not in (None, 0):
            failure = failure or "solver_process_nonzero_exit"
        passed = failure is None and outcome is not None
        report = DeepSeekSolverPreflightReportV1(
            campaign_id=request.campaign_id,
            status="pass" if passed else "fail",
            eligible_for_business_eval=passed,
            authorization_request_sha256=request_sha,
            authorization_receipt_sha256=_sha(receipt_file),
            fixture_tree_sha256=request.fixture_tree_sha256,
            process_returncode=returncode,
            outcome_path=str(outcome_path) if outcome_path.is_file() else None,
            outcome_sha256=_sha(outcome_path) if outcome_path.is_file() else None,
            stdout_path=str(stdout_path), stdout_sha256=_sha(stdout_path),
            stderr_path=str(stderr_path), stderr_sha256=_sha(stderr_path),
            first_failure=failure,
            provider_calls=outcome.usage.provider_calls if outcome else 0,
            contract_cost_usd=outcome.usage.contract_cost_usd if outcome else 0.0,
            created_at=_now(),
        )
        _write(report_path, report.model_dump(mode="json"))
        _write(
            state_path,
            {
                "state_version": "v3.deepseek_solver_preflight_execution_state.1",
                "status": "completed",
                "authorization_request_sha256": request_sha,
                "authorization_receipt_sha256": _sha(receipt_file),
                "attempt_count": 1,
                "report_sha256": _sha(report_path),
                "finished_at": _now(),
            },
        )
        return report, report_path

    def _validate_request(
        self, request: DeepSeekSolverPreflightAuthorizationRequestV1, request_sha: str
    ) -> None:
        campaign = self.campaign.read()
        immutable = (
            self.root / "governance" / "deepseek_preflight_authorization_requests"
            / f"{request_sha}.json"
        )
        parity = Path(request.parity_report_path)
        repository_root = Path(__file__).resolve().parents[2]
        checks = {
            "active_request": self.current_request.is_file() and _sha(self.current_request) == request_sha,
            "immutable_request": immutable.is_file() and _sha(immutable) == request_sha,
            "campaign_id": request.campaign_id == campaign.campaign_id,
            "campaign_manifest": request.campaign_manifest_sha256 == _sha(self.campaign.manifest_path),
            "parity": parity.is_file() and _sha(parity) == request.parity_report_sha256,
            "source": request.source_fingerprint == governed_source_fingerprint(repository_root),
            "campaign_source": request.source_fingerprint == campaign.source_fingerprint,
        }
        failed = sorted(key for key, value in checks.items() if not value)
        if failed:
            raise PermissionError("deepseek_preflight_request_state_mismatch:" + ",".join(failed))

    @staticmethod
    def _validate_public_fixture(root: Path) -> None:
        validate_public_solver_fixture(root)
