"""R10.12-G1 immutable XLSX evidence regrade of three frozen audit deliveries."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

import run_r10_12_stirrup_calibration as base
from r10_12_remote_strict_grader import _extract
from run_r10_behavioral_pilot import CHATGPT_CODEX_STACK, _run_remote
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.independent_rubric_grader import (
    IndependentRubricGradeDraftV2, IndependentRubricGradeV1, adapt_gdpval_rubric,
    canonical_json_sha256, finalize_independent_grade_v2, tree_sha256,
)
from task_generator.evaluation.spreadsheet_evidence import SpreadsheetEvidenceV1, validate_spreadsheet_locator

RUN_ID = "r10_12_audit_grader_repair_c_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
SOURCE = ROOT / "artifacts/r10/r10_12_model_supplement_b_20260904"
TASK_ID = "7d7fc9a7-21a7-4b83-906f-416dea5ad04f"
DELIVERIES = {
    "gpt-5.5": "cc67fc13bdde4f2092dc2ba3",
    "gpt-5.6-sol": "7a6d78664dbc74672449ee10",
    "gpt-5.4-mini": "75199adcc3ca0cf26671ef18",
}
PRIMARY_JUDGE = "deepseek-v4-pro@official_api"
CHECK_JUDGE = "gpt-5.6-terra@chatgpt_codex"
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"

STRICT_SYSTEM = """You independently grade one anonymous professional XLSX work product against a fixed rubric.
Use only the supplied packet. Workbook facts retain sheet/cell coordinates, original formulas, recalculated values,
and binding diagnostics. The task prompt's target amounts are not evidence that a candidate formula produces them.
In workbook_evidence each sheet's cells are columnar: cell_columns gives the field names for each cells row.
For every rubric item return exactly one assessment. Cite XLSX evidence as
anonymous_submission/<file>.xlsx#sheet=<exact sheet>&range=<A1 range>.
Full credit requires satisfaction='met', direct support, no defects, and the maximum score. For all/every/each
criteria, full credit requires verification_scope='all_rows' and candidate plus reference evidence. A formula cycle,
formula error, missing field, or stated-period conflict is binding negative evidence. Do not infer authorship, add
criteria, use holistic preference, or perform downward audit. Keep each support, defects, and rationale entry concise
(at most 16 words); return no prose outside the JSON matching the supplied schema."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return base._file_sha256(path)


def _task() -> dict[str, Any]:
    return json.loads((SOURCE / "cases" / TASK_ID / "dataset_row.json").read_text(encoding="utf-8"))


def _stage(workspace: Path, model: str) -> dict[str, str]:
    task = _task()
    workspace.mkdir(parents=True)
    (workspace / "candidate_task.md").write_text(task["prompt"], encoding="utf-8")
    shutil.copytree(SOURCE / "cases" / TASK_ID / "reference_files", workspace / "reference_files")
    delivery = SOURCE / "solver_sessions" / DELIVERIES[model] / "attempts/attempt_1/output/deliverable_files"
    shutil.copytree(delivery, workspace / "anonymous_submission")
    rubric = adapt_gdpval_rubric(base._binding(TASK_ID))
    _write(workspace / "task.json", {"task_id": TASK_ID})
    _write(workspace / "rubric_items.json", [row.model_dump(mode="json") for row in rubric])
    _write(workspace / "grade_schema.json", _strict_output_schema(IndependentRubricGradeDraftV2.model_json_schema()))
    (workspace / "strict_system.txt").write_text(STRICT_SYSTEM, encoding="utf-8")
    parts = []
    for path in [workspace / "candidate_task.md"] + sorted((workspace / "reference_files").glob("*.pdf")):
        parts.append(f"\n===== {path.relative_to(workspace).as_posix()} =====\n{_extract(path)}")
    (workspace / "materials_text.txt").write_text("".join(parts), encoding="utf-8")
    shutil.copy2(ROOT / "Test/r10_12_remote_packet_grader_v2.py", workspace / "r10_12_remote_strict_grader.py")
    return {
        "input_sha256": base._task_hashes(TASK_ID)["input_sha256"],
        "rubric_sha256": canonical_json_sha256(rubric),
        "delivery_sha256": tree_sha256(workspace / "anonymous_submission"),
    }


