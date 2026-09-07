"""R10.12-G2 Agent-native item grading of three frozen audit deliveries."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

import run_r10_12_stirrup_calibration as base
from run_r10_behavioral_pilot import (
    CHATGPT_CODEX_STACK,
    DEEPSEEK_OPENCODE_STACK,
    _extract_opencode_json,
    _run_remote,
    _scp,
    _ssh,
)
from task_generator.evaluation.agent_rubric_grader import (
    AgentRubricGradeDraftV2,
    finalize_agent_rubric_grade_v2,
)
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.independent_rubric_grader import (
    IndependentRubricGradeV1,
    adapt_gdpval_rubric,
    canonical_json_sha256,
    tree_sha256,
)
from task_generator.evaluation.spreadsheet_evidence import SpreadsheetEvidenceV1


RUN_ID = "r10_12_agent_grader_repair_b_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
SOURCE = ROOT / "artifacts/r10/r10_12_model_supplement_b_20260904"
TASK_ID = "7d7fc9a7-21a7-4b83-906f-416dea5ad04f"
DELIVERIES = {
    "gpt-5.5": "cc67fc13bdde4f2092dc2ba3",
    "gpt-5.6-sol": "7a6d78664dbc74672449ee10",
    "gpt-5.4-mini": "75199adcc3ca0cf26671ef18",
}
JUDGES = {
    "primary": {"judge_id": "gpt-5.6-terra@chatgpt_codex", "stack": CHATGPT_CODEX_STACK, "model": "gpt-5.6-terra"},
    "check": {"judge_id": "deepseek-v4-pro@official_opencode", "stack": DEEPSEEK_OPENCODE_STACK, "model": "deepseek-v4-pro"},
}
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
REMOTE_ROOT = f"{base.REMOTE_ROOT}/{RUN_ID}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return base._file_sha256(path)


def _source_delivery(model: str) -> Path:
    return SOURCE / "solver_sessions" / DELIVERIES[model] / "attempts/attempt_1/output/deliverable_files"


def prepare(run_root: Path) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError("r10_12_g2_run_root_exists")
    hashes = base._task_hashes(TASK_ID)
    source_scope = json.loads((SOURCE / "scope.json").read_text(encoding="utf-8"))
    if source_scope["task_hashes"][TASK_ID] != hashes:
        raise ValueError("r10_12_g2_source_task_hash_drift")
    receipts = {
        row["solver_id"]: row
        for row in json.loads((SOURCE / "solver_receipts.json").read_text(encoding="utf-8"))
        if row["task_id"] == TASK_ID
    }
    delivery_hashes = {}
    for model in DELIVERIES:
        delivery_hashes[model] = tree_sha256(_source_delivery(model))
        if receipts[model]["delivery_status"] != "complete" or receipts[model]["delivery_sha256"] != delivery_hashes[model]:
            raise ValueError("r10_12_g2_frozen_delivery_hash_drift")
    scope = {
        "scope_version": "r10.agent_grader_repair_scope.2",
        "campaign_id": run_root.name,
        "created_at": _now(),
        "source_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip(),
        "source_campaign": SOURCE.name,
        "task_id": TASK_ID,
        "task_hashes": hashes,
        "deliveries": DELIVERIES,
        "delivery_hashes": delivery_hashes,
        "image": base.IMAGE,
        "image_sha256": base.IMAGE_SHA256,
        "judges": JUDGES,
        "normal_agent_sessions": 6,
        "format_recoveries": {"primary": 1, "check": 1},
        "solver_calls": 0,
        "excluded": ["semantic_redraw", "pairwise", "holistic", "downward_audit", "training", "generation"],
    }
    _write(run_root / "scope.json", scope)
    _write(run_root / "dry_run.json", {
        "dry_run_version": "r10.agent_grader_repair_dry_run.2",
        "provider_calls": 0,
        "normal_agent_sessions": 6,
        "format_recovery_limits": {"primary": 1, "check": 1},
        "assignments": [{"submission_id": model, "judge": JUDGES[role]["judge_id"]} for role in JUDGES for model in DELIVERIES],
        "solver_calls": 0,
        "task_hashes": hashes,
        "delivery_hashes": delivery_hashes,
        "image": base.IMAGE,
        "output_directory": run_root.as_posix(),
    })
    return scope


def _stage_evidence(run_root: Path, model: str) -> Path:
    target = run_root / "evidence" / model / "workspace"
    target.mkdir(parents=True)
    task = json.loads((SOURCE / "cases" / TASK_ID / "dataset_row.json").read_text(encoding="utf-8"))
    (target / "candidate_task.md").write_text(task["prompt"], encoding="utf-8")
    shutil.copytree(SOURCE / "cases" / TASK_ID / "reference_files", target / "reference_files")
    shutil.copytree(_source_delivery(model), target / "anonymous_submission")
    shutil.copy2(ROOT / "Test/r10_12_xlsx_evidence_tool.py", target / "xlsx_evidence_tool.py")
    shutil.copy2(ROOT / "Test/r10_12_remote_packet_grader_v2.py", target / "r10_12_remote_packet_grader_v2.py")
    return target


def _build_evidence(run_root: Path, model: str) -> Path:
    workspace = _stage_evidence(run_root, model)
    remote = f"{REMOTE_ROOT}/evidence_{model}"
    prepared = _ssh(base.HOST, f"mkdir -p '{REMOTE_ROOT}' && rm -rf '{remote}'", timeout=120, check=False)
    if prepared.returncode:
        raise ConnectionError("r10_12_g2_evidence_remote_prepare_failed")
    uploaded = _scp(str(workspace), f"{base.HOST}:{remote}")
    if uploaded.returncode:
        raise ConnectionError("r10_12_g2_evidence_upload_failed")
    command = (
        f"workspace='{remote}'; timeout --preserve-status 300 docker run --rm --init --read-only --cap-drop ALL "
        "--security-opt no-new-privileges:true --user 1000:1000 --memory 3g --cpus 2 --pids-limit 256 "
        "--tmpfs /tmp:rw,nosuid,nodev,size=512m -v \"$workspace:/workspace:rw\" -w /workspace "
        f"--entrypoint python3 {base.IMAGE} /workspace/xlsx_evidence_tool.py build"
    )
    executed = _ssh(base.HOST, command, timeout=420, check=False)
    if executed.returncode:
        raise RuntimeError("r10_12_g2_evidence_build_failed")
    downloaded = _scp(f"{base.HOST}:{remote}/spreadsheet_evidence.json", str(workspace / "spreadsheet_evidence.json"))
    if downloaded.returncode:
        raise ConnectionError("r10_12_g2_evidence_download_failed")
    payload = json.loads((workspace / "spreadsheet_evidence.json").read_text(encoding="utf-8"))
    evidence = {key: SpreadsheetEvidenceV1.model_validate(value) for key, value in payload["workbooks"].items()}
    if any(value.recalculation_status != "recalculated" for value in evidence.values()):
        raise RuntimeError("r10_12_g2_evidence_recalculation_incomplete")
    for relative, value in evidence.items():
        if _sha(workspace / Path(*Path(relative).parts)) != value.original_sha256:
            raise ValueError("r10_12_g2_evidence_original_hash_mismatch")
    _write(workspace.parent / "evidence_receipt.json", {
        "spreadsheet_evidence_sha256": _sha(workspace / "spreadsheet_evidence.json"),
        "workbook_count": len(evidence),
        "all_recalculated": True,
    })
    return workspace


def _prompt() -> str:
    return """You independently grade one anonymous XLSX work product item by item. Read candidate_task.md,
