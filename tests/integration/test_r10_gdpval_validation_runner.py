from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_gdpval_validation", ROOT / "Test" / "run_r10_gdpval_validation.py"
)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(runner)

from task_generator.evaluation.r10_gdpval_validation import GDPvalRubricItemV1, GDPvalTaskBindingV1


def binding() -> GDPvalTaskBindingV1:
    return GDPvalTaskBindingV1(
        task_id="public-task", sector="Government", occupation="Compliance Officers",
        split="development", prompt_sha256="a" * 64, reference_tree_sha256="b" * 64,
        gold_tree_sha256="c" * 64, reference_files=[],
        expected_deliverables=["result.xlsx", "memo.docx"],
        rubric_items=[GDPvalRubricItemV1(
            rubric_item_id="r1", score=2, criterion="Contains the required conclusion"
        )],
    )


class GDPvalRunnerTests(unittest.TestCase):
    def test_solver_configuration_is_frozen(self):
        self.assertEqual(runner.SOLVERS["gpt-5.6-sol@chatgpt_codex"]["reasoning"], "none")
        self.assertEqual(runner.SOLVERS["deepseek-v4-pro@official_opencode"]["variant"], "max")
        self.assertEqual(runner.SOLVERS["deepseek-v4-flash@official_opencode"]["variant"], "high")
        self.assertEqual(runner.LUNA["gpt-5.6-luna@chatgpt_codex"]["reasoning"], "medium")

    def test_stage_pair_is_anonymous_and_keeps_human_rubric(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data, run, target = root / "data", root / "run", root / "target"
            task = data / "tasks" / "public-task"
            (task / "reference_files").mkdir(parents=True)
            (task / "human_gold").mkdir()
            (task / "prompt.txt").write_text("Public task prompt", encoding="utf-8")
            (task / "human_gold" / "gold.txt").write_text("gold", encoding="utf-8")
            for solver in ("model-a", "model-b"):
                delivery = run / "solvers" / solver / "public-task" / "workspace" / "deliverable_files"
                delivery.mkdir(parents=True)
                (delivery / f"{solver}.txt").write_text(solver, encoding="utf-8")
            runner._stage_pair(
                target=target, data_root=data, run_root=run, binding=binding(),
                candidate_a="model-a", candidate_b="model-b", order="a_b",
                pair_id="pair", judge_id=runner.PRIMARY_JUDGE,
            )
            task_text = (target / "TASK.md").read_text(encoding="utf-8")
            self.assertNotIn("model-a", task_text)
            self.assertNotIn("model-b", task_text)
            rubric = json.loads((target / "human_rubric.json").read_text(encoding="utf-8"))
            self.assertEqual(rubric[0]["rubric_item_id"], "r1")

    def test_delivery_validation_opens_xlsx_and_docx(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, task = root / "workspace", root / "task"
            (workspace / "deliverable_files").mkdir(parents=True)
            (task / "reference_files").mkdir(parents=True)
            workbook = Workbook()
            workbook.active["A1"] = "content"
            workbook.save(workspace / "deliverable_files" / "result.xlsx")
            with zipfile.ZipFile(workspace / "deliverable_files" / "memo.docx", "w") as archive:
                archive.writestr("word/document.xml", "<document>memo</document>")
            (workspace / "docx_office_opened.txt").write_text(
                "deliverable_files/memo.docx\n", encoding="utf-8"
            )
            result = runner._validate_delivery(workspace, binding(), task)
            self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
