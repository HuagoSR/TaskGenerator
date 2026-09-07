import pytest

from task_generator.evaluation.stirrup_calibration import StirrupSolverAttemptV1
from task_generator.evaluation.stirrup_supplement import (
    SUPPLEMENT_MODELS,
    StrictGradePacketV1,
    StirrupSupplementProtocolProbeV1,
    StirrupSupplementSolverReceiptV1,
    TerraTransportDiagnosticReceiptV1,
    classify_supplement_result,
    freeze_supplement_panel,
)


HASH = "a" * 64


def _probe(slot, status="passed"):
    passed = status == "passed"
    return StirrupSupplementProtocolProbeV1(
        slot=slot,
        requested_model=SUPPLEMENT_MODELS[slot],
        status=status,
        attempt_count=1,
        completed_model_requests=2 if passed else 1,
        code_exec_observed=passed,
        finish_observed=passed,
        tool_result_roundtrip_observed=passed,
        delivery_valid=passed,
        evidence_path=f"preflight/{slot}",
    )


def test_four_route_panel_requires_every_protocol_probe():
    panel = freeze_supplement_panel([_probe(slot) for slot in SUPPLEMENT_MODELS])
    assert panel.models == SUPPLEMENT_MODELS
    with pytest.raises(ValueError, match="protocol_gate_failed"):
        freeze_supplement_panel([
            _probe(slot, "protocol_or_semantic_failure" if slot == "cross_family" else "passed")
            for slot in SUPPLEMENT_MODELS
        ])


def test_probe_requires_two_request_tool_roundtrip():
    with pytest.raises(ValueError, match="probe_status_evidence_conflict"):
        StirrupSupplementProtocolProbeV1(
            slot="strong_primary", requested_model="gpt-5.5", status="passed",
            attempt_count=1, completed_model_requests=1, code_exec_observed=True,
            finish_observed=True, tool_result_roundtrip_observed=False,
            delivery_valid=True, evidence_path="preflight/strong_primary",
        )


def test_supplement_receipt_rejects_model_alias_and_invalid_hash_pair():
    attempt = StirrupSolverAttemptV1(
        attempt_number=1, state="succeeded", semantic_phase_started=True,
        evidence_path="solver/attempt_1",
    )
    with pytest.raises(ValueError, match="unregistered_solver_model"):
        StirrupSupplementSolverReceiptV1(
            task_id="task", solver_id="gpt-5-mini", slot="lower_anchor",
            input_sha256=HASH, rubric_sha256=HASH, delivery_status="complete",
            delivery_sha256=HASH, attempts=[attempt],
        )
    valid = StirrupSupplementSolverReceiptV1(
        task_id="task", solver_id="gpt-5.4-mini", slot="lower_anchor",
        input_sha256=HASH, rubric_sha256=HASH, delivery_status="complete",
        delivery_sha256=HASH, attempts=[attempt],
    )
    assert valid.context_window_tokens == 64000
    assert valid.max_completion_tokens == 8192
    assert valid.completed_model_requests == 0


def test_result_classification_support_ceiling_mixed_and_incomplete():
    supported_means = {
        "gpt-5.5": .90, "gpt-5.6-sol": .86, "glm-5.2": .78, "gpt-5.4-mini": .70,
    }
    supported_tasks = {
        f"t{i}": {"gpt-5.5": .90, "gpt-5.6-sol": .86, "glm-5.2": .78, "gpt-5.4-mini": .70}
        for i in range(3)
    }
    common = dict(all_deliveries_valid=True, primary_structural_valid=True, sentinel_acceptance=True)
    assert classify_supplement_result(
        **common, means=supported_means, task_scores=supported_tasks,
        professional_item_gap_present=True,
    ) == "strong_anchor_separation_supported"
    ceiling_means = {model: .90 + i * .01 for i, model in enumerate(SUPPLEMENT_MODELS.values())}
    ceiling_tasks = {f"t{i}": dict(ceiling_means) for i in range(3)}
    assert classify_supplement_result(
        **common, means=ceiling_means, task_scores=ceiling_tasks,
        professional_item_gap_present=False,
    ) == "tasks_likely_ceiling_limited"
    assert classify_supplement_result(
        **common, means=supported_means | {"gpt-5.5": .79}, task_scores=supported_tasks,
        professional_item_gap_present=True,
    ) == "mixed_inconclusive"
    assert classify_supplement_result(
        all_deliveries_valid=False, primary_structural_valid=True, sentinel_acceptance=True,
        means=supported_means, task_scores=supported_tasks, professional_item_gap_present=True,
    ) == "incomplete"


def test_terra_transport_receipt_requires_output_only_on_pass():
    with pytest.raises(ValueError, match="output_status_conflict"):
        TerraTransportDiagnosticReceiptV1(
            transport="server_tuzi_chat", request_started=True, status="passed",
            environment_sha256=HASH, input_sha256=HASH, evidence_path="paths/server",
        )


def test_strict_grade_packet_is_self_contained():
    packet = StrictGradePacketV1(
        task_id="probe", strict_system="strict", rubric_items=[{"rubric_item_id": "one"}],
        required_evidence_path_roots=["anonymous_submission/"], materials="OK", output_schema={"type": "object"},
    )
    assert packet.packet_version == "r10.strict_grade_packet.1"
