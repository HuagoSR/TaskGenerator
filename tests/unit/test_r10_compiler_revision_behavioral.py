from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("r10_revision_behavioral", ROOT / "Test" / "run_r10_compiler_revision_behavioral.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def completed(score: float, *, major: bool = False) -> dict:
    review = {"weighted_score": score, "major_defect": major}
    return {"delivery": {"valid": True}, "reviews": {solver: {"status": "completed", "review": review} for solver in RUNNER.STACKS}}


class R10CompilerRevisionBehavioralTests(unittest.TestCase):
    def test_revision_campaign_defaults_to_official_chatgpt_codex(self):
        self.assertEqual(RUNNER.STACKS, ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"))
        binding = MagicMock()
        binding.model_dump.return_value = {
            "task_id": "fixture-task", "domain": "audit_compliance",
            "package_root": "/fixture/task", "package_tree_sha256": "1" * 64,
            "candidate_tree_sha256": "2" * 64, "task_compilation_sha256": "3" * 64,
            "deliverable_contract_sha256": "4" * 64,
            "expected_delivery": "deliverable_files/result.xlsx",
        }
        evidence = {
            "evidence_version": "r10.public_gate_evidence.1", "source_commit": "a" * 40,
            "image": "image", "image_sha256": "a" * 64, "stacks": list(RUNNER.STACKS),
            "decision": "public_gates_passed", "result_sha256": "b" * 64,
            "public_tree_sha256": "c" * 64,
        }
        with patch.object(RUNNER, "binding_from_task", return_value=binding), patch.object(RUNNER, "_source_commit", return_value="a" * 40):
            scope = RUNNER._scope("official-revision", image="image", image_sha256="a" * 64, public_gate_evidence=evidence)
        self.assertEqual(scope["gpt_environment"]["transport"], "chatgpt_codex")
        self.assertEqual(scope["gpt_environment"]["provider"], "openai_chatgpt")
        self.assertEqual(scope["gpt_environment"]["authentication"], "chatgpt_oauth")
        self.assertNotIn("tuzi", __import__("json").dumps(scope).casefold())
        self.assertEqual(scope["solver_stacks"], list(RUNNER.STACKS))
        self.assertEqual(scope["judges"], list(RUNNER.STACKS))
        self.assertTrue(scope["complex_judge_probe_required"])
        self.assertEqual(scope["public_gate_evidence"], evidence)

    def test_tuzi_transport_is_explicit_and_never_mixed_with_official_scope(self):
        self.assertEqual(
            RUNNER._stacks("tuzi_codex"),
            ("gpt-5.6-sol@tuzi_codex", "deepseek-v4-pro@official_opencode"),
        )
        self.assertNotEqual(RUNNER._stacks("tuzi_codex"), RUNNER.STACKS)
        with self.assertRaisesRegex(ValueError, "gpt_transport_invalid"):
            RUNNER._stacks("fallback")

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

    def test_public_only_mode_does_not_read_private_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "public"
            arguments = [
                "runner", "--public-only", "--run-id", "public-fixture", "--output-root", str(output),
                "--image", "public-image", "--image-sha256", "a" * 64,
            ]
            def record_public_gates(*, output_root, **_kwargs):
                RUNNER._write(output_root / "result.json", {"decision": "public_gates_passed", "probes": {stack: True for stack in RUNNER.STACKS}})
                return True, {stack: True for stack in RUNNER.STACKS}
            with patch.object(sys, "argv", arguments), patch.object(RUNNER, "_scope", side_effect=AssertionError("private_scope_read")), patch.object(RUNNER, "_record_public_gates", side_effect=record_public_gates), patch.object(RUNNER, "_source_commit", return_value="b" * 40):
                RUNNER.main()
            evidence = __import__("json").loads((output / "public_gate_evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["decision"], "public_gates_passed")
        self.assertEqual(evidence["stacks"], list(RUNNER.STACKS))

    def test_public_gate_evidence_rejects_image_or_tree_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            RUNNER._write(root / "result.json", {"decision": "public_gates_passed", "probes": {stack: True for stack in RUNNER.STACKS}})
            with patch.object(RUNNER, "_source_commit", return_value="c" * 40):
                evidence = RUNNER._write_public_gate_evidence(output_root=root, image="image", image_sha256="d" * 64)
                self.assertEqual(RUNNER._load_public_gate_evidence(root=root, image="image", image_sha256="d" * 64), evidence)
                (root / "result.json").write_text('{"decision":"incomplete"}\n', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "evidence_drift|result_drift"):
                    RUNNER._load_public_gate_evidence(root=root, image="image", image_sha256="d" * 64)

    def test_scope_uses_immutable_build_metadata_when_git_is_unavailable(self):
        with patch.object(RUNNER.subprocess, "run", side_effect=FileNotFoundError), patch.dict(RUNNER.os.environ, {"TASKGEN_SOURCE_COMMIT": "b" * 40}, clear=False):
            self.assertEqual(RUNNER._source_commit(), "b" * 40)


if __name__ == "__main__":
    unittest.main()
