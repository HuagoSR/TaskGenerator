from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from task_generator.v3_phase16_evidence_to_deliverable_redesign import Phase16CleanEvalGate


def build_phase16_clean_eval_gate(
    output_root: str | Path,
    external_eval_results_path: Optional[str] = None,
    scope_id: str = "two_case",
    case_ids: Optional[List[str]] = None,
):
    """Build Phase 16.7 clean-eval runbook and optional imported-result validation report."""

    return Phase16CleanEvalGate().build(
        Path(output_root),
        external_eval_results_path,
        scope_id=scope_id,
        case_ids=case_ids,
    )