rubric_items.json, reference_files/, anonymous_submission/, and spreadsheet_evidence.json. Use local read-only tools
to inspect actual files as needed. Spreadsheet evidence contains original formulas, recalculated values and binding
formula diagnostics. The task prompt's target amounts are not evidence that the submitted formulas are correct.

Return exactly one assessment for every rubric item. Full credit requires direct evidence and no defects. Partial or
ambiguous evidence cannot receive full credit. Record coverage separately from verification_methods: coverage says
how much was checked (presence, sample, all_rows), while verification_methods says how it was checked (for example
formula and recalculated_value). Formula is never a substitute for coverage. For all/every/each requirements, full
credit requires coverage=all_rows and both candidate and reference range citations; it may simultaneously use
verification_methods=[formula, recalculated_value]. Formula cycles, formula errors, missing fields and period conflicts are
binding negative evidence. Use structured evidence_refs; never construct #sheet locators yourself. An XLSX content
citation must include exact relative_path, sheet_name and one continuous A1 cell_range. Only a pure presence check may
cite an XLSX without sheet/range. Do not infer the Solver, add rubric obligations, use holistic preference, pairwise
comparison or downward audit. Write only JSON matching grade_schema.json to grade.raw.json."""


def _stage_judge(evidence_workspace: Path, target: Path) -> None:
    shutil.copytree(evidence_workspace, target)
    rubric = adapt_gdpval_rubric(base._binding(TASK_ID))
    _write(target / "rubric_items.json", [row.model_dump(mode="json") for row in rubric])
    _write(target / "grade_schema.json", _strict_output_schema(AgentRubricGradeDraftV2.model_json_schema()))
    (target / "TASK.md").write_text(_prompt(), encoding="utf-8")


def _load_draft(workspace: Path, role: str) -> AgentRubricGradeDraftV2:
    raw = workspace / "grade.raw.json"
    if not raw.is_file() and role == "check":
        text = (workspace / "agent.jsonl").read_text(encoding="utf-8", errors="replace") if (workspace / "agent.jsonl").is_file() else ""
        candidate = _extract_opencode_json(text)
        if candidate:
            raw.write_text(candidate, encoding="utf-8")
    return AgentRubricGradeDraftV2.model_validate_json(raw.read_text(encoding="utf-8"))


def _finalize(workspace: Path, model: str, role: str, draft: AgentRubricGradeDraftV2 | None = None) -> tuple[IndependentRubricGradeV1, list[Any]]:
    payload = json.loads((workspace / "spreadsheet_evidence.json").read_text(encoding="utf-8"))
    evidence = {key: SpreadsheetEvidenceV1.model_validate(value) for key, value in payload["workbooks"].items()}
    draft = draft or _load_draft(workspace, role)
    return finalize_agent_rubric_grade_v2(
        task_id=TASK_ID,
        submission_id=model,
        judge_id=JUDGES[role]["judge_id"],
        rubric_items=adapt_gdpval_rubric(base._binding(TASK_ID)),
        draft=draft,
        staging_root=workspace,
        spreadsheet_evidence=evidence,
        input_sha256=base._task_hashes(TASK_ID)["input_sha256"],
        delivery_sha256=tree_sha256(workspace / "anonymous_submission"),
    )


def _raw_semantic_output(workspace: Path) -> str:
    raw = workspace / "grade.raw.json"
    if raw.is_file():
        return raw.read_text(encoding="utf-8", errors="replace")
    stream = workspace / "agent.jsonl"
    return stream.read_text(encoding="utf-8", errors="replace") if stream.is_file() else ""


def _complete_item_mentions(text: str) -> bool:
    identifiers = [row.rubric_item_id for row in adapt_gdpval_rubric(base._binding(TASK_ID))]
    return bool(text.strip()) and all(text.count(identifier) >= 1 for identifier in identifiers)


def _semantic_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_status": value.get("material_status"),
        "material_notes": value.get("material_notes"),
        "assessments": value.get("assessments"),
    }


def _validate_recovery_preserves_semantics(raw_text: str, recovered: AgentRubricGradeDraftV2) -> None:
    try:
        original = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("r10_12_g2_format_recovery_raw_not_json") from exc
    if not isinstance(original, dict) or not isinstance(original.get("assessments"), list):
        raise ValueError("r10_12_g2_format_recovery_raw_structure_missing")
    if _semantic_projection(original) != _semantic_projection(recovered.model_dump(mode="json")):
        raise ValueError("r10_12_g2_format_recovery_changed_semantics")


def _format_recovery(run_root: Path, original: Path, model: str, role: str, budget: dict[str, int]) -> AgentRubricGradeDraftV2:
    raw_text = _raw_semantic_output(original)
    if budget[role] <= 0 or not _complete_item_mentions(raw_text):
        raise ValueError("r10_12_g2_format_recovery_not_eligible")
    try:
        json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("r10_12_g2_format_recovery_not_parseable") from exc
    budget[role] -= 1
    recovery = run_root / "grading" / role / model / "format_recovery" / "workspace"
    recovery.mkdir(parents=True)
    (recovery / "raw_attempt.txt").write_text(raw_text, encoding="utf-8")
    shutil.copy2(original / "grade_schema.json", recovery / "grade_schema.json")
    (recovery / "TASK.md").write_text(
        "This is format-only recovery. Read raw_attempt.txt and grade_schema.json. Preserve every rubric item, "
        "score, satisfaction, verification scope, evidence reference, support, defect and rationale exactly. "
        "Do not inspect task files, add findings, remove findings or reassess anything. Write only corrected JSON "
        "to grade.raw.json. If the raw attempt lacks a required semantic value, stop without inventing it.\n",
        encoding="utf-8",
    )
    config = JUDGES[role]
    code, _, error = _run_remote(
        host=base.HOST,
        remote=f"{REMOTE_ROOT}/{role}_{model}_format_recovery",
        local=recovery,
        stack=config["stack"],
        grade=True,
        image=base.IMAGE,
        codex_auth_dir=CODEX_AUTH_DIR,
        timeout_seconds=900,
        codex_reasoning_effort="medium" if role == "primary" else None,
        model_override=config["model"],
        opencode_variant="max" if role == "check" else None,
    )
    if code:
        raise ConnectionError(error[:300])
    recovered = _load_draft(recovery, role)
    _validate_recovery_preserves_semantics(raw_text, recovered)
    return recovered


def _run_judge(
    run_root: Path,
    evidence_workspace: Path,
    model: str,
    role: str,
    recovery_budget: dict[str, int],
) -> tuple[IndependentRubricGradeV1, list[Any]]:
    workspace = run_root / "grading" / role / model / "attempt_1" / "workspace"
    _stage_judge(evidence_workspace, workspace)
    config = JUDGES[role]
    code, _, error = _run_remote(
        host=base.HOST,
        remote=f"{REMOTE_ROOT}/{role}_{model}_attempt_1",
        local=workspace,
        stack=config["stack"],
        grade=True,
        image=base.IMAGE,
        codex_auth_dir=CODEX_AUTH_DIR,
        timeout_seconds=1800,
        codex_reasoning_effort="medium" if role == "primary" else None,
        model_override=config["model"],
        opencode_variant="max" if role == "check" else None,
    )
    if code:
        raise ConnectionError(error[:300])
    try:
        draft = _load_draft(workspace, role)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError):
        recovered = _format_recovery(run_root, workspace, model, role, recovery_budget)
        draft = recovered
    # Controller/evidence/score failures are semantic and are never recovered.
    grade, citations = _finalize(workspace, model, role, draft)
    _write(workspace.parent / "review.json", grade)
    _write(workspace.parent / "citations.json", citations)
    return grade, citations


def _challenge_assertions(run_root: Path, grades: dict[str, dict[str, IndependentRubricGradeV1]]) -> tuple[bool, bool]:
    payload = json.loads((run_root / "evidence/gpt-5.4-mini/workspace/spreadsheet_evidence.json").read_text(encoding="utf-8"))
    candidate = next(value for key, value in payload["workbooks"].items() if key.startswith("anonymous_submission/"))
    cycles = any(row["kind"] == "formula_cycle" and any("Prepaid Summary!B9" in item for item in row["locations"]) for row in candidate["diagnostics"])
    defect_ids = {
        "c32bebfb-d7c6-4984-a831-8882b4533e39": 2,
        "15e57159-42d2-4578-9a62-4d40df436d8d": 1,
        "0746a460-bd9f-44ae-aedc-872551d608be": 1,
        "266d8ae4-86d7-4aef-9439-8e751e7e7cdf": 1,
    }
    not_full = True
    for role in JUDGES:
        scores = {row.rubric_item_id: row.awarded for row in grades[role]["gpt-5.4-mini"].items}
        not_full = not_full and all(scores[item] < maximum for item, maximum in defect_ids.items())
    return cycles, not_full


def execute(run_root: Path) -> dict[str, Any]:
    # Keep the historical body for inspection; no execution bypass is exposed.
    raise RuntimeError("评分校准已暂停，需要新的明确执行范围")
    evidence_workspaces: dict[str, Path] = {}
    grades: dict[str, dict[str, IndependentRubricGradeV1]] = {role: {} for role in JUDGES}
    recovery_budget = {"primary": 1, "check": 1}
    try:
        for model in DELIVERIES:
            evidence_workspaces[model] = _build_evidence(run_root, model)
        for role in JUDGES:
            for model in DELIVERIES:
                grades[role][model], _ = _run_judge(run_root, evidence_workspaces[model], model, role, recovery_budget)
    except Exception as exc:
        summary = {
            "summary_version": "r10.agent_grader_repair_summary.2",
            "status": "incomplete",
            "stop_reason": f"{type(exc).__name__}:{str(exc)[:240]}",
            "completed_grades": sum(len(value) for value in grades.values()),
        }
        _write(run_root / "summary.json", summary)
        return summary
    deltas, conflicts = {}, []
    for model in DELIVERIES:
        deltas[model] = round(abs(grades["primary"][model].normalized_score - grades["check"][model].normalized_score), 6)
        left = {row.rubric_item_id: row for row in grades["primary"][model].items}
        for right in grades["check"][model].items:
            if right.max_score >= 2 and {left[right.rubric_item_id].awarded, right.awarded} == {0, right.max_score}:
                conflicts.append({"submission_id": model, "rubric_item_id": right.rubric_item_id})
    cycles, defects_not_full = _challenge_assertions(run_root, grades)
    supported = cycles and defects_not_full and all(value <= 0.10 for value in deltas.values()) and not conflicts
    status = "agent_grader_supported" if supported else "agent_grader_inconclusive"
    summary = {
        "summary_version": "r10.agent_grader_repair_summary.2",
        "status": status,
        "evidence_level": "provisional_llm_proxy",
        "primary_scores": {key: value.normalized_score for key, value in grades["primary"].items()},
        "check_scores": {key: value.normalized_score for key, value in grades["check"].items()},
        "cross_judge_deltas": deltas,
        "high_weight_extreme_conflicts": conflicts,
        "mini_b9_cycle_detected": cycles,
        "mini_known_defects_not_full": defects_not_full,
        "model_ranking_claim": False,
    }
    _write(run_root / "summary.json", summary)
    _write(run_root / "receipt.json", {
        "receipt_version": "r10.agent_grader_repair_receipt.1",
        "status": status,
        "scope_sha256": _sha(run_root / "scope.json"),
        "completed_grades": 6,
        "completed_at": _now(),
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        parser.error("评分校准已暂停，需要新的明确执行范围")
    if not (args.run_root / "scope.json").is_file() or not (args.run_root / "dry_run.json").is_file():
        raise RuntimeError("r10_12_g2_existing_run_root_not_prepared")
    value = execute(args.run_root) if args.execute else json.loads((args.run_root / "dry_run.json").read_text(encoding="utf-8"))
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    main()
