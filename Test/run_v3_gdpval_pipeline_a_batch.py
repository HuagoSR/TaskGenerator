import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_v3_gdpval_prompt_sources import (  # noqa: E402
    DEFAULT_GDPVAL_ARROW,
    build_normalized_source,
    build_prompt_package,
    infer_domain_tags,
    load_gdpval_rows,
    slugify,
)
from v3_skill_extractor import (  # noqa: E402
    FallbackSkillExtractor,
    LLMSkillExtractor,
    ProviderAttempt,
    build_deepseek_config,
    build_tuzi_config,
)
from v3_skill_registry import SkillRegistryBuilder  # noqa: E402
from v3_skill_reviewer import SkillCandidateReviewer  # noqa: E402
from v3_source_schema import (  # noqa: E402
    ExtractedSkillCandidate,
    NormalizedSource,
    SkillExtractionPromptPackage,
    dump_json_file,
    load_skill_candidates,
)


DEFAULT_OUTPUT_ROOT = ROOT / "Test" / "v3_gdpval_prompt_sources" / "pipeline_a_batches"
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_BATCH_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_a_batch_report.json"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_DEEPSEEK_KEY_PATH = ROOT / "deepseek-key.txt"
DEFAULT_OCCUPATIONS = [
    "Financial and Investment Analysts",
    "Financial Managers",
    "Compliance Officers",
]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def rows_for_batch(rows: List[Dict[str, object]], occupation: str, limit: int) -> List[Dict[str, object]]:
    matched = [
        row for row in rows
        if occupation.lower() in str(row.get("occupation", "")).lower()
    ]
    selected = matched[:limit] if limit > 0 else matched
    if not selected:
        raise RuntimeError(f"No GDPVal rows matched occupation: {occupation}")
    return selected


