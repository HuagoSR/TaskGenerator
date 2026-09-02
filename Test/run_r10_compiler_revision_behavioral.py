"""Evaluate the two frozen R10.8B-2 tasks in the fixed Huago environment.

The harness leaves the four-task pilot immutable.  Both native solver and
judge stacks run in the same restricted remote container contract so local
LibreOffice or Codex state cannot affect the result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

from run_r10_behavioral_pilot import (
    CHATGPT_CODEX_STACK, DEEPSEEK_OPENCODE_STACK, TUZI_CODEX_STACK,
    _codex_turn_completed, _execute_judge, _execute_solver, _record_probe,
    _run_remote, _safe_remote_root,
)
from task_generator.evaluation.r10_behavioral import binding_from_task, sha256_json

TASKS = {
    "r10r_audit_revenue_evidence_reliability": (ROOT / "artifacts/r10/r10_8b2_compiler_revision_retry3_20260901/tasks/r10r_audit_revenue_evidence_reliability", "audit_compliance", "near_tie"),
    "r10r_procurement_price_reasonableness": (ROOT / "artifacts/r10/r10_8b2_compiler_revision_retry3_20260901/tasks/r10r_procurement_price_reasonableness", "procurement_operations", "saturated"),
}
GPT_TRANSPORTS = {
    "chatgpt_codex": CHATGPT_CODEX_STACK,
    "tuzi_codex": TUZI_CODEX_STACK,
}
DEFAULT_GPT_TRANSPORT = "chatgpt_codex"
STACKS = (CHATGPT_CODEX_STACK, DEEPSEEK_OPENCODE_STACK)
REMOTE_CURRENT_ACCOUNT_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
SLIM_JUDGE_REASONING_EFFORT = "medium"
MINIMAL_ACCOUNT_PROBE_TIMEOUT_SECONDS = 120
SLIM_JUDGE_PROBE_TIMEOUT_SECONDS = 600


def _stacks(gpt_transport: str) -> tuple[str, str]:
    try:
        return GPT_TRANSPORTS[gpt_transport], DEEPSEEK_OPENCODE_STACK
    except KeyError as exc:
        raise ValueError("r10_compiler_revision_gpt_transport_invalid") from exc


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _auth_profile_fingerprint(codex_auth_dir: str) -> str:
    return hashlib.sha256(
        f"r10-codex-auth-profile:{codex_auth_dir}".encode("utf-8")
    ).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_commit() -> str:
    """Use Git on a developer checkout and immutable build metadata in images."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True,
        )
    except FileNotFoundError:
        result = None
    if result is not None and result.returncode == 0 and len(result.stdout.strip()) == 40:
        return result.stdout.strip()
    commit = os.environ.get("TASKGEN_SOURCE_COMMIT", "")
    if len(commit) == 40 and all(character in "0123456789abcdef" for character in commit):
        return commit
    raise RuntimeError("r10_compiler_revision_source_commit_unavailable")


def _scope(
    run_id: str, *, image: str, image_sha256: str,
    public_gate_evidence: dict[str, Any], gpt_transport: str = DEFAULT_GPT_TRANSPORT,
    codex_auth_dir: str = REMOTE_CURRENT_ACCOUNT_AUTH_DIR,
) -> dict[str, Any]:
    commit = _source_commit()
    stacks = _stacks(gpt_transport)
    bindings = []
    for task_id, (root, domain, old_classification) in TASKS.items():
        binding = binding_from_task(root, domain=domain)
        bindings.append({**binding.model_dump(mode="json"), "old_classification": old_classification})
    return {
        "scope_version": "r10.compiler_revision_behavioral_scope.1", "campaign_id": run_id,
        "source_commit": commit, "bindings": bindings,
        "solver_stacks": list(stacks), "judges": list(stacks),
        "gpt_environment": {
            "transport": gpt_transport,
            "provider": "openai_chatgpt" if gpt_transport == "chatgpt_codex" else "tuzi",
            "authentication": "chatgpt_oauth" if gpt_transport == "chatgpt_codex" else "provider_key",
            "auth_profile_fingerprint": _auth_profile_fingerprint(codex_auth_dir)
            if gpt_transport == "chatgpt_codex" else None,
            "image": image, "image_sha256": image_sha256,
            "model": "gpt-5.6-sol", "codex_version": "0.149.1", "timeout_seconds": 1800,
            "judge_reasoning_effort": SLIM_JUDGE_REASONING_EFFORT,
        },
        "deepseek_environment": {"transport": "huago_opencode", "image": image, "image_sha256": image_sha256, "model": "deepseek-v4-pro", "timeout_seconds": 1800},
        "public_probe_required": True, "complex_judge_probe_required": True,
        "public_gate_evidence": public_gate_evidence,
        "solver_attempt_limit": 1, "judge_format_attempt_limit": 2,
        "excluded_actions": ["task_generation", "candidate_mutation", "release", "training", "promotion"],
        "professional_validity": "provisional",
    }


