from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_hybrid_task_materializer import HybridTaskMaterializer
from task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignProposalV1,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize one frozen CapabilityBrief/TaskDesignProposal pair "
            "without provider, solver, grader, registry, or release effects."
        )
    )
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    brief = CapabilityBriefV1.model_validate_json(
        args.brief.read_text(encoding="utf-8")
    )
    proposal = TaskDesignProposalV1.model_validate_json(
        args.proposal.read_text(encoding="utf-8")
    )
    report = HybridTaskMaterializer().materialize(
        brief,
        proposal,
        args.output_root,
    )
    print(report.model_dump_json(indent=2))
    return 0 if report.decision == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
