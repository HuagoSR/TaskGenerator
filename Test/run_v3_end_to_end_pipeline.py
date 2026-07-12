import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_end_to_end_pipeline import (  # noqa: E402
    DEFAULT_ENV_PATH,
    DEFAULT_DEEPSEEK_KEY_PATH,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_RW_TASK_ROOT,
    STAGE_ORDER,
    EndToEndPipeline,
    EndToEndRequest,
)
from task_generator.v3_domain_profile import DEFAULT_DOMAIN_PROFILE_PATH


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the report-first V3 end-to-end source-to-eval pipeline hub."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--action", choices=["run", "resume", "status", "rerun"], default="run")
    parser.add_argument(
        "--profile",
        choices=["custom", "public-smoke-offline", "public-smoke-llm", "local-existing", "local-source", "web-source", "finance-production"],
        default=None,
    )
    parser.add_argument("--from-stage", choices=STAGE_ORDER, default=None)
    parser.add_argument(
        "--stage",
        choices=["all", *STAGE_ORDER],
        default="all",
        help="Run all stages or one observable stage.",
    )
    parser.add_argument(
        "--source-mode",
        choices=["web", "local", "existing", "public_fixture"],
        default="existing",
    )
    parser.add_argument(
        "--registry-mode",
        choices=["existing", "fresh_scratch", "snapshot_scratch"],
        default=None,
        help="Registry source for this run. Defaults to existing for new runs and resumes from manifest for prior runs.",
    )
    parser.add_argument(
        "--registry-path",
        default=None,
        help="Optional custom registry path. Cannot be combined with --registry-mode fresh_scratch.",
    )
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument(
        "--collection-dir",
        action="append",
        default=[],
        help="Reuse an existing collected raw_sources directory instead of collecting again.",
    )
    parser.add_argument("--local-source-dir")
    parser.add_argument("--source-limit", type=int, default=3)
    parser.add_argument("--collector-backend", choices=["direct", "stirrup"], default="direct")
    parser.add_argument("--collector-max-turns", type=int, default=32)
    parser.add_argument("--topic-queries-path")
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--domain-profile", choices=["finance_audit", "warehouse_inventory"], default="finance_audit")
    parser.add_argument("--domain-profile-path", default=str(DEFAULT_DOMAIN_PROFILE_PATH))
    parser.add_argument("--motif", action="append", default=[])
    parser.add_argument("--case-index-offset", type=int, default=0)
    parser.add_argument("--target-difficulty-profile", default=None)
    parser.add_argument("--motif-occurrence-offset", action="append", default=[])
    parser.add_argument("--apply-registry-update", action="store_true")
    parser.add_argument("--skip-registry-update", action="store_true")
    parser.add_argument("--allow-web-collection", action="store_true")
    parser.add_argument("--allow-external-upload", action="store_true")
    parser.add_argument("--allow-external-source-upload", action="store_true")
    parser.add_argument("--allow-external-eval", action="store_true")
    parser.add_argument("--allow-external-semantic-review", action="store_true")
    parser.add_argument("--semantic-review-mode", choices=["disabled", "prepare", "diagnostic", "blocking"], default="disabled")
    parser.add_argument("--semantic-review-execute", action="store_true")
    parser.add_argument("--semantic-repair-iteration", type=int, default=0)
    parser.add_argument("--extractor-mode", choices=["none", "mock", "llm"], default="none")
    parser.add_argument(
        "--public-package-path",
        default=str(ROOT / "Test" / "v3_public_smoke_package" / "skill_extraction_prompt_package.json"),
    )
    parser.add_argument("--provider", choices=["auto", "tuzi", "deepseek", "mock"], default="deepseek")
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument("--extractor-model", default=None)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--extractor-max-tokens", type=int, default=6000)
    parser.add_argument("--extractor-output-profile", choices=["standard", "bounded_smoke", "bounded_production"], default="standard")
    parser.add_argument("--review-spec-path")
    parser.add_argument(
        "--eval-mode",
        choices=["dry-run", "prepare_only", "execute"],
        default="prepare_only",
    )
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--allow-draft-eval", action="store_true")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--rw-task-root", default=str(DEFAULT_RW_TASK_ROOT))
    parser.add_argument("--env-path", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--deepseek-key-path", default=str(DEFAULT_DEEPSEEK_KEY_PATH))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--force-stage", action="store_true")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()

    run_dir = Path(args.output_root) / args.run_id
    manifest_path = run_dir / "end_to_end_run_manifest.json"
    if args.action == "status":
        if not manifest_path.exists():
            raise SystemExit(f"Run manifest not found: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "run_id": payload.get("run_id"),
                    "manifest_version": payload.get("end_to_end_manifest_version"),
                    "run_status": payload.get("run_status", "legacy_v1"),
                    "stage_states": {key: value.get("state") for key, value in (payload.get("stages") or {}).items()},
                    "manifest_path": str(manifest_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    legacy_flags = {
        "--stage", "--source-mode", "--registry-mode", "--registry-path", "--topic",
        "--collection-dir", "--local-source-dir", "--apply-registry-update", "--run-eval",
    }
    legacy_invocation = args.profile is None and any(flag in sys.argv for flag in legacy_flags)
    profile = args.profile or ("custom" if legacy_invocation else "public-smoke-offline")
    if legacy_invocation:
        print(
            "DEPRECATED: flat end-to-end flags are running in custom compatibility mode; prefer --profile plus --action.",
            file=sys.stderr,
        )
    if profile == "public-smoke-offline":
        args.source_mode = "public_fixture"
        args.registry_mode = "fresh_scratch"
        args.extractor_mode = "mock"
        args.max_cases = 2
        args.eval_mode = "prepare_only"
        args.model = ["gpt-4o-mini"]
    elif profile == "public-smoke-llm":
        args.source_mode = "public_fixture"
        args.registry_mode = "fresh_scratch"
        args.extractor_mode = "llm"
        args.max_cases = 2
        args.max_candidates = 4
        args.extractor_max_tokens = 6000
        args.extractor_output_profile = "bounded_smoke"
        args.eval_mode = "prepare_only"
        args.model = ["gpt-4o-mini"]
        if not args.allow_external_source_upload:
            parser.error("public-smoke-llm requires --allow-external-source-upload")
    elif profile == "local-existing":
        args.source_mode = "existing"
        args.registry_mode = "snapshot_scratch"
        args.eval_mode = "prepare_only"
    elif profile == "local-source":
        args.source_mode = "local"
        args.registry_mode = "fresh_scratch"
        args.extractor_mode = "llm"
        args.eval_mode = "prepare_only"
    elif profile == "web-source":
        args.source_mode = "web"
        args.registry_mode = "fresh_scratch"
        args.extractor_mode = "llm"
        args.eval_mode = "prepare_only"
    elif profile == "finance-production":
        args.source_mode = "web"
        args.registry_mode = args.registry_mode or "fresh_scratch"
        args.extractor_mode = "llm"
        args.provider = "deepseek"
        args.deepseek_model = "deepseek-v4-flash"
        args.max_candidates = 6
        args.extractor_max_tokens = 8000
        args.extractor_output_profile = "bounded_production"
        args.eval_mode = "dry-run"
        args.model = []
        args.semantic_review_mode = "diagnostic" if args.allow_external_semantic_review else "prepare"
        args.semantic_review_execute = args.allow_external_semantic_review
        if not args.motif:
            args.motif = ["fan_in_reconciliation", "cross_check_validation", "policy_application"]
        if not args.allow_web_collection or not args.allow_external_source_upload:
            parser.error("finance-production requires --allow-web-collection and --allow-external-source-upload")

    if args.eval_mode == "execute" and not args.allow_external_eval:
        parser.error("eval execution requires --allow-external-eval")
    if profile not in {"custom", "finance-production"}:
        args.apply_registry_update = False

    selected_stages = STAGE_ORDER if args.stage == "all" else [args.stage]
    if profile == "finance-production" and args.stage == "all":
        selected_stages = ["production_review"]
    motif_occurrence_offsets = {}
    for item in args.motif_occurrence_offset:
        if "=" not in item:
            parser.error("--motif-occurrence-offset must use motif=integer")
        motif, value = item.split("=", 1)
        motif_occurrence_offsets[motif] = int(value)
    request = EndToEndRequest(
        run_id=args.run_id,
        selected_stages=selected_stages,
        action=args.action,
        profile=profile,
        from_stage=args.from_stage,
        source_mode=args.source_mode,
        registry_mode=args.registry_mode,
        registry_path=args.registry_path,
        topics=args.topic,
        collection_dirs=args.collection_dir,
        local_source_dir=args.local_source_dir,
        source_limit=args.source_limit,
        collector_backend=args.collector_backend,
        collector_max_turns=args.collector_max_turns,
        topic_queries_path=args.topic_queries_path,
        max_cases=args.max_cases,
        apply_registry_update=args.apply_registry_update and not args.skip_registry_update,
        allow_web_collection=args.allow_web_collection,
        allow_external_upload=args.allow_external_upload,
        allow_external_source_upload=args.allow_external_source_upload,
        allow_external_eval=args.allow_external_eval,
        allow_external_semantic_review=args.allow_external_semantic_review,
        extractor_mode=args.extractor_mode,
        public_package_path=args.public_package_path,
        provider=args.provider,
        model=args.extractor_model,
        deepseek_model=args.deepseek_model,
        max_candidates=args.max_candidates,
        extractor_max_tokens=args.extractor_max_tokens,
        extractor_output_profile=args.extractor_output_profile,
        reuse_existing=args.reuse_existing,
        force_stage=args.force_stage,
        review_spec_path=args.review_spec_path,
        eval_mode=args.eval_mode,
        run_eval=args.run_eval,
        allow_draft_eval=args.allow_draft_eval,
        models=args.model,
        rw_task_root=args.rw_task_root,
        env_path=args.env_path,
        deepseek_key_path=args.deepseek_key_path,
        python_exe=args.python_exe,
        timeout_seconds=args.timeout_seconds,
        domain_profile=args.domain_profile,
        domain_profile_path=args.domain_profile_path,
        motifs=args.motif,
        case_index_offset=args.case_index_offset,
        target_difficulty_profile=args.target_difficulty_profile,
        motif_occurrence_offsets=motif_occurrence_offsets,
        semantic_review_mode=args.semantic_review_mode,
        semantic_review_execute=args.semantic_review_execute,
        semantic_repair_iteration=args.semantic_repair_iteration,
    )
    if args.action in {"resume", "rerun"} and manifest_path.exists():
        stored_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if stored_payload.get("end_to_end_manifest_version") == "v3.end_to_end_pipeline.2":
            request = EndToEndRequest.model_validate(stored_payload["request"]).model_copy(
                update={
                    "action": args.action,
                    "from_stage": args.from_stage,
                    "reuse_existing": True,
                    "force_stage": args.action == "rerun",
                    "timeout_seconds": args.timeout_seconds or int(stored_payload["request"].get("timeout_seconds") or 0),
                }
            )

    manifest = EndToEndPipeline(repo_root=ROOT).run(request, output_root=args.output_root)
    print(
        json.dumps(
            {
                "run_id": manifest.run_id,
                "run_dir": manifest.run_dir,
                "manifest_path": str(Path(manifest.run_dir) / "end_to_end_run_manifest.json"),
                "stage_status_path": manifest.stage_status_path,
                "summary_report_path": manifest.summary_report_path,
                "stage_states": {
                    stage: status.state for stage, status in manifest.stages.items()
                },
                "run_status": manifest.run_status,
                "acceptance_report_path": manifest.acceptance_report_path,
                "lifecycle_index_path": manifest.lifecycle_index_path,
                "content_fingerprint": manifest.content_fingerprint,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
