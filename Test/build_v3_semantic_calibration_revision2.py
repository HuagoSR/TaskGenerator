from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict


CASH_CASES = {2, 6}
CROSS_CASES = {13, 31, 47}
POLICY_CASES = {18, 35, 38}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build revision-02 semantic twins from revision-01 findings.")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = Path(args.source_dir)
    output = Path(args.output_dir)
    if output.exists():
        raise FileExistsError(f"Revision output already exists: {output}")
    shutil.copytree(source, output)
    records = []
    for number in sorted(CASH_CASES | CROSS_CASES | POLICY_CASES):
        key = f"{number:02d}"
        candidate_dir = output / "candidate_view" / key
        teacher_dir = output / "teacher_view" / key
        dataset_path = candidate_dir / "dataset_row.json"
        dataset = _read_json(dataset_path)
        if number in CASH_CASES:
            addendum = candidate_dir / "reference_files" / "cash_matching_rules.md"
            addendum.write_text(
                "# Cash matching and activity rules\n\n"
                "- Match records only when the transaction reference and signed amount agree exactly.\n"
                "- A bank record whose reference is absent from the ledger is bank-only.\n"
                "- A ledger record whose reference is absent from the bank statement is ledger-only.\n"
                "- Period-activity total is the sum of every signed Amount in that source; it is not an opening, ending, or adjusted account balance.\n",
                encoding="utf-8",
            )
            _append_reference(dataset, addendum.name)
            repair = "make exact reference matching and period-activity meaning explicit"
        elif number in CROSS_CASES:
            rules = candidate_dir / "reference_files" / "disposition_rules.md"
            rules.write_text(
                "# Three-way match formulas and disposition rules\n\n"
                "- Quantity variance is `Invoiced_Qty - Received_Qty`. PO quantity is retained as supporting context.\n"
                "- Unit-price variance is `Invoice_Unit_Price - PO_Unit_Price`.\n"
                "- Two invoice lines are a duplicate pair when PO_ID, Item_ID, Invoiced_Qty, and Invoice_Unit_Price are identical; flag every member of the pair.\n"
                "- `clear`: both variances are zero, a receipt exists, and the line is not in a duplicate pair.\n"
                "- `hold`: every member of a duplicate pair.\n"
                "- `investigate`: any nonzero quantity or unit-price variance, or a missing receipt, unless duplicate hold already applies.\n",
                encoding="utf-8",
            )
            _append_reference(dataset, rules.name)
            repair = "define exact variance formulas, duplicate identity, and disposition precedence"
        else:
            rules = candidate_dir / "reference_files" / "exception_follow_up_rules.md"
            rules.write_text(
                "# Expense exception follow-up rules\n\n"
                "- POL-001 missing receipt: request the receipt and hold reimbursement until supplied.\n"
                "- POL-002 per-person meal threshold: obtain Director approval before reimbursement.\n"
                "- POL-003 entertainment approval: obtain documented Director approval and hold reimbursement until supplied.\n"
                "- If more than one clause applies, include every corresponding follow-up action.\n",
                encoding="utf-8",
            )
            _append_reference(dataset, rules.name)
            _augment_policy_answer_key(teacher_dir / "deterministic_answer_key.json")
            _rebalance_policy_rubric(teacher_dir / "rubric.json")
            repair = "define deterministic follow-up actions and add them to teacher truth and rubric"
        _write_json(dataset_path, dataset)
        _write_json(
            teacher_dir / "semantic_repair_addendum.json",
            {
                "revision": 2,
                "candidate_visible_repair": repair,
                "goldenrun_alignment": "GoldenRun must apply the added candidate-visible rule file and must not use any unstated assumption.",
                "all_visible_requirements_covered": True,
            },
        )
        records.append({"case_number": number, "repair": repair})
    _write_json(output / "revision_02_manifest.json", {"revision": 2, "case_count": 8, "records": records, "source_revision_preserved": True})


def _append_reference(dataset: Dict[str, Any], name: str) -> None:
    value = f"reference_files\\{name}"
    references = dataset.setdefault("reference_files", [])
    if value not in references:
        references.append(value)


def _augment_policy_answer_key(path: Path) -> None:
    payload = _read_json(path)
    follow_up_by_clause = {
        "POL-001": "request missing receipt and hold reimbursement",
        "POL-002": "obtain Director approval before reimbursement",
        "POL-003": "obtain documented Director approval and hold reimbursement",
    }
    for item in payload.get("exceptions") or []:
        clauses = item.get("clauses") or []
        item["attendee_count"] = 1 if "POL-002" in clauses else None
        item["per_person_amount"] = item.get("amount") if "POL-002" in clauses else None
        item["required_follow_up"] = [follow_up_by_clause[clause] for clause in clauses if clause in follow_up_by_clause]
    _write_json(path, payload)


def _rebalance_policy_rubric(path: Path) -> None:
    payload = _read_json(path)
    fact_section = next(section for section in payload["sections"] if section["section_name"] == "fact_checks")
    fact_section["criteria"].append(
        {
            "criterion_id": "R_FACT_004",
            "section": "fact_checks",
            "criterion_type": "fact",
            "audience": "candidate",
            "description": "State every required follow-up action using the candidate-visible follow-up rules.",
            "pass_condition": "Every exception includes the rule-defined follow-up for each applicable clause.",
            "weight": 20,
            "source_ids": ["deterministic_answer_key", "exception_follow_up_rules"],
        }
    )
    for criterion in fact_section["criteria"]:
        criterion["weight"] = 20
    compliance = next(section for section in payload["sections"] if section["section_name"] == "compliance_checks")
    for criterion in compliance["criteria"]:
        criterion["weight"] = 10
    payload["fact_weight_ratio"] = 0.8
    _write_json(path, payload)


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
