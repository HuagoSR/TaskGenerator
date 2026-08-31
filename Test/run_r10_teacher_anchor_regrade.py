"""Regrade one frozen R10 delivery after a verified teacher-anchor correction.

This is intentionally judge-only: it reads immutable Solver deliveries and a
new teacher-side fingerprint, and never launches a Solver or edits candidate
material.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.evaluation.r10_behavioral import (
    R10JudgeDraftV1,
    R10ModelTaskResultV1,
    TeacherAnchorCheckV1,
    aggregate_behavioral_result,
    audit_teacher_anchors,
    finalize_judge_review,
    sha256_file,
    sha256_json,
)
from task_generator.planning.scenario_task_compiler import TaskSpecificRubricV1, tree_sha256
from r10_local_codex_judge import local_codex_version, run_local_codex_judge
from run_r10_behavioral_pilot import (
    IMAGE,
    IMAGE_SHA256,
    STACKS,
    _execute_judge,
    _safe_remote_root,
    _stage_grade,
    _write,
)


TASK_ID = "r10_procurement_delivery_acceptance"
TASK_ROOT = ROOT / "artifacts/r10/r10_7a_task_compilation_20260831/tasks" / TASK_ID
RECOVERY_ROOT = ROOT / "artifacts/r10/r10_7b_judge_recovery_20260831"
SOLVER_ROOT = ROOT / "artifacts/r10/r10_7b_behavioral_pilot_20260831_execute5/collected_solvers"


def _load_records(path: Path) -> list[R10ModelTaskResultV1]:
    return [R10ModelTaskResultV1.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _collect_review(*, output_root: Path, solver: str, judge: str):
    """Parse a downloaded remote response without submitting another request."""
    workspace = output_root / "judges" / judge / TASK_ID / "attempt_01" / "workspace"
    raw = workspace / "grade.raw.json"
    if not raw.is_file():
        raise FileNotFoundError("r10_teacher_anchor_collected_grade_missing")
    draft = R10JudgeDraftV1.model_validate_json(raw.read_text(encoding="utf-8"))
    rubric = TaskSpecificRubricV1.model_validate_json((TASK_ROOT / "teacher" / "task_specific_rubric.json").read_text(encoding="utf-8"))
    review = finalize_judge_review(judge_id=judge, draft=draft, rubric=rubric)
    _write(workspace.parent / "review.json", review)
    _write(output_root / "judge_runs" / solver / f"{judge}.json", {"status": "completed", "review": review})
    return review


def _aggregate(*, output_root: Path) -> dict[str, Any]:
    replacement = {
        solver: [_collect_review(output_root=output_root, solver=solver, judge=judge) for judge in STACKS]
        for solver in STACKS
    }
    records = _load_records(RECOVERY_ROOT / "records.json")
    corrected = [
        item.model_copy(update={"reviews": replacement[item.solver_id]})
        if item.task_id == TASK_ID else item
        for item in records
    ]
    _write(output_root / "corrected_records.json", corrected)
    aggregate = aggregate_behavioral_result(corrected)
    result = {"decision": aggregate.decision, "aggregate": aggregate}
    _write(output_root / "result.json", result)
    return result


def _scope(
    run_id: str,
    *,
    image: str = IMAGE,
    image_sha256: str = IMAGE_SHA256,
    local_codex_command: str = "codex",
) -> dict[str, Any]:
    deliveries = {
        solver: SOLVER_ROOT / solver / TASK_ID / "deliverable_files" / "acceptance_disposition_followup.xlsx"
        for solver in STACKS
    }
    return {
        "scope_version": "r10.teacher_anchor_regrade_scope.2",
        "campaign_id": run_id,
        "image": image,
        "image_sha256": image_sha256,
        "task_id": TASK_ID,
        "candidate_tree_sha256": tree_sha256(TASK_ROOT / "reference_files"),
        "teacher_tree_sha256": tree_sha256(TASK_ROOT / "teacher"),
        "solver_delivery_sha256": {solver: sha256_file(path) for solver, path in deliveries.items()},
        "judge_ids": list(STACKS),
        "gpt_judge_environment": {
            "transport": "local_codex",
            "command": local_codex_command,
            "version": local_codex_version(local_codex_command),
            "model": "gpt-5.6-sol",
            "sandbox": "workspace-write",
        },
        "deepseek_judge_environment": {
            "transport": "huago_opencode",
            "image": image,
            "image_sha256": image_sha256,
            "model": "deepseek-v4-pro",
        },
        "judge_format_attempt_limit": 2,
        "excluded_actions": ["solver", "candidate_mutation", "task_generation", "release", "training", "promotion"],
    }


def _execute_local_gpt_judge(
    *,
    output_root: Path,
    task_root: Path,
    task_id: str,
    delivery: Path,
    codex_command: str,
) -> dict[str, Any]:
    """Execute a local GPT judge; only format failures may receive one retry."""
    feedback: str | None = None
    raw_paths: list[str] = []
    first_failure: str | None = None
    for attempt in (1, 2):
        workspace = output_root / "judges" / "gpt-5.6-sol@chatgpt_codex" / task_id / f"attempt_{attempt:02d}" / "workspace"
        rubric = _stage_grade(task_root=task_root, delivery=delivery, target=workspace, task_id=task_id, feedback=feedback)
        result = run_local_codex_judge(
            workspace=workspace,
            prompt=(workspace / "TASK.md").read_text(encoding="utf-8"),
            command=codex_command,
        )
        raw = workspace / "grade.raw.json"
        raw_paths.append(str(raw))
        if result["returncode"] != 0:
            return {
                "status": "infrastructure_failed",
                "first_failure": "provider_or_local_runtime_failure",
                "raw_paths": raw_paths,
                "diagnostics": result,
            }
        try:
            draft = R10JudgeDraftV1.model_validate_json(raw.read_text(encoding="utf-8"))
            if draft.task_id != task_id:
                raise ValueError("judge_task_id_mismatch")
            review = finalize_judge_review(judge_id="gpt-5.6-sol@chatgpt_codex", draft=draft, rubric=rubric)
            _write(workspace.parent / "review.json", review)
            return {
                "status": "completed",
                "review": review,
                "review_path": str(workspace.parent / "review.json"),
                "raw_paths": raw_paths,
                "first_failure": first_failure,
                "diagnostics": result,
            }
        except Exception as exc:
            first_failure = first_failure or f"judge_json_or_schema_invalid:{type(exc).__name__}"
            feedback = first_failure
    return {"status": "format_failed", "first_failure": first_failure, "raw_paths": raw_paths}


def _stage_public_judge_probe(root: Path, *, complex_input: bool = False) -> tuple[Path, Path]:
    """Create a wholly public task that exercises the exact Judge path."""
    task = root / "public_task"
    teacher = task / "teacher"
    reference = task / "reference_files"
    teacher.mkdir(parents=True)
    reference.mkdir()
    (task / "TASK.md").write_text("Review the public sample workbook and prepare a concise reconciliation.", encoding="utf-8")
    (task / "deliverable_contract.json").write_text(json.dumps({"contract_version": "deliverable_contract.1", "case_id": "public-probe", "deliverables": [{"relative_path": "deliverable_files/review.xlsx", "file_name": "review.xlsx", "format": "xlsx", "creation_mode": "create"}]}), encoding="utf-8")
    (teacher / "decision_matrix.json").write_text(json.dumps({"contract_version": "r10.task_decision_matrix.1", "scenario_id": "public-probe", "decision_points": [
        {"decision_id": "d1", "question": "Was the source reviewed?", "evidence_refs": [{"artifact_id": "source.txt", "record_id": "whole_document", "field_names": ["content"]}], "rule_ids": ["rule"], "skill_ids": ["skill"], "acceptable_conclusions": ["Reviewed."], "major_errors": ["Ignored source."], "allowed_uncertainty_conclusions": [], "required_follow_up_actions": ["Document review."]},
        {"decision_id": "d2", "question": "Is the calculation documented?", "evidence_refs": [{"artifact_id": "source.txt", "record_id": "whole_document", "field_names": ["content"]}], "rule_ids": ["rule"], "skill_ids": ["skill"], "acceptable_conclusions": ["Calculation documented."], "major_errors": ["Invented calculation."], "allowed_uncertainty_conclusions": [], "required_follow_up_actions": ["Retain calculation."]},
        {"decision_id": "d3", "question": "Is a follow-up stated?", "evidence_refs": [{"artifact_id": "source.txt", "record_id": "whole_document", "field_names": ["content"]}], "rule_ids": ["rule"], "skill_ids": ["skill"], "acceptable_conclusions": ["Follow-up stated."], "major_errors": ["No follow-up."], "allowed_uncertainty_conclusions": [], "required_follow_up_actions": ["Escalate discrepancy."]},
    ]}), encoding="utf-8")
    (teacher / "teacher_truth.json").write_text(json.dumps({"truth": []}), encoding="utf-8")
    rubric = {"rubric_version": "r10.task_specific_rubric.1", "criteria": [
        {"criterion_id": "c1", "decision_id": "d1", "weight": 0.34, "description": "source", "major_error_blocks_credit": True},
        {"criterion_id": "c2", "decision_id": "d2", "weight": 0.33, "description": "calculation", "major_error_blocks_credit": True},
        {"criterion_id": "c3", "decision_id": "d3", "weight": 0.33, "description": "follow-up", "major_error_blocks_credit": True},
    ]}
    (teacher / "task_specific_rubric.json").write_text(json.dumps(rubric), encoding="utf-8")
    (reference / "source.txt").write_text("Public source: 40 units were received; three require review.", encoding="utf-8")
    if complex_input:
        (reference / "receipt_log.csv").write_text(
            "receipt_id,units,inspection_status\nR-001,40,limited exterior review\nR-002,0,not applicable\n",
            encoding="utf-8",
        )
        (reference / "quality_note.txt").write_text(
            "The public sample certificate supports a claimed standard but does not establish lot traceability or signer authority.",
            encoding="utf-8",
        )
        (reference / "authority_matrix.txt").write_text(
            "A receiving official records receipt facts. A contracting officer makes the final acceptance decision.",
            encoding="utf-8",
        )
        (reference / "follow_up_template.txt").write_text(
            "A complete follow-up records issue, owner, requested support, target date, and closure evidence.",
            encoding="utf-8",
        )
    delivery = root / "public_delivery.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Review"
    sheet.append(["Source reviewed", "Calculation", "Follow-up", "Authority"])
    sheet.append(["Yes", "3/40 = 7.5%", "Escalate for review with closure evidence", "Contracting Officer retains final acceptance"])
    if complex_input:
        detail = book.create_sheet("Evidence Review")
        detail.append(["Source", "Observation", "Conclusion", "Required follow-up"])
        detail.append(["receipt_log.csv", "40 units independently supported", "Receiving record differs from unsupported count", "Obtain controlled correction"])
        detail.append(["quality_note.txt", "No lot traceability", "Certificate is not conclusive", "Request issuer and lot support"])
        detail.append(["authority_matrix.txt", "Receiving official lacks final authority", "Do not record acceptance", "Route recommendation to Contracting Officer"])
    book.save(delivery)
    return task, delivery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_8a_procurement_acceptance_anchor_regrade_local_20260901")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_8a_procurement_acceptance_anchor_regrade_local_20260901")
    parser.add_argument("--local-codex-command", default="codex")
    parser.add_argument("--public-probe", action="store_true")
    parser.add_argument("--public-complex-probe", action="store_true")
    parser.add_argument("--single-solver", choices=STACKS)
    parser.add_argument("--single-judge", choices=STACKS)
    parser.add_argument("--collect", action="store_true", help="Parse one already-downloaded response; never calls a provider.")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate four collected reviews; never calls a provider.")
    parser.add_argument("--scope-only", action="store_true", help="Create the immutable receipt without calling a provider.")
    parser.add_argument("--mark-incomplete", action="store_true", help="Persist a verified infrastructure stop; never calls a provider.")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--image-sha256", default=IMAGE_SHA256)
    args = parser.parse_args()
    single = bool(args.single_solver or args.single_judge)
    if single != bool(args.single_solver and args.single_judge):
        parser.error("single_solver_and_single_judge_must_be_supplied_together")
    if sum(bool(value) for value in (args.public_probe, args.public_complex_probe, args.aggregate, args.scope_only, args.mark_incomplete, single and not args.collect, args.collect)) > 1:
        parser.error("probe_single_collect_and_aggregate_are_mutually_exclusive")
    if args.output_root.exists() and not (single or args.collect or args.aggregate or args.mark_incomplete):
        raise FileExistsError("r10_teacher_anchor_regrade_output_already_exists")

    if args.public_probe or args.public_complex_probe:
        args.output_root.mkdir(parents=True)
        task, delivery = _stage_public_judge_probe(args.output_root, complex_input=args.public_complex_probe)
        result = _execute_local_gpt_judge(
            output_root=args.output_root,
            task_root=task,
            task_id="public-probe",
            delivery=delivery,
            codex_command=args.local_codex_command,
        )
        _write(args.output_root / "result.json", {"decision": "pass" if result["status"] == "completed" else "incomplete", "judge_result": result})
        print(json.dumps({"decision": "pass" if result["status"] == "completed" else "incomplete", "output_root": str(args.output_root)}, ensure_ascii=False))
        return

    if args.mark_incomplete:
        scope_path = args.output_root / "scope.json"
        if not scope_path.is_file() or json.loads(scope_path.read_text(encoding="utf-8")) != _scope(args.run_id, image=args.image, image_sha256=args.image_sha256, local_codex_command=args.local_codex_command):
            raise RuntimeError("r10_teacher_anchor_regrade_scope_mismatch")
        _write(args.output_root / "result.json", {
            "decision": "evaluation_inconclusive",
            "first_failure": {
                "category": "provider_session_no_progress",
                "detail": "codex emitted thread.started and turn.started but no tool or completion event before the controlled stop.",
                "observed_at": datetime.now(UTC).isoformat(),
            },
        })
        print(json.dumps({"decision": "evaluation_inconclusive"}, ensure_ascii=False))
        return

    if args.collect:
        if not single:
            parser.error("collect_requires_single_solver_and_single_judge")
        review = _collect_review(output_root=args.output_root, solver=args.single_solver, judge=args.single_judge)
        print(json.dumps({"decision": "collected", "weighted_score": review.weighted_score}, ensure_ascii=False))
        return

    if args.aggregate:
        result = _aggregate(output_root=args.output_root)
        print(json.dumps({"decision": result["decision"]}, ensure_ascii=False))
        return

    checks = [TeacherAnchorCheckV1.model_validate(item) for item in json.loads((TASK_ROOT / "teacher/teacher_anchor_checks.json").read_text(encoding="utf-8"))]
    audit = audit_teacher_anchors(checks)
    args.output_root.mkdir(parents=True, exist_ok=single)
    _write(args.output_root / "teacher_anchor_audit.json", audit)
    if audit.decision != "pass":
        _write(args.output_root / "result.json", {"decision": "teacher_anchor_conflict", "reason": "corrected_anchor_did_not_pass"})
        return

    scope = _scope(args.run_id, image=args.image, image_sha256=args.image_sha256, local_codex_command=args.local_codex_command)
    scope_path = args.output_root / "scope.json"
    if single:
        if not scope_path.is_file() or json.loads(scope_path.read_text(encoding="utf-8")) != scope:
            raise RuntimeError("r10_teacher_anchor_regrade_scope_mismatch")
    else:
        _write(scope_path, scope)
        _write(args.output_root / "receipt.json", {"scope_sha256": sha256_json(scope), "consumed_at": datetime.now(UTC).isoformat()})
    if args.scope_only:
        print(json.dumps({"decision": "scope_created", "scope_sha256": sha256_json(scope)}, ensure_ascii=False))
        return
    remote_root: str | None = None
    if not single or args.single_judge == "deepseek-v4-pro@official_opencode":
        remote_root = _safe_remote_root(args.host, args.run_id)
    if single:
        delivery = SOLVER_ROOT / args.single_solver / TASK_ID / "deliverable_files" / "acceptance_disposition_followup.xlsx"
        result = (
            _execute_local_gpt_judge(
                output_root=args.output_root,
                task_root=TASK_ROOT,
                task_id=TASK_ID,
                delivery=delivery,
                codex_command=args.local_codex_command,
            )
            if args.single_judge.startswith("gpt")
            else _execute_judge(host=args.host, remote_root=remote_root or "", output_root=args.output_root, task_root=TASK_ROOT, task_id=TASK_ID, delivery=delivery, judge=args.single_judge, image=args.image)
        )
        _write(args.output_root / "judge_runs" / args.single_solver / f"{args.single_judge}.json", result)
        print(json.dumps({"decision": result["status"]}, ensure_ascii=False))
        return
    replacement_reviews: dict[str, list[Any]] = {}
    for solver in STACKS:
        delivery = SOLVER_ROOT / solver / TASK_ID / "deliverable_files" / "acceptance_disposition_followup.xlsx"
        if not delivery.is_file():
            raise FileNotFoundError(f"r10_teacher_anchor_delivery_missing:{solver}")
        reviews = []
        for judge in STACKS:
            result = (
                _execute_local_gpt_judge(
                    output_root=args.output_root,
                    task_root=TASK_ROOT,
                    task_id=TASK_ID,
                    delivery=delivery,
                    codex_command=args.local_codex_command,
                )
                if judge.startswith("gpt")
                else _execute_judge(
                    host=args.host, remote_root=remote_root or "", output_root=args.output_root,
                    task_root=TASK_ROOT, task_id=TASK_ID, delivery=delivery, judge=judge, image=args.image,
                )
            )
            _write(args.output_root / "judge_runs" / solver / f"{judge}.json", result)
            if result["status"] != "completed":
                _write(args.output_root / "result.json", {"decision": "evaluation_inconclusive", "reason": result["first_failure"]})
                return
            reviews.append(result["review"])
        replacement_reviews[solver] = reviews

    records = _load_records(RECOVERY_ROOT / "records.json")
    corrected = [
        item.model_copy(update={"reviews": replacement_reviews[item.solver_id]})
        if item.task_id == TASK_ID else item
        for item in records
    ]
    _write(args.output_root / "corrected_records.json", corrected)
    aggregate = aggregate_behavioral_result(corrected)
    _write(args.output_root / "result.json", {"decision": aggregate.decision, "aggregate": aggregate})
    print(json.dumps({"decision": aggregate.decision, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
