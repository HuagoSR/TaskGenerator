from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy" / "docker"
DEFAULT_HOST = "huago-cone"
DEFAULT_RW_TASK = ROOT.parent / "rw-task"
MIN_AVAILABLE_DISK_BYTES = 95 * 1024 * 1024 * 1024
ALLOWED_RW_TASK = ("pyproject.toml", "README.md", "bench_standalone")
FORBIDDEN_PARTS = {
    ".env",
    "deepseek-key.txt",
    "auth.json",
    "artifacts",
    "v2_outputs",
    ".git",
    "__pycache__",
    ".DS_Store",
}


def run(command: list[str], *, cwd: Path = ROOT, check: bool = True, timeout: int = 1800):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"command_failed:{result.returncode}:{' '.join(command[:4])}:"
            f"{result.stderr[-2000:]}"
        )
    return result


def ssh(host: str, command: str, *, check: bool = True, timeout: int = 1800):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", host):
        raise ValueError("unsafe_ssh_host")
    return run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        check=check,
        timeout=timeout,
    )


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _copy_rw_task(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for name in ALLOWED_RW_TASK:
        item = source / name
        if not item.exists():
            raise FileNotFoundError(f"rw_task_allowlist_missing:{name}")
        target = destination / name
        if item.is_dir():
            shutil.copytree(
                item,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".env", "artifacts"),
            )
        else:
            shutil.copy2(item, target)


def _assert_clean_context(root: Path) -> None:
    findings = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts) or path.suffix == ".pyc":
            findings.append(relative.as_posix())
    if findings:
        raise RuntimeError("release_context_forbidden:" + ",".join(findings[:20]))


def _prune_forbidden_context(root: Path) -> None:
    candidates = sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    for path in candidates:
        relative = path.relative_to(root)
        if not (
            any(part in FORBIDDEN_PARTS for part in relative.parts)
            or path.suffix == ".pyc"
        ):
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _governed_dirty() -> list[str]:
    lines = run(["git", "status", "--porcelain=v1"]).stdout.splitlines()
    allowed_prefixes = ("artifacts/", ".env", "deepseek-key.txt")
    return [line for line in lines if not line[3:].replace("\\", "/").startswith(allowed_prefixes)]


def prepare_context(*, output_root: Path, rw_task_root: Path) -> Path:
    dirty = _governed_dirty()
    if dirty:
        raise RuntimeError("governed_worktree_not_committed:" + ",".join(dirty[:20]))
    commit = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="taskgen-release-seed-") as temporary:
        archive = Path(temporary) / "source.tar"
        run(["git", "archive", "--format=tar", "-o", str(archive), commit])
        fingerprint = sha_file(archive)
        release_id = f"milestone-r9-huago-cone-{fingerprint[:12]}"
        release_root = output_root / release_id
        if release_root.exists():
            raise FileExistsError("release_context_exists")
        context = release_root / "context"
        taskgenerator = context / "taskgenerator"
        taskgenerator.mkdir(parents=True)
        with tarfile.open(archive) as handle:
            handle.extractall(taskgenerator, filter="data")
    _prune_forbidden_context(taskgenerator)
    _copy_rw_task(rw_task_root, context / "rw-task")
    shutil.copy2(DEPLOY / "Dockerfile", context / "Dockerfile")
    shutil.copy2(DEPLOY / "Dockerfile.agent-eval", context / "Dockerfile.agent-eval")
    shutil.copy2(DEPLOY / "requirements.lock", context / "requirements.lock")
    shutil.copy2(DEPLOY / ".dockerignore", context / ".dockerignore")
    shutil.copy2(DEPLOY / "compose.yaml", release_root / "compose.yaml")
    _assert_clean_context(context)
    context_archive = release_root / "context.tar.gz"
    with tarfile.open(context_archive, "w:gz") as handle:
        handle.add(context, arcname="context")
    manifest = {
        "manifest_version": "v3.huago_cone_release.1",
        "release_id": release_id,
        "source_commit": commit,
        "source_fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "architecture": "linux/amd64",
        "factory_image": f"taskgenerator-factory:{release_id}",
        "eval_image": f"taskgenerator-eval:{release_id}",
        "codex_version": "0.146.0",
        "opencode_version": "1.17.13",
        "context_archive_sha256": sha_file(context_archive),
        "context_archive_size_bytes": context_archive.stat().st_size,
        "forbidden_context_findings": [],
        "secret_values_recorded": False,
    }
    atomic_json(release_root / "release_manifest.json", manifest)
    return release_root


