"""Run the four frozen R10 Scenario-First tasks through two native agent stacks.

The runner is deliberately a one-off pilot harness.  It stages only candidate
material for solvers and only grading inputs for judges; it does not reuse the
R9 package format or mutate any R10 task package.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.core.deliverable_contract import DeliverableContractV1
from task_generator.evaluation.r10_behavioral import (
    R10BehavioralScopeV1,
    R10JudgeDraftV1,
    R10ModelTaskResultV1,
    R10SolverOutcomeV1,
    aggregate_behavioral_result,
    binding_from_task,
    finalize_judge_review,
    inspect_delivery,
    sha256_file,
    sha256_json,
)
from task_generator.planning.scenario_task_compiler import (
    TaskCompilationOutputV1,
    TaskSpecificRubricV1,
)
from run_r10_skill_compiler import IMAGE, _run, _ssh


IMAGE_SHA256 = "02b79e7f6c1b9966918fc986c7624f50c2f45c6e32a5502bc30f65ccd328a722"
STACKS = ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode")
TASK_ROOTS = {
    "r10_audit_revenue_evidence_reliability": (ROOT / "artifacts/r10/r10_6_task_compilation_20260831_execute3/tasks/r10_audit_revenue_evidence_reliability", "audit_compliance"),
    "r10_procurement_price_reasonableness": (ROOT / "artifacts/r10/r10_6_task_compilation_20260831_execute3/tasks/r10_procurement_price_reasonableness", "procurement_operations"),
    "r10_audit_control_deficiency_evaluation": (ROOT / "artifacts/r10/r10_7a_task_compilation_20260831/tasks/r10_audit_control_deficiency_evaluation", "audit_compliance"),
    "r10_procurement_delivery_acceptance": (ROOT / "artifacts/r10/r10_7a_task_compilation_20260831/tasks/r10_procurement_delivery_acceptance", "procurement_operations"),
}
INFRA_MARKERS = (
    "authentication", "authorization", "not logged in", "unauthorized", "connection", "connecterror",
    "remoteprotocolerror", "stream disconnected", "getaddrinfo", "internal server error", "rate limit",
    "service unavailable", "timeout", "tls", "dns",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _task_bindings():
    return [binding_from_task(path, domain=domain) for path, domain in TASK_ROOTS.values()]


def _scope(run_id: str) -> R10BehavioralScopeV1:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    return R10BehavioralScopeV1(campaign_id=run_id, source_commit=commit, image=IMAGE, image_sha256=IMAGE_SHA256, bindings=_task_bindings())


def _safe_remote_root(host: str, run_id: str) -> str:
    home = _ssh(host, 'printf %s "$HOME"', timeout=120).stdout.strip()
    if not home or any(token in run_id for token in ("/", "\\", "..")):
        raise ValueError("r10_behavioral_remote_root_invalid")
    return f"{home}/taskgenerator-data/r10-behavioral/{run_id}"


def _remote_script(workspace: str, *, stack: str, grade: bool = False) -> str:
    if stack not in STACKS:
        raise ValueError("r10_behavioral_unknown_stack")
    agent_command = (
        "codex --ask-for-approval never --model gpt-5.6-sol exec -c project_doc_max_bytes=0 -c agents.enabled=false "
        "--disable plugins --disable apps --disable multi_agent --disable skill_search --json --ephemeral "
        "--ignore-user-config --ignore-rules --sandbox danger-full-access --skip-git-repo-check "
        + ("--output-schema /workspace/grade_schema.json --output-last-message /workspace/grade.raw.json " if grade else "")
        + "-C /workspace - < TASK.md > agent.jsonl 2> stderr.txt"
        if stack.startswith("gpt")
        else "export DEEPSEEK_API_KEY=\"$(cat /run/secrets/deepseek_api_key)\"; "
        "opencode run --format json --model deepseek/deepseek-v4-pro --auto --dir /workspace "
        "\"$(cat TASK.md)\" > agent.jsonl 2> stderr.txt"
    )
    mounts = '-v "$auth_file:/run/codex-auth/auth.json:ro"'
    if not stack.startswith("gpt"):
        mounts += ' -v "$deepseek_file:/run/secrets/deepseek_api_key:ro"'
    inner = [
        "set -eu", "mkdir -p .codex", "ln -sf /run/codex-auth/auth.json .codex/auth.json",
        "trap 'rm -rf /workspace/.codex' EXIT", "export CODEX_HOME=/workspace/.codex", agent_command,
    ]
    if not grade:
        inner.extend([
            "rm -rf /workspace/.docx_office_check; mkdir -p /workspace/.docx_office_check",
            "for doc in /workspace/deliverable_files/*.docx; do [ -f \"$doc\" ] || continue; libreoffice --headless --convert-to pdf:writer_pdf_Export --outdir /workspace/.docx_office_check \"$doc\" >/dev/null 2>&1 && printf '%s\\n' \"${doc#/workspace/}\"; done > /workspace/docx_office_opened.txt",
        ])
    return "\n".join([
        "set -eu", f"workspace='{workspace}'", 'auth_file="$HOME/.codex/auth.json"',
        'deepseek_file="$HOME/taskgenerator-secrets/deepseek_api_key"', 'test -r "$auth_file"',
        ("test -r \"$deepseek_file\"" if not stack.startswith("gpt") else ":"), 'cd "$workspace"',
        'timeout --preserve-status 1800 docker run -i --rm --init --read-only --cap-drop ALL --security-opt no-new-privileges:true '
        '--user 1000:1000 --memory 3g --cpus 2 --pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=512m '
        '--tmpfs /home/taskgenerator/.cache:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.local:rw,nosuid,nodev,size=512m '
        '--tmpfs /home/taskgenerator/.config:rw,nosuid,nodev,size=256m -v "$workspace:/workspace:rw" '
        + mounts + ' -w /workspace --entrypoint /bin/sh ' + IMAGE + " -s > docker_stdout.txt 2> docker_stderr.txt <<'INNER'",
        *inner, "INNER",
    ]) + "\n"


def _run_remote(*, host: str, remote: str, local: Path, stack: str, grade: bool = False) -> tuple[int, str, str]:
    _ssh(host, f"mkdir -p '{remote.rsplit('/', 1)[0]}' && rm -rf '{remote}'", timeout=120)
    _run(["scp", "-r", str(local), f"{host}:{remote}"], timeout=240)
    result = _ssh(host, "sh -s", input_text=_remote_script(remote, stack=stack, grade=grade), timeout=1900, check=False)
    _run(["scp", "-r", f"{host}:{remote}/.", str(local)], timeout=240)
    return result.returncode, result.stdout[-4000:], result.stderr[-4000:]


def _input_hashes(root: Path) -> set[str]:
    return {sha256_file(path) for path in (root / "reference_files").rglob("*") if path.is_file()}


def _remote_docx_opened(workspace: Path, expected: str) -> bool | None:
    if Path(expected).suffix.casefold() != ".docx":
        return None
    path = workspace / "docx_office_opened.txt"
    if not path.is_file():
        return False
    return expected.replace("\\", "/") in {line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()}


def _stage_solver(task_root: Path, target: Path) -> None:
    target.mkdir(parents=True)
    shutil.copy2(task_root / "TASK.md", target / "TASK.md")
    shutil.copy2(task_root / "deliverable_contract.json", target / "deliverable_contract.json")
    shutil.copytree(task_root / "reference_files", target / "reference_files")
    (target / "deliverable_files").mkdir()


def _public_probe_workspace(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "deliverable_files").mkdir()
    (target / "TASK.md").write_text(
        "Create deliverable_files/probe.xlsx and deliverable_files/probe.docx. The workbook must contain a Summary sheet, headers, two data rows and a formula. The document must contain a title and two short paragraphs. Reopen both files to verify them. Do not access private files.\n",
        encoding="utf-8",
    )


def _is_infrastructure(returncode: int, stderr: str) -> bool:
    lowered = stderr.casefold()
    return returncode == 124 or any(marker in lowered for marker in INFRA_MARKERS)


def _record_probe(*, output_root: Path, host: str, remote_root: str, stack: str) -> bool:
    workspace = output_root / "public_probes" / stack / "workspace"
    _public_probe_workspace(workspace)
    code, stdout, stderr = _run_remote(host=host, remote=f"{remote_root}/public/{stack}", local=workspace, stack=stack)
    _write(workspace.parent / "diagnostics.json", {"returncode": code, "stdout": stdout, "stderr": stderr})
    xlsx = inspect_delivery(workspace, expected="deliverable_files/probe.xlsx", input_hashes=set())
    docx = inspect_delivery(
        workspace, expected="deliverable_files/probe.docx", input_hashes=set(),
        verify_docx_with_office=False, office_openable_override=_remote_docx_opened(workspace, "deliverable_files/probe.docx"),
    )
    passed = code == 0 and xlsx.valid and docx.valid
    _write(workspace.parent / "probe_result.json", {"stack_id": stack, "decision": "pass" if passed else "incompatible_stack", "xlsx": xlsx, "docx": docx})
    return passed


def _execute_solver(*, host: str, remote_root: str, output_root: Path, binding, stack: str) -> R10SolverOutcomeV1:
    task_root = Path(binding.package_root)
    if binding_from_task(task_root, domain=binding.domain) != binding:
        raise RuntimeError("r10_behavioral_binding_drift")
    workspace = output_root / "solvers" / stack / binding.task_id / "workspace"
    _stage_solver(task_root, workspace)
    started = time.monotonic()
    code, stdout, stderr = _run_remote(host=host, remote=f"{remote_root}/solvers/{stack}/{binding.task_id}", local=workspace, stack=stack)
    duration = round(time.monotonic() - started, 3)
    stdout_path, stderr_path = workspace.parent / "agent.jsonl", workspace.parent / "stderr.txt"
    if (workspace / "agent.jsonl").is_file():
        shutil.copy2(workspace / "agent.jsonl", stdout_path)
    else:
        stdout_path.write_text(stdout, encoding="utf-8")
    if (workspace / "stderr.txt").is_file():
        shutil.copy2(workspace / "stderr.txt", stderr_path)
    else:
        stderr_path.write_text(stderr, encoding="utf-8")
    delivery = inspect_delivery(
        workspace, expected=binding.expected_delivery, input_hashes=_input_hashes(workspace),
        verify_docx_with_office=False, office_openable_override=_remote_docx_opened(workspace, binding.expected_delivery),
    )
    if code == 0 and delivery.valid:
        status, failure = "completed", None
    elif _is_infrastructure(code, stderr_path.read_text(encoding="utf-8", errors="replace")):
        status, failure = "infrastructure_failed", "provider_or_runtime_failure"
    else:
        status, failure = "task_failed", delivery.first_failure or f"agent_exit:{code}"
    outcome = R10SolverOutcomeV1(task_id=binding.task_id, solver_id=stack, status=status, returncode=code, timed_out=code == 124, duration_seconds=duration, stdout_sha256=sha256_file(stdout_path), stderr_sha256=sha256_file(stderr_path), delivery=delivery, first_failure=failure)
    _write(workspace.parent / "outcome.json", outcome)
    return outcome


def _grade_schema() -> dict:
    return R10JudgeDraftV1.model_json_schema()


def _grade_prompt(task_id: str, *, feedback: str | None = None) -> str:
    suffix = f"\nYour previous attempt had only a JSON/schema error: {feedback}. Preserve the substantive review and write valid JSON.\n" if feedback else ""
    return f"""You are grading one route-blind professional work product. Read candidate_task.md, deliverable_contract.json, decision_matrix.json, teacher_truth.json, task_specific_rubric.json and the submitted delivery file. Inspect the actual file with local tools. Do not infer or mention the solver, model, generation route, Skills, or Scenario Bible.

