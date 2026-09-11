"""The public, offline-only TaskGenerator command-line interface."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from task_generator.cli.config import CliInputError, load_local_config, load_preview_spec
from task_generator.cli.readers import UnsupportedArtifactError, discover, inspect_path, markdown_report


VERSION = "0.1.0"


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        if not getattr(args, "command", None):
            parser.print_help()
            raise SystemExit(2)
        config = load_local_config(args.config) if getattr(args, "config", None) else None
        result = _dispatch(args, config)
        _emit(result, args, parser)
    except (CliInputError, UnsupportedArtifactError) as exc:
        _emit_error(str(exc), 2 if isinstance(exc, CliInputError) else 3, getattr(locals().get("args", None), "json", False))
    except BrokenPipeError:
        raise SystemExit(0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TaskGenerator 的公开、只读离线入口。")
    parser.add_argument("--version", action="version", version=f"taskgen {VERSION}")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--config", type=Path, help="本地只读配置 JSON")
    sub = parser.add_subparsers(dest="command")
    for name, help_text in (("doctor", "检查本地只读能力"), ("runs", "发现运行记录"), ("inspect", "读取受支持对象"), ("report", "生成只读摘要"), ("generate", "预览未来生产"), ("evaluate", "预览未来诊断")):
        child = sub.add_parser(name, help=help_text, parents=[_common_parser()])
        if name == "runs":
            child.add_argument("--root", type=Path, required=True)
        elif name in {"inspect", "report"}:
            child.add_argument("path", type=Path)
            if name == "report":
                child.add_argument("--format", choices=["terminal", "json", "markdown"], default="terminal")
                child.add_argument("--output", type=Path)
        elif name in {"generate", "evaluate"}:
            child.add_argument("--spec", type=Path, required=True)
            child.add_argument("--dry-run", action="store_true", required=True)
    return parser


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--version", action="version", version=f"taskgen {VERSION}")
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="输出 JSON")
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="本地只读配置 JSON")
    return parser


def _dispatch(args: argparse.Namespace, config: Any) -> dict[str, Any]:
    if args.command == "doctor":
        return {"kind": "doctor", "version": VERSION, "python": sys.version.split()[0], "platform": platform.platform(), "config_loaded": config is not None, "capabilities": {"network": "not_used", "provider": "not_used", "ssh": "not_used", "e2b": "not_used", "read_only_cli": "available"}}
    if args.command == "runs":
        return {"kind": "runs", "root": str(args.root.resolve()), "runs": discover(args.root)}
    if args.command == "inspect":
        return inspect_path(args.path)
    if args.command == "report":
        projection = inspect_path(args.path)
        rendered = markdown_report(projection) if args.format in {"terminal", "markdown"} else json.dumps(projection, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_new_output(args.output, rendered)
        return {"kind": "report", "projection": projection, "rendered": rendered, "output": str(args.output.resolve()) if args.output else None}
    if args.command in {"generate", "evaluate"}:
        return load_preview_spec(args.spec, args.command)
    raise CliInputError("unsupported command")


def _write_new_output(path: Path, content: str) -> None:
    if path.exists() or path.is_symlink():
        raise CliInputError("report output must be a new regular file path")
    if any(part == ".." for part in path.parts):
        raise CliInputError("report output cannot contain parent traversal")
    parent = path.parent.resolve()
    if not parent.is_dir() or parent.is_symlink():
        raise CliInputError("report output parent must be an existing regular directory")
    path.write_text(content, encoding="utf-8")


def _emit(result: dict[str, Any], args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command == "report" and args.format == "terminal" and not args.json:
        sys.stdout.write(result["rendered"])
    elif args.command == "report" and args.format == "markdown" and not args.json:
        sys.stdout.write(result["rendered"])
    else:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def _emit_error(message: str, code: int, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(json.dumps({"error": message, "exit_code": code}, ensure_ascii=False) + "\n")
    else:
        sys.stderr.write(f"taskgen: {message}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
