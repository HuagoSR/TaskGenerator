from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_public_gates_do_not_require_private_task_bindings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(RUNNER, "_record_probe", return_value=True), patch.object(RUNNER, "_record_complex_judge_probe", return_value=True):
            passed, probes = RUNNER._record_public_gates(
                output_root=Path(directory), host="public-host", remote_root="/tmp/public", image="public-image",
            )
        self.assertTrue(passed)
        self.assertEqual(set(probes), set(RUNNER.STACKS))

    def test_scope_uses_immutable_build_metadata_when_git_is_unavailable(self):
        completed_process = __import__("subprocess").CompletedProcess(["git"], 1, "", "missing")
        with patch.object(RUNNER.subprocess, "run", return_value=completed_process), patch.dict(RUNNER.os.environ, {"TASKGEN_SOURCE_COMMIT": "b" * 40}, clear=False):
            self.assertEqual(RUNNER._source_commit(), "b" * 40)


if __name__ == "__main__":
    unittest.main()