def prepare(run_root: Path) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError("r10_12_g1_run_root_exists")
    hashes = base._task_hashes(TASK_ID)
    source_scope = json.loads((SOURCE / "scope.json").read_text(encoding="utf-8"))
    if source_scope["task_hashes"][TASK_ID] != hashes:
        raise ValueError("r10_12_g1_source_task_hash_drift")
    receipts = {row["solver_id"]: row for row in json.loads((SOURCE / "solver_receipts.json").read_text(encoding="utf-8")) if row["task_id"] == TASK_ID}
    for model, assignment in DELIVERIES.items():
        receipt = receipts.get(model)
        delivery = SOURCE / "solver_sessions" / assignment / "attempts/attempt_1/output/deliverable_files"
        if not receipt or receipt.get("delivery_status") != "complete" or receipt.get("delivery_sha256") != tree_sha256(delivery):
            raise ValueError("r10_12_g1_frozen_delivery_hash_drift")
    scope = {
        "scope_version": "r10.audit_grader_repair.1", "campaign_id": run_root.name, "created_at": _now(),
        "source_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip(),
        "purpose": "xlsx_evidence_grader_repair", "source_campaign": SOURCE.name, "task_id": TASK_ID,
        "source_task_hashes": hashes, "deliveries": DELIVERIES,
        "grading": {"primary": {"judge_id": PRIMARY_JUDGE, "normal": 3, "format_recoveries": 1},
                    "checks": {"judge_id": CHECK_JUDGE, "normal": 3, "format_recoveries": 1},
                    "pairwise": False, "holistic": False, "downward_audit": False},
        "solver_calls": 0, "semantic_redraw": False, "automatic_generator_feedback": False,
        "model_identity_claim": False, "model_ranking_claim": False,
    }
    _write(run_root / "scope.json", scope)
    _write(run_root / "dry_run.json", {
        "dry_run_version": "r10.audit_grader_repair.1", "provider_calls": 0, "solver_calls": 0,
        "primary_normal": 3, "primary_format_recoveries": 1, "check_normal": 3, "check_format_recoveries": 1,
        "task_id": TASK_ID, "deliveries": DELIVERIES, "image": base.IMAGE, "output_directory": run_root.as_posix(),
    })
    return scope