def _remote_solver(
    *, output_root: Path, host: str, remote_root: str, task_id: str,
    task_root: Path, domain: str, stack: str, image: str,
    codex_auth_dir: str = REMOTE_CURRENT_ACCOUNT_AUTH_DIR,
) -> dict[str, Any]:
    binding = binding_from_task(task_root, domain=domain)
    outcome = _execute_solver(
        host=host, remote_root=remote_root, output_root=output_root,
        binding=binding, stack=stack, image=image, codex_auth_dir=codex_auth_dir,
    )
    return outcome.model_dump(mode="json")


def _record_complex_judge_probe(
    *, output_root: Path, host: str, remote_root: str, image: str,
    stacks: tuple[str, str] = STACKS,
) -> bool:
    """Exercise the exact structured judge path using only public material."""
    from run_r10_teacher_anchor_regrade import _stage_public_judge_probe

    probe_root = output_root / "public_complex_judge_probe"
    task_root, delivery = _stage_public_judge_probe(probe_root, complex_input=True)
    results = {
        judge: _jsonable(_execute_judge(
            host=host, remote_root=remote_root, output_root=probe_root,
            task_root=task_root, task_id="public-probe", delivery=delivery,
            judge=judge, image=image,
        ))
        for judge in stacks
    }
    passed = all(item["status"] == "completed" for item in results.values())
    _write(probe_root / "result.json", {"decision": "pass" if passed else "incomplete", "results": results})
    return passed


def _record_public_gates(
    *, output_root: Path, host: str, remote_root: str, image: str,
    stacks: tuple[str, str] = STACKS,
) -> tuple[bool, dict[str, bool]]:
    """Run the public-only admission gates before any private binding is read."""
    probes = {
        stack: _record_probe(
            output_root=output_root, host=host, remote_root=remote_root,
            stack=stack, image=image,
        )
        for stack in stacks
    }
    if not all(probes.values()):
        _write(output_root / "result.json", {
            "decision": "incomplete", "reason": "public_probe_failed", "probes": probes,
        })
        return False, probes
    if not _record_complex_judge_probe(
        output_root=output_root, host=host, remote_root=remote_root, image=image, stacks=stacks,
    ):
        _write(output_root / "result.json", {
            "decision": "incomplete", "reason": "public_complex_judge_probe_failed", "probes": probes,
        })
        return False, probes
    _write(output_root / "result.json", {"decision": "public_gates_passed", "probes": probes})
    return True, probes


def _validate_reused_public_evidence(root: Path) -> dict[str, Any]:
    """Reuse immutable file-tool and DeepSeek judge evidence from the same image."""
    required = {
        "gpt_tool_probe": root / "public_probes" / CHATGPT_CODEX_STACK / "probe_result.json",
        "deepseek_tool_probe": root / "public_probes" / DEEPSEEK_OPENCODE_STACK / "probe_result.json",
        "deepseek_complex_judge": root / "public_complex_judge_probe" / "judges" / DEEPSEEK_OPENCODE_STACK / "public-probe" / "attempt_01" / "review.json",
    }
    for path in required.values():
        if not path.is_file():
            raise FileNotFoundError("r10_reused_public_evidence_missing")
    for key in ("gpt_tool_probe", "deepseek_tool_probe"):
        if json.loads(required[key].read_text(encoding="utf-8")).get("decision") != "pass":
            raise ValueError("r10_reused_tool_probe_not_passed")
    json.loads(required["deepseek_complex_judge"].read_text(encoding="utf-8"))
    return {
        "root_tree_sha256": _public_tree_sha256(root),
        "files": {
            key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in required.items()
        },
    }


