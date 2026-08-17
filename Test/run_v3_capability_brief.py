from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_domain_profile import load_domain_profile  # noqa: E402
from task_generator.v3_pipeline_b_sampler import PipelineBSubgraph  # noqa: E402
from task_generator.v3_task_design_frontend import TaskDesignFrontend  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile a deterministic CapabilityBrief from a Pipeline B subgraph."
    )
    parser.add_argument("--subgraph-report", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--domain-profile", default="finance_audit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    subgraph = PipelineBSubgraph.model_validate_json(
        args.subgraph_report.read_text(encoding="utf-8")
    )
    brief = TaskDesignFrontend().build_capability_brief(
        case_id=args.case_id,
        subgraph=subgraph,
        domain_profile=load_domain_profile(args.domain_profile),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "brief_id": brief.brief_id,
                "motif": brief.motif,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
