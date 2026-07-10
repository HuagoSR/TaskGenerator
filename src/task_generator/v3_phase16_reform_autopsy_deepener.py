from __future__ import annotations

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (
    Phase16EvidenceToDeliverableRedesignBuilder,
    Phase16RedesignRequest,
)


def build_phase16_reform_deep_autopsy(request: Phase16RedesignRequest):
    """Build Phase 16 autopsy artifacts through the Phase 16 report-first workflow."""

    return Phase16EvidenceToDeliverableRedesignBuilder().build(request)
