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
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_RW_TASK_ROOT,
    STAGE_ORDER,
    EndToEndPipeline,
    EndToEndRequest,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the report-first V3 end-to-end source-to-eval pipeline hub."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--stage",
        choices=["all", *STAGE_ORDER],
        default="all",
        help="Run all stages or one observable stage.",
    )
    parser.add_argument(
        "--source-mode",
        choices=["web", "local", "existing"],
        default="existing",
    )
    parser.add_argument(
        "--registry-mode",
        choices=["existing", "fresh_scratch"],
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
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--apply-registry-update", action="store_true")
    parser.add_argument("--skip-registry-update", action="store_true")
    parser.add_argument("--allow-web-collection", action="store_true")
    parser.add_argument("--allow-external-upload", action="store_true")
    parser.add_argument("--review-spec-path")
    parser.add_argument(
        "--eval-mode",
        choices=["dry-run", "execute"],
        default="dry-run",
    )
    parser.add_argument("--run-eval", action="store_true")
    parser.add_argument("--allow-draft-eval", action="store_true")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--rw-task-root", default=str(DEFAULT_RW_TASK_ROOT))
    parser.add_argument("--env-path", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--force-stage", action="store_true")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()

    selected_stages = STAGE_ORDER if args.stage == "all" else [args.stage]
    request = EndToEndRequest(
        run_id=args.run_id,
        selected_stages=selected_stages,
        source_mode=args.source_mode,
        registry_mode=args.registry_mode,
        registry_path=args.registry_path,
        topics=args.topic,
        collection_dirs=args.collection_dir,
        local_source_dir=args.local_source_dir,
        source_limit=args.source_limit,
        collector_backend=args.collector_backend,
        collector_max_turns=args.collector_max_turns,
        max_cases=args.max_cases,
        apply_registry_update=args.apply_registry_update and not args.skip_registry_update,
        allow_web_collection=args.allow_web_collection,
        allow_external_upload=args.allow_external_upload,
        reuse_existing=args.reuse_existing,
        force_stage=args.force_stage,
        review_spec_path=args.review_spec_path,
        eval_mode=args.eval_mode,
        run_eval=args.run_eval,
        allow_draft_eval=args.allow_draft_eval,
        models=args.model,
        rw_task_root=args.rw_task_root,
        env_path=args.env_path,
        python_exe=args.python_exe,
        timeout_seconds=args.timeout_seconds,
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
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
