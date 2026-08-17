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
from task_generator.v3_codex_local_grader import _strict_output_schema
from task_generator.v3_compact_screening_grader import (
    CompactGraderDraftV2,
    CompactGraderReviewV2,
)
from task_generator.v3_matched_screening import RUBRIC_WEIGHTS
from task_generator.v3_huago_cone_production import (
    JudgeScoreV1,
    ModelTaskEvaluationV1,
)


StackId = Literal[
    "gpt-5.6-sol@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "gemini-3.1-pro-preview@tuzi_opencode",
]
JudgeId = Literal[
    "gpt-5.6-sol@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
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


class R9JudgeRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: Literal["v3.r9_judge_record.1"] = "v3.r9_judge_record.1"
    task_id: str
    judge_id: JudgeId
    status: Literal[
        "pending", "not_eligible", "completed", "infrastructure_failed", "format_failed"
    ]
    attempt_count: int = Field(ge=0, le=2)
    review_path: Optional[str] = None
    review_sha256: Optional[str] = None
    raw_paths: List[str] = Field(default_factory=list, max_length=2)
    first_failure: Optional[str] = None
    duration_seconds: float = 0.0


class R9JudgeManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.r9_judge_manifest.1"] = "v3.r9_judge_manifest.1"
    judge_id: JudgeId
    solver_campaign_sha256: str = Field(min_length=64, max_length=64)
    generation_result_sha256: str = Field(min_length=64, max_length=64)
    records: Dict[str, R9JudgeRecordV1]
    completed_count: int = 0
    infrastructure_failed_count: int = 0
    format_failed_count: int = 0
    created_at: str
    updated_at: str


class R9EvaluationRecordSetV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_set_version: Literal["v3.r9_evaluation_record_set.1"] = (
        "v3.r9_evaluation_record_set.1"
    )
    generation_result_sha256: str = Field(min_length=64, max_length=64)
    solver_campaign_sha256: Dict[str, str]
    judge_manifest_sha256: Dict[str, Dict[str, str]]
    records: List[ModelTaskEvaluationV1]
    created_at: str


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
            if manifest.stack_id != self.stack_id:
                raise ValueError("r9_solver_manifest_stack_mismatch")
            if manifest.package_generation_sha256 != _sha(generation_path):
                raise ValueError("r9_solver_generation_result_drift")
            if set(manifest.task_states) != {item["blind_task_id"] for item in cases}:
                raise ValueError("r9_solver_task_set_drift")
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
        try:
            code, timed_out, duration, stdout, stderr = _run(
                command, cwd=workspace, env=env, stdin=stdin, timeout=timeout
            )
        finally:
            # The authentication mount/link is process-scoped and must never remain
            # in the persisted solver workspace or output tree.
            shutil.rmtree(workspace / ".codex", ignore_errors=True)
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


def _grade_prompt(task_id: str, *, format_feedback: Optional[str] = None) -> str:
    suffix = (
        "\nThe previous attempt failed only JSON/schema validation. Preserve the same substantive "
        "judgment and emit a contract-valid object. Previous failure: " + format_feedback
        if format_feedback
        else ""
    )
    return f"""You are independently grading one route-blind professional XLSX work product.
Read candidate_prompt.json, rubric.json, fact_anchors.json and grade_schema.json. Inspect
deliverable.xlsx with Python/openpyxl. Never infer or mention the solver or generation route.

Return exactly one JSON object matching grade_schema.json with blind_task_id={task_id}.
Score all seven dimensions 0-4. Score 3 means professionally adequate and contract-complete.
Score 4 requires specific exceptional_evidence beyond the explicit contract. Every score <=2
requires a concise criterion-bound finding. Use at most five findings and two exceptional
evidence records. Do not modify deliverable.xlsx. For OpenCode, write the JSON object to
grade.raw.json using Python's json module and also return it as the final response.{suffix}
"""


class R9DualJudgeRunner:
    def __init__(
        self,
        *,
        judge_id: JudgeId,
        output_root: str | Path,
        codex_auth_path: str | Path = "/home/taskgenerator/.codex/auth.json",
        deepseek_key_path: str | Path = "/run/secrets/deepseek_api_key",
        timeout_seconds: int = 1800,
    ) -> None:
        self.judge_id = judge_id
        self.output = Path(output_root).resolve()
        self.codex_auth = Path(codex_auth_path)
        self.deepseek_key = Path(deepseek_key_path)
        self.timeout = timeout_seconds

    def grade(
        self,
        *,
        solver_campaign_path: str | Path,
        generation_result_path: str | Path,
    ) -> R9JudgeManifestV1:
        solver_path = Path(solver_campaign_path).resolve()
        generation_path = Path(generation_result_path).resolve()
        solver = R9SolverCampaignV1.model_validate_json(
            solver_path.read_text(encoding="utf-8")
        )
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        packages = {item["blind_task_id"]: Path(item["package_root"]) for item in generation["cases"]}
        manifest_path = self.output / "judge_manifest.json"
        if manifest_path.exists():
            manifest = R9JudgeManifestV1.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            if manifest.judge_id != self.judge_id:
                raise ValueError("r9_judge_manifest_judge_mismatch")
            if manifest.solver_campaign_sha256 != _sha(solver_path):
                raise ValueError("r9_judge_solver_campaign_drift")
            if manifest.generation_result_sha256 != _sha(generation_path):
                raise ValueError("r9_judge_generation_result_drift")
        else:
            records: Dict[str, R9JudgeRecordV1] = {}
            for task_id, outcome_path in solver.outcome_paths.items():
                outcome = R9SolverOutcomeV1.model_validate_json(
                    Path(outcome_path).read_text(encoding="utf-8")
                )
                records[task_id] = R9JudgeRecordV1(
                    task_id=task_id,
                    judge_id=self.judge_id,
                    status="not_eligible" if outcome.status != "pass" else "pending",
                    attempt_count=0,
                    first_failure=("solver_delivery_not_eligible" if outcome.status != "pass" else None),
                )
            manifest = R9JudgeManifestV1(
                judge_id=self.judge_id,
                solver_campaign_sha256=_sha(solver_path),
                generation_result_sha256=_sha(generation_path),
                records=records,
                created_at=_now(), updated_at=_now(),
            )
            _atomic(manifest_path, manifest)
        for task_id, record in manifest.records.items():
            if record.status != "pending" or record.attempt_count:
                continue
            outcome_path = Path(solver.outcome_paths[task_id])
            outcome = R9SolverOutcomeV1.model_validate_json(outcome_path.read_text(encoding="utf-8"))
            delivery = outcome_path.parent / "workspace" / outcome.delivery["relative_path"]
            package = packages[task_id]
            task_root = self.output / "tasks" / task_id
            feedback: Optional[str] = None
            total_duration = 0.0
            for attempt in (1, 2):
                workspace = task_root / f"attempt_{attempt:02d}" / "workspace"
                self._stage(package, delivery, workspace, task_id, feedback)
                record.attempt_count = attempt
                manifest.updated_at = _now()
                _atomic(manifest_path, manifest)
                raw_path, status, failure, duration = self._run_one(workspace, task_id)
                total_duration += duration
                record.raw_paths.append(str(raw_path))
                if status == "infrastructure_failed":
                    record.status = "infrastructure_failed"
                    record.first_failure = record.first_failure or failure
                    break
                try:
                    draft = CompactGraderDraftV2.model_validate_json(raw_path.read_text(encoding="utf-8"))
                    if draft.blind_task_id != task_id:
                        raise ValueError("r9_grader_blind_task_id_mismatch")
                    scores = draft.scores.by_criterion_id()
                    weighted = round(sum((scores[key] / 4.0) * RUBRIC_WEIGHTS[key] for key in RUBRIC_WEIGHTS), 6)
                    review = CompactGraderReviewV2(
                        **draft.model_dump(mode="json"), weighted_score=weighted,
                        professional_plausibility=("pass" if weighted >= 0.625 and not draft.major_defect else "fail"),
                    )
                    review_path = task_root / "review.json"
                    _atomic(review_path, review)
                    record.status = "completed"
                    record.review_path = str(review_path)
                    record.review_sha256 = _sha(review_path)
                    record.first_failure = None
                    break
                except Exception as exc:
                    feedback = f"{type(exc).__name__}:{exc}"[:500]
                    record.first_failure = record.first_failure or feedback
                    record.status = "format_failed"
                    if attempt == 2:
                        break
            record.duration_seconds = round(total_duration, 3)
            manifest.updated_at = _now()
            _atomic(manifest_path, manifest)
        manifest.completed_count = sum(item.status == "completed" for item in manifest.records.values())
        manifest.infrastructure_failed_count = sum(item.status == "infrastructure_failed" for item in manifest.records.values())
        manifest.format_failed_count = sum(item.status == "format_failed" for item in manifest.records.values())
        manifest.updated_at = _now()
        _atomic(manifest_path, manifest)
        return manifest

    @staticmethod
    def _stage(
        package: Path, delivery: Path, workspace: Path, task_id: str,
        feedback: Optional[str],
    ) -> None:
        if workspace.exists():
            raise FileExistsError("r9_grader_workspace_exists")
        workspace.mkdir(parents=True)
        shutil.copy2(package / "rw_task_export" / "dataset_row.json", workspace / "candidate_prompt.json")
        shutil.copy2(package / "teacher" / "rubric_plan_v2.json", workspace / "rubric.json")
        shutil.copy2(package / "teacher" / "deterministic_fact_anchors.json", workspace / "fact_anchors.json")
        shutil.copy2(delivery, workspace / "deliverable.xlsx")
        schema = _strict_output_schema(CompactGraderDraftV2.model_json_schema())
        (workspace / "grade_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        (workspace / "TASK.md").write_text(_grade_prompt(task_id, format_feedback=feedback), encoding="utf-8")

    def _run_one(self, workspace: Path, task_id: str):
        env = os.environ.copy()
        secrets: List[str] = []
        raw_path = workspace / "grade.raw.json"
        prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
        if self.judge_id == "gpt-5.6-sol@chatgpt_codex":
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
                "--output-schema", str(workspace / "grade_schema.json"),
                "--output-last-message", str(raw_path), "-C", str(workspace), "-",
            ]
            stdin = prompt
        else:
            key = _read_secret(self.deepseek_key)
            env["DEEPSEEK_API_KEY"] = key
            secrets.append(key)
            command = [
                "opencode", "run", "--format", "json", "--model", "deepseek/deepseek-v4-pro",
                "--auto", "--dir", str(workspace), "Read TASK.md and complete the grading contract.",
            ]
            stdin = ""
        try:
            code, timed_out, duration, stdout, stderr = _run(
                command, cwd=workspace, env=env, stdin=stdin, timeout=self.timeout
            )
        finally:
            shutil.rmtree(workspace / ".codex", ignore_errors=True)
        stdout = _redact(stdout, secrets)
        stderr = _redact(stderr, secrets)
        attempt_root = workspace.parent
        (attempt_root / "judge.jsonl").write_text(stdout, encoding="utf-8")
        (attempt_root / "stderr.txt").write_text(stderr, encoding="utf-8")
        lowered = stderr.lower()
        infrastructure = timed_out or any(marker in lowered for marker in (
            "unauthorized", "authentication", "connection", "connecterror", "remoteprotocolerror",
            "stream disconnected", "getaddrinfo", "internal server error", "rate limit",
        ))
        if infrastructure or code != 0:
            return raw_path, "infrastructure_failed", "timeout_or_provider_failure", duration
        if not raw_path.is_file():
            # OpenCode sometimes returns the JSON as final text without writing the requested file.
            for line in reversed(stdout.splitlines()):
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                text = ((event.get("part") or {}).get("text")) if isinstance(event, dict) else None
                if isinstance(text, str) and text.strip().startswith("{"):
                    raw_path.write_text(text.strip(), encoding="utf-8")
                    break
        if not raw_path.is_file():
            raw_path.write_text("", encoding="utf-8")
        return raw_path, "format_candidate", None, duration


def compile_r9_evaluation_records(
    *,
    generation_result_path: str | Path,
    solver_campaign_paths: Dict[str, str | Path],
    judge_manifest_paths: Dict[str, Dict[str, str | Path]],
    output_path: str | Path,
) -> R9EvaluationRecordSetV1:
    """Bind delivery admission and both programmed judge reviews for aggregation."""
    generation_path = Path(generation_result_path).resolve()
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    task_ids = [item["blind_task_id"] for item in generation["cases"]]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("r9_evaluation_duplicate_task_id")
    records: List[ModelTaskEvaluationV1] = []
    solver_hashes: Dict[str, str] = {}
    judge_hashes: Dict[str, Dict[str, str]] = {}
    for solver_id, raw_solver_path in solver_campaign_paths.items():
        solver_path = Path(raw_solver_path).resolve()
        solver = R9SolverCampaignV1.model_validate_json(
            solver_path.read_text(encoding="utf-8")
        )
        if solver.stack_id != solver_id:
            raise ValueError("r9_evaluation_solver_identity_mismatch")
        if set(solver.task_states) != set(task_ids):
            raise ValueError("r9_evaluation_solver_task_set_mismatch")
        solver_hashes[solver_id] = _sha(solver_path)
        manifests: Dict[str, R9JudgeManifestV1] = {}
        judge_hashes[solver_id] = {}
        for judge_id in (
            "gpt-5.6-sol@chatgpt_codex",
            "deepseek-v4-pro@official_opencode",
        ):
            try:
                raw_judge_path = judge_manifest_paths[solver_id][judge_id]
            except KeyError as exc:
                raise ValueError("r9_evaluation_missing_judge_manifest") from exc
            judge_path = Path(raw_judge_path).resolve()
            manifest = R9JudgeManifestV1.model_validate_json(
                judge_path.read_text(encoding="utf-8")
            )
            if manifest.judge_id != judge_id:
                raise ValueError("r9_evaluation_judge_identity_mismatch")
            if manifest.solver_campaign_sha256 != solver_hashes[solver_id]:
                raise ValueError("r9_evaluation_judge_solver_binding_mismatch")
            if manifest.generation_result_sha256 != _sha(generation_path):
                raise ValueError("r9_evaluation_judge_generation_binding_mismatch")
            if set(manifest.records) != set(task_ids):
                raise ValueError("r9_evaluation_judge_task_set_mismatch")
            manifests[judge_id] = manifest
            judge_hashes[solver_id][judge_id] = _sha(judge_path)
        for task_id in task_ids:
            outcome_path = solver.outcome_paths.get(task_id)
            delivery_valid = False
            if outcome_path:
                outcome = R9SolverOutcomeV1.model_validate_json(
                    Path(outcome_path).read_text(encoding="utf-8")
                )
                delivery_valid = outcome.status == "pass" and bool(outcome.delivery.get("valid"))
            judges: List[JudgeScoreV1] = []
            for judge_id, manifest in manifests.items():
                item = manifest.records[task_id]
                if item.status == "completed" and item.review_path:
                    review_path = Path(item.review_path)
                    if _sha(review_path) != item.review_sha256:
                        raise ValueError("r9_evaluation_review_hash_mismatch")
                    review = CompactGraderReviewV2.model_validate_json(
                        review_path.read_text(encoding="utf-8")
                    )
                    if review.blind_task_id != task_id:
                        raise ValueError("r9_evaluation_review_task_mismatch")
                    judges.append(
                        JudgeScoreV1(
                            judge_id=judge_id,
                            valid=True,
                            weighted_score=review.weighted_score,
                            major_defect=review.major_defect,
                        )
                    )
                else:
                    judges.append(JudgeScoreV1(judge_id=judge_id, valid=False))
            records.append(
                ModelTaskEvaluationV1(
                    task_id=task_id,
                    solver_id=solver_id,
                    delivery_valid=delivery_valid,
                    judges=judges,
                )
            )
    result = R9EvaluationRecordSetV1(
        generation_result_sha256=_sha(generation_path),
        solver_campaign_sha256=solver_hashes,
        judge_manifest_sha256=judge_hashes,
        records=records,
        created_at=_now(),
    )
    _atomic(Path(output_path), result)
    return result
