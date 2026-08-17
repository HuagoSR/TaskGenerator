from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from task_generator.v3_huago_cone_eval import (
    R9DualJudgeRunner,
    R9JudgeRecordV1,
    R9NativeSolverRunner,
    _grade_prompt,
    _read_env,
    _redact,
)


class HuagoConeEvalTests(unittest.TestCase):
    def test_crlf_env_is_normalized(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "env"
            path.write_bytes(b"TUZI_API_KEY=secret-value\r\nTUZI_BASE_URL=https://example.test/v1\r\n")
            values = _read_env(path)
            self.assertEqual(values["TUZI_API_KEY"], "secret-value")
            self.assertEqual(values["TUZI_BASE_URL"], "https://example.test/v1")

    def test_secret_redaction(self):
        value = _redact("before secret-value after", ["secret-value"])
        self.assertEqual(value, "before [REDACTED] after")
        self.assertNotIn("secret-value", value)

    def test_public_probe_stages_task_and_delivery_directory(self):
        with tempfile.TemporaryDirectory() as root:
            runner = R9NativeSolverRunner(
                stack_id="deepseek-v4-pro@official_opencode",
                output_root=root,
            )
            captured = {}

            def fake_execute(**kwargs):
                captured.update(kwargs)
                workspace = kwargs["workspace"]
                self.assertTrue((workspace / "TASK.md").is_file())
                self.assertTrue((workspace / "deliverable_files").is_dir())
                raise RuntimeError("stop_after_staging")

            runner._execute = fake_execute
            with self.assertRaisesRegex(RuntimeError, "stop_after_staging"):
                runner.public_probe()
            self.assertIn("public_probe.xlsx", captured["expected"])

    def test_judge_pending_state_is_explicit(self):
        record = R9JudgeRecordV1(
            task_id="task-1",
            judge_id="gpt-5.6-sol@chatgpt_codex",
            status="pending",
            attempt_count=0,
        )
        self.assertEqual(record.status, "pending")
        self.assertIsNone(record.first_failure)

    def test_grade_prompt_is_route_and_solver_blind(self):
        prompt = _grade_prompt("task-1")
        lowered = prompt.lower()
        self.assertNotIn("skill_guided", lowered)
        self.assertNotIn("llm_led", lowered)
        self.assertNotIn("solver_id", lowered)
        self.assertIn("task-1", prompt)

    def test_grader_stage_contains_only_contract_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            package = root / "package"
            (package / "rw_task_export").mkdir(parents=True)
            (package / "teacher").mkdir()
            (package / "rw_task_export" / "dataset_row.json").write_text(
                json.dumps({"prompt": "candidate request"}), encoding="utf-8"
            )
            (package / "teacher" / "rubric_plan_v2.json").write_text(
                json.dumps({"criteria": []}), encoding="utf-8"
            )
            (package / "teacher" / "deterministic_fact_anchors.json").write_text(
                json.dumps({"anchors": []}), encoding="utf-8"
            )
            delivery = root / "answer.xlsx"
            delivery.write_bytes(b"test-delivery")
            workspace = root / "workspace"
            R9DualJudgeRunner._stage(package, delivery, workspace, "task-1", None)
            self.assertEqual(
                {item.name for item in workspace.iterdir()},
                {
                    "TASK.md", "candidate_prompt.json", "rubric.json",
                    "fact_anchors.json", "grade_schema.json", "deliverable.xlsx",
                },
            )
            staged_prompt = (workspace / "TASK.md").read_text(encoding="utf-8").lower()
            self.assertNotIn("skill_guided", staged_prompt)
            self.assertNotIn("llm_led", staged_prompt)


if __name__ == "__main__":
    unittest.main()
