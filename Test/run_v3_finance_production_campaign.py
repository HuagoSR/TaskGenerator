from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "SkillRegistry" / "v3_finance_production_campaign.experimental.json"
DEFAULT_OUTPUT_ROOT = Path("/data/runs") if Path("/data").exists() else ROOT / "artifacts" / "finance_production_runs"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def initialize_registry(path: Path) -> None:
    if not path.exists():
        atomic_json(path, {"registry_version": "v3.0", "entry_count": 0, "entries": []})


def wave_spec(spec: dict, wave: int) -> dict:
    return next(item for item in spec["waves"] if int(item["wave"]) == wave)


def wave_motifs(spec: dict, wave: int) -> list[str]:
    item = wave_spec(spec, wave)
    if item.get("motifs"):
        return list(item["motifs"])
    motifs = []
    for motif in spec["allowed_motifs"]:
        motifs.extend([motif] * int(item["motif_quota"][motif]))
    return motifs


def occurrence_offsets(spec: dict, wave: int) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for index in range(1, wave):
        counts.update(wave_motifs(spec, index))
    return dict(counts)


def topic_payload(spec: dict, wave: int) -> tuple[list[str], dict[str, list[str]]]:
    if wave not in {1, 2}:
        return [], {}
    topics = [item for item in spec["topics"] if int(item["wave_available"]) == wave]
    return [item["topic"] for item in topics], {item["topic"]: item["queries"] for item in topics}


def build_command(args: argparse.Namespace, spec: dict, campaign_root: Path) -> list[str]:
    wave = args.wave
    wave_id = f"wave_{wave:02d}"
    registry = campaign_root / "state" / "campaign_registry.json"
    initialize_registry(registry)
    topics, queries = topic_payload(spec, wave)
    query_path = campaign_root / "state" / f"{wave_id}_topic_queries.json"
    atomic_json(query_path, {"topics": queries})
    command = [
        sys.executable,
        str(ROOT / "Test" / "run_v3_end_to_end_pipeline.py"),
        "--run-id", wave_id,
        "--action", args.pipeline_action,
        "--profile", "custom",
        "--stage", "production_review",
        "--registry-mode", "existing",
        "--registry-path", str(registry),
        "--domain-profile", "finance_audit",
        "--target-difficulty-profile", "finance_production_v1",
        "--max-cases", str(wave_spec(spec, wave)["target_ready"]),
        "--case-index-offset", str(wave_spec(spec, wave)["case_offset"]),
        "--rw-task-root", args.rw_task_root,
        "--python-exe", sys.executable,
        "--output-root", str(campaign_root / "waves"),
        "--timeout-seconds", str(args.timeout_seconds),
    ]
    for motif in wave_motifs(spec, wave):
        command.extend(["--motif", motif])
    for motif, offset in occurrence_offsets(spec, wave).items():
        command.extend(["--motif-occurrence-offset", f"{motif}={offset}"])
    if topics:
        command.extend([
            "--source-mode", "web",
            "--apply-registry-update",
            "--allow-web-collection",
            "--allow-external-source-upload",
            "--collector-backend", "direct",
            "--source-limit", str(spec["source_limit_per_topic"]),
            "--provider", spec["provider"],
            "--deepseek-model", spec["model"],
            "--max-candidates", str(spec["max_candidates_per_topic"]),
            "--extractor-max-tokens", str(spec["max_tokens"]),
            "--extractor-output-profile", spec["extractor_output_profile"],
            "--topic-queries-path", str(query_path),
            "--env-path", args.env_path,
            "--deepseek-key-path", args.deepseek_key_path,
        ])
        for topic in topics:
            command.extend(["--topic", topic])
    else:
        command.extend(["--source-mode", "existing"])
    return command


