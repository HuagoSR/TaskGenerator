from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import traceback
from time import perf_counter
from pathlib import Path

from .v3_solver_execution_budget import (
    SolverProtocolObservationV1,
    SolverExecutionBudgetLedger,
    SolverExecutionBudgetV1,
    SolverProcessOutcomeV1,
    inspect_solver_process_outcome,
)


MODEL_MAX_TOKENS_OVERRIDES: dict[str, int] = {
    "gpt-4o-mini": 16384,
}

DEFAULT_MAX_TOKENS = 64000


def resolve_stirrup_max_tokens(model: str) -> int:
    return MODEL_MAX_TOKENS_OVERRIDES.get(model, DEFAULT_MAX_TOKENS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for rw-task bench_standalone.stirrup_batch with model-aware max token overrides."
    )
    parser.add_argument("input_path")
    parser.add_argument("--output", required=True)
    parser.add_argument("-w", "--workers", type=int, default=1)
    parser.add_argument("--model", required=True)
    parser.add_argument("--e2b-template", default="rw-task-sandbox:stable")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument(
        "--budget-contract",
        type=Path,
        default=None,
        help=(
            "Opt-in fail-closed solver budget. Disables SDK/Tenacity retries, "
            "hard-bounds calls/turns/tokens/contract cost, and requires a finish "
            "signal plus a nonempty deliverable."
        ),
    )
    args = parser.parse_args()

    rw_task_root = Path(r"E:\THU\2026Spring\SRT\rw-task")
    if str(rw_task_root) not in sys.path:
        sys.path.insert(0, str(rw_task_root))

    from bench_standalone import stirrup_batch as stirrup_batch_module

    budget = None
    if args.budget_contract:
        budget = SolverExecutionBudgetV1.model_validate_json(
            args.budget_contract.read_text(encoding="utf-8")
        )
        if budget.solver_model != args.model:
            raise SystemExit("budget_contract_solver_model_mismatch")
        if args.max_tokens and args.max_tokens != budget.maximum_completion_tokens_per_call:
            raise SystemExit("budget_contract_completion_token_mismatch")
        stirrup_batch_module.MAX_TURN = budget.maximum_agent_turns
        # Stirrup uses MAX_TOKENS as the model context window and separately
        # passes it into the client. Keep the context semantic here; the
        # governed client applies the completion ceiling only during a call.
        stirrup_batch_module.MAX_TOKENS = budget.maximum_context_tokens
    else:
        stirrup_batch_module.MAX_TOKENS = args.max_tokens or resolve_stirrup_max_tokens(args.model)
    input_path = Path(args.input_path).resolve()
    output_batch_dir = Path(args.output).resolve()
    output_batch_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_batch_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    test_cases = stirrup_batch_module.find_test_cases(input_path)
    if not test_cases:
        raise SystemExit(f"Error: no test cases found in {input_path}")

    print(f"[Wrapper] Output directory : {output_batch_dir}")
    print(f"Input directory  : {input_path}")
    print(f"Test cases found : {len(test_cases)}")
    print(f"Workers          : {args.workers}")
    print(f"Model            : {args.model}")
    print(f"E2B template     : {args.e2b_template}")
    print()

    succeeded = 0
    failed = 0
    skipped = 0
    for case_dir in test_cases:
        with open(case_dir / stirrup_batch_module.DATASET_ROW_FILENAME, encoding="utf-8") as f:
            task_id = json.load(f)["task_id"]
        safe = stirrup_batch_module._safe_name(case_dir.name)
        output_run_dir = output_batch_dir / f"run_{safe}"
        log_file = log_dir / f"{safe}.txt"
        if budget and output_run_dir.exists():
            outcome_path = output_run_dir / "solver_process_outcome.json"
            if outcome_path.is_file():
                try:
                    prior = SolverProcessOutcomeV1.model_validate_json(
                        outcome_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    prior = None
                if (
                    prior is not None
                    and prior.solver_model == args.model
                    and prior.budget == budget
                    and prior.process_status == "succeeded"
                ):
                    print(f"  [SKIP] {task_id}  ({case_dir.name})")
                    skipped += 1
                    continue
            print(f"  [FAIL] {task_id}  (governed output collision or prior failure)")
            failed += 1
            continue
        if not budget and stirrup_batch_module.is_completed(output_run_dir):
            print(f"  [SKIP] {task_id}  ({case_dir.name})")
            skipped += 1
            continue
        ok = _run_single_case(
            stirrup_batch_module=stirrup_batch_module,
            case_dir=case_dir,
            output_run_dir=output_run_dir,
            log_file=log_file,
            model=args.model,
            e2b_template=args.e2b_template,
            budget=budget,
        )
        if ok:
            succeeded += 1
            print(f"  [OK  ] {task_id}")
        else:
            failed += 1
            print(f"  [FAIL] {task_id}  (see logs/{log_file.name})")

    print()
    print("=== Batch Run Complete ===")
    print(f"Total    : {len(test_cases)}")
    print(f"Skipped  : {skipped}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed   : {failed}")
    print(f"Output   : {output_batch_dir}")
    print(f"Logs     : {log_dir}")
    if budget is not None and failed:
        raise SystemExit(1)


def _run_single_case(
    stirrup_batch_module,
    case_dir: Path,
    output_run_dir: Path,
    log_file: Path,
    model: str,
    e2b_template: str,
    budget: SolverExecutionBudgetV1 | None = None,
) -> bool:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    ledger = SolverExecutionBudgetLedger(budget) if budget else None
    expected_deliverable_paths = None
    if budget:
        dataset_row = json.loads(
            (case_dir / stirrup_batch_module.DATASET_ROW_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        expected_deliverable_paths = dataset_row.get("deliverable_files")
        if not isinstance(expected_deliverable_paths, list) or not all(
            isinstance(item, str) and item.startswith("deliverable_files/")
            for item in expected_deliverable_paths
        ):
            raise ValueError("governed_expected_deliverable_paths_invalid")
    finish_state = {"received": False, "protocol_observations": []}
    restore = (
        _install_governed_stirrup_runtime(budget, ledger, finish_state)
        if budget and ledger
        else lambda: None
    )
    process_error: str | None = None
    with open(log_file, "w", encoding="utf-8", buffering=1) as log:
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = log
        sys.stderr = log
        try:
            asyncio.run(stirrup_batch_module._run_async(case_dir, output_run_dir, model, e2b_template))
            if expected_deliverable_paths is not None:
                _normalize_legacy_hash_delivery(
                    output_run_dir, expected_deliverable_paths
                )
        except Exception as exc:
            process_error = str(exc)
            print(f"\n[ERROR] {exc}")
            traceback.print_exc()
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            restore()
    if budget and ledger:
        if process_error and process_error.startswith("solver_budget_blocked:"):
            process_error = f"budget:{process_error}"
        outcome = inspect_solver_process_outcome(
            solver_model=model,
            output_root=output_run_dir,
            budget=budget,
            usage=ledger.usage,
            finish_signal_received=finish_state["received"],
            process_error=process_error,
            expected_deliverable_paths=expected_deliverable_paths,
            deliverable_contract_path=case_dir / "deliverable_contract.json",
            protocol_observations=finish_state["protocol_observations"],
        )
        outcome_path = output_run_dir / "solver_process_outcome.json"
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
        return outcome.process_status == "succeeded"
    return process_error is None


def _normalize_legacy_hash_delivery(
    output_run_dir: Path, expected_deliverable_paths: list[str]
) -> None:
    """Remove rw-task's legacy MD5 directory only when mapping is unambiguous."""

    deliverable_root = output_run_dir / "deliverable_files"
    observed = sorted(item for item in deliverable_root.rglob("*") if item.is_file())
    expected = [output_run_dir / Path(item) for item in expected_deliverable_paths]
    if {item.relative_to(output_run_dir).as_posix() for item in observed} == set(
        expected_deliverable_paths
    ):
        return
    if len(observed) != len(expected):
        return
    mapping: list[tuple[Path, Path]] = []
    for target in expected:
        candidates = [item for item in observed if item.name == target.name]
        if len(candidates) != 1:
            return
        source = candidates[0]
        if (
            source.parent.parent != deliverable_root
            or re.fullmatch(r"[0-9a-f]{32}", source.parent.name) is None
        ):
            return
        mapping.append((source, target))
    for source, target in mapping:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
    for directory in sorted(deliverable_root.iterdir()):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    output_row = output_run_dir / "dataset_row.json"
    if output_row.is_file():
        row = json.loads(output_row.read_text(encoding="utf-8"))
        row["deliverable_files"] = expected_deliverable_paths
        output_row.write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _install_governed_stirrup_runtime(
    budget: SolverExecutionBudgetV1,
    ledger: SolverExecutionBudgetLedger,
    finish_state: dict[str, bool],
    *,
    client_module_override=None,
    session_agent_class=None,
):
    """Patch only the current process and return an idempotent restore callback."""
    finish_state.setdefault("protocol_observations", [])
    if client_module_override is None or session_agent_class is None:
        import stirrup.clients.chat_completions_client as client_module
        from stirrup.core.agent import SessionAgent
    else:
        client_module = client_module_override
        SessionAgent = session_agent_class

    base_client = client_module.ChatCompletionsClient
    original_session_run = SessionAgent.run
    raw_generate = getattr(base_client.generate, "__wrapped__", None)
    if raw_generate is None:
        raise RuntimeError("stirrup_generate_retry_bypass_unavailable")

    class GovernedChatCompletionsClient(base_client):
        def __init__(self, *args, **kwargs):
            kwargs["max_retries"] = 0
            kwargs["max_tokens"] = budget.maximum_context_tokens
            super().__init__(*args, **kwargs)
            self._governed_empty_response_streak = 0

        async def generate(self, messages, tools):
            is_official_deepseek = str(getattr(getattr(self, "_client", None), "base_url", "")).rstrip("/").startswith(
                "https://api.deepseek.com"
            ) and self.model_slug == "deepseek-v4-pro"
            payload = {
                "model": self.model_slug,
                "messages": messages,
                "tools": tools,
                (
                    "max_tokens"
                    if is_official_deepseek
                    else "max_completion_tokens"
                ): budget.maximum_completion_tokens_per_call,
            }
            decision = ledger.before_call(payload)
            if decision.decision != "allow":
                raise RuntimeError(f"solver_budget_blocked:{decision.reason}")
            # The installed Stirrup ChatCompletions client currently uses its
            # `max_tokens` context property as `max_completion_tokens` too.
            # Temporarily narrow only the provider call, then restore the true
            # context window used by Agent.run() summarization decisions.
            context_tokens = self._max_tokens
            self._max_tokens = budget.maximum_completion_tokens_per_call
            try:
                response = (
                    await _generate_official_deepseek(
                        self,
                        messages,
                        tools,
                        budget.maximum_completion_tokens_per_call,
                    )
                    if is_official_deepseek
                    else await raw_generate(self, messages, tools)
                )
            finally:
                self._max_tokens = context_tokens
            ledger.after_call(
                input_tokens=response.token_usage.input,
                output_tokens=response.token_usage.output,
            )
            has_content = _response_has_content(response.content)
            has_tool_calls = bool(response.tool_calls)
            reasoning = getattr(response, "reasoning", None)
            has_reasoning = bool(
                reasoning
                and _response_has_content(getattr(reasoning, "content", reasoning))
            )
            substantive = has_content or has_tool_calls or has_reasoning
            self._governed_empty_response_streak = (
                0 if substantive else self._governed_empty_response_streak + 1
            )
            finish_state["protocol_observations"].append(
                SolverProtocolObservationV1(
                    provider_call=ledger.usage.provider_calls,
                    has_content=has_content,
                    has_tool_calls=has_tool_calls,
                    has_reasoning=has_reasoning,
                    input_tokens=response.token_usage.input,
                    answer_tokens=getattr(
                        response.token_usage,
                        "answer",
                        getattr(response.token_usage, "output", 0),
                    ),
                    reasoning_tokens=getattr(response.token_usage, "reasoning", 0),
                    consecutive_empty_responses=self._governed_empty_response_streak,
                    disposition=(
                        "substantive" if substantive else "empty_protocol_shape"
                    ),
                )
            )
            if (
                self._governed_empty_response_streak
                >= budget.maximum_consecutive_empty_assistant_responses
            ):
                raise RuntimeError(
                    "solver_protocol_blocked:consecutive_empty_assistant_responses"
                )
            return response

    async def governed_session_run(self, *args, **kwargs):
        result = await original_session_run(self, *args, **kwargs)
        finish_state["received"] = result[0] is not None
        return result

    client_module.ChatCompletionsClient = GovernedChatCompletionsClient
    SessionAgent.run = governed_session_run
    restored = False

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        client_module.ChatCompletionsClient = base_client
        SessionAgent.run = original_session_run
        restored = True

    return restore


async def _generate_official_deepseek(client, messages, tools, max_tokens: int):
    """Single-attempt non-thinking tool call for the official DeepSeek endpoint."""

    from stirrup.clients.utils import to_openai_messages, to_openai_tools
    from stirrup.core.models import AssistantMessage, Reasoning, TokenUsage, ToolCall

    request = {
        "model": client.model_slug,
        "messages": to_openai_messages(messages),
        "max_tokens": max_tokens,
    }
    if tools:
        request["tools"] = to_openai_tools(tools)
        request["tool_choice"] = "auto"
    started = perf_counter()
    response = await client._client.chat.completions.create(**request)
    finished = perf_counter()
    choice = response.choices[0]
    message = choice.message
    reasoning_content = getattr(message, "reasoning_content", None)
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    reasoning_tokens = 0
    if usage and getattr(usage, "completion_tokens_details", None):
        reasoning_tokens = (
            getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0
        )
    return AssistantMessage(
        reasoning=(
            Reasoning(content=reasoning_content) if reasoning_content else None
        ),
        content=message.content or "",
        tool_calls=[
            ToolCall(
                tool_call_id=item.id,
                name=item.function.name,
                arguments=item.function.arguments or "",
            )
            for item in (message.tool_calls or [])
        ],
        token_usage=TokenUsage(
            input=input_tokens,
            answer=max(0, output_tokens - reasoning_tokens),
            reasoning=reasoning_tokens,
        ),
        request_start_time=started,
        request_end_time=finished,
    )


def _response_has_content(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return bool(value)


if __name__ == "__main__":
    main()
