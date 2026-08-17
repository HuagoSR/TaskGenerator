from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_source_fingerprint import (  # noqa: E402
    governed_source_fingerprint,
    iter_governed_snapshot_files,
)

DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "pipeline_reconstruction" / "docker_parity"
DEFAULT_SSH_HOST = "serene-cloud"
DEFAULT_BASE_IMAGE = "taskgenerator:f4-3-eval-eddd09a"
SCP_TIMEOUT_SECONDS = 600
def _run(
    command: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
        timeout=timeout,
    )


def iter_snapshot_files() -> list[Path]:
    return iter_governed_snapshot_files(ROOT)


def source_fingerprint(files: list[Path]) -> str:
    if files != iter_snapshot_files():
        raise ValueError("source_fingerprint_requires_governed_snapshot")
    return governed_source_fingerprint(ROOT)


def build_snapshot(archive_path: Path, files: list[Path]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in files:
            archive.add(
                path,
                arcname=path.relative_to(ROOT).as_posix(),
                recursive=False,
            )


def execute_remote_parity(
    *,
    ssh_host: str,
    base_image: str,
    output_root: Path,
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", ssh_host):
        raise ValueError("unsafe_ssh_host")
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", base_image):
        raise ValueError("unsafe_base_image")
    files = iter_snapshot_files()
    fingerprint = source_fingerprint(files)
    run_id = (
        datetime.now(timezone.utc).strftime("r6-docker-%Y%m%d-%H%M%S")
        + "-"
        + fingerprint[:8]
    )
    if not re.fullmatch(r"[a-z0-9-]+", run_id):
        raise RuntimeError("unsafe_parity_run_id")

    run_root = output_root / run_id
    archive_path = run_root / "source.tar.gz"
    build_snapshot(archive_path, files)

    remote_root = f"~/taskgenerator-data/reconstruction-parity/{run_id}"
    image = f"taskgenerator:reconstruction-parity-{fingerprint[:12]}"
    # The run id is restricted above, so leaving "~" unquoted safely allows
    # the remote shell (and scp) to resolve the account home directory.
    quoted_remote_root = remote_root
    quoted_image = shlex.quote(image)
    quoted_base = shlex.quote(base_image)
    quoted_fingerprint = shlex.quote(fingerprint)

    _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            ssh_host,
            f"mkdir -p {quoted_remote_root}",
        ],
        timeout=30,
    )
    _run(
        [
            "scp",
            "-C",
            str(archive_path),
            f"{ssh_host}:{remote_root}/source.tar.gz",
        ],
        timeout=SCP_TIMEOUT_SECONDS,
    )

    remote_command = " && ".join(
        [
            f"cd {quoted_remote_root}",
            "tar -xzf source.tar.gz",
            (
                "docker build "
                f"--build-arg BASE_IMAGE={quoted_base} "
                f"--build-arg SOURCE_FINGERPRINT={quoted_fingerprint} "
                f"-f deploy/docker/Dockerfile.reconstruction-parity "
                f"-t {quoted_image} ."
            ),
            (
                "docker run --rm --network none --read-only "
                "--tmpfs /tmp:size=536870912,mode=1777 "
                "--tmpfs /home/taskgenerator/.cache:size=134217728,mode=0700,uid=1000,gid=1000 "
                f"{quoted_image} -m unittest discover -s Test -p 'test_*.py'"
            ),
        ]
    )
    started_at = datetime.now(timezone.utc).isoformat()
    result = _run(
        ["ssh", "-o", "BatchMode=yes", ssh_host, remote_command],
        check=False,
        timeout=1800,
    )
    cleanup = _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            ssh_host,
            (
                f"docker image rm {quoted_image} >/dev/null 2>&1 || true; "
                f"rm -rf {quoted_remote_root}"
            ),
        ],
        check=False,
        timeout=120,
    )

    report = {
        "report_version": "v3.reconstruction_docker_parity.1",
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "ssh_host": ssh_host,
        "base_image": base_image,
        "source_fingerprint": fingerprint,
        "snapshot_file_count": len(files),
        "network_mode": "none",
        "read_only_root": True,
        "provider_credentials_mounted": False,
        "test_command": "python -m unittest discover -s Test -p test_*.py",
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "stdout_tail": result.stdout[-12000:],
        "stderr_tail": result.stderr[-12000:],
        "cleanup_returncode": cleanup.returncode,
        "promotion_authorized": False,
        "external_model_execution_authorized": False,
    }
    report_path = run_root / "parity_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build and test the current reconstruction snapshot inside a fixed, "
            "network-disabled remote Docker base without deploying or activating it."
        )
    )
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_HOST)
    parser.add_argument("--base-image", default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report = execute_remote_parity(
        ssh_host=args.ssh_host,
        base_image=args.base_image,
        output_root=args.output_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
