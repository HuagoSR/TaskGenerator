"""Run the fixed R10.11 independent item-grading calibration.

This one-off harness never reruns a Solver and never mutates source packages.
Dry-run is provider-free and records the exact 17+4 assignment scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

from pydantic import ValidationError

from run_r10_behavioral_pilot import CHATGPT_CODEX_STACK, _run_remote, _scp, _ssh
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.independent_rubric_grader import (
    FrozenRubricItemV1,
    IndependentRubricGradeDraftV1,
    adapt_gdpval_rubric,
    adapt_r10_v1_rubric,
    canonical_json_sha256,
    finalize_independent_grade,
    tree_sha256,
)
from task_generator.evaluation.r10_gdpval_validation import GDPvalTaskBindingV1
from task_generator.production.campaign import atomic_json


RUN_ID = "r10_11_independent_grader_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
GDPVAL_DATA = ROOT / "artifacts/r10/r10_10_gdpval_public_20260903"
GDPVAL_SOLVERS = ROOT / "artifacts/r10/r10_10_gdpval_validation_20260903_v1/solvers"
R10_DATA = ROOT / "artifacts/r10/r10_9_world_first_pilot_20260902"
IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099"
IMAGE_SHA256 = "3c6c76324780a911ff7b47bf52629280b4f2a49f26248540de049a61b9129363"
HOST = "huago-cone"
REMOTE_ROOT = "/home/huagosr/taskgenerator-data/r10-11-independent-grader"
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
PRIMARY_JUDGE = "deepseek-v4-pro@official_api"
CHECK_JUDGE = "gpt-5.6-terra@chatgpt_codex"
PRIMARY_RECOVERY_LIMIT = 3
CHECK_RECOVERY_LIMIT = 1

GDPVAL_TASKS = (
    "7d7fc9a7-21a7-4b83-906f-416dea5ad04f",
    "1b1ade2d-f9f6-4a04-baa5-aa15012b53be",
    "36d567ba-e205-4313-9756-931c6e4691fe",
)
GDPVAL_STACKS = (
    "gpt-5.6-sol@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "deepseek-v4-flash@official_opencode",
)
R10_TASKS = (
    "r10_9_audit_reliability_baseline_task",
    "r10_9_audit_reliability_adversarial_task",
    "r10_9_procurement_price_baseline_task",
    "r10_9_procurement_price_adversarial_task",
)
R10_STACKS = ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode")
SENTINELS = (
    (GDPVAL_TASKS[0], GDPVAL_STACKS[0]),
    (GDPVAL_TASKS[2], GDPVAL_STACKS[2]),
    (R10_TASKS[1], R10_STACKS[0]),
    (R10_TASKS[2], R10_STACKS[1]),
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    atomic_json(path, value.model_dump(mode="json") if hasattr(value, "model_dump") else value)


def assignments() -> list[dict[str, str]]:
    rows = [
        {"task_id": task, "submission_id": stack, "source": "gdpval", "judge_id": PRIMARY_JUDGE, "role": "primary"}
        for task in GDPVAL_TASKS for stack in GDPVAL_STACKS
    ]
    rows += [
        {"task_id": task, "submission_id": stack, "source": "r10_9", "judge_id": PRIMARY_JUDGE, "role": "primary"}
        for task in R10_TASKS for stack in R10_STACKS
    ]
    rows += [
        {"task_id": task, "submission_id": stack, "source": "gdpval" if task in GDPVAL_TASKS else "r10_9",
         "judge_id": CHECK_JUDGE, "role": "check"}
        for task, stack in SENTINELS
    ]
    for row in rows:
        row["assignment_id"] = canonical_json_sha256(row)[:24]
    return rows


def _sources(row: dict[str, str]) -> tuple[Path, Path, list[FrozenRubricItemV1]]:
    task_id, stack = row["task_id"], row["submission_id"]
    if row["source"] == "gdpval":
        task = GDPVAL_DATA / "tasks" / task_id
        binding = GDPvalTaskBindingV1.model_validate_json((task / "binding.json").read_text(encoding="utf-8"))
        delivery = GDPVAL_SOLVERS / stack / task_id / "workspace/deliverable_files"
        return task, delivery, adapt_gdpval_rubric(binding)
    task = R10_DATA / "tasks" / task_id
    delivery = R10_DATA / "solvers" / stack / task_id / "workspace/deliverable_files"
    rubric = json.loads((task / "teacher/task_specific_rubric.json").read_text(encoding="utf-8"))
    return task, delivery, adapt_r10_v1_rubric(rubric)


def _stage(workspace: Path, row: dict[str, str]) -> dict[str, str]:
    task, delivery, rubric = _sources(row)
    if workspace.exists():
        raise FileExistsError(f"r10_11_workspace_already_exists:{workspace}")
    _validate_delivery_root(task, delivery, row)
    workspace.mkdir(parents=True)
    prompt = task / ("prompt.txt" if row["source"] == "gdpval" else "TASK.md")
    shutil.copy2(prompt, workspace / "candidate_task.md")
    shutil.copytree(task / "reference_files", workspace / "reference_files")
    shutil.copytree(delivery, workspace / "anonymous_submission")
    _write(workspace / "rubric_items.json", [item.model_dump(mode="json") for item in rubric])
    _write(
        workspace / "grade_schema.json",
        _strict_output_schema(IndependentRubricGradeDraftV1.model_json_schema()),
    )
    return {
        "input_sha256": _candidate_input_sha256(workspace),
        "rubric_sha256": canonical_json_sha256(rubric),
        "delivery_sha256": tree_sha256(workspace / "anonymous_submission"),
    }


def _validate_delivery_root(task: Path, delivery: Path, row: dict[str, str]) -> None:
    files = sorted(path for path in delivery.rglob("*") if path.is_file())
    if row["source"] == "gdpval":
        binding = json.loads((task / "binding.json").read_text(encoding="utf-8"))
        expected = set(binding["expected_deliverables"])
    else:
        contract = json.loads((task / "deliverable_contract.json").read_text(encoding="utf-8"))
        expected = {item["file_name"] for item in contract["deliverables"] if item["must_exist"]}
    if {path.name for path in files} != expected or any(path.stat().st_size == 0 for path in files):
        raise ValueError(f"r10_11_invalid_delivery:{row['assignment_id']}")
    for path in files:
        if path.suffix.casefold() in {".docx", ".xlsx", ".pptx"}:
            try:
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip() is not None:
                        raise ValueError("corrupt_member")
            except (OSError, zipfile.BadZipFile, ValueError) as exc:
                raise ValueError(f"r10_11_invalid_delivery:{row['assignment_id']}") from exc


def _candidate_input_sha256(workspace: Path) -> str:
    digest = hashlib.sha256()
    files = [workspace / "candidate_task.md"] + sorted(
        path for path in (workspace / "reference_files").rglob("*") if path.is_file()
    )
    for path in files:
        relative = path.relative_to(workspace).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_file_sha256(path)))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _terra_task(workspace: Path) -> None:
    (workspace / "TASK.md").write_text(
        """Grade ONE anonymous submission independently against rubric_items.json. Inspect candidate_task.md,
