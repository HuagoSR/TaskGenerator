from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.v3_official_deepseek_opencode import (  # noqa: E402
    E2BOpenCodeBackend,
    MATCHED_TASK_IDS,
    OpenCodeProcessOutcomeV1,
    _failure_code,
    _inspect_bytes,
    _redact,
    matched_extension_allowed,
    parse_opencode_jsonl,
    task_execution_order,
)


def workbook_bytes(value: str = "ok") -> bytes:
    stream = BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["value"])
    sheet.append([value])
    workbook.save(stream)
    return stream.getvalue()


class FakeFiles:
    def __init__(self, delivery: bytes | None):
        self.delivery = delivery
        self.writes = {}

    def make_dir(self, path):
        return None

    def write(self, path, value):
        self.writes[path] = value

    def exists(self, path):
        return (
            self.delivery is not None
            and "deliverable_files" in path
            and path.endswith(".xlsx")
        )

    def read(self, path, format="text"):
        return self.delivery


class FakeSandbox:
    def __init__(self, delivery: bytes | None):
        self.sandbox_id = "sandbox-public"
        self.files = FakeFiles(delivery)
        self.commands = self
        self.calls = []
        self.killed = False

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if "if [ ! -x" in command:
            return SimpleNamespace(exit_code=0, stdout="", stderr="")
        events = "\n".join(
            [
                json.dumps({"type": "step_start"}),
                json.dumps(
                    {
                        "type": "tool_use",
                        "part": {"type": "tool", "tool": "bash"},
                    }
                ),
                json.dumps({"type": "runner.exit", "exit_code": 0}),
            ]
        )
        return SimpleNamespace(exit_code=0, stdout=events, stderr="")

    def kill(self):
        self.killed = True


class FakeEnvironmentSandbox(FakeSandbox):
    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if "printf \"OPENCODE=\"" in command:
            return SimpleNamespace(
                exit_code=0,
                stdout=(
                    "OPENCODE=1.18.10\n"
                    "PYTHON=Python 3.11.9\n"
                    "PIP=pip 24.0\n"
                    "VENV=0\n"
                    "OPENPYXL=Traceback (most recent call last):\n"
                ),
                stderr="",
            )
        if "pip install" in command:
            return SimpleNamespace(
                exit_code=0, stdout="3.1.5\n", stderr=""
            )
        return super().run(command, **kwargs)


def outcome(task_id: str, *, status="pass", valid=True):
    return OpenCodeProcessOutcomeV1(
        kind="private_task",
        blind_task_id=task_id,
        environment_kind="e2b_official_opencode",
        status=status,
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:01Z",
        duration_seconds=1,
        returncode=0,
        timed_out=False,
        command_identity=["opencode", "run"],
        workspace_path="x",
        workspace_input_tree_sha256="a" * 64,
        jsonl_path="x",
        jsonl_sha256="b" * 64,
        stderr_path="y",
        stderr_sha256="c" * 64,
        diagnostics=parse_opencode_jsonl(
            '{"type":"step_start"}\n'
            '{"type":"tool_use","part":{"type":"tool","tool":"bash"}}'
        ),
        delivery={"valid": valid, "relative_path": "deliverable_files/x.xlsx"},
        output_tree_sha256="d" * 64,
    )


