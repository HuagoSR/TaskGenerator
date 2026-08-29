from __future__ import annotations

import json
import unittest
from pathlib import Path

from task_generator.core.scenario_first import ScenarioBibleV1
from task_generator.planning.evidence_projection_readiness import EvidenceProjectionReadinessValidator


_FIXTURE = Path(__file__).parents[1] / "fixtures" / "scenario_first" / "valid_static_case.json"
class EvidenceProjectionReadinessTests(unittest.TestCase):
    def test_narrative_v1_bible_is_blocked_without_inventing_records(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        report = EvidenceProjectionReadinessValidator().evaluate(ScenarioBibleV1.model_validate(payload["bible"]))
        self.assertEqual(report.decision, "blocked")
        self.assertEqual({finding.code for finding in report.findings}, {
            "missing_artifact_hints", "missing_business_object_id",
            "missing_candidate_visibility", "missing_field_values",
        })
        self.assertTrue(all(not finding.passed for finding in report.findings))

    def test_report_is_stable_for_a_frozen_bible(self):
        payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        bible = ScenarioBibleV1.model_validate(payload["bible"])
        first = EvidenceProjectionReadinessValidator().evaluate(bible)
        second = EvidenceProjectionReadinessValidator().evaluate(bible)
        self.assertEqual(first.bible_sha256, second.bible_sha256)
        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))


if __name__ == "__main__":
    unittest.main()
