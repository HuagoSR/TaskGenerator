from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_codex_local_solver import (  # noqa: E402
    CodexLocalTooling,
)
from task_generator.v3_external_model_comparison import (  # noqa: E402
    ExternalComparisonRunner,
    aggregate_external_comparison,
    compile_external_comparison_scope,
    grade_external_deliveries,
)
from task_generator.v3_skill_extractor import load_env_file  # noqa: E402


def _tuzi_credentials(env_path: Path) -> tuple[str, str]:
    values = load_env_file(env_path)
    key = (
        values.get("OPENAI_API_KEY")
        or values.get("AGENT_API_KEY")
        or values.get("GRADER_API_KEY")
    )
    base_url = (
        values.get("OPENAI_BASE_URL")
        or values.get("AGENT_BASE_URL")
        or values.get("GRADER_BASE_URL")
    )
    if not key or not base_url:
        raise SystemExit("tuzi_credentials_missing")
    return key, base_url


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen 24-task external model stack comparison."
        )
    )
    parser.add_argument(
        "--action",
        choices=("compile-scope", "execute", "grade", "aggregate"),
        required=True,
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--env-path", type=Path, default=ROOT / ".env")
    parser.add_argument("--tooling-root", type=Path)
    parser.add_argument("--representative-campaign", type=Path)
    parser.add_argument("--baseline-solver-manifest", type=Path)
    parser.add_argument("--baseline-grader-manifest", type=Path)
    parser.add_argument("--baseline-grader-outcome", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--execution-manifest", type=Path)
    parser.add_argument("--comparison-grader-manifest", type=Path)
    parser.add_argument(
        "--codex-home", type=Path, default=Path.home() / ".codex"
    )
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=Path(sys.executable),
    )
    args = parser.parse_args()

    if args.action == "compile-scope":
        required = (
            args.tooling_root,
            args.representative_campaign,
            args.baseline_solver_manifest,
            args.baseline_grader_manifest,
            args.baseline_grader_outcome,
            args.parity_report,
        )
        if any(item is None for item in required):
            raise SystemExit("compile_scope_inputs_missing")
        _, base_url = _tuzi_credentials(args.env_path)
        scope, scope_path, receipt_path = (
            compile_external_comparison_scope(
                representative_campaign_path=(
                    args.representative_campaign
                ),
                baseline_solver_manifest_path=(
                    args.baseline_solver_manifest
                ),
                baseline_grader_manifest_path=(
                    args.baseline_grader_manifest
                ),
                baseline_grader_outcome_path=(
                    args.baseline_grader_outcome
                ),
                parity_report_path=args.parity_report,
                cli_identity=CodexLocalTooling(
                    args.tooling_root
                ).freeze_identity(),
                repository_root=ROOT,
                output_root=args.output_root,
                base_url=base_url,
            )
        )
        print(
            json.dumps(
                {
                    "scope_path": str(scope_path),
                    "scope_sha256": scope_path.stem,
                    "receipt_path": str(receipt_path),
                    "models": [
                        item.model for item in scope.external_stacks
                    ],
                    "task_count_per_model": len(scope.task_bindings),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.action == "execute":
        if not args.scope or not args.receipt:
            raise SystemExit("execute_scope_receipt_missing")
        key, _ = _tuzi_credentials(args.env_path)
        manifest, path = ExternalComparisonRunner(
            scope_path=args.scope,
            receipt_path=args.receipt,
            output_root=args.output_root,
            python_executable=args.python_executable,
            tuzi_api_key=key,
        ).execute()
        print(
            json.dumps(
                {
                    "status": manifest.status,
                    "stacks": {
                        key: value.status
                        for key, value in manifest.stacks.items()
                    },
                    "manifest_path": str(path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.action == "grade":
        if not args.scope or not args.execution_manifest:
            raise SystemExit("grade_inputs_missing")
        manifest, path = grade_external_deliveries(
            scope_path=args.scope,
            execution_manifest_path=args.execution_manifest,
            output_root=args.output_root,
            codex_home=args.codex_home,
            python_executable=args.python_executable,
        )
        print(
            json.dumps(
                {
                    "status": manifest.status,
                    "completed": {
                        stack: sum(
                            item.status == "completed"
                            for item in records.values()
                        )
                        for stack, records in manifest.records.items()
                    },
                    "manifest_path": str(path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if (
        not args.scope
        or not args.execution_manifest
        or not args.comparison_grader_manifest
    ):
        raise SystemExit("aggregate_inputs_missing")
    result, path = aggregate_external_comparison(
        scope_path=args.scope,
        execution_manifest_path=args.execution_manifest,
        grader_manifest_path=args.comparison_grader_manifest,
        output_path=args.output_root / "comparison_result.json",
    )
    print(
        json.dumps(
            {
                "decision": result.decision,
                "ranking": result.practical_ranking,
                "stack_summaries": [
                    item.model_dump(mode="json")
                    for item in result.stack_summaries
                ],
                "result_path": str(path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
