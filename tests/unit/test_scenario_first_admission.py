from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from task_generator.core.scenario_first import (
    EvidenceProjectionPlanV1,
    ProfessionalRuleSetV1,
    ScenarioBibleV1,
    TaskDecisionMatrixV1,
    WorkSeedV1,
)
from task_generator.planning.scenario_first_admission import ScenarioFirstAdmissionValidator


_FIXTURE = Path(__file__).parents[1] / "fixtures" / "scenario_first" / "valid_static_case.json"


class ScenarioFirstAdmissionTests(unittest.TestCase):
    def _case(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        return (
            WorkSeedV1.model_validate(payload["work_seed"]),
            ProfessionalRuleSetV1.model_validate(payload["rule_set"]),
            ScenarioBibleV1.model_validate(payload["bible"]),
            EvidenceProjectionPlanV1.model_validate(payload["projection"]),
            TaskDecisionMatrixV1.model_validate(payload["matrix"]),
        )

    def _report(self, mutate=None):
        seed, rules, bible, projection, matrix = self._case()
        payloads = [item.model_dump(mode="json") for item in (seed, rules, bible, projection, matrix)]
        if mutate:
            mutate(*payloads)
        return ScenarioFirstAdmissionValidator().evaluate(
            work_seed=WorkSeedV1.model_validate(payloads[0]),
            rule_set=ProfessionalRuleSetV1.model_validate(payloads[1]),
            bible=ScenarioBibleV1.model_validate(payloads[2]),
            projection=EvidenceProjectionPlanV1.model_validate(payloads[3]),
            matrix=TaskDecisionMatrixV1.model_validate(payloads[4]),
            known_skill_ids=["skill_evidence_review"],
        )

    def test_valid_fixture_passes_and_hashes_stably(self):
        first = self._report()
        second = self._report()
        self.assertEqual(first.decision, "pass")
        self.assertEqual(first.input_sha256, second.input_sha256)
        seed, *_ = self._case()
        self.assertEqual(seed.canonical_sha256(), seed.canonical_sha256())

    def test_contracts_reject_extra_fields_and_non_https_sources(self):
        seed, *_ = self._case()
        with self.assertRaises(ValidationError):
            WorkSeedV1.model_validate({**seed.model_dump(), "unknown": True})
        bad = seed.model_dump(mode="json")
        bad["public_sources"][0]["locator"] = "http://example.gov/not-allowed"
        with self.assertRaises(ValidationError):
            WorkSeedV1.model_validate(bad)

    def test_blocks_missing_source_trace(self):
        seed, *_ = self._case()
        payload = seed.model_dump(mode="json")
        payload["public_sources"] = []
        with self.assertRaises(ValidationError):
            WorkSeedV1.model_validate(payload)

    def test_blocks_timeline_role_and_fact_reference_failures(self):
        def mutate(_seed, _rules, bible, projection, _matrix):
            bible["facts"][1]["actor_role_id"] = "role_missing"
            projection["artifacts"][0]["records"][0]["fact_ids"] = ["fact_missing"]
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        reasons = [item.reason_code for item in report.findings]
        self.assertIn("world_reference_or_timeline_invalid", reasons)
        self.assertIn("projection_shape_or_fact_reference_invalid", reasons)

    def test_blocks_infeasible_business_timeline(self):
        def mutate(_seed, _rules, bible, _projection, _matrix):
            bible["facts"][1]["occurred_at"] = 0
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        self.assertIn("world_reference_or_timeline_invalid", [item.reason_code for item in report.findings])

    def test_blocks_role_authority_and_nonvisible_evidence(self):
        def mutate(_seed, _rules, bible, projection, matrix):
            bible["facts"][1]["authority_required"] = "approves payment"
            matrix["decision_points"][0]["evidence_refs"][0]["field_names"] = ["internal_only"]
            projection["artifacts"][0]["records"][0]["values"]["internal_only"] = "not visible"
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        self.assertIn("world_reference_or_timeline_invalid", [item.reason_code for item in report.findings])
        self.assertIn("decision_reference_or_count_invalid", [item.reason_code for item in report.findings])

    def test_blocks_record_shape_and_missing_normal_background(self):
        def mutate(_seed, _rules, _bible, projection, _matrix):
            for artifact in projection["artifacts"]:
                artifact["records"] = artifact["records"][:1]
                artifact["records"][0]["record_class"] = "decision_relevant"
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        finding = next(item for item in report.findings if item.category == "projection_integrity")
        self.assertFalse(finding.passed)

    def test_blocks_answer_labels(self):
        def mutate(_seed, _rules, _bible, projection, _matrix):
            projection["artifacts"][0]["candidate_visible_fields"].append("Requires Follow-Up")
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        finding = next(item for item in report.findings if item.category == "answer_leakage")
        self.assertEqual(finding.reason_code, "answer_label_leakage")

    def test_blocks_decision_without_evidence_or_unknown_skill(self):
        def mutate(_seed, _rules, _bible, _projection, matrix):
            matrix["decision_points"][0]["evidence_refs"][0]["record_id"] = "missing"
            matrix["decision_points"][1]["skill_ids"] = ["unregistered_skill"]
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        self.assertIn("decision_reference_or_count_invalid", [item.reason_code for item in report.findings])

    def test_unresolved_fact_requires_uncertainty_conclusion(self):
        def mutate(_seed, _rules, _bible, _projection, matrix):
            matrix["decision_points"][2]["allowed_uncertainty_conclusions"] = []
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        self.assertIn("unresolved_fact_requires_uncertainty_conclusion", [item.reason_code for item in report.findings])

    def test_blocks_direct_teacher_treatment_in_candidate_values(self):
        def mutate(_seed, _rules, bible, projection, _matrix):
            projection["artifacts"][0]["records"][0]["values"]["memo"] = bible["correct_treatments"][0]
        report = self._report(mutate)
        self.assertEqual(report.decision, "blocked")
        self.assertIn("teacher_only_treatment_leaked", [item.reason_code for item in report.findings])

    def test_r7_regression_fixture_is_diagnostic_only(self):
        path = _FIXTURE.parent / "r7_failure_patterns.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["patterns"]), 4)
        self.assertTrue(all("TASK_" not in json.dumps(item) for item in payload["patterns"]))


if __name__ == "__main__":
    unittest.main()
