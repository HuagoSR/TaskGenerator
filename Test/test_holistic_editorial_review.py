import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.task_generator.v3_holistic_editorial import (
    CandidateSolveReview, HolisticCostLedger, WholeTaskRevisionBundle,
)
from Test.run_v3_holistic_editorial_review import _compare, _compile_prompt, _fact_rubric


class HolisticEditorialReviewTests(unittest.TestCase):
    def test_revision_bundle_is_complete_but_not_micro_findings(self):
        bundle = WholeTaskRevisionBundle(
            task_id="t", overall_decision="revise", issue_summary=["missing input"],
            revised_prompt="complete prompt", expected_result={"count": 1},
            calculation_explanation=["count visible rows"],
            rubric=[{"criterion": "fact", "weight": 70}, {"criterion": "deliverable", "weight": 20}, {"criterion": "style", "weight": 10}],
        )
        self.assertEqual(bundle.overall_decision, "revise")

    def test_cost_ledger_uses_backup_and_hard_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = HolisticCostLedger(Path(directory) / "ledger.json", budget_rmb=1, request_cap=1)
            reserve = ledger.reserve("gpt-5.6-terra", 1000, 100)
            class Usage: prompt_tokens=500; completion_tokens=50
            ledger.record("gpt-5.6-terra", "editor", 1, Usage(), reserve, "completed")
            data = json.loads((Path(directory) / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(data["key_slot"], "backup")
            with self.assertRaises(Exception): ledger.reserve("gpt-5.6-terra", 1000, 100)

    def test_prompts_remove_known_hidden_assumptions(self):
        base={"reference_files":["reference_files/a.xlsx"],"deliverable_files":["deliverable_files/out.xlsx"]}
        cash=_compile_prompt(base,"fan_in_reconciliation")
        self.assertIn("do not infer",cash)
        self.assertNotIn("calculate adjusted",cash.lower())
        policy=_compile_prompt(base,"policy_application")
        self.assertIn("attendee_counts.xlsx",policy)

    def test_fact_rubric_is_at_least_sixty_percent(self):
        rubric=_fact_rubric("cross_check_validation",{"hold":2})
        ratio=sum(x["weight"] for x in rubric if x["type"]=="fact")/sum(x["weight"] for x in rubric)
        self.assertGreaterEqual(ratio,.6)
        self.assertFalse(any("travel" in x["criterion"].lower() for x in rubric))

    def test_comparison_requires_all_expected_facts(self):
        self.assertTrue(_compare({"count":2},{"count":2,"note":"ok"})["match"])
        self.assertFalse(_compare({"count":2},{"count":3})["match"])


if __name__ == "__main__": unittest.main()
