from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
for path in (ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_v3_collected_sources_to_skill_package import load_raw_sources  # noqa: E402
from run_v3_local_source_to_skill import build_prompt_package, normalize_source  # noqa: E402
from task_generator.v3_skill_extractor import (  # noqa: E402
    FallbackSkillExtractor,
    LLMSkillExtractor,
    ProviderAttempt,
    build_deepseek_config,
    build_tuzi_config,
)
from task_generator.v3_skill_registry import SkillRegistryBuilder  # noqa: E402
from task_generator.v3_skill_reviewer import SkillCandidateReviewer  # noqa: E402
from task_generator.v3_skill_graph_diagnostics import (  # noqa: E402
    build_graph_extraction_diagnostics,
    write_graph_extraction_diagnostics,
)
from task_generator.v3_skill_transition_graph import (  # noqa: E402
    SkillTransitionGraphBuilder,
    load_optional_json,
    load_optional_motif_hints,
    load_optional_trace_edges,
    write_graph_report,
)
from task_generator.v3_source_schema import (  # noqa: E402
    ExtractedSkillCandidate,
    NormalizedSource,
    RawSource,
    SkillExtractionPromptPackage,
    dump_json_file,
    load_json_file,
    load_skill_candidates,
)


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_BATCH_REPORT_PATH = ROOT / "SkillRegistry" / "v3_web_source_pipeline_a_report.json"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_DEEPSEEK_KEY_PATH = ROOT / "deepseek-key.txt"
DEFAULT_AUDIT_REPORT_PATH = ROOT / "SkillRegistry" / "v3_skill_registry_audit_report.json"
DEFAULT_READINESS_REPORT_PATH = ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_text_length(raw_source: RawSource) -> Tuple[int, bool]:
    if not raw_source.raw_text_path:
        return 0, False
    path = Path(raw_source.raw_text_path)
    if not path.exists():
        return 0, False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(text.strip()), True


def normalize_collection(collection_dir: Path, output_dir: Path, reuse_existing: bool) -> SkillExtractionPromptPackage:
    package_path = output_dir / "skill_extraction_prompt_package.json"
    if reuse_existing and package_path.exists():
        return SkillExtractionPromptPackage.model_validate(load_json_file(str(package_path)))

    raw_sources = load_raw_sources(collection_dir)
    norm_dir = output_dir / "normalized_sources"
    norm_dir.mkdir(parents=True, exist_ok=True)

    normalized_sources: List[NormalizedSource] = []
    manifest_rows = []
    for raw_source in raw_sources:
        normalized = normalize_source(raw_source)
        dump_json_file(normalized, str(norm_dir / f"{normalized.normalized_source_id}.json"))
        normalized_sources.append(normalized)
        manifest_rows.append(
            {
                "source_id": raw_source.source_id,
                "normalized_source_id": normalized.normalized_source_id,
                "title": raw_source.title,
                "url_or_path": raw_source.url_or_path,
                "block_count": len(normalized.blocks),
            }
        )

    package = build_prompt_package(normalized_sources)
    dump_json_file(package, str(package_path))
    write_json(
        output_dir / "manifest.json",
        {
            "collection_dir": str(collection_dir),
            "source_count": len(raw_sources),
            "normalized_source_count": len(normalized_sources),
            "sources": manifest_rows,
        },
    )
    return package


def diagnose_sources(
    collection_dir: Path,
    normalized_package_dir: Path,
    min_sources: int,
    min_text_chars: int,
) -> Dict[str, object]:
    raw_sources = load_raw_sources(collection_dir)
    normalized_by_source: Dict[str, NormalizedSource] = {}
    norm_dir = normalized_package_dir / "normalized_sources"
    if norm_dir.exists():
        for path in sorted(norm_dir.glob("*.json")):
            normalized = NormalizedSource.model_validate(load_json_file(str(path)))
            normalized_by_source[normalized.source_id] = normalized

    url_counts = Counter(source.url_or_path.strip().lower() for source in raw_sources if source.url_or_path)
    source_reports = []
    warning_counts: Counter[str] = Counter()
    fail_counts: Counter[str] = Counter()

    for source in raw_sources:
        warnings = []
        failures = []
        text_chars, raw_text_exists = read_text_length(source)
        normalized = normalized_by_source.get(source.source_id)
        block_count = len(normalized.blocks) if normalized else 0

        if not source.title.strip():
            failures.append("missing_title")
        if not source.url_or_path.strip():
            failures.append("missing_url_or_path")
        if not raw_text_exists:
            failures.append("missing_raw_text")
        elif text_chars < min_text_chars:
            warnings.append("short_raw_text")
        if not source.collection_trace:
            warnings.append("missing_collection_trace")
        if url_counts[source.url_or_path.strip().lower()] > 1:
            warnings.append("duplicate_url")
        if normalized is None:
            failures.append("missing_normalized_source")
        elif block_count == 0:
            failures.append("empty_normalized_blocks")

        warning_counts.update(warnings)
        fail_counts.update(failures)
        source_reports.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "url_or_path": source.url_or_path,
                "text_char_count": text_chars,
                "normalized_block_count": block_count,
                "domain_tags": source.domain_tags,
                "status": "fail" if failures else ("warn" if warnings else "pass"),
                "warnings": warnings,
                "failures": failures,
            }
        )

    failed_sources = sum(1 for item in source_reports if item["status"] == "fail")
    warning_sources = sum(1 for item in source_reports if item["status"] == "warn")
    global_failures = []
    if len(raw_sources) < min_sources:
        global_failures.append("insufficient_source_count")
    if failed_sources:
        global_failures.append("source_quality_failures")

    status = "fail" if global_failures else ("warn" if warning_sources else "pass")
    return {
        "collection_dir": str(collection_dir),
        "normalized_package_dir": str(normalized_package_dir),
        "status": status,
        "source_count": len(raw_sources),
        "min_sources": min_sources,
        "min_text_chars": min_text_chars,
        "failed_source_count": failed_sources,
        "warning_source_count": warning_sources,
        "global_failures": global_failures,
        "warning_counts": dict(sorted(warning_counts.items())),
        "failure_counts": dict(sorted(fail_counts.items())),
        "sources": source_reports,
    }


