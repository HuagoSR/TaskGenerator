import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_source_collector import (  # noqa: E402
    build_collection_prompt,
    build_collection_request,
    records_from_payload,
    slugify,
    utc_now,
    write_collected_sources,
)
from v3_source_search_tools import SerperWebToolProvider  # noqa: E402
from v3_source_schema import dump_json_file  # noqa: E402


RW_TASK_ROOT = ROOT.parent / "rw-task"
DEFAULT_ENV_PATH = RW_TASK_ROOT / ".env"
DEFAULT_OUTPUT_ROOT = ROOT / "Test" / "v3_web_source_collections"
DEFAULT_E2B_TEMPLATE = "rw-task-sandbox:stable"


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError("python-dotenv is required in the real-world-task environment.") from exc
    load_dotenv(path)


def require_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def optional_model(cli_model: str | None) -> str:
    return cli_model or os.getenv("AGENT_MODEL") or os.getenv("STIRRUP_OPENAI_MODEL") or "gpt-5-mini"


def extract_json_payload(value: Any) -> Dict[str, Any]:
    if value is None:
        raise ValueError("Stirrup finish params are empty.")
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    elif not isinstance(value, (dict, list, str)):
        value = vars(value)

    if isinstance(value, dict):
        for key in ("sources", "manifest", "result", "json", "payload", "answer", "content", "text"):
            if key in value:
                nested = value[key]
                if key == "sources":
                    return {"sources": nested}
                if isinstance(nested, str):
                    return json.loads(nested)
                if isinstance(nested, dict):
                    return nested
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        return json.loads(text)
    raise ValueError("Could not parse Stirrup finish params as JSON.")


def load_artifact_manifest(artifacts_dir: Path) -> Dict[str, Any] | None:
    for name in ("source_manifest.json", "collection_manifest.json", "sources.json"):
        path = artifacts_dir / name
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def build_web_tool_provider(args: argparse.Namespace):
    if args.search_backend == "serper":
        require_env(args.serper_api_key_env)
        return SerperWebToolProvider(
            api_key_env=args.serper_api_key_env,
            timeout=args.web_timeout_seconds,
            num_results=args.search_result_count,
        )
    from stirrup.tools import WebToolProvider

    require_env("BRAVE_API_KEY")
    return WebToolProvider(timeout=args.web_timeout_seconds)


async def run_stirrup_collection(args: argparse.Namespace, prompt: str) -> Dict[str, Any]:
    if str(RW_TASK_ROOT) not in sys.path:
        sys.path.insert(0, str(RW_TASK_ROOT))

    from stirrup import Agent, aggregate_metadata
    from stirrup.clients.chat_completions_client import ChatCompletionsClient
    from stirrup.tools import ViewImageToolProvider
    from stirrup.tools.code_backends.e2b import E2BCodeExecToolProvider

    api_key = (
        os.getenv("AGENT_API_KEY")
        or os.getenv("STIRRUP_OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    base_url = (
        os.getenv("AGENT_BASE_URL")
        or os.getenv("STIRRUP_OPENAI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    if not api_key:
        raise RuntimeError("Set AGENT_API_KEY or STIRRUP_OPENAI_API_KEY in the env file.")
    require_env("E2B_API_KEY")

    client = ChatCompletionsClient(
        base_url=base_url,
        model=args.model,
        api_key=api_key,
        max_tokens=args.max_tokens,
    )
    agent = Agent(
        client=client,
        name="v3_source_collector_agent",
        max_turns=args.max_turns,
        tools=[
            E2BCodeExecToolProvider(template=args.e2b_template, timeout=args.e2b_timeout_seconds),
            build_web_tool_provider(args),
            ViewImageToolProvider(),
        ],
    )

    artifacts_dir = args.output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    async with agent.session(output_dir=str(artifacts_dir)) as session:
        finish_params, history, metadata = await session.run(prompt)
    return {
        "finish_params": finish_params,
        "history_turn_count": len(history),
        "metadata": aggregate_metadata(metadata),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="Collect public web source materials for V3 Pipeline A using Stirrup/E2B.")
    parser.add_argument("--topic", default="audit evidence reconciliation and internal control testing")
    parser.add_argument("--domain", action="append", default=["finance", "audit", "compliance"], help="Domain tag. Can be repeated.")
    parser.add_argument("--query", action="append", default=[], help="Suggested web query. Can be repeated.")
    parser.add_argument("--limit", type=int, default=3, help="Target source count.")
    parser.add_argument("--model", default=None, help="Override AGENT_MODEL from env.")
    parser.add_argument("--e2b-template", default=DEFAULT_E2B_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--e2b-timeout-seconds", type=int, default=1800)
    parser.add_argument("--web-timeout-seconds", type=int, default=180)
    parser.add_argument("--search-result-count", type=int, default=5)
    parser.add_argument("--search-backend", choices=["serper", "brave"], default="serper")
    parser.add_argument("--serper-api-key-env", default="SERPER_API_KEY")
    parser.add_argument("--allow-web-collection", action="store_true")
    parser.add_argument("--dry-run-prompt", action="store_true", help="Write request and prompt only; do not call Stirrup.")
    args = parser.parse_args()

    load_env_file(args.env_path)
    args.model = optional_model(args.model)
    if args.output_dir is None:
        stamp = utc_now().replace(":", "").replace("+", "_").replace(".", "_")
        args.output_dir = DEFAULT_OUTPUT_ROOT / f"{slugify(args.topic)}_{stamp}"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    request = build_collection_request(
        topic=args.topic,
        domain_tags=args.domain,
        queries=args.query,
        source_count=args.limit,
        collector_model=args.model,
        e2b_template=args.e2b_template,
        search_backend=args.search_backend,
    )
    prompt = build_collection_prompt(request)
    dump_json_file(request, str(args.output_dir / "collection_request.json"))
    (args.output_dir / "source_collection_prompt.md").write_text(prompt, encoding="utf-8")

    if args.dry_run_prompt:
        print(json.dumps({"status": "dry_run_prompt", "output_dir": str(args.output_dir)}, ensure_ascii=False, indent=2))
        return
    if not args.allow_web_collection:
        raise RuntimeError("Web source collection requires explicit --allow-web-collection.")

    run_result = asyncio.run(run_stirrup_collection(args, prompt))
    write_json(
        args.output_dir / "artifacts" / "stirrup_collection_metadata.json",
        {
            "history_turn_count": run_result["history_turn_count"],
            "metadata": run_result["metadata"],
            "search_backend": args.search_backend,
        },
    )
    payload = load_artifact_manifest(args.output_dir / "artifacts") or extract_json_payload(run_result["finish_params"])
    write_json(args.output_dir / "artifacts" / "source_manifest_from_finish.json", payload)
    records = records_from_payload(payload)
    report = write_collected_sources(args.output_dir, request, records)
    dump_json_file(report, str(args.output_dir / "collection_report.json"))
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
