from __future__ import annotations

import json
import copy
import unittest
from pathlib import Path

from src.task_generator.v3_task_design_frontend import CapabilityBriefV1
from src.task_generator.v3_task_design_normalizer import (
    TaskDesignProposalNormalizer,
    TaskDesignSemanticProposalV1,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
)


def _semantic_payload() -> dict:
    payload = json.loads(
        (FIXTURE_ROOT / "valid_proposal.json").read_text(encoding="utf-8")
    )
    payload.pop("proposal_version", None)
    payload.pop("proposal_origin", None)
    payload.pop("authority", None)
    payload["semantic_proposal_version"] = (
        "v3.task_design_semantic_proposal.1"
    )
    for node_index, node in enumerate(payload["evidence_nodes"], start=1):
        node.pop("candidate_visible", None)
        node["artifact_spec"] = {
            "fact_origin": "governed_scenario_fact",
            "record_type": node["artifact_role"],
            "primary_key_field": "record_id",
            "fields": [
                {
                    "field_name": "record_id",
                    "display_name": "Record ID",
                    "data_type": "identifier",
                    "description": "Stable candidate-visible record identifier.",
                },
                {
                    "field_name": "case_id",
                    "display_name": "Case ID",
                    "data_type": "identifier",
                    "description": "Shared key for cross-file analysis.",
                },
                {
                    "field_name": "business_period",
                    "display_name": "Business Period",
                    "data_type": "text",
                    "description": "Applicable business reporting period.",
                },
                {
                    "field_name": "record_status",
                    "display_name": "Record Status",
                    "data_type": "enum",
                    "description": "Candidate-visible business record status.",
                },
            ],
            "records": [
                {
                    "record_id": f"N{node_index}-REC-{record_index:03d}",
                    "case_id": f"CASE-{record_index:03d}",
                    "business_period": "2026-Q1",
                    "record_status": (
                        "Pending assessment"
                        if record_index == 3
                        else "Complete"
                    ),
                }
                for record_index in range(1, 4)
            ],
            "methodological_source_ref_ids": node["source_ref_ids"],
        }
    for relation in payload["evidence_relations"]:
        relation["from_join_field"] = "case_id"
        relation["to_join_field"] = "case_id"
        relation["comparison_fields"] = []
    return payload


class LossInjectingNormalizer(TaskDesignProposalNormalizer):
    @staticmethod
    def _normalized_projection(proposal):
        projection = TaskDesignProposalNormalizer._normalized_projection(
            proposal
        )
        projection["productive_complexity"] = []
        return projection


class TaskDesignNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = CapabilityBriefV1.model_validate_json(
            (FIXTURE_ROOT / "capability_brief.json").read_text(
                encoding="utf-8"
            )
        )

    def test_semantic_payload_normalizes_without_fact_or_complexity_loss(
        self,
    ) -> None:
        payload = _semantic_payload()
        proposal, report = TaskDesignProposalNormalizer().normalize_payload(
            payload,
            self.brief,
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(report.decision, "pass")
        self.assertEqual(report.facts_added, 0)
        self.assertEqual(report.facts_removed, 0)
        self.assertFalse(report.semantic_loss_detected)
        self.assertTrue(report.productive_complexity_preserved)
        self.assertEqual(
            report.provider_semantics_source_sha256,
            report.provider_semantics_normalized_sha256,
        )
        self.assertTrue(report.authority_boundary_stamped_by_program)
        self.assertFalse(report.materialization_authorized)
        self.assertFalse(report.registry_mutation_authorized)
        self.assertFalse(report.promotion_authorized)
        assert proposal is not None
        self.assertEqual(proposal.proposal_version, "v3.task_design_proposal.2")
        self.assertEqual(proposal.proposal_origin, "llm")
        self.assertTrue(all(node.candidate_visible for node in proposal.evidence_nodes))
        self.assertFalse(proposal.authority.may_define_truth)
        self.assertFalse(proposal.authority.may_define_submission_path)
        self.assertFalse(proposal.authority.may_mutate_registry)
        self.assertFalse(proposal.authority.may_promote_release)
        self.assertFalse(proposal.authority.may_define_final_rubric)
        source_records = [
            record
            for node in payload["evidence_nodes"]
            for record in node["artifact_spec"]["records"]
        ]
        normalized_records = [
            record.values
            for node in proposal.evidence_nodes
            if node.artifact_spec is not None
            for record in node.artifact_spec.records
        ]
        self.assertEqual(source_records, normalized_records)

    def test_missing_primary_key_value_blocks_without_synthetic_repair(
        self,
    ) -> None:
        payload = _semantic_payload()
        payload["evidence_nodes"][0]["artifact_spec"]["records"][0].pop(
            "record_id"
        )
        proposal, report = TaskDesignProposalNormalizer().normalize_payload(
            payload,
            self.brief,
        )
        self.assertIsNone(proposal)
        self.assertEqual(report.decision, "blocked")
        self.assertIn(
            "missing_semantic_record_field:node_primary:0",
            report.blocking_reasons,
        )
        self.assertIn(
            "missing_semantic_primary_key_value:node_primary:0",
            report.blocking_reasons,
        )
        self.assertEqual(report.facts_added, 0)

    def test_semantic_schema_requires_complete_relation_join_contract(
        self,
    ) -> None:
        relation_schema = TaskDesignSemanticProposalV1.model_json_schema()[
            "$defs"
        ]["SemanticEvidenceRelationV1"]
        self.assertIn("from_join_field", relation_schema["required"])
        self.assertIn("to_join_field", relation_schema["required"])

        payload = _semantic_payload()
        payload["evidence_relations"][0].pop("from_join_field")
        proposal, report = TaskDesignProposalNormalizer().normalize_payload(
            payload,
            self.brief,
        )
        self.assertIsNone(proposal)
        self.assertEqual(report.decision, "blocked")
        self.assertIn(
            "semantic_proposal_schema_invalid",
            report.blocking_reasons,
        )
        self.assertTrue(
            any(
                finding.location[-1:] == ["from_join_field"]
                for finding in report.findings
            )
        )

    def test_unknown_record_field_blocks_without_dropping_it(self) -> None:
        payload = _semantic_payload()
        payload["evidence_nodes"][0]["artifact_spec"]["records"][0][
            "undeclared_business_fact"
        ] = "must-not-be-dropped"
        proposal, report = TaskDesignProposalNormalizer().normalize_payload(
            payload,
            self.brief,
        )
        self.assertIsNone(proposal)
        self.assertIn(
            "unknown_semantic_record_field:node_primary:0",
            report.blocking_reasons,
        )

    def test_schema_findings_do_not_persist_provider_values(self) -> None:
        payload = _semantic_payload()
        secret_marker = "provider-private-value-7f191d"
        payload["scenario"] = {"invalid": secret_marker}
        proposal, report = TaskDesignProposalNormalizer().normalize_payload(
            payload,
            self.brief,
        )
        self.assertIsNone(proposal)
        self.assertTrue(report.findings)
        serialized = json.dumps(report.model_dump(mode="json"))
        self.assertNotIn(secret_marker, serialized)
        self.assertNotIn("input", serialized)
        self.assertFalse(report.raw_provider_values_in_findings)

    def test_projection_guard_detects_semantic_loss(self) -> None:
        proposal, report = LossInjectingNormalizer().normalize_payload(
            _semantic_payload(),
            self.brief,
        )
        self.assertIsNone(proposal)
        self.assertEqual(report.decision, "blocked")
        self.assertTrue(report.semantic_loss_detected)
        self.assertIn(
            "normalization_semantic_loss_detected",
            report.blocking_reasons,
        )
        self.assertGreater(report.facts_removed, 0)

    def test_tracked_schema_interface_negative_controls_fail_closed(self) -> None:
        catalog = json.loads(
            (FIXTURE_ROOT / "schema_interface_cases.json").read_text(
                encoding="utf-8"
            )
        )
        observed_case_ids = []
        for case in catalog["cases"]:
            with self.subTest(case_id=case["case_id"]):
                payload = copy.deepcopy(_semantic_payload())
                mutation = case["mutation"]
                parent = payload
                for part in mutation["path"][:-1]:
                    parent = parent[part]
                leaf = mutation["path"][-1]
                if mutation["op"] == "remove":
                    parent.pop(leaf)
                elif mutation["op"] == "replace":
                    parent[leaf] = mutation["value"]
                elif mutation["op"] == "repeat_string":
                    parent[leaf] = mutation["value"] * mutation["count"]
                elif mutation["op"] == "wrap_record":
                    values = parent[leaf]
                    parent[leaf] = {
                        "record_id": values["record_id"],
                        "values": values,
                    }
                else:  # pragma: no cover - fixture contract guard
                    self.fail(f"unknown mutation op: {mutation['op']}")
                proposal, report = (
                    TaskDesignProposalNormalizer().normalize_payload(
                        payload,
                        self.brief,
                    )
                )
                self.assertIsNone(proposal)
                self.assertEqual(report.decision, "blocked")
                self.assertIn(
                    case["expected_blocking_reason"],
                    report.blocking_reasons,
                )
                self.assertFalse(report.materialization_authorized)
                self.assertFalse(report.registry_mutation_authorized)
                self.assertFalse(report.promotion_authorized)
                self.assertNotIn(
                    "provider-private-value-must-not-persist",
                    json.dumps(report.model_dump(mode="json")),
                )
                observed_case_ids.append(case["case_id"])
        self.assertEqual(
            observed_case_ids,
            [
                "missing_required_field",
                "wrong_union_shape",
                "legacy_nested_record_shape",
                "missing_relation_join_contract",
                "boolean_enum_display",
                "oversized_semantic_proposal",
            ],
        )


if __name__ == "__main__":
    unittest.main()
