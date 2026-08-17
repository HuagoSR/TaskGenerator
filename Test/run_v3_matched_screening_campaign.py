from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_matched_screening import (  # noqa: E402
    MatchedScreeningCampaign,
)
from task_generator.v3_matched_solver_preflight import (  # noqa: E402
    MatchedSolverPreflightGovernance,
)
from task_generator.v3_matched_business_execution import (  # noqa: E402
    MatchedBusinessGovernance,
)
from task_generator.v3_skill_extractor import build_deepseek_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and govern the two-route matched screening cohort.")
    parser.add_argument(
        "--action",
        choices=(
            "prepare", "request-generation", "request-deepseek-preflight",
            "prepare-deepseek-preflight-fixture",
            "receipt-deepseek-preflight", "execute-deepseek-preflight",
            "select-business-solver", "request-business-screening",
            "receipt-business-screening", "execute-business-screening",
        ),
        required=True,
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--campaign-id", default="r6_two_route_matched_screening_v1")
    parser.add_argument("--replicate-a-brief", action="append", type=Path)
    parser.add_argument("--replicate-a-package-map", type=Path)
    parser.add_argument("--replicate-a-campaign-manifest", type=Path)
    parser.add_argument("--source-ledger", type=Path)
    parser.add_argument("--retained-reality-result", type=Path)
    parser.add_argument("--repair-readiness-report", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--maximum-total-cost-usd", type=float, default=24.0)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--authorization-request", type=Path)
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--authorization-statement")
    parser.add_argument("--expires-at")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--real-world-python", type=Path)
    parser.add_argument("--rw-task-root", type=Path)
    parser.add_argument("--preflight-report", type=Path)
    parser.add_argument("--solver-selection", type=Path)
    parser.add_argument("--deepseek-key-path", type=Path)
    args = parser.parse_args()
    campaign = MatchedScreeningCampaign(args.campaign_root)
    if args.action == "prepare":
        required = (
            args.replicate_a_brief,
            args.replicate_a_campaign_manifest,
            args.source_ledger,
            args.retained_reality_result,
            args.repair_readiness_report,
        )
        if any(value is None for value in required):
            raise SystemExit("prepare_requires_all_matched_screening_inputs")
        retained_manifest = json.loads(
            args.replicate_a_campaign_manifest.read_text(encoding="utf-8")
        )
        package_map = (
            json.loads(args.replicate_a_package_map.read_text(encoding="utf-8"))
            if args.replicate_a_package_map is not None
            else {
                brief_id: {
                    route: next(
                        item["package_root"]
                        for item in retained_manifest["assignments"]
                        if item["brief_id"] == brief_id and item["route_id"] == route
                    )
                    for route in ("skill_guided_llm", "llm_led_hybrid")
                }
                for brief_id in {path.stem for path in args.replicate_a_brief}
            }
        )
        result = campaign.prepare(
            campaign_id=args.campaign_id,
            replicate_a_brief_paths=args.replicate_a_brief,
            replicate_a_packages=package_map,
            replicate_a_campaign_manifest_path=args.replicate_a_campaign_manifest,
            source_ledger_path=args.source_ledger,
            retained_reality_result_path=args.retained_reality_result,
            repair_readiness_report_path=args.repair_readiness_report,
            repository_root=ROOT,
        )
        print(result.model_dump_json(indent=2))
        return
    if args.action == "request-deepseek-preflight":
        if args.fixture_root is None or args.parity_report is None:
            raise SystemExit("deepseek_preflight_request_requires_fixture_and_parity")
        request, path, request_sha = campaign.compile_deepseek_preflight_request(
            fixture_root=args.fixture_root, parity_report_path=args.parity_report
        )
        print(json.dumps({"request": request.model_dump(mode="json"), "immutable_request_path": str(path), "request_sha256": request_sha, "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    governance = MatchedSolverPreflightGovernance(args.campaign_root)
    if args.action == "prepare-deepseek-preflight-fixture":
        if args.fixture_root is None:
            raise SystemExit("deepseek_preflight_fixture_root_required")
        path = campaign.prepare_deepseek_preflight_fixture(args.fixture_root)
        print(json.dumps({"fixture_root": str(path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "receipt-deepseek-preflight":
        if not all((args.authorization_request, args.authorization_statement, args.expires_at)):
            raise SystemExit("deepseek_preflight_receipt_requires_request_statement_expiry")
        receipt, path = governance.compile_receipt(
            authorization_request_path=args.authorization_request,
            authorization_statement=args.authorization_statement,
            expires_at=args.expires_at,
        )
        print(json.dumps({"receipt": receipt.model_dump(mode="json"), "receipt_path": str(path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "execute-deepseek-preflight":
        required = (args.authorization_receipt, args.fixture_root, args.output_root, args.real_world_python, args.rw_task_root)
        if any(value is None for value in required):
            raise SystemExit("deepseek_preflight_execution_requires_receipt_fixture_output_runtime")
        report, path = governance.execute(
            receipt_path=args.authorization_receipt,
            fixture_root=args.fixture_root,
            output_root=args.output_root,
            real_world_python=args.real_world_python,
            rw_task_root=args.rw_task_root,
        )
        print(json.dumps({"report": report.model_dump(mode="json"), "report_path": str(path)}, ensure_ascii=False, indent=2))
        return
    business = MatchedBusinessGovernance(args.campaign_root)
    if args.action == "select-business-solver":
        if args.preflight_report is None:
            raise SystemExit("business_solver_selection_requires_preflight_report")
        selection, path = business.compile_solver_selection(args.preflight_report)
        print(json.dumps({"selection": selection.model_dump(mode="json"), "selection_path": str(path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "request-business-screening":
        if args.solver_selection is None or args.parity_report is None:
            raise SystemExit("business_request_requires_selection_and_parity")
        request, path, request_sha = campaign.compile_business_request(
            solver_selection_path=args.solver_selection,
            parity_report_path=args.parity_report,
        )
        print(json.dumps({"request": request.model_dump(mode="json"), "immutable_request_path": str(path), "request_sha256": request_sha, "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "receipt-business-screening":
        if not all((args.authorization_request, args.authorization_statement, args.expires_at)):
            raise SystemExit("business_receipt_requires_request_statement_expiry")
        receipt, path = business.compile_receipt(request_path=args.authorization_request, authorization_statement=args.authorization_statement, expires_at=args.expires_at)
        print(json.dumps({"receipt": receipt.model_dump(mode="json"), "receipt_path": str(path), "external_calls_made": False}, ensure_ascii=False, indent=2))
        return
    if args.action == "execute-business-screening":
        required = (args.authorization_receipt, args.output_root, args.real_world_python, args.rw_task_root, args.deepseek_key_path)
        if any(value is None for value in required):
            raise SystemExit("business_execution_requires_receipt_output_runtime_key")
        config = build_deepseek_config(args.deepseek_key_path, "deepseek-v4-pro", 900)
        if config is None:
            raise SystemExit("deepseek_configuration_missing")
        os.environ["DEEPSEEK_API_KEY"] = config.api_key
        try:
            manifest, path = business.execute(receipt_path=args.authorization_receipt, output_root=args.output_root, real_world_python=args.real_world_python, rw_task_root=args.rw_task_root, provider_config=config)
        finally:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        print(json.dumps({"manifest": manifest.model_dump(mode="json"), "manifest_path": str(path)}, ensure_ascii=False, indent=2))
        return
    if args.parity_report is None:
        raise SystemExit("request_generation_requires_parity_report")
    request, path, request_sha = campaign.compile_generation_request(
        parity_report_path=args.parity_report,
        maximum_total_cost_usd=args.maximum_total_cost_usd,
    )
    print(
        json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "immutable_request_path": str(path),
                "request_sha256": request_sha,
                "external_calls_made": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
