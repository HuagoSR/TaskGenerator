"""The public, offline-only TaskGenerator command-line interface."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from task_generator.cli.config import CliInputError, CliPrerequisiteError, load_local_config, load_preview_spec
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
    except (CliInputError, CliPrerequisiteError, UnsupportedArtifactError) as exc:
        _emit_error(str(exc), 2 if isinstance(exc, CliInputError) else 3, getattr(locals().get("args", None), "json", False))
    except BrokenPipeError:
        raise SystemExit(0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TaskGenerator public, read-only offline interface.")
    parser.add_argument("--version", action="version", version=f"taskgen {VERSION}")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--config", type=Path, help="local read-only JSON configuration")
    sub = parser.add_subparsers(dest="command")
    for name, help_text in (("doctor", "inspect local read-only capability"), ("runs", "discover local run records"), ("inspect", "read a supported object"), ("report", "render a read-only summary"), ("generate", "preview future generation"), ("evaluate", "preview future diagnostic")):
        child = sub.add_parser(name, help=help_text, parents=[_common_parser()])
        if name == "runs":
            child.add_argument("--root", type=Path)
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
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="emit JSON")
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="local read-only JSON configuration")
    return parser


def _dispatch(args: argparse.Namespace, config: Any) -> dict[str, Any]:
    if args.command == "doctor":
        return {"kind": "doctor", "version": VERSION, "python": sys.version.split()[0], "platform": platform.platform(), "config_loaded": config is not None, "capabilities": {"network": "not_used", "provider": "not_used", "ssh": "not_used", "e2b": "not_used", "read_only_cli": "available"}}
    if args.command == "runs":
        roots = (args.root,) if args.root else (config.artifact_roots if config else ())
        if not roots:
            raise CliInputError("runs requires --root or local configuration artifact_roots")
        return {"kind": "runs", "roots": [str(root.resolve()) for root in roots], "runs": [item for root in roots for item in discover(root)]}
    if args.command == "inspect":
        return inspect_path(args.path)
    if args.command == "report":
        projection = inspect_path(args.path)
        rendered = markdown_report(projection) if args.format in {"terminal", "markdown"} else json.dumps(projection, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_new_output(args.output, config.report_output_root if config else None, rendered)
        return {"kind": "report", "projection": projection, "rendered": rendered, "output": str(args.output.resolve()) if args.output else None}
    if args.command in {"generate", "evaluate"}:
        return load_preview_spec(args.spec, args.command)
    raise CliInputError("unsupported command")


def _write_new_output(path: Path, allowed_root: Path | None, content: str) -> None:
    if path.exists() or path.is_symlink():
        raise CliPrerequisiteError("report output must be a new regular file path")
    if any(part == ".." for part in path.parts):
        raise CliInputError("report output cannot contain parent traversal")
    parent = path.parent.resolve()
    if not parent.is_dir() or parent.is_symlink():
        raise CliPrerequisiteError("report output parent must be an existing regular directory")
    if allowed_root is not None:
        root = allowed_root.resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise CliInputError("report output must remain under configured report_output_root") from exc
    path.write_text(content, encoding="utf-8")


def _emit(result: dict[str, Any], args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command == "report" and args.format == "terminal" and not args.json:
        _write_text(sys.stdout, result["rendered"])
    elif args.command == "report" and args.format == "markdown" and not args.json:
        _write_text(sys.stdout, result["rendered"])
    else:
        _write_text(sys.stdout, json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def _emit_error(message: str, code: int, json_mode: bool) -> None:
    if json_mode:
        _write_text(sys.stdout, json.dumps({"error": message, "exit_code": code}, ensure_ascii=False) + "\n")
    else:
        _write_text(sys.stderr, f"taskgen: {message}\n")
    raise SystemExit(code)


def _write_text(stream: Any, text: str) -> None:
    """Keep CLI output available on legacy Windows terminals without corrupting JSON."""
    encoding = (getattr(stream, "encoding", None) or "utf-8").lower().replace("_", "-")
    if encoding not in {"utf-8", "utf8"}:
        text = text.encode("ascii", errors="backslashreplace").decode("ascii")
    try:
        stream.write(text)
    except UnicodeEncodeError:
        stream.write(text.encode("ascii", errors="backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()
