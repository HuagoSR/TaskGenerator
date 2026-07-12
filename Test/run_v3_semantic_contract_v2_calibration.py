from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_semantic_contract_v2 import LegacyFinanceSemanticAuditor  # noqa: E402


SAMPLE_IDS = ["02", "06", "13", "18", "31", "35", "38", "47"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic F3 8+8 calibration.")
    parser.add_argument(
        "--legacy-review-root",
        type=Path,
        default=ROOT / "artifacts" / "finance_30_human_review_01",
    )
    parser.add_argument("--repaired-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    originals = []
    for sample_id in SAMPLE_IDS:
        candidate = args.legacy_review_root / "candidate_view" / sample_id
        teacher = args.legacy_review_root / "teacher_view" / sample_id
        dataset = _read(candidate / "dataset_row.json")
        rubric = _read(teacher / "rubric.json")
        report = LegacyFinanceSemanticAuditor().audit(dataset, candidate / "reference_files", rubric)
        originals.append({"sample_id": sample_id, **report.model_dump()})

    manifest = _read(args.repaired_manifest)
    repaired = []
    for case in manifest.get("cases") or []:
        contract_path = Path(case["case_dir"]) / "semantic_contract" / "task_semantic_contract.json"
        consistency_path = Path(case["case_dir"]) / "semantic_contract" / "semantic_contract_consistency_report.json"
        contract = _read(contract_path)
        consistency = _read(consistency_path)
        repaired.append({
            "task_id": case["case_id"],
            "motif": case["motif"],
            "contract_origin": contract.get("contract_origin"),
            "lifecycle": contract.get("lifecycle"),
            "consistency_decision": consistency.get("decision"),
            "candidate_ready": case.get("task_state") == "candidate_ready",
            "contract_sha256": _sha(contract_path),
        })

    original_blocked = sum(item["decision"] == "blocked" for item in originals)
    repaired_pass = sum(
        item["contract_origin"] == "generator_owned_v2"
        and item["lifecycle"] == "verified"
        and item["consistency_decision"] == "pass"
        and item["candidate_ready"]
        for item in repaired
    )
    issue_families = {
        "candidate_support": any("missing_candidate_input" in item["reason_codes"] for item in originals),
        "decision_rule": any("underdefined_decision_rule" in item["reason_codes"] for item in originals),
        "rubric_fact_coverage": all("rubric_missing_fact_coverage" in item["reason_codes"] for item in originals),
    }
    decision = "offline_contract_calibration_pass" if (
        original_blocked == 8 and repaired_pass >= 7 and all(issue_families.values())
    ) else "offline_contract_calibration_fail"
    payload = {
        "report_version": "v3.semantic_contract_v2_calibration.1",
        "decision": decision,
        "original_count": len(originals),
        "original_blocked_count": original_blocked,
        "repaired_count": len(repaired),
        "repaired_pass_count": repaired_pass,
        "issue_family_recall": issue_families,
        "originals": originals,
        "repaired": repaired,
        "external_calls": 0,
        "notes": [
            "Original task evidence is read-only.",
            "Repaired twins are newly generated V2 tasks, not overwritten legacy tasks.",
        ],
    }
    _write(args.output_dir / "semantic_contract_v2_calibration_report.json", payload)
    print(json.dumps({key: payload[key] for key in [
        "decision", "original_blocked_count", "repaired_pass_count", "issue_family_recall", "external_calls"
    ]}, ensure_ascii=False, indent=2))


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
