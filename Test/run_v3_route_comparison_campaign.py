from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_route_comparison_campaign import (  # noqa: E402
    RouteComparisonCampaign,
)
from task_generator.v3_skill_extractor import build_tuzi_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare and govern the R6 matched route-comparison campaign. "
            "Prepare, strict-materialize and authorization-free preflight make "
            "no external model calls."
        )
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "prepare",
            "strict-materialize",
            "preflight",
            "authorization-request",
            "authorization-receipt",
            "provider-generate",
            "provider-screening-outcome",
            "blind-stage",
            "evidence-analyze",
            "evidence-template",
            "evidence-freeze",
            "status",
        ],
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--comparison-id")
    parser.add_argument("--brief", type=Path, action="append", default=[])
    parser.add_argument("--source-snapshot", type=Path)
    parser.add_argument("--brief-admission-report", type=Path)
    parser.add_argument("--repair-readiness-report", type=Path)
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Prepare a fixture dry-run that is not eligible for formal provider execution.",
    )
    parser.add_argument(
        "--environment-contract-id",
        default="fixed-linux-amd64-network-governed-v1",
    )
    parser.add_argument(
        "--solver-preflight-contract-path",
        default="governance/frozen_solver_panel.json",
    )
    parser.add_argument(
        "--grader-calibration-contract-path",
        default="governance/evaluation_calibration_contract.json",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument(
        "--maximum-provider-cost-usd",
        type=float,
        default=100.0,
    )
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--authorization-request", type=Path)
    parser.add_argument("--authorization-id")
    parser.add_argument("--authorization-statement")
    parser.add_argument("--authorization-expires-at")
    parser.add_argument("--authorization-brief-id")
    parser.add_argument("--evidence-input", type=Path)
    parser.add_argument("--solver-panel", type=Path)
    parser.add_argument("--grader-observations", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-path", type=Path)
    parser.add_argument(
        "--blind-task-id",
        action="append",
        default=[],
        help="Limit provider generation to selected route-blind assignments.",
    )
    parser.add_argument(
        "--maximum-assignments",
        type=int,
        default=None,
        help="Bound the number of provider assignments processed in this invocation.",
    )
    args = parser.parse_args()
    campaign = RouteComparisonCampaign(args.campaign_root)
    if args.action == "prepare":
        if not args.comparison_id:
            parser.error("prepare requires --comparison-id")
        if len(args.brief) != 4:
            parser.error("prepare requires exactly four --brief arguments")
        if not args.source_snapshot:
            parser.error("prepare requires --source-snapshot")
        if not args.contract_only and not args.brief_admission_report:
            parser.error(
                "formal prepare requires --brief-admission-report; "
                "use --contract-only only for fixture dry-runs"
            )
        if not args.contract_only and not args.repair_readiness_report:
            parser.error(
                "formal prepare requires --repair-readiness-report"
            )
        result = campaign.prepare(
            comparison_id=args.comparison_id,
            brief_paths=args.brief,
            source_snapshot_path=args.source_snapshot,
            environment_contract_id=args.environment_contract_id,
            solver_preflight_contract_path=(
                args.solver_preflight_contract_path
            ),
            grader_calibration_contract_path=(
                args.grader_calibration_contract_path
            ),
            timeout_seconds=args.timeout_seconds,
            maximum_provider_cost_usd=args.maximum_provider_cost_usd,
            input_class=(
                "contract_only"
                if args.contract_only
                else "formal_public_source"
            ),
            brief_admission_report_path=args.brief_admission_report,
            repair_readiness_report_path=args.repair_readiness_report,
        ).model_dump(mode="json")
    elif args.action == "strict-materialize":
        result = campaign.materialize_strict_template_controls().model_dump(
            mode="json"
        )
    elif args.action == "preflight":
        result = campaign.preflight(
            args.authorization_receipt
        ).model_dump(mode="json")
    elif args.action == "authorization-request":
        if not args.authorization_brief_id:
            parser.error(
                "authorization-request requires --authorization-brief-id"
            )
        result = campaign.write_provider_smoke_authorization_request(
            brief_id=args.authorization_brief_id,
            maximum_provider_cost_usd=args.maximum_provider_cost_usd,
        ).model_dump(mode="json")
    elif args.action == "authorization-receipt":
        if not all(
            [
                args.authorization_request,
                args.authorization_id,
                args.authorization_statement,
                args.authorization_expires_at,
                args.output,
            ]
        ):
            parser.error(
                "authorization-receipt requires --authorization-request, "
                "--authorization-id, --authorization-statement, "
                "--authorization-expires-at and --output"
            )
        result = campaign.compile_authorization_receipt(
            authorization_request_path=args.authorization_request,
            authorization_id=args.authorization_id,
            authorization_statement=args.authorization_statement,
            expires_at=args.authorization_expires_at,
            output_path=args.output,
        ).model_dump(mode="json")
    elif args.action == "provider-generate":
        if not args.authorization_receipt:
            parser.error(
                "provider-generate requires --authorization-receipt"
            )
        if not args.env_path:
            parser.error("provider-generate requires --env-path")
        preflight = campaign.preflight(args.authorization_receipt)
        if preflight.execution_decision != "ready":
            raise RuntimeError("campaign_execution_preflight_not_ready")
        config = build_tuzi_config(args.env_path, "gpt-5.6-sol", 900)
        if config is None:
            raise RuntimeError("campaign_provider_config_unavailable")
        result = campaign.generate_provider_routes(
            config=config,
            blind_task_ids=args.blind_task_id or None,
            maximum_assignments=args.maximum_assignments,
        ).model_dump(mode="json")
    elif args.action == "provider-screening-outcome":
        result = campaign.write_provider_screening_outcome().model_dump(
            mode="json"
        )
    elif args.action == "blind-stage":
        result = campaign.stage_route_blind_packages().model_dump(
            mode="json"
        )
    elif args.action == "evidence-analyze":
        if not args.evidence_input:
            parser.error("evidence-analyze requires --evidence-input")
        result = campaign.compile_and_analyze_evidence(
            args.evidence_input
        ).model_dump(mode="json")
    elif args.action == "evidence-template":
        if not all(
            [
                args.solver_panel,
                args.grader_observations,
                args.output,
            ]
        ):
            parser.error(
                "evidence-template requires --solver-panel, "
                "--grader-observations and --output"
            )
        result = campaign.write_evidence_input_template(
            frozen_solver_panel_path=args.solver_panel,
            grader_observations_path=args.grader_observations,
            output_path=args.output,
        ).model_dump(mode="json")
    elif args.action == "evidence-freeze":
        if not args.evidence_input or not args.output:
            parser.error(
                "evidence-freeze requires --evidence-input and --output"
            )
        result = campaign.freeze_evidence_input(
            template_path=args.evidence_input,
            output_path=args.output,
        ).model_dump(mode="json")
    else:
        result = campaign.read().model_dump(mode="json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