def summarize_wave(campaign_root: Path, wave: int, spec: dict) -> dict:
    wave_dir = campaign_root / "waves" / f"wave_{wave:02d}"
    manifest_path = wave_dir / "end_to_end_run_manifest.json"
    if not manifest_path.exists():
        return {"wave": wave, "state": "not_started"}
    manifest = load_json(manifest_path)
    source = manifest.get("stages", {}).get("source_to_skills", {}).get("summary", {})
    registry = manifest.get("stages", {}).get("registry_prepare", {}).get("summary", {})
    production_path = manifest.get("stages", {}).get("task_generation", {}).get("artifact_paths", {}).get("production_batch_manifest")
    production = load_json(Path(production_path)) if production_path and Path(production_path).exists() else {}
    cases = production.get("cases", [])
    ready = [case for case in cases if case.get("task_state") == "candidate_ready"]
    review = manifest.get("stages", {}).get("production_review", {}).get("summary", {})
    source_counts = []
    batch_report_path = manifest.get("stages", {}).get("source_to_skills", {}).get("artifact_paths", {}).get("web_source_batch_report")
    if batch_report_path and Path(batch_report_path).exists():
        batch = load_json(Path(batch_report_path))
        for item in batch.get("batches", []):
            report = item.get("collector", {}).get("collection_report", {})
            source_counts.append(int(report.get("accepted_source_count") or report.get("source_count") or 0))
    target = int(wave_spec(spec, wave)["target_ready"])
    reference_hashes: dict[str, list[str]] = {}
    # Count each candidate-visible file once. Export/eval-input copies are transport
    # replicas of the package, not cross-case duplicate evidence.
    for path in wave_dir.glob("03_task_generation/**/package/reference_files/*"):
        if path.is_file():
            reference_hashes.setdefault(sha256_file(path), []).append(str(path.relative_to(wave_dir)))
    duplicate_reference_groups = [paths for paths in reference_hashes.values() if len(paths) > 1]
    requirements = {
        "target_ready": len(ready) == target,
        "verifier_all_pass": all(case.get("verifier_status") == "pass" for case in ready),
        "export_all_compatible": all("compatible" in str(case.get("validation_status")) for case in ready),
        "qa_non_blocking": int(review.get("blocked_count") or 0) == 0,
        "no_eval_stage": "rw_task_eval" not in manifest.get("stages", {}),
        "no_external_eval": not manifest.get("external_effects", {}).get("external_eval", False),
        "no_eval_preparation": not manifest.get("external_effects", {}).get("eval_preparation", False),
        "no_exact_reference_duplicates": not duplicate_reference_groups,
    }
    if wave == 1:
        requirements.update({
            "five_topics_two_sources_each": len(source_counts) == 5 and all(count >= 2 for count in source_counts),
            "accepted_skills_min_15": int(source.get("accepted_count") or 0) >= 15,
            "sample_ready_min_12": int(registry.get("selected_count") or 0) >= 12,
        })
    return {
        "wave": wave,
        "state": manifest.get("run_status"),
        "manifest_path": str(manifest_path),
        "candidate_ready_count": len(ready),
        "case_count": len(cases),
        "source_counts": source_counts,
        "accepted_skill_count": int(source.get("accepted_count") or 0),
        "sample_ready_count": int(registry.get("selected_count") or 0),
        "duplicate_reference_groups": duplicate_reference_groups,
        "requirements": requirements,
        "decision": "pass" if requirements and all(requirements.values()) else "blocked",
    }


def write_campaign_status(campaign_root: Path, spec: dict) -> dict:
    canonical = ROOT / "SkillRegistry" / "v3_skill_registry.json"
    status = {
        "campaign_status_version": "v3.finance_production_status.1",
        "campaign_id": spec["campaign_id"],
        "updated_at": now(),
        "canonical_registry_sha256": sha256_file(canonical),
        "waves": [summarize_wave(campaign_root, wave, spec) for wave in range(1, 5)],
    }
    atomic_json(campaign_root / "campaign_status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrate finance production waves through the existing end-to-end pipeline.")
    parser.add_argument("--action", choices=["run", "resume", "status"], default="run")
    parser.add_argument("--wave", type=int, choices=[1, 2, 3, 4], default=1)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--env-path", default="/run/secrets/provider_env")
    parser.add_argument("--deepseek-key-path", default="/run/secrets/deepseek_api_key")
    parser.add_argument("--rw-task-root", default="/opt/rw-task")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    spec = load_json(args.spec)
    campaign_root = args.output_root / spec["campaign_id"]
    campaign_root.mkdir(parents=True, exist_ok=True)
    if args.action == "status":
        print(json.dumps(write_campaign_status(campaign_root, spec), ensure_ascii=False, indent=2))
        return
    args.pipeline_action = "resume" if args.action == "resume" else "run"
    command = build_command(args, spec, campaign_root)
    run_record = {"wave": args.wave, "started_at": now(), "state": "running", "command": [item for item in command if "key" not in item.lower()]}
    atomic_json(campaign_root / "active_run.json", run_record)
    result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    run_record.update({"finished_at": now(), "returncode": result.returncode, "state": "completed" if result.returncode == 0 else "failed"})
    atomic_json(campaign_root / "active_run.json", run_record)
    status = write_campaign_status(campaign_root, spec)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
