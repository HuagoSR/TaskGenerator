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
    tuzi_backup_semantic_config,
)
from task_generator.v3_semantic_secondary_cost import SecondaryCostLedgerManager
from task_generator.v3_semantic_contract_v2 import LegacyFinanceSemanticAuditor  # noqa: E402
from task_generator.v3_semantic_validity import (  # noqa: E402
    CandidateBlindReview,
    SecondarySemanticReview,
    SemanticFinding,
    SemanticContractDraftBuilder,
    SemanticReviewPackageBuilder,
    SemanticValidityGate,
    TeacherRubricReview,
    write_semantic_artifact,
)


CASES = [2, 6, 13, 18, 31, 35, 38, 47]
FIXED_AUDIT_CASES = {2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the governed 8-task semantic calibration campaign.")
    parser.add_argument("--review-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--deepseek-key-path", required=True)
    parser.add_argument("--tuzi-env-path", required=True)
    parser.add_argument("--allow-external-semantic-review", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--secondary-model", default="gpt-5.4-pro")
    parser.add_argument("--tuzi-key-slot", choices=["legacy", "backup"], default="legacy")
    parser.add_argument("--secondary-max-tokens", type=int, default=8000)
    parser.add_argument("--campaign-budget-rmb", type=float, default=10.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.allow_external_semantic_review:
        raise SystemExit("Calibration requires --allow-external-semantic-review.")
    review_root = Path(args.review_root)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    expected = _read_json(ROOT / "Test" / "v3_semantic_calibration" / "acceptance_contract.json")
    records = []
    for number in CASES:
        records.append(_run_case(number, review_root, output_root, args))
        _write_summary(output_root, records, expected, "running")
    summary = _write_summary(output_root, records, expected, "completed")
    print(json.dumps(summary, ensure_ascii=False))


def _run_case(number: int, review_root: Path, output_root: Path, args: argparse.Namespace) -> Dict[str, Any]:
    case_key = f"{number:02d}"
    output_dir = output_root / case_key
    output_dir.mkdir(parents=True, exist_ok=True)
    gate_path = output_dir / "semantic_validity_gate_report.json"
    if args.resume and gate_path.exists():
        gate = _read_json(gate_path)
        return _record(number, gate, output_dir, bool(gate.get("artifact_sha256", {}).get("secondary_blind")))

    candidate_dir = review_root / "candidate_view" / case_key
    teacher_dir = review_root / "teacher_view" / case_key
    dataset_path = candidate_dir / "dataset_row.json"
    dataset = _read_json(dataset_path)
    references = sorted((candidate_dir / "reference_files").glob("*"))
    legacy_audit = LegacyFinanceSemanticAuditor().audit(
        dataset,
        candidate_dir / "reference_files",
        _read_json(teacher_dir / "rubric.json"),
    )
    deterministic_findings = [SemanticFinding(
        finding_code=code,
        severity="blocking",
        message=f"Deterministic legacy audit confirmed: {code}",
        deterministic_corroboration=True,
    ) for code in legacy_audit.reason_codes]
    contract = SemanticContractDraftBuilder().build_from_legacy_dataset(dataset, references)
    contract_path = output_dir / "task_semantic_contract.json"
    write_semantic_artifact(contract_path, contract)
    deliverable_contract = {Path(str(value).replace("\\", "/")).name: ["Satisfy every visible requirement in the prompt."] for value in dataset.get("deliverable_files") or []}
    blind_package_path = output_dir / "candidate_blind_prompt_package.json"
    blind_package = SemanticReviewPackageBuilder().build_blind_package(
        contract.task_id,
        str(dataset.get("prompt") or ""),
        deliverable_contract,
        references,
        blind_package_path,
        semantic_contract=contract,
    )

    blind_review_path = output_dir / "candidate_blind_review.json"
    primary = SemanticReviewExecutor(deepseek_semantic_config(args.deepseek_key_path, args.timeout_seconds))
    if args.resume and blind_review_path.exists():
        blind_review = CandidateBlindReview.model_validate(_read_json(blind_review_path))
    else:
        blind_review = _run_with_retry(lambda: primary.review_blind(blind_package), output_dir, "primary_blind")
        write_semantic_artifact(blind_review_path, blind_review)
        _write_json(output_dir / "primary_blind_provider_diagnostics.json", primary.last_diagnostics)

    teacher_paths = {path.stem: path for path in sorted(teacher_dir.glob("*.json"))}
    teacher_package_path = output_dir / "teacher_rubric_prompt_package.json"
    teacher_package = SemanticReviewPackageBuilder().build_teacher_package(
        contract.task_id, blind_review_path, contract_path, teacher_paths, teacher_package_path
    )
    teacher_review_path = output_dir / "teacher_rubric_review.json"
    if args.resume and teacher_review_path.exists():
        teacher_review = TeacherRubricReview.model_validate(_read_json(teacher_review_path))
    else:
        teacher_review = _run_with_retry(lambda: primary.review_teacher(teacher_package), output_dir, "primary_teacher")
        write_semantic_artifact(teacher_review_path, teacher_review)
        _write_json(output_dir / "primary_teacher_provider_diagnostics.json", primary.last_diagnostics)

    preliminary = SemanticValidityGate().build(
        contract,
        blind_review,
        teacher_review,
        "blocking",
        force_secondary_audit=number in FIXED_AUDIT_CASES,
        deterministic_findings=deterministic_findings,
    )
    secondary_reviews = []
    secondary_failed = False
    if preliminary.secondary_review_required:
        provider_status_path = output_root / "secondary_provider_status.json"
        if provider_status_path.exists() and _read_json(provider_status_path).get("status") == "unavailable":
            secondary_failed = True
        else:
            secondary_failed, secondary_reviews = _run_secondary_reviews(
                args,
                output_dir,
                blind_package,
                contract,
                contract_path,
                blind_review_path,
                teacher_paths,
                [item for item in preliminary.findings if item.severity == "blocking" and not item.deterministic_corroboration],
            )

    gate = SemanticValidityGate().build(
        contract,
        blind_review,
        teacher_review,
        "blocking",
        force_secondary_audit=number in FIXED_AUDIT_CASES,
        secondary_compact_reviews=secondary_reviews,
        deterministic_findings=deterministic_findings,
    )
    if secondary_failed:
        gate.decision = "needs_secondary_review"
        gate.semantic_gate_pass = False
        gate.secondary_review_required = False
        gate.needs_human_review = True
        gate.notes.append("Secondary reviewer is unavailable or exhausted the allowed attempts; manual review is required.")
    gate.artifact_sha256 = {
        "contract": _sha256(contract_path),
        "blind_package": _sha256(blind_package_path),
        "blind_review": _sha256(blind_review_path),
        "teacher_review": _sha256(teacher_review_path),
    }
    if secondary_reviews:
        gate.artifact_sha256["secondary_compact"] = _sha256(output_dir / "secondary_candidate_blind_review.json")
    write_semantic_artifact(gate_path, gate)
    return _record(number, gate.model_dump(mode="json"), output_dir, bool(secondary_reviews))


def _run_secondary_reviews(
    args: argparse.Namespace,
    output_dir: Path,
    blind_package: Dict[str, Any],
    contract,
    contract_path: Path,
    blind_review_path: Path,
    teacher_paths: Dict[str, Path],
    primary_findings,
):
    secondary_failed = False
    reviews = []
    secondary_blind_path = output_dir / "secondary_candidate_blind_review.json"
    if args.tuzi_key_slot == "backup":
        config = tuzi_backup_semantic_config(args.tuzi_env_path, args.secondary_model, args.timeout_seconds)
        ledger = SecondaryCostLedgerManager(output_dir.parent / "secondary_cost_ledger.json", args.campaign_budget_rmb)
    else:
        config = gpt54_semantic_config(args.tuzi_env_path, args.timeout_seconds)
        ledger = None
    secondary = SemanticReviewExecutor(config, max_tokens=args.secondary_max_tokens, cost_ledger=ledger)
    if args.resume and secondary_blind_path.exists():
        reviews.append(SecondarySemanticReview.model_validate(_read_json(secondary_blind_path)))
    elif args.resume and _attempts_exhausted(output_dir / "secondary_blind_attempt_report.json"):
        secondary_failed = True
    else:
        try:
            review = _run_with_retry(
                lambda: secondary.review_secondary(blind_package, primary_findings, "candidate_blind"),
                output_dir,
                "secondary_blind",
            )
            reviews.append(review)
            write_semantic_artifact(secondary_blind_path, review)
            _write_json(output_dir / "secondary_blind_provider_diagnostics.json", secondary.last_diagnostics)
        except Exception:
            secondary_failed = True
    if reviews:
        secondary_package_path = output_dir / "secondary_teacher_rubric_prompt_package.json"
        secondary_package = SemanticReviewPackageBuilder().build_teacher_package(
            contract.task_id, blind_review_path, contract_path, teacher_paths, secondary_package_path
        )
        secondary_teacher_path = output_dir / "secondary_teacher_rubric_review.json"
        if args.resume and secondary_teacher_path.exists():
            reviews.append(SecondarySemanticReview.model_validate(_read_json(secondary_teacher_path)))
        elif args.resume and _attempts_exhausted(output_dir / "secondary_teacher_attempt_report.json"):
            secondary_failed = True
        else:
            try:
                review = _run_with_retry(
                    lambda: secondary.review_secondary(secondary_package, primary_findings, "teacher_rubric"),
                    output_dir,
                    "secondary_teacher",
                )
                reviews.append(review)
                write_semantic_artifact(secondary_teacher_path, review)
                _write_json(output_dir / "secondary_teacher_provider_diagnostics.json", secondary.last_diagnostics)
            except Exception:
                secondary_failed = True
    return secondary_failed, reviews


def _record(number: int, gate: Dict[str, Any], output_dir: Path, secondary: bool) -> Dict[str, Any]:
    return {
        "case_number": number,
        "task_id": gate.get("task_id"),
        "decision": gate.get("decision"),
        "reason_codes": gate.get("reason_codes") or [],
        "semantic_gate_pass": bool(gate.get("semantic_gate_pass")),
        "secondary_review_performed": secondary,
        "needs_human_review": bool(gate.get("needs_human_review")),
        "gate_report_path": str(output_dir / "semantic_validity_gate_report.json"),
    }


def _write_summary(output_root: Path, records: List[Dict[str, Any]], expected: Dict[str, Any], status: str) -> Dict[str, Any]:
    known = expected.get("expected_primary_findings") or {}
    detected = 0
    total = 0
    blocking_hits = 0
    for record in records:
        required = set(known.get(str(record["case_number"])) or [])
        found = set(record.get("reason_codes") or [])
        detected += len(required.intersection(found))
        total += len(required)
        if record.get("decision") in {"revise", "blocked", "needs_secondary_review", "needs_human_review"}:
            blocking_hits += 1
    summary = {
        "report_version": "v3.semantic_calibration_campaign.1",
        "status": status,
        "authorized_scope": "fixed_8_task_semantic_review_only",
        "case_count": len(records),
        "blocking_recall": blocking_hits / len(records) if records else 0.0,
        "known_finding_recall": detected / total if total else 0.0,
        "secondary_review_count": sum(1 for item in records if item.get("secondary_review_performed")),
        "needs_human_review_count": sum(1 for item in records if item.get("needs_human_review")),
        "records": records,
        "external_effects": {"deepseek_official": bool(records), "tuzi": any(item.get("secondary_review_performed") for item in records)},
    }
    _write_json(output_root / "semantic_calibration_summary.json", summary)
    return summary


def _run_with_retry(callable_, output_dir: Path, label: str):
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


def _attempts_exhausted(path: Path) -> bool:
    if not path.exists():
        return False
    payload = _read_json(path)
    attempts = payload.get("attempts") or []
    return len(attempts) >= 2 and all(item.get("status") == "failed" for item in attempts)


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
