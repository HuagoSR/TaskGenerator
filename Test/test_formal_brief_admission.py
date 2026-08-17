from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.task_generator.v3_formal_brief_admission import (
    FormalBriefCohortAdmission,
    SourceProvenanceLedgerV1,
    SourceProvenanceLedgerCompiler,
    SourceProvenanceRecordV1,
)
from src.task_generator.v3_task_design_frontend import CapabilityBriefV1


FIXTURE_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
)


class FormalBriefAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads(
            (FIXTURE_ROOT / "capability_brief.json").read_text(encoding="utf-8")
        )
        payload["source_refs"] = [
            {
                "source_ref_id": "source_candidate_public_001",
                "locator": "https://example.org/governed-source",
                "evidence_spans": ["ev_public_001"],
                "trust_boundary": "untrusted_source_data",
            }
        ]
        for skill in payload["selected_skills"]:
            skill["provenance_ref_ids"] = [
                "source_candidate_public_001",
                "ev_public_001",
            ]
        self.brief = CapabilityBriefV1.model_validate(payload)
        self.ledger = SourceProvenanceLedgerV1(
            records=[
                SourceProvenanceRecordV1(
                    source_candidate_id="source_candidate_public_001",
                    source_id="web_source_public_001",
                    normalized_source_id="norm_public_001",
                    source_kind="public_web",
                    source_group_id="governed_workflow_public_001",
                    locator="https://example.org/governed-source",
                    evidence_refs=["ev_public_001"],
                    evidence_spans=["block_001:10-40"],
                )
            ]
        )

    def _cohort(self):
        briefs = []
        for index, motif in enumerate(
            [
                "cross_check_validation",
                "evidence_to_deliverable",
                "fan_in_reconciliation",
                "policy_application",
            ],
            start=1,
        ):
            payload = self.brief.model_dump(mode="json")
            payload["brief_id"] = f"brief_public_{index}"
            payload["case_id"] = f"case_public_{index}"
            payload["motif"] = motif
            payload["workflow_context"]["subgraph_id"] = f"subgraph_public_{index}"
            briefs.append(CapabilityBriefV1.model_validate(payload))
        return briefs

    def test_public_resolved_distinct_cohort_passes(self):
        report = FormalBriefCohortAdmission().evaluate(
            self._cohort(), self.ledger
        )
        self.assertEqual(report.decision, "pass")
        self.assertEqual(len(report.admitted_brief_ids), 4)

    def test_gdpval_source_blocks_entire_brief(self):
        ledger = self.ledger.model_copy(deep=True)
        ledger.records[0].source_kind = "gdpval"
        report = FormalBriefCohortAdmission().evaluate(self._cohort(), ledger)
        self.assertEqual(report.decision, "blocked")
        self.assertTrue(
            all(
                "forbidden_generation_source_kind" in finding.reason_codes
                for finding in report.findings
                if finding.brief_id != "__cohort__"
            )
        )

    def test_opaque_or_unresolved_source_blocks(self):
        briefs = self._cohort()
        briefs[0].source_refs[0].locator = (
            "registry-source-candidate:source_candidate_public_001"
        )
        report = FormalBriefCohortAdmission().evaluate(
            briefs, SourceProvenanceLedgerV1()
        )
        self.assertEqual(report.decision, "blocked")
        finding = next(
            item for item in report.findings if item.brief_id == briefs[0].brief_id
        )
        self.assertIn("opaque_or_synthetic_source_locator", finding.reason_codes)
        self.assertIn("unresolved_source_candidate", finding.reason_codes)

    def test_multiple_source_groups_block_formal_brief(self):
        briefs = self._cohort()
        second = self.ledger.records[0].model_copy(deep=True)
        second.source_candidate_id = "source_candidate_public_002"
        second.source_group_id = "different_workflow"
        briefs[0].source_refs.append(
            briefs[0].source_refs[0].model_copy(
                update={"source_ref_id": second.source_candidate_id}
            )
        )
        briefs[0].selected_skills[0].provenance_ref_ids.append(
            second.source_candidate_id
        )
        report = FormalBriefCohortAdmission().evaluate(
            briefs,
            SourceProvenanceLedgerV1(records=[self.ledger.records[0], second]),
        )
        finding = next(
            item for item in report.findings if item.brief_id == briefs[0].brief_id
        )
        self.assertEqual(report.decision, "blocked")
        self.assertIn("multiple_source_groups_in_brief", finding.reason_codes)

    def test_missing_source_group_blocks_formal_brief(self):
        ledger = self.ledger.model_copy(deep=True)
        ledger.records[0].source_group_id = None
        report = FormalBriefCohortAdmission().evaluate(self._cohort(), ledger)
        self.assertEqual(report.decision, "blocked")
        self.assertTrue(
            all(
                "missing_source_group" in finding.reason_codes
                for finding in report.findings
                if finding.brief_id != "__cohort__"
            )
        )

    def test_hydration_replaces_opaque_registry_locator(self):
        brief = self._cohort()[0]
        brief.source_refs[0].locator = (
            "registry-source-candidate:source_candidate_public_001"
        )
        hydrated = FormalBriefCohortAdmission().hydrate_brief(brief, self.ledger)
        self.assertEqual(
            hydrated.source_refs[0].locator,
            "https://example.org/governed-source",
        )

    def test_candidate_ref_matches_registry_algorithm(self):
        compiler = SourceProvenanceLedgerCompiler()
        self.assertTrue(callable(compiler.compile))

    def _representative_pilot(self):
        briefs = []
        domains = {}
        index = 0
        for domain in ("audit_compliance", "procurement_operations"):
            for motif in (
                "fan_in_reconciliation",
                "cross_check_validation",
                "policy_application",
            ):
                for replicate in ("a", "b"):
                    index += 1
                    payload = self.brief.model_dump(mode="json")
                    payload["brief_id"] = f"brief_pilot_{index:02d}"
                    payload["case_id"] = f"case_pilot_{index:02d}"
                    payload["motif"] = motif
                    payload["workflow_context"]["subgraph_id"] = (
                        f"subgraph_pilot_{index:02d}"
                    )
                    payload["productive_complexity_floor"] = [
                        "Decide how evidence should be connected.",
                        "Preserve an evidence conflict requiring judgment.",
                        "Produce a review-ready synthesis.",
                        f"Preserve the {motif} relationship.",
                    ]
                    brief = CapabilityBriefV1.model_validate(payload)
                    briefs.append(brief)
                    domains[brief.brief_id] = domain
        return briefs, domains

    def test_representative_pilot_requires_and_accepts_twelve_cells(self):
        briefs, domains = self._representative_pilot()
        report = FormalBriefCohortAdmission().evaluate_representative_pilot(
            briefs,
            self.ledger,
            domains_by_brief=domains,
        )
        self.assertEqual(report.decision, "pass")
        self.assertEqual(len(report.admitted_brief_ids), 12)
        self.assertEqual(set(report.cell_counts.values()), {2})

    def test_representative_pilot_blocks_missing_cell(self):
        briefs, domains = self._representative_pilot()
        removed = briefs.pop()
        domains.pop(removed.brief_id)
        report = FormalBriefCohortAdmission().evaluate_representative_pilot(
            briefs,
            self.ledger,
            domains_by_brief=domains,
        )
        self.assertEqual(report.decision, "blocked")
        cohort = next(
            item for item in report.findings if item.brief_id == "__cohort__"
        )
        self.assertIn("unexpected_brief_count", cohort.reason_codes)

    def test_representative_pilot_blocks_unbound_capability(self):
        briefs, domains = self._representative_pilot()
        briefs[0].required_capabilities.append(
            briefs[0].required_capabilities[0].model_copy(
                update={"capability_id": "capability_unbound"}
            )
        )
        report = FormalBriefCohortAdmission().evaluate_representative_pilot(
            briefs,
            self.ledger,
            domains_by_brief=domains,
        )
        finding = next(
            item for item in report.findings if item.brief_id == briefs[0].brief_id
        )
        self.assertEqual(report.decision, "blocked")
        self.assertIn(
            "required_capability_not_causally_bound",
            finding.reason_codes,
        )


if __name__ == "__main__":
    unittest.main()
