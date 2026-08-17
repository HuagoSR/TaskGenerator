from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_validation import (  # noqa: E402
    BehavioralExecutionReportV1,
    SolverToolPreflight,
    SolverToolPreflightReportV1,
)
from task_generator.v3_evaluation_calibration import (  # noqa: E402
    EvaluationCalibrationCompiler,
    GraderScoreObservationV1,
    ProfessionalValidityReviewV1,
    SolverPanelMemberV1,
)
from task_generator.v3_route_comparison_campaign import (  # noqa: E402
    RouteComparisonCampaign,
)
from task_generator.v3_route_evidence_compiler import (  # noqa: E402
    RouteComparisonEvidenceCompiler,
    RouteComparisonEvidenceInputManifestV1,
    RouteTaskEvidenceInputV1,
)


BRIEF_FIXTURE = (
    ROOT
    / "Test"
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
    / "capability_brief.json"
)


class RouteEvidenceCompilerTests(unittest.TestCase):
    MODELS = [
        ("weak-model", "weak", 0.35),
        ("medium-model", "medium", 0.65),
        ("strong-model", "strong", 0.90),
    ]

    def _campaign(self, root: Path) -> RouteComparisonCampaign:
        base = json.loads(BRIEF_FIXTURE.read_text(encoding="utf-8"))
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
            payload = json.loads(json.dumps(base))
            payload["brief_id"] = f"evidence_brief_{index}"
            payload["case_id"] = f"evidence_case_{index}"
            payload["motif"] = motif
            path = root / f"brief_{index}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            briefs.append(path)
        source = root / "source.json"
        source.write_text('{"source":"fixture"}', encoding="utf-8")
        campaign = RouteComparisonCampaign(root / "campaign")
        campaign.prepare(
            comparison_id="evidence_compiler_fixture",
            brief_paths=briefs,
            source_snapshot_path=source,
            environment_contract_id="fixed-test-environment",
            solver_preflight_contract_path="governance/panel.json",
            grader_calibration_contract_path="governance/grader.json",
        )
        campaign.materialize_strict_template_controls()
        manifest = campaign.read()
        for brief_id in manifest.frozen_brief_paths:
            strict = next(
                item
                for item in manifest.assignments
                if item.brief_id == brief_id
                and item.route_id == "strict_template"
            )
            for route in ("skill_guided_llm", "llm_led_hybrid"):
                target = next(
                    item
                    for item in manifest.assignments
                    if item.brief_id == brief_id and item.route_id == route
                )
                import shutil

                shutil.copytree(strict.package_root, target.package_root)
                target.stage = "materialized"
                target.package_fingerprint = campaign._tree_fingerprint(
                    Path(target.package_root)
                )
        manifest.status = "packages_ready"
        campaign._write(manifest)
        campaign.stage_route_blind_packages()
        return campaign

    def _input_manifest(
        self,
        root: Path,
        *,
        invalid_grader_delivery: bool = False,
        systemic_task_id: str | None = None,
    ) -> RouteComparisonEvidenceInputManifestV1:
        campaign = self._campaign(root)
        campaign_manifest = campaign.read()
        staging_report_path = (
            root
            / "campaign"
            / "blind_staging"
            / "governance"
            / "route_blind_staging_report.json"
        )
        staging_payload = json.loads(
            staging_report_path.read_text(encoding="utf-8")
        )
        staged_by_task = {
            item["blind_task_id"]: item for item in staging_payload["records"]
        }
        panel_members = []
        preflight_paths = {}
        for model, stratum, _ in self.MODELS:
            preflight = SolverToolPreflightReportV1(
                solver_model=model,
                environment_id="fixed-test-environment",
                status="pass",
                eligible_for_business_eval=True,
            )
            preflight_path = root / f"{model}_preflight.json"
            preflight_path.write_text(
                preflight.model_dump_json(indent=2),
                encoding="utf-8",
            )
            preflight_paths[model] = preflight_path
            panel_members.append(
                SolverPanelMemberV1(
                    solver_model=model,
                    stratum=stratum,
                    preflight_report_path=str(preflight_path),
                    preflight_report=preflight,
                    provider="fixture",
                    maximum_cost_per_task_usd=1.0,
                )
            )
        panel = EvaluationCalibrationCompiler().freeze_solver_panel(
            panel_id="fixture-panel",
            members=panel_members,
        )
        panel_path = root / "panel.json"
        panel_path.write_text(panel.model_dump_json(indent=2), encoding="utf-8")

        observations = []
        tasks = []
        for assignment in campaign_manifest.assignments:
            task_root = root / "evidence" / assignment.blind_task_id
            task_root.mkdir(parents=True)
            behavioral_paths = []
            for model, _, score in self.MODELS:
                fail = (
                    assignment.blind_task_id == systemic_task_id
                    and model != "strong-model"
                )
                solver_output = task_root / f"{model}_solver_output"
                solver_output.mkdir()
                if not fail:
                    (solver_output / "output.xlsx").write_bytes(
                        f"{assignment.blind_task_id}:{model}".encode("utf-8")
                    )
                output_fingerprints = (
                    SolverToolPreflight.output_fingerprints(solver_output)
                )
                delivery_path = task_root / f"{model}_delivery.json"
                delivery_path.write_text(
                    json.dumps(
                        {
                            "delivery_status": (
                                "invalid" if fail else "valid"
                            )
                        }
                    ),
                    encoding="utf-8",
                )
                staged = staged_by_task[assignment.blind_task_id]
                report = BehavioralExecutionReportV1(
                    case_id=assignment.blind_task_id,
                    solver_model=model,
                    environment_id="fixed-test-environment",
                    preflight_required=True,
                    preflight_status="pass",
                    process_status="succeeded",
                    delivery_status="invalid" if fail else "valid",
                    file_validity_status="fail" if fail else "pass",
                    business_validity_status="not_evaluated" if fail else "pass",
                    professional_quality_status="not_evaluated",
                    grader_eligible=not fail,
                    grader_executed=not fail,
                    failure_category="wrong_path" if fail else "none",
                    input_package_root=staged["staged_export_root"],
                    input_package_fingerprint=staged[
                        "staged_package_fingerprint"
                    ],
                    output_root=str(solver_output),
                    output_tree_fingerprint=(
                        SolverToolPreflight.tree_fingerprint(
                            output_fingerprints
                        )
                    ),
                    output_fingerprints=output_fingerprints,
                    solver_preflight_report_path=str(
                        preflight_paths[model]
                    ),
                    solver_preflight_report_sha256=hashlib.sha256(
                        preflight_paths[model].read_bytes()
                    ).hexdigest(),
                    delivery_inspection_path=str(delivery_path),
                    delivery_inspection_sha256=hashlib.sha256(
                        delivery_path.read_bytes()
                    ).hexdigest(),
                )
                path = task_root / f"{model}_behavioral.json"
                path.write_text(
                    report.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                behavioral_paths.append(str(path))
                if not fail:
                    for repeat, offset in ((1, 0.0), (2, 0.02)):
                        observations.append(
                            self._grader_observation(
                                task_root=task_root,
                                task_id=assignment.blind_task_id,
                                model=model,
                                repeat=repeat,
                                score=score + offset,
                                valid_delivery=not (
                                    invalid_grader_delivery
                                    and not observations
                                ),
                            )
                        )
            (task_root / "professional_review_notes.md").write_text(
                "Independent fixture review notes.",
                encoding="utf-8",
            )
            review = ProfessionalValidityReviewV1(
                blind_task_id=assignment.blind_task_id,
                reviewer_type="independent_expert",
                reviewer_id="fixture-expert",
                generator_independent=True,
                decision="pass",
                evidence_paths=["professional_review_notes.md"],
                rationale=(
                    "Independent fixture review finds the workflow and artifact plausible."
                ),
            )
            review_path = task_root / "professional_review.json"
            review_path.write_text(
                review.model_dump_json(indent=2),
                encoding="utf-8",
            )
            tasks.append(
                RouteTaskEvidenceInputV1(
                    blind_task_id=assignment.blind_task_id,
                    package_root=assignment.package_root,
                    package_fingerprint=campaign._tree_fingerprint(
                        Path(assignment.package_root)
                    ),
                    behavioral_report_paths=behavioral_paths,
                    professional_review_path=str(review_path),
                    provider_cost_usd=1.0,
                    runtime_seconds=10.0,
                    review_minutes=2.0,
                    implementation_complexity_points=1.0,
                )
            )
        observations_path = root / "grader_observations.json"
        observations_path.write_text(
            json.dumps(
                {
                    "observations": [
                        item.model_dump(mode="json") for item in observations
                    ]
                }
            ),
            encoding="utf-8",
        )
        template = RouteComparisonEvidenceInputManifestV1(
            comparison_manifest_path=(
                campaign_manifest.route_comparison_manifest_path
            ),
            route_blind_staging_report_path=str(staging_report_path),
            frozen_solver_panel_path=str(panel_path),
            grader_observations_path=str(observations_path),
            tasks=tasks,
        )
        return RouteComparisonEvidenceCompiler().freeze(template)

    @staticmethod
    def _grader_observation(
        *,
        task_root: Path,
        task_id: str,
        model: str,
        repeat: int,
        score: float,
        valid_delivery: bool,
    ) -> GraderScoreObservationV1:
        output = task_root / f"{model}_grader_{repeat}.json"
        output.write_text(
            json.dumps({"overall_score_ratio": score}),
            encoding="utf-8",
        )
        return GraderScoreObservationV1(
            blind_task_id=task_id,
            solver_model=model,
            grader_model="fixed-grader",
            repeat_index=repeat,
            overall_score_ratio=score,
            dimension_score_ratios={"factual_accuracy": score},
            valid_delivery=valid_delivery,
            grader_output_path=str(output),
            grader_output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        )

    def test_complete_matched_evidence_compiles_twelve_records(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "pass")
            self.assertEqual(report.evidence_count, 12)
            self.assertTrue(
                all(item.exact_valid_delivery for item in report.evidence)
            )
            self.assertTrue(
                all(item.comparable_model_pair for item in report.evidence)
            )
            self.assertTrue(
                all(
                    item.professional_plausibility == "pass"
                    for item in report.evidence
                )
            )

    def test_content_identical_server_path_mapping_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._input_manifest(root)
            staging = json.loads(
                Path(manifest.route_blind_staging_report_path).read_text(
                    encoding="utf-8"
                )
            )
            staged = next(
                item
                for item in staging["records"]
                if item["blind_task_id"] == manifest.tasks[0].blind_task_id
            )
            mapped_input = root / "server_mapped_candidate"
            shutil.copytree(staged["staged_export_root"], mapped_input)
            for report_path_text in manifest.tasks[0].behavioral_report_paths:
                report_path = Path(report_path_text)
                payload = json.loads(
                    report_path.read_text(encoding="utf-8")
                )
                payload["input_package_root"] = str(mapped_input)
                original_preflight = Path(
                    payload["solver_preflight_report_path"]
                )
                mapped_preflight = (
                    root
                    / "server_preflight"
                    / original_preflight.name
                )
                mapped_preflight.parent.mkdir(exist_ok=True)
                shutil.copy2(original_preflight, mapped_preflight)
                payload["solver_preflight_report_path"] = str(
                    mapped_preflight
                )
                report_path.write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )
                manifest.tasks[0].behavioral_report_sha256[
                    report_path_text
                ] = hashlib.sha256(report_path.read_bytes()).hexdigest()
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "pass")

    def test_unfrozen_evidence_template_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            frozen = self._input_manifest(Path(directory))
            payload = frozen.model_dump(mode="json")
            payload["evidence_frozen"] = False
            template = RouteComparisonEvidenceInputManifestV1.model_validate(
                payload
            )
            report = RouteComparisonEvidenceCompiler().compile(template)
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "route_evidence_input_not_frozen",
                report.blocking_reasons,
            )

    def test_invalid_delivery_is_rejected_from_grader_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(
                Path(directory),
                invalid_grader_delivery=True,
            )
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "grader_observation_contains_invalid_delivery",
                report.blocking_reasons,
            )

    def test_missing_behavior_report_blocks_all_partial_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            missing = Path(
                manifest.tasks[0].behavioral_report_paths[0]
            )
            missing.unlink()
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            self.assertEqual(report.evidence_count, 0)
            self.assertIn(
                manifest.tasks[0].blind_task_id,
                report.task_blocking_reasons,
            )

    def test_package_root_cannot_be_substituted_across_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            manifest.tasks[0].package_root = manifest.tasks[1].package_root
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            reasons = report.task_blocking_reasons[
                manifest.tasks[0].blind_task_id
            ]
            self.assertTrue(
                any("package_root_assignment_mismatch" in item for item in reasons)
            )

    def test_mutated_package_fingerprint_blocks_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            package_root = Path(manifest.tasks[0].package_root)
            (package_root / "candidate" / "prompt.md").write_text(
                "mutated prompt",
                encoding="utf-8",
            )
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            reasons = report.task_blocking_reasons[
                manifest.tasks[0].blind_task_id
            ]
            self.assertTrue(
                any(
                    "assignment_package_fingerprint_mismatch" in item
                    for item in reasons
                )
            )

    def test_mutated_grader_output_blocks_all_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            observations_payload = json.loads(
                Path(manifest.grader_observations_path).read_text(
                    encoding="utf-8"
                )
            )
            output_path = Path(
                observations_payload["observations"][0]["grader_output_path"]
            )
            output_path.write_text("mutated", encoding="utf-8")
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "grader_output_artifact_sha256_mismatch",
                report.blocking_reasons,
            )

    def test_mutated_behavioral_report_blocks_task_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            report_path = Path(
                manifest.tasks[0].behavioral_report_paths[0]
            )
            report_path.write_text("{}", encoding="utf-8")
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            reasons = report.task_blocking_reasons[
                manifest.tasks[0].blind_task_id
            ]
            self.assertTrue(
                any(
                    "behavioral_report_sha256_mismatch" in item
                    for item in reasons
                )
            )

    def test_mutated_solver_output_blocks_task_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            report_path = Path(
                manifest.tasks[0].behavioral_report_paths[0]
            )
            behavioral = json.loads(
                report_path.read_text(encoding="utf-8")
            )
            output_root = Path(behavioral["output_root"])
            (output_root / "post_freeze.txt").write_text(
                "mutated solver output",
                encoding="utf-8",
            )
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            reasons = report.task_blocking_reasons[
                manifest.tasks[0].blind_task_id
            ]
            self.assertTrue(
                any(
                    "behavioral_output_fingerprint_mismatch" in item
                    for item in reasons
                )
            )

    def test_mutated_staged_candidate_blocks_task_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            staging = json.loads(
                Path(manifest.route_blind_staging_report_path).read_text(
                    encoding="utf-8"
                )
            )
            staged_root = Path(staging["records"][0]["staged_export_root"])
            (staged_root / "prompt.md").write_text(
                "mutated candidate prompt",
                encoding="utf-8",
            )
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            task_id = staging["records"][0]["blind_task_id"]
            self.assertTrue(
                any(
                    "staged_candidate_package_fingerprint_mismatch" in item
                    for item in report.task_blocking_reasons[task_id]
                )
            )

    def test_frozen_comparison_thresholds_drive_pair_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            comparison_path = Path(manifest.comparison_manifest_path)
            comparison = json.loads(
                comparison_path.read_text(encoding="utf-8")
            )
            comparison["thresholds"][
                "grader_disagreement_absolute_threshold"
            ] = 0.01
            comparison["thresholds"][
                "informative_case_min_score_spread"
            ] = 0.80
            comparison_path.write_text(
                json.dumps(comparison),
                encoding="utf-8",
            )
            manifest.comparison_manifest_sha256 = hashlib.sha256(
                comparison_path.read_bytes()
            ).hexdigest()
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "pass")
            self.assertTrue(
                all(item.grader_disagreement for item in report.evidence)
            )
            self.assertTrue(
                all(
                    not item.comparable_model_pair
                    for item in report.evidence
                )
            )

    def test_missing_professional_support_blocks_task_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self._input_manifest(Path(directory))
            review_path = Path(manifest.tasks[0].professional_review_path)
            (review_path.parent / "professional_review_notes.md").unlink()
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "blocked")
            reasons = report.task_blocking_reasons[
                manifest.tasks[0].blind_task_id
            ]
            self.assertTrue(
                any(
                    "professional_review_support_sha256_mismatch" in item
                    for item in reasons
                )
            )

    def test_two_same_failures_are_systemic_and_delivery_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._input_manifest(root)
            task_id = manifest.tasks[0].blind_task_id
            # Regenerate with the first task carrying two identical failures.
            root2 = root / "systemic"
            root2.mkdir()
            manifest = self._input_manifest(
                root2,
                systemic_task_id=task_id,
            )
            report = RouteComparisonEvidenceCompiler().compile(manifest)
            self.assertEqual(report.decision, "pass")
            task = next(
                item for item in report.evidence
                if item.blind_task_id == task_id
            )
            self.assertTrue(task.systemic_task_failure)
            self.assertFalse(task.exact_valid_delivery)


if __name__ == "__main__":
    unittest.main()
