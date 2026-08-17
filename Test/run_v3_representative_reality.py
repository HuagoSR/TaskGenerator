from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_representative_reality import (
    RepresentativeRealityCampaign,
)
from task_generator.v3_semantic_review_executor import deepseek_semantic_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile or execute the 24-package representative Reality cohort."
    )
    parser.add_argument("--action", required=True, choices=["scope", "execute"])
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--package-readiness", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--deepseek-key",
        type=Path,
        default=ROOT / "deepseek-key.txt",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    campaign = RepresentativeRealityCampaign(args.campaign_root)
    if args.action == "scope":
        if not args.package_readiness or not args.parity_report:
            parser.error(
                "scope requires --package-readiness and --parity-report"
            )
        result = campaign.compile_scope(
            package_readiness_path=args.package_readiness,
            parity_report_path=args.parity_report,
            repository_root=ROOT,
        )
    else:
        if not args.output:
            parser.error("execute requires --output")
        config = deepseek_semantic_config(
            args.deepseek_key, args.timeout_seconds
        )
        result = campaign.execute(
            provider_config=config,
            output_root=args.output,
            repository_root=ROOT,
        )
    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.action == "execute" and result.status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
