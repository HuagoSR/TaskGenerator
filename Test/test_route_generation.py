from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_hybrid_task_materializer import HybridTaskMaterializer
from src.task_generator.v3_route_generation import StrictTemplateProposalCompiler
from src.task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignFrontend,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
    / "capability_brief.json"
)


class RouteGenerationTests(unittest.TestCase):
    def test_strict_template_uses_distinct_motif_semantics(self):
        base = CapabilityBriefV1.model_validate_json(
            FIXTURE.read_text(encoding="utf-8")
        )
        motifs = {
            "fan_in_reconciliation": ("transaction_id", "source_amount"),
            "cross_check_validation": ("control_id", "observed_result"),
            "policy_application": ("control_id", "compliance_status"),
            "evidence_to_deliverable": ("finding_id", "risk_rating"),
        }
        field_sets = set()
        compiler = StrictTemplateProposalCompiler()
        for motif, (join_field, comparison_field) in motifs.items():
            brief = base.model_copy(update={"motif": motif})
            proposal = compiler.compile(brief)
            first_spec = proposal.evidence_nodes[0].artifact_spec
            self.assertIsNotNone(first_spec)
            fields = tuple(item.field_name for item in first_spec.fields)
            field_sets.add(fields)
            self.assertIn(join_field, fields)
            self.assertIn(comparison_field, fields)
            self.assertNotIn("business_requirement", fields)
            self.assertNotIn("review_status", fields)
            self.assertTrue(
                all(
                    relation.from_join_field == join_field
                    and relation.to_join_field == join_field
                    and relation.comparison_fields[0].from_field
                    == comparison_field
                    for relation in proposal.evidence_relations
                )
            )
            validation = TaskDesignFrontend().validate_proposal(brief, proposal)
            self.assertEqual(validation.decision, "pass")
        self.assertEqual(len(field_sets), len(motifs))

    def test_strict_template_compiles_without_llm_and_passes_frontend(self):
        brief = CapabilityBriefV1.model_validate_json(
            FIXTURE.read_text(encoding="utf-8")
        )
        proposal = StrictTemplateProposalCompiler().compile(brief)
        self.assertEqual(proposal.proposal_origin, "program")
        self.assertEqual(
            proposal.proposal_version,
            "v3.task_design_proposal.2",
        )
        self.assertTrue(
            all(node.artifact_spec is not None for node in proposal.evidence_nodes)
        )
        self.assertEqual(proposal.actor_role, brief.business_role)
        self.assertEqual(proposal.trigger_event, brief.trigger_event)
        validation = TaskDesignFrontend().validate_proposal(brief, proposal)
        self.assertEqual(validation.decision, "pass")
        authority = TaskDesignFrontend().validate_design_authority(
            brief,
            proposal,
            "skill_guided_llm",
        )
        self.assertEqual(authority.decision, "pass")

    def test_strict_template_materializes_on_shared_hybrid_backend(self):
        brief = CapabilityBriefV1.model_validate_json(
            FIXTURE.read_text(encoding="utf-8")
        )
        proposal = StrictTemplateProposalCompiler().compile(brief)
        with tempfile.TemporaryDirectory() as directory:
            report = HybridTaskMaterializer().materialize(
                brief,
                proposal,
                Path(directory) / "strict_template",
            )
        self.assertEqual(report.decision, "pass")
        self.assertEqual(report.evidence_content_quality_decision, "pass")
        self.assertEqual(
            report.materialization_backend,
            "hybrid_semantic_artifact_v2",
        )
        self.assertFalse(report.legacy_template_route_used)


if __name__ == "__main__":
    unittest.main()
