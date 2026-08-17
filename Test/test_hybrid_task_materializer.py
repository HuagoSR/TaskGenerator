from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from src.task_generator.v3_hybrid_task_materializer import HybridTaskMaterializer
from src.task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignProposalV1,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
)


class HybridTaskMaterializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = CapabilityBriefV1.model_validate_json(
            (FIXTURE_ROOT / "capability_brief.json").read_text(encoding="utf-8")
        )
        self.proposal = TaskDesignProposalV1.model_validate_json(
            (FIXTURE_ROOT / "valid_proposal.json").read_text(encoding="utf-8")
        )

    def test_valid_proposal_materializes_candidate_visible_truth_and_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hybrid"
            report = HybridTaskMaterializer().materialize(
                self.brief,
                self.proposal,
                root,
            )
            self.assertEqual(report.decision, "pass")
            self.assertEqual(report.evidence_file_count, 2)
            self.assertGreaterEqual(report.deterministic_anchor_count, 3)
            self.assertTrue(report.deliverable_contract_valid)
            self.assertTrue(report.complexity_preservation_pass)
            self.assertTrue(report.r5_offline_governance_pass)
            self.assertEqual(report.validity_overall_status, "provisional")
            self.assertEqual(report.utility_profile_status, "provisional")
            self.assertEqual(report.rubric_plan_decision, "pass")
            self.assertTrue(report.visual_validation_pass)
            self.assertEqual(
                report.rw_task_export_validation_status,
                "draft_compatible",
            )
            self.assertTrue(report.candidate_teacher_isolation_pass)
            self.assertFalse(report.legacy_template_route_used)

            prompt = (root / "candidate" / "prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "deliverable_files/validation_workpaper.xlsx",
                prompt,
            )
            self.assertNotIn("mismatch_keys", prompt)
            candidate_manifest = json.loads(
                (
                    root
                    / "candidate"
                    / "candidate_package_manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertFalse(candidate_manifest["teacher_artifacts_included"])
            self.assertFalse(
                any("teacher" in item for item in candidate_manifest["reference_files"])
            )

            anchors = json.loads(
                (
                    root
                    / "teacher"
                    / "deterministic_fact_anchors.json"
                ).read_text(encoding="utf-8")
            )
            relation = next(
                item
                for item in anchors["anchors"]
                if item["anchor_type"] == "relation_crosscheck"
            )
            self.assertEqual(relation["expected_value"]["mismatch_keys"], ["REC-002"])
            self.assertEqual(relation["expected_value"]["exact_match_count"], 3)
            self.assertTrue(
                all(
                    item["truth_authority"]
                    == "deterministic_candidate_visible_recomputation"
                    for item in anchors["anchors"]
                )
            )
            self.assertTrue(
                (root / "teacher" / "rubric_plan_v2.json").is_file()
            )
            self.assertTrue(
                (root / "governance" / "validity_vector.json").is_file()
            )
            self.assertTrue(
                (root / "governance" / "utility_profile.json").is_file()
            )
            self.assertTrue(
                (
                    root
                    / "governance"
                    / "evaluation_calibration_contract.json"
                ).is_file()
            )
            dataset_row = json.loads(
                (root / "rw_task_export" / "dataset_row.json").read_text(
                    encoding="utf-8"
                )
            )
            rubric = json.loads(dataset_row["rubric_json"])
            self.assertEqual(len(rubric), 7)
            self.assertEqual(sum(item["weight"] for item in rubric), 1.0)
            self.assertEqual(
                dataset_row["extra"]["rubric_factual_weight_ratio"],
                0.2,
            )
            self.assertTrue(
                dataset_row["extra"]["behavioral_preflight_required"]
            )
            workbook_path = next(
                (root / "candidate" / "reference_files").glob("*.xlsx")
            )
            workbook = load_workbook(workbook_path, read_only=True)
            self.assertEqual(workbook["Evidence"]["B2"].value, "REC-001")
            workbook.close()
            dossier = json.loads(
                (
                    root
                    / "governance"
                    / "evidence_dossier_plan.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(
                all(item["linked_skill_ids"] for item in dossier["files"])
            )
            self.assertTrue(
                all(item["linked_capability_ids"] for item in dossier["files"])
            )
            export_validation = json.loads(
                (
                    root
                    / "rw_task_export"
                    / "rw_task_export_validation_report.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                export_validation["validation_status"],
                "draft_compatible",
            )

    def test_invalid_proposal_stops_before_candidate_package(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self.proposal.model_dump(mode="json")
            payload["unresolved_design_questions"] = ["Which threshold applies?"]
            proposal = TaskDesignProposalV1.model_validate(payload)
            root = Path(directory) / "blocked"
            report = HybridTaskMaterializer().materialize(
                self.brief,
                proposal,
                root,
            )
            self.assertEqual(report.decision, "blocked")
            self.assertIn("task_design_proposal_invalid", report.reason_codes)
            self.assertFalse((root / "candidate" / "prompt.md").exists())

    def test_repair_context_exposes_governed_contracts_as_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hybrid"
            materializer = HybridTaskMaterializer()
            materializer.materialize(self.brief, self.proposal, root)
            context = materializer.build_repair_context(
                root, ["independent reviewer requested clearer exception rationale"]
            )
            self.assertIn(
                "deliverable_files/validation_workpaper.xlsx",
                context.candidate_prompt,
            )
            self.assertTrue(context.evidence_dossier["files"])
            self.assertTrue(context.deterministic_fact_anchors["anchors"])
            self.assertTrue(context.rubric_binding_plan["bindings"])
            self.assertTrue(
                any("read-only" in item for item in context.immutable_authorities)
            )

    def test_bounded_repair_loop_allows_one_revision_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid_payload = self.proposal.model_dump(mode="json")
            invalid_payload["unresolved_design_questions"] = [
                "Which threshold applies?"
            ]
            invalid = TaskDesignProposalV1.model_validate(invalid_payload)
            root = Path(directory) / "repair"
            report = HybridTaskMaterializer().run_bounded_repair_loop(
                self.brief,
                [invalid, self.proposal],
                root,
            )
            self.assertEqual(report.decision, "pass")
            self.assertEqual(report.attempt_count, 2)
            self.assertEqual(
                report.selected_proposal_id,
                self.proposal.proposal_id,
            )
            self.assertFalse(report.external_editor_calls)
            self.assertTrue(
                Path(report.attempts[0].repair_context_path).is_file()
            )

    def test_repair_loop_rejects_more_than_one_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "attempt_limit"):
                HybridTaskMaterializer().run_bounded_repair_loop(
                    self.brief,
                    [self.proposal, self.proposal, self.proposal],
                    Path(directory) / "too_many",
                )


if __name__ == "__main__":
    unittest.main()
