from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from task_generator.core.scenario_first import ProfessionalRuleSetV1
from task_generator.planning.work_seed_admission import (
    PublicWorkSourceCatalogV1,
    WorkSeedAdmissionValidator,
    WorkSeedCandidateV1,
)


_ROOT = Path(__file__).parents[2] / "data" / "r10" / "work_seeds"


class WorkSeedAdmissionTests(unittest.TestCase):
    def _inputs(self):
        catalog = PublicWorkSourceCatalogV1.model_validate_json(
            (_ROOT / "public_source_catalog.json").read_text(encoding="utf-8")
        )
        candidates = [
            WorkSeedCandidateV1.model_validate(item)
            for item in json.loads((_ROOT / "candidate_work_seeds.json").read_text(encoding="utf-8"))
        ]
        rules = [
            ProfessionalRuleSetV1.model_validate(item)
            for item in json.loads((_ROOT / "professional_rule_sets.json").read_text(encoding="utf-8"))
        ]
        return catalog, candidates, rules

    def test_public_seed_cohort_has_four_candidates_per_domain_and_four_admissions(self):
        catalog, candidates, rules = self._inputs()
        report = WorkSeedAdmissionValidator().evaluate(
            catalog=catalog, candidates=candidates, rule_sets=rules,
        )
        self.assertEqual(report.decision, "pass")
        self.assertEqual(len(report.admitted_seed_ids), 4)
        self.assertEqual(len({item.seed.domain for item in candidates if item.status == "admitted"}), 2)
        self.assertTrue(all(item.passed for item in report.findings))

    def test_unknown_source_block_fails_closed(self):
        catalog, candidates, rules = self._inputs()
        payload = candidates[0].model_dump(mode="json")
        payload["seed"]["public_sources"][0]["block_ids"] = ["not_a_real_block"]
        candidates[0] = WorkSeedCandidateV1.model_validate(payload)
        report = WorkSeedAdmissionValidator().evaluate(
            catalog=catalog, candidates=candidates, rule_sets=rules,
        )
        self.assertEqual(report.decision, "blocked")
        finding = next(item for item in report.findings if item.candidate_id == candidates[0].candidate_id)
        self.assertIn("unknown_public_source_block", finding.reason_codes)

    def test_missing_candidate_or_rule_cohort_shape_fails_closed(self):
        catalog, candidates, rules = self._inputs()
        report = WorkSeedAdmissionValidator().evaluate(
            catalog=catalog, candidates=candidates[:-1], rule_sets=rules[:-1],
        )
        self.assertEqual(report.decision, "blocked")
        cohort = next(item for item in report.findings if item.candidate_id == "__cohort__")
        self.assertIn("candidate_count_invalid:procurement_operations", cohort.reason_codes)
        self.assertIn("missing_rule_set:procurement_operations", cohort.reason_codes)

    def test_browser_verified_source_requires_a_verification_note(self):
        catalog, _, _ = self._inputs()
        payload = catalog.model_dump(mode="json")
        payload["sources"][2]["verification_note"] = None
        with self.assertRaises(ValidationError):
            PublicWorkSourceCatalogV1.model_validate(payload)

    def test_candidate_status_requires_a_reasoned_rejection(self):
        _, candidates, _ = self._inputs()
        payload = candidates[2].model_dump(mode="json")
        payload["rejection_reason"] = None
        with self.assertRaises(ValidationError):
            WorkSeedCandidateV1.model_validate(payload)

    def test_admission_module_has_no_provider_or_registry_dependency(self):
        text = (Path(__file__).parents[2] / "src" / "task_generator" / "planning" / "work_seed_admission.py").read_text(encoding="utf-8")
        self.assertNotIn("ProviderConfig", text)
        self.assertNotIn("openai", text.casefold())
        self.assertNotIn("SkillRegistry", text)

    def test_offline_cli_writes_a_reproducible_report(self):
        from unittest.mock import patch
        from task_generator.cli.scenario_first import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "admission.json"
            with patch("sys.argv", [
                "taskgen-scenario-first", "--action", "admit-seeds",
                "--source-catalog", str(_ROOT / "public_source_catalog.json"),
                "--candidates", str(_ROOT / "candidate_work_seeds.json"),
                "--rule-sets", str(_ROOT / "professional_rule_sets.json"),
                "--output", str(output),
            ]):
                main()
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["decision"], "pass")
        self.assertEqual(len(payload["admitted_seed_ids"]), 4)


if __name__ == "__main__":
    unittest.main()