class OfficialDeepSeekOpenCodeTests(unittest.TestCase):
    def test_parser_requires_real_json_events(self):
        diagnostics = parse_opencode_jsonl(
            "not json\n"
            + json.dumps({"type": "step_start"})
            + "\n"
            + json.dumps(
                {
                    "type": "tool_use",
                    "part": {"type": "tool", "tool": "bash"},
                    "usage": {"input_tokens": 10},
                }
            )
        )
        self.assertEqual(diagnostics.invalid_line_count, 1)
        self.assertTrue(diagnostics.turn_event_seen)
        self.assertTrue(diagnostics.tool_event_seen)
        self.assertTrue(diagnostics.shell_or_python_seen)
        self.assertEqual(diagnostics.usage["input_tokens"], 10)

    def test_delivery_blocks_input_copy_and_fake_xlsx(self):
        source = workbook_bytes("source")
        copied = _inspect_bytes(
            source,
            "deliverable_files/x.xlsx",
            {__import__("hashlib").sha256(source).hexdigest()},
        )
        self.assertFalse(copied["valid"])
        self.assertEqual(copied["failure"], "expected_delivery_copies_input")
        fake = _inspect_bytes(
            b"not an xlsx", "deliverable_files/x.xlsx", set()
        )
        self.assertFalse(fake["xlsx_openable"])
        self.assertEqual(fake["failure"], "expected_delivery_not_real_xlsx")

    def test_e2b_keys_are_injected_only_at_their_boundaries(self):
        sandbox = FakeSandbox(workbook_bytes("delivery"))
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            return sandbox

        backend = E2BOpenCodeBackend(sandbox_factory=factory)
        with tempfile.TemporaryDirectory() as temp:
            result = backend.run_one(
                template="opencode",
                environment_kind="e2b_official_opencode",
                kind="public_probe",
                task_id="probe",
                uploads={
                    "reference_files/source.xlsx": workbook_bytes("source")
                },
                prompt="make it",
                expected="deliverable_files/x.xlsx",
                timeout=300,
                deepseek_key="deepseek-secret-value",
                e2b_key="e2b-secret-value",
                output_dir=Path(temp),
            )
            persisted = "".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in Path(temp).rglob("*")
                if path.is_file() and path.suffix != ".xlsx"
            )
        self.assertEqual(result.status, "pass")
        self.assertEqual(calls[0]["api_key"], "e2b-secret-value")
        agent_calls = [
            item for item in sandbox.calls if "opencode run" in item[0]
        ]
        self.assertEqual(len(agent_calls), 1)
        command, kwargs = agent_calls[0]
        self.assertNotIn("deepseek-secret-value", command)
        self.assertNotIn("e2b-secret-value", command)
        self.assertEqual(
            kwargs["envs"]["DEEPSEEK_API_KEY"],
            "deepseek-secret-value",
        )
        self.assertNotIn("deepseek-secret-value", persisted)
        self.assertNotIn("e2b-secret-value", persisted)
        self.assertTrue(sandbox.killed)

    def test_environment_probe_installs_openpyxl_after_missing_import(self):
        sandbox = FakeEnvironmentSandbox(None)
        backend = E2BOpenCodeBackend(
            sandbox_factory=lambda **_: sandbox
        )
        with tempfile.TemporaryDirectory() as temp:
            result = backend.inspect_environment(
                template="opencode",
                e2b_key="e2b-secret-value",
                output_path=Path(temp) / "environment.json",
            )
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.opencode_version, "1.18.10")
        self.assertEqual(result.openpyxl_version, "3.1.5")
        inspect_command = sandbox.calls[0][0]
        self.assertIn("exit 0", inspect_command)
        self.assertTrue(
            any("pip install" in command for command, _ in sandbox.calls)
        )

    def test_public_failure_classification(self):
        diagnostics = parse_opencode_jsonl("")
        self.assertEqual(
            _failure_code(
                diagnostics,
                "HTTP 401 unauthorized",
                timed_out=False,
                returncode=1,
            ),
            "authentication_failure",
        )
        self.assertEqual(
            _failure_code(
                diagnostics, "", timed_out=True, returncode=None
            ),
            "timeout_without_tool_activity",
        )
        for message in (
            "ConnectError:[Errno 11002] getaddrinfo failed",
            "RemoteProtocolError:peer closed connection without sending "
            "complete message body (incomplete chunked read)",
        ):
            self.assertEqual(
                _failure_code(
                    diagnostics,
                    message,
                    timed_out=False,
                    returncode=None,
                ),
                "service_or_stream_failure",
            )

    def test_matched_pair_gates_remaining_22(self):
        all_ids = list(MATCHED_TASK_IDS) + [f"task-{i}" for i in range(22)]
        order = task_execution_order(all_ids)
        self.assertEqual(tuple(order[:2]), MATCHED_TASK_IDS)
        self.assertEqual(len(order[2:]), 22)
        self.assertTrue(
            matched_extension_allowed(
                [outcome(MATCHED_TASK_IDS[0]), outcome(MATCHED_TASK_IDS[1])]
            )
        )
        self.assertFalse(
            matched_extension_allowed(
                [
                    outcome(MATCHED_TASK_IDS[0]),
                    outcome(MATCHED_TASK_IDS[1], valid=False),
                ]
            )
        )

    def test_secrets_are_redacted(self):
        value = _redact(
            "deep=alpha e2b=beta",
            ["alpha", "beta"],
        )
        self.assertNotIn("alpha", value)
        self.assertNotIn("beta", value)
        self.assertEqual(value.count("[REDACTED_SECRET]"), 2)

    def test_module_excludes_deprecated_solver_paths(self):
        source = (
            ROOT
            / "src"
            / "task_generator"
            / "v3_official_deepseek_opencode.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "TUZI_API_KEY",
            "stirrup",
            "DeepSeekSolver",
            "SolverExecutionBudgetLedger",
            "codex exec",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn('--dir "$1"', source)


if __name__ == "__main__":
    unittest.main()