def _record_minimal_account_probe(
    *, output_root: Path, host: str, remote_root: str, image: str,
    codex_auth_dir: str,
) -> bool:
    workspace = output_root / "minimal_account_probe" / "workspace"
    workspace.mkdir(parents=True)
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"status": {"const": "ok"}}, "required": ["status"],
    }
    _write(workspace / "grade_schema.json", schema)
    (workspace / "TASK.md").write_text(
        'Return exactly {"status":"ok"}. Do not run commands or inspect files.\n',
        encoding="utf-8",
    )
    code, stdout, stderr = _run_remote(
        host=host, remote=f"{remote_root}/minimal-account-probe", local=workspace,
        stack=CHATGPT_CODEX_STACK, grade=True, image=image,
        codex_auth_dir=codex_auth_dir,
        timeout_seconds=MINIMAL_ACCOUNT_PROBE_TIMEOUT_SECONDS,
        codex_reasoning_effort="low",
    )
    raw = workspace / "grade.raw.json"
    parsed = None
    if raw.is_file():
        try:
            parsed = json.loads(raw.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = None
    passed = code == 0 and _codex_turn_completed(workspace / "agent.jsonl") and parsed == {"status": "ok"}
    _write(workspace.parent / "result.json", {
        "decision": "pass" if passed else "incomplete", "returncode": code,
        "turn_completed": _codex_turn_completed(workspace / "agent.jsonl"),
        "output_valid": parsed == {"status": "ok"}, "stderr": stderr[-2000:],
    })
    return passed


def _record_slim_official_gates(
    *, output_root: Path, host: str, remote_root: str, image: str,
    codex_auth_dir: str, reused_public_root: Path,
) -> bool:
    reused = _validate_reused_public_evidence(reused_public_root)
    if not _record_minimal_account_probe(
        output_root=output_root, host=host, remote_root=remote_root,
        image=image, codex_auth_dir=codex_auth_dir,
    ):
        _write(output_root / "result.json", {
            "decision": "incomplete", "reason": "minimal_account_probe_failed",
            "reused_public_evidence": reused,
        })
        return False
    probe_root = output_root / "slim_public_judge_probe"
    source_probe = reused_public_root / "public_complex_judge_probe"
    staged_root = probe_root / "public_task"
    delivery = probe_root / "public_delivery.xlsx"
    shutil.copytree(source_probe / "public_task", staged_root)
    shutil.copy2(source_probe / "public_delivery.xlsx", delivery)
    result = _jsonable(_execute_judge(
        host=host, remote_root=remote_root, output_root=probe_root,
        task_root=staged_root, task_id="public-probe", delivery=delivery,
        judge=CHATGPT_CODEX_STACK, image=image, codex_auth_dir=codex_auth_dir,
        timeout_seconds=SLIM_JUDGE_PROBE_TIMEOUT_SECONDS,
        codex_reasoning_effort=SLIM_JUDGE_REASONING_EFFORT, attempt_limit=1,
    ))
    passed = result.get("status") == "completed"
    _write(probe_root / "result.json", result)
    _write(output_root / "result.json", {
        "decision": "public_gates_passed" if passed else "incomplete",
        "reason": None if passed else "slim_public_judge_probe_failed",
        "auth_profile_fingerprint": _auth_profile_fingerprint(codex_auth_dir),
        "reused_public_evidence": reused,
        "minimal_account_probe": "pass", "slim_public_judge_probe": "pass" if passed else "incomplete",
    })
    return passed


def _public_tree_sha256(root: Path) -> str:
    """Hash public probe output without the self-referential evidence record."""
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "public_gate_evidence.json"):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_public_gate_evidence(
    *, output_root: Path, image: str, image_sha256: str,
    stacks: tuple[str, str] = STACKS,
) -> dict[str, Any]:
    result = json.loads((output_root / "result.json").read_text(encoding="utf-8"))
    evidence = {
        "evidence_version": "r10.public_gate_evidence.1",
        "source_commit": _source_commit(),
        "image": image,
        "image_sha256": image_sha256,
        "stacks": list(stacks),
        "decision": result["decision"],
        "result_sha256": sha256_json(result),
        "public_tree_sha256": _public_tree_sha256(output_root),
    }
    _write(output_root / "public_gate_evidence.json", evidence)
    return evidence