def build_external_extractor(args: argparse.Namespace) -> FallbackSkillExtractor:
    extractors = []
    if args.provider in {"auto", "tuzi"}:
        tuzi_config = build_tuzi_config(args.env_path, args.model, args.timeout_seconds)
        if tuzi_config is not None:
            tuzi_config.max_tokens = args.max_tokens
            tuzi_config.output_profile = getattr(args, "output_profile", "standard")
            extractors.append(("tuzi", LLMSkillExtractor(tuzi_config)))
        elif args.provider == "tuzi":
            raise RuntimeError("Tuzi provider requested, but .env provider config is incomplete.")

    if args.provider in {"auto", "deepseek"}:
        deepseek_config = build_deepseek_config(args.deepseek_key_path, args.deepseek_model, args.timeout_seconds)
        if deepseek_config is not None:
            deepseek_config.max_tokens = args.max_tokens
            deepseek_config.output_profile = getattr(args, "output_profile", "standard")
            extractors.append(("deepseek", LLMSkillExtractor(deepseek_config)))
        elif args.provider == "deepseek":
            raise RuntimeError("DeepSeek provider requested, but deepseek-key.txt is missing or empty.")

    if not extractors:
        raise RuntimeError("No external LLM provider is configured. Web-source Pipeline A does not use mock fallback.")
    return FallbackSkillExtractor(extractors=extractors, allow_mock_fallback=False)


def write_extraction_outputs(
    output_dir: Path,
    package: SkillExtractionPromptPackage,
    provider_name: str,
    candidates: List[ExtractedSkillCandidate],
    attempts: List[ProviderAttempt],
    trace_edges: List[object] | None = None,
    motif_hints: List[object] | None = None,
) -> None:
    trace_edges = trace_edges or []
    motif_hints = motif_hints or []
    write_json(
        output_dir / "extracted_skill_candidates.json",
        {
            "request_id": package.request_id,
            "extractor": provider_name,
            "candidate_count": len(candidates),
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        },
    )
    write_json(
        output_dir / "skill_extraction_report.json",
        {
            "request_id": package.request_id,
            "normalized_source_count": len(package.normalized_sources),
            "candidate_count": len(candidates),
            "trace_edge_count": len(trace_edges),
            "motif_hint_count": len(motif_hints),
            "candidate_names": [candidate.proposed_name for candidate in candidates],
            "provider_used": provider_name,
        },
    )
    write_json(
        output_dir / "provider_attempts.json",
        {
            "request_id": package.request_id,
            "attempts": [attempt.to_report() for attempt in attempts],
        },
    )
    write_json(
        output_dir / "skill_trace_edges.json",
        {
            "request_id": package.request_id,
            "trace_edge_count": len(trace_edges),
            "trace_edges": [edge.model_dump(mode="json") for edge in trace_edges],
        },
    )
    write_json(
        output_dir / "skill_motif_hints.json",
        {
            "request_id": package.request_id,
            "motif_hint_count": len(motif_hints),
            "motif_hints": [hint.model_dump(mode="json") for hint in motif_hints],
        },
    )
    write_graph_extraction_diagnostics(
        build_graph_extraction_diagnostics(
            candidates=candidates,
            trace_edges=trace_edges,
            motif_hints=motif_hints,
            package=package,
        ),
        output_dir / "graph_extraction_diagnostics.json",
    )


