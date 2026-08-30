from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "Test"))

from run_r10_skill_review_ab import _copy_base, _review_prompt
from task_generator.substrate.professional_skills import LoadedProfessionalSkillV1, ProfessionalSkillCatalogEntryV1


class SkillReviewABRunnerTests(unittest.TestCase):
    def _skill(self) -> LoadedProfessionalSkillV1:
        entry = ProfessionalSkillCatalogEntryV1(contract_version="r10.professional_skill_catalog_entry.1", skill_id="r10.audit", name="audit", description="Audit scenario review.", domain="audit_compliance", relative_path="audit", version="0.2.0", status="curated")
        return LoadedProfessionalSkillV1(entry=entry, skill_markdown="---\nname: audit\ndescription: Audit scenario review.\n---\n# Audit\n", reference_markdown={"references/source-map.md": "[PCAOB](https://pcaobus.org/x)"})

    def test_common_base_is_copied_before_only_skill_side_differs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            (base / "candidate").mkdir(parents=True)
            (base / "teacher").mkdir()
            (base / "candidate" / "record.txt").write_text("source record", encoding="utf-8")
            (base / "teacher" / "scenario_extension.json").write_text('{"facts":[]}', encoding="utf-8")
            (base / "teacher" / "evidence_map.json").write_text('{"artifacts":[]}', encoding="utf-8")
            plain, skilled = root / "plain", root / "skilled"
            _copy_base(base=base, destination=plain, skill=self._skill(), with_skill=False)
            _copy_base(base=base, destination=skilled, skill=self._skill(), with_skill=True)
            self.assertEqual((plain / "candidate" / "record.txt").read_bytes(), (skilled / "candidate" / "record.txt").read_bytes())
            self.assertFalse((plain / "teacher" / "professional_skill").exists())
            self.assertTrue((skilled / "teacher" / "professional_skill" / "SKILL.md").is_file())
            self.assertNotIn("professional_skill", _review_prompt(with_skill=False))
            self.assertIn("professional_skill", _review_prompt(with_skill=True))


if __name__ == "__main__":
    unittest.main()