def _load_public_gate_evidence(
    *, root: Path, image: str, image_sha256: str,
    stacks: tuple[str, str] = STACKS,
    codex_auth_dir: str | None = None,
) -> dict[str, Any]:
    evidence_path = root / "public_gate_evidence.json"
    if not evidence_path.is_file():
        raise FileNotFoundError("r10_compiler_revision_public_gate_evidence_missing")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("evidence_version") != "r10.public_gate_evidence.1":
        raise ValueError("r10_compiler_revision_public_gate_evidence_version_invalid")
    if evidence.get("decision") != "public_gates_passed":
        raise ValueError("r10_compiler_revision_public_gate_not_passed")
    if evidence.get("source_commit") != _source_commit() or evidence.get("image") != image or evidence.get("image_sha256") != image_sha256:
        raise ValueError("r10_compiler_revision_public_gate_fingerprint_drift")
    if evidence.get("stacks") != list(stacks) or evidence.get("public_tree_sha256") != _public_tree_sha256(root):
        raise ValueError("r10_compiler_revision_public_gate_evidence_drift")
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    if codex_auth_dir is not None and result.get("auth_profile_fingerprint") != _auth_profile_fingerprint(codex_auth_dir):
        raise ValueError("r10_compiler_revision_public_gate_auth_profile_drift")
    if evidence.get("result_sha256") != sha256_json(result):
        raise ValueError("r10_compiler_revision_public_gate_result_drift")
    return evidence