def ensure_graph_extraction_diagnostics(
    output_dir: Path,
    package: SkillExtractionPromptPackage,
    candidates: List[ExtractedSkillCandidate],
) -> Dict[str, object]:
    diagnostics = build_graph_extraction_diagnostics(
        candidates=candidates,
        trace_edges=load_optional_trace_edges(output_dir / "skill_trace_edges.json"),
        motif_hints=load_optional_motif_hints(output_dir / "skill_motif_hints.json"),
        package=package,
    )
    write_graph_extraction_diagnostics(diagnostics, output_dir / "graph_extraction_diagnostics.json")
    return diagnostics


def run_extraction(args: argparse.Namespace, package: SkillExtractionPromptPackage, output_dir: Path) -> List[ExtractedSkillCandidate]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / "extracted_skill_candidates.json"
    if args.reuse_existing and candidate_path.exists():
        candidates = load_skill_candidates(str(candidate_path))
        ensure_graph_extraction_diagnostics(output_dir, package, candidates)
        return candidates
    if not args.allow_external_upload:
        raise RuntimeError("External LLM extraction requires --allow-external-upload for approved public web-source packages.")

    extractor = build_external_extractor(args)
    candidates = extractor.extract(package, max_candidates=args.max_candidates)
    provider_used = next((attempt.provider_name for attempt in extractor.attempts if attempt.success), "unknown")
    write_extraction_outputs(
        output_dir,
        package,
        provider_used,
        candidates,
        extractor.attempts,
        trace_edges=extractor.last_trace_edges,
        motif_hints=extractor.last_motif_hints,
    )
    return candidates


def run_review(candidates: List[ExtractedSkillCandidate], output_dir: Path) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reviewer = SkillCandidateReviewer()
    reviews = reviewer.review_many(candidates)
    accepted = reviewer.accepted_candidates(candidates, reviews)
    report_payload = {
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "revise_count": sum(1 for review in reviews if review.decision == "revise"),
        "rejected_count": sum(1 for review in reviews if review.decision == "reject"),
        "decisions": [
            {
                "candidate_id": review.candidate_id,
                "proposed_name": review.proposed_name,
                "decision": review.decision,
                "total_score": review.scores.total_score,
                "reason_codes": review.reason_codes,
                "suggested_abstraction": review.suggested_abstraction,
            }
            for review in reviews
        ],
    }
    write_json(
        output_dir / "reviewed_skill_candidates.json",
        {
            "candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "reviews": [review.model_dump(mode="json") for review in reviews],
        },
    )
    write_json(
        output_dir / "accepted_skill_candidates.json",
        {
            "candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "accepted_candidates": [candidate.model_dump(mode="json") for candidate in accepted],
        },
    )
    write_json(output_dir / "skill_candidate_review_report.json", report_payload)
    return {
        "report": report_payload,
        "accepted_candidates": accepted,
        "accepted_candidates_path": str(output_dir / "accepted_skill_candidates.json"),
    }


def update_registry(registry_path: Path, accepted_candidates: List[ExtractedSkillCandidate], output_dir: Path) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    builder = SkillRegistryBuilder()
    existing_entries = builder.load_registry(registry_path)
    updated_entries, report = builder.update_registry(existing_entries, accepted_candidates)
    builder.write_registry(registry_path, updated_entries)
    report["registry_path"] = str(registry_path)
    write_json(output_dir / "registry_update_report.json", report)
    return report


