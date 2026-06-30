import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
for path in (ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_v3_web_source_pipeline_a import run_pipeline as run_web_source_pipeline  # noqa: E402
from v3_skill_registry import SkillRegistryBuilder  # noqa: E402
from v3_source_collector import slugify  # noqa: E402


DEFAULT_TOPICS = [
    "audit evidence reconciliation",
    "internal control testing",
    "compliance documentation review",
]
DEFAULT_DOMAIN_TAGS = ["finance", "audit", "compliance"]
DEFAULT_OUTPUT_ROOT = ROOT / "Test" / "v3_web_source_collections" / "pipeline_a_batches"
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_BATCH_REPORT_PATH = ROOT / "SkillRegistry" / "v3_web_source_pipeline_a_batch_report.json"
DEFAULT_ENV_PATH = ROOT.parent / "rw-task" / ".env"
DEFAULT_DEEPSEEK_KEY_PATH = ROOT / "deepseek-key.txt"
DEFAULT_AUDIT_REPORT_PATH = ROOT / "SkillRegistry" / "v3_skill_registry_audit_report.json"


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_json(path: Path) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collection_is_ready(collection_dir: Path) -> bool:
    return (
        collection_dir.exists()
        and (collection_dir / "collection_report.json").exists()
        and (collection_dir / "raw_sources").exists()
        and any((collection_dir / "raw_sources").glob("*.json"))
    )


def infer_topic_from_collection(collection_dir: Path) -> str:
    request_path = collection_dir / "collection_request.json"
    if request_path.exists():
        request = load_json(request_path)
        topic = str(request.get("topic", "")).strip()
        if topic:
            return topic
    return collection_dir.name


def collection_dir_for_topic(output_root: Path, topic: str) -> Path:
    return output_root / slugify(topic)


def run_collector(args: argparse.Namespace, topic: str, collection_dir: Path) -> Dict[str, object]:
    if args.reuse_existing and collection_is_ready(collection_dir):
        return {
            "status": "reused_existing",
            "collection_dir": str(collection_dir),
            "note": "Existing collection_report.json and raw_sources were reused.",
        }
    if not args.allow_web_collection:
        raise RuntimeError("Web collection requires --allow-web-collection unless --reuse-existing can reuse a ready collection.")

    cmd = [
        sys.executable,
        str(TEST_DIR / "run_v3_stirrup_source_collector.py"),
        "--topic",
        topic,
        "--limit",
        str(args.limit),
        "--search-backend",
        args.search_backend,
        "--output-dir",
        str(collection_dir),
        "--env-path",
        str(args.env_path),
        "--model",
        args.collector_model,
        "--max-turns",
        str(args.collector_max_turns),
        "--max-tokens",
        str(args.collector_max_tokens),
        "--allow-web-collection",
    ]
    for domain in args.domain:
        cmd.extend(["--domain", domain])
    for query in args.query:
        cmd.extend(["--query", query])
    if args.search_backend == "serper":
        cmd.extend(["--serper-api-key-env", args.serper_api_key_env])

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=args.collector_timeout_seconds,
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        return {
            "status": "failed",
            "collection_dir": str(collection_dir),
            "returncode": result.returncode,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
        }
    report_path = collection_dir / "collection_report.json"
    report = load_json(report_path) if report_path.exists() else {}
    return {
        "status": "success",
        "collection_dir": str(collection_dir),
        "collection_report": report,
        "stdout_tail": stdout[-2000:],
    }


def pipeline_args(args: argparse.Namespace, collection_dir: Path, output_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        collection_dir=collection_dir,
        output_dir=output_dir,
        registry_path=args.registry_path,
        batch_report_path=output_dir / "web_source_pipeline_a_report.json",
        audit_report_path=args.audit_report_path,
        readiness_report_path=args.readiness_report_path,
        provider=args.provider,
        model=args.model,
        deepseek_model=args.deepseek_model,
        max_candidates=args.max_candidates,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout_seconds,
        allow_external_upload=args.allow_external_upload,
        reuse_existing=args.reuse_existing,
        dry_run=args.dry_run_pipeline,
        min_sources=args.min_sources,
        min_text_chars=args.min_text_chars,
        env_path=args.env_path,
        deepseek_key_path=args.deepseek_key_path,
        build_transition_graph=args.build_transition_graph,
        skip_registry_update=args.skip_registry_update,
        calibration_only=args.calibration_only,
    )


def summarize_source_quality(report: Optional[Dict[str, object]]) -> Dict[str, object]:
    if not report:
        return {}
    warning_counts: Counter[str] = Counter(report.get("warning_counts", {}))
    failure_counts: Counter[str] = Counter(report.get("failure_counts", {}))
    return {
        "status": report.get("status"),
        "source_count": report.get("source_count"),
        "failed_source_count": report.get("failed_source_count"),
        "warning_source_count": report.get("warning_source_count"),
        "warning_counts": dict(sorted(warning_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
    }


def run_mode(args: argparse.Namespace) -> str:
    if args.dry_run_pipeline:
        return "dry_run_pipeline"
    if args.calibration_only:
        return "calibration_only"
    if args.reuse_existing:
        return "reuse_existing"
    return "fresh_collection"


def registry_entry_count(registry_path: Path) -> int:
    return len(SkillRegistryBuilder().load_registry(registry_path))


def batch_warnings(summary: Dict[str, object], source_quality: Optional[Dict[str, object]], args: argparse.Namespace) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    status = str(summary.get("status", ""))
    if status not in {"success", "dry_run_complete"}:
        warnings.append({"code": "batch_failed", "message": f"Batch status is {status}."})
    if source_quality and source_quality.get("status") in {"warn", "fail"}:
        warnings.append(
            {
                "code": f"source_quality_{source_quality.get('status')}",
                "message": "Source quality diagnostics should be inspected before trusting extracted skills.",
            }
        )
    candidate_count = int(summary.get("candidate_count") or 0)
    accepted_count = int(summary.get("accepted_count") or 0)
    if candidate_count > 0 and accepted_count == candidate_count:
        warnings.append({"code": "all_candidates_accepted", "message": "Reviewer accepted every candidate in this topic."})
    if candidate_count > 0 and accepted_count == 0:
        warnings.append({"code": "zero_candidates_accepted", "message": "No candidates survived deterministic review."})
    if accepted_count > 0 and int(summary.get("registry_new_entry_count") or 0) == 0:
        if args.skip_registry_update:
            warnings.append({"code": "registry_update_skipped_for_calibration", "message": "Persistent registry update was intentionally skipped for graph calibration."})
        elif args.reuse_existing:
            warnings.append({"code": "idempotency_no_growth_expected", "message": "Reuse run merged existing accepted candidates without growing the registry."})
        else:
            warnings.append({"code": "registry_no_growth", "message": "Accepted candidates merged or skipped without adding coverage."})
    if int(summary.get("possible_duplicate_count") or 0) >= 3:
        warnings.append({"code": "possible_duplicate_spike", "message": "Several possible duplicates were detected."})
    graph_diagnostics = summary.get("graph_extraction_diagnostics") or {}
    for warning_code in graph_diagnostics.get("warning_codes", []):
        warnings.append(
            {
                "code": f"graph_extraction_{warning_code}",
                "message": "Graph extraction diagnostics emitted a warning; inspect graph_extraction_diagnostics.json.",
            }
        )
    return warnings


def run_topic_batch(args: argparse.Namespace, topic: str, collection_dir: Path) -> Dict[str, object]:
    batch_id = slugify(topic)
    pipeline_output_dir = collection_dir / "pipeline_a_run"
    collector_report = run_collector(args, topic, collection_dir)
    if collector_report["status"] == "failed":
        return {
            "batch_id": batch_id,
            "topic": topic,
            "status": "collection_failed",
            "collection_dir": str(collection_dir),
            "collector": collector_report,
            "warnings": [{"code": "collection_failed", "message": "SourceCollector failed; LLM extraction was skipped."}],
        }

    try:
        pipeline_report = run_web_source_pipeline(pipeline_args(args, collection_dir, pipeline_output_dir))
    except Exception as exc:
        source_quality_path = pipeline_output_dir / "source_quality_report.json"
        source_quality = load_json(source_quality_path) if source_quality_path.exists() else None
        return {
            "batch_id": batch_id,
            "topic": topic,
            "status": "pipeline_failed",
            "collection_dir": str(collection_dir),
            "pipeline_output_dir": str(pipeline_output_dir),
            "collector": collector_report,
            "source_quality": summarize_source_quality(source_quality),
            "error": str(exc),
            "warnings": [{"code": "pipeline_failed", "message": "Pipeline A failed after collection; inspect per-topic outputs."}],
        }

    source_quality = load_json(Path(pipeline_report["source_quality_report"]))
    warnings = batch_warnings(pipeline_report, source_quality, args)
    return {
        "batch_id": batch_id,
        "topic": topic,
        "status": pipeline_report.get("status"),
        "collection_dir": str(collection_dir),
        "pipeline_output_dir": str(pipeline_output_dir),
        "collector": collector_report,
        "source_quality": summarize_source_quality(source_quality),
        "candidate_count": pipeline_report.get("candidate_count", 0),
        "accepted_count": pipeline_report.get("accepted_count", 0),
        "revise_count": pipeline_report.get("revise_count", 0),
        "rejected_count": pipeline_report.get("rejected_count", 0),
        "registry_new_entry_count": pipeline_report.get("registry_new_entry_count", 0),
        "registry_merged_candidate_count": pipeline_report.get("registry_merged_candidate_count", 0),
        "registry_skipped_candidate_count": pipeline_report.get("registry_skipped_candidate_count", 0),
        "registry_update_mode": pipeline_report.get("registry_update_mode"),
        "registry_update_skipped": pipeline_report.get("registry_update_skipped"),
        "registry_entry_count_before": pipeline_report.get("registry_entry_count_before"),
        "registry_entry_count_after": pipeline_report.get("registry_entry_count_after"),
        "registry_entry_delta_this_run": pipeline_report.get("registry_entry_delta_this_run"),
        "registry_final_entry_count": pipeline_report.get("registry_final_entry_count"),
        "possible_duplicate_count": pipeline_report.get("possible_duplicate_count", 0),
        "review_reason_code_counts": pipeline_report.get("review_reason_code_counts", {}),
        "graph_extraction_diagnostics": pipeline_report.get("graph_extraction_diagnostics", {}),
        "graph_summary": pipeline_report.get("graph_summary", {}),
        "warnings": warnings,
    }


def aggregate_source_quality(batch_summaries: List[Dict[str, object]]) -> Dict[str, object]:
    warning_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    total_sources = 0
    for batch in batch_summaries:
        source_quality = batch.get("source_quality") or {}
        status_counts.update([str(source_quality.get("status", "missing"))])
        total_sources += int(source_quality.get("source_count") or 0)
        warning_counts.update(source_quality.get("warning_counts", {}))
        failure_counts.update(source_quality.get("failure_counts", {}))
    return {
        "total_source_count": total_sources,
        "status_counts": dict(sorted(status_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
    }


def aggregate_graph_extraction(batch_summaries: List[Dict[str, object]]) -> Dict[str, object]:
    warning_counts: Counter[str] = Counter()
    total_resources = 0
    total_trace_edges = 0
    total_motif_hints = 0
    graph_ready_count = 0
    for batch in batch_summaries:
        diagnostics = batch.get("graph_extraction_diagnostics") or {}
        total_resources += int(diagnostics.get("resource_count") or 0)
        total_trace_edges += int(diagnostics.get("trace_edge_count") or 0)
        total_motif_hints += int(diagnostics.get("motif_hint_count") or 0)
        if diagnostics.get("is_graph_ready"):
            graph_ready_count += 1
        warning_counts.update(diagnostics.get("warning_codes", []))
    return {
        "batch_count": len(batch_summaries),
        "graph_ready_count": graph_ready_count,
        "resource_count": total_resources,
        "trace_edge_count": total_trace_edges,
        "motif_hint_count": total_motif_hints,
        "warning_counts": dict(sorted(warning_counts.items())),
    }


def aggregate_report(
    args: argparse.Namespace,
    batch_summaries: List[Dict[str, object]],
    registry_count_before: int,
    registry_count_after: int,
) -> Dict[str, object]:
    warning_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for batch in batch_summaries:
        warning_counts.update(warning["code"] for warning in batch.get("warnings", []))
        reason_counts.update(batch.get("review_reason_code_counts", {}))

    effective_registry_count_after = registry_count_before if args.skip_registry_update else registry_count_after
    return {
        "status": "success" if all(batch.get("status") in {"success", "dry_run_complete"} for batch in batch_summaries) else "partial_failure",
        "batch_count": len(batch_summaries),
        "output_root": str(args.output_root),
        "registry_path": str(args.registry_path),
        "report_path": str(args.batch_report_path),
        "provider": args.provider,
        "model": args.model,
        "deepseek_model": args.deepseek_model,
        "search_backend": args.search_backend,
        "limit": args.limit,
        "max_candidates": args.max_candidates,
        "max_tokens": args.max_tokens,
        "timeout_seconds": args.timeout_seconds,
        "reuse_existing": args.reuse_existing,
        "dry_run_pipeline": args.dry_run_pipeline,
        "run_mode": run_mode(args),
        "registry_update_mode": "skipped" if args.skip_registry_update else ("not_applicable" if args.dry_run_pipeline else "updated"),
        "registry_update_skipped": bool(args.skip_registry_update or args.dry_run_pipeline),
        "registry_entry_count_before": registry_count_before,
        "registry_entry_count_after": effective_registry_count_after,
        "registry_entry_delta_this_run": effective_registry_count_after - registry_count_before,
        "registry_growth_note": (
            "Persistent registry update was skipped for graph calibration; zero registry growth is expected."
            if args.skip_registry_update
            else (
            "This report describes the current run only. In reuse_existing mode, zero growth is expected when prior accepted candidates are idempotently merged."
            if args.reuse_existing
            else "This report describes the current run only; historical first-run growth remains in prior per-topic registry_update reports."
            )
        ),
        "totals": {
            "candidate_count": sum(int(batch.get("candidate_count") or 0) for batch in batch_summaries),
            "accepted_count": sum(int(batch.get("accepted_count") or 0) for batch in batch_summaries),
            "revise_count": sum(int(batch.get("revise_count") or 0) for batch in batch_summaries),
            "rejected_count": sum(int(batch.get("rejected_count") or 0) for batch in batch_summaries),
            "registry_new_entry_count": sum(int(batch.get("registry_new_entry_count") or 0) for batch in batch_summaries),
            "registry_merged_candidate_count": sum(int(batch.get("registry_merged_candidate_count") or 0) for batch in batch_summaries),
            "registry_skipped_candidate_count": sum(int(batch.get("registry_skipped_candidate_count") or 0) for batch in batch_summaries),
            "possible_duplicate_count": sum(int(batch.get("possible_duplicate_count") or 0) for batch in batch_summaries),
        },
        "graph_summary": {
            "enabled": args.build_transition_graph,
            "edge_count": sum(int(batch.get("graph_summary", {}).get("edge_count") or 0) for batch in batch_summaries),
            "motif_count": sum(int(batch.get("graph_summary", {}).get("motif_count") or 0) for batch in batch_summaries),
            "usable_edge_count": sum(int(batch.get("graph_summary", {}).get("usable_edge_count") or 0) for batch in batch_summaries),
            "blocked_edge_count": sum(int(batch.get("graph_summary", {}).get("blocked_edge_count") or 0) for batch in batch_summaries),
        },
        "source_quality_summary": aggregate_source_quality(batch_summaries),
        "graph_extraction_summary": aggregate_graph_extraction(batch_summaries),
        "warning_counts": dict(sorted(warning_counts.items())),
        "review_reason_code_counts": dict(sorted(reason_counts.items())),
        "batches": batch_summaries,
    }


def main() -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="Run V3 Pipeline A across multiple web-source topics or existing collections.")
    parser.add_argument("--topic", action="append", default=[], help="Web-source topic. Can be repeated.")
    parser.add_argument("--collection-dir", action="append", type=Path, default=[], help="Existing collection directory. Can be repeated.")
    parser.add_argument("--domain", action="append", default=DEFAULT_DOMAIN_TAGS, help="Domain tag for new collections. Can be repeated.")
    parser.add_argument("--query", action="append", default=[], help="Suggested query for all new topic collections. Can be repeated.")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--batch-report-path", type=Path, default=DEFAULT_BATCH_REPORT_PATH)
    parser.add_argument("--audit-report-path", type=Path, default=DEFAULT_AUDIT_REPORT_PATH)
    parser.add_argument("--readiness-report-path", type=Path, default=ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json")
    parser.add_argument("--search-backend", choices=["serper", "brave"], default="serper")
    parser.add_argument("--serper-api-key-env", default="SERPER_API_KEY")
    parser.add_argument("--collector-model", default="gpt-5-mini")
    parser.add_argument("--collector-max-turns", type=int, default=16)
    parser.add_argument("--collector-max-tokens", type=int, default=6000)
    parser.add_argument("--collector-timeout-seconds", type=int, default=2400)
    parser.add_argument("--provider", choices=["auto", "tuzi", "deepseek"], default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--allow-web-collection", action="store_true")
    parser.add_argument("--allow-external-upload", action="store_true")
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--dry-run-pipeline", action="store_true", help="Run collection/normalization/source quality only; skip LLM extraction.")
    parser.add_argument("--min-sources", type=int, default=1)
    parser.add_argument("--min-text-chars", type=int, default=500)
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--deepseek-key-path", type=Path, default=DEFAULT_DEEPSEEK_KEY_PATH)
    parser.add_argument("--build-transition-graph", action="store_true", help="Build report-only transition graph and composition readiness artifacts.")
    parser.add_argument("--skip-registry-update", action="store_true", help="Run extraction, review, and diagnostics without writing accepted candidates into the persistent registry.")
    parser.add_argument("--calibration-only", action="store_true", help="Shortcut for graph calibration: skip persistent registry update and build transition graph reports.")
    args = parser.parse_args()
    if args.calibration_only:
        args.skip_registry_update = True
        args.build_transition_graph = True

    args.output_root.mkdir(parents=True, exist_ok=True)
    batch_inputs = []
    for topic in args.topic or ([] if args.collection_dir else DEFAULT_TOPICS):
        batch_inputs.append((topic, collection_dir_for_topic(args.output_root, topic)))
    for collection_dir in args.collection_dir:
        resolved = collection_dir.resolve()
        batch_inputs.append((infer_topic_from_collection(resolved), resolved))

    if not batch_inputs:
        raise RuntimeError("No topics or collection directories were provided.")
    if not args.allow_external_upload and not args.dry_run_pipeline:
        raise RuntimeError("External LLM extraction requires --allow-external-upload.")

    registry_count_before = registry_entry_count(args.registry_path)
    batch_summaries = [
        run_topic_batch(args, topic=topic, collection_dir=collection_dir)
        for topic, collection_dir in batch_inputs
    ]
    registry_count_after = registry_entry_count(args.registry_path)
    report = aggregate_report(args, batch_summaries, registry_count_before, registry_count_after)
    write_json(args.batch_report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