def _score_pair(
    *, output_root: Path, host: str, remote_root: str, solver: str,
    task_id: str, task_root: Path, delivery: Path, image: str,
    stacks: tuple[str, str] = STACKS,
    codex_auth_dir: str = REMOTE_CURRENT_ACCOUNT_AUTH_DIR,
) -> dict[str, Any]:
    return {
        judge: _jsonable(_execute_judge(
            host=host, remote_root=remote_root,
            output_root=output_root / "judge_assignments" / solver / task_id,
            task_root=task_root, task_id=task_id, delivery=delivery, judge=judge, image=image,
            codex_auth_dir=codex_auth_dir,
            codex_reasoning_effort=SLIM_JUDGE_REASONING_EFFORT if judge == CHATGPT_CODEX_STACK else None,
        ))
        for judge in stacks
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _aggregate(
    records: dict[str, dict[str, Any]], *, stacks: tuple[str, str] = STACKS,
) -> dict[str, Any]:
    diagnoses = []
    for task_id, (_, _, old) in TASKS.items():
        by_solver = records[task_id]
        scores, majors, ambiguous = {}, {}, False
        complete = True
        for solver in stacks:
            item = by_solver.get(solver, {})
            reviews = item.get("reviews", {})
            if not item.get("delivery", {}).get("valid") or not all(reviews.get(judge, {}).get("status") == "completed" for judge in stacks):
                complete = False
                continue
            values = [reviews[judge]["review"]["weighted_score"] for judge in stacks]
            flags = [reviews[judge]["review"]["major_defect"] for judge in stacks]
            scores[solver] = sum(values) / 2
            majors[solver] = any(flags)
            ambiguous = ambiguous or abs(values[0] - values[1]) >= 0.125 or flags[0] != flags[1]
        gap = abs(scores[stacks[0]] - scores[stacks[1]]) if len(scores) == 2 else None
        differs = len(majors) == 2 and majors[stacks[0]] != majors[stacks[1]]
        clean = bool(complete and not ambiguous and ((gap is not None and gap >= 0.05) or differs))
        diagnoses.append({"task_id": task_id, "old_classification": old, "scores": scores, "score_gap": gap, "major_defect_differs": differs, "judge_ambiguous": ambiguous, "classification": "cleanly_discriminative" if clean else "incomplete" if not complete else "judge_ambiguous" if ambiguous else "near_tie"})
    clean = sum(item["classification"] == "cleanly_discriminative" for item in diagnoses)
    if any(item["classification"] == "incomplete" for item in diagnoses): decision = "incomplete"
    elif any(item["classification"] == "judge_ambiguous" for item in diagnoses): decision = "evaluator_revision_required"
    elif clean == 2: decision = "compiler_revision_supported"
    elif clean == 1: decision = "compiler_revision_mixed"
    else: decision = "compiler_revision_not_supported"
    return {"result_version": "r10.compiler_revision_behavioral_result.1", "decision": decision, "task_diagnoses": diagnoses, "professional_validity": "provisional"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="r10_8b2_compiler_revision_behavioral_20260901")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_8b2_compiler_revision_behavioral_20260901")
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--image", required=True)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--gpt-transport", choices=tuple(GPT_TRANSPORTS), default=DEFAULT_GPT_TRANSPORT)
    parser.add_argument("--scope-only", action="store_true")
    parser.add_argument("--public-only", action="store_true")
    parser.add_argument("--public-gate-root", type=Path)
    parser.add_argument("--authorized-scope-sha256")
    parser.add_argument("--codex-auth-dir", default=REMOTE_CURRENT_ACCOUNT_AUTH_DIR)
    parser.add_argument("--reused-public-root", type=Path)
    args = parser.parse_args()
    if args.scope_only and args.public_only:
        raise ValueError("r10_compiler_revision_behavioral_modes_conflict")
    stacks = _stacks(args.gpt_transport)
    if args.public_only:
        if args.authorized_scope_sha256 or args.public_gate_root:
            raise PermissionError("r10_compiler_revision_public_probe_does_not_accept_scope")
        if args.output_root.exists():
            raise FileExistsError("r10_compiler_revision_public_probe_output_exists")
        args.output_root.mkdir(parents=True)
        if args.gpt_transport == "chatgpt_codex":
            if args.reused_public_root is None:
                raise ValueError("r10_reused_public_evidence_required")
            passed = _record_slim_official_gates(
                output_root=args.output_root, host=args.host,
                remote_root=_safe_remote_root(args.host, args.run_id), image=args.image,
                codex_auth_dir=args.codex_auth_dir,
                reused_public_root=args.reused_public_root,
            )
        else:
            passed, _ = _record_public_gates(
                output_root=args.output_root, host=args.host,
                remote_root=_safe_remote_root(args.host, args.run_id), image=args.image, stacks=stacks,
            )
        if not passed:
            raise SystemExit(1)
        _write_public_gate_evidence(
            output_root=args.output_root, image=args.image, image_sha256=args.image_sha256, stacks=stacks,
        )
        return
    if args.public_gate_root is None:
        raise ValueError("r10_compiler_revision_public_gate_evidence_required")
    public_gate_evidence = _load_public_gate_evidence(
        root=args.public_gate_root, image=args.image, image_sha256=args.image_sha256,
        stacks=stacks,
        codex_auth_dir=args.codex_auth_dir if args.gpt_transport == "chatgpt_codex" else None,
    )
    scope = _scope(
        args.run_id, image=args.image, image_sha256=args.image_sha256,
        public_gate_evidence=public_gate_evidence, gpt_transport=args.gpt_transport,
        codex_auth_dir=args.codex_auth_dir,
    ); digest = sha256_json(scope)
    if args.scope_only:
        if args.output_root.exists(): raise FileExistsError("r10_compiler_revision_behavioral_output_exists")
        args.output_root.mkdir(parents=True); _write(args.output_root / "scope.json", scope); print(digest); return
    if args.authorized_scope_sha256 != digest: raise PermissionError("r10_compiler_revision_behavioral_scope_mismatch")
    if not args.output_root.is_dir() or set(path.name for path in args.output_root.iterdir()) != {"scope.json"}: raise FileExistsError("r10_compiler_revision_behavioral_output_invalid")
    _write(args.output_root / "receipt.json", {"scope_sha256": digest, "consumed_at": _now()})
    remote_root = _safe_remote_root(args.host, args.run_id)
    records: dict[str, dict[str, Any]] = {task_id: {} for task_id in TASKS}
    for task_id, (task_root, domain, _) in TASKS.items():
        for stack in stacks:
            records[task_id][stack] = _remote_solver(
                output_root=args.output_root, host=args.host, remote_root=remote_root,
                task_id=task_id, task_root=task_root, domain=domain, stack=stack, image=args.image,
                codex_auth_dir=args.codex_auth_dir,
            )
    for task_id, (task_root, _, _) in TASKS.items():
        for solver in stacks:
            item = records[task_id][solver]
            if item["delivery"]["valid"]:
                delivery = args.output_root / "solvers" / solver / task_id / "workspace" / item["delivery"]["relative_path"]
                item["reviews"] = _score_pair(
                    output_root=args.output_root, host=args.host, remote_root=remote_root,
                    solver=solver, task_id=task_id, task_root=task_root,
                    delivery=delivery, image=args.image, stacks=stacks,
                    codex_auth_dir=args.codex_auth_dir,
                )
            else: item["reviews"] = {}
    _write(args.output_root / "records.json", _jsonable(records)); _write(
        args.output_root / "result.json", _aggregate(_jsonable(records), stacks=stacks),
    )


if __name__ == "__main__": main()
