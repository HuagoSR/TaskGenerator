from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_task_design_executor import (  # noqa: E402
    TaskDesignProposalExecutor,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile an offline, no-provider readiness report proving that "
            "preserved failed proposal attempts produce feedback-conditioned "
            "repair prompts."
        )
    )
    parser.add_argument(
        "--failed-execution-report",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--portable-bundle-dir",
        type=Path,
        help=(
            "Freeze all replay dependencies into a self-contained bundle; "
            "required for formal campaign admission."
        ),
    )
    args = parser.parse_args()
    report = TaskDesignProposalExecutor().compile_repair_readiness(
        args.failed_execution_report,
        args.output,
        portable_bundle_dir=args.portable_bundle_dir,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if report.decision != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
