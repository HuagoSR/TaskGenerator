from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_semantic_review_executor import (  # noqa: E402
    SemanticReviewExecutor,
    deepseek_semantic_config,
    gpt54_semantic_config,
)
from task_generator.v3_semantic_contract_v2 import (  # noqa: E402
    TaskSemanticContractV2,
    to_review_contract,
)
from task_generator.v3_semantic_validity import (  # noqa: E402
    CandidateBlindReview,
    SemanticContractDraftBuilder,
    SemanticReviewPackageBuilder,
    SemanticValidityGate,
    TaskSemanticContract,
    TeacherRubricReview,
    SemanticFinding,
    write_semantic_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optionally execute governed semantic validity reviews.")
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=["disabled", "prepare", "diagnostic", "blocking"], default="prepare")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-external-semantic-review", action="store_true")
    parser.add_argument("--deepseek-key-path")
    parser.add_argument("--tuzi-env-path")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--repair-iteration", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.execute and not args.allow_external_semantic_review:
        raise SystemExit("External semantic review requires --execute and --allow-external-semantic-review.")
    manifest_path = Path(args.manifest_path)
    manifest = _read_json(manifest_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, case in enumerate(manifest.get("cases") or []):
        if case.get("batch_status") != "completed":
            continue
        force_audit = index % 10 == 0
        records.append(_review_case(case, output_dir, args, force_audit))
    summary = {
        "report_version": "v3.semantic_validation_batch.1",
        "mode": args.mode,
        "case_count": len(records),
        "decision_counts": _counts(records, "decision"),
        "semantic_pass_count": sum(1 for item in records if item["semantic_gate_pass"]),
        "secondary_review_count": sum(1 for item in records if item["secondary_review_performed"]),
        "needs_human_review_count": sum(1 for item in records if item["needs_human_review"]),
        "records": records,
        "external_effects": {"deepseek_semantic_review": bool(args.execute), "claude_secondary_review": any(item["secondary_review_performed"] for item in records)},
    }
    augmented = _augmented_manifest(manifest, records, args.mode)
    augmented_path = output_dir / "semantic_augmented_production_manifest.json"
    _write_json(augmented_path, augmented)
    summary["augmented_production_manifest_path"] = str(augmented_path)
    _write_json(output_dir / "semantic_validation_batch_report.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


def _review_case(case: Dict[str, Any], output_root: Path, args: argparse.Namespace, force_audit: bool) -> Dict[str, Any]:
    task_id = str(case.get("case_id") or "unknown")
    case_dir = Path(str(case.get("case_dir") or ""))
    output_dir = output_root / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    blueprint_path = _first_existing(
        case_dir / "prototype" / "draft_task_blueprint.json",
        case_dir / "package" / "artifacts" / "draft_task_blueprint.json",
    )
    rubric_path = _first_existing(
        case_dir / "rubric" / "rubric.json",
        case_dir / "package" / "artifacts" / "rubric.json",
    )
    dataset_path = _find_dataset_row(case_dir, task_id)
    blueprint = _read_json(blueprint_path)
    rubric = _read_json(rubric_path) if rubric_path else {}
    dataset = _read_json(dataset_path)
    v2_contract_path = case_dir / "semantic_contract" / "task_semantic_contract.json"
    v2_consistency_path = case_dir / "semantic_contract" / "semantic_contract_consistency_report.json"
    if v2_contract_path.exists():
        v2_contract = TaskSemanticContractV2.model_validate(_read_json(v2_contract_path))
        contract = to_review_contract(v2_contract)
        teacher_contract_path = v2_contract_path
        deterministic_findings = _v2_consistency_findings(v2_consistency_path)
    else:
        v2_contract = None
        contract = SemanticContractDraftBuilder().build(task_id, blueprint, rubric)
        teacher_contract_path = output_dir / "task_semantic_contract.json"
        deterministic_findings = []
    contract_path = output_dir / "task_semantic_contract.json"
    write_semantic_artifact(contract_path, contract)

    references = [_resolve_reference(dataset_path.parent, value) for value in dataset.get("reference_files") or []]
    deliverables = {
        str(item.get("file_name") or ""): list(item.get("requirements") or [])
        for item in blueprint.get("deliverable_spec") or []
    }
    blind_package_path = output_dir / "candidate_blind_prompt_package.json"
    blind_package = SemanticReviewPackageBuilder().build_blind_package(
        task_id=task_id,
        prompt=str(dataset.get("prompt") or ""),
        deliverable_contract=deliverables,
        reference_files=references,
        output_path=blind_package_path,
        semantic_contract=contract,
    )

    blind_review = None
    teacher_review = None
    secondary_blind = None
    secondary_teacher = None
    if args.execute:
        primary = SemanticReviewExecutor(deepseek_semantic_config(args.deepseek_key_path, args.timeout_seconds))
        blind_review = _retry_once(lambda: primary.review_blind(blind_package), output_dir, "primary_blind")
        blind_review_path = output_dir / "candidate_blind_review.json"
        write_semantic_artifact(blind_review_path, blind_review)
        teacher_paths = _teacher_paths(case_dir, rubric_path)
        teacher_package_path = output_dir / "teacher_rubric_prompt_package.json"
        teacher_package = SemanticReviewPackageBuilder().build_teacher_package(
            task_id, blind_review_path, teacher_contract_path, teacher_paths, teacher_package_path
        )
        teacher_review = _retry_once(lambda: primary.review_teacher(teacher_package), output_dir, "primary_teacher")
        write_semantic_artifact(output_dir / "teacher_rubric_review.json", teacher_review)

        preliminary = SemanticValidityGate().build(
            contract,
            blind_review,
            teacher_review,
            args.mode,
            args.repair_iteration,
            force_secondary_audit=force_audit,
            deterministic_findings=deterministic_findings,
        )
        if preliminary.secondary_review_required:
            secondary = SemanticReviewExecutor(gpt54_semantic_config(args.tuzi_env_path, args.timeout_seconds))
            secondary_blind = _retry_once(lambda: secondary.review_blind(blind_package), output_dir, "secondary_blind")
            secondary_blind_path = output_dir / "secondary_candidate_blind_review.json"
            write_semantic_artifact(secondary_blind_path, secondary_blind)
            secondary_teacher_package_path = output_dir / "secondary_teacher_rubric_prompt_package.json"
            secondary_package = SemanticReviewPackageBuilder().build_teacher_package(
                task_id, secondary_blind_path, teacher_contract_path, teacher_paths, secondary_teacher_package_path
            )
            secondary_teacher = _retry_once(lambda: secondary.review_teacher(secondary_package), output_dir, "secondary_teacher")
            write_semantic_artifact(output_dir / "secondary_teacher_rubric_review.json", secondary_teacher)

    gate = SemanticValidityGate().build(
        contract,
        blind_review,
        teacher_review,
        args.mode,
        args.repair_iteration,
        force_secondary_audit=force_audit,
        secondary_blind_review=secondary_blind,
        secondary_teacher_review=secondary_teacher,
        deterministic_findings=deterministic_findings,
    )
    gate.artifact_sha256 = {
        "contract": _sha256(contract_path),
        "blind_package": _sha256(blind_package_path),
    }
    write_semantic_artifact(output_dir / "semantic_validity_gate_report.json", gate)
    return {
        "task_id": task_id,
        "decision": gate.decision,
        "semantic_gate_pass": gate.semantic_gate_pass,
        "reason_codes": gate.reason_codes,
        "secondary_review_performed": secondary_blind is not None,
        "needs_human_review": gate.needs_human_review,
        "gate_report_path": str(output_dir / "semantic_validity_gate_report.json"),
    }


def _v2_consistency_findings(path: Path) -> List[SemanticFinding]:
    if not path.exists():
        return [SemanticFinding(
            finding_code="deliverable_contract_mismatch",
            severity="blocking",
            message="Generator-owned semantic contract has no consistency report.",
            deterministic_corroboration=True,
        )]
    payload = _read_json(path)
    mapping = {
        "legacy_contract_not_production_eligible": "hidden_assumption_required",
        "hidden_candidate_dependency": "hidden_assumption_required",
        "deterministic_validator_not_passed": "teacher_truth_conflict",
        "rubric_missing_fact_coverage": "rubric_missing_fact_coverage",
        "rubric_weight_imbalance": "rubric_weight_imbalance",
    }
    return [SemanticFinding(
        finding_code=mapping.get(code, "deliverable_contract_mismatch"),
        severity="blocking",
        message=f"V2 deterministic consistency failure: {code}",
        deterministic_corroboration=True,
    ) for code in payload.get("reason_codes") or []]


def _teacher_paths(case_dir: Path, rubric_path: Path) -> Dict[str, Path]:
    candidates = {
        "rubric": rubric_path,
        "golden_run": _first_existing(case_dir / "teacher_runner" / "golden_run.json", case_dir / "package" / "artifacts" / "golden_run.json"),
        "training_annotation": _first_existing(case_dir / "training_annotation" / "training_annotation.json", case_dir / "package" / "artifacts" / "training_annotation.json"),
        "deterministic_answer_key": _optional_existing(case_dir / "package" / "artifacts" / "deterministic_answer_key.json"),
    }
    return {name: path for name, path in candidates.items() if path is not None and path.exists()}


def _find_dataset_row(case_dir: Path, task_id: str) -> Path:
    direct = list(case_dir.glob("rw_task_eval_input/*/dataset_row.json"))
    direct.extend(case_dir.glob("package/**/dataset_row.json"))
    if not direct:
        raise FileNotFoundError(f"dataset_row.json missing for {task_id}")
    return direct[0]


def _resolve_reference(base: Path, value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    candidate = base / path
    if candidate.exists():
        return candidate
    candidate = base / "reference_files" / path.name
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Candidate reference file missing: {value}")


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path and path.exists():
            return path
    raise FileNotFoundError(f"None of the expected artifact paths exist: {[str(path) for path in paths]}")


def _optional_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def _retry_once(callable_, output_dir: Path, label: str):
    attempts = []
    for attempt in (1, 2):
        try:
            result = callable_()
            attempts.append({"attempt": attempt, "status": "completed"})
            _write_json(output_dir / f"{label}_attempt_report.json", {"attempts": attempts, "raw_response_included": False})
            return result
        except Exception as exc:
            attempts.append({"attempt": attempt, "status": "failed", "error_type": type(exc).__name__})
            _write_json(output_dir / f"{label}_attempt_report.json", {"attempts": attempts, "raw_response_included": False})
            if attempt == 2:
                raise
    raise RuntimeError("unreachable")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(records: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _augmented_manifest(manifest: Dict[str, Any], records: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    payload = json.loads(json.dumps(manifest))
    by_task = {item["task_id"]: item for item in records}
    payload["production_batch_manifest_version"] = "v3.production_batch_manifest.semantic.1"
    payload["semantic_validation_mode"] = mode
    for case in payload.get("cases") or []:
        task_id = str(case.get("case_id") or "")
        record = by_task.get(task_id)
        case["legacy_task_state"] = case.get("task_state")
        case["semantic_gate_status"] = record.get("decision") if record else "not_evaluated"
        case["semantic_gate_pass"] = bool(record and record.get("semantic_gate_pass"))
        if mode == "blocking" and not case["semantic_gate_pass"]:
            case["task_state"] = "verifier_passed"
            case["production_candidate_eligible"] = False
            case["training_pool_candidate_eligible"] = False
            case["diagnostic_eval_recommended"] = False
            case.setdefault("blocker_reason_codes", []).append("semantic_validation_not_pass")
        elif mode != "blocking":
            case["legacy_semantic_status"] = "diagnostic_not_promoted"
    return payload


if __name__ == "__main__":
    main()
