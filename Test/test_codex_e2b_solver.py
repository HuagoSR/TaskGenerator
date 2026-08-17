from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from task_generator.v3_codex_e2b_solver import (
    CODEX_HOME,
    CodexE2BRunner,
    CodexE2BSliceReceiptV1,
    CodexE2BSliceScopeV1,
    CodexE2BTaskBindingV1,
    _config_toml,
    _codex_exit_code,
    _inspect,
    _parse_jsonl,
    _redact,
    _expected_deliverable,
)
from task_generator.v3_skill_extractor import ProviderConfig


def workbook_bytes(value="done") -> bytes:
    wb = Workbook()
    wb.active["A1"] = value
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


class FakeFiles:
    def __init__(self, delivery: bytes | None):
        self.data = {}
        self.delivery = delivery
        self.private_uploads = []

    def make_dir(self, path):
        return None

    def write(self, path, data):
        self.data[path] = data
        if "ms_" in str(data) or "validation_workpaper" in path:
            self.private_uploads.append(path)

    def exists(self, path):
        return path.endswith(".xlsx") and self.delivery is not None and "deliverable_files" in path

    def read(self, path, format="text"):
        return self.delivery


class FakeSandbox:
    def __init__(self, delivery: bytes | None, stdout: str, stderr="", exit_code=0):
        self.sandbox_id = "sandbox-test"
        self.files = FakeFiles(delivery)
        self.calls = []
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.commands = self

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if "pip install" in command:
            return SimpleNamespace(exit_code=0, stdout="installed\n__INSTALL_EXIT__:0\n", stderr="")
        marked = self.stdout + "\n" + json.dumps({"type": "runner.exit", "exit_code": self.exit_code})
        return SimpleNamespace(exit_code=0, stdout=marked, stderr=self.stderr)

    def kill(self):
        pass


