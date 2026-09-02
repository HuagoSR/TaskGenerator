from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(__file__).resolve().parents[2] / "Test"
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import run_r10_evaluator_v2_calibration as runner
from task_generator.evaluation.r10_evaluator_v2 import (
    CounterbalancedPairReviewV2,
    assess_counterbalance_stability,
)


class R10EvaluatorV2RunnerTests(unittest.TestCase):
    def test_scope_binds_frozen_deliveries_and_never_requests_solver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profiles = runner.build_profiles(Path(temporary), "v2.0")
            scope = runner._scope("fixture", profiles)
        self.assertEqual(set(scope["r10_splits"]), {"development", "holdout"})
        self.assertEqual(len(scope["frozen_delivery_sha256"]), 8)
        self.assertIn("solver_rerun", scope["excluded_actions"])
        self.assertEqual(scope["judges"]["gpt-5.6-terra@chatgpt_codex"]["reasoning"], "medium")
        self.assertEqual(scope["judges"]["deepseek-v4-pro@official_opencode"]["variant"], "max")

    def test_stage_reverses_only_anonymous_presentation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profiles = runner.build_profiles(root / "profiles", "v2.0")
            task_id = runner.R10_SPLITS["development"][0]
            runner._stage(
                target=root / "ab", task_id=task_id, profile=profiles[task_id],
                order="a_b", judge_id="gpt-5.6-terra@chatgpt_codex",
            )
            runner._stage(
                target=root / "ba", task_id=task_id, profile=profiles[task_id],
                order="b_a", judge_id="gpt-5.6-terra@chatgpt_codex",
            )
            self.assertEqual(
                (root / "ab/anonymous_slot_1.xlsx").read_bytes(),
                (root / "ba/anonymous_slot_2.xlsx").read_bytes(),
            )
            self.assertEqual(
                (root / "ab/anonymous_slot_2.xlsx").read_bytes(),
                (root / "ba/anonymous_slot_1.xlsx").read_bytes(),
            )
            self.assertNotIn("gpt-5.6-sol", (root / "ab/TASK.md").read_text(encoding="utf-8"))

    def test_started_session_is_never_silently_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profiles = runner.build_profiles(root, "v2.0")
            task_id = runner.R10_SPLITS["development"][0]
            assignment = f"{task_id}__gpt-5.6-terra_chatgpt_codex__a_b"
            state = root / "sessions" / assignment / "state.json"
            state.parent.mkdir(parents=True)
            state.write_text('{"status":"running"}', encoding="utf-8")
            with patch.object(runner, "_run_remote") as remote, self.assertRaises(RuntimeError):
                runner._run_assignment(
                    run_root=root, run_id="fixture", task_id=task_id,
                    profile=profiles[task_id], judge_id="gpt-5.6-terra@chatgpt_codex",
                    config=runner.JUDGES["gpt-5.6-terra@chatgpt_codex"], order="a_b",
                )
            remote.assert_not_called()

    def test_review_schema_requires_anonymous_slots(self) -> None:
        schema = CounterbalancedPairReviewV2.model_json_schema()
        self.assertNotIn("solver", str(schema).casefold())
        self.assertIn("slot_1", str(schema))
        self.assertIn("slot_2", str(schema))

    def test_opencode_fenced_json_is_recovered_without_retry(self) -> None:
        payload = {
            "review_version": "r10.counterbalanced_pair_review.2",
            "task_id": "task", "judge_id": "deepseek-v4-pro@official_opencode",
            "order_id": "a_b", "preference": "tie", "bundles": [],
        }
        event = {"type": "text", "part": {"type": "text", "text": "Done.\n```json\n" + __import__("json").dumps(payload) + "\n```"}}
        recovered = runner._extract_fenced_json_from_opencode(__import__("json").dumps(event))
        self.assertEqual(__import__("json").loads(recovered), payload)


if __name__ == "__main__":
    unittest.main()
