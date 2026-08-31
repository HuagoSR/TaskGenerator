"""Local, judge-only Codex transport for the R10 pilot.

This module intentionally owns only process isolation and Codex JSON capture.
R10's grade staging, schema validation, and score recomputation remain in the
existing behavioral runner.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


def local_codex_version(command: str = "codex") -> str:
    """Return the executable-reported version without inspecting credentials."""
    completed = subprocess.run(
        [command, "--version"], text=True, capture_output=True, timeout=30, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError("r10_local_codex_version_failed")
    version = completed.stdout.strip()
    if not re.fullmatch(r"codex-cli\s+\S+", version):
        raise RuntimeError("r10_local_codex_version_unrecognized")
    return version


def local_codex_command(*, command: str, model: str, workspace: Path) -> list[str]:
    """Build the non-interactive, workspace-limited command used for R10 judges."""
    return [
        command,
        "exec",
        "--approve-for-me",
        "--model",
        model,
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        "agents.enabled=false",
        "--disable",
        "plugins",
        "--disable",
        "apps",
        "--disable",
        "multi_agent",
        "--disable",
        "skill_search",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--output-schema",
        str(workspace / "grade_schema.json"),
        "--output-last-message",
        str(workspace / "grade.raw.json"),
        "-C",
        str(workspace),
        "-",
    ]


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    else:
        process.kill()


def _redact(text: str) -> str:
    """Remove credential-shaped strings before persistence, defensively."""
    text = re.sub(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", text)
    return text


def run_local_codex_judge(
    *,
    workspace: Path,
    prompt: str,
    command: str = "codex",
    model: str = "gpt-5.6-sol",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Run one local judge session and persist only redacted diagnostics.

    The caller owns grade staging and semantic/schema validation.  This helper
    never reads, writes, or copies Codex authentication material.
    """
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    jsonl_path = workspace / "agent.jsonl"
    stderr_path = workspace / "stderr.txt"
    args = local_codex_command(command=command, model=model, workspace=workspace)
    started = time.monotonic()
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        args,
        cwd=workspace,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = process.communicate(timeout=30)
    duration = round(time.monotonic() - started, 3)
    jsonl_path.write_text(_redact(stdout), encoding="utf-8")
    stderr_path.write_text(_redact(stderr), encoding="utf-8")
    return {
        "returncode": 124 if timed_out else process.returncode,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "jsonl_path": str(jsonl_path),
        "stderr_path": str(stderr_path),
        "version": local_codex_version(command),
        "command_name": Path(command).name,
        "model": model,
    }
