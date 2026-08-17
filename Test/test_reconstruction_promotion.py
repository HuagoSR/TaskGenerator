from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_reconstruction_promotion import (
    ConfirmationGateEvidenceV1,
    ReconstructionPromotionCompiler,
    RouteConfirmationCompiler,
)
from src.task_generator.v3_route_comparison import (
    RouteComparisonAnalyzer,
    RouteComparisonManifestBuilder,
    RouteComparisonReportV1,
    RouteTaskEvidenceV1,
)
from src.task_generator.v3_route_evidence_compiler import (
    RouteComparisonEvidenceCompileReportV1,
)
from src.task_generator.v3_task_design_frontend import CapabilityBriefV1


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
    / "capability_brief.json"
)


class ReconstructionPromotionTests(unittest.TestCase):
    CANDIDATES = ["skill_guided_llm", "llm_led_hybrid"]

    def _screening(
        self,
        root: Path,
        decision: str = "advance_two_routes",
    ) -> Path:
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
            item["brief_id"] = f"promotion_brief_{index}"
            item["case_id"] = f"promotion_case_{index}"
            item["motif"] = motif
            briefs.append(CapabilityBriefV1.model_validate(item))
        package_roots = {
            brief.brief_id: {
                route: str(root / brief.brief_id / route)
                for route in RouteComparisonManifestBuilder.ROUTES
            }
            for brief in briefs
        }
        manifest = RouteComparisonManifestBuilder().build(
            comparison_id="comparison_fixture",
            briefs=briefs,
            source_snapshot_sha256="a" * 64,
            package_roots=package_roots,
            code_fingerprint="b" * 64,
            environment_contract_id="fixed-environment",
            solver_preflight_contract_path="panel.json",
            grader_calibration_contract_path="grader.json",
            timeout_seconds=1800,
            maximum_provider_cost_usd=20.0,
        )
        manifest_path = root / "comparison_manifest.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        evidence = []
        for index, assignment in enumerate(manifest.assignments):
            passing = assignment.route_id != "strict_template"
            evidence.append(
                RouteTaskEvidenceV1(
                    blind_task_id=assignment.blind_task_id,
                    brief_id=assignment.brief_id,
                    route_id=assignment.route_id,
                    offline_validity_pass=passing,
                    solver_preflight_pass=passing,
                    exact_valid_delivery=passing,
                    systemic_task_failure=not passing,
                    major_defect=not passing,
                    professional_plausibility=(
                        "pass" if passing else "fail"
                    ),
                    productive_complexity_coverage=(
                        0.9 if passing else 0.4
                    ),
                    skill_causal_coverage=(
                        0.95 if passing else 0.4
                    ),
                    effective_rubric_dimensions=(
                        7 if passing else 3
                    ),
                    score_ratio=[0.2, 0.4, 0.6, 0.8][index % 4],
                    grader_disagreement=False,
                    comparable_model_pair=passing,
                    validity_vector_path="validity.json",
                    utility_profile_path="utility.json",
                    behavioral_execution_report_path="behavioral",
                )
            )
        compile_report = RouteComparisonEvidenceCompileReportV1(
            comparison_id="comparison_fixture",
            decision="pass",
            evidence_count=12,
            evidence=[
                item.model_dump(mode="json") for item in evidence
            ],
        )
        compile_path = root / "evidence_compile_report.json"
        compile_path.write_text(
            compile_report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        report = RouteComparisonAnalyzer().analyze(manifest, evidence)
        if decision != "advance_two_routes":
            report.decision = decision
            report.confirmation_candidates = []
        report.comparison_manifest_path = str(manifest_path)
        report.comparison_manifest_sha256 = self._sha(manifest_path)
        report.evidence_compile_report_path = str(compile_path)
        report.evidence_compile_report_sha256 = self._sha(compile_path)
        path = root / "screening.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def _confirmation(
        self,
        root: Path,
        screening: Path,
        *,
        blocked_gate: str | None = None,
    ) -> Path:
        gate_paths = {}
        for gate in RouteConfirmationCompiler.REQUIRED_GATES:
            support = root / f"{gate}_support.json"
            support.write_text(
                json.dumps({"gate": gate, "evidence": "fixture"}),
                encoding="utf-8",
            )
            gate_report = ConfirmationGateEvidenceV1(
                gate=gate,
                comparison_id="comparison_fixture",
                candidate_routes=self.CANDIDATES,
                decision="blocked" if gate == blocked_gate else "pass",
                generator_independent=True,
                environment_id=(
                    "fixed-environment"
                    if gate
                    in {
                        "matched_environment",
                        "server_candidate_reproduction",
                    }
                    else None
                ),
                evidence_paths=[str(support)],
                evidence_sha256={str(support): self._sha(support)},
                findings=(
                    ["unresolved truth mismatch"]
                    if gate == blocked_gate
                    else []
                ),
            )
            path = root / f"{gate}.json"
            path.write_text(
                gate_report.model_dump_json(indent=2),
                encoding="utf-8",
            )
            gate_paths[gate] = path
        confirmation = RouteConfirmationCompiler().compile(
            screening_report_path=screening,
            gate_evidence_paths=gate_paths,
            winning_route="llm_led_hybrid",
        )
        path = root / "confirmation.json"
        path.write_text(
            confirmation.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    def test_screening_alone_can_only_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screening = self._screening(root)
            record = ReconstructionPromotionCompiler().compile(
                screening_report_path=screening
            )
            self.assertEqual(record.decision, "hold")
            self.assertIn(
                "confirmation_evidence_missing",
                record.blocking_reasons,
            )
            self.assertFalse(record.release_activation_authorized)

    def test_complete_confirmation_only_proposes_opt_in_route(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screening = self._screening(root)
            confirmation = self._confirmation(root, screening)
            record = ReconstructionPromotionCompiler().compile(
                screening_report_path=screening,
                confirmation_report_path=confirmation,
            )
            self.assertEqual(record.decision, "promote")
            self.assertEqual(record.selected_route, "llm_led_hybrid")
            self.assertTrue(record.opt_in_profile_only)
            self.assertFalse(record.default_chain_mutation_authorized)
            self.assertFalse(record.training_authorized)

    def test_open_major_finding_yields_redesign(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screening = self._screening(root)
            confirmation = self._confirmation(
                root,
                screening,
                blocked_gate="major_validity_closure",
            )
            record = ReconstructionPromotionCompiler().compile(
                screening_report_path=screening,
                confirmation_report_path=confirmation,
            )
            self.assertEqual(record.decision, "redesign_again")
            self.assertIn(
                "major_validity_findings_open",
                record.blocking_reasons,
            )

    def test_tampered_confirmation_support_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screening = self._screening(root)
            confirmation = self._confirmation(root, screening)
            (root / "rollback_verification_support.json").write_text(
                "tampered",
                encoding="utf-8",
            )
            record = ReconstructionPromotionCompiler().compile(
                screening_report_path=screening,
                confirmation_report_path=confirmation,
            )
            self.assertEqual(record.decision, "hold")
            self.assertIn(
                "confirmation_gate_support_sha256_mismatch:"
                "rollback_verification",
                record.blocking_reasons,
            )

    def test_tampered_screening_compile_report_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screening = self._screening(root)
            confirmation = self._confirmation(root, screening)
            (root / "evidence_compile_report.json").write_text(
                "{}",
                encoding="utf-8",
            )
            record = ReconstructionPromotionCompiler().compile(
                screening_report_path=screening,
                confirmation_report_path=confirmation,
            )
            self.assertEqual(record.decision, "hold")
            self.assertIn(
                "screening_evidence_compile_report_sha256_mismatch",
                record.blocking_reasons,
            )

    def test_screening_report_must_recompute_from_compiled_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screening = self._screening(root)
            payload = json.loads(screening.read_text(encoding="utf-8"))
            payload["route_aggregates"][0]["provider_cost_usd"] = 999.0
            screening.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            confirmation = self._confirmation(root, screening)
            record = ReconstructionPromotionCompiler().compile(
                screening_report_path=screening,
                confirmation_report_path=confirmation,
            )
            self.assertEqual(record.decision, "hold")
            self.assertIn(
                "screening_report_recomputation_mismatch",
                record.blocking_reasons,
            )

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
