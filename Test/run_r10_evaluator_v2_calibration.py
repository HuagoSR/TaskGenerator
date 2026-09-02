"""Run the bounded R10.10 evaluator development/holdout calibration.

The runner never reruns solvers.  It counterbalances the two frozen R10.9
deliveries, uses the campaign-scoped V2 evaluator profile, and persists every
Judge session before moving to the next assignment.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

from run_r10_behavioral_pilot import (
    CHATGPT_CODEX_STACK,
    DEEPSEEK_OPENCODE_STACK,
    _codex_turn_completed,
    _extract_opencode_json,
    _run_remote,
)
from task_generator.core.scenario_first import TaskDecisionMatrixV1
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.r10_evaluator_v2 import (
    CounterbalancedPairReviewV2,
    EvaluatorProfileV2,
    assess_counterbalance_stability,
    canonical_sha256,
    confirm_major_errors,
    normalize_pair_review,
    profile_from_frozen_supervision,
    score_bundle,
)
from task_generator.planning.scenario_task_compiler import TaskSpecificRubricV1, tree_sha256
from task_generator.production.campaign import atomic_json


SOURCE_RUN = ROOT / "artifacts/r10/r10_9_world_first_pilot_20260902"
DEFAULT_RUN = ROOT / "artifacts/r10/r10_10_evaluator_v2_20260903"
IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099"
IMAGE_SHA256 = "3c6c76324780a911ff7b47bf52629280b4f2a49f26248540de049a61b9129363"
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
REMOTE_HOME = "/home/huagosr/taskgenerator-data/r10-evaluator-v2"
GPT_SOLVER = "gpt-5.6-sol@chatgpt_codex"
DEEPSEEK_SOLVER = "deepseek-v4-pro@official_opencode"
JUDGES = {
    "gpt-5.6-terra@chatgpt_codex": {
        "stack": CHATGPT_CODEX_STACK, "model": "gpt-5.6-terra", "reasoning": "medium",
    },
    "deepseek-v4-pro@official_opencode": {
        "stack": DEEPSEEK_OPENCODE_STACK, "model": "deepseek-v4-pro", "variant": "max",
    },
}
LUNA_JUDGE = {
    "gpt-5.6-luna@chatgpt_codex": {
        "stack": CHATGPT_CODEX_STACK, "model": "gpt-5.6-luna", "reasoning": "medium",
    }
}
R10_SPLITS = {
    "development": (
        "r10_9_audit_reliability_baseline_task",
        "r10_9_procurement_price_baseline_task",
    ),
    "holdout": (
        "r10_9_audit_reliability_adversarial_task",
        "r10_9_procurement_price_adversarial_task",
    ),
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    atomic_json(path, value)


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        capture_output=True, check=True,
    ).stdout.strip()


def _task(task_id: str) -> Path:
    root = SOURCE_RUN / "tasks" / task_id
    if not root.is_dir():
        raise FileNotFoundError(f"r10_10_task_missing:{task_id}")
    return root


def _delivery(task_id: str, solver: str) -> Path:
    root = SOURCE_RUN / "solvers" / solver / task_id / "workspace/deliverable_files"
    files = sorted(path for path in root.glob("*") if path.is_file())
    if len(files) != 1:
        raise ValueError(f"r10_10_frozen_delivery_count_invalid:{task_id}:{solver}")
    return files[0]


def build_profiles(run_root: Path, iteration: str) -> dict[str, EvaluatorProfileV2]:
    profiles: dict[str, EvaluatorProfileV2] = {}
    for task_id in (*R10_SPLITS["development"], *R10_SPLITS["holdout"]):
        task = _task(task_id)
        teacher = task / "teacher"
        profile = profile_from_frozen_supervision(
            task_id=task_id, task_tree_sha256=tree_sha256(task),
            teacher_tree_sha256=tree_sha256(teacher),
            matrix=TaskDecisionMatrixV1.model_validate_json(
                (teacher / "decision_matrix.json").read_text(encoding="utf-8")
            ),
            rubric=TaskSpecificRubricV1.model_validate_json(
                (teacher / "task_specific_rubric.json").read_text(encoding="utf-8")
            ),
            iteration=iteration,
        )
        profiles[task_id] = profile
        _write(run_root / "profiles" / f"{task_id}.json", profile.model_dump(mode="json"))
    return profiles


def _scope(run_id: str, profiles: dict[str, EvaluatorProfileV2]) -> dict[str, Any]:
    return {
        "scope_version": "r10.evaluator_v2_calibration_scope.1",
        "campaign_id": run_id,
        "source_commit": _git_head(),
        "source_r10_9_tree_sha256": tree_sha256(SOURCE_RUN / "tasks"),
        "image": IMAGE, "image_sha256": IMAGE_SHA256,
        "r10_splits": {key: list(value) for key, value in R10_SPLITS.items()},
        "profile_sha256": {key: value.canonical_sha256() for key, value in profiles.items()},
        "frozen_delivery_sha256": {
            f"{task_id}:{solver}": _sha_file(_delivery(task_id, solver))
            for task_id in profiles for solver in (GPT_SOLVER, DEEPSEEK_SOLVER)
        },
        "judges": JUDGES,
        "luna_judge_trigger": "only_after_primary_judge_conflict",
        "orders": ["a_b", "b_a"],
        "semantic_retry_limit": 0,
        "format_retry_limit": 1,
        "holdout_may_be_opened_once": True,
        "excluded_actions": ["solver_rerun", "task_mutation", "teacher_mutation", "training", "release"],
    }


def _sha_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage(
    *, target: Path, task_id: str, profile: EvaluatorProfileV2,
    order: str, judge_id: str,
) -> None:
    target.mkdir(parents=True)
    task = _task(task_id)
    shutil.copy2(task / "TASK.md", target / "candidate_task.md")
    shutil.copy2(task / "deliverable_contract.json", target / "deliverable_contract.json")
    shutil.copytree(task / "reference_files", target / "reference_files")
    for name in ("teacher_truth.json", "decision_matrix.json", "task_specific_rubric.json"):
        shutil.copy2(task / "teacher" / name, target / name)
    _write(target / "evaluator_profile_v2.json", profile.model_dump(mode="json"))
    first = _delivery(task_id, GPT_SOLVER if order == "a_b" else DEEPSEEK_SOLVER)
    second = _delivery(task_id, DEEPSEEK_SOLVER if order == "a_b" else GPT_SOLVER)
    shutil.copy2(first, target / f"anonymous_slot_1{first.suffix.lower()}")
    shutil.copy2(second, target / f"anonymous_slot_2{second.suffix.lower()}")
    schema = _strict_output_schema(CounterbalancedPairReviewV2.model_json_schema())
    _write(target / "grade_schema.json", schema)
    (target / "TASK.md").write_text(
        f"""Act as an independent professional evaluator for task `{task_id}`.

