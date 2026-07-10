from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (
    EvidenceToDeliverableAlignmentV2,
)


def build_alignment_v2_reports(contract: Dict[str, Any], output_dir: str | Path):
    """Build Contract V2 GoldenRun, rubric, and verifier alignment reports."""

    return EvidenceToDeliverableAlignmentV2().build_reports(contract, Path(output_dir))