def write_prompt_package(
    output_dir: Path,
    rows: List[Dict[str, object]],
    include_public_upload_note: bool,
) -> SkillExtractionPromptPackage:
    output_dir.mkdir(parents=True, exist_ok=True)
    norm_dir = output_dir / "normalized_sources"
    norm_dir.mkdir(parents=True, exist_ok=True)

    normalized_sources = [build_normalized_source(row) for row in rows]
    for source in normalized_sources:
        dump_json_file(source, str(norm_dir / f"{source.normalized_source_id}.json"))

    package = build_prompt_package(normalized_sources, include_public_upload_note=include_public_upload_note)
    dump_json_file(package, str(output_dir / "skill_extraction_prompt_package.json"))

    manifest = {
        "source": "openai/gdpval",
        "split": "train",
        "prompt_only": True,
        "excludes": ["rubric", "reference_files", "deliverable_files", "answers", "data_file_contents"],
        "row_count": len(rows),
        "rows": [
            {
                "task_id": str(row.get("task_id", "")),
                "sector": str(row.get("sector", "")),
                "occupation": str(row.get("occupation", "")),
                "source_id": source.source_id,
                "normalized_source_id": source.normalized_source_id,
                "prompt_char_count": len(str(row.get("prompt", ""))),
                "domain_tags": infer_domain_tags(row),
            }
            for row, source in zip(rows, normalized_sources)
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "README.md").write_text(
        "# GDPVal Pipeline A Prompt-Only Batch\n\n"
        "This batch contains GDPVal prompt text and task metadata only.\n\n"
        "It excludes rubrics, reference files, deliverable files, answer traces, and file contents.\n",
        encoding="utf-8",
    )
    return package


def build_external_extractor(args: argparse.Namespace) -> FallbackSkillExtractor:
    extractors = []
    if args.provider in {"auto", "tuzi"}:
        tuzi_config = build_tuzi_config(args.env_path, args.model, args.timeout_seconds)
        if tuzi_config is not None:
            tuzi_config.max_tokens = args.max_tokens
            extractors.append(("tuzi", LLMSkillExtractor(tuzi_config)))
        elif args.provider == "tuzi":
            raise RuntimeError("Tuzi provider requested, but .env provider config is incomplete.")

    if args.provider in {"auto", "deepseek"}:
        deepseek_config = build_deepseek_config(args.deepseek_key_path, args.deepseek_model, args.timeout_seconds)
        if deepseek_config is not None:
            deepseek_config.max_tokens = args.max_tokens
            extractors.append(("deepseek", LLMSkillExtractor(deepseek_config)))
        elif args.provider == "deepseek":
            raise RuntimeError("DeepSeek provider requested, but deepseek-key.txt is missing or empty.")

    if not extractors:
        raise RuntimeError("No external LLM provider is configured. This batch runner does not use mock fallback.")
    return FallbackSkillExtractor(extractors=extractors, allow_mock_fallback=False)


def write_extraction_outputs(
    output_dir: Path,
    package: SkillExtractionPromptPackage,
    provider_name: str,
    candidates: List[ExtractedSkillCandidate],
    attempts: List[ProviderAttempt],
) -> None:
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


def run_extraction(args: argparse.Namespace, package: SkillExtractionPromptPackage, output_dir: Path) -> List[ExtractedSkillCandidate]:
    candidate_path = output_dir / "extracted_skill_candidates.json"
    if args.reuse_existing and candidate_path.exists():
        return load_skill_candidates(str(candidate_path))

    if not args.allow_external_upload:
        raise RuntimeError("External LLM extraction requires --allow-external-upload for approved GDPVal prompt-only batches.")

    extractor = build_external_extractor(args)
    candidates = extractor.extract(package, max_candidates=args.max_candidates)
    provider_used = next((attempt.provider_name for attempt in extractor.attempts if attempt.success), "unknown")
    write_extraction_outputs(output_dir, package, provider_used, candidates, extractor.attempts)
    return candidates


def run_review(candidates: List[ExtractedSkillCandidate], output_dir: Path) -> Dict[str, object]:
    reviewer = SkillCandidateReviewer()
    reviews = reviewer.review_many(candidates)
    accepted = reviewer.accepted_candidates(candidates, reviews)
    reviewed_payload = {
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "reviews": [review.model_dump(mode="json") for review in reviews],
    }
    accepted_payload = {
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "accepted_candidates": [candidate.model_dump(mode="json") for candidate in accepted],
    }
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
    write_json(output_dir / "reviewed_skill_candidates.json", reviewed_payload)
    write_json(output_dir / "accepted_skill_candidates.json", accepted_payload)
    write_json(output_dir / "skill_candidate_review_report.json", report_payload)
    return {
        "report": report_payload,
        "accepted_candidates": accepted,
        "accepted_candidates_path": str(output_dir / "accepted_skill_candidates.json"),
    }


def update_registry(
    registry_path: Path,
    accepted_candidates: List[ExtractedSkillCandidate],
    output_dir: Path,
) -> Dict[str, object]:
    builder = SkillRegistryBuilder()
    existing_entries = builder.load_registry(registry_path)
    updated_entries, report = builder.update_registry(existing_entries, accepted_candidates)
    builder.write_registry(registry_path, updated_entries)
    report["registry_path"] = str(registry_path)
    write_json(output_dir / "registry_update_report.json", report)
    return report


def run_batch(args: argparse.Namespace, rows: List[Dict[str, object]], occupation: str) -> Dict[str, object]:
    batch_slug = slugify(occupation)
    batch_dir = args.output_root / batch_slug
    selected_rows = rows_for_batch(rows, occupation, args.limit)
    package = write_prompt_package(batch_dir, selected_rows, include_public_upload_note=True)
    candidates = run_extraction(args, package, batch_dir / "extraction")
    review_result = run_review(candidates, batch_dir / "review")
    registry_report = update_registry(
        args.registry_path,
        review_result["accepted_candidates"],
        batch_dir / "registry_update",
    )
    return {
        "batch_id": batch_slug,
        "occupation": occupation,
        "row_count": len(selected_rows),
        "output_dir": str(batch_dir),
        "prompt_package": str(batch_dir / "skill_extraction_prompt_package.json"),
        "candidate_count": len(candidates),
        "accepted_count": review_result["report"]["accepted_count"],
        "revise_count": review_result["report"]["revise_count"],
        "rejected_count": review_result["report"]["rejected_count"],
        "registry_new_entry_count": registry_report["new_entry_count"],
        "registry_merged_candidate_count": registry_report["merged_candidate_count"],
        "registry_skipped_candidate_count": registry_report["skipped_candidate_count"],
        "registry_final_entry_count": registry_report["final_entry_count"],
        "possible_duplicate_count": len(registry_report["possible_duplicates"]),
        "accepted_candidates_path": review_result["accepted_candidates_path"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GDPVal prompt-only Pipeline A batch extraction, review, and persistent registry update.")
    parser.add_argument("--occupation", action="append", default=[], help="GDPVal occupation filter. Can be repeated.")
    parser.add_argument("--limit", type=int, default=5, help="Rows per occupation batch.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--batch-report-path", type=Path, default=DEFAULT_BATCH_REPORT_PATH)
    parser.add_argument("--provider", choices=["auto", "tuzi", "deepseek"], default="deepseek")
    parser.add_argument("--model", default=None, help="Override .env OPENAI_MODEL for Tuzi/OpenAI-compatible provider.")
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--allow-external-upload", action="store_true")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse existing extraction outputs when present.")
    parser.add_argument("--allow-network", action="store_true", help="Allow HuggingFace network access instead of local cache only.")
    parser.add_argument("--cache-arrow", type=Path, default=DEFAULT_GDPVAL_ARROW)
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--deepseek-key-path", type=Path, default=DEFAULT_DEEPSEEK_KEY_PATH)
    args = parser.parse_args()

    occupations = args.occupation or DEFAULT_OCCUPATIONS
    rows = load_gdpval_rows(local_files_only=not args.allow_network, cache_arrow=args.cache_arrow)
    batch_summaries = []
    for occupation in occupations:
        batch_summaries.append(run_batch(args, rows, occupation))

    builder = SkillRegistryBuilder()
    final_entries = builder.load_registry(args.registry_path)
    aggregate_report = {
        "registry_path": str(args.registry_path),
        "registry_entry_count": len(final_entries),
        "batch_count": len(batch_summaries),
        "batches": batch_summaries,
        "coverage": builder.coverage_report(final_entries),
        "provider": args.provider,
        "deepseek_model": args.deepseek_model,
        "reuse_existing": args.reuse_existing,
    }
    write_json(args.batch_report_path, aggregate_report)
    print(json.dumps(aggregate_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
