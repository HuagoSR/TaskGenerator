import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_direct_source_collector import DirectWebSourceCollector  # noqa: E402
from task_generator.v3_source_collector import slugify, utc_now  # noqa: E402
from task_generator.v3_source_schema import dump_json_file  # noqa: E402


RW_TASK_ROOT = ROOT.parent / "rw-task"
DEFAULT_ENV_PATH = RW_TASK_ROOT / ".env"
DEFAULT_OUTPUT_ROOT = ROOT / "Test" / "v3_web_source_collections"


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError("python-dotenv is required in the taskgenerator environment.") from exc
    load_dotenv(path)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def main() -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(
        description="Collect public web source materials for V3 Pipeline A using direct deterministic code."
    )
    parser.add_argument("--topic", default="audit evidence reconciliation and internal control testing")
    parser.add_argument("--domain", action="append", default=["finance", "audit", "compliance"])
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--search-timeout-seconds", type=int, default=180)
    parser.add_argument("--fetch-timeout-seconds", type=int, default=180)
    parser.add_argument("--search-result-count", type=int, default=5)
    parser.add_argument("--serper-api-key-env", default="SERPER_API_KEY")
    parser.add_argument("--allow-web-collection", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env_file(args.env_path)
    if args.output_dir is None:
        stamp = utc_now().replace(":", "").replace("+", "_").replace(".", "_")
        args.output_dir = DEFAULT_OUTPUT_ROOT / f"{slugify(args.topic)}_{stamp}"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    collector = DirectWebSourceCollector(
        api_key=require_env(args.serper_api_key_env),
        search_timeout_seconds=args.search_timeout_seconds,
        fetch_timeout_seconds=args.fetch_timeout_seconds,
        search_result_count=args.search_result_count,
    )
    request = collector.build_request(
        topic=args.topic,
        domain_tags=args.domain,
        queries=args.query or [args.topic],
        source_count=args.limit,
    )
    dump_json_file(request, str(args.output_dir / "collection_request.json"))

    if args.dry_run:
        plan = {
            "status": "dry_run",
            "backend": "direct",
            "topic": args.topic,
            "queries": request.queries,
            "output_dir": str(args.output_dir),
            "note": "Dry run wrote the request only. No network calls were made.",
        }
        dump_json_file(plan, str(args.output_dir / "artifacts" / "direct_collection_plan.json"))
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    if not args.allow_web_collection:
        raise RuntimeError("Web source collection requires explicit --allow-web-collection.")

    result = collector.collect(output_dir=str(args.output_dir), request=request)
    report = result["report"]
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
