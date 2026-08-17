from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from task_generator.v3_task_design_executor import TaskDesignProposalExecutor


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Revalidate a persisted strict V2 task-design proposal without "
            "calling an external provider."
        )
    )
    parser.add_argument("--capability-brief", required=True)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--route-id",
        required=True,
        choices=["skill_guided_llm", "llm_led_hybrid"],
    )
    args = parser.parse_args()
    report = TaskDesignProposalExecutor().replay_persisted_proposal(
        capability_brief_path=args.capability_brief,
        proposal_path=args.proposal,
        output_dir=args.output_dir,
        route_id=args.route_id,
    )
    print(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
