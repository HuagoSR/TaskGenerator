from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("r10_revision_behavioral", ROOT / "Test" / "run_r10_compiler_revision_behavioral.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def completed(score: float, *, major: bool = False) -> dict:
    review = {"weighted_score": score, "major_defect": major}
    return {"delivery": {"valid": True}, "reviews": {solver: {"status": "completed", "review": review} for solver in RUNNER.STACKS}}


class R10CompilerRevisionBehavioralTests(unittest.TestCase):
    def test_revision_campaign_uses_a_distinct_tuzi_codex_stack(self):
        self.assertEqual(RUNNER.STACKS, ("gpt-5.6-sol@tuzi_codex", "deepseek-v4-pro@official_opencode"))
        scope = RUNNER._scope("tuzi-revision", image="image", image_sha256="a" * 64)
        self.assertEqual(scope["gpt_environment"]["transport"], "tuzi_codex")
        self.assertEqual(scope["gpt_environment"]["provider"], "tuzi")
        self.assertTrue(scope["complex_judge_probe_required"])

    def test_two_clean_differences_support_revision(self):
        records = {
            task_id: {
                RUNNER.STACKS[0]: completed(0.95),
                RUNNER.STACKS[1]: completed(0.75),
            }
            for task_id in RUNNER.TASKS
        }
        self.assertEqual(RUNNER._aggregate(records)["decision"], "compiler_revision_supported")

    def test_judge_disagreement_requires_evaluator_revision(self):
        records = {
            task_id: {
                RUNNER.STACKS[0]: completed(0.95),
                RUNNER.STACKS[1]: completed(0.75),
            }
            for task_id in RUNNER.TASKS
        }
        first = next(iter(records))
        records[first][RUNNER.STACKS[0]]["reviews"][RUNNER.STACKS[1]]["review"] = {"weighted_score": 0.70, "major_defect": False}
        self.assertEqual(RUNNER._aggregate(records)["decision"], "evaluator_revision_required")


if __name__ == "__main__":
    unittest.main()
