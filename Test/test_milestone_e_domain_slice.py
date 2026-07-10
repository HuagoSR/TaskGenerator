from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_domain_profile import (  # noqa: E402
    DEFAULT_DOMAIN_PROFILE_PATH,
    domain_profile_sha256,
    load_domain_profile,
)
from task_generator.v3_end_to_end_pipeline import EndToEndPipeline, EndToEndRequest  # noqa: E402
from task_generator.v3_gdpval_contamination import (  # noqa: E402
    audit_generation,
    build_protected_index,
)
from task_generator.v3_pipeline_b_prototype import PipelineBPrototypeBuilder  # noqa: E402
from task_generator.v3_skill_extractor import MockSkillExtractor  # noqa: E402
from task_generator.v3_source_schema import SkillExtractionPromptPackage, load_json_file  # noqa: E402


class MilestoneEDomainSliceTests(unittest.TestCase):
    def test_profiles_are_frozen_and_warehouse_scope_is_bounded(self) -> None:
        finance = load_domain_profile("finance_audit")
        warehouse = load_domain_profile("warehouse_inventory")
        self.assertEqual(finance.domain_scope, "finance_audit")
        self.assertEqual(warehouse.allowed_output_file_types, ["xlsx", "docx"])
        self.assertEqual(
            warehouse.allowed_motifs,
            ["fan_in_reconciliation", "cross_check_validation", "policy_application"],
        )
        self.assertEqual(len(domain_profile_sha256(DEFAULT_DOMAIN_PROFILE_PATH)), 64)

    def test_request_freezes_domain_profile(self) -> None:
        request = EndToEndRequest(
            run_id="warehouse",
            selected_stages=["source_to_skills"],
            domain_profile="warehouse_inventory",
            motifs=["fan_in_reconciliation"],
        )
        pipeline = EndToEndPipeline(ROOT)
        self.assertNotEqual(
            pipeline._request_sha(request),
            pipeline._request_sha(request.model_copy(update={"domain_profile": "finance_audit"})),
        )

    def test_warehouse_mock_extractor_emits_four_domain_skills(self) -> None:
        source_dir = ROOT / "Test" / "v3_warehouse_inventory_source"
        with tempfile.TemporaryDirectory() as tmp:
            import subprocess

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "Test" / "run_v3_local_source_to_skill.py"),
                    "--input-dir",
                    str(source_dir),
                    "--output-dir",
                    tmp,
                    "--domain-tag",
                    "warehouse",
                    "--domain-tag",
                    "inventory",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            package = SkillExtractionPromptPackage.model_validate(
                load_json_file(str(Path(tmp) / "skill_extraction_prompt_package.json"))
            )
            candidates = MockSkillExtractor().extract(package, max_candidates=4)
        self.assertEqual(len(candidates), 4)
        self.assertTrue(all("warehouse" in candidate.domain_tags for candidate in candidates))
        self.assertIn("Reconcile Inbound Shipment Records", [candidate.proposed_name for candidate in candidates])

    def test_warehouse_profile_rewrites_finance_persona_and_files(self) -> None:
        report = PipelineBPrototypeBuilder().build_report(
            registry_path=ROOT / "SkillRegistry" / "v3_skill_registry.json",
            seed_report_path=ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json",
            motif="fan_in_reconciliation",
            skill_count=3,
            domain_profile=load_domain_profile("warehouse_inventory"),
        )
        blueprint = report["draft_task_blueprint"]
        rendered = json.dumps(blueprint, ensure_ascii=False).lower()
        self.assertIn("shipping, receiving, and inventory clerk", rendered)
        self.assertIn("warehouse_activity.xlsx", rendered)
        self.assertIn("expected_inventory.xlsx", rendered)
        for term in load_domain_profile("warehouse_inventory").forbidden_terms:
            self.assertNotIn(term, rendered)

    def test_contamination_exact_prompt_blocks_without_raw_prompt_in_ledger(self) -> None:
        rows = [
            {
                "task_id": "protected-task-1",
                "prompt": "Prepare an exact protected inventory analysis from the attached records.",
                "reference_file_hf_uris": ["hf://protected/file.xlsx"],
                "reference_file_urls": [],
                "reference_files": [],
            }
        ]
        protected = build_protected_index(rows)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "source_manifest.json"
            manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
            generated = root / "generated"
            generated.mkdir()
            (generated / "prompt.txt").write_text(rows[0]["prompt"], encoding="utf-8")
            ledger = audit_generation(manifest, generated, protected)
        self.assertEqual(ledger.decision, "blocked")
        self.assertIn("exact_gdpval_prompt_present", ledger.blocking_reasons)
        self.assertFalse(ledger.contains_raw_gdpval_content)
        self.assertNotIn(rows[0]["prompt"], ledger.model_dump_json())


if __name__ == "__main__":
    unittest.main()
