from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "Test"
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))
SPEC = importlib.util.spec_from_file_location("r10_world_first_runner", TEST_ROOT / "run_r10_world_first_pilot.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class WorldFirstRunnerTests(unittest.TestCase):
    def test_scope_is_exact_four_case_native_stack_campaign(self) -> None:
        inputs = RUNNER._load_inputs()
        scope = RUNNER._scope("r10_9_fixture", inputs)
        self.assertEqual(len(scope["cases"]), 4)
        self.assertEqual({item["variant"] for item in scope["cases"]}, {"baseline", "adversarial"})
        self.assertNotIn("gdpval", json.dumps(scope["authorized_uploads"]).casefold())
        self.assertIn("gdpval_content_generation_input", scope["excluded_actions"])
        self.assertEqual(scope["sol_model"], "gpt-5.6-sol")
        self.assertEqual(scope["deepseek_model"], "deepseek-v4-pro")

    def test_public_staging_has_no_historical_bible_or_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            RUNNER._stage_public_inputs(workspace, RUNNER._load_inputs()["audit_compliance"])
            names = {path.name for path in (workspace / "inputs").iterdir()}
            self.assertEqual(names, {"work_seed.json", "professional_rules.json", "current_skill.md", "source_map.md"})
            text = "\n".join(path.read_text(encoding="utf-8") for path in (workspace / "inputs").iterdir())
            self.assertNotIn("ScenarioBible", text)
            self.assertNotIn("GDPval", text)

    def test_world_validator_requires_candidate_coverage_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            candidate.mkdir(parents=True)
            workbook = Workbook()
            workbook.active["A1"] = "record"
            workbook.save(candidate / "records.xlsx")
            (candidate / "note.txt").write_text("Routine operating note", encoding="utf-8")
            teacher = root / "teacher"
            teacher.mkdir()
            (teacher / "world_ledger.md").write_text("World chronology and facts. " * 20, encoding="utf-8")
            (root / "world_manifest.json").write_text(json.dumps({
                "case_id": "case", "artifacts": [
                    {"path": "candidate/records.xlsx", "producer": "system", "system": "erp", "purpose": "record"},
                    {"path": "candidate/note.txt", "producer": "analyst", "system": "email", "purpose": "context"},
                    {"path": "teacher/world_ledger.md", "producer": "authority", "system": "factory", "purpose": "truth"},
                ],
                "cross_file_relationships": [
                    {"paths": ["candidate/records.xlsx", "candidate/note.txt"], "relationship": "timing"},
                    {"paths": ["candidate/note.txt", "candidate/records.xlsx"], "relationship": "scope"},
                ],
            }), encoding="utf-8")
            RUNNER._validate_world(root, case_id="case")

    def test_resume_refuses_any_started_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scope.json").write_text("{}", encoding="utf-8")
            self.assertEqual(RUNNER.status(root)["status"], "running_or_interrupted")

    def test_task_miner_workspace_paths_compile_to_candidate_relative_paths(self) -> None:
        self.assertEqual(
            RUNNER._candidate_relative_path("inputs/candidate/report.xlsx"),
            "report.xlsx",
        )
        self.assertEqual(
            RUNNER._candidate_relative_path("candidate/subdir/note.txt"),
            "subdir/note.txt",
        )

    def test_artifact_writer_serializes_lists_of_contract_models(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "models.json"
            seed = RUNNER._load_inputs()["audit_compliance"]["seed"]
            RUNNER._write(path, [seed])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["seed_id"], seed.seed_id)


if __name__ == "__main__":
    unittest.main()