all reference_files and anonymous_submission files with installed tools. Assess every rubric_item_id exactly once.
Use integer awarded from 0 through max_score, actual evidence_paths rooted only at candidate_task.md,
reference_files/ or anonymous_submission/, and a concise rationale. Do not add criteria, holistic preference,
veto, hidden penalty, authorship inference, or high-score audit. If a visible prerequisite did not trigger, use
not_triggered and full item credit. If material cannot be read or applicability cannot be established, use
unresolved and material_status incomplete rather than guessing. Return exactly one JSON object matching
grade_schema.json; omit totals because the controller computes them. Do not alter input files.\n""",
        encoding="utf-8",
    )


def prepare(run_root: Path) -> dict[str, Any]:
    rows = assignments()
    if run_root.exists() and (run_root / "scope.json").exists():
        return json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    hashes = {}
    for row in rows:
        workspace = run_root / "sessions" / row["assignment_id"] / "workspace"
        hashes[row["assignment_id"]] = _stage(workspace, row)
        if row["role"] == "primary":
            shutil.copy2(ROOT / "Test/r10_11_remote_independent_grader.py", workspace)
        else:
            _terra_task(workspace)
    scope = {
        "scope_version": "r10.independent_grader_scope.1", "campaign_id": RUN_ID,
        "created_at": _now(), "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip(),
        "image": IMAGE, "image_sha256": IMAGE_SHA256, "host": HOST,
        "controller_sha256": _file_sha256(Path(__file__)),
        "remote_grader_sha256": _file_sha256(ROOT / "Test/r10_11_remote_independent_grader.py"),
        "contract_sha256": _file_sha256(ROOT / "src/task_generator/evaluation/independent_rubric_grader.py"),
        "primary": {"judge_id": PRIMARY_JUDGE, "normal_call_limit": 17, "campaign_recovery_limit": 3,
                    "transport": "official_api_direct", "policy": "balanced_item_only"},
        "checks": {"judge_id": CHECK_JUDGE, "reasoning": "medium", "normal_call_limit": 4,
                   "campaign_recovery_limit": 1},
        "assignments": rows, "hashes": hashes,
        "authorization": "user_authorized_scoring_uploads_for_this_campaign",
        "excluded_actions": ["solver_rerun", "semantic_redraw", "pairwise", "holistic_preference",
                             "downward_audit", "task_mutation", "training", "release"],
    }
    _write(run_root / "scope.json", scope)
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.independent_grader_receipt.1", "scope_sha256": canonical_json_sha256(scope),
        "status": "prepared", "provider_calls": 0, "prepared_at": _now(),
    })
    return scope


def _primary_call(workspace: Path, remote: str) -> tuple[int, str]:
    _ssh(HOST, f"mkdir -p '{remote.rsplit('/', 1)[0]}' && rm -rf '{remote}'", timeout=120)
    upload = _scp(str(workspace), f"{HOST}:{remote}")
    if upload.returncode:
        return upload.returncode, "upload:" + upload.stderr[-2000:]
    command = (
        "set -u; workspace='" + remote + "'; key=/home/huagosr/taskgenerator-secrets/deepseek_api_key; "
        "test -r \"$key\"; timeout --preserve-status 1200 docker run --rm --init --read-only --cap-drop ALL "
        "--security-opt no-new-privileges:true --user 1000:1000 --memory 3g --cpus 2 --pids-limit 256 "
        "--tmpfs /tmp:rw,nosuid,nodev,size=512m -v \"$workspace:/workspace:rw\" "
        "-v \"$key:/run/secrets/deepseek_api_key:ro\" -w /workspace --entrypoint /bin/sh " + IMAGE + " -lc "
        "'export DEEPSEEK_API_KEY=\"$(cat /run/secrets/deepseek_api_key)\"; python3 /workspace/r10_11_remote_independent_grader.py' "
        "> \"$workspace/docker_stdout.txt\" 2> \"$workspace/docker_stderr.txt\""
    )
    result = _ssh(HOST, command, timeout=1300, check=False)
    with tempfile.TemporaryDirectory(prefix="r10-11-return-", dir=workspace.parent) as temporary:
        returned = Path(temporary) / "returned"
        download = _scp(f"{HOST}:{remote}", str(returned))
        if download.returncode:
            return download.returncode, "download:" + download.stderr[-2000:]
        nested = returned / Path(remote).name
        source = nested if nested.is_dir() else returned
        for name in ("grade.raw.json", "provider_response.json", "docker_stdout.txt", "docker_stderr.txt"):
            if (source / name).is_file():
                shutil.copy2(source / name, workspace / name)
    return result.returncode, result.stderr[-2000:]


def _parse_finalize(workspace: Path, row: dict[str, str], hashes: dict[str, str]):
    draft = IndependentRubricGradeDraftV1.model_validate_json(
        (workspace / "grade.raw.json").read_text(encoding="utf-8")
    )
    _, _, rubric = _sources(row)
    if canonical_json_sha256(rubric) != hashes["rubric_sha256"]:
        raise ValueError("r10_11_rubric_hash_drift")
    if draft.material_status == "incomplete" or any(x.applicability == "unresolved" for x in draft.assessments):
        raise RuntimeError("r10_11_material_incomplete")
    grade = finalize_independent_grade(
        task_id=row["task_id"], submission_id=row["submission_id"], judge_id=row["judge_id"],
        rubric_items=rubric, draft=draft, staging_root=workspace,
        input_sha256=hashes["input_sha256"], delivery_sha256=hashes["delivery_sha256"],
    )
    _write(workspace.parent / "review.json", grade)
    return grade


def _recoverable(exc: Exception) -> bool:
    return isinstance(exc, (FileNotFoundError, json.JSONDecodeError, ValidationError))


def execute(run_root: Path) -> dict[str, Any]:
    scope = prepare(run_root)
    current_controller = _file_sha256(Path(__file__))
    if current_controller != scope["controller_sha256"]:
        amendments = sorted(run_root.glob("scope_amendment*.json"))
        prior_controller = scope["controller_sha256"]
        for path in amendments:
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior["old_controller_sha256"] != prior_controller:
                raise RuntimeError("r10_11_scope_amendment_chain_invalid")
            prior_controller = prior["new_controller_sha256"]
        if prior_controller != current_controller:
            number = len(amendments) + 1
            suffix = "" if number == 1 else f"_{number}"
            amendment_path = run_root / f"scope_amendment{suffix}.json"
        else:
            amendment_path = None
        amendment = {
            "amendment_version": "r10.independent_grader_scope_amendment.1",
            "original_scope_sha256": canonical_json_sha256(scope),
            "old_controller_sha256": prior_controller,
            "new_controller_sha256": current_controller,
            "reason": "controller_only_finalize_and_transport_state_repair",
            "semantic_prompt_changed": False, "provider_input_changed": False,
            "provider_retry_authorized_by_repair": False, "recorded_at": _now(),
        }
        if amendment_path is not None:
            _write(amendment_path, amendment)
    primary_recoveries = check_recoveries = calls = 0
    results = []
    for row in scope["assignments"]:
        session = run_root / "sessions" / row["assignment_id"]
        state_path, workspace = session / "state.json", session / "workspace"
        if state_path.exists():
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            if previous.get("status") == "completed":
                results.append(json.loads((session / "review.json").read_text(encoding="utf-8")))
                continue
            if previous.get("status") == "pre_provider_transport_failed":
                pass
                # No provider request was sent; the preserved failed attempt
                # may be followed by a transport recovery.
            else:
                attempt_roots = sorted((session / "attempts").glob("attempt_*"))
                if attempt_roots:
                    try:
                        recovered = _parse_finalize(
                            attempt_roots[-1], row, scope["hashes"][row["assignment_id"]]
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            f"r10_11_started_assignment_not_rerunnable:{row['assignment_id']}"
                        ) from exc
                    _write(session / "review.json", recovered)
                    _write(state_path, {"status": "completed", "recovered_without_provider_call": True,
                                        "completed_at": _now(), "review_sha256": recovered.canonical_sha256()})
                    results.append(recovered.model_dump(mode="json"))
                    continue
                raise RuntimeError(f"r10_11_started_assignment_not_rerunnable:{row['assignment_id']}")
        attempts = session / "attempts"
        attempts.mkdir(exist_ok=True)
        while True:
            attempt = len(list(attempts.iterdir())) + 1
            attempt_root = attempts / f"attempt_{attempt}"
            shutil.copytree(workspace, attempt_root)
            _write(state_path, {"status": "running", "attempt": attempt, "started_at": _now()})
            calls += 1
            try:
                if row["role"] == "primary":
                    code, error = _primary_call(attempt_root, f"{REMOTE_ROOT}/{RUN_ID}/{row['assignment_id']}/attempt_{attempt}")
                else:
                    code, _, error = _run_remote(
                        host=HOST, remote=f"{REMOTE_ROOT}/{RUN_ID}/{row['assignment_id']}/attempt_{attempt}",
                        local=attempt_root, stack=CHATGPT_CODEX_STACK, grade=True, image=IMAGE,
                        codex_auth_dir=CODEX_AUTH_DIR, timeout_seconds=1800,
                        codex_reasoning_effort="medium", model_override="gpt-5.6-terra",
                    )
            except Exception as exc:
                _write(attempt_root / "failure.json", {
                    "type": type(exc).__name__, "message": str(exc), "provider_call_started": False,
                })
                _write(state_path, {"status": "pre_provider_transport_failed", "attempt": attempt,
                                    "error": str(exc), "failed_at": _now()})
                if row["role"] == "primary" and primary_recoveries < PRIMARY_RECOVERY_LIMIT:
                    primary_recoveries += 1
                    continue
                if row["role"] == "check" and check_recoveries < CHECK_RECOVERY_LIMIT:
                    check_recoveries += 1
                    continue
                raise RuntimeError("r10_11_campaign_recovery_limit_reached_before_provider") from exc
            try:
                if code:
                    raise ConnectionError(f"provider_transport_failed:{code}:{error}")
                grade = _parse_finalize(attempt_root, row, scope["hashes"][row["assignment_id"]])
                _write(session / "review.json", grade)
                _write(state_path, {"status": "completed", "attempt": attempt, "completed_at": _now(),
                                    "review_sha256": grade.canonical_sha256()})
                results.append(grade.model_dump(mode="json"))
                break
            except Exception as exc:
                _write(attempt_root / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
                recoverable = isinstance(exc, ConnectionError) or _recoverable(exc)
                if not recoverable:
                    _write(state_path, {"status": "incomplete", "terminal": True, "error": str(exc)})
                    raise
                if row["role"] == "primary" and primary_recoveries < PRIMARY_RECOVERY_LIMIT:
                    primary_recoveries += 1
                    continue
                if row["role"] == "check" and check_recoveries < CHECK_RECOVERY_LIMIT:
                    check_recoveries += 1
                    continue
                _write(state_path, {"status": "incomplete", "terminal": True, "error": str(exc)})
                raise RuntimeError("r10_11_campaign_recovery_limit_reached") from exc
    summary = summarize(results, scope)
    _write(run_root / "summary.json", summary)
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.independent_grader_receipt.1", "scope_sha256": canonical_json_sha256(scope),
        "status": summary["status"], "provider_calls": calls, "primary_recoveries": primary_recoveries,
        "check_recoveries": check_recoveries, "completed_at": _now(),
    })
    return summary


def summarize(results: list[dict[str, Any]], scope: dict[str, Any]) -> dict[str, Any]:
    primary = {(row["task_id"], row["submission_id"]): row for row in results if row["judge_id"] == PRIMARY_JUDGE}
    checks = [row for row in results if row["judge_id"] == CHECK_JUDGE]
    sentinel = []
    for check in checks:
        main = primary[(check["task_id"], check["submission_id"])]
        high = max(item["max_score"] for item in main["items"])
        main_items = {item["rubric_item_id"]: item for item in main["items"]}
        extreme = any(
            item["max_score"] == high and {item["awarded"], main_items[item["rubric_item_id"]]["awarded"]} == {0, high}
            for item in check["items"]
        )
        sentinel.append({"task_id": check["task_id"], "submission_id": check["submission_id"],
                         "normalized_delta": round(abs(check["normalized_score"] - main["normalized_score"]), 6),
                         "high_weight_extreme_conflict": extreme})
    valid = len(primary) == 17 and len(checks) == 4 and all(
        row["material_status"] == "complete" and row["total_score"] == sum(item["awarded"] for item in row["items"])
        for row in results
    )
    sentinel_ok = len(sentinel) == 4 and all(row["normalized_delta"] <= .10 and not row["high_weight_extreme_conflict"] for row in sentinel)
    return {"summary_version": "r10.independent_grader_summary.1",
            "status": "accepted" if valid and sentinel_ok else "incomplete",
            "evidence_level": "provisional_llm_proxy", "completed": len(results), "planned": len(scope["assignments"]),
            "structural_valid": valid, "sentinel_acceptance": sentinel_ok, "sentinels": sentinel,
            "gdpval_ranking_direction": "diagnostic_only", "r10_9_model_gap": "diagnostic_only"}


def close_incomplete(run_root: Path) -> dict[str, Any]:
    """Close a stopped campaign from persisted evidence without provider calls."""
    scope = json.loads((run_root / "scope.json").read_text(encoding="utf-8"))
    results = [
        json.loads((run_root / "sessions" / row["assignment_id"] / "review.json").read_text(encoding="utf-8"))
        for row in scope["assignments"]
        if (run_root / "sessions" / row["assignment_id"] / "review.json").is_file()
    ]
    primary = [row for row in results if row["judge_id"] == PRIMARY_JUDGE]
    by_source: dict[str, dict[str, list[float]]] = {"gdpval": {}, "r10_9": {}}
    source_by_task = {row["task_id"]: row["source"] for row in scope["assignments"]}
    task_scores = []
    for row in primary:
        source = source_by_task[row["task_id"]]
        by_source[source].setdefault(row["submission_id"], []).append(row["normalized_score"])
        task_scores.append({"task_id": row["task_id"], "submission_id": row["submission_id"],
                            "normalized_score": row["normalized_score"]})
    means = {
        source: {stack: round(sum(values) / len(values), 6) for stack, values in stacks.items()}
        for source, stacks in by_source.items()
    }
    terminal = []
    for row in scope["assignments"]:
        state = run_root / "sessions" / row["assignment_id"] / "state.json"
        if state.is_file():
            value = json.loads(state.read_text(encoding="utf-8"))
            if value.get("status") != "completed":
                terminal.append({"assignment_id": row["assignment_id"], "task_id": row["task_id"],
                                 "judge_id": row["judge_id"], "state": value})
    summary = {
        "summary_version": "r10.independent_grader_summary.1", "status": "incomplete",
        "stop_reason": "terra_sentinel_schema_recovery_budget_exhausted",
        "evidence_level": "provisional_llm_proxy", "completed": len(results),
        "planned": len(scope["assignments"]), "primary_completed": len(primary),
        "primary_structural_valid": len(primary) == 17 and all(
            row["material_status"] == "complete" and
            row["total_score"] == sum(item["awarded"] for item in row["items"])
            for row in primary
        ),
        "sentinels_completed": len(results) - len(primary), "sentinels_planned": 4,
        "sentinel_acceptance": False, "terminal_assignments": terminal,
        "diagnostic_means": means, "diagnostic_task_scores": task_scores,
        "gdpval_ranking_direction": "diagnostic_only", "r10_9_model_gap": "diagnostic_only",
    }
    _write(run_root / "summary.json", summary)
    amendments = sorted(run_root.glob("scope_amendment*.json"))
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.independent_grader_receipt.1",
        "scope_sha256": canonical_json_sha256(scope),
        "scope_amendment_sha256": [_file_sha256(path) for path in amendments],
        "closeout_controller_sha256": _file_sha256(Path(__file__)),
        "status": "incomplete", "normal_primary_provider_calls": 17,
        "primary_format_or_transport_recoveries": 0,
        "pre_provider_transport_failures": 1,
        "terra_provider_requests": 2, "terra_format_recoveries": 1,
        "closed_at": _now(), "stop_reason": summary["stop_reason"],
    })
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("dry-run", "execute", "status", "close-incomplete"))
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    if args.action == "dry-run":
        scope = prepare(args.run_root)
        print(json.dumps({"status": "prepared", "assignments": len(scope["assignments"]),
                          "primary_calls": 17, "primary_recovery_cap": 3,
                          "check_calls": 4, "check_recovery_cap": 1,
                          "models": [PRIMARY_JUDGE, CHECK_JUDGE], "image": IMAGE}, indent=2))
    elif args.action == "execute":
        print(json.dumps(execute(args.run_root), ensure_ascii=False, indent=2))
    elif args.action == "close-incomplete":
        print(json.dumps(close_incomplete(args.run_root), ensure_ascii=False, indent=2))
    else:
        for name in ("scope.json", "receipt.json", "summary.json"):
            path = args.run_root / name
            print(path.read_text(encoding="utf-8") if path.is_file() else f"{name}: missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
