from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from task_generator.v3_official_deepseek_opencode import (  # noqa: E402
    OfficialDeepSeekOpenCodeRunner,
    aggregate_official_opencode_comparison,
    audit_official_opencode_execution,
    compile_official_opencode_scope,
    grade_official_opencode_deliveries,
)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]
        values[name.strip()] = value
    return values


def _keys(args) -> tuple[str, str]:
    env_values = _read_env(Path(args.env_file).resolve())
    e2b = env_values.get("E2B_API_KEY") or os.environ.get("E2B_API_KEY", "")
    deepseek_path = Path(args.deepseek_key_file).resolve()
    deepseek = (
        deepseek_path.read_text(encoding="utf-8-sig").strip()
        if deepseek_path.is_file()
        else os.environ.get("DEEPSEEK_API_KEY", "")
    )
    return deepseek, e2b


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--representative-campaign", required=True)
    compile_parser.add_argument("--baseline-solver-manifest", required=True)
    compile_parser.add_argument("--baseline-grader-outcome", required=True)
    compile_parser.add_argument("--parity-report", required=True)
    compile_parser.add_argument("--output-root", required=True)

    execute = sub.add_parser("execute")
    execute.add_argument("--scope", required=True)
    execute.add_argument("--receipt", required=True)
    execute.add_argument("--output-root", required=True)
    execute.add_argument(
        "--env-file",
        default=str(REPOSITORY_ROOT.parent / "rw-task" / ".env"),
    )
    execute.add_argument(
        "--deepseek-key-file",
        default=str(REPOSITORY_ROOT / "deepseek-key.txt"),
    )

    grade = sub.add_parser("grade")
    grade.add_argument("--scope", required=True)
    grade.add_argument("--execution", required=True)
    grade.add_argument("--output-root", required=True)
    grade.add_argument("--codex-home", required=True)
    grade.add_argument(
        "--python",
        default=r"D:\miniconda3\envs\taskgenerator\python.exe",
    )

    audit = sub.add_parser("audit")
    audit.add_argument("--scope", required=True)
    audit.add_argument("--execution", required=True)
    audit.add_argument("--output", required=True)

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--scope", required=True)
    aggregate.add_argument("--execution", required=True)
    aggregate.add_argument("--grader", required=True)
    aggregate.add_argument("--audit")
    aggregate.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.action == "compile":
        scope, scope_path, receipt_path = compile_official_opencode_scope(
            representative_campaign_path=args.representative_campaign,
            baseline_solver_manifest_path=args.baseline_solver_manifest,
            baseline_grader_outcome_path=args.baseline_grader_outcome,
            parity_report_path=args.parity_report,
            repository_root=REPOSITORY_ROOT,
            output_root=args.output_root,
        )
        print(scope_path)
        print(receipt_path)
        print(scope.campaign_id)
        return 0
    if args.action == "execute":
        deepseek, e2b = _keys(args)
        runner = OfficialDeepSeekOpenCodeRunner(
            scope_path=args.scope,
            receipt_path=args.receipt,
            output_root=args.output_root,
            repository_root=REPOSITORY_ROOT,
            deepseek_key=deepseek,
            e2b_key=e2b,
        )
        manifest, path = runner.execute()
        print(path)
        print(manifest.status)
        return 0
    if args.action == "grade":
        manifest, path = grade_official_opencode_deliveries(
            scope_path=args.scope,
            execution_path=args.execution,
            output_root=args.output_root,
            codex_home=args.codex_home,
            python_executable=args.python,
        )
        print(path)
        print(manifest.status)
        return 0
    if args.action == "audit":
        audit, path = audit_official_opencode_execution(
            scope_path=args.scope,
            execution_path=args.execution,
            output_path=args.output,
        )
        print(path)
        print(audit.audited_execution_status)
        print(audit.post_freeze_attempt_count)
        return 0
    result, path = aggregate_official_opencode_comparison(
        scope_path=args.scope,
        execution_path=args.execution,
        grader_path=args.grader,
        output_path=args.output,
        execution_audit_path=args.audit,
    )
    print(path)
    print(result.decision)
    print(result.practical_winner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
