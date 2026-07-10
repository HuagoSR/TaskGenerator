import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (  # noqa: E402
    Phase16EvidenceToDeliverableRedesignBuilder,
    Phase16RedesignRequest,
)


def main() -> None:
    report = Phase16EvidenceToDeliverableRedesignBuilder().build(Phase16RedesignRequest())
    print(
        json.dumps(
            {
                "deep_autopsy": report.outputs.get("deep_autopsy"),
                "case_delta_report": report.outputs.get("case_delta_report"),
                "phase16_decision": report.phase16_decision,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
