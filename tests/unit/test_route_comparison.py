from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from task_generator.generation.hybrid_materializer import HybridTaskMaterializer
from task_generator.evaluation.route_comparison import (
    RouteComparisonAnalyzer,
    RouteComparisonManifestBuilder,
    RouteBlindPackageStager,
    RouteTaskEvidenceV1,
)
from task_generator.planning.task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignProposalV1,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"

    / "task_design"
    / "capability_brief.json"
)


class RouteComparisonTests(unittest.TestCase):
    def test_manifest_freezes_four_by_three_matched_screening(self):
        manifest = self._manifest()
        self.assertEqual(len(manifest.briefs), 4)
        self.assertEqual(len(manifest.assignments), 12)
        self.assertEqual(len({item.blind_task_id for item in manifest.assignments}), 12)
        self.assertTrue(manifest.route_blinding_enabled)
        self.assertTrue(manifest.thresholds.frozen_before_results)
        self.assertFalse(manifest.gdpval_generation_use)
        self.assertFalse(manifest.promotion_authorized)

    def test_absolute_gates_precede_relative_ranking(self):
        manifest = self._manifest()
        evidence = []
        for index, assignment in enumerate(manifest.assignments):
            passing = assignment.route_id != "strict_template"
            evidence.append(
                self._evidence(
                    assignment,
                    passing=passing,
                    score_ratio=[0.45, 0.60, 0.75, 0.95][index % 4],
                    complexity=(
                        0.92
                        if assignment.route_id == "llm_led_hybrid"
                        else 0.85
                        if passing
                        else 0.50
                    ),
                )
            )
        report = RouteComparisonAnalyzer().analyze(manifest, evidence)
        self.assertTrue(report.evidence_complete)
        self.assertEqual(report.decision, "advance_two_routes")
        self.assertEqual(
            report.confirmation_candidates,
            ["llm_led_hybrid", "skill_guided_llm"],
        )
        strict = next(
            item
            for item in report.route_aggregates
            if item.route_id == "strict_template"
        )
        self.assertFalse(strict.absolute_gate_pass)

    def test_all_routes_failing_absolute_gates_yields_redesign_again(self):
        manifest = self._manifest()
        evidence = [
            self._evidence(
                assignment,
                passing=False,
                score_ratio=0.99,
                complexity=0.40,
            )
            for assignment in manifest.assignments
        ]
        report = RouteComparisonAnalyzer().analyze(manifest, evidence)
        self.assertEqual(report.decision, "redesign_again")
        self.assertFalse(report.confirmation_candidates)

    def test_incomplete_evidence_is_not_ranked(self):
        manifest = self._manifest()
        report = RouteComparisonAnalyzer().analyze(
            manifest,
            [
                self._evidence(
                    manifest.assignments[0],
                    passing=True,
                    score_ratio=0.5,
                    complexity=0.9,
                )
            ],
        )
        self.assertEqual(report.decision, "not_evaluated")
        self.assertFalse(report.evidence_complete)
        self.assertIn("missing_task_evidence", report.blocking_reasons)

    def test_route_blind_staging_removes_route_identity_from_candidate_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            brief = CapabilityBriefV1.model_validate_json(
                FIXTURE.read_text(encoding="utf-8")
            )
            proposal = TaskDesignProposalV1.model_validate_json(
                (FIXTURE.parent / "valid_proposal.json").read_text(
                    encoding="utf-8"
                )
            )
            materialized = root / "materialized"
            HybridTaskMaterializer().materialize(
                brief,
                proposal,
                materialized,
            )
            source_export = materialized / "rw_task_export"
            manifest = self._manifest()
            for assignment in manifest.assignments:
                package_root = (
                    root
                    / "route_sources"
                    / assignment.brief_id
                    / assignment.route_id
                )
                shutil.copytree(source_export, package_root)
                assignment.package_root = str(package_root)

            output = root / "staged"
            report = RouteBlindPackageStager().stage(manifest, output)
            self.assertEqual(report.decision, "pass")
            self.assertEqual(report.package_count, 12)
            self.assertTrue(
                (
                    output
                    / "governance"
                    / "route_blind_staging_report.json"
                ).is_file()
            )
            for record in report.records:
                staged = Path(record.staged_export_root)
                self.assertEqual(staged.name, record.blind_task_id)
                dataset_text = (staged / "dataset_row.json").read_text(
                    encoding="utf-8"
                )
                dataset = json.loads(dataset_text)
                self.assertEqual(dataset["task_id"], record.blind_task_id)
                self.assertNotIn("materialization_route", dataset_text)
                self.assertNotIn("task_design_proposal_id", dataset_text)
                self.assertNotIn(record.route_id, dataset_text)
                self.assertIn(
                    record.validation_status,
                    {"draft_compatible", "candidate_ready_compatible"},
                )
                self.assertFalse(
                    any(
                        "teacher" in part.lower()
                        for path in staged.rglob("*")
                        for part in path.relative_to(staged).parts
                    )
                )

    def _manifest(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        briefs = []
        for index, motif in enumerate(
            [
                "cross_document_reconciliation",
                "exception_analysis",
                "validation_workpaper",
                "review_memo",
            ],
            start=1,
        ):
            item = json.loads(json.dumps(payload))
            item["brief_id"] = f"brief_{index}"
            item["case_id"] = f"case_{index}"
            item["motif"] = motif
            briefs.append(CapabilityBriefV1.model_validate(item))
        routes = RouteComparisonManifestBuilder.ROUTES
        package_roots = {
            brief.brief_id: {
                route: f"artifacts/comparison/{brief.brief_id}/{route}"
                for route in routes
            }
            for brief in briefs
        }
        return RouteComparisonManifestBuilder().build(
            comparison_id="comparison_fixture",
            briefs=briefs,
            source_snapshot_sha256="a" * 64,
            package_roots=package_roots,
            code_fingerprint="b" * 40,
            environment_contract_id="fixed-local-docker-v1",
            solver_preflight_contract_path="governance/solver_preflight.json",
            grader_calibration_contract_path=(
                "governance/evaluation_calibration_contract.json"
            ),
            timeout_seconds=1800,
            maximum_provider_cost_usd=100.0,
        )

    @staticmethod
    def _evidence(
        assignment,
        *,
        passing: bool,
        score_ratio: float,
        complexity: float,
    ):
        return RouteTaskEvidenceV1(
            blind_task_id=assignment.blind_task_id,
            brief_id=assignment.brief_id,
            route_id=assignment.route_id,
            offline_validity_pass=passing,
            solver_preflight_pass=passing,
            exact_valid_delivery=passing,
            systemic_task_failure=not passing,
            major_defect=not passing,
            professional_plausibility="pass" if passing else "fail",
            productive_complexity_coverage=complexity,
            skill_causal_coverage=0.95 if passing else 0.50,
            effective_rubric_dimensions=7 if passing else 3,
            score_ratio=score_ratio,
            grader_disagreement=False,
            comparable_model_pair=passing,
            provider_cost_usd=1.0,
            runtime_seconds=10.0,
            review_minutes=2.0,
            implementation_complexity_points=1.0,
            validity_vector_path="validity_vector.json",
            utility_profile_path="utility_profile.json",
            behavioral_execution_report_path="behavioral_execution_report.json",
            output_fingerprints=["output.xlsx:sha256"],
        )


if __name__ == "__main__":
    unittest.main()
