from __future__ import annotations

import argparse
import gzip
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "docker"
DEFAULT_RELEASE_ROOT = ROOT / "artifacts" / "releases" / "milestone_d"
DEFAULT_RW_TASK_ROOT = ROOT.parent / "rw-task"
DEFAULT_SSH_HOST = "serene-cloud"
RW_TASK_ALLOWED = ("pyproject.toml", "README.md", "bench_standalone")
FORBIDDEN_NAMES = {".env", ".DS_Store", "deepseek-key.txt", "artifacts", "result", "evaluation", "e2b", "__pycache__"}


def run(command: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command[:4])}\n{result.stderr[-2000:]}")
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def safe_copy_rw_task(source: Path, target: Path) -> dict[str, str]:
    if not source.is_dir():
        raise RuntimeError(f"rw-task root is missing: {source}")
    target.mkdir(parents=True, exist_ok=True)
    for name in RW_TASK_ALLOWED:
        item = source / name
        if not item.exists():
            raise RuntimeError(f"Required rw-task allowlist item is missing: {item}")
        destination = target / name
        if item.is_dir():
            shutil.copytree(
                item,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env", "artifacts", "result"),
            )
        else:
            shutil.copy2(item, destination)
    prune_forbidden_tree(target)
    files = sorted(path for path in target.rglob("*") if path.is_file())
    return {path.relative_to(target).as_posix(): sha256_file(path) for path in files}


def assert_release_clean(context: Path) -> list[str]:
    findings: list[str] = []
    for path in context.rglob("*"):
        relative = path.relative_to(context)
        if any(part in FORBIDDEN_NAMES for part in relative.parts):
            findings.append(relative.as_posix())
    if findings:
        raise RuntimeError("Forbidden release content: " + ", ".join(sorted(set(findings))[:20]))
    return findings


def prune_forbidden_tree(root: Path) -> None:
    candidates = sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    for path in candidates:
        if path.name not in FORBIDDEN_NAMES and path.suffix.lower() != ".pyc":
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def build_release(release_id: str, rw_task_root: Path, release_root: Path) -> Path:
    release_dir = release_root / release_id
    if release_dir.exists():
        raise RuntimeError(f"Release already exists: {release_dir}")
    context = release_dir / "context"
    taskgenerator = context / "taskgenerator"
    context.mkdir(parents=True)
    archive = release_dir / "taskgenerator.tar"
    run(["git", "archive", "--format=tar", "-o", str(archive), "HEAD"])
    taskgenerator.mkdir()
    with tarfile.open(archive) as handle:
        handle.extractall(taskgenerator, filter="data")
    archive.unlink()
    for forbidden in (taskgenerator / ".env", taskgenerator / "deepseek-key.txt"):
        forbidden.unlink(missing_ok=True)
    prune_forbidden_tree(taskgenerator)
    shutil.copy2(DEPLOY / "Dockerfile", context / "Dockerfile")
    shutil.copy2(DEPLOY / "requirements.lock", context / "requirements.lock")
    shutil.copy2(DEPLOY / ".dockerignore", context / ".dockerignore")
    shutil.copy2(DEPLOY / "compose.yaml", release_dir / "compose.yaml")
    rw_hashes = safe_copy_rw_task(rw_task_root, context / "rw-task")
    assert_release_clean(context)

    commit = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    dirty = [line for line in run(["git", "status", "--short"]).stdout.splitlines() if not line.endswith(" .env")]
    image = f"taskgenerator:{release_id}"
    rw_snapshot = hashlib.sha256(json.dumps(rw_hashes, sort_keys=True).encode()).hexdigest()
    run(
        [
            "docker", "buildx", "build", "--platform", "linux/amd64", "--load",
            "--build-arg", f"RELEASE_ID={release_id}", "--build-arg", f"SOURCE_COMMIT={commit}",
            "--build-arg", f"RW_TASK_SNAPSHOT={rw_snapshot}",
            "--label", f"cloud.huago.taskgenerator.rw-task-sha256={rw_snapshot}",
            "-t", image, str(context),
        ],
        cwd=release_dir,
    )
    inspect = json.loads(run(["docker", "image", "inspect", image]).stdout)[0]
    image_id = inspect["Id"]
    manifest = {
        "release_manifest_version": "v3.milestone_d_release.1",
        "release_id": release_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "non_env_dirty_worktree": dirty,
        "image": image,
        "image_id": image_id,
        "architecture": inspect.get("Architecture"),
        "os": inspect.get("Os"),
        "image_size_bytes": inspect.get("Size"),
        "rw_task_snapshot_sha256": rw_snapshot,
        "rw_task_files": rw_hashes,
        "dockerfile_sha256": sha256_file(DEPLOY / "Dockerfile"),
        "requirements_lock_sha256": sha256_file(DEPLOY / "requirements.lock"),
        "compose_sha256": sha256_file(DEPLOY / "compose.yaml"),
        "security_scan": {"forbidden_context_findings": [], "secret_values_recorded": False},
    }
    atomic_json(release_dir / "release_manifest.json", manifest)
    archive_path = release_dir / f"{release_id}.image.tar.gz"
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        run(["docker", "save", "-o", str(temporary_path), image])
        with temporary_path.open("rb") as source, gzip.open(archive_path, "wb", compresslevel=1) as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
    finally:
        temporary_path.unlink(missing_ok=True)
    manifest["image_archive_sha256"] = sha256_file(archive_path)
    manifest["image_archive_size_bytes"] = archive_path.stat().st_size
    atomic_json(release_dir / "release_manifest.json", manifest)
    shutil.rmtree(context)
    return release_dir


