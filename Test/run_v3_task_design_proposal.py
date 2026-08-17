from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_skill_extractor import build_tuzi_config  # noqa: E402
from task_generator.v3_task_design_executor import (  # noqa: E402
    TaskDesignExecutionRequestV1,
    TaskDesignProposalExecutor,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one governed, proposal-only TaskDesignProposal request."
    )
    parser.add_argument("--capability-brief", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-path", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument(
        "--route-id",
        choices=["skill_guided_llm", "llm_led_hybrid"],
        default="llm_led_hybrid",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--input-token-hard-limit", type=int, default=30000)
    parser.add_argument("--allow-external-provider", action="store_true")
    parser.add_argument("--allow-expensive-model", action="store_true")
    parser.add_argument("--overwrite-completed", action="store_true")
    args = parser.parse_args()

    if not args.allow_external_provider:
        parser.error(
            "External proposal execution requires --allow-external-provider and "
            "campaign-scoped user authorization."
        )
    config = build_tuzi_config(
        args.env_path,
        args.model,
        args.timeout_seconds,
    )
    if config is None:
        parser.error("No compatible provider configuration was found.")
    request = TaskDesignExecutionRequestV1(
        capability_brief_path=str(args.capability_brief),
        output_dir=str(args.output_dir),
        route_id=args.route_id,
        model=args.model,
        allow_external_provider=True,
        allow_expensive_model=args.allow_expensive_model,
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
        input_token_hard_limit=args.input_token_hard_limit,
        overwrite_completed=args.overwrite_completed,
    )
    report = TaskDesignProposalExecutor().run(request, config)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
