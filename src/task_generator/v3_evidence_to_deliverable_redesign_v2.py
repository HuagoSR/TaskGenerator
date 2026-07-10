from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (
    EvidenceToDeliverableRedesignV2,
)


def build_redesign_v2_tasks(contract: Dict[str, Any], gap_cases: List[Dict[str, Any]], output_dir: str | Path):
    """Build deterministic Phase 16 redesign_v2 task-package descriptors."""

    return EvidenceToDeliverableRedesignV2().build_tasks(contract, gap_cases, Path(output_dir))
