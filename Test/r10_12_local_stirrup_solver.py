"""Run one fixed GDPval-shape assignment with the legacy Stirrup tool loop."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


# Common output ceiling accepted by the smaller Tuzi routes. Stirrup sends
# this value as max_completion_tokens, so the previous 64k was rejected
# before smaller Tuzi routes could return a first response.
MAX_TOKENS = 8_192
CONTEXT_WINDOW_TOKENS = 64_000
TEMPLATE = "rw-task-sandbox:stable"

# Rich 13 can select its legacy Windows renderer even when the controller is
# capturing pipes.  Force a lossless UTF-8 stream before Stirrup imports it;
# otherwise its session banner (which contains ▶) can fail before E2B starts.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_event(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


async def _run(args: argparse.Namespace) -> None:
    rw_root = args.rw_task_root.resolve()
    sys.path.insert(0, str(rw_root))
    from stirrup import Agent, aggregate_metadata
    from stirrup.clients.chat_completions_client import ChatCompletionsClient
    from stirrup.constants import FINISH_TOOL_NAME
    from stirrup.tools import ViewImageToolProvider, WebToolProvider
    from stirrup.tools.code_backends.e2b import E2BCodeExecToolProvider

    from bench_standalone.prompt import build_task_prompt

    case_dir = args.case_dir.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"r10_12_solver_output_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    marker = output_dir / "phase.json"
    _write(marker, {"phase": "initializing", "semantic_phase_started": False, "at": _now()})

    row = json.loads((case_dir / "dataset_row.json").read_text(encoding="utf-8"))
    references = row.get("reference_files") or []
    if not isinstance(references, list):
        raise ValueError("r10_12_reference_files_must_be_array")
    absolute_references = [(case_dir / str(value)).resolve() for value in references]
    if any(not path.is_file() for path in absolute_references):
        raise FileNotFoundError("r10_12_reference_file_missing")
    sample = {
        "task_id": row["task_id"],
        "prompt": row["prompt"],
        "reference_files": [str(path) for path in absolute_references],
    }
    api_key = os.getenv("AGENT_API_KEY") or os.getenv("STIRRUP_OPENAI_API_KEY")
    base_url = os.getenv("AGENT_BASE_URL") or os.getenv("STIRRUP_OPENAI_BASE_URL")
    e2b_key = os.getenv("E2B_API_KEY")
    if not api_key or not base_url or not e2b_key:
        raise RuntimeError("r10_12_required_secret_environment_missing")

    request_client = ChatCompletionsClient(
        base_url=base_url.rstrip("/"), model=args.model, api_key=api_key, max_tokens=MAX_TOKENS,
    )
    progress = output_dir / "progress.jsonl"
    sdk_create = request_client._client.chat.completions.create
    request_number = 0

    async def create_with_sanitized_metadata(**kwargs):
        response = await sdk_create(**kwargs)
        usage = response.usage
        _append_event(progress, {
            "event": "provider_response_metadata",
            "request_number": request_number,
            "endpoint": "/v1/chat/completions",
            "requested_model": args.model,
            "response_model": getattr(response, "model", None),
            "response_object": getattr(response, "object", None),
            "request_id": getattr(response, "_request_id", None),
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
            },
            "at": _now(),
        })
        return response

    request_client._client.chat.completions.create = create_with_sanitized_metadata
    original_generate = request_client.generate

    async def generate_with_progress(messages, tools):
        nonlocal request_number
        request_number += 1
        _append_event(progress, {
            "event": "model_request_started", "request_number": request_number,
            "message_count": len(messages), "tool_count": len(tools), "at": _now(),
        })
        try:
            response = await original_generate(messages, tools)
        except Exception as exc:
            _append_event(progress, {
                "event": "model_request_failed", "request_number": request_number,
                "error_type": type(exc).__name__, "at": _now(),
            })
            raise
        _append_event(progress, {
            "event": "model_request_completed", "request_number": request_number,
            "tool_calls": [call.name for call in response.tool_calls], "at": _now(),
        })
        return response

    class ContextWindowClient:
        """Expose context capacity separately from the provider output ceiling."""

        max_tokens = CONTEXT_WINDOW_TOKENS
        model_slug = request_client.model_slug

        async def generate(self, messages, tools):
            return await generate_with_progress(messages, tools)

    agent = Agent(
        client=ContextWindowClient(),
        name="r10_12_uniform_stirrup_agent",
        max_turns=args.max_turns,
        tools=[
            E2BCodeExecToolProvider(template=TEMPLATE, timeout=1800),
            WebToolProvider(),
            ViewImageToolProvider(),
        ],
    )
    deliverables = output_dir / "deliverable_files"
    deliverables.mkdir()
    prompt = build_task_prompt(sample, finish_tool_name=FINISH_TOOL_NAME)
    async with agent.session(output_dir=str(deliverables), input_files=[str(path) for path in absolute_references]) as session:
        _write(marker, {"phase": "semantic", "semantic_phase_started": True, "at": _now()})
        _append_event(progress, {"event": "session_run_started", "at": _now()})
        finish_params, history, metadata = await session.run(prompt)
        _append_event(progress, {"event": "session_run_completed", "turn_count": len(history), "at": _now()})

    reference_names = {path.name for path in absolute_references}
    for path in list(deliverables.rglob("*")):
        if path.is_file() and path.name in reference_names:
            path.unlink()
    for path in list(deliverables.iterdir()):
        if path.is_file():
            digest = hashlib.md5(path.read_bytes()).hexdigest()  # GDPval-compatible rw-task layout.
            target = deliverables / digest
            target.mkdir(exist_ok=True)
            path.replace(target / path.name)
    generated = sorted(
        path.relative_to(output_dir).as_posix() for path in deliverables.rglob("*") if path.is_file()
    )
    copied_row = dict(row)
    copied_row["deliverable_files"] = generated
    _write(output_dir / "dataset_row.json", copied_row)
    source_references = case_dir / "reference_files"
    if source_references.is_dir():
        shutil.copytree(source_references, output_dir / "reference_files")
    finish_value = finish_params.model_dump(mode="json") if hasattr(finish_params, "model_dump") else vars(finish_params)
    _write(output_dir / "solver_result.json", {
        "result_version": "r10.stirrup_solver_raw_result.1",
        "task_id": row["task_id"],
        "model_id": args.model,
        "max_turns": args.max_turns,
        "turn_count": len(history),
        "deliverable_files": generated,
        "finish": finish_value,
        "metadata": aggregate_metadata(metadata),
        "completed_at": _now(),
    })
    _write(marker, {"phase": "completed", "semantic_phase_started": True, "at": _now()})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--rw-task-root", type=Path, required=True)
    parser.add_argument("--max-turns", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.max_turns <= 100:
        raise SystemExit("max-turns must be in 1..100")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