def skip_registry_update(
    registry_path: Path,
    accepted_candidates: List[ExtractedSkillCandidate],
    output_dir: Path,
) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    builder = SkillRegistryBuilder()
    existing_entries = builder.load_registry(registry_path)
    registry_count = len(existing_entries)
    report = {
        "status": "skipped",
        "registry_update_mode": "skipped",
        "registry_update_skipped": True,
        "registry_path": str(registry_path),
        "accepted_candidate_count": len(accepted_candidates),
        "initial_entry_count": registry_count,
        "final_entry_count": registry_count,
        "new_entry_count": 0,
        "merged_candidate_count": 0,
        "skipped_candidate_count": 0,
        "possible_duplicates": [],
        "note": "Persistent registry update was skipped for graph calibration; SkillRegistryEntry records were not modified.",
    }
    write_json(output_dir / "registry_update_skipped_report.json", report)
    return report


def build_transition_graph_reports(
    args: argparse.Namespace,
    candidates: List[ExtractedSkillCandidate],
    accepted_candidates: List[ExtractedSkillCandidate],
    extraction_dir: Path,
    output_dir: Path,
) -> Dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_entries = SkillRegistryBuilder().load_registry(args.registry_path)
    transition_report, composition_report = SkillTransitionGraphBuilder().build_reports(
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        registry_entries=registry_entries,
        trace_edges=load_optional_trace_edges(extraction_dir / "skill_trace_edges.json"),
        motif_hints=load_optional_motif_hints(extraction_dir / "skill_motif_hints.json"),
        readiness_report=load_optional_json(args.readiness_report_path),
    )
    transition_path = output_dir / "skill_transition_graph_report.json"
    composition_path = output_dir / "composition_readiness_report.json"
    write_graph_report(transition_path, transition_report)
    write_graph_report(composition_path, composition_report)
    return {
        "transition_graph_report_path": str(transition_path),
        "composition_readiness_report_path": str(composition_path),
        "edge_count": transition_report["edge_count"],
        "motif_count": transition_report["motif_count"],
        "usable_edge_count": transition_report["edge_decision_counts"].get("usable", 0),
        "blocked_edge_count": transition_report["edge_decision_counts"].get("blocked", 0),
        "edge_scope_counts": transition_report.get("edge_scope_counts", {}),
        "registry_mapped_edge_count": transition_report.get("registry_mapped_edge_count", 0),
        "candidate_local_edge_count": transition_report.get("candidate_local_edge_count", 0),
        "top_motifs": sorted(
            transition_report["motif_counts"].items(),
            key=lambda item: (-item[1], item[0]),
        )[:5],
        "role_counts": composition_report["role_counts"],
    }


