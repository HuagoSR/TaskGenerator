"""Two development-task rubric author/review sessions; never solves or grades.

Reuse the existing restricted remote execution transport. No GDPval module or
dataset is imported. Frozen tasks are read through an explicit input allowlist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "Test")]

from run_r10_behavioral_pilot import (
    CHATGPT_CODEX_STACK, DEEPSEEK_OPENCODE_STACK, _run_remote, _ssh,
    _extract_opencode_json,
)
from task_generator.core.scenario_first import TaskDecisionMatrixV1
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.planning.scenario_task_compiler import tree_sha256
from task_generator.planning.rubric_compiler_v2 import (
    RubricCompilationV2, RubricAuthorReviewV2, TaskSpecificRubricV2,
    rubric_compiler_prompt, rubric_review_prompt, validate_rubric, validate_review,
)
from task_generator.production.campaign import atomic_json

SOURCE = ROOT / "artifacts/r10/r10_9_world_first_pilot_20260902/tasks"
TASKS = ("r10_9_audit_reliability_baseline_task", "r10_9_procurement_price_baseline_task")
IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099"
IMAGE_SHA = "3c6c76324780a911ff7b47bf52629280b4f2a49f26248540de049a61b9129363"
AUTH = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
REMOTE = "/home/huagosr/taskgenerator-data/r10-rubric-compilation"
CONFIGS = {
    "author": {"stack": CHATGPT_CODEX_STACK, "model": "gpt-5.6-terra", "reasoning": "medium"},
    "review": {"stack": DEEPSEEK_OPENCODE_STACK, "model": "deepseek-v4-pro", "variant": "max"},
}
ALLOWLIST = {"TASK.md": "candidate_task.md", "deliverable_contract.json": "deliverable_contract.json",
             "teacher/teacher_truth.json": "teacher_truth.json",
             "teacher/decision_matrix.json": "decision_matrix.json"}


def now():
    return datetime.now(UTC).isoformat()


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    atomic_json(path, value.model_dump(mode="json") if hasattr(value, "model_dump") else value)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def input_files(task: Path):
    files = {target: task / source for source, target in ALLOWLIST.items()}
    files.update({p.relative_to(task).as_posix(): p for p in (task / "reference_files").rglob("*") if p.is_file()})
    for name, path in files.items():
        if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(task.resolve())
                or any(part in {".env", "auth.json", "deepseek-key.txt"} for part in path.parts)):
            raise ValueError("unsafe_or_missing_rubric_input")
    if not any(name.startswith("reference_files/") for name in files):
        raise ValueError("rubric_candidate_files_missing")
    return files


def bindings(source: Path):
    return {task_id: {"task_tree_sha256": tree_sha256(source / task_id),
                     "inputs": {name: sha(path) for name, path in input_files(source / task_id).items()}}
            for task_id in TASKS}


def stage(target: Path, task: Path, phase: str, rubric=None):
    target.mkdir(parents=True, exist_ok=False)
    for name, path in input_files(task).items():
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    (target / "deliverable_files").mkdir()
    if phase == "review":
        write(target / "new_rubric.json", rubric)
    model = RubricCompilationV2 if phase == "author" else RubricAuthorReviewV2
    write(target / "grade_schema.json", _strict_output_schema(model.model_json_schema()))
    prompt = rubric_compiler_prompt(task.name) if phase == "author" else rubric_review_prompt(task.name)
    (target / "TASK.md").write_text(prompt + "\nReturn the JSON as the final answer, without Markdown fences.\n", encoding="utf-8")
    return {p.relative_to(target).as_posix(): sha(p) for p in target.rglob("*") if p.is_file()}


def completed(workspace: Path, phase: str):
    try:
        events = [json.loads(line) for line in (workspace / "agent.jsonl").read_text(encoding="utf-8").split("\n") if line.strip()]
    except (OSError, ValueError):
        return False
    if any(row.get("type") in {"error", "turn.failed"} for row in events):
        return False
    if phase == "author":
        return any(row.get("type") == "turn.completed" for row in events)
    return bool(events) and events[-1].get("type") == "step_finish" and events[-1].get("part", {}).get("reason") == "stop"


def parse_output(workspace: Path, phase: str):
    if phase == "author":
        raw = (workspace / "grade.raw.json").read_text(encoding="utf-8")
    else:
        events = (workspace / "agent.jsonl").read_text(encoding="utf-8")
        # Preserve legal U+2028 inside JSON strings: event boundaries are LF only.
        escaped = "\n".join(json.dumps(json.loads(line), ensure_ascii=True) for line in events.split("\n") if line.strip())
        raw = _extract_opencode_json(escaped)
        if not raw:
            raise ValueError("rubric_review_json_missing")
    model = RubricCompilationV2 if phase == "author" else RubricAuthorReviewV2
    return model.model_validate_json(raw)


def verify_remote_inputs(host, remote, frozen):
    names = " ".join(shlex.quote(name) for name in sorted(frozen))
    response = _ssh(host, f"cd {shlex.quote(remote)} && sha256sum -- {names}", timeout=120)
    found = {}
    for line in response.stdout.splitlines():
        value, name = line.split("  ", 1)
        found[name] = value
    if found != frozen:
        raise ValueError("remote_rubric_inputs_mutated")


def sanitize_logs(workspace):
    """Retain observable events/usage, not provider reasoning or credential text."""
    pattern = re.compile(r"sk-[A-Za-z0-9_-]{24,}|eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_.-]+")
    log = workspace / "agent.jsonl"
    original_sha = sha(log) if log.exists() else None
    if log.exists():
        clean = []
        for line in log.read_text(encoding="utf-8", errors="replace").split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if event.get("type") in {"reasoning", "reasoning_delta"} or any(
                    event.get(key, {}).get("type") == "reasoning" for key in ("part", "item")
                    if isinstance(event.get(key, {}), dict)):
                    continue
                clean.append(pattern.sub("[REDACTED]", json.dumps(event, ensure_ascii=False)))
            except ValueError:
                clean.append(pattern.sub("[REDACTED]", line))
        log.write_text("\n".join(clean) + "\n", encoding="utf-8")
    for name in ("stderr.txt", "docker_stderr.txt", "docker_stdout.txt", "grade.raw.json"):
        path = workspace / name
        if path.is_file():
            path.write_text(pattern.sub("[REDACTED]", path.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    return original_sha


def reserve_attempt(run: Path, retry: bool):
    path = run / "attempts.json"
    count = read(path) if path.exists() else {"attempts": 0, "retries": 0}
    if count["attempts"] >= 6 or (retry and count["retries"] >= 2):
        raise RuntimeError("rubric_campaign_attempt_limit")
    count["attempts"] += 1
    count["retries"] += int(retry)
    write(path, count)


def execute_assignment(host, run, run_id, source, task_id, phase, rubric=None):
    root = run / task_id / phase
    if (root / "state.json").exists():
        raise RuntimeError("rubric_started_assignment_not_rerunnable")
    config = CONFIGS[phase]
    first_failure = None
    frozen = None
    for attempt in (1, 2):
        workspace = root / f"attempt_{attempt}" / "workspace"
        input_sha = stage(workspace, source / task_id, phase, rubric)
        if frozen is not None and input_sha != frozen:
            raise ValueError("rubric_retry_input_drift")
        frozen = input_sha
        reserve_attempt(run, retry=attempt == 2)
        write(root / "state.json", {"status": "running", "attempt": attempt,
              "input_sha256": digest(input_sha), "started_at": now(), "first_failure": first_failure})
        start = time.monotonic()
        remote = f"{REMOTE}/{run_id}/{task_id}/{phase}/attempt_{attempt}"
        retryable = False
        try:
            code, _, _ = _run_remote(host=host, remote=remote, local=workspace, stack=config["stack"],
                grade=True, image=IMAGE, codex_auth_dir=AUTH, timeout_seconds=1800,
                model_override=config["model"], codex_reasoning_effort=config.get("reasoning"),
                opencode_variant=config.get("variant"))
            terminal = completed(workspace, phase)
            raw_sha = sanitize_logs(workspace)
            write(root / f"attempt_{attempt}" / "diagnostics.json", {
                "exit_code": code, "terminal": terminal, "raw_events_sha256": raw_sha,
                "duration_seconds": round(time.monotonic() - start, 3), "model": config})
            if code != 0 or not terminal:
                raise RuntimeError("rubric_agent_infrastructure_incomplete")
            verify_remote_inputs(host, remote, input_sha)
            retryable = True
            output = parse_output(workspace, phase)
            # Semantic references are NOT format failures eligible for redraw.
            retryable = False
            if output.task_id != task_id:
                raise ValueError("rubric_task_identity_mismatch")
            if phase == "author" and output.status == "compiled":
                matrix = TaskDecisionMatrixV1.model_validate(read(workspace / "decision_matrix.json"))
                validate_rubric(output.rubric, matrix, workspace)
            elif phase == "review":
                validate_review(output, rubric, workspace)
            write(root / "result.json", output)
            write(root / "state.json", {"status": "completed", "attempt": attempt,
                  "first_failure": first_failure, "completed_at": now(), "output_sha256": digest(output)})
            return output
        except Exception as exc:
            sanitize_logs(workspace)
            # Persist classifications, never exception bodies potentially containing credentials.
            failure = {"type": type(exc).__name__, "phase": "format" if retryable else "execution_or_admission"}
            if hasattr(exc, "errors"):
                failure["schema_errors"] = [{"loc": list(e["loc"]), "type": e["type"]}
                    for e in exc.errors(include_input=False, include_context=False)]
            first_failure = first_failure or failure
            write(root / f"attempt_{attempt}" / "failure.json", failure)
            write(root / "state.json", {"status": "incomplete", "attempt": attempt,
                  "first_failure": first_failure, "retryable": retryable, "ended_at": now()})
            if not retryable or attempt == 2:
                raise RuntimeError("rubric_assignment_incomplete") from None
    raise AssertionError("unreachable")


def chinese_report(run: Path, task_id: str, compiled: RubricCompilationV2, review=None):
    lines = [f"# Rubric 生成检查：{task_id}", "", compiled.summary_zh, "",
             "本材料只验证 rubric 编译，不代表新评分、模型排名或专家有效性。", ""]
    if compiled.rubric:
        lines += [f"条目数：{len(compiled.rubric.criteria)}；总分：{compiled.rubric.total_points}。", ""]
        for row in compiled.rubric.criteria:
            lines += [f"## {row.criterion_id}（{row.max_points} 分）", "", f"工作要求：{row.requirement}",
                f"对应判断：{row.decision_id}", "", "得分边界：", ""]
            lines += [f"- {b.awarded} 分：{b.description}" for b in sorted(row.score_boundaries, key=lambda b: -b.awarded)]
            lines += ["", f"适用与例外：{row.applicability}", f"等价表达：{row.acceptable_alternatives}",
                      f"核验方法：{row.verification}", "", "依据：", ""]
            lines += [f"- {b.path} / {b.locator}：{b.explanation}" for b in row.requirement_basis]
            lines += [""]
    if compiled.upstream_issues:
        lines += ["## 上游问题", "", *[f"- {x}" for x in compiled.upstream_issues], ""]
    if review:
        lines += ["## 独立审查", "", f"结论：{review.decision}", review.summary_zh, ""]
        lines += [f"- {c.check}：{c.status} — {c.rationale_zh}" for c in review.checks]
    path = run / task_id / "中文检查材料.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def environment(host):
    image_id = _ssh(host, f"docker image inspect --format '{{{{.Id}}}}' {shlex.quote(IMAGE)}", timeout=120).stdout.strip()
    if image_id != "sha256:" + IMAGE_SHA:
        raise ValueError("rubric_environment_image_drift")
    return {"image": IMAGE, "image_sha256": IMAGE_SHA, "existing_tool_evidence_reused": True,
            "codex_version": "0.149.1", "opencode_version": "1.17.13",
            "auth_location_fingerprint": hashlib.sha256(AUTH.encode()).hexdigest()}


def run_campaign(host, run, run_id, source=SOURCE):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
        raise ValueError("unsafe_run_id")
    if not run.resolve().is_relative_to((ROOT / "artifacts/r10").resolve()):
        raise ValueError("rubric_run_must_be_ignored_artifact")
    if run.exists():
        raise ValueError("rubric_campaign_already_exists_no_silent_resume")
    frozen = bindings(source)
    env = environment(host)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    scope = {"scope_version": "r10.rubric_compilation_scope.2", "campaign_id": run_id,
             "source_commit": commit, "source_files_sha256": {
                 "runner": sha(Path(__file__)),
                 "compiler": sha(Path(__file__).resolve().parents[1] / "src/task_generator/planning/rubric_compiler_v2.py")},
             "environment": env, "tasks": frozen, "models": CONFIGS,
             "assignments": [{"task_id": tid, "phase": p} for tid in TASKS for p in CONFIGS],
             "max_attempts": 6, "global_retries": 2, "max_attempts_per_assignment": 2,
             "excluded": ["solver", "scoring", "gdpval", "holdout", "task_mutation", "release"]}
    write(run / "scope.json", scope)
    write(run / "receipt.json", {"scope_sha256": digest(scope), "consumed_at": now(),
                                "authority": "user_approved_two_task_rubric_generation_and_review"})
    result = {"status": "incomplete", "tasks": {}, "first_failure": None,
              "evidence_level": "generation_only_llm_proxy", "scope_sha256": digest(scope)}
    try:
        for task_id in TASKS:
            if bindings(source) != frozen:
                raise ValueError("rubric_frozen_source_drift")
            compiled = execute_assignment(host, run, run_id, source, task_id, "author")
            chinese_report(run, task_id, compiled)
            if compiled.status == "upstream_issue":
                result["tasks"][task_id] = {"status": "upstream_issue", "author_sha256": digest(compiled)}
                continue
            review = execute_assignment(host, run, run_id, source, task_id, "review", compiled.rubric)
            chinese_report(run, task_id, compiled, review)
            result["tasks"][task_id] = {"status": review.decision, "author_sha256": digest(compiled),
                                       "review_sha256": digest(review), "items": len(compiled.rubric.criteria),
                                       "total_points": compiled.rubric.total_points}
            write(run / "result.json", result)
        if bindings(source) != frozen:
            raise ValueError("rubric_frozen_source_drift")
        result["status"] = ("rubric_compilation_supported" if all(t["status"] == "pass" for t in result["tasks"].values())
                            else "rubric_revision_required")
    except Exception as exc:
        result["first_failure"] = {"type": type(exc).__name__, "classification": "execution_or_admission_incomplete"}
    result["finished_at"] = now()
    result["attempts"] = read(run / "attempts.json") if (run / "attempts.json").exists() else {"attempts": 0, "retries": 0}
    write(run / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "status"])
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", default="r10_10_rubric_generation_20260903")
    parser.add_argument("--host", default="huago-cone")
    args = parser.parse_args()
    result = read(args.run_root / "result.json") if args.command == "status" else run_campaign(args.host, args.run_root, args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