def deploy_and_build(*, release_root: Path, host: str) -> dict:
    manifest_path = release_root / "release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release_id = manifest["release_id"]
    home = ssh(host, "printf %s \"$HOME\"").stdout.strip()
    remote_release = f"{home}/taskgenerator-deploy/releases/{release_id}"
    ssh(
        host,
        " && ".join(
            [
                f"mkdir -p '{remote_release}'",
                f"mkdir -p '{home}/taskgenerator-data/runs' '{home}/taskgenerator-data/inputs' '{home}/taskgenerator-data/eval-workspaces'",
                f"mkdir -p '{home}/taskgenerator-secrets'",
                f"chmod 700 '{home}/taskgenerator-secrets' '{home}/.codex'",
                f"test $(df --output=avail -B1 '{home}' | tail -1) -ge {MIN_AVAILABLE_DISK_BYTES}",
            ]
        ),
    )
    run(
        [
            "scp",
            "-C",
            str(release_root / "context.tar.gz"),
            str(manifest_path),
            str(release_root / "compose.yaml"),
            f"{host}:{remote_release}/",
        ],
        timeout=1200,
    )
    factory = manifest["factory_image"]
    evaluation = manifest["eval_image"]
    remote_command = " && ".join(
        [
            f"cd '{remote_release}'",
            "tar -xzf context.tar.gz",
            (
                "docker build --platform linux/amd64 "
                f"--build-arg RELEASE_ID='{release_id}' "
                f"--build-arg SOURCE_COMMIT='{manifest['source_commit']}' "
                f"-t '{factory}' -f context/Dockerfile context"
            ),
            (
                "docker build --platform linux/amd64 "
                f"--build-arg FACTORY_IMAGE='{factory}' "
                "--build-arg CODEX_VERSION=0.146.0 --build-arg OPENCODE_VERSION=1.17.13 "
                f"-t '{evaluation}' -f context/Dockerfile.agent-eval context"
            ),
            "rm -rf context context.tar.gz",
            f"ln -sfn '{remote_release}' '{home}/taskgenerator-deploy/candidate'",
        ]
    )
    build = ssh(host, remote_command, timeout=3600)
    inspect = ssh(
        host,
        f"docker image inspect '{factory}' '{evaluation}' --format '{{{{.Id}}}}|{{{{.Architecture}}}}|{{{{.Size}}}}'",
    ).stdout.splitlines()
    manifest["remote_build_completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["remote_images"] = inspect
    manifest["remote_build_stdout_tail"] = build.stdout[-4000:]
    atomic_json(manifest_path, manifest)
    run(["scp", str(manifest_path), f"{host}:{remote_release}/release_manifest.json"])
    return manifest


def parity(*, release_root: Path, host: str) -> dict:
    manifest = json.loads((release_root / "release_manifest.json").read_text(encoding="utf-8"))
    image = manifest["factory_image"]
    command = (
        "docker run --rm --network none --read-only --cap-drop ALL "
        "--security-opt no-new-privileges --memory 3g --cpus 2 "
        "--tmpfs /tmp:size=536870912,mode=1777 "
        "--tmpfs /home/taskgenerator/.cache:size=134217728,mode=0700,uid=1000,gid=1000 "
        "-e PYTHONPATH=/opt/taskgenerator/src "
        "--entrypoint python "
        f"'{image}' -m unittest discover -s tests -p 'test_*.py'"
    )
    result = ssh(host, command, check=False, timeout=3600)
    report = {
        "report_version": "v3.huago_cone_release_parity.1",
        "release_id": manifest["release_id"],
        "source_fingerprint": manifest["source_fingerprint"],
        "network_disabled": True,
        "read_only_root": True,
        "credentials_mounted": False,
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "stdout_tail": result.stdout[-12000:],
        "stderr_tail": result.stderr[-12000:],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(release_root / "parity_report.json", report)
    return report


def write_release_env(*, release_root: Path, host: str) -> Path:
    manifest = json.loads((release_root / "release_manifest.json").read_text(encoding="utf-8"))
    home = ssh(host, "printf %s \"$HOME\"").stdout.strip()
    values = {
        "TASKGEN_IMAGE": manifest["factory_image"],
        "TASKGEN_FACTORY_IMAGE": manifest["factory_image"],
        "TASKGEN_EVAL_IMAGE": manifest["eval_image"],
        "TASKGEN_IMAGE_ID": "remote-build",
        "TASKGEN_EVAL_IMAGE_ID": "remote-build",
        "TASKGEN_RELEASE_ID": manifest["release_id"],
        "TASKGEN_SOURCE_COMMIT": manifest["source_commit"],
        "TASKGEN_RW_TASK_SNAPSHOT": "embedded-allowlist",
        "TASKGEN_RUNS_DIR": f"{home}/taskgenerator-data/runs",
        "TASKGEN_INPUT_DIR": f"{home}/taskgenerator-data/inputs",
        "TASKGEN_EVAL_WORKSPACES_DIR": f"{home}/taskgenerator-data/eval-workspaces",
        "TASKGEN_DEEPSEEK_KEY_FILE": f"{home}/taskgenerator-secrets/deepseek_api_key",
        "TASKGEN_PROVIDER_ENV_FILE": f"{home}/taskgenerator-secrets/provider.env",
        "TASKGEN_EVAL_TUZI_ENV_FILE": f"{home}/taskgenerator-secrets/eval_tuzi.env",
        "TASKGEN_E2B_KEY_FILE": f"{home}/taskgenerator-secrets/unused_e2b_key",
        "TASKGEN_CODEX_AUTH_FILE": f"{home}/.codex/auth.json",
    }
    path = release_root / "release.env"
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    remote = f"{home}/taskgenerator-deploy/releases/{manifest['release_id']}"
    run(["scp", str(path), f"{host}:{remote}/release.env"])
    return path


def install_secrets(*, host: str, provider_env: Path, deepseek_key: Path) -> dict:
    """Install only the named provider values; never copy the source env file."""
    allowed = {"OPENAI_API_KEY", "OPENAI_BASE_URL", "SERPER_API_KEY"}
    values = {}
    for line in provider_env.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in allowed:
            values[key] = value.strip().strip('"').strip("'")
    if not all(values.get(key) for key in allowed):
        raise RuntimeError("required_provider_secret_missing")
    deepseek_value = deepseek_key.read_text(encoding="utf-8").strip()
    if not deepseek_value:
        raise RuntimeError("deepseek_secret_missing")
    home = ssh(host, "printf %s \"$HOME\"").stdout.strip()
    remote = f"{home}/taskgenerator-secrets"
    ssh(host, f"mkdir -p '{remote}' && chmod 700 '{remote}'")
    with tempfile.TemporaryDirectory(prefix="taskgen-r9-secret-stage-") as temporary:
        root = Path(temporary)
        provider = root / "provider.env"
        tuzi = root / "eval_tuzi.env"
        deepseek = root / "deepseek_api_key"
        unused = root / "unused_e2b_key"
        lines = [
            f"OPENAI_API_KEY={values['OPENAI_API_KEY']}",
            f"OPENAI_BASE_URL={values['OPENAI_BASE_URL']}",
            "OPENAI_MODEL=gpt-5.6-sol",
            f"SERPER_API_KEY={values['SERPER_API_KEY']}",
        ]
        provider.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tuzi.write_text(
            f"TUZI_API_KEY={values['OPENAI_API_KEY']}\nTUZI_BASE_URL={values['OPENAI_BASE_URL']}\n",
            encoding="utf-8",
        )
        deepseek.write_text(deepseek_value + "\n", encoding="utf-8")
        unused.write_text("unused\n", encoding="utf-8")
        for path in (provider, tuzi, deepseek, unused):
            run(["scp", str(path), f"{host}:{remote}/.{path.name}.tmp"])
            ssh(host, f"chmod 600 '{remote}/.{path.name}.tmp' && mv '{remote}/.{path.name}.tmp' '{remote}/{path.name}'")
    return {"installed": True, "secret_values_recorded": False, "codex_auth_touched": False}


def smoke(*, release_root: Path, host: str) -> dict:
    manifest = json.loads((release_root / "release_manifest.json").read_text(encoding="utf-8"))
    release_id = manifest["release_id"]
    write_release_env(release_root=release_root, host=host)
    command = (
        f"cd ~/taskgenerator-deploy/releases/{release_id} && "
        "docker compose --env-file release.env -f compose.yaml run --rm --no-deps "
        "--entrypoint sh offline -lc 'python -c \"import bs4, openai, openpyxl; print(bs4.__version__); print(openai.__version__); print(openpyxl.__version__)\"' && "
        "docker compose --env-file release.env -f compose.yaml run --rm --no-deps "
        "--entrypoint sh eval -lc 'codex --version && opencode --version'"
    )
    result = ssh(host, command, check=False, timeout=600)
    report = {
        "report_version": "v3.huago_cone_candidate_smoke.1",
        "release_id": release_id,
        "returncode": result.returncode,
        "passed": result.returncode == 0 and "2.44.0" in result.stdout and "codex-cli 0.146.0" in result.stdout and "1.17.13" in result.stdout,
        "stdout": result.stdout,
        "stderr_tail": result.stderr[-4000:],
    }
    atomic_json(release_root / "candidate_smoke_report.json", report)
    return report


def activate(*, release_root: Path, host: str) -> None:
    manifest = json.loads((release_root / "release_manifest.json").read_text(encoding="utf-8"))
    if not json.loads((release_root / "parity_report.json").read_text(encoding="utf-8"))["passed"]:
        raise RuntimeError("release_parity_not_passed")
    if not json.loads((release_root / "candidate_smoke_report.json").read_text(encoding="utf-8"))["passed"]:
        raise RuntimeError("release_smoke_not_passed")
    release_id = manifest["release_id"]
    ssh(
        host,
        (
            "cd ~/taskgenerator-deploy && "
            "if [ -L current ]; then ln -sfn \"$(readlink -f current)\" previous; fi && "
            f"ln -sfn \"$HOME/taskgenerator-deploy/releases/{release_id}\" current"
        ),
    )


def status(host: str) -> dict:
    output = ssh(
        host,
        "printf 'current='; readlink -f ~/taskgenerator-deploy/current 2>/dev/null || true; "
        "printf 'previous='; readlink -f ~/taskgenerator-deploy/previous 2>/dev/null || true; "
        "df -BG --output=avail ~ | tail -1; "
        "docker images --filter label=cloud.huago.taskgenerator.managed=true --format '{{.Repository}}:{{.Tag}}|{{.Size}}'",
    ).stdout
    return {"host": host, "raw_status": output}


def rollback(host: str) -> None:
    ssh(
        host,
        "cd ~/taskgenerator-deploy && test -L previous && target=$(readlink -f previous) && current=$(readlink -f current) && ln -sfn \"$target\" current && ln -sfn \"$current\" previous",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and operate the Huago-cone R9 batch release.")
    parser.add_argument("--action", choices=["prepare", "deploy", "secrets", "parity", "smoke", "activate", "status", "rollback"], required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--release-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "releases" / "huago_cone")
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK)
    parser.add_argument("--provider-env", type=Path, default=ROOT / ".env")
    parser.add_argument("--deepseek-key", type=Path, default=ROOT / "deepseek-key.txt")
    args = parser.parse_args()
    if args.action == "prepare":
        value = {"release_root": str(prepare_context(output_root=args.output_root, rw_task_root=args.rw_task_root))}
    elif args.action == "status":
        value = status(args.host)
    elif args.action == "rollback":
        rollback(args.host); value = status(args.host)
    elif args.action == "secrets":
        value = install_secrets(host=args.host, provider_env=args.provider_env, deepseek_key=args.deepseek_key)
    else:
        if args.release_root is None:
            parser.error("--release-root is required")
        if args.action == "deploy": value = deploy_and_build(release_root=args.release_root, host=args.host)
        elif args.action == "parity": value = parity(release_root=args.release_root, host=args.host)
        elif args.action == "smoke": value = smoke(release_root=args.release_root, host=args.host)
        else: activate(release_root=args.release_root, host=args.host); value = status(args.host)
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