def _expand_workbook_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Expand the lossless columnar cell rows used in StrictGradePacketV2."""
    result: dict[str, Any] = {}
    for relative, workbook in value.items():
        decoded = dict(workbook)
        sheets = []
        for sheet in workbook["sheets"]:
            decoded_sheet = dict(sheet)
            columns = decoded_sheet.pop("cell_columns", None)
            if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
                raise ValueError("r10_12_g1_compact_evidence_columns_invalid")
            rows = decoded_sheet["cells"]
            if not all(isinstance(row, list) and len(row) == len(columns) for row in rows):
                raise ValueError("r10_12_g1_compact_evidence_rows_invalid")
            decoded_sheet["cells"] = [dict(zip(columns, row, strict=True)) for row in rows]
            sheets.append(decoded_sheet)
        decoded["sheets"] = sheets
        result[relative] = decoded
    return result


def _finalize(workspace: Path, model: str, hashes: dict[str, str], judge: str) -> IndependentRubricGradeV1:
    draft = IndependentRubricGradeDraftV2.model_validate_json((workspace / "grade.raw.json").read_text(encoding="utf-8"))
    packet = json.loads((workspace / "strict_grade_packet_v2.json").read_text(encoding="utf-8"))
    evidence = {key: SpreadsheetEvidenceV1.model_validate(value) for key, value in _expand_workbook_evidence(packet["workbook_evidence"]).items()}
    if any(value.recalculation_status != "recalculated" for value in evidence.values()):
        raise RuntimeError("r10_12_g1_recalculation_incomplete")
    return finalize_independent_grade_v2(
        task_id=TASK_ID, submission_id=model, judge_id=judge, rubric_items=adapt_gdpval_rubric(base._binding(TASK_ID)),
        draft=draft, staging_root=workspace, input_sha256=hashes["input_sha256"], delivery_sha256=hashes["delivery_sha256"],
        validate_locator=lambda value: validate_spreadsheet_locator(value, evidence),
    )


def _primary(run_root: Path, model: str, budget: dict[str, int]) -> tuple[IndependentRubricGradeV1, str]:
    session = run_root / "grading/primary" / model
    session.mkdir(parents=True)
    for attempt in (1, 2):
        workspace = session / "attempts" / f"attempt_{attempt}"
        hashes = _stage(workspace, model)
        code, error = base._remote_grade_call(
            workspace, f"{base.REMOTE_ROOT}/{run_root.name}/primary_{model}/attempt_{attempt}", "deepseek_official"
        )
        try:
            if code:
                raise ConnectionError(error)
            grade = _finalize(workspace, model, hashes, PRIMARY_JUDGE)
            packet_sha = _sha(workspace / "strict_grade_packet_v2.json")
            _write(session / "review.json", grade)
            _write(session / "packet_receipt.json", {"strict_grade_packet_sha256": packet_sha})
            return grade, packet_sha
        except (ConnectionError, FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError, RuntimeError) as exc:
            _write(workspace / "failure.json", {"type": type(exc).__name__, "detail": str(exc)[:300]})
            if attempt == 2 or budget["remaining"] <= 0:
                raise
            budget["remaining"] -= 1
    raise AssertionError("unreachable")


def _check(run_root: Path, model: str, packet_sha: str, budget: dict[str, int]) -> IndependentRubricGradeV1:
    session = run_root / "grading/checks" / model
    session.mkdir(parents=True)
    primary_workspace = run_root / "grading/primary" / model / "attempts/attempt_1"
    for attempt in (1, 2):
        workspace = session / "attempts" / f"attempt_{attempt}"
        shutil.copytree(primary_workspace, workspace)
        (workspace / "TASK.md").write_text(
            "Read only strict_grade_packet_v2.json. Apply its strict system to its evidence. "
            "Return exactly one JSON object matching grade_schema.json in grade.raw.json. Do not inspect other files.\n",
            encoding="utf-8",
        )
        code, _, error = _run_remote(
            host=base.HOST, remote=f"{base.REMOTE_ROOT}/{run_root.name}/check_{model}/attempt_{attempt}",
            local=workspace, stack=CHATGPT_CODEX_STACK, grade=True, image=base.IMAGE, codex_auth_dir=CODEX_AUTH_DIR,
            timeout_seconds=1800, codex_reasoning_effort="medium", model_override="gpt-5.6-terra",
        )
        try:
            if code:
                raise ConnectionError(error)
            hashes = {"input_sha256": base._task_hashes(TASK_ID)["input_sha256"],
                      "delivery_sha256": tree_sha256(workspace / "anonymous_submission")}
            grade = _finalize(workspace, model, hashes, CHECK_JUDGE)
            if _sha(workspace / "strict_grade_packet_v2.json") != packet_sha:
                raise ValueError("r10_12_g1_cross_judge_packet_drift")
            _write(session / "review.json", grade)
            _write(session / "packet_receipt.json", {"strict_grade_packet_sha256": packet_sha})
            return grade
        except (ConnectionError, FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError, RuntimeError) as exc:
            _write(workspace / "failure.json", {"type": type(exc).__name__, "detail": str(exc)[:300]})
            if attempt == 2 or budget["remaining"] <= 0:
                raise
            budget["remaining"] -= 1
    raise AssertionError("unreachable")


def grade(run_root: Path) -> dict[str, Any]:
    primary, checks, packets = {}, {}, {}
    primary_budget, check_budget = {"remaining": 1}, {"remaining": 1}
    try:
        for model in DELIVERIES:
            primary[model], packets[model] = _primary(run_root, model, primary_budget)
        for model in DELIVERIES:
            checks[model] = _check(run_root, model, packets[model], check_budget)
    except Exception as exc:
        summary = {"summary_version": "r10.audit_grader_repair.1", "status": "incomplete", "evidence_level": "grading",
                   "stop_reason": f"{type(exc).__name__}:{str(exc)[:160]}", "primary_grades": len(primary), "check_grades": len(checks)}
        _write(run_root / "summary.json", summary)
        return summary
    deltas, conflicts = {}, []
    for model in DELIVERIES:
        deltas[model] = round(abs(primary[model].normalized_score - checks[model].normalized_score), 6)
        left = {row.rubric_item_id: row for row in primary[model].items}
        for right in checks[model].items:
            if right.max_score >= 2 and {right.awarded, left[right.rubric_item_id].awarded} == {0, right.max_score}:
                conflicts.append({"model": model, "rubric_item_id": right.rubric_item_id})
    mini = {judge: {row.rubric_item_id: row.awarded for row in result.items} for judge, result in
            (("primary", primary["gpt-5.4-mini"]), ("check", checks["gpt-5.4-mini"]))}
    defect_ids = {"c32bebfb-d7c6-4984-a831-8882b4533e39": 2, "15e57159-42d2-4578-9a62-4d40df436d8d": 1,
                  "0746a460-bd9f-44ae-aedc-872551d608be": 1, "266d8ae4-86d7-4aef-9439-8e751e7e7cdf": 1}
    defects_not_full = all(mini[judge][item] < maximum for judge in mini for item, maximum in defect_ids.items())
    packet = json.loads((run_root / "grading/primary/gpt-5.4-mini/attempts/attempt_1/strict_grade_packet_v2.json").read_text(encoding="utf-8"))
    mini_path = next(key for key in packet["workbook_evidence"] if key.startswith("anonymous_submission/"))
    cycles = any(row["kind"] == "formula_cycle" for row in packet["workbook_evidence"][mini_path]["diagnostics"])
    supported = all(row.material_status == "complete" for row in list(primary.values()) + list(checks.values()))
    supported = supported and cycles and defects_not_full and all(value <= .10 for value in deltas.values()) and not conflicts
    status = "grader_repair_supported" if supported else "grader_repair_inconclusive"
    summary = {
        "summary_version": "r10.audit_grader_repair.1", "status": status, "evidence_level": "provisional_llm_proxy",
        "primary_scores": {key: value.normalized_score for key, value in primary.items()},
        "check_scores": {key: value.normalized_score for key, value in checks.items()},
        "cross_judge_deltas": deltas, "high_weight_extreme_conflicts": conflicts,
        "mini_formula_cycle_detected": cycles, "mini_known_defects_not_full": defects_not_full,
        "model_ranking_claim": False, "automatic_generator_feedback": False,
    }
    _write(run_root / "summary.json", summary)
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.audit_grader_repair_receipt.1", "scope_sha256": _sha(run_root / "scope.json"),
        "status": status, "primary_grades": 3, "check_grades": 3, "completed_at": _now(),
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.run_root.exists():
        prepare(args.run_root)
    elif not (args.run_root / "scope.json").is_file() or not (args.run_root / "dry_run.json").is_file():
        raise RuntimeError("r10_12_g1_existing_run_root_not_prepared")
    print(json.dumps(grade(args.run_root) if args.execute else json.loads((args.run_root / "dry_run.json").read_text(encoding="utf-8")), ensure_ascii=False))


if __name__ == "__main__":
    main()
