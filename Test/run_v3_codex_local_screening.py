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
    CodexLocalRunner,
    CodexLocalScreeningFinalizer,
    CodexLocalTooling,
    compile_scope,
    compile_standing_receipt,
)
from task_generator.v3_compact_screening_grader import (  # noqa: E402
    CompactScreeningGraderV2,
    compile_compact_grader_scope,
)
from task_generator.v3_professional_calibration import (  # noqa: E402
    ProfessionalCalibrationRunnerV1,
    compile_professional_calibration_scope,
)
from task_generator.v3_semantic_review_executor import (  # noqa: E402
    tuzi_semantic_config,
)
from task_generator.v3_skill_extractor import (  # noqa: E402
    ProviderConfig,
    load_env_file,
)


DEFAULT_CAMPAIGN_ROOT = (
    ROOT
    / "artifacts"
    / "pipeline_reconstruction"
    / "route_comparison"
    / "r6_two_route_matched_screening_v2_20260721"
)
DEFAULT_OUTPUT_ROOT = (
    DEFAULT_CAMPAIGN_ROOT / "codex_local_screening_v1"
)
DEFAULT_TOOLING_ROOT = (
    ROOT
    / "artifacts"
    / "pipeline_reconstruction"
    / "codex_local_tooling"
)


def _deepseek_config(
    env_path: Path | None,
    key_path: Path | None,
    reasoning_mode: str = "high",
) -> ProviderConfig:
    values = load_env_file(env_path) if env_path else {}
    key = values.get("DEEPSEEK_API_KEY")
    if not key and key_path and key_path.is_file():
        key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit("deepseek_configuration_missing")
    return ProviderConfig(
        provider_name="deepseek",
        base_url="https://api.deepseek.com",
        api_key=key,
        model="deepseek-v4-pro",
        timeout_seconds=900,
        reasoning_mode=reasoning_mode,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the homogeneous 12-task matched screening with a pinned local "
            "Codex CLI and the retained route-blind DeepSeek grader."
        )
    )
    parser.add_argument(
        "--action",
        choices=(
            "install-cli",
            "freeze-cli",
            "compile-scope",
            "compile-receipt",
            "execute-solver",
            "finalize-grader",
            "compile-compact-grader",
            "execute-compact-grader",
            "compile-professional-calibration",
            "execute-professional-calibration",
        ),
        required=True,
    )
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--tooling-root", type=Path, default=DEFAULT_TOOLING_ROOT)
    parser.add_argument("--npm-executable", type=Path)
    parser.add_argument("--codex-version")
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    parser.add_argument("--env-path", type=Path)
    parser.add_argument("--solver-execution-root", type=Path)
    parser.add_argument("--compact-scope", type=Path)
    parser.add_argument("--compact-outcome", type=Path)
    parser.add_argument(
        "--deepseek-key-path",
        type=Path,
        default=ROOT / "deepseek-key.txt",
    )
    parser.add_argument(
        "--grader-reasoning-mode",
        choices=("high", "disabled"),
        default="high",
    )
    args = parser.parse_args()

    tooling = CodexLocalTooling(args.tooling_root)
    if args.action == "install-cli":
        if not args.npm_executable or not args.codex_version:
            raise SystemExit("install_cli_requires_npm_executable_and_version")
        identity = tooling.install_exact(
            version=args.codex_version,
            npm_executable=args.npm_executable,
        )
        print(
            json.dumps(
                {
                    "cli_identity": identity.model_dump(mode="json"),
                    "external_model_calls_made": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "freeze-cli":
        print(
            json.dumps(
                {
                    "cli_identity": tooling.freeze_identity().model_dump(
                        mode="json"
                    ),
                    "external_model_calls_made": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "compile-scope":
        if not args.parity_report:
            raise SystemExit("compile_scope_requires_parity_report")
        scope, path, digest = compile_scope(
            campaign_root=args.campaign_root,
            parity_report_path=args.parity_report,
            cli_identity=tooling.freeze_identity(),
            repository_root=ROOT,
            output_root=args.output_root,
        )
        print(
            json.dumps(
                {
                    "scope": scope.model_dump(mode="json"),
                    "scope_path": str(path),
                    "scope_sha256": digest,
                    "external_model_calls_made": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "compile-receipt":
        if not args.scope:
            raise SystemExit("compile_receipt_requires_scope")
        receipt, path = compile_standing_receipt(
            scope_path=args.scope,
            output_root=args.output_root,
        )
        print(
            json.dumps(
                {
                    "receipt": receipt.model_dump(mode="json"),
                    "receipt_path": str(path),
                    "external_model_calls_made": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "execute-solver":
        if not args.scope or not args.receipt:
            raise SystemExit("execute_solver_requires_scope_and_receipt")
        runner = CodexLocalRunner(
            scope_path=args.scope,
            receipt_path=args.receipt,
            campaign_root=args.campaign_root,
            output_root=args.output_root / "execution",
            codex_home=args.codex_home,
            python_executable=args.python_executable,
        )
        manifest, path = runner.run_solver()
        print(
            json.dumps(
                {
                    "status": manifest.status,
                    "manifest_path": str(path),
                    "first_failure": manifest.first_failure,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "compile-compact-grader":
        if not args.parity_report or not args.solver_execution_root:
            raise SystemExit(
                "compile_compact_grader_requires_parity_and_solver_execution"
            )
        scope, path, digest = compile_compact_grader_scope(
            campaign_root=args.campaign_root,
            solver_execution_root=args.solver_execution_root,
            output_root=args.output_root,
            parity_report_path=args.parity_report,
            repository_root=ROOT,
            deepseek_reasoning_mode=args.grader_reasoning_mode,
        )
        print(
            json.dumps(
                {
                    "scope": scope.model_dump(mode="json"),
                    "scope_path": str(path),
                    "scope_sha256": digest,
                    "external_model_calls_made": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "execute-compact-grader":
        if not args.scope:
            raise SystemExit("execute_compact_grader_requires_scope")
        grader = CompactScreeningGraderV2(
            scope_path=args.scope,
            output_root=args.output_root,
            provider_config=_deepseek_config(
                args.env_path,
                args.deepseek_key_path,
                args.grader_reasoning_mode,
            ),
        )
        outcome, path = grader.execute()
        print(
            json.dumps(
                {
                    "completed_grades": outcome.completed_grades,
                    "infrastructure_failed_grades": (
                        outcome.infrastructure_failed_grades
                    ),
                    "provider_calls": outcome.provider_calls,
                    "decision": outcome.screening_result.decision,
                    "score_distribution": outcome.score_distribution,
                    "outcome_path": str(path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "compile-professional-calibration":
        if (
            not args.compact_scope
            or not args.compact_outcome
            or not args.parity_report
        ):
            raise SystemExit(
                "compile_professional_calibration_requires_compact_and_parity"
            )
        scope, path, digest = compile_professional_calibration_scope(
            compact_scope_path=args.compact_scope,
            compact_outcome_path=args.compact_outcome,
            parity_report_path=args.parity_report,
            output_root=args.output_root,
            repository_root=ROOT,
        )
        print(
            json.dumps(
                {
                    "scope": scope.model_dump(mode="json"),
                    "scope_path": str(path),
                    "scope_sha256": digest,
                    "external_model_calls_made": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.action == "execute-professional-calibration":
        if not args.scope or not args.env_path:
            raise SystemExit(
                "execute_professional_calibration_requires_scope_and_env"
            )
        config = tuzi_semantic_config(
            args.env_path, "gemini-3.1-pro-preview", 900
        )
        runner = ProfessionalCalibrationRunnerV1(
            scope_path=args.scope,
            output_root=args.output_root,
            provider_config=config,
        )
        result, path = runner.execute()
        print(
            json.dumps(
                {
                    "result": result.model_dump(mode="json"),
                    "result_path": str(path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    finalizer = CodexLocalScreeningFinalizer(
        campaign_root=args.campaign_root,
        execution_root=args.output_root / "execution",
        provider_config=_deepseek_config(
            args.env_path, args.deepseek_key_path
        ),
    )
    manifest, path = finalizer.finalize()
    print(
        json.dumps(
            {
                "status": manifest.status,
                "manifest_path": str(path),
                "result_path": manifest.result_path,
                "result_sha256": manifest.result_sha256,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