Write exactly one JSON object to grade.raw.json with task_id `{task_id}` and one assessment for every decision_matrix decision_id. Each assessment must contain decision_id, rating (`met`, `partial`, or `not_met`), major_error, one or more cited evidence_paths, rationale, and evidence_insufficient. Do not provide an overall score; it is recomputed outside this task.\n{suffix}"""


def _stage_grade(*, task_root: Path, delivery: Path, target: Path, task_id: str, feedback: str | None) -> TaskSpecificRubricV1:
    target.mkdir(parents=True)
    shutil.copy2(task_root / "TASK.md", target / "candidate_task.md")
    shutil.copy2(task_root / "deliverable_contract.json", target / "deliverable_contract.json")
    shutil.copy2(task_root / "teacher" / "decision_matrix.json", target / "decision_matrix.json")
    shutil.copy2(task_root / "teacher" / "teacher_truth.json", target / "teacher_truth.json")
    shutil.copy2(task_root / "teacher" / "task_specific_rubric.json", target / "task_specific_rubric.json")
    shutil.copytree(task_root / "reference_files", target / "reference_files")
    shutil.copy2(delivery, target / f"delivery{delivery.suffix.lower()}")
    (target / "grade_schema.json").write_text(json.dumps(_grade_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "TASK.md").write_text(_grade_prompt(task_id, feedback=feedback), encoding="utf-8")
    return TaskSpecificRubricV1.model_validate_json((target / "task_specific_rubric.json").read_text(encoding="utf-8"))


def _extract_opencode_json(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = item.get("part") if isinstance(item, dict) else None
        value = part.get("text") if isinstance(part, dict) else None
        if isinstance(value, str) and value.lstrip().startswith("{"):
            return value.strip()
    match = re.search(r"(\{\s*\"task_id\"[\s\S]*\})\s*$", text)
    return match.group(1) if match else None


def _execute_judge(*, host: str, remote_root: str, output_root: Path, task_root: Path, task_id: str, delivery: Path, judge: str) -> dict[str, Any]:
    feedback: str | None = None
    raw_paths: list[str] = []
    first_failure: str | None = None
    for attempt in (1, 2):
        workspace = output_root / "judges" / judge / task_id / f"attempt_{attempt:02d}" / "workspace"
        rubric = _stage_grade(task_root=task_root, delivery=delivery, target=workspace, task_id=task_id, feedback=feedback)
        code, stdout, stderr = _run_remote(host=host, remote=f"{remote_root}/judges/{judge}/{task_id}/attempt_{attempt:02d}", local=workspace, stack=judge, grade=True)
        raw = workspace / "grade.raw.json"
        if not raw.is_file() and judge.startswith("deepseek"):
            candidate = _extract_opencode_json((workspace / "agent.jsonl").read_text(encoding="utf-8", errors="replace") if (workspace / "agent.jsonl").is_file() else stdout)
            if candidate:
                raw.write_text(candidate, encoding="utf-8")
        raw_paths.append(str(raw))
        if code != 0 and _is_infrastructure(code, stderr):
            return {"status": "infrastructure_failed", "first_failure": "provider_or_runtime_failure", "raw_paths": raw_paths}
        try:
            draft = R10JudgeDraftV1.model_validate_json(raw.read_text(encoding="utf-8"))
            if draft.task_id != task_id:
                raise ValueError("judge_task_id_mismatch")
            review = finalize_judge_review(judge_id=judge, draft=draft, rubric=rubric)
            _write(workspace.parent / "review.json", review)
            return {"status": "completed", "review": review, "review_path": str(workspace.parent / "review.json"), "raw_paths": raw_paths, "first_failure": first_failure}
        except Exception as exc:
            first_failure = first_failure or f"judge_json_or_schema_invalid:{type(exc).__name__}"
            feedback = first_failure
    return {"status": "format_failed", "first_failure": first_failure, "raw_paths": raw_paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_7b_behavioral_pilot_20260831")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_7b_behavioral_pilot_20260831")
    parser.add_argument("--scope-only", action="store_true")
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("r10_behavioral_output_already_exists")
    scope = _scope(args.run_id)
    args.output_root.mkdir(parents=True)
    _write(args.output_root / "scope.json", scope)
    _write(args.output_root / "receipt.json", {"scope_sha256": scope.canonical_sha256(), "consumed_at": _now()})
    if args.scope_only:
        print(json.dumps({"decision": "scope_ready", "scope_sha256": scope.canonical_sha256()}, ensure_ascii=False))
        return
    remote_root = _safe_remote_root(args.host, args.run_id)
    probes = {stack: _record_probe(output_root=args.output_root, host=args.host, remote_root=remote_root, stack=stack) for stack in STACKS}
    if not all(probes.values()):
        _write(args.output_root / "result.json", {"decision": "behaviorally_inconclusive", "reason": "public_probe_failed", "probes": probes})
        print(json.dumps({"decision": "behaviorally_inconclusive", "probes": probes}, ensure_ascii=False))
        return
    outcomes: dict[str, dict[str, R10SolverOutcomeV1]] = {stack: {} for stack in STACKS}
    for stack in STACKS:
        consecutive_infra = 0
        for binding in scope.bindings:
            outcome = _execute_solver(host=args.host, remote_root=remote_root, output_root=args.output_root, binding=binding, stack=stack)
            outcomes[stack][binding.task_id] = outcome
            consecutive_infra = consecutive_infra + 1 if outcome.status == "infrastructure_failed" else 0
            if consecutive_infra >= 3:
                break
    records: list[R10ModelTaskResultV1] = []
    judge_manifest: dict[str, Any] = {}
    for stack in STACKS:
        for binding in scope.bindings:
            outcome = outcomes[stack].get(binding.task_id)
            reviews = []
            if outcome and outcome.delivery.valid:
                delivery = args.output_root / "solvers" / stack / binding.task_id / "workspace" / binding.expected_delivery
                for judge in STACKS:
                    result = _execute_judge(host=args.host, remote_root=remote_root, output_root=args.output_root, task_root=Path(binding.package_root), task_id=binding.task_id, delivery=delivery, judge=judge)
                    judge_manifest[f"{stack}:{binding.task_id}:{judge}"] = {key: (value.model_dump(mode="json") if hasattr(value, "model_dump") else value) for key, value in result.items()}
                    if result["status"] == "completed":
                        reviews.append(result["review"])
            records.append(R10ModelTaskResultV1(task_id=binding.task_id, solver_id=stack, delivery_valid=bool(outcome and outcome.delivery.valid), reviews=reviews))
    _write(args.output_root / "judge_manifest.json", judge_manifest)
    _write(args.output_root / "records.json", records)
    try:
        result = aggregate_behavioral_result(records)
    except ValueError as exc:
        _write(args.output_root / "result.json", {"decision": "behaviorally_inconclusive", "reason": str(exc)})
        raise
    _write(args.output_root / "result.json", result)
    print(json.dumps({"decision": result.decision, "low_model_separation": result.low_model_separation, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
