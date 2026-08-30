from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.substrate.professional_skill_compiler import OfficialDeepSeekSkillContentReviewer, admit_compiled_skill
from task_generator.substrate.professional_skills import ProfessionalSkillCatalogEntryV1


class ProfessionalSkillCompilerTests(unittest.TestCase):
    def _entry(self) -> ProfessionalSkillCatalogEntryV1:
        return ProfessionalSkillCatalogEntryV1(contract_version="r10.professional_skill_catalog_entry.1", skill_id="r10.audit", name="audit-skill", description="Review audit evidence situations.", domain="audit_compliance", relative_path="audit", version="0.2.0", status="curated")

    def _package(self, root: Path, *, source_map: str | None = None) -> Path:
        package = root / "audit"
        (package / "references").mkdir(parents=True)
        (package / "SKILL.md").write_text("---\nname: audit-skill\ndescription: Review audit evidence situations.\n---\n\n# Audit\n\nPreserve source-system ownership and leave reliability conclusions for the worker.\n", encoding="utf-8")
        (package / "references" / "source-map.md").write_text(source_map or "[PCAOB](https://pcaobus.org/oversight/standards/auditing-standards/details/AS1105)\n", encoding="utf-8")
        return package

    def test_admission_accepts_compact_source_grounded_package(self):
        with tempfile.TemporaryDirectory() as directory:
            package = self._package(Path(directory))
            self.assertEqual(admit_compiled_skill(entry=self._entry(), package_root=package, forbidden_terms={"HelioTrack", "correct treatment"}), [])

    def test_admission_blocks_private_content_or_unapproved_source_host(self):
        with tempfile.TemporaryDirectory() as directory:
            package = self._package(Path(directory), source_map="[bad](https://example.com/x) HelioTrack")
            errors = admit_compiled_skill(entry=self._entry(), package_root=package, forbidden_terms={"HelioTrack", "correct treatment"})
            self.assertIn("compiled_skill_source_host_not_allowed", errors)
            self.assertIn("compiled_skill_contains_private_or_answer_content", errors)

    def test_independent_reviewer_never_rewrites_skill(self):
        def executor(body, api_key, timeout):
            self.assertNotIn(api_key, json.dumps(body))
            return 200, {"choices": [{"message": {"content": json.dumps({"decision": "pass", "supported_source_ids": ["as1105"], "issues": []})}}]}
        with tempfile.TemporaryDirectory() as directory:
            package = self._package(Path(directory))
            review = OfficialDeepSeekSkillContentReviewer(executor).review(entry=self._entry(), package_root=package, api_key="secret")
        self.assertEqual(review.decision, "pass")
        self.assertEqual(review.supported_source_ids, ["as1105"])


if __name__ == "__main__":
    unittest.main()
