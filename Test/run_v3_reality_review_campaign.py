from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_reality_review_campaign import RealityReviewCampaign
from task_generator.v3_semantic_review_executor import deepseek_semantic_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Governed six-case LLM reality review campaign.")
    parser.add_argument(
        "--action",
        required=True,
        choices=["request", "request-continuation", "receipt", "execute"],
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--authorization-id")
    parser.add_argument("--authorization-statement")
    parser.add_argument("--expires-at")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prior-manifest", type=Path)
    args = parser.parse_args()
    campaign = RealityReviewCampaign(args.campaign_root)
    if args.action in {"request", "request-continuation"}:
        if not args.selection or not args.parity_report:
            parser.error("request requires --selection and --parity-report")
        if args.action == "request-continuation":
            if not args.prior_manifest:
                parser.error("request-continuation requires --prior-manifest")
            result = campaign.compile_continuation_request(
                selection_path=args.selection,
                parity_path=args.parity_report,
                prior_manifest_path=args.prior_manifest,
            )
        else:
            result = campaign.compile_request(
                selection_path=args.selection, parity_path=args.parity_report
            )
    elif args.action == "receipt":
        if not all([args.request, args.authorization_id, args.authorization_statement, args.expires_at, args.output]):
            parser.error("receipt requires request, authorization fields and output")
        result = campaign.compile_receipt(
            request_path=args.request,
            authorization_id=args.authorization_id,
            authorization_statement=args.authorization_statement,
            expires_at=args.expires_at,
            output_path=args.output,
        )
    else:
        if not args.receipt or not args.output:
            parser.error("execute requires --receipt and --output")
        config = deepseek_semantic_config(ROOT / "deepseek-key.txt", 600)
        result = campaign.execute(receipt_path=args.receipt, provider_config=config, output_root=args.output)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if args.action == "execute" and result.status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
