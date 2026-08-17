from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_codex_e2b_solver import (  # noqa: E402
    CodexE2BRunner, compile_recovery_scope, compile_scope, compile_screening_recovery_scope,
    compile_screening_solver_scope, execute_recovery, execute_screening_recovery,
    execute_screening_solver,
)
from task_generator.v3_skill_extractor import build_tuzi_config, load_env_file  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded Tuzi Codex × E2B compatibility slice.")
    parser.add_argument("--action", choices=("prepare", "execute", "prepare-recovery", "execute-recovery", "prepare-screening-solver", "execute-screening-solver", "prepare-screening-recovery", "execute-screening-recovery"), required=True)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--env-path", type=Path)
    parser.add_argument("--retained-result", type=Path)
    parser.add_argument("--parity-report", type=Path)
    args = parser.parse_args()

    if args.action == "prepare":
        scope, scope_path, receipt_path = compile_scope(args.campaign_root, args.output_root)
        print(json.dumps({
            "scope": scope.model_dump(mode="json"),
            "scope_path": str(scope_path),
            "scope_sha256": scope_path.stem,
            "receipt_path": str(receipt_path),
            "external_calls_made": False,
        }, ensure_ascii=False, indent=2))
        return

    if args.action == "prepare-recovery":
        if not args.retained_result or not args.parity_report:
            raise SystemExit("prepare_recovery_requires_retained_result_and_parity")
        scope, scope_path, receipt_path = compile_recovery_scope(
            campaign_root=args.campaign_root, retained_result_path=args.retained_result,
            parity_report_path=args.parity_report, output_root=args.output_root,
        )
        print(json.dumps({"scope": scope.model_dump(mode="json"), "scope_path": str(scope_path), "scope_sha256": scope_path.stem, "receipt_path": str(receipt_path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "prepare-screening-solver":
        if not args.retained_result or not args.parity_report:
            raise SystemExit("prepare_screening_solver_requires_retained_result_and_parity")
        scope, scope_path, receipt_path = compile_screening_solver_scope(
            campaign_root=args.campaign_root, retained_result_path=args.retained_result,
            parity_report_path=args.parity_report, output_root=args.output_root,
        )
        print(json.dumps({"scope": scope.model_dump(mode="json"), "scope_path": str(scope_path), "scope_sha256": scope_path.stem, "receipt_path": str(receipt_path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "prepare-screening-recovery":
        if not args.retained_result or not args.parity_report:
            raise SystemExit("prepare_screening_recovery_requires_frozen_result_and_parity")
        scope, scope_path, receipt_path = compile_screening_recovery_scope(
            campaign_root=args.campaign_root, frozen_result_path=args.retained_result,
            parity_report_path=args.parity_report, output_root=args.output_root,
        )
        print(json.dumps({"scope": scope.model_dump(mode="json"), "scope_path": str(scope_path), "scope_sha256": scope_path.stem, "receipt_path": str(receipt_path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return

    if not all((args.scope, args.receipt, args.env_path)):
        raise SystemExit("execute_requires_scope_receipt_and_env_path")
    config = build_tuzi_config(args.env_path, "gpt-5.6-sol", 1800)
    if config is None:
        raise SystemExit("tuzi_configuration_missing")
    e2b_api_key = load_env_file(args.env_path).get("E2B_API_KEY")
    if not e2b_api_key:
        raise SystemExit("e2b_configuration_missing")
    if args.action == "execute-screening-recovery":
        if not args.retained_result:
            raise SystemExit("execute_screening_recovery_requires_frozen_result")
        result, result_path = execute_screening_recovery(
            scope_path=args.scope, receipt_path=args.receipt, frozen_result_path=args.retained_result,
            campaign_root=args.campaign_root, output_root=args.output_root / "execution",
            config=config, e2b_api_key=e2b_api_key,
        )
    elif args.action == "execute-screening-solver":
        if not args.retained_result:
            raise SystemExit("execute_screening_solver_requires_retained_result")
        result, result_path = execute_screening_solver(
            scope_path=args.scope, receipt_path=args.receipt, retained_result_path=args.retained_result,
            campaign_root=args.campaign_root, output_root=args.output_root / "execution",
            config=config, e2b_api_key=e2b_api_key,
        )
    elif args.action == "execute-recovery":
        if not args.retained_result:
            raise SystemExit("execute_recovery_requires_retained_result")
        result, result_path = execute_recovery(
            scope_path=args.scope, receipt_path=args.receipt, retained_result_path=args.retained_result,
            campaign_root=args.campaign_root, output_root=args.output_root / "execution",
            config=config, e2b_api_key=e2b_api_key,
        )
    else:
        result, result_path = CodexE2BRunner().execute(
            scope_path=args.scope, receipt_path=args.receipt, campaign_root=args.campaign_root,
            output_root=args.output_root / "execution", config=config, e2b_api_key=e2b_api_key,
        )
    print(json.dumps({"decision": result.decision, "result_path": str(result_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
