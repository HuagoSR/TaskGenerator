from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.substrate.professional_skill_curation import (
    OfficialDeepSeekProfessionalSkillCurator,
    ProfessionalSkillCurationSourcesV1,
)
from task_generator.substrate.professional_skills import ProfessionalSkillLoader


ROOT = Path(__file__).parents[2]


class ProfessionalSkillCurationTests(unittest.TestCase):
    def setUp(self) -> None:
        loader = ProfessionalSkillLoader()
        self.catalog = loader.load_catalog(ROOT / "data/r10/professional_skills/catalog.json")
        self.sources = ProfessionalSkillCurationSourcesV1.model_validate_json(
            (ROOT / "data/r10/professional_skills/curation_sources.json").read_text(encoding="utf-8")
        )

    def test_source_mix_has_rule_practice_and_failure_mode_per_skill(self) -> None:
        for entry in self.catalog.entries:
            kinds = {item.evidence_kind for item in self.sources.sources if item.skill_id == entry.skill_id}
            self.assertEqual(kinds, {"rule", "practice", "failure_mode"})

    def test_successful_single_batch_is_source_bound(self) -> None:
        def executor(body, api_key, timeout):
            self.assertEqual(body["model"], "deepseek-v4-pro")
            self.assertNotIn(api_key, json.dumps(body))
            return 200, {"choices": [{"message": {"content": json.dumps({"skills": [
                {"skill_id": "r10.audit-evidence-reliability", "instructions": [
                    {"text": "Assess whether company-produced information has evidence of accuracy and completeness before relying on it.", "source_ids": ["audit_as1105_reliability"]},
                    {"text": "Represent the source population or inspected items so a reviewable workpaper can trace what was examined.", "source_ids": ["audit_as1215_workpaper"]},
                    {"text": "Do not let selectively favourable monitoring evidence stand in for a complete effectiveness picture.", "source_ids": ["audit_pcaob_remediation_monitoring"]}], "trigger_examples": ["An audit senior receives conflicting internal reports."], "exclusions": ["Generic spreadsheet formatting."]},
                {"skill_id": "r10.procurement-price-reasonableness", "instructions": [
                    {"text": "Document the basis for price reasonableness before award, including the support available when only one response is responsive.", "source_ids": ["procurement_far_13_106_3"]},
                    {"text": "Make comparability and data adequacy affect the choice of price-analysis method.", "source_ids": ["procurement_far_15_404_1_methods"]},
                    {"text": "When the record is insufficient, request or escalate for needed support instead of treating a thin record as adequate.", "source_ids": ["procurement_dfars_pgi_insufficient_data"]}], "trigger_examples": ["A contract specialist prepares a pre-award file."], "exclusions": ["Generic vendor sorting."]}
            ]})}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        with tempfile.TemporaryDirectory() as directory:
            curated_catalog = self.catalog.model_copy(update={"entries": [entry for entry in self.catalog.entries if entry.skill_id in {"r10.audit-evidence-reliability", "r10.procurement-price-reasonableness"}]})
            report, drafts = OfficialDeepSeekProfessionalSkillCurator(executor).curate(catalog=curated_catalog, sources=self.sources, api_key="secret", output_root=Path(directory) / "result")
        self.assertEqual(report.decision, "pass")
        self.assertEqual(len(drafts), 2)

    def test_invalid_json_gets_only_one_format_retry_then_incomplete(self) -> None:
        calls = 0
        def executor(body, api_key, timeout):
            nonlocal calls
            calls += 1
            return 200, {"choices": [{"message": {"content": "not json"}}]}
        with tempfile.TemporaryDirectory() as directory:
            report, drafts = OfficialDeepSeekProfessionalSkillCurator(executor).curate(catalog=self.catalog, sources=self.sources, api_key="secret", output_root=Path(directory) / "result")
        self.assertEqual(calls, 2)
        self.assertEqual(report.decision, "incomplete")
        self.assertEqual(drafts, [])

    def test_unknown_instruction_source_blocks_without_retry(self) -> None:
        def executor(body, api_key, timeout):
            bad = {"skills": [{"skill_id": entry.skill_id, "instructions": [{"text": "This instruction is long enough to satisfy the schema and cites an unknown source.", "source_ids": ["unknown"]}] * 3, "trigger_examples": ["example"], "exclusions": ["exclude"]} for entry in self.catalog.entries]}
            return 200, {"choices": [{"message": {"content": json.dumps(bad)}}]}
        with tempfile.TemporaryDirectory() as directory:
            report, _ = OfficialDeepSeekProfessionalSkillCurator(executor).curate(catalog=self.catalog, sources=self.sources, api_key="secret", output_root=Path(directory) / "result")
        self.assertEqual(report.decision, "blocked")
        self.assertEqual(report.provider_call_count, 1)

    def test_nonretryable_http_failure_is_recorded_once(self) -> None:
        calls = 0
        def executor(body, api_key, timeout):
            nonlocal calls
            calls += 1
            return 401, {}
        with tempfile.TemporaryDirectory() as directory:
            report, _ = OfficialDeepSeekProfessionalSkillCurator(executor).curate(catalog=self.catalog, sources=self.sources, api_key="secret", output_root=Path(directory) / "result")
        self.assertEqual(calls, 1)
        self.assertEqual(report.provider_call_count, 1)
        self.assertEqual(report.provider_retry_count, 0)


if __name__ == "__main__":
    unittest.main()
