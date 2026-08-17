from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_authorization import (  # noqa: E402
    BehavioralAuthorizationManager,
    BehavioralPreflightPanelMemberV1,
    BehavioralRetainedPanelEvidenceV1,
)
from task_generator.v3_solver_execution_budget import SolverExecutionBudgetV1  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile or validate exact authorization for tool-only solver "
            "preflight. This runner never calls a provider, solver or grader."
        )
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "request",
            "receipt",
            "check",
            "request-v2",
            "receipt-v2",
            "check-v2",
            "request-v3-replacement",
            "receipt-v3-replacement",
            "check-v3-replacement",
            "request-protocol-probe-v1",
            "receipt-protocol-probe-v1",
            "check-protocol-probe-v1",
        ],
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--panel", type=Path)
    parser.add_argument("--container-parity-report", type=Path)
    parser.add_argument("--maximum-total-cost-usd", type=float, default=6.0)
    parser.add_argument("--timeout-seconds-per-model", type=int, default=900)
    parser.add_argument("--authorization-request", type=Path)
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--authorization-id")
    parser.add_argument("--authorization-statement")
    parser.add_argument("--authorization-expires-at")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--solver-budgets", type=Path)
    parser.add_argument("--pricing-schedule-source")
    parser.add_argument("--retained-evidence", type=Path)
    parser.add_argument("--admission-plan", type=Path)
    parser.add_argument("--replacement-boundary", type=Path)
    parser.add_argument("--retained-frozen-panel", type=Path)
    parser.add_argument("--retained-evidence-integrity", type=Path)
    args = parser.parse_args()
    manager = BehavioralAuthorizationManager(args.campaign_root)
    if args.action in {
        "request", "request-v2", "request-v3-replacement",
        "request-protocol-probe-v1",
    }:
        if not args.panel or not args.container_parity_report:
            parser.error("request requires --panel and --container-parity-report")
        payload = json.loads(args.panel.read_text(encoding="utf-8"))
        members = [
            BehavioralPreflightPanelMemberV1.model_validate(item)
            for item in payload.get("members", [])
        ]
        if args.action in {
            "request-v2", "request-v3-replacement", "request-protocol-probe-v1"
        }:
            if not args.solver_budgets or not args.pricing_schedule_source:
                parser.error("budgeted requests require solver budgets and pricing source")
            budget_payload = json.loads(args.solver_budgets.read_text(encoding="utf-8"))
            budgets = [
                SolverExecutionBudgetV1.model_validate(item)
                for item in budget_payload.get("budgets", [])
            ]
            if args.action == "request-protocol-probe-v1":
                if len(members) != 1 or len(budgets) != 1:
                    parser.error("protocol probe requires one panel member and one budget")
                result = manager.write_agent_protocol_probe_request_v1(
                    panel_member=members[0],
                    solver_execution_budget=budgets[0],
                    pricing_schedule_source=args.pricing_schedule_source,
                    container_parity_report_path=args.container_parity_report,
                    timeout_seconds=args.timeout_seconds_per_model,
                    maximum_total_cost_usd=args.maximum_total_cost_usd,
                )
            elif args.action == "request-v3-replacement":
                required = [
                    args.retained_evidence,
                    args.admission_plan,
                    args.replacement_boundary,
                    args.retained_frozen_panel,
                    args.retained_evidence_integrity,
                ]
                if not all(required):
                    parser.error("replacement request requires retained and admission evidence")
                retained_payload = json.loads(
                    args.retained_evidence.read_text(encoding="utf-8")
                )
                result = manager.write_replacement_request_v3(
                    panel_members=members,
                    retained_evidence=[
                        BehavioralRetainedPanelEvidenceV1.model_validate(item)
                        for item in retained_payload.get("retained_evidence", [])
                    ],
                    solver_execution_budgets=budgets,
                    pricing_schedule_source=args.pricing_schedule_source,
                    admission_plan_path=args.admission_plan,
                    replacement_boundary_path=args.replacement_boundary,
                    retained_frozen_panel_path=args.retained_frozen_panel,
                    retained_evidence_integrity_path=args.retained_evidence_integrity,
                    container_parity_report_path=args.container_parity_report,
                    timeout_seconds_per_model=args.timeout_seconds_per_model,
                    maximum_total_cost_usd=args.maximum_total_cost_usd,
                )
            else:
                result = manager.write_preflight_request_v2(
                    panel_members=members,
                    solver_execution_budgets=budgets,
                    pricing_schedule_source=args.pricing_schedule_source,
                    container_parity_report_path=args.container_parity_report,
                    timeout_seconds_per_model=args.timeout_seconds_per_model,
                    maximum_total_cost_usd=args.maximum_total_cost_usd,
                )
        else:
            result = manager.write_preflight_request(
                panel_members=members,
                container_parity_report_path=args.container_parity_report,
                timeout_seconds_per_model=args.timeout_seconds_per_model,
                maximum_total_cost_usd=args.maximum_total_cost_usd,
            )
    elif args.action in {
        "receipt", "receipt-v2", "receipt-v3-replacement",
        "receipt-protocol-probe-v1",
    }:
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
                "receipt requires request, id, statement, expiry and output"
            )
        method = {
            "receipt": manager.compile_receipt,
            "receipt-v2": manager.compile_receipt_v2,
            "receipt-v3-replacement": manager.compile_replacement_receipt_v3,
            "receipt-protocol-probe-v1": manager.compile_agent_protocol_probe_receipt_v1,
        }[args.action]
        result = method(
                authorization_request_path=args.authorization_request,
                authorization_id=args.authorization_id,
                authorization_statement=args.authorization_statement,
                expires_at=args.authorization_expires_at,
                output_path=args.output,
            )
    elif args.action == "check-v2":
        result = manager.check_v2(args.authorization_receipt)
    elif args.action == "check-v3-replacement":
        result = manager.check_replacement_v3(args.authorization_receipt)
    elif args.action == "check-protocol-probe-v1":
        result = manager.check_agent_protocol_probe_v1(args.authorization_receipt)
    else:
        result = manager.check(args.authorization_receipt)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
