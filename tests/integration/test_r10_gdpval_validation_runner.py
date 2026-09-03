from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

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
                pair_id="model-a_vs_model-b", judge_id=runner.PRIMARY_JUDGE,
            )
            task_text = (target / "TASK.md").read_text(encoding="utf-8")
            self.assertNotIn("model-a", task_text)
            self.assertNotIn("model-b", task_text)
            self.assertNotIn(runner.PRIMARY_JUDGE, task_text)
            schema = json.loads((target / "grade_schema.json").read_text(encoding="utf-8"))
            self.assertFalse({"judge_id", "pair_id", "order_id", "task_id"} & set(schema["properties"]))
            self.assertNotIn("deepseek", json.dumps(schema))
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

    @staticmethod
    def raw_review(rating="met"):
        return {"review_version": "r10.gdpval_pair_review.1", "preference": "tie", "bundles": [
            {"slot": slot, "assessments": [{"rubric_item_id": "r1", "rating": rating,
                "evidence_paths": ["anonymous_slot_1/result.xlsx"], "rationale": "Visible required content."}]}
            for slot in ("slot_1", "slot_2")]}

    def test_parser_supplies_metadata_and_rejects_duplicate_or_missing_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            raw = self.raw_review()
            def parse(value):
                (workspace / "grade.raw.json").write_text(json.dumps(value), encoding="utf-8")
                return runner._parse_pair(workspace, runner.PRIMARY_JUDGE, "", binding=binding(), pair_id="opaque", order="b_a")
            review = parse(raw)
            self.assertEqual(review.order_id, "b_a")
            with self.assertRaises(ValueError):
                parse({**raw, "judge_id": runner.PRIMARY_JUDGE})
            raw["bundles"][0]["assessments"].append(raw["bundles"][0]["assessments"][0])
            with self.assertRaises(ValueError):
                parse(raw)
            raw = self.raw_review()
            raw["bundles"][0]["assessments"][0]["rubric_item_id"] = "wrong"
            with self.assertRaises(ValueError):
                parse(raw)

    def test_sentinels_cover_occupations_and_splits_not_first_pairs(self):
        candidates = []
        for occupation in ("Accountants and Auditors", "Buyers and Purchasing Agents", "Compliance Officers"):
            for split in ("development", "holdout"):
                for pair in range(3):
                    b = binding().model_copy(update={"occupation": occupation, "split": split, "task_id": f"{occupation}-{split}"})
                    candidates.append((b, "a", "b", str(pair), "a_b", {"preference": "a"}))
        selected = runner._select_sentinels(candidates)
        self.assertEqual(len(selected), 6)
        self.assertEqual(len({(row[0].occupation, row[0].split) for row in selected}), 6)
        self.assertEqual(selected, runner._select_sentinels(list(reversed(candidates))))

    def test_format_failure_gets_one_retry_but_low_score_does_not(self):
        for malformed_first, expected in ((False, 1), (True, 2)):
            with self.subTest(malformed_first=malformed_first), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                def stage(**kwargs):
                    kwargs["target"].mkdir(parents=True)
                    (kwargs["target"] / "TASK.md").write_text("frozen", encoding="utf-8")
                calls = []
                def execute(**kwargs):
                    calls.append(kwargs)
                    workspace = kwargs["local"]
                    (workspace / "agent.jsonl").write_text('{"type":"turn.completed"}\n', encoding="utf-8")
                    value = "invalid" if malformed_first and len(calls) == 1 else json.dumps(self.raw_review("not_met"))
                    (workspace / "grade.raw.json").write_text(value, encoding="utf-8")
                    return 0, "", ""
                with patch.object(runner, "_stage_pair", side_effect=stage), patch.object(runner, "_run_remote", side_effect=execute):
                    review = runner._run_pair(host="unused", remote_root="/unused", data_root=root,
                        run_root=root, binding=binding(), candidate_a="model-a", candidate_b="model-b",
                        pair_id="opaque", order="a_b", judge_id=runner.PRIMARY_JUDGE)
                    self.assertEqual(len(calls), expected)
                    self.assertEqual(runner.score_gdpval_bundle(binding(), review.bundles[0]), 0)
                    self.assertNotIn("model-a", calls[0]["remote"])
                    runner._run_pair(host="unused", remote_root="/unused", data_root=root,
                        run_root=root, binding=binding(), candidate_a="model-a", candidate_b="model-b",
                        pair_id="opaque", order="a_b", judge_id=runner.PRIMARY_JUDGE)
                    self.assertEqual(len(calls), expected)
                if malformed_first:
                    failures = list(root.glob("judges/*/attempt_1/failure.json"))
                    self.assertEqual(len(failures), 1)

    def test_nonterminal_agent_is_not_redrawn(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def stage(**kwargs):
                kwargs["target"].mkdir(parents=True)
            with patch.object(runner, "_stage_pair", side_effect=stage), patch.object(runner, "_run_remote", return_value=(124, "", "timeout")) as call:
                with self.assertRaises(RuntimeError):
                    runner._run_pair(host="unused", remote_root="/unused", data_root=root,
                        run_root=root, binding=binding(), candidate_a="a", candidate_b="b",
                        pair_id="opaque", order="a_b", judge_id=runner.PRIMARY_JUDGE)
                self.assertEqual(call.call_count, 1)

    def test_recovery_only_imports_terminal_output_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            solver = next(iter(runner.SOLVERS))
            root = run / "solvers" / solver / "public-task"
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "TASK.md").write_text("frozen", encoding="utf-8")
            runner._write(root / "state.json", {"status": "running", "input_sha256": runner.tree_sha256(workspace)})
            (workspace / ".r10_agent.sh").write_text("temporary control script", encoding="utf-8")
            returned = root / "returned"
            (returned / "deliverable_files").mkdir(parents=True)
            (returned / "deliverable_files" / "result.xlsx").write_bytes(b"fixture")
            (returned / "agent.jsonl").write_text('{"type":"turn.completed"}\n', encoding="utf-8")
            with patch.object(runner, "_bindings", return_value=[binding()]), patch.object(runner, "_task_root", return_value=run), patch.object(runner, "_validate_delivery", return_value={"valid": True}), patch.object(runner, "_run_remote") as provider:
                state = runner.recover_solver(run, run, solver, "public-task", returned)
                self.assertTrue(state["recovered_without_provider_call"])
                self.assertIsNone(state["returncode"])
                provider.assert_not_called()
                with self.assertRaises(ValueError):
                    runner.recover_solver(run, run, solver, "public-task", returned)

    def test_judge_only_scope_binds_solver_receipt_and_deliveries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            solver = next(iter(runner.SOLVERS))
            path = root / "solvers" / solver / "public-task"
            delivery = path / "workspace" / "deliverable_files"
            delivery.mkdir(parents=True)
            (delivery / "result.xlsx").write_bytes(b"unchanged delivery")
            state = {"status": "completed", "output_tree_sha256": runner.tree_sha256(delivery)}
            runner._write(path / "state.json", state)
            runner._write(root / "solver_result.json", {"results": {solver: {"public-task": state}}})
            parent = {"task_binding_sha256": {}, "dataset_manifest_sha256": "a" * 64,
                      "image_sha256": "b" * 64, "solvers": runner.SOLVERS}
            runner._write(root / "scope.json", parent)
            runner._write(root / "receipt.json", {"scope_sha256": runner.canonical_sha256(parent)})
            with patch.object(runner, "_scope", return_value=dict(parent)), patch.object(runner, "_verify_public_files"):
                scope = runner._judge_scope("new", root, [binding()], root)
                self.assertEqual(scope["solver_scope_sha256"], runner.canonical_sha256(parent))
                (delivery / "result.xlsx").write_bytes(b"changed delivery")
                with self.assertRaisesRegex(ValueError, "delivery_drift"):
                    runner._judge_scope("new", root, [binding()], root)

    def test_position_and_judge_rates_are_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = list(runner.SOLVERS)
            runner._write(root / "solver_result.json", {"valid_counts": {model: 12 for model in models}})
            runner._write(root / "judge_result.json", {"eligible_solvers": models, "pair_results": [],
                "sentinel_results": [{"position_consistent": False, "judge_agrees_with_primary": True}
                                     for _ in range(6)]})
            runner._write(root / "ranking_snapshot.json", {
                "source_url": "https://example.test", "captured_at": "2026-09-03T00:00:00Z",
                "reference_order": models, "scores": dict(zip(models, [3, 2, 1]))})
            with patch.object(runner, "bootstrap_model_order", return_value={"observed_order": models}):
                report = runner.aggregate(root, root)
            self.assertEqual(report["sentinel_position_consistency"], 0)
            self.assertEqual(report["judge_direction_consistency"], 1)
            self.assertEqual(report["decision"], "gdpval_protocol_partial")


if __name__ == "__main__":
    unittest.main()