def ssh(host: str, command: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["ssh", "-o", "BatchMode=yes", host, command], check=check)


def preflight(host: str) -> dict:
    remote = ssh(
        host,
        "printf 'home=%s\\n' \"$HOME\"; uname -m; nproc; free -b; df -B1 /; docker version --format '{{.Server.Version}}'; docker compose version; docker ps --format '{{.Names}}|{{.Ports}}'",
    ).stdout
    local = run(["docker", "version", "--format", "{{.Client.Version}}|{{.Server.Version}}"]).stdout.strip()
    report = {"ssh_host": host, "local_docker": local, "remote_probe": remote, "passed": "x86_64" in remote}
    if not report["passed"]:
        raise RuntimeError("Remote preflight did not confirm x86_64.")
    return report


def release_payload(release_dir: Path) -> dict:
    return json.loads((release_dir / "release_manifest.json").read_text(encoding="utf-8"))


def _env_value(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def deploy_release(
    release_dir: Path,
    host: str,
    deepseek_key: Path | None,
    provider_env_source: Path | None,
    tuzi_key_slot: str = "primary",
) -> None:
    manifest = release_payload(release_dir)
    release_id = manifest["release_id"]
    remote_home = ssh(host, "printf %s \"$HOME\"").stdout.strip()
    remote_release = f"{remote_home}/taskgenerator-deploy/releases/{release_id}"
    ssh(host, f"mkdir -p '{remote_release}' '{remote_home}/taskgenerator-data/runs' '{remote_home}/taskgenerator-data/inputs' '{remote_home}/taskgenerator-secrets'")
    archive = release_dir / f"{release_id}.image.tar.gz"
    # Stream the image into docker load instead of storing a second compressed
    # copy on the small server disk.  Release metadata remains durable, while
    # the local archive is the transport/recovery artifact.
    run(["scp", str(release_dir / "compose.yaml"), str(release_dir / "release_manifest.json"), f"{host}:{remote_release}/"])
    env_path = release_dir / "release.env"
    env_path.write_text(
        "\n".join(
            [
                f"TASKGEN_IMAGE={manifest['image']}",
                f"TASKGEN_IMAGE_ID={manifest['image_id']}",
                f"TASKGEN_RELEASE_ID={release_id}",
                f"TASKGEN_SOURCE_COMMIT={manifest['source_commit']}",
                f"TASKGEN_RW_TASK_SNAPSHOT={manifest['rw_task_snapshot_sha256']}",
                f"TASKGEN_RUNS_DIR={remote_home}/taskgenerator-data/runs",
                f"TASKGEN_INPUT_DIR={remote_home}/taskgenerator-data/inputs",
                f"TASKGEN_DEEPSEEK_KEY_FILE={remote_home}/taskgenerator-secrets/deepseek_api_key",
                f"TASKGEN_PROVIDER_ENV_FILE={remote_home}/taskgenerator-secrets/provider.env",
                "TASKGEN_EVAL_TUZI_ENV_FILE=" + (
                    f"{remote_home}/taskgenerator-secrets/f4_tuzi_backup.env"
                    if tuzi_key_slot == "backup"
                    else f"{remote_home}/taskgenerator-secrets/eval_tuzi.env"
                ),
                f"TASKGEN_E2B_KEY_FILE={remote_home}/taskgenerator-secrets/e2b_api_key",
            ]
        ) + "\n",
        encoding="utf-8",
    )
    run(["scp", str(env_path), f"{host}:{remote_release}/release.env"])
    if deepseek_key:
        if not deepseek_key.is_file() or not deepseek_key.read_text(encoding="utf-8").strip():
            raise RuntimeError("DeepSeek key file is missing or empty.")
        remote_tmp = f"{remote_home}/taskgenerator-secrets/.deepseek_api_key.tmp"
        run(["scp", str(deepseek_key), f"{host}:{remote_tmp}"])
        ssh(host, f"chmod 600 '{remote_tmp}' && mv '{remote_tmp}' '{remote_home}/taskgenerator-secrets/deepseek_api_key'")
    if provider_env_source:
        serper_key = _env_value(provider_env_source, "SERPER_API_KEY")
        if not serper_key:
            raise RuntimeError("SERPER_API_KEY is missing from the local provider env source.")
        with tempfile.TemporaryDirectory(prefix="taskgen-provider-") as temporary:
            minimal = Path(temporary) / "provider.env"
            minimal.write_text(f"SERPER_API_KEY={serper_key}\n", encoding="utf-8")
            remote_tmp = f"{remote_home}/taskgenerator-secrets/.provider.env.tmp"
            run(["scp", str(minimal), f"{host}:{remote_tmp}"])
            ssh(host, f"chmod 600 '{remote_tmp}' && mv '{remote_tmp}' '{remote_home}/taskgenerator-secrets/provider.env'")
    with gzip.open(archive, "rb") as source:
        process = subprocess.Popen(["ssh", host, "docker load"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdin is not None
        shutil.copyfileobj(source, process.stdin, length=1024 * 1024)
        process.stdin.close()
        stdout = process.stdout.read() if process.stdout else b""
        stderr = process.stderr.read() if process.stderr else b""
        returncode = process.wait()
        if returncode:
            raise RuntimeError(f"remote_docker_load_failed:{returncode}:{stderr.decode(errors='replace')[-500:]}")
    ssh(host, f"cd '{remote_home}/taskgenerator-deploy' && ln -sfn '{remote_release}' candidate")


def compose_command(host: str, release_id: str, service: str, arguments: Iterable[str]) -> subprocess.CompletedProcess[str]:
    quoted = " ".join("'" + item.replace("'", "'\\''") + "'" for item in arguments)
    return ssh(host, f"cd ~/taskgenerator-deploy/releases/{release_id} && docker compose --env-file release.env -f compose.yaml run --rm {service} {quoted}")


def activate_release(release_id: str, host: str) -> None:
    remote_home = ssh(host, "printf %s \"$HOME\"").stdout.strip()
    remote_release = f"{remote_home}/taskgenerator-deploy/releases/{release_id}"
    ssh(
        host,
        (
            f"test -f '{remote_release}/release_manifest.json' && "
            f"docker image inspect 'taskgenerator:{release_id}' >/dev/null && "
            f"cd '{remote_home}/taskgenerator-deploy' && "
            "if [ -L current ]; then ln -sfn \"$(readlink -f current)\" previous; fi && "
            f"ln -sfn '{remote_release}' current"
        ),
    )


def local_compose(release_dir: Path, service: str, arguments: Iterable[str]) -> subprocess.CompletedProcess[str]:
    manifest = release_payload(release_dir)
    local_root = release_dir / "local_runtime"
    runs = local_root / "runs"
    inputs = local_root / "inputs"
    runs.mkdir(parents=True, exist_ok=True)
    inputs.mkdir(parents=True, exist_ok=True)
    unused_secret = local_root / "unused_secret"
    unused_secret.touch(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "TASKGEN_IMAGE": manifest["image"],
            "TASKGEN_IMAGE_ID": manifest["image_id"],
            "TASKGEN_RELEASE_ID": manifest["release_id"],
            "TASKGEN_SOURCE_COMMIT": manifest["source_commit"],
            "TASKGEN_RW_TASK_SNAPSHOT": manifest["rw_task_snapshot_sha256"],
            "TASKGEN_RUNS_DIR": str(runs.resolve()),
            "TASKGEN_INPUT_DIR": str(inputs.resolve()),
            "TASKGEN_DEEPSEEK_KEY_FILE": str((ROOT / "deepseek-key.txt").resolve()),
            "TASKGEN_PROVIDER_ENV_FILE": str((ROOT / ".env").resolve()),
            # Compose interpolates every service even when only offline is
            # selected. These placeholders are never mounted by that service.
            "TASKGEN_EVAL_TUZI_ENV_FILE": str(unused_secret.resolve()),
            "TASKGEN_E2B_KEY_FILE": str(unused_secret.resolve()),
        }
    )
    result = subprocess.run(
        ["docker", "compose", "-f", str(release_dir / "compose.yaml"), "run", "--rm", service, *arguments],
        cwd=release_dir,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:] or result.stdout[-3000:])
    return result


def pipeline_args(action: str, run_id: str, mode: str, from_stage: str | None = None) -> list[str]:
    args = ["--run-id", run_id, "--action", action, "--output-root", "/data/runs", "--rw-task-root", "/opt/rw-task", "--python-exe", sys.executable if os.name != "nt" else "python"]
    if action == "run":
        profile = {"demo-offline": "public-smoke-offline", "demo-llm": "public-smoke-llm", "batch": "local-existing"}[mode]
        args.extend(["--profile", profile])
        if mode == "demo-llm":
            args.extend(["--allow-external-source-upload", "--provider", "deepseek", "--deepseek-model", "deepseek-v4-flash", "--deepseek-key-path", "/run/secrets/deepseek_api_key"])
        if mode == "batch":
            args.extend(["--max-cases", "4"])
    if from_stage:
        args.extend(["--from-stage", from_stage])
    return args


def production_container_name(campaign_id: str, wave: int) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in campaign_id)
    return f"taskgenerator-{safe}-wave-{wave:02d}"


