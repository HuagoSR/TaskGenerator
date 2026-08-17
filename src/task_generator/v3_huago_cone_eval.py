from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_codex_local_solver import inspect_delivery


StackId = Literal[
    "gpt-5.6-sol@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "gemini-3.1-pro-preview@tuzi_opencode",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic(path: Path, value: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_secret(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip().replace("\r", "")
    if not value:
        raise ValueError("empty_secret")
    return value


def _read_env(path: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().replace("\r", "")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _redact(text: str, secrets: List[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _run(command: List[str], *, cwd: Path, env: Dict[str, str], stdin: str, timeout: int):
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        except Exception:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                pass
        stdout, stderr = process.communicate()
    return process.returncode, timed_out, time.monotonic() - started, stdout or "", stderr or ""


class R9SolverOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_version: Literal["v3.r9_solver_outcome.1"] = "v3.r9_solver_outcome.1"
    stack_id: StackId
    kind: Literal["public_probe", "private_task"]
    task_id: str
    status: Literal["pass", "task_failed", "infrastructure_failed"]
    started_at: str
    completed_at: str
    duration_seconds: float
    returncode: Optional[int]
    timed_out: bool
    command_identity: List[str]
    stdout_path: str
    stdout_sha256: str
    stderr_path: str
    stderr_sha256: str
    delivery: dict
    first_failure: Optional[str] = None


class R9SolverCampaignV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.r9_solver_campaign.1"] = "v3.r9_solver_campaign.1"
    stack_id: StackId
    package_generation_sha256: str
    public_probe_status: Literal["not_started", "pass", "incompatible_stack"]
    task_states: Dict[str, Literal["not_started", "running", "completed", "interrupted"]]
    outcome_paths: Dict[str, str] = Field(default_factory=dict)
    valid_delivery_count: int = 0
    infrastructure_failure_count: int = 0
    task_failure_count: int = 0
    canary_infrastructure_failed: bool = False
    frozen_after_systemic_failures: bool = False
    created_at: str
    updated_at: str


class R9NativeSolverRunner:
    def __init__(
        self,
        *,
        stack_id: StackId,
        output_root: str | Path,
        codex_auth_path: str | Path = "/home/taskgenerator/.codex/auth.json",
        deepseek_key_path: str | Path = "/run/secrets/deepseek_api_key",
        tuzi_env_path: str | Path = "/run/secrets/eval_tuzi_env",
        timeout_seconds: int = 1800,
    ) -> None:
        self.stack_id = stack_id
        self.output = Path(output_root).resolve()
        self.codex_auth = Path(codex_auth_path)
        self.deepseek_key = Path(deepseek_key_path)
        self.tuzi_env = Path(tuzi_env_path)
        self.timeout = timeout_seconds

    def public_probe(self) -> R9SolverOutcomeV1:
        workspace = self.output / "public_probe" / "workspace"
        if workspace.exists():
            raise FileExistsError("r9_public_probe_workspace_exists")
        workspace.mkdir(parents=True)
        expected = "deliverable_files/public_probe.xlsx"
        prompt = (
            "Create deliverable_files/public_probe.xlsx with Python/openpyxl. "
            "Use a Summary sheet, three named columns, at least two data rows and one formula. "
            "Reopen the saved workbook to verify it. Do not copy another workbook."
        )
        (workspace / "TASK.md").write_text(prompt, encoding="utf-8")
        (workspace / "deliverable_files").mkdir()
        outcome = self._execute(
            kind="public_probe", task_id="public_xlsx_probe", workspace=workspace,
            prompt=prompt, expected=expected, input_hashes=set(), timeout=min(self.timeout, 300),
        )
        _atomic(self.output / "public_probe" / "outcome.json", outcome)
        return outcome

    def solve(self, *, generation_result_path: str | Path) -> R9SolverCampaignV1:
        generation_path = Path(generation_result_path).resolve()
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        cases = [item for item in generation["cases"] if item["status"] == "materialized"]
        probe_path = self.output / "public_probe" / "outcome.json"
        if not probe_path.is_file():
            raise FileNotFoundError("r9_public_probe_missing")
        probe = R9SolverOutcomeV1.model_validate_json(probe_path.read_text(encoding="utf-8"))
        if probe.status != "pass":
            raise PermissionError("r9_public_probe_not_passed")
        manifest_path = self.output / "solver_campaign.json"
        if manifest_path.exists():
            manifest = R9SolverCampaignV1.model_validate_json(manifest_path.read_text(encoding="utf-8"))
            if any(value == "running" for value in manifest.task_states.values()):
                raise RuntimeError("r9_interrupted_task_requires_review")
        else:
            manifest = R9SolverCampaignV1(
                stack_id=self.stack_id,
                package_generation_sha256=_sha(generation_path),
                public_probe_status="pass",
                task_states={item["blind_task_id"]: "not_started" for item in cases},
                created_at=_now(), updated_at=_now(),
            )
            _atomic(manifest_path, manifest)
        by_domain: Dict[str, List[dict]] = {"audit_compliance": [], "procurement_operations": []}
        for case in cases:
            row = json.loads((Path(case["package_root"]) / "rw_task_export" / "dataset_row.json").read_text(encoding="utf-8"))
            by_domain[row["sector"]].append(case)
        ordered = [by_domain["audit_compliance"][0], by_domain["procurement_operations"][0]]
        ordered += [item for item in cases if item not in ordered]
        consecutive_infra = 0
        for position, case in enumerate(ordered):
            task_id = case["blind_task_id"]
            if manifest.task_states[task_id] != "not_started":
                continue
            manifest.task_states[task_id] = "running"
            manifest.updated_at = _now()
            _atomic(manifest_path, manifest)
            package = Path(case["package_root"])
            workspace = self.output / "tasks" / task_id / "workspace"
            self._stage(package, workspace)
            contract = json.loads((workspace / "deliverable_contract.json").read_text(encoding="utf-8"))
            expected = contract["deliverables"][0]["relative_path"]
            input_hashes = {_sha(path) for path in (workspace / "reference_files").glob("*.xlsx")}
            prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
            outcome = self._execute(
                kind="private_task", task_id=task_id, workspace=workspace,
                prompt=prompt, expected=expected, input_hashes=input_hashes, timeout=self.timeout,
            )
            outcome_path = self.output / "tasks" / task_id / "outcome.json"
            _atomic(outcome_path, outcome)
            manifest.outcome_paths[task_id] = str(outcome_path)
            manifest.task_states[task_id] = "completed"
            if outcome.status == "pass":
                manifest.valid_delivery_count += 1
                consecutive_infra = 0
            elif outcome.status == "infrastructure_failed":
                manifest.infrastructure_failure_count += 1
                consecutive_infra += 1
            else:
                manifest.task_failure_count += 1
                consecutive_infra = 0
            if position < 2 and outcome.status == "infrastructure_failed":
                manifest.canary_infrastructure_failed = True
                manifest.updated_at = _now()
                _atomic(manifest_path, manifest)
                break
            if consecutive_infra >= 3:
                manifest.frozen_after_systemic_failures = True
                manifest.updated_at = _now()
                _atomic(manifest_path, manifest)
                break
            manifest.updated_at = _now()
            _atomic(manifest_path, manifest)
        return manifest

    @staticmethod
    def _stage(package: Path, workspace: Path) -> None:
        if workspace.exists():
            raise FileExistsError("r9_task_workspace_exists")
        workspace.mkdir(parents=True)
        candidate = package / "candidate"
        shutil.copy2(candidate / "prompt.md", workspace / "TASK.md")
        shutil.copy2(candidate / "deliverable_contract.json", workspace / "deliverable_contract.json")
        shutil.copytree(candidate / "reference_files", workspace / "reference_files")
        (workspace / "deliverable_files").mkdir()

    def _execute(
        self, *, kind: str, task_id: str, workspace: Path, prompt: str,
        expected: str, input_hashes: set[str], timeout: int,
    ) -> R9SolverOutcomeV1:
        started_at = _now()
        env = os.environ.copy()
        secrets: List[str] = []
        if self.stack_id == "gpt-5.6-sol@chatgpt_codex":
            codex_home = workspace / ".codex"
            codex_home.mkdir()
            (codex_home / "auth.json").symlink_to(self.codex_auth)
            env["CODEX_HOME"] = str(codex_home)
            command = [
                "codex", "--ask-for-approval", "never", "--model", "gpt-5.6-sol", "exec",
                "-c", "project_doc_max_bytes=0", "-c", "agents.enabled=false",
                "--disable", "plugins", "--disable", "apps", "--disable", "multi_agent",
                "--disable", "skill_search", "--json", "--ephemeral", "--ignore-user-config",
                "--ignore-rules", "--sandbox", "danger-full-access", "--skip-git-repo-check",
                "-C", str(workspace), "-",
            ]
            stdin = prompt
        else:
            if self.stack_id == "deepseek-v4-pro@official_opencode":
                key = _read_secret(self.deepseek_key)
                env["DEEPSEEK_API_KEY"] = key
                secrets.append(key)
                model = "deepseek/deepseek-v4-pro"
            else:
                values = _read_env(self.tuzi_env)
                key = values["TUZI_API_KEY"]
                base = values["TUZI_BASE_URL"]
                env.update({"TUZI_API_KEY": key, "TUZI_BASE_URL": base})
                secrets.append(key)
                config = {
                    "$schema": "https://opencode.ai/config.json",
                    "provider": {"tuzi": {
                        "npm": "@ai-sdk/openai-compatible", "name": "Tuzi OpenAI-compatible",
                        "options": {"baseURL": "{env:TUZI_BASE_URL}", "apiKey": "{env:TUZI_API_KEY}"},
                        "models": {"gemini-3.1-pro-preview": {"name": "Gemini 3.1 Pro Preview",
                            "limit": {"context": 65536, "output": 8192}}},
                    }},
                }
                (workspace / "opencode.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
                model = "tuzi/gemini-3.1-pro-preview"
            command = ["opencode", "run", "--format", "json", "--model", model,
                       "--auto", "--dir", str(workspace),
                       "Read TASK.md and the reference_files directory. Complete the task and save the exact required XLSX."]
            stdin = ""
        code, timed_out, duration, stdout, stderr = _run(
            command, cwd=workspace, env=env, stdin=stdin, timeout=timeout
        )
        stdout = _redact(stdout, secrets)
        stderr = _redact(stderr, secrets)
        if any(secret in stdout or secret in stderr for secret in secrets):
            raise RuntimeError("r9_solver_secret_redaction_failed")
        artifact_root = workspace.parent
        stdout_path = artifact_root / ("codex.jsonl" if self.stack_id.startswith("gpt") else "opencode.jsonl")
        stderr_path = artifact_root / "stderr.txt"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        delivery = inspect_delivery(workspace, expected, input_hashes)
        lowered = stderr.lower()
        infrastructure = timed_out or any(marker in lowered for marker in (
            "unauthorized", "authentication", "connection", "connecterror", "remoteprotocolerror",
            "stream disconnected", "getaddrinfo", "internal server error", "rate limit",
        ))
        if code == 0 and delivery.valid:
            status, failure = "pass", None
        elif infrastructure:
            status, failure = "infrastructure_failed", "timeout_or_provider_failure"
        else:
            status, failure = "task_failed", delivery.failure or "agent_process_failed"
        return R9SolverOutcomeV1(
            stack_id=self.stack_id, kind=kind, task_id=task_id, status=status,
            started_at=started_at, completed_at=_now(), duration_seconds=round(duration, 3),
            returncode=code, timed_out=timed_out,
            command_identity=["codex", "exec"] if self.stack_id.startswith("gpt") else ["opencode", "run"],
            stdout_path=str(stdout_path), stdout_sha256=_sha(stdout_path),
            stderr_path=str(stderr_path), stderr_sha256=_sha(stderr_path),
            delivery=delivery.model_dump(mode="json"), first_failure=failure,
        )