Inspect candidate_task.md, the reference files, frozen teacher supervision, evaluator_profile_v2.json, and both anonymous work products. First assess each work product independently against every atomic criterion. Only then compare them. Do not infer model or provider identity.

For each slot, include every criterion exactly once with met/partial/not_met, concrete file-level evidence, and a concise rationale. Alleged major errors must use only error IDs defined in evaluator_profile_v2.json and must satisfy that rule's trigger fact, necessary evidence, and business consequence; do not invent broad fatal errors. Use `tie` when there is no professionally meaningful preference.

Return exactly one JSON object matching grade_schema.json. Set task_id to `{task_id}`, judge_id to `{judge_id}`, order_id to `{order}`. The controller recomputes scores and major-error confirmation.
""",
        encoding="utf-8",
    )


def _parse_review(workspace: Path, *, stdout: str, judge_id: str) -> CounterbalancedPairReviewV2:
    raw = workspace / "grade.raw.json"
    if not raw.is_file() and judge_id.startswith("deepseek"):
        text = (workspace / "agent.jsonl").read_text(encoding="utf-8", errors="replace") if (workspace / "agent.jsonl").is_file() else stdout
        extracted = _extract_opencode_json(text) or _extract_fenced_json_from_opencode(text)
        if extracted:
            raw.write_text(extracted, encoding="utf-8")
    if not raw.is_file():
        raise ValueError("r10_10_judge_output_missing")
    return CounterbalancedPairReviewV2.model_validate_json(raw.read_text(encoding="utf-8"))


def _extract_fenced_json_from_opencode(text: str) -> str | None:
    """Recover a final JSON object wrapped in prose or a Markdown fence.

    OpenCode's JSON event stream is valid even when the model's final text is
    not a bare JSON object.  This is a controller parsing repair, not a second
    semantic model attempt.
    """

    candidates: list[str] = []
    for line in reversed(text.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = event.get("part") if isinstance(event, dict) else None
        value = part.get("text") if isinstance(part, dict) else None
        if isinstance(value, str):
            candidates.append(value)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                value, end = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            remainder = candidate[index + end:].strip().replace("```", "").strip()
            if isinstance(value, dict) and not remainder:
                return json.dumps(value, ensure_ascii=False)
    return None


def _run_assignment(
    *, run_root: Path, run_id: str, task_id: str, profile: EvaluatorProfileV2,
    judge_id: str, config: dict[str, str], order: str,
) -> CounterbalancedPairReviewV2:
    assignment = f"{task_id}__{judge_id.replace('@', '_')}__{order}"
    assignment_root = run_root / "sessions" / assignment
    state = assignment_root / "state.json"
    if state.exists():
        value = json.loads(state.read_text(encoding="utf-8"))
        if value.get("status") == "completed":
            return CounterbalancedPairReviewV2.model_validate_json(
                (assignment_root / "review.json").read_text(encoding="utf-8")
            )
        if value.get("status") == "incomplete":
            workspace = assignment_root / "workspace"
            try:
                recovered = _parse_review(workspace, stdout="", judge_id=judge_id)
            except Exception as exc:
                raise RuntimeError(f"r10_10_started_assignment_not_rerunnable:{assignment}") from exc
            if recovered.task_id != task_id or recovered.judge_id != judge_id or recovered.order_id != order:
                raise ValueError("r10_10_recovered_judge_identity_mismatch")
            _write(assignment_root / "review.json", recovered.model_dump(mode="json"))
            _write(state, {
                "status": "completed", "recovered_without_provider_call": True,
                "completed_at": _now(), "review_sha256": recovered.canonical_sha256(),
                "original_first_failure": value.get("first_failure"),
            })
            return recovered
        raise RuntimeError(f"r10_10_started_assignment_not_rerunnable:{assignment}")
    workspace = assignment_root / "workspace"
    _stage(target=workspace, task_id=task_id, profile=profile, order=order, judge_id=judge_id)
    _write(state, {"status": "running", "started_at": _now(), "input_tree_sha256": tree_sha256(workspace)})
    started = time.monotonic()
    code, stdout, stderr = _run_remote(
        host="huago-cone", remote=f"{REMOTE_HOME}/{run_id}/{assignment}", local=workspace,
        stack=config["stack"], grade=True, image=IMAGE, codex_auth_dir=CODEX_AUTH_DIR,
        timeout_seconds=1800, model_override=config["model"],
        codex_reasoning_effort=config.get("reasoning"), opencode_variant=config.get("variant"),
    )
    try:
        if code != 0:
            raise RuntimeError(f"judge_exit:{code}:{stderr[-1000:]}")
        if config["stack"] == CHATGPT_CODEX_STACK and not _codex_turn_completed(workspace / "agent.jsonl"):
            raise RuntimeError("judge_codex_turn_not_completed")
        review = _parse_review(workspace, stdout=stdout, judge_id=judge_id)
        if review.task_id != task_id or review.judge_id != judge_id or review.order_id != order:
            raise ValueError("r10_10_judge_identity_mismatch")
        _write(assignment_root / "review.json", review.model_dump(mode="json"))
        _write(state, {
            "status": "completed", "started_at": json.loads(state.read_text(encoding="utf-8"))["started_at"],
            "completed_at": _now(), "duration_seconds": round(time.monotonic() - started, 3),
            "review_sha256": review.canonical_sha256(),
        })
        return review
    except Exception as exc:
        _write(state, {
            "status": "incomplete", "completed_at": _now(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "first_failure": f"{type(exc).__name__}:{exc}",
        })
        raise


def _aggregate_task(profile: EvaluatorProfileV2, reviews: list[CounterbalancedPairReviewV2]) -> dict[str, Any]:
    stability = assess_counterbalance_stability(reviews)
    scores: dict[str, list[float]] = {"candidate_a": [], "candidate_b": []}
    for review in reviews:
        normalized = normalize_pair_review(review)
        for candidate in scores:
            scores[candidate].append(score_bundle(profile=profile, bundle=normalized[candidate]))
    majors = confirm_major_errors(
        profile=profile, reviews=reviews,
        deterministic_results_by_candidate={"candidate_a": [], "candidate_b": []},
    )
    means = {candidate: round(sum(values) / len(values), 6) for candidate, values in scores.items()}
    return {
        "task_id": profile.task_id, "counterbalance": stability,
        "scores": scores, "mean_scores": means, "confirmed_major_errors": majors,
        "stable_preference": stability["stable"],
    }


def run_split(run_root: Path, run_id: str, split: str, *, include_luna: bool = False) -> dict[str, Any]:
    if split == "holdout" and (run_root / "holdout_opened.json").exists():
        raise RuntimeError("r10_10_holdout_may_only_be_opened_once")
    profiles = build_profiles(run_root, "v2.0")
    scope_path = run_root / "scope.json"
    if not scope_path.exists():
        scope = _scope(run_id, profiles)
        _write(scope_path, scope)
        _write(run_root / "receipt.json", {"scope_sha256": canonical_sha256(scope), "consumed_at": _now()})
    if split == "holdout":
        _write(run_root / "holdout_opened.json", {"opened_at": _now(), "task_ids": list(R10_SPLITS[split])})
    judges = {**JUDGES, **(LUNA_JUDGE if include_luna else {})}
    task_results: dict[str, Any] = {}
    for task_id in R10_SPLITS[split]:
        reviews = [
            _run_assignment(
                run_root=run_root, run_id=run_id, task_id=task_id, profile=profiles[task_id],
                judge_id=judge_id, config=config, order=order,
            )
            for judge_id, config in judges.items() for order in ("a_b", "b_a")
        ]
        task_results[task_id] = _aggregate_task(profiles[task_id], reviews)
    result = {
        "result_version": "r10.evaluator_v2_split_result.1", "split": split,
        "profile_iteration": "v2.0", "judges": list(judges),
        "task_results": task_results,
        "stable": all(item["stable_preference"] for item in task_results.values()),
        "completed_at": _now(),
    }
    _write(run_root / f"{split}_result.json", result)
    return result


def status(run_root: Path) -> dict[str, Any]:
    return {
        "run_root": str(run_root),
        "development": json.loads((run_root / "development_result.json").read_text(encoding="utf-8")) if (run_root / "development_result.json").is_file() else None,
        "holdout": json.loads((run_root / "holdout_result.json").read_text(encoding="utf-8")) if (run_root / "holdout_result.json").is_file() else None,
        "sessions": {
            path.parent.name: json.loads(path.read_text(encoding="utf-8")).get("status")
            for path in sorted((run_root / "sessions").glob("*/state.json"))
        } if (run_root / "sessions").is_dir() else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["scope", "development", "holdout", "status"])
    parser.add_argument("--run-id", default="r10_10_evaluator_v2_20260903")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--include-luna", action="store_true")
    args = parser.parse_args()
    if args.action == "status":
        print(json.dumps(status(args.output_root), ensure_ascii=False, indent=2))
        return
    profiles = build_profiles(args.output_root, "v2.0")
    if args.action == "scope":
        scope = _scope(args.run_id, profiles)
        print(json.dumps({"scope_sha256": canonical_sha256(scope), "scope": scope}, ensure_ascii=False, indent=2))
        return
    result = run_split(args.output_root, args.run_id, args.action, include_luna=args.include_luna)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
