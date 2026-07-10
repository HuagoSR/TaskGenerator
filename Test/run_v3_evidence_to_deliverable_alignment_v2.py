import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (  # noqa: E402
    EvidenceToDeliverableAlignmentV2,
    EvidenceToDeliverableContractV2,
)


def main() -> None:
    contract = EvidenceToDeliverableContractV2().build_contract()
    paths = EvidenceToDeliverableAlignmentV2().build_reports(contract, ROOT / "artifacts" / "phase16" / "alignment")
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