class CodexE2BSolverTests(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig("tuzi", "https://example.invalid/v1", "top-secret-key", "gpt-5.6-sol")
        self.e2b_key = "e2b-secret-key"
        self.events = "\n".join((
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}}),
        ))

    def test_provider_config_is_responses_and_contains_no_key(self):
        config = _config_toml(self.config)
        self.assertIn('wire_api = "responses"', config)
        self.assertIn("request_max_retries = 0", config)
        self.assertNotIn(self.config.api_key, config)

    def test_jsonl_requires_turn_and_command(self):
        types, command, turn, usage = _parse_jsonl(self.events + "\nnot-json")
        self.assertTrue(command)
        self.assertTrue(turn)
        self.assertEqual(usage["output_tokens"], 2)
        self.assertIn("turn.completed", types)
        self.assertEqual(_codex_exit_code(self.events + '\n{"type":"runner.exit","exit_code":7}'), 7)

    def test_delivery_rejects_copy_pseudo_and_empty_workbook(self):
        original = workbook_bytes("source")
        self.assertFalse(_inspect(original, {__import__("hashlib").sha256(original).hexdigest()}).differs_from_inputs)
        self.assertFalse(_inspect(b"not xlsx", set()).xlsx_openable)
        empty = Workbook()
        empty.active["A1"] = None
        stream = BytesIO(); empty.save(stream)
        self.assertFalse(_inspect(stream.getvalue(), set()).has_nonempty_sheet)

    def test_single_run_uses_key_only_in_env_and_has_no_retry(self):
        sandbox = FakeSandbox(workbook_bytes(), self.events)
        factory_calls = []
        def factory(**kwargs):
            factory_calls.append(kwargs)
            return sandbox
        with tempfile.TemporaryDirectory() as temp:
            result = CodexE2BRunner(factory)._run_one(
                kind="public_probe", task_id="probe", prompt="make file",
                uploads={"reference_files/source.xlsx": workbook_bytes("source")},
                expected="deliverable_files/codex_probe.xlsx", timeout=300,
                config=self.config, e2b_api_key=self.e2b_key, output_dir=Path(temp),
            )
            self.assertEqual(result.status, "pass")
            self.assertEqual(factory_calls[0]["api_key"], self.e2b_key)
            codex_calls = [call for call in sandbox.calls if "codex exec" in call[0]]
            self.assertEqual(len(codex_calls), 1)
            command, kwargs = codex_calls[0]
            self.assertNotIn(self.config.api_key, command)
            self.assertEqual(kwargs["envs"]["TUZI_API_KEY"], self.config.api_key)
            self.assertEqual(kwargs["envs"]["CODEX_HOME"], str(CODEX_HOME))
            combined = "".join(path.read_text(encoding="utf-8") for path in Path(temp).rglob("*.txt"))
            self.assertNotIn(self.config.api_key, combined)
            self.assertNotIn(self.e2b_key, combined)

    def test_provider_protocol_failure_is_infrastructure(self):
        sandbox = FakeSandbox(None, "", "HTTP 404 /responses unsupported", 1)
        with tempfile.TemporaryDirectory() as temp:
            outcome = CodexE2BRunner(lambda **_: sandbox)._run_one(
                kind="public_probe", task_id="probe", prompt="x", uploads={},
                expected="deliverable_files/codex_probe.xlsx", timeout=300,
                config=self.config, e2b_api_key=self.e2b_key, output_dir=Path(temp),
            )
        self.assertEqual(outcome.status, "infrastructure_failed")

    def test_stream_disconnect_in_jsonl_is_infrastructure(self):
        events = self.events + "\n" + json.dumps({
            "type": "error", "message": "stream disconnected before completion: error decoding response body"
        })
        sandbox = FakeSandbox(None, events, "", 1)
        with tempfile.TemporaryDirectory() as temp:
            outcome = CodexE2BRunner(lambda **_: sandbox)._run_one(
                kind="private_task", task_id="probe", prompt="x", uploads={},
                expected="deliverable_files/x.xlsx", timeout=300,
                config=self.config, e2b_api_key=self.e2b_key, output_dir=Path(temp),
            )
        self.assertEqual(outcome.status, "infrastructure_failed")

    def test_install_failure_is_preserved_without_codex_retry(self):
        sandbox = FakeSandbox(None, self.events)
        original_run = sandbox.run
        def failing_install(command, **kwargs):
            if "pip install" in command:
                sandbox.calls.append((command, kwargs))
                return SimpleNamespace(exit_code=0, stdout="__INSTALL_EXIT__:1\n", stderr="temporary package error")
            return original_run(command, **kwargs)
        sandbox.commands.run = failing_install
        with tempfile.TemporaryDirectory() as temp:
            outcome = CodexE2BRunner(lambda **_: sandbox)._run_one(
                kind="public_probe", task_id="probe", prompt="x", uploads={},
                expected="deliverable_files/codex_probe.xlsx", timeout=300,
                config=self.config, e2b_api_key=self.e2b_key, output_dir=Path(temp),
            )
        self.assertEqual(outcome.status, "infrastructure_failed")
        self.assertIn("temporary package error", outcome.first_failure)
        self.assertFalse(any("codex exec" in call[0] for call in sandbox.calls))

    def test_scope_has_no_budget_or_grader_authority(self):
        scope = CodexE2BSliceScopeV1(campaign_id="c", task_bindings=[
            CodexE2BTaskBindingV1(blind_task_id="a", package_fingerprint="a" * 64, candidate_tree_sha256="b" * 64, expected_deliverable="deliverable_files/x.xlsx")
        ])
        payload = scope.model_dump()
        self.assertNotIn("budget", json.dumps(payload).lower())
        self.assertFalse(payload["grader_authorized"])
        receipt = CodexE2BSliceReceiptV1(scope_sha256="c" * 64)
        self.assertTrue(receipt.private_package_upload_authorized)

    def test_expected_deliverable_is_read_per_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "deliverable_contract.json").write_text(json.dumps({
                "deliverables": [{"relative_path": "deliverable_files/review_memo.xlsx"}]
            }), encoding="utf-8")
            self.assertEqual(_expected_deliverable(root), "deliverable_files/review_memo.xlsx")

    def test_both_secrets_are_redacted_from_provider_errors(self):
        text = f"tuzi={self.config.api_key}; e2b={self.e2b_key}"
        redacted = _redact(text, [self.config.api_key, self.e2b_key])
        self.assertNotIn(self.config.api_key, redacted)
        self.assertNotIn(self.e2b_key, redacted)
        self.assertEqual(redacted.count("[REDACTED_SECRET]"), 2)

    def test_module_does_not_import_old_solver_stack(self):
        source = (Path(__file__).parents[1] / "src/task_generator/v3_codex_e2b_solver.py").read_text(encoding="utf-8")
        for forbidden in ("SolverExecutionBudgetLedger", "v3_rw_task_eval_stirrup_wrapper", "DeepSeekSolver"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