def production_start(host: str, release_id: str, campaign_id: str, wave: int, *, resume: bool = False) -> str:
    name = production_container_name(campaign_id, wave)
    action = "resume" if resume else "run"
    command = (
        f"cd ~/taskgenerator-deploy/releases/{release_id} && "
        f"(docker rm -f '{name}' >/dev/null 2>&1 || true) && "
        f"docker compose --env-file release.env -f compose.yaml run -d --name '{name}' "
        "--entrypoint python online Test/run_v3_finance_production_campaign.py "
        f"--action '{action}' --wave '{wave}' --output-root /data/runs"
    )
    return ssh(host, command).stdout.strip()


def production_status(host: str, release_id: str, campaign_id: str, wave: int) -> dict:
    name = production_container_name(campaign_id, wave)
    inspect = ssh(host, f"docker inspect '{name}' --format '{{{{json .State}}}}'", check=False)
    state = json.loads(inspect.stdout) if inspect.returncode == 0 and inspect.stdout.strip() else {"Status": "not_found"}
    command = (
        f"cd ~/taskgenerator-deploy/releases/{release_id} && "
        "docker compose --env-file release.env -f compose.yaml run --rm --entrypoint python online "
        "Test/run_v3_finance_production_campaign.py --action status --output-root /data/runs"
    )
    report = ssh(host, command, check=False)
    payload = json.loads(report.stdout) if report.returncode == 0 and report.stdout.strip().startswith("{") else {"status_error": report.stderr[-1000:]}
    return {"container": name, "container_state": state, "campaign": payload}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, deploy, and verify the Milestone D immutable Docker release.")
    parser.add_argument("--action", required=True, choices=["preflight", "build", "deploy", "activate", "demo-offline", "demo-llm", "batch", "status", "resume", "rerun", "fetch", "compare", "rollback", "production-start", "production-status", "production-logs", "production-monitor", "production-resume", "production-stop", "production-fetch", "eval-install-secrets", "eval-pilot-start", "eval-pilot-grade", "eval-pilot-status", "eval-pilot-logs", "eval-pilot-fetch", "eval-extended-prepare", "eval-extended-start", "eval-extended-grade", "eval-extended-status", "eval-extended-logs", "eval-extended-fetch"])
    parser.add_argument("--release-id")
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--rw-task-root", type=Path, default=DEFAULT_RW_TASK_ROOT)
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_HOST)
    parser.add_argument("--deepseek-key-file", type=Path, default=ROOT / "deepseek-key.txt")
    parser.add_argument("--provider-env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--rw-task-env-file", type=Path, default=Path(r"E:\THU\2026Spring\SRT\rw-task\.env"))
    parser.add_argument("--tuzi-key-slot", choices=["primary", "backup"], default="primary")
    parser.add_argument("--target", choices=["local", "server"], default="server")
    parser.add_argument("--service", choices=["offline", "online"], default="offline", help="Use online only when resuming an explicitly approved LLM run.")
    parser.add_argument("--run-id")
    parser.add_argument("--from-stage", choices=["source_to_skills", "registry_prepare", "task_generation", "production_review", "rw_task_eval"])
    parser.add_argument("--local-manifest", type=Path)
    parser.add_argument("--remote-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--campaign-id", default="finance_audit_production_01")
    parser.add_argument("--wave", type=int, choices=[1, 2, 3, 4], default=1)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-polls", type=int, default=0)
    args = parser.parse_args()

    if args.action == "preflight":
        print(json.dumps(preflight(args.ssh_host), ensure_ascii=False, indent=2))
        return
    release_id = args.release_id or datetime.now(timezone.utc).strftime("d-%Y%m%d-%H%M%S")
    release_dir = args.release_root / release_id
    if args.action == "build":
        built = build_release(release_id, args.rw_task_root, args.release_root)
        print(json.dumps(release_payload(built), ensure_ascii=False, indent=2))
        return
    if args.action == "deploy":
        deploy_release(release_dir, args.ssh_host, args.deepseek_key_file, args.provider_env_file, args.tuzi_key_slot)
        print(json.dumps({"deployed_candidate": release_id, "host": args.ssh_host, "activated": False}, ensure_ascii=False))
        return
    if args.action == "eval-install-secrets":
        tuzi_key = _env_value(args.rw_task_env_file, "AGENT_API_KEY") or _env_value(args.rw_task_env_file, "OPENAI_API_KEY")
        tuzi_url = _env_value(args.rw_task_env_file, "AGENT_BASE_URL") or _env_value(args.rw_task_env_file, "OPENAI_BASE_URL")
        e2b_key = _env_value(args.provider_env_file, "E2B_API_KEY")
        if not all((tuzi_key, tuzi_url, e2b_key)): raise RuntimeError("Tuzi or E2B eval secret is missing")
        with tempfile.TemporaryDirectory(prefix="taskgen-eval-secrets-") as temporary:
            root = Path(temporary); tuzi = root / "eval_tuzi.env"; e2b = root / "e2b_api_key"
            tuzi.write_text(f"TUZI_API_KEY={tuzi_key}\nTUZI_BASE_URL={tuzi_url}\n", encoding="utf-8"); e2b.write_text(e2b_key + "\n", encoding="utf-8")
            run(["scp", str(tuzi), str(e2b), f"{args.ssh_host}:~/taskgenerator-secrets/"])
        ssh(args.ssh_host, "chmod 600 ~/taskgenerator-secrets/eval_tuzi.env ~/taskgenerator-secrets/e2b_api_key")
        print(json.dumps({"installed": ["eval_tuzi.env", "e2b_api_key"], "mode": "0600"})); return
    if args.action in {"production-start", "production-resume"}:
        container_id = production_start(
            args.ssh_host,
            release_id,
            args.campaign_id,
            args.wave,
            resume=args.action == "production-resume",
        )
        print(json.dumps({"container_id": container_id, "campaign_id": args.campaign_id, "wave": args.wave}, ensure_ascii=False))
        return
    if args.action == "eval-pilot-start":
        name = "taskgenerator-finance-model-difference-pilot"
        command = (f"cd ~/taskgenerator-deploy/releases/{release_id} && (docker rm -f '{name}' >/dev/null 2>&1 || true) && "
                   f"docker compose --env-file release.env -f compose.yaml run -d --name '{name}' --entrypoint python eval "
                   "Test/run_v3_finance_model_difference_eval.py --action run")
        print(json.dumps({"container_id": ssh(args.ssh_host, command).stdout.strip(), "campaign_id": "finance_model_difference_eval_01"}, ensure_ascii=False)); return
    if args.action == "eval-pilot-grade":
        name = "taskgenerator-finance-model-difference-grading"
        command = (f"cd ~/taskgenerator-deploy/releases/{release_id} && (docker rm -f '{name}' >/dev/null 2>&1 || true) && "
                   f"docker compose --env-file release.env -f compose.yaml run -d --name '{name}' --entrypoint python eval "
                   "Test/run_v3_finance_model_difference_eval.py --action grade")
        print(json.dumps({"container_id": ssh(args.ssh_host, command).stdout.strip(), "campaign_id": "finance_model_difference_eval_01"}, ensure_ascii=False)); return
    if args.action in {"eval-pilot-status", "eval-pilot-logs"}:
        name = "taskgenerator-finance-model-difference-pilot"
        if args.action == "eval-pilot-logs": print(ssh(args.ssh_host, f"docker logs --tail 100 '{name}'", check=False).stdout); return
        inspect = ssh(args.ssh_host, f"docker inspect '{name}' --format '{{{{json .State}}}}'", check=False)
        report = ssh(args.ssh_host, f"cd ~/taskgenerator-deploy/releases/{release_id} && docker compose --env-file release.env -f compose.yaml run --rm --entrypoint python eval Test/run_v3_finance_model_difference_eval.py --action status")
        print(json.dumps({"container_state": json.loads(inspect.stdout) if inspect.returncode == 0 else {"Status":"not_found"}, "campaign": json.loads(report.stdout)}, ensure_ascii=False, indent=2)); return
    if args.action == "eval-pilot-fetch":
        destination = release_dir / "fetched" / "finance_model_difference_eval_01"; destination.parent.mkdir(parents=True, exist_ok=True)
        run(["scp", "-r", f"{args.ssh_host}:~/taskgenerator-data/runs/finance_model_difference_eval_01", str(destination.parent)]); print(destination); return
    if args.action == "eval-extended-prepare":
        command = (f"cd ~/taskgenerator-deploy/releases/{release_id} && docker compose --env-file release.env -f compose.yaml run --rm "
                   "--entrypoint python eval Test/run_v3_finance_model_difference_eval.py --action prepare")
        print(ssh(args.ssh_host, command).stdout); return
    if args.action in {"eval-extended-start", "eval-extended-grade"}:
        stage = "solver" if args.action == "eval-extended-start" else "grading"
        name = f"taskgenerator-finance-model-difference-30-{stage}"
        runner_action = "run" if stage == "solver" else "grade"
        command = (f"cd ~/taskgenerator-deploy/releases/{release_id} && (docker rm -f '{name}' >/dev/null 2>&1 || true) && "
                   f"docker compose --env-file release.env -f compose.yaml run -d --name '{name}' --entrypoint python eval "
                   f"Test/run_v3_finance_model_difference_eval.py --action {runner_action}")
        container_id = ssh(args.ssh_host, command).stdout.strip()
        if stage == "solver":
            grading_name = "taskgenerator-finance-model-difference-30-grading"
            watcher_log = "~/taskgenerator-data/runs/finance_model_difference_eval_30_01/grading_watcher.log"
            watcher = (f"cd ~/taskgenerator-deploy/releases/{release_id} && mkdir -p ~/taskgenerator-data/runs/finance_model_difference_eval_30_01 && "
                       f"nohup sh -c \"docker wait '{name}'; docker rm -f '{grading_name}' >/dev/null 2>&1 || true; "
                       f"docker compose --env-file release.env -f compose.yaml run -d --name '{grading_name}' --entrypoint python eval "
                       f"Test/run_v3_finance_model_difference_eval.py --action grade\" > {watcher_log} 2>&1 < /dev/null &")
            ssh(args.ssh_host, watcher)
        print(json.dumps({"container_id": container_id, "campaign_id": "finance_model_difference_eval_30_01", "stage": stage}, ensure_ascii=False)); return
    if args.action in {"eval-extended-status", "eval-extended-logs"}:
        if args.action == "eval-extended-logs":
            output = []
            for stage in ("solver", "grading"):
                name = f"taskgenerator-finance-model-difference-30-{stage}"
                result = ssh(args.ssh_host, f"docker logs --tail 100 '{name}'", check=False)
                output.append(f"== {stage} ==\n{result.stdout}{result.stderr}")
            print("\n".join(output)); return
        states = {}
        for stage in ("solver", "grading"):
            name = f"taskgenerator-finance-model-difference-30-{stage}"
            inspect = ssh(args.ssh_host, f"docker inspect '{name}' --format '{{{{json .State}}}}'", check=False)
            states[stage] = json.loads(inspect.stdout) if inspect.returncode == 0 else {"Status":"not_found"}
        command = (f"cd ~/taskgenerator-deploy/releases/{release_id} && docker compose --env-file release.env -f compose.yaml run --rm "
                   "--entrypoint python eval Test/run_v3_finance_model_difference_eval.py --action status")
        report = ssh(args.ssh_host, command, check=False)
        campaign = json.loads(report.stdout) if report.returncode == 0 and report.stdout.strip().startswith("{") else {"status_error":report.stderr[-1000:]}
        print(json.dumps({"container_states":states,"campaign":campaign},ensure_ascii=False,indent=2)); return
    if args.action == "eval-extended-fetch":
        destination = release_dir / "fetched" / "finance_model_difference_eval_30_01"; destination.parent.mkdir(parents=True, exist_ok=True)
        run(["scp", "-r", f"{args.ssh_host}:~/taskgenerator-data/runs/finance_model_difference_eval_30_01", str(destination.parent)]); print(destination); return
    if args.action == "production-status":
        print(json.dumps(production_status(args.ssh_host, release_id, args.campaign_id, args.wave), ensure_ascii=False, indent=2))
        return
    if args.action == "production-logs":
        name = production_container_name(args.campaign_id, args.wave)
        result = ssh(args.ssh_host, f"docker logs --tail 200 '{name}'", check=False)
        print((result.stdout or "") + (result.stderr or ""))
        return
    if args.action == "production-monitor":
        import time
        polls = 0
        while args.max_polls == 0 or polls < args.max_polls:
            payload = production_status(args.ssh_host, release_id, args.campaign_id, args.wave)
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            polls += 1
            state = payload.get("container_state", {})
            if state.get("Status") in {"exited", "dead", "not_found"}:
                break
            time.sleep(max(5, min(args.poll_seconds, 60)))
        return
    if args.action == "production-stop":
        name = production_container_name(args.campaign_id, args.wave)
        result = ssh(args.ssh_host, f"docker stop -t 30 '{name}'", check=False)
        print(json.dumps({"container": name, "returncode": result.returncode}, ensure_ascii=False))
        return
    if args.action == "production-fetch":
        destination = release_dir / "fetched" / args.campaign_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        run(["scp", "-r", f"{args.ssh_host}:~/taskgenerator-data/runs/{args.campaign_id}", str(destination.parent)])
        print(destination)
        return
    if args.action == "activate":
        activate_release(release_id, args.ssh_host)
        print(json.dumps({"activated": release_id, "host": args.ssh_host}, ensure_ascii=False))
        return
    if args.action in {"demo-offline", "demo-llm", "batch"}:
        if not args.run_id:
            parser.error("--run-id is required")
        service = "online" if args.action == "demo-llm" else "offline"
        command = pipeline_args("run", args.run_id, args.action)
        result = local_compose(release_dir, service, command) if args.target == "local" else compose_command(args.ssh_host, release_id, service, command)
        print(result.stdout)
        return
    if args.action in {"status", "resume", "rerun"}:
        if not args.run_id:
            parser.error("--run-id is required")
        command = pipeline_args(args.action, args.run_id, "demo-offline", args.from_stage)
        result = local_compose(release_dir, args.service, command) if args.target == "local" else compose_command(args.ssh_host, release_id, args.service, command)
        print(result.stdout)
        return
    if args.action == "fetch":
        if not args.run_id:
            parser.error("--run-id is required")
        destination = release_dir / "fetched" / args.run_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        run(["scp", "-r", f"{args.ssh_host}:~/taskgenerator-data/runs/{args.run_id}", str(destination.parent)])
        print(destination)
        return
    if args.action == "compare":
        if not args.local_manifest or not args.remote_manifest or not args.output:
            parser.error("compare requires --local-manifest, --remote-manifest, and --output")
        sys.path.insert(0, str(ROOT / "src"))
        from task_generator.v3_environment_equivalence import compare_environments, write_report
        manifest = release_payload(release_dir)
        report = compare_environments(args.local_manifest, args.remote_manifest, expected_image_id=manifest["image_id"])
        write_report(report, args.output)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        raise SystemExit(0 if report.decision == "equivalent" else 1)
    if args.action == "rollback":
        ssh(args.ssh_host, "cd ~/taskgenerator-deploy && test -L previous && old=$(readlink -f current) && target=$(readlink -f previous) && ln -sfn \"$target\" current && ln -sfn \"$old\" previous")
        print(json.dumps({"rollback": "completed", "host": args.ssh_host}))


if __name__ == "__main__":
    main()
