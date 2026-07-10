from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from task_generator.v3_domain_profile import DomainProfile


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_summary(run_root: Path) -> Dict[str, Any]:
    acceptance = _load(run_root / "acceptance_report.json")
    manifest = _load(run_root / "end_to_end_run_manifest.json")
    batch_path = Path(manifest["stages"]["task_generation"]["artifact_paths"]["pipeline_b_batch_report"])
    batch = _load(batch_path)
    cases: List[Dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    for case in batch.get("cases") or []:
        case_dir = Path(str(case.get("case_dir") or ""))
        blueprint_path = case_dir / "prototype" / "draft_task_blueprint.json"
        blueprint = _load(blueprint_path) if blueprint_path.is_file() else {}
        reference_files = [item.get("file_name") for item in ((blueprint.get("data_spec") or {}).get("reference_files") or [])]
        deliverables = [item.get("file_name") for item in (blueprint.get("deliverable_spec") or [])]
        reason_counts.update(case.get("reason_codes") or [])
        cases.append(
            {
                "case_id": case.get("case_id"),
                "motif": case.get("motif"),
                "task_state": "candidate_ready" if case.get("package_readiness") == "candidate_ready" else case.get("package_readiness"),
                "verifier_status": case.get("verifier_status"),
                "export_decision": case.get("export_decision"),
                "workflow_context_fit": case.get("workflow_context_fit"),
                "selected_skill_count": case.get("selected_skill_count"),
                "reference_files": reference_files,
                "deliverables": deliverables,
            }
        )
    return {
        "run_id": acceptance.get("run_id"),
        "metrics": acceptance.get("metrics") or {},
        "content_fingerprint": acceptance.get("content_fingerprint"),
        "external_effects": acceptance.get("external_effects") or {},
        "failure_reason_counts": dict(sorted(reason_counts.items())),
        "cases": cases,
    }


def build_domain_slice_comparison(
    finance_run_root: str | Path,
    warehouse_run_root: str | Path,
    warehouse_profile: DomainProfile,
    contamination_ledger_path: str | Path,
) -> Dict[str, Any]:
    finance = _run_summary(Path(finance_run_root))
    warehouse_root = Path(warehouse_run_root)
    warehouse = _run_summary(warehouse_root)
    contamination = _load(Path(contamination_ledger_path))
    leakage_hits: List[Dict[str, str]] = []
    for path in sorted(warehouse_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".txt", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in warehouse_profile.forbidden_terms:
            if term.lower() in text:
                leakage_hits.append({"path": path.relative_to(warehouse_root).as_posix(), "term": term})
    warehouse_metrics = warehouse["metrics"]
    decision = "offline_vertical_slice_passed"
    blockers: List[str] = []
    if any(int(warehouse_metrics.get(key) or 0) < 3 for key in ("generated_case_count", "candidate_ready_count", "verifier_pass_count", "export_compatible_count")):
        blockers.append("warehouse_three_case_acceptance_not_met")
    if int(warehouse_metrics.get("qa_blocked_count") or 0):
        blockers.append("warehouse_qa_blocked")
    if int(warehouse_metrics.get("executed_eval_count") or 0):
        blockers.append("external_eval_was_executed")
    if contamination.get("decision") != "pass":
        blockers.append("contamination_gate_not_passed")
    if leakage_hits:
        blockers.append("finance_audit_vocabulary_leakage")
    if blockers:
        decision = "offline_vertical_slice_blocked"
    return {
        "version": "v3.milestone_e_domain_slice_comparison.1",
        "comparison_scope": "single_second_domain_vertical_slice_not_broad_generalization",
        "controlled_variables": {
            "case_count": 3,
            "motifs": ["fan_in_reconciliation", "cross_check_validation", "policy_application"],
            "workers": 1,
            "eval_policy": "prepare_only",
            "extractor": "deterministic_mock_smoke_only",
        },
        "finance_control": finance,
        "warehouse_inventory": warehouse,
        "contamination_decision": contamination.get("decision"),
        "forbidden_term_hits": leakage_hits,
        "decision": decision,
        "blocking_reasons": blockers,
        "next_gate": "explicit_authorization_required_for_public_source_deepseek_extraction",
    }