def reason_code_counts(review_report: Dict[str, object]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for decision in review_report.get("decisions", []):
        counts.update(decision.get("reason_codes", []))
    return dict(sorted(counts.items()))


def run_pipeline(args: argparse.Namespace) -> Dict[str, object]:
    collection_dir = args.collection_dir.resolve()
    output_dir = args.output_dir or (collection_dir / "pipeline_a_run")
    normalized_dir = output_dir / "normalized_package"
    extraction_dir = output_dir / "extraction"
    review_dir = output_dir / "review"
    registry_update_dir = output_dir / "registry_update"
    if not hasattr(args, "skip_registry_update"):
        args.skip_registry_update = False
    if not hasattr(args, "calibration_only"):
        args.calibration_only = False
    if getattr(args, "calibration_only", False):
        args.skip_registry_update = True
        args.build_transition_graph = True

    output_dir.mkdir(parents=True, exist_ok=True)
    builder = SkillRegistryBuilder()
    registry_count_before = len(builder.load_registry(args.registry_path))
    package = normalize_collection(collection_dir, normalized_dir, reuse_existing=args.reuse_existing)
    source_quality = diagnose_sources(collection_dir, normalized_dir, args.min_sources, args.min_text_chars)
    write_json(output_dir / "source_quality_report.json", source_quality)

    if source_quality["status"] == "fail":
        raise RuntimeError("Source quality check failed; inspect source_quality_report.json before LLM extraction.")

    if args.dry_run:
        report = {
            "status": "dry_run_complete",
            "collection_dir": str(collection_dir),
            "output_dir": str(output_dir),
            "prompt_package": str(normalized_dir / "skill_extraction_prompt_package.json"),
            "source_quality_report": str(output_dir / "source_quality_report.json"),
            "source_quality_status": source_quality["status"],
            "source_count": source_quality["source_count"],
            "registry_path": str(args.registry_path),
            "registry_entry_count_before": registry_count_before,
            "registry_entry_count_after": registry_count_before,
            "registry_entry_delta_this_run": 0,
            "registry_update_mode": "not_applicable",
            "registry_update_skipped": True,
            "note": "Dry run stops before external LLM extraction and registry update.",
        }
        write_json(output_dir / "web_source_pipeline_a_report.json", report)
        return report

    candidates = run_extraction(args, package, extraction_dir)
    graph_extraction_diagnostics = ensure_graph_extraction_diagnostics(extraction_dir, package, candidates)
    review_result = run_review(candidates, review_dir)
    if args.skip_registry_update:
        registry_report = skip_registry_update(args.registry_path, review_result["accepted_candidates"], registry_update_dir)
        registry_update_mode = "skipped"
    else:
        registry_report = update_registry(args.registry_path, review_result["accepted_candidates"], registry_update_dir)
        registry_update_mode = "updated"
    graph_summary = {}
    if args.build_transition_graph:
        graph_summary = build_transition_graph_reports(
            args,
            candidates,
            review_result["accepted_candidates"],
            extraction_dir,
            output_dir / "transition_graph",
        )

    final_entries = builder.load_registry(args.registry_path)
    registry_count_after = len(final_entries)
    report = {
        "status": "success",
        "collection_dir": str(collection_dir),
        "output_dir": str(output_dir),
        "prompt_package": str(normalized_dir / "skill_extraction_prompt_package.json"),
        "source_quality_report": str(output_dir / "source_quality_report.json"),
        "source_quality_status": source_quality["status"],
        "source_count": source_quality["source_count"],
        "candidate_count": len(candidates),
        "accepted_count": review_result["report"]["accepted_count"],
        "revise_count": review_result["report"]["revise_count"],
        "rejected_count": review_result["report"]["rejected_count"],
        "review_reason_code_counts": reason_code_counts(review_result["report"]),
        "graph_extraction_diagnostics": {
            "path": str(extraction_dir / "graph_extraction_diagnostics.json"),
            "resource_count": graph_extraction_diagnostics["typed_resource_summary"]["resource_count"],
            "trace_edge_count": graph_extraction_diagnostics["trace_edge_summary"]["trace_edge_count"],
            "motif_hint_count": graph_extraction_diagnostics["motif_hint_summary"]["motif_hint_count"],
            "warning_codes": [warning["code"] for warning in graph_extraction_diagnostics["warnings"]],
            "is_graph_ready": graph_extraction_diagnostics["is_graph_ready"],
        },
        "accepted_candidates_path": review_result["accepted_candidates_path"],
        "registry_path": str(args.registry_path),
        "registry_update_mode": registry_update_mode,
        "registry_update_skipped": args.skip_registry_update,
        "registry_entry_count_before": registry_count_before,
        "registry_entry_count_after": registry_count_after,
        "registry_entry_delta_this_run": registry_count_after - registry_count_before,
        "registry_new_entry_count": registry_report["new_entry_count"],
        "registry_merged_candidate_count": registry_report["merged_candidate_count"],
        "registry_skipped_candidate_count": registry_report["skipped_candidate_count"],
        "registry_final_entry_count": registry_report["final_entry_count"],
        "possible_duplicate_count": len(registry_report["possible_duplicates"]),
        "coverage": builder.coverage_report(final_entries),
        "provider": args.provider,
        "model": args.model,
        "deepseek_model": args.deepseek_model,
        "max_candidates": args.max_candidates,
        "max_tokens": args.max_tokens,
        "timeout_seconds": args.timeout_seconds,
        "reuse_existing": args.reuse_existing,
        "registry_audit_report": {
            "path": str(args.audit_report_path),
            "exists": args.audit_report_path.exists(),
            "note": "Web-source runner does not execute or apply registry audit automatically.",
        },
        "graph_summary": graph_summary,
    }
    write_json(output_dir / "web_source_pipeline_a_report.json", report)
    write_json(args.batch_report_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V3 Pipeline A on an existing web source collection.")
    parser.add_argument("--collection-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--batch-report-path", type=Path, default=DEFAULT_BATCH_REPORT_PATH)
    parser.add_argument("--audit-report-path", type=Path, default=DEFAULT_AUDIT_REPORT_PATH)
    parser.add_argument("--readiness-report-path", type=Path, default=DEFAULT_READINESS_REPORT_PATH)
    parser.add_argument("--provider", choices=["auto", "tuzi", "deepseek"], default="deepseek")
    parser.add_argument("--model", default=None, help="Override .env OPENAI_MODEL for Tuzi/OpenAI-compatible provider.")
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--allow-external-upload", action="store_true")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse existing normalized package or extraction outputs when present.")
    parser.add_argument("--dry-run", action="store_true", help="Stop after normalization and source quality diagnostics.")
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

    report = run_pipeline(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



