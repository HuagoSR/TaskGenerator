import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (  # noqa: E402
    EvidenceToDeliverableContractV2,
    EvidenceToDeliverableRedesignV2,
)


def main() -> None:
    gap_path = ROOT / "artifacts" / "phase15" / "eval_results" / "phase15_gap_delta_report.json"
    gap = json.loads(gap_path.read_text(encoding="utf-8-sig"))
    contract = EvidenceToDeliverableContractV2().build_contract()
    result = EvidenceToDeliverableRedesignV2().build_tasks(
        contract,
        gap.get("cases") or [],
        ROOT / "artifacts" / "phase16" / "redesign_v2",
    )
    print(
        json.dumps(
            {
                "manifest_path": str(result["manifest_path"]),
                "arm_count": len(result["manifest"].get("arms") or []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
