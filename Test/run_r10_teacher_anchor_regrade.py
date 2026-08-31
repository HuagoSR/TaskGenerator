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
    R10ModelTaskResultV1,
    TeacherAnchorCheckV1,
    aggregate_behavioral_result,
    audit_teacher_anchors,
    sha256_file,
    sha256_json,
)
from task_generator.planning.scenario_task_compiler import tree_sha256
from run_r10_behavioral_pilot import STACKS, _execute_judge, _safe_remote_root, _write


TASK_ID = "r10_procurement_delivery_acceptance"
TASK_ROOT = ROOT / "artifacts/r10/r10_7a_task_compilation_20260831/tasks" / TASK_ID
RECOVERY_ROOT = ROOT / "artifacts/r10/r10_7b_judge_recovery_20260831"
SOLVER_ROOT = ROOT / "artifacts/r10/r10_7b_behavioral_pilot_20260831_execute5/collected_solvers"


def _load_records(path: Path) -> list[R10ModelTaskResultV1]:
    return [R10ModelTaskResultV1.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _scope() -> dict[str, Any]:
    deliveries = {
        solver: SOLVER_ROOT / solver / TASK_ID / "deliverable_files" / "acceptance_disposition_followup.xlsx"
        for solver in STACKS
    }


def _stage_public_judge_probe(root: Path) -> tuple[Path, Path]:
    """Create a wholly public XLSX task that exercises the exact Judge path."""
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
    delivery = root / "public_delivery.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Review"
    sheet.append(["Source reviewed", "Calculation", "Follow-up"])
    sheet.append(["Yes", "3/40 = 7.5%", "Escalate for review"])
    book.save(delivery)
    return task, delivery
    return {
        "scope_version": "r10.teacher_anchor_regrade_scope.1",
        "campaign_id": "r10_8a_procurement_acceptance_anchor_regrade_20260831",
        "task_id": TASK_ID,
        "candidate_tree_sha256": tree_sha256(TASK_ROOT / "reference_files"),
        "teacher_tree_sha256": tree_sha256(TASK_ROOT / "teacher"),
        "solver_delivery_sha256": {solver: sha256_file(path) for solver, path in deliveries.items()},
        "judge_ids": list(STACKS),
        "judge_format_attempt_limit": 2,
        "excluded_actions": ["solver", "candidate_mutation", "task_generation", "release", "training", "promotion"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_8a_procurement_acceptance_anchor_regrade_20260831")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_8a_procurement_acceptance_anchor_regrade_20260831")
    parser.add_argument("--public-probe", action="store_true")
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("r10_teacher_anchor_regrade_output_already_exists")

    if args.public_probe:
        args.output_root.mkdir(parents=True)
        task, delivery = _stage_public_judge_probe(args.output_root)
        remote_root = _safe_remote_root(args.host, args.run_id)
        result = _execute_judge(host=args.host, remote_root=remote_root, output_root=args.output_root, task_root=task, task_id="public-probe", delivery=delivery, judge="gpt-5.6-sol@chatgpt_codex")
        _write(args.output_root / "result.json", {"decision": "pass" if result["status"] == "completed" else "incomplete", "judge_result": result})
        print(json.dumps({"decision": "pass" if result["status"] == "completed" else "incomplete", "output_root": str(args.output_root)}, ensure_ascii=False))
        return

    checks = [TeacherAnchorCheckV1.model_validate(item) for item in json.loads((TASK_ROOT / "teacher/teacher_anchor_checks.json").read_text(encoding="utf-8"))]
    audit = audit_teacher_anchors(checks)
    args.output_root.mkdir(parents=True)
    _write(args.output_root / "teacher_anchor_audit.json", audit)
    if audit.decision != "pass":
        _write(args.output_root / "result.json", {"decision": "teacher_anchor_conflict", "reason": "corrected_anchor_did_not_pass"})
        return

    scope = _scope()
    _write(args.output_root / "scope.json", scope)
    _write(args.output_root / "receipt.json", {"scope_sha256": sha256_json(scope), "consumed_at": datetime.now(UTC).isoformat()})
    remote_root = _safe_remote_root(args.host, args.run_id)
    replacement_reviews: dict[str, list[Any]] = {}
    for solver in STACKS:
        delivery = SOLVER_ROOT / solver / TASK_ID / "deliverable_files" / "acceptance_disposition_followup.xlsx"
        if not delivery.is_file():
            raise FileNotFoundError(f"r10_teacher_anchor_delivery_missing:{solver}")
        reviews = []
        for judge in STACKS:
            result = _execute_judge(
                host=args.host, remote_root=remote_root, output_root=args.output_root,
                task_root=TASK_ROOT, task_id=TASK_ID, delivery=delivery, judge=judge,
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
