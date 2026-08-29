from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from task_generator.substrate.professional_skills import (
    CATALOG_VERSION,
    ENTRY_VERSION,
    ProfessionalSkillCatalogError,
    ProfessionalSkillCatalogV1,
    ProfessionalSkillLoader,
)


ROOT = Path(__file__).parents[2]
CATALOG_PATH = ROOT / "data" / "r10" / "professional_skills" / "catalog.json"
SKILLS_ROOT = ROOT / ".agents" / "skills" / "r10"
LEGACY_REGISTRY = ROOT / "SkillRegistry" / "v3_skill_registry.json"
LEGACY_REGISTRY_SHA256 = "7329e377fd3ef794c1bbbf089bb326bb8bd482a54939968c720cc3ef4a090fc7"


class ProfessionalSkillLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = ProfessionalSkillLoader()
        self.catalog = self.loader.load_catalog(CATALOG_PATH)

    def test_catalog_is_thin_and_has_two_draft_skills(self) -> None:
        self.assertEqual(self.catalog.contract_version, CATALOG_VERSION)
        self.assertEqual({entry.status for entry in self.catalog.entries}, {"curated"})
        self.assertEqual(
            {entry.skill_id for entry in self.catalog.entries},
            {"r10.audit-evidence-reliability", "r10.procurement-price-reasonableness"},
        )

    def test_domain_and_text_search_return_metadata_only(self) -> None:
        with patch.object(self.loader, "load_skill", side_effect=AssertionError):
            audit = self.loader.search(
                self.catalog,
                query="audit evidence reliability",
                domain="audit_compliance",
            )
        self.assertEqual([entry.name for entry in audit], ["audit-evidence-reliability"])
        self.assertEqual(
            self.loader.search(
                self.catalog,
                query="tax withholding",
                domain="audit_compliance",
            ),
            [],
        )
        self.assertEqual(
            self.loader.search(
                self.catalog,
                query="price reasonableness",
                domain="audit_compliance",
            ),
            [],
        )

    def test_selected_skill_loads_body_and_source_map(self) -> None:
        entry = self.loader.search(
            self.catalog,
            query="company-produced information",
            domain="audit_compliance",
        )[0]
        loaded = self.loader.load_skill(entry, skills_root=SKILLS_ROOT)
        self.assertIn("# Audit evidence reliability", loaded.skill_markdown)
        self.assertIn("references/source-map.md", loaded.reference_markdown)

    def test_catalog_rejects_duplicate_id_and_path(self) -> None:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        payload["entries"].append(dict(payload["entries"][0]))
        with self.assertRaises(ValidationError):
            ProfessionalSkillCatalogV1.model_validate(payload)

        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        payload["entries"][1]["relative_path"] = payload["entries"][0]["relative_path"]
        with self.assertRaises(ValidationError):
            ProfessionalSkillCatalogV1.model_validate(payload)

    def test_loader_rejects_escape_missing_file_and_frontmatter_mismatch(self) -> None:
        entry = self.catalog.entries[0].model_copy(update={"relative_path": "../escape"})
        with self.assertRaises(ProfessionalSkillCatalogError):
            self.loader.load_skill(entry, skills_root=SKILLS_ROOT)

        missing = self.catalog.entries[0].model_copy(update={"relative_path": "missing"})
        with self.assertRaises(ProfessionalSkillCatalogError):
            self.loader.load_skill(missing, skills_root=SKILLS_ROOT)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "audit-evidence-reliability"
            package.mkdir()
            (package / "SKILL.md").write_text(
                "---\nname: wrong-name\ndescription: wrong\n---\n# Wrong\n", encoding="utf-8"
            )
            with self.assertRaises(ProfessionalSkillCatalogError):
                self.loader.load_skill(self.catalog.entries[0], skills_root=root)

    def test_search_limit_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            self.loader.search(self.catalog, limit=0)
        with self.assertRaises(ValueError):
            self.loader.search(self.catalog, limit=5)

    def test_legacy_registry_remains_unchanged(self) -> None:
        digest = hashlib.sha256(LEGACY_REGISTRY.read_bytes()).hexdigest()
        self.assertEqual(digest, LEGACY_REGISTRY_SHA256)

    def test_stage_one_loader_has_no_provider_client_dependency(self) -> None:
        source = (ROOT / "src" / "task_generator" / "substrate" / "professional_skills.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests", source.lower())
        self.assertEqual(ENTRY_VERSION, "r10.professional_skill_catalog_entry.1")

    def test_curated_skills_do_not_contain_bible_answers_or_organizations(self) -> None:
        for entry in self.catalog.entries:
            loaded = self.loader.load_skill(entry, skills_root=SKILLS_ROOT)
            text = loaded.skill_markdown.lower()
            self.assertNotIn("correct treatment", text)
            self.assertNotIn("heliotrack", text)
            self.assertNotIn("harborview", text)


if __name__ == "__main__":
    unittest.main()
