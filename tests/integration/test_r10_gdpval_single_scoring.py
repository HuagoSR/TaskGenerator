from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_r10_gdpval_validation_runner import runner, binding
from task_generator.evaluation.r10_gdpval_validation import (
    GDPvalSingleReviewV1, GDPvalMaterialIncomplete, score_gdpval_single, summarize_single_scores,
)


def raw(awarded=2, applicability="applicable"):
    return {"review_version": "r10.gdpval_single_review.1", "material_status": "complete", "material_notes": "Read all materials.",
            "assessments": [{"rubric_item_id": "r1", "awarded": awarded, "applicability": applicability,
                             "evidence_paths": ["anonymous_submission/report.txt"], "rationale": "Specific supporting content."}]}


class SingleScoringTests(unittest.TestCase):
    def test_integer_scoring_and_bounds(self):
        for awarded, score in [(0, 0), (1, .5), (2, 1)]:
            self.assertEqual(score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate(raw(awarded))), score)
        for awarded in [-1, 3, 1.5, True, "2"]:
            with self.assertRaises(ValueError):
                score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate(raw(awarded)))
        for changed in [{**raw(), "preference": "slot_1"}, {**raw(), "total_score": 2},
                        {**raw(), "assessments": raw()["assessments"] * 2}, {**raw(), "assessments": []}]:
            with self.assertRaises(ValueError):
                GDPvalSingleReviewV1.model_validate(changed)
        value = raw(); value["assessments"][0]["rubric_item_id"] = "unknown"
        with self.assertRaises(ValueError):
            score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate(value))

    def test_conditional_policy(self):
        self.assertEqual(score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate(raw(2, "not_triggered"))), 1)
        with self.assertRaises(ValueError):
            score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate(raw(1, "not_triggered")))
        with self.assertRaises(GDPvalMaterialIncomplete):
            score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate(raw(0, "unresolved")))
        with self.assertRaises(GDPvalMaterialIncomplete):
            score_gdpval_single(binding(), GDPvalSingleReviewV1.model_validate({**raw(), "material_status": "incomplete"}))

    def test_fixed_nine_plus_three_and_primary_means(self):
        assignments = runner._single_assignments()
        self.assertEqual(len(assignments), 12)
        self.assertEqual(len({x["assignment_id"] for x in assignments}), 12)
        self.assertTrue(all(x["task_id"] == runner.SINGLE_TASKS[0] for x in assignments[:3]))
        self.assertEqual([x["solver_id"] for x in assignments[9:]], list(runner.SOLVERS))
        self.assertTrue(all(x["judge_id"] == runner.SECONDARY_JUDGE for x in assignments[:9]))
        rows = [{**a, "score": .8 if a["role"] == "primary" else 0} for a in assignments]
        report = summarize_single_scores(rows, assignments)
        self.assertEqual(report["status"], "preliminary_scoring_complete")
        self.assertEqual(set(report["primary_means"].values()), {.8})
        self.assertTrue(all(x["interpretation"] == "difference_unclear" for x in report["comparisons"]))
        self.assertEqual(summarize_single_scores(rows[:1], assignments)["primary_means"], {})
        with self.assertRaises(ValueError):
            summarize_single_scores(rows + rows[:1], assignments)

    def test_single_staging_is_anonymous_and_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, run, target = root / "data", root / "run", root / "target"
            task = data / "tasks/public-task"
            (task / "reference_files").mkdir(parents=True)
            (task / "prompt.txt").write_text("Public prompt")
            delivery = run / "solvers/hidden-model/public-task/workspace/deliverable_files"
            delivery.mkdir(parents=True); (delivery / "report.txt").write_text("Required conclusion")
            runner._stage_single(target, data, run, binding(), "hidden-model")
            self.assertFalse((target / "human_gold").exists())
            self.assertFalse((target / "anonymous_slot_2").exists())
            text = (target / "TASK.md").read_text(encoding="utf-8")
            self.assertNotIn("hidden-model", text)
            self.assertIn("not_triggered", text)
            self.assertIn("separate directory", text)
            (target / "grade.raw.json").write_text(json.dumps(raw()))
            runner._parse_single(target, binding(), runner.PRIMARY_JUDGE)
            for name in ["../secret.txt", "human_rubric.json", "anonymous_submission/missing.txt", "C:/secret", "anonymous_submission/../TASK.md"]:
                value = raw(); value["assessments"][0]["evidence_paths"] = [name]
                (target / "grade.raw.json").write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    runner._parse_single(target, binding(), runner.PRIMARY_JUDGE)

    def test_jsonl_unicode_separators_are_not_record_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "anonymous_submission").mkdir()
            (root / "anonymous_submission/report.txt").write_text("Conclusion")
            rows = [{"type": "tool_use", "part": {"output": "PDF text\u2028next line\u0085more"}},
                    {"type": "text", "part": {"text": json.dumps(raw())}},
                    {"type": "step_finish", "part": {"reason": "stop"}}]
            path = root / "agent.jsonl"
            path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
            self.assertTrue(runner._agent_completed(root, runner.DEEPSEEK_OPENCODE_STACK))
            self.assertEqual(runner._parse_single(root, binding(), runner.SECONDARY_JUDGE).material_status, "complete")
            path.write_text('{"type":\ninvalid}\n', encoding="utf-8")
            self.assertFalse(runner._agent_completed(root, runner.DEEPSEEK_OPENCODE_STACK))

    def test_budget_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(2):
                runner._write(root / f"singles/s{index}/state.json", {"attempt": 2})
            runner._single_budget(root, retry=False)
            with self.assertRaises(RuntimeError):
                runner._single_budget(root, retry=True)
            for index in range(2, 12):
                runner._write(root / f"singles/s{index}/state.json", {"attempt": 1})
            with self.assertRaises(RuntimeError):
                runner._single_budget(root, retry=False)

    def test_reference_normalization_preserves_scores_and_rationale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "anonymous_submission").mkdir()
            (root / "anonymous_submission/report.txt").write_text("Conclusion")
            value = raw(1)
            value["assessments"][0]["evidence_paths"] = ["/workspace/anonymous_submission/report.txt (page 1)",
                "/tmp/opencode/pdf/report.pdf (rendered layout); /workspace/anonymous_submission/report.txt (title)"]
            review = GDPvalSingleReviewV1.model_validate(value)
            result, changes = runner._normalize_single_references(root, review)
            self.assertEqual(result.assessments[0].awarded, 1)
            self.assertEqual(result.assessments[0].rationale, review.assessments[0].rationale)
            self.assertEqual(result.assessments[0].evidence_paths, ["anonymous_submission/report.txt"])
            self.assertEqual(len(changes), 2)
            for bad in ["/workspace/../anonymous_submission/report.txt", "/workspace/anonymous_submission/report.txt.evil",
                        "/tmp/opencode/pdf/report.pdf (rendered layout)",
                        "/tmp/opencode/pdf/other.pdf (rendered layout); /workspace/anonymous_submission/report.txt"]:
                value["assessments"][0]["evidence_paths"] = [bad]
                with self.assertRaises(ValueError):
                    runner._normalize_single_references(root, GDPvalSingleReviewV1.model_validate(value))

    def test_explicit_canary_recovery_is_offline_and_counts_original_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); parent, new, data = root / "parent", root / "new", root / "data"
            spec = runner._single_assignments()[0]
            source = parent / "singles" / spec["assignment_id"]
            workspace = source / "attempt_1/workspace"
            (workspace / "anonymous_submission").mkdir(parents=True)
            (workspace / "anonymous_submission/report.txt").write_text("Conclusion")
            (workspace / "reference_files").mkdir()
            (workspace / "candidate_task.md").write_text("Public prompt")
            (workspace / "grade.raw.json").write_text(json.dumps(raw(1)))
            (workspace / "agent.jsonl").write_text('{"type":"step_finish","part":{"reason":"stop"}}\n')
            b = binding().model_copy(update={"task_id": spec["task_id"], "reference_tree_sha256": runner.tree_sha256(workspace / "reference_files")})
            runner._write(workspace / "human_rubric.json", [r.model_dump(mode="json") for r in b.rubric_items])
            task = data / "tasks" / b.task_id; task.mkdir(parents=True)
            (task / "prompt.txt").write_text("Public prompt")
            runner._write(source / "state.json", {"status":"incomplete", "attempt":1, "first_failure":"parser"})
            scope = {"scope_version":"r10.gdpval_single_scope.1", "protocol":"fixture", "image_sha256":"a"*64,
                "judges":runner.JUDGES, "assignments":runner._single_assignments(),
                "task_binding_sha256":{b.task_id:b.canonical_sha256()},
                "solver_output_sha256":{f"{spec['solver_id']}/{b.task_id}":runner.tree_sha256(workspace / "anonymous_submission")}}
            runner._write(parent / "scope.json", scope)
            runner._write(parent / "receipt.json", {"scope_sha256":runner.canonical_sha256(scope)})
            original = runner.tree_sha256(parent)
            scope["recovery"] = runner._single_recovery_source(parent, scope)
            with patch.object(runner, "_bindings", return_value=[b]), patch.object(runner, "_run_remote") as provider:
                runner._import_single_canary(parent, data, new, scope)
                runner._import_single_canary(parent, data, new, scope)
                provider.assert_not_called()
            state = runner._state(new / "singles" / spec["assignment_id"])
            self.assertEqual((state["status"], state["attempt"]), ("completed",1))
            self.assertEqual(runner.tree_sha256(parent), original)
            with self.assertRaises(ValueError):
                runner._single_recovery_source(parent, {**scope,"image_sha256":"b"*64})
            (workspace / "agent.jsonl").write_text('{"type":"step_start"}\n')
            with self.assertRaises(ValueError):
                runner._single_recovery_source(parent, scope)

    def exercise(self, responses):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); spec = {"assignment_id": "single_fixture", "task_id": "public-task",
                                     "solver_id": "hidden-model", "judge_id": runner.PRIMARY_JUDGE, "role": "primary"}
        calls = []
        def stage(target, *args):
            target.mkdir(parents=True); (target / "anonymous_submission").mkdir()
            (target / "anonymous_submission/report.txt").write_text("Conclusion")
        def execute(**kwargs):
            calls.append(kwargs)
            value = responses[min(len(calls) - 1, len(responses) - 1)]
            path = kwargs["local"]
            (path / "agent.jsonl").write_text('{"type":"turn.completed"}\n')
            (path / "grade.raw.json").write_text(value)
            return 0, "", ""
        return root, spec, calls, stage, execute

    def test_one_format_retry_then_reuse_and_no_low_score_redraw(self):
        root, spec, calls, stage, execute = self.exercise(["bad json", json.dumps(raw(0))])
        with patch.object(runner, "_stage_single", side_effect=stage), patch.object(runner, "_run_remote", side_effect=execute):
            result = runner._run_single("fixture", root, root, "run", binding(), spec)
            self.assertEqual(result["score"], 0)
            self.assertEqual(len(calls), 2)
            self.assertIsNotNone(runner._state(root / "singles/single_fixture")["first_failure"])
            self.assertEqual(runner._run_single("fixture", root, root, "run", binding(), spec), result)
            self.assertEqual(len(calls), 2)

    def test_material_failure_and_nonterminal_do_not_retry(self):
        root, spec, calls, stage, execute = self.exercise([json.dumps(raw(0, "unresolved"))])
        with patch.object(runner, "_stage_single", side_effect=stage), patch.object(runner, "_run_remote", side_effect=execute):
            with self.assertRaises(RuntimeError):
                runner._run_single("fixture", root, root, "run", binding(), spec)
            self.assertEqual(len(calls), 1)
            with self.assertRaises(RuntimeError):
                runner._run_single("fixture", root, root, "run", binding(), spec)
            self.assertEqual(len(calls), 1)
        root, spec, calls, stage, execute = self.exercise([json.dumps(raw())])
        with patch.object(runner, "_stage_single", side_effect=stage), patch.object(runner, "_run_remote", side_effect=execute), patch.object(runner, "_agent_completed", return_value=False):
            with self.assertRaises(RuntimeError):
                runner._run_single("fixture", root, root, "run", binding(), spec)
            self.assertEqual(len(calls), 1)

    def test_two_format_failures_and_started_state_freeze(self):
        root, spec, calls, stage, execute = self.exercise(["bad"])
        with patch.object(runner, "_stage_single", side_effect=stage), patch.object(runner, "_run_remote", side_effect=execute):
            with self.assertRaises(RuntimeError):
                runner._run_single("fixture", root, root, "run", binding(), spec)
            self.assertEqual(len(calls), 2)
            with self.assertRaises(RuntimeError):
                runner._run_single("fixture", root, root, "run", binding(), spec)
            self.assertEqual(len(calls), 2)

    def test_receipt_scope_subset_does_not_include_pair_or_gold_plan(self):
        base = {"solver_output_sha256": {f"{a['solver_id']}/{a['task_id']}": "a" * 64 for a in runner._single_assignments()},
                "ranking_snapshot_sha256": "b" * 64, "optional_luna": {}, "sentinel_count": 6}
        bindings = [binding().model_copy(update={"task_id": tid, "occupation": occ}) for tid, occ in zip(runner.SINGLE_TASKS,
                    ["Accountants and Auditors", "Buyers and Purchasing Agents", "Compliance Officers"])]
        with patch.object(runner, "_judge_scope", return_value=base):
            scope = runner._single_scope("fixture", Path("none"), bindings, Path("none"))
        self.assertEqual(len(scope["solver_output_sha256"]), 9)
        self.assertEqual(scope["max_attempts"], 14)
        self.assertNotIn("ranking_snapshot_sha256", scope)
        self.assertNotIn("sentinel_count", scope)
        with patch.object(runner, "_judge_scope", return_value=base), self.assertRaises(ValueError):
            runner._single_scope("fixture", Path("none"), [b.model_copy(update={"split": "holdout"}) for b in bindings], Path("none"))

    def test_canary_failure_and_stop_marker_prevent_more_calls(self):
        assignments = runner._single_assignments()
        bindings = [binding().model_copy(update={"task_id": tid}) for tid in runner.SINGLE_TASKS]
        scope = {"assignments": assignments, "task_binding_sha256": {b.task_id: b.canonical_sha256() for b in bindings},
                 "solver_output_sha256": {f"{a['solver_id']}/{a['task_id']}": "a" * 64 for a in assignments}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(runner, "_bindings", return_value=bindings), patch.object(runner, "_verify_public_files"), patch.object(runner, "tree_sha256", return_value="a" * 64), patch.object(runner, "_run_single", side_effect=RuntimeError("fixture failure")) as call:
                result = runner.run_single_scoring("fixture", root, root, "run", scope)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(result["status"], "preliminary_scoring_partial")
                (root / "STOP_REQUESTED").touch()
                call.reset_mock()
                runner.run_single_scoring("fixture", root, root, "run", scope)
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
