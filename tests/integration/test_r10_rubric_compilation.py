from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Test"))
import run_r10_rubric_compilation as runner
from task_generator.planning.rubric_compiler_v2 import (
    TaskSpecificRubricV2, RubricCompilationV2, RubricAuthorReviewV2, REVIEW_CHECKS,
    validate_rubric, validate_review, sum_rubric_points, rubric_compiler_prompt,
)
from task_generator.core.scenario_first import TaskDecisionMatrixV1


def matrix():
    return TaskDecisionMatrixV1.model_validate({"scenario_id": "synthetic", "decision_points": [{
        "decision_id": "decision_one", "question": "Reconcile every month and qualify the conclusion.",
        "evidence_refs": [{"artifact_id": "ledger.txt", "record_id": "months", "field_names": ["amount"]}],
        "rule_ids": ["rule_one"], "skill_ids": ["skill_one"], "acceptable_conclusions": ["conditional"],
        "major_errors": ["future item recognized early"], "allowed_uncertainty_conclusions": ["needs evidence"],
        "required_follow_up_actions": ["request support"],
    }]})


def rubric(task_id=runner.TASKS[0]):
    common = {
        "decision_id": "decision_one", "max_points": 2,
        "score_boundaries": [{"awarded": 0, "description": "No supporting calculation."},
            {"awarded": 1, "description": "Some but not all periods verified."},
            {"awarded": 2, "description": "All requested periods correctly verified."}],
        "requirement_basis": [{"path": "candidate_task.md", "locator": "paragraph 1",
                                "explanation": "The task explicitly requests all months."}],
        "evidence_paths": ["reference_files/ledger.txt"],
        "applicability": "Applicable to every requested month; proven absent prerequisites earn full credit, unresolved is incomplete.",
        "acceptable_alternatives": "Accept equivalent layouts and conditional conclusions.",
        "verification": "Check each requested month, every line and monthly totals; not only the final balance.",
    }
    return TaskSpecificRubricV2.model_validate({"task_id": task_id, "criteria": [
        {**common, "criterion_id": "monthly_identity", "requirement": "Correct opening plus movement equals closing every month."},
        {**common, "criterion_id": "monthly_reconciliation", "requirement": "Monthly ledger totals reconcile to independent records."},
    ]})


def compiled(task_id):
    return RubricCompilationV2(task_id=task_id, status="compiled", rubric=rubric(task_id),
        upstream_issues=[], summary_zh="按任务明确要求逐项编译，保留合理表达与不确定结论。")


def reviewed(task_id, decision="pass"):
    checks = [{"check": name, "status": "pass", "criterion_ids": [r.criterion_id for r in rubric().criteria],
               "evidence": [{"path": "candidate_task.md", "locator": "paragraph 1", "explanation": "Requirement evidence checked."}],
               "rationale_zh": "逐项对应题干和候选材料，核验范围完整。"} for name in sorted(REVIEW_CHECKS)]
    if decision != "pass":
        checks[0]["status"] = "issue"
    return RubricAuthorReviewV2(task_id=task_id, decision=decision, checks=checks,
                                summary_zh="独立审查全部评分项，保留发现的问题，不作模型评分。")


def make_source(source):
    for tid in runner.TASKS:
        task = source / tid
        (task / "reference_files").mkdir(parents=True)
        (task / "teacher").mkdir()
        (task / "TASK.md").write_text("Reconcile all months; the exempt item needs no narrative. Equivalent headings are allowed.", encoding="utf-8")
        (task / "reference_files/ledger.txt").write_text("January 0; February movement 12, ending 12; March ending 12.", encoding="utf-8")
        runner.write(task / "deliverable_contract.json", {"path": "deliverable_files/report.xlsx"})
        runner.write(task / "teacher/decision_matrix.json", matrix())
        runner.write(task / "teacher/teacher_truth.json", {"conditional": "reconcile all months"})
        (task / "teacher/task_specific_rubric.json").write_text("FROZEN_OLD_RUBRIC", encoding="utf-8")
        (task / "solver_answer.txt").write_text("DO_NOT_UPLOAD_ANSWER", encoding="utf-8")
        (task / "rankings.txt").write_text("DO_NOT_UPLOAD_RANKINGS", encoding="utf-8")


