from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_codex_local_grader import (  # noqa: E402
    CodexLocalGraderRunnerV1,
    compile_candidate_data_admission_manifest,
    compile_codex_local_grader_scope,
    compile_route_convergence_report,
)
from task_generator.v3_codex_local_solver import (  # noqa: E402
    CodexLocalTooling,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Grade the frozen representative deliveries with route-blind "
            "local Codex structured output."
        )
    )
    parser.add_argument(
        "--action",
        choices=(
            "compile-scope",
            "execute",
            "compile-convergence",
            "compile-data-admission",
        ),
        required=True,
    )
    parser.add_argument("--upstream-compact-scope", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--tooling-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--grader-outcome", type=Path)
    parser.add_argument("--grader-manifest", type=Path)
    parser.add_argument("--representative-campaign", type=Path)
    parser.add_argument("--route-convergence-report", type=Path)
    parser.add_argument(
        "--codex-home", type=Path, default=Path.home() / ".codex"
    )
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=Path(sys.executable),
    )
    args = parser.parse_args()

    if args.action == "compile-data-admission":
        if not (
            args.grader_outcome
            and args.grader_manifest
            and args.representative_campaign
            and args.route_convergence_report
        ):
            raise SystemExit(
                "compile_data_admission_requires_complete_evidence"
            )
        manifest, path = compile_candidate_data_admission_manifest(
            grader_outcome_path=args.grader_outcome,
            grader_manifest_path=args.grader_manifest,
            representative_campaign_path=args.representative_campaign,
            route_convergence_report_path=args.route_convergence_report,
            output_path=args.output_root
            / "candidate_data_admission_manifest.json",
        )
        print(
            json.dumps(
                {
                    "admitted_record_count": (
                        manifest.admitted_record_count
                    ),
                    "production_candidate_record_count": (
                        manifest.production_candidate_record_count
                    ),
                    "challenger_control_record_count": (
                        manifest.challenger_control_record_count
                    ),
                    "manifest_path": str(path),
                    "training_started": manifest.training_started,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.action == "compile-convergence":
        if not (
            args.grader_outcome
            and args.grader_manifest
            and args.representative_campaign
        ):
            raise SystemExit(
                "compile_convergence_requires_outcome_manifest_campaign"
            )
        report, path = compile_route_convergence_report(
            grader_outcome_path=args.grader_outcome,
            grader_manifest_path=args.grader_manifest,
            representative_campaign_path=args.representative_campaign,
            output_path=args.output_root / "route_convergence_report.json",
        )
        print(
            json.dumps(
                {
                    "recommendation": report.recommendation,
                    "challenger": report.challenger,
                    "score_mean_gap": report.score_mean_gap,
                    "report_path": str(path),
                    "training_authorized": report.training_authorized,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.action == "compile-scope":
        if not args.upstream_compact_scope or not args.parity_report:
            raise SystemExit(
                "compile_scope_requires_upstream_and_parity"
            )
        scope, path, digest = compile_codex_local_grader_scope(
            upstream_compact_scope_path=args.upstream_compact_scope,
            parity_report_path=args.parity_report,
            cli_identity=CodexLocalTooling(
                args.tooling_root
            ).freeze_identity(),
            repository_root=ROOT,
            output_root=args.output_root,
        )
        print(
            json.dumps(
                {
                    "scope_path": str(path),
                    "scope_sha256": digest,
                    "task_count": len(scope.bindings),
                    "evidence_kind": scope.evidence_kind,
                    "external_provider_calls": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not args.scope:
        raise SystemExit("execute_requires_scope")
    outcome, path = CodexLocalGraderRunnerV1(
        scope_path=args.scope,
        output_root=args.output_root,
        codex_home=args.codex_home,
        python_executable=args.python_executable,
    ).execute()
    print(
        json.dumps(
            {
                "completed_grades": outcome.completed_grades,
                "infrastructure_failed_grades": (
                    outcome.infrastructure_failed_grades
                ),
                "grading_failed_grades": outcome.grading_failed_grades,
                "decision": outcome.screening_result.decision,
                "score_distribution": outcome.score_distribution,
                "outcome_path": str(path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
