from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_clean_eval_gate import build_phase16_clean_eval_gate
from task_generator.v3_phase16_external_eval_result_builder import (
    Phase16ExternalEvalResultBuilderRequest,
    build_phase16_external_eval_results,
)


CASES = [f"pipeline_b_batch_{index:02d}_evidence_to_deliverable" for index in range(1, 5)]
ARMS = ["baseline_deterministic", "contract_v2_only", "contract_v2_plus_productive_complexity"]
MODELS = ["gpt-4o-mini", "gemini-3-pro-preview"]


def complete_records(case_ids: list[str]) -> list[dict]:
    scores = {
        "baseline_deterministic": {"gpt-4o-mini": 0.40, "gemini-3-pro-preview": 0.80},
        "contract_v2_only": {"gpt-4o-mini": 0.35, "gemini-3-pro-preview": 0.82},
        "contract_v2_plus_productive_complexity": {"gpt-4o-mini": 0.20, "gemini-3-pro-preview": 0.81},
    }
    return [
        {
            "case_id": case_id,
            "arm_id": arm,
            "evaluated_model": model,
            "grader_model": "gpt-5.4-pro",
            "score": scores[arm][model],
            "run_status": "completed",
            "contains_secret": False,
            "raw_prompt_included": False,
        }
        for case_id in case_ids
        for arm in ARMS
        for model in MODELS
    ]


class Phase16EvalScopeTests(unittest.TestCase):
    def run_gate(self, records: list[dict], case_ids: list[str], scope_id: str = "four_case") -> dict:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result_path = root / "results.json"
            result_path.write_text(json.dumps({"records": records}), encoding="utf-8")
            return build_phase16_clean_eval_gate(
                root,
                str(result_path),
                scope_id=scope_id,
                case_ids=case_ids,
            )["import_report"]

    def test_complete_four_case_scope_accepts_24_records(self) -> None:
        report = self.run_gate(complete_records(CASES), CASES)
        acceptance = report["clean_eval_acceptance"]
        self.assertTrue(acceptance["clean_eval_proven"])
        self.assertTrue(acceptance["four_case_clean_eval_proven"])
        self.assertEqual(acceptance["record_count"], 24)

    def test_complete_negative_four_case_scope_is_proven_but_not_promotable(self) -> None:
        records = complete_records(CASES)
        for record in records:
            if record["arm_id"] != "baseline_deterministic":
                record["score"] = 0.50
        report = self.run_gate(records, CASES)
        self.assertTrue(report["clean_eval_acceptance"]["clean_eval_proven"])
        self.assertFalse(report["performance_gate"]["passed"])
        self.assertEqual(report["performance_gate"]["recommended_decision"], "redesign_again")

    def test_missing_record_blocks(self) -> None:
        report = self.run_gate(complete_records(CASES)[:-1], CASES)
        self.assertFalse(report["clean_eval_acceptance"]["clean_eval_proven"])
        self.assertIn("missing_required_clean_eval_records", report["clean_eval_acceptance"]["blocking_reasons"])

    def test_duplicate_record_blocks(self) -> None:
        records = complete_records(CASES)
        report = self.run_gate(records + [deepcopy(records[0])], CASES)
        self.assertFalse(report["clean_eval_acceptance"]["clean_eval_proven"])
        reasons = [item["reason"] for item in report["clean_eval_acceptance"]["malformed_records"]]
        self.assertIn("duplicate_record_key", reasons)

    def test_malformed_record_variants_block(self) -> None:
        mutations = {
            "wrong_grader": ("grader_model", "not-the-fixed-grader"),
            "null_score": ("score", None),
            "secret": ("contains_secret", True),
            "raw_prompt": ("raw_prompt_included", True),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(label=label):
                records = complete_records(CASES)
                records[0][field] = value
                report = self.run_gate(records, CASES)
                self.assertFalse(report["clean_eval_acceptance"]["clean_eval_proven"])

    def test_two_case_default_remains_compatible(self) -> None:
        two_cases = [CASES[0], CASES[2]]
        report = self.run_gate(complete_records(two_cases), two_cases, scope_id="two_case")
        acceptance = report["clean_eval_acceptance"]
        self.assertTrue(acceptance["two_case_clean_eval_proven"])
        self.assertEqual(acceptance["expected_record_count"], 12)

    def test_result_builder_reports_conflicting_existing_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runbook = root / "runbook.json"
            runbook.write_text(json.dumps({"items": []}), encoding="utf-8")
            first = root / "first.json"
            second = root / "second.json"
            records = complete_records([CASES[0]])[:1]
            first.write_text(json.dumps({"records": records}), encoding="utf-8")
            conflicting = deepcopy(records)
            conflicting[0]["score"] = 0.99
            second.write_text(json.dumps({"records": conflicting}), encoding="utf-8")
            report = build_phase16_external_eval_results(
                Phase16ExternalEvalResultBuilderRequest(
                    runbook_path=str(runbook),
                    output_dir=str(root / "report"),
                    result_output_path=str(root / "merged.json"),
                    existing_result_paths=[str(first), str(second)],
                )
            )
            self.assertEqual(report.summary["merge_conflict_count"], 1)


if __name__ == "__main__":
    unittest.main()
