from __future__ import annotations

from pathlib import Path
import asyncio
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.task_generator.v3_solver_execution_budget import (
    SolverExecutionBudgetLedger,
    SolverExecutionBudgetV1,
    inspect_solver_process_outcome,
)
from src.task_generator.v3_behavioral_validation import SolverToolPreflight
from src.task_generator.v3_rw_task_eval_stirrup_wrapper import (
    _install_governed_stirrup_runtime,
    _normalize_legacy_hash_delivery,
    _run_single_case,
)


def _budget(**overrides) -> SolverExecutionBudgetV1:
    values = {
        "solver_model": "test-model",
        "maximum_provider_calls": 3,
        "maximum_agent_turns": 3,
        "maximum_request_bytes_per_call": 4096,
        "maximum_completion_tokens_per_call": 1000,
        "maximum_provider_input_tokens": 10000,
        "maximum_provider_output_tokens": 3000,
        "input_cost_usd_per_million_tokens": 1.0,
        "output_cost_usd_per_million_tokens": 2.0,
        "maximum_contract_cost_usd": 1.0,
    }
    values.update(overrides)
    return SolverExecutionBudgetV1(**values)


class SolverExecutionBudgetTest(unittest.TestCase):
    def test_provider_calls_are_hard_bounded(self) -> None:
        ledger = SolverExecutionBudgetLedger(_budget(maximum_provider_calls=2, maximum_agent_turns=2))
        self.assertEqual(ledger.before_call({"messages": ["a"]}).decision, "allow")
        ledger.after_call(input_tokens=10, output_tokens=10)
        self.assertEqual(ledger.before_call({"messages": ["b"]}).decision, "allow")
        ledger.after_call(input_tokens=10, output_tokens=10)
        blocked = ledger.before_call({"messages": ["c"]})
        self.assertEqual(blocked.reason, "provider_call_ceiling_reached")
        self.assertEqual(ledger.usage.provider_calls, 2)

    def test_request_bytes_and_completion_reservation_fail_before_call(self) -> None:
        request_block = SolverExecutionBudgetLedger(
            _budget(maximum_request_bytes_per_call=1024)
        ).before_call({"messages": ["x" * 2000]})
        self.assertEqual(request_block.reason, "request_byte_ceiling_exceeded")
        cost_block = SolverExecutionBudgetLedger(
            _budget(maximum_contract_cost_usd=0.0001)
        ).before_call({"messages": ["small"]})
        self.assertEqual(cost_block.reason, "contract_cost_reservation_exceeded")

    def test_reported_usage_cannot_exceed_token_ceiling(self) -> None:
        ledger = SolverExecutionBudgetLedger(_budget(maximum_provider_input_tokens=20))
        self.assertEqual(ledger.before_call({"m": "x"}).decision, "allow")
        with self.assertRaisesRegex(RuntimeError, "input_token_ceiling"):
            ledger.after_call(input_tokens=21, output_tokens=1)

    def test_max_turns_cannot_exceed_calls(self) -> None:
        with self.assertRaisesRegex(ValueError, "agent_turns_exceed"):
            _budget(maximum_provider_calls=2, maximum_agent_turns=3)

    def test_missing_finish_or_delivery_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outcome = inspect_solver_process_outcome(
                solver_model="test-model",
                output_root=root,
                budget=_budget(),
                usage=SolverExecutionBudgetLedger(_budget()).usage,
                finish_signal_received=False,
            )
            self.assertEqual(outcome.process_status, "failed")
            self.assertEqual(outcome.first_failure, "finish_signal_missing")

    def test_finish_and_real_file_are_required_for_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deliverable = root / "deliverable_files" / "result.xlsx"
            deliverable.parent.mkdir(parents=True)
            deliverable.write_bytes(b"xlsx")
            budget = _budget()
            outcome = inspect_solver_process_outcome(
                solver_model="test-model",
                output_root=root,
                budget=budget,
                usage=SolverExecutionBudgetLedger(budget).usage,
                finish_signal_received=True,
                expected_deliverable_paths=["deliverable_files/result.xlsx"],
            )
            self.assertEqual(outcome.process_status, "succeeded")
            self.assertEqual(outcome.deliverable_file_count, 1)
            self.assertIsNotNone(outcome.output_tree_sha256)

    def test_nested_hash_directory_fails_exact_delivery_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            misplaced = root / "deliverable_files" / "random-hash" / "result.xlsx"
            misplaced.parent.mkdir(parents=True)
            misplaced.write_bytes(b"xlsx")
            budget = _budget()
            outcome = inspect_solver_process_outcome(
                solver_model="test-model",
                output_root=root,
                budget=budget,
                usage=SolverExecutionBudgetLedger(budget).usage,
                finish_signal_received=True,
                expected_deliverable_paths=["deliverable_files/result.xlsx"],
            )
            self.assertEqual(outcome.process_status, "failed")
            self.assertEqual(
                outcome.first_failure,
                "exact_deliverable_contract_not_satisfied",
            )

    def test_fake_xlsx_extension_fails_openable_delivery_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = SolverToolPreflight().create_fixture(root)
            created = root / "deliverable_files" / "created_workbook.xlsx"
            edited = root / "deliverable_files" / "edited_template.xlsx"
            created.write_text("created_marker", encoding="utf-8")
            edited.write_text("template_marker", encoding="utf-8")
            budget = _budget()
            outcome = inspect_solver_process_outcome(
                solver_model="test-model",
                output_root=root,
                budget=budget,
                usage=SolverExecutionBudgetLedger(budget).usage,
                finish_signal_received=True,
                expected_deliverable_paths=[
                    "deliverable_files/created_workbook.xlsx",
                    "deliverable_files/edited_template.xlsx",
                ],
                deliverable_contract_path=fixture["contract_path"],
            )
            self.assertEqual(outcome.process_status, "failed")
            self.assertEqual(
                outcome.first_failure,
                "openable_deliverable_contract_not_satisfied",
            )

    def test_legacy_hash_delivery_is_normalized_only_by_exact_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashed = root / "deliverable_files" / ("a" * 32) / "result.xlsx"
            hashed.parent.mkdir(parents=True)
            hashed.write_bytes(b"xlsx")
            (root / "dataset_row.json").write_text(
                json.dumps({"deliverable_files": [hashed.relative_to(root).as_posix()]}),
                encoding="utf-8",
            )
            _normalize_legacy_hash_delivery(
                root, ["deliverable_files/result.xlsx"]
            )
            self.assertTrue((root / "deliverable_files" / "result.xlsx").is_file())
            self.assertFalse(hashed.exists())
            row = json.loads((root / "dataset_row.json").read_text(encoding="utf-8"))
            self.assertEqual(row["deliverable_files"], ["deliverable_files/result.xlsx"])

    def test_wrapper_does_not_treat_normal_return_without_finish_as_success(self) -> None:
        async def fake_run(case_dir, output_run_dir, model, template):
            (output_run_dir / "deliverable_files").mkdir(parents=True)

        fake_module = SimpleNamespace(_run_async=fake_run)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = root / "input"
            case.mkdir()
            (case / "dataset_row.json").write_text(
                json.dumps({"deliverable_files": ["deliverable_files/result.xlsx"]}),
                encoding="utf-8",
            )
            fake_module.DATASET_ROW_FILENAME = "dataset_row.json"
            with patch(
                "src.task_generator.v3_rw_task_eval_stirrup_wrapper._install_governed_stirrup_runtime",
                return_value=lambda: None,
            ):
                passed = _run_single_case(
                    stirrup_batch_module=fake_module,
                    case_dir=case,
                    output_run_dir=root / "output",
                    log_file=root / "run.log",
                    model="test-model",
                    e2b_template="test",
                    budget=_budget(),
                )
            self.assertFalse(passed)
            outcome = (root / "output" / "solver_process_outcome.json").read_text(
                encoding="utf-8"
            )
            self.assertIn("finish_signal_missing", outcome)

    def test_wrapper_requires_nonempty_deliverable_even_with_finish(self) -> None:
        async def fake_run(case_dir, output_run_dir, model, template):
            (output_run_dir / "deliverable_files").mkdir(parents=True)

        def install(_budget, _ledger, finish_state):
            finish_state["received"] = True
            return lambda: None

        fake_module = SimpleNamespace(_run_async=fake_run)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = root / "input"
            case.mkdir()
            (case / "dataset_row.json").write_text(
                json.dumps({"deliverable_files": ["deliverable_files/result.xlsx"]}),
                encoding="utf-8",
            )
            fake_module.DATASET_ROW_FILENAME = "dataset_row.json"
            with patch(
                "src.task_generator.v3_rw_task_eval_stirrup_wrapper._install_governed_stirrup_runtime",
                side_effect=install,
            ):
                passed = _run_single_case(
                    stirrup_batch_module=fake_module,
                    case_dir=case,
                    output_run_dir=root / "output",
                    log_file=root / "run.log",
                    model="test-model",
                    e2b_template="test",
                    budget=_budget(),
                )
            self.assertFalse(passed)
            outcome = (root / "output" / "solver_process_outcome.json").read_text(
                encoding="utf-8"
            )
            self.assertIn("nonempty_deliverable_missing", outcome)

    def test_governed_client_bypasses_retries_and_blocks_third_call(self) -> None:
        init_kwargs = []

        async def raw_generate(self, messages, tools):
            return SimpleNamespace(
                content="working",
                tool_calls=[],
                reasoning=None,
                token_usage=SimpleNamespace(
                    input=10, output=5, answer=5, reasoning=0
                ),
            )

        async def decorated_generate(self, messages, tools):
            raise AssertionError("decorated retry path must not execute")

        decorated_generate.__wrapped__ = raw_generate

        class FakeClient:
            generate = decorated_generate

            def __init__(self, model, **kwargs):
                self._model = model
                self._max_tokens = kwargs["max_tokens"]
                init_kwargs.append(kwargs)

            @property
            def model_slug(self):
                return self._model

        class FakeSessionAgent:
            async def run(self, *args, **kwargs):
                return object(), [], {}

        client_module = SimpleNamespace(ChatCompletionsClient=FakeClient)
        budget = _budget(
            maximum_provider_calls=2,
            maximum_agent_turns=2,
            maximum_completion_tokens_per_call=256,
            maximum_provider_output_tokens=512,
        )
        ledger = SolverExecutionBudgetLedger(budget)
        finish_state = {"received": False}
        restore = _install_governed_stirrup_runtime(
            budget,
            ledger,
            finish_state,
            client_module_override=client_module,
            session_agent_class=FakeSessionAgent,
        )

        async def execute_probe():
            client = client_module.ChatCompletionsClient(model="test-model")
            await client.generate(["a"], {})
            await client.generate(["b"], {})
            with self.assertRaisesRegex(RuntimeError, "provider_call_ceiling"):
                await client.generate(["c"], {})
            await FakeSessionAgent().run("prompt")

        try:
            asyncio.run(execute_probe())
        finally:
            restore()
        self.assertEqual(init_kwargs[0]["max_retries"], 0)
        self.assertEqual(init_kwargs[0]["max_tokens"], budget.maximum_context_tokens)
        self.assertEqual(ledger.usage.provider_calls, 2)
        self.assertEqual(len(finish_state["protocol_observations"]), 2)
        self.assertTrue(
            all(
                item.disposition == "substantive"
                for item in finish_state["protocol_observations"]
            )
        )
        self.assertTrue(finish_state["received"])
        self.assertIs(client_module.ChatCompletionsClient, FakeClient)

    def test_governed_client_fails_fast_after_two_empty_protocol_shapes(self) -> None:
        observed_max_tokens = []

        async def raw_generate(self, messages, tools):
            observed_max_tokens.append(self._max_tokens)
            return SimpleNamespace(
                content="",
                tool_calls=[],
                reasoning=None,
                token_usage=SimpleNamespace(
                    input=10, output=8, answer=0, reasoning=8
                ),
            )

        async def decorated_generate(self, messages, tools):
            raise AssertionError("decorated retry path must not execute")

        decorated_generate.__wrapped__ = raw_generate

        class FakeClient:
            generate = decorated_generate

            def __init__(self, model, **kwargs):
                self._model = model
                self._max_tokens = kwargs["max_tokens"]

            @property
            def model_slug(self):
                return self._model

            @property
            def max_tokens(self):
                return self._max_tokens

        class FakeSessionAgent:
            async def run(self, *args, **kwargs):
                return None, [], {}

        client_module = SimpleNamespace(ChatCompletionsClient=FakeClient)
        budget = _budget(
            maximum_provider_calls=3,
            maximum_agent_turns=3,
            maximum_completion_tokens_per_call=256,
            maximum_provider_output_tokens=768,
            maximum_context_tokens=64000,
        )
        ledger = SolverExecutionBudgetLedger(budget)
        finish_state = {"received": False}
        restore = _install_governed_stirrup_runtime(
            budget,
            ledger,
            finish_state,
            client_module_override=client_module,
            session_agent_class=FakeSessionAgent,
        )

        async def execute_probe():
            client = client_module.ChatCompletionsClient(model="test-model")
            await client.generate(["a"], {})
            self.assertEqual(client.max_tokens, 64000)
            with self.assertRaisesRegex(
                RuntimeError, "consecutive_empty_assistant_responses"
            ):
                await client.generate(["b"], {})
            self.assertEqual(client.max_tokens, 64000)

        try:
            asyncio.run(execute_probe())
        finally:
            restore()
        self.assertEqual(observed_max_tokens, [256, 256])
        self.assertEqual(ledger.usage.provider_calls, 2)
        self.assertEqual(
            [
                item.consecutive_empty_responses
                for item in finish_state["protocol_observations"]
            ],
            [1, 2],
        )

    def test_official_deepseek_uses_max_tokens_adapter_without_retry(self) -> None:
        async def decorated_generate(self, messages, tools):
            raise AssertionError("generic chat-completions path must not execute")

        async def raw_generate(self, messages, tools):
            raise AssertionError("generic raw path must not execute")

        decorated_generate.__wrapped__ = raw_generate

        class FakeClient:
            generate = decorated_generate

            def __init__(self, model, **kwargs):
                self._model = model
                self._max_tokens = kwargs["max_tokens"]
                self._client = SimpleNamespace(base_url="https://api.deepseek.com/")

            @property
            def model_slug(self):
                return self._model

        class FakeSessionAgent:
            async def run(self, *args, **kwargs):
                return object(), [], {}

        async def deepseek_generate(client, messages, tools, max_tokens):
            self.assertEqual(max_tokens, 256)
            return SimpleNamespace(
                content="working",
                tool_calls=[SimpleNamespace(name="tool")],
                reasoning=None,
                token_usage=SimpleNamespace(input=12, output=5, answer=5, reasoning=0),
            )

        client_module = SimpleNamespace(ChatCompletionsClient=FakeClient)
        budget = _budget(
            solver_model="deepseek-v4-pro",
            maximum_provider_calls=1,
            maximum_agent_turns=1,
            maximum_completion_tokens_per_call=256,
            maximum_provider_output_tokens=256,
        )
        ledger = SolverExecutionBudgetLedger(budget)
        restore = _install_governed_stirrup_runtime(
            budget,
            ledger,
            {"received": False},
            client_module_override=client_module,
            session_agent_class=FakeSessionAgent,
        )
        try:
            with patch(
                "src.task_generator.v3_rw_task_eval_stirrup_wrapper._generate_official_deepseek",
                side_effect=deepseek_generate,
            ):
                asyncio.run(
                    client_module.ChatCompletionsClient(
                        model="deepseek-v4-pro"
                    ).generate(["message"], {"tool": object()})
                )
        finally:
            restore()
        self.assertEqual(ledger.usage.provider_calls, 1)

    def test_context_window_cannot_be_below_completion_ceiling(self) -> None:
        with self.assertRaisesRegex(ValueError, "context_window_below_completion"):
            _budget(
                maximum_completion_tokens_per_call=5000,
                maximum_context_tokens=4096,
            )


if __name__ == "__main__":
    unittest.main()