class RubricCompilationTests(unittest.TestCase):
    def test_many_items_per_decision_and_integer_sum(self):
        r = rubric()
        self.assertEqual(r.total_points, 4)
        self.assertEqual(sum_rubric_points(r, {"monthly_identity": 1, "monthly_reconciliation": 2}), .75)
        self.assertEqual(r.canonical_sha256(), TaskSpecificRubricV2.model_validate_json(r.model_dump_json()).canonical_sha256())

    def test_duplicate_missing_score_or_out_of_range(self):
        for change in (lambda r: r["criteria"].append(r["criteria"][0]),
                       lambda r: r["criteria"][0]["score_boundaries"].pop(),
                       lambda r: r["criteria"][0].update(max_points=True),
                       lambda r: r.update(preference="first")):
            value = rubric().model_dump(mode="json"); change(value)
            with self.assertRaises(ValueError):
                TaskSpecificRubricV2.model_validate(value)
        for values in ({}, {"monthly_identity": True, "monthly_reconciliation": 2},
                       {"monthly_identity": 3, "monthly_reconciliation": 2}):
            with self.assertRaises(ValueError):
                sum_rubric_points(rubric(), values)

    def test_source_visibility_and_decision_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"; make_source(source)
            workspace = Path(tmp) / "workspace"; runner.stage(workspace, source / runner.TASKS[0], "author")
            validate_rubric(rubric(), matrix(), workspace)
            for path in ("teacher_truth.json", "../ledger.txt", "/tmp/ledger.txt", "reference_files/missing.txt"):
                r = rubric(); r.criteria[0].requirement_basis[0].path = path
                with self.assertRaises(ValueError):
                    validate_rubric(r, matrix(), workspace)
            r = rubric(); r.criteria[0].decision_id = "missing_decision"
            with self.assertRaises(ValueError):
                validate_rubric(r, matrix(), workspace)

    def test_review_complete_and_cannot_pass_issues(self):
        value = reviewed(runner.TASKS[0]).model_dump(mode="json")
        value["checks"][0]["status"] = "uncertain"
        with self.assertRaises(ValueError):
            RubricAuthorReviewV2.model_validate(value)
        value = reviewed(runner.TASKS[0]).model_dump(mode="json"); value["checks"].pop()
        with self.assertRaises(ValueError):
            RubricAuthorReviewV2.model_validate(value)

    def test_prompt_covers_scope_exceptions_and_equivalence(self):
        text = rubric_compiler_prompt("synthetic")
        for marker in ("all periods/rows", "not only", "exceptions", "equivalent", "Hidden teacher"):
            self.assertIn(marker, text)
        self.assertIn("unresolved applicability means incomplete", text)
        self.assertNotIn("GDPval", text)

    def test_no_private_answers_or_old_rubric_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"; make_source(source)
            dest = Path(tmp) / "workspace"; runner.stage(dest, source / runner.TASKS[0], "author")
            joined = "\n".join(p.read_text(encoding="utf-8") for p in dest.rglob("*") if p.is_file())
            for forbidden in ("FROZEN_OLD_RUBRIC", "DO_NOT_UPLOAD_ANSWER", "DO_NOT_UPLOAD_RANKINGS"):
                self.assertNotIn(forbidden, joined)
            self.assertTrue(all("baseline" in tid for tid in runner.TASKS))

    def test_unicode_event_delimiter_and_reasoning_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [{"type": "reasoning", "part": {"text": "hidden"}},
                      {"type": "text", "part": {"text": "legal\u2028separator"}},
                      {"type": "step_finish", "part": {"reason": "stop"}}]
            (root / "agent.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
            self.assertTrue(runner.completed(root, "review"))
            runner.sanitize_logs(root)
            self.assertNotIn("hidden", (root / "agent.jsonl").read_text(encoding="utf-8"))
            self.assertTrue(runner.completed(root, "review"))

    def test_global_retry_limit_and_no_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for retry in (False, True, False, True):
                runner.reserve_attempt(root, retry)
            with self.assertRaises(RuntimeError):
                runner.reserve_attempt(root, True)
            runner.reserve_attempt(root, False); runner.reserve_attempt(root, False)
            with self.assertRaises(RuntimeError):
                runner.reserve_attempt(root, False)

    def simulate(self, *, format_once=False, low_quality=False, nonterminal=False, upstream=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; make_source(source)
            run = root / "artifacts/r10/trial"
            before = runner.bindings(source)
            calls = []
            def remote(**kw):
                ws = kw["local"]; author = kw["model_override"] == "gpt-5.6-terra"
                tid = ws.parents[2].name
                calls.append((tid, author, kw))
                if author:
                    (ws / "agent.jsonl").write_text(json.dumps({"type": "turn.started" if nonterminal else "turn.completed"}) + "\n", encoding="utf-8")
                    result = compiled(tid)
                    if upstream and tid == runner.TASKS[0]:
                        result = RubricCompilationV2(task_id=tid, status="upstream_issue", rubric=None,
                            upstream_issues=["Frozen requirement and truth conflict."], summary_zh="题干与监督冲突，不能通过评分项掩盖。")
                    (ws / "grade.raw.json").write_text("{}" if format_once and len(calls) == 1 else result.model_dump_json(), encoding="utf-8")
                else:
                    value = reviewed(tid, "revision_required" if low_quality else "pass")
                    (ws / "agent.jsonl").write_text("\n".join(json.dumps(e) for e in [
                        {"type": "text", "part": {"text": value.model_dump_json()}},
                        {"type": "step_finish", "part": {"reason": "stop"}}]), encoding="utf-8")
                return 0, "", ""
            with patch.object(runner, "ROOT", root), patch.object(runner, "environment", return_value={"image_sha256": runner.IMAGE_SHA}), \
                 patch.object(runner.subprocess, "run", return_value=SimpleNamespace(stdout="a" * 40)), \
                 patch.object(runner, "_run_remote", side_effect=remote), patch.object(runner, "verify_remote_inputs"):
                result = runner.run_campaign("fixture", run, "trial", source)
                with self.assertRaises(ValueError):
                    runner.run_campaign("fixture", run, "trial", source)
            self.assertEqual(runner.bindings(source), before)
            return result, calls

    def test_full_two_task_campaign_four_calls(self):
        result, calls = self.simulate()
        self.assertEqual(result["status"], "rubric_compilation_supported")
        self.assertEqual(len(calls), 4)
        self.assertEqual(result["attempts"], {"attempts": 4, "retries": 0})
        self.assertEqual(calls[0][2]["codex_reasoning_effort"], "medium")
        self.assertEqual(calls[1][2]["opencode_variant"], "max")

    def test_one_format_retry_preserves_frozen_input(self):
        result, calls = self.simulate(format_once=True)
        self.assertEqual(result["status"], "rubric_compilation_supported")
        self.assertEqual(len(calls), 5)
        self.assertEqual(result["attempts"]["retries"], 1)

    def test_bad_quality_does_not_redraw(self):
        result, calls = self.simulate(low_quality=True)
        self.assertEqual(result["status"], "rubric_revision_required")
        self.assertEqual(len(calls), 4)

    def test_nonterminal_stops_without_semantic_retry(self):
        result, calls = self.simulate(nonterminal=True)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(calls), 1)

    def test_upstream_issue_skips_review_not_hidden(self):
        result, calls = self.simulate(upstream=True)
        self.assertEqual(result["status"], "rubric_revision_required")
        self.assertEqual(result["tasks"][runner.TASKS[0]]["status"], "upstream_issue")
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
