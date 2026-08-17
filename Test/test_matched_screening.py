from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_formal_brief_admission import (
    FormalBriefCohortAdmission,
    SourceProvenanceLedgerV1,
    SourceProvenanceRecordV1,
)
from src.task_generator.v3_matched_screening import (
    DeepSeekSolverPreflightAuthorizationRequestV1,
    MatchedGenerationAuthorizationRequestV1,
    MatchedGenerationRecoveryAuthorizationRequestV1,
    MatchedScreeningAnalyzer,
    MatchedScreeningCampaign,
    ScreeningTaskObservationV1,
    ScreeningGraderReviewV1,
    deepseek_solver_environment,
    select_screening_solver,
)
from src.task_generator.v3_matched_solver_preflight import (
    DeepSeekSolverPreflightAuthorizationReceiptV1,
    MatchedSolverPreflightGovernance,
)
from src.task_generator.v3_solver_execution_budget import SolverExecutionBudgetV1
from src.task_generator.v3_task_design_frontend import CapabilityBriefV1


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pipeline_reconstruction" / "task_design" / "capability_brief.json"


class MatchedScreeningTests(unittest.TestCase):
    def _brief(self, motif: str, suffix: str) -> CapabilityBriefV1:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["brief_id"] = f"brief_{suffix}"
        payload["case_id"] = f"case_{suffix}"
        payload["motif"] = motif
        payload["workflow_context"]["subgraph_id"] = f"subgraph_{suffix}"
        payload["source_refs"] = [
            {
                "source_ref_id": "source_candidate_public_001",
                "locator": "https://example.org/public",
                "evidence_spans": ["evidence_public"],
                "trust_boundary": "untrusted_source_data",
            }
        ]
        for skill in payload["selected_skills"]:
            skill["provenance_ref_ids"] = ["source_candidate_public_001", "evidence_public"]
        return CapabilityBriefV1.model_validate(payload)

    def _ledger(self) -> SourceProvenanceLedgerV1:
        return SourceProvenanceLedgerV1(
            records=[
                SourceProvenanceRecordV1(
                    source_candidate_id="source_candidate_public_001",
                    source_id="source_public_001",
                    source_kind="public_web",
                    source_group_id="finance_audit_public",
                    locator="https://example.org/public",
                    evidence_refs=["evidence_public"],
                    evidence_spans=["block:1-10"],
                )
            ]
        )

    def test_matched_admission_allows_two_per_motif(self):
        briefs = []
        for motif in ("fan_in_reconciliation", "cross_check_validation", "policy_application"):
            briefs.extend([self._brief(motif, motif + "_a"), self._brief(motif, motif + "_b")])
        report = FormalBriefCohortAdmission().evaluate_matched_screening(briefs, self._ledger())
        self.assertEqual(report.decision, "pass")
        self.assertEqual(report.motif_counts["fan_in_reconciliation"], 2)

    def test_matched_admission_blocks_e2d_and_wrong_shape(self):
        briefs = [self._brief("fan_in_reconciliation", str(index)) for index in range(6)]
        briefs[-1].motif = "evidence_to_deliverable"
        report = FormalBriefCohortAdmission().evaluate_matched_screening(briefs, self._ledger())
        self.assertEqual(report.decision, "blocked")
        reasons = report.findings[0].reason_codes
        self.assertIn("experimental_motif_forbidden", reasons)

    def test_replicate_b_changes_identity_and_trigger(self):
        original = self._brief("policy_application", "policy_a")
        sibling = MatchedScreeningCampaign.compile_replicate_b(original)
        self.assertNotEqual(original.brief_id, sibling.brief_id)
        self.assertNotEqual(original.case_id, sibling.case_id)
        self.assertNotEqual(original.trigger_event, sibling.trigger_event)
        self.assertEqual(
            {item.skill_id for item in original.selected_skills},
            {item.skill_id for item in sibling.selected_skills},
        )

    def test_generation_request_rejects_missing_exclusions(self):
        with self.assertRaises(ValueError):
            MatchedGenerationAuthorizationRequestV1(
                campaign_id="screening",
                requested_blind_task_ids=[f"task_{i}" for i in range(6)],
                requested_routes=["skill_guided_llm", "llm_led_hybrid"],
                maximum_total_cost_usd=24,
                campaign_manifest_sha256="a" * 64,
                source_ledger_sha256="b" * 64,
                admission_report_sha256="c" * 64,
                repair_readiness_report_sha256="d" * 64,
                source_fingerprint="e" * 64,
                parity_report_path="parity.json",
                parity_report_sha256="f" * 64,
                excluded_authorities=[],
            )

    def test_deepseek_environment_is_child_only(self):
        base = {"DEEPSEEK_API_KEY": "secret-test-value", "UNCHANGED": "yes"}
        child = deepseek_solver_environment(base)
        self.assertEqual(child["AGENT_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(child["AGENT_API_KEY"], "secret-test-value")
        self.assertNotIn("AGENT_API_KEY", base)

    def test_deepseek_preflight_request_is_single_attempt_public_only(self):
        budget = SolverExecutionBudgetV1(
            solver_model="deepseek-v4-pro", maximum_provider_calls=8,
            maximum_agent_turns=8, maximum_request_bytes_per_call=131072,
            maximum_completion_tokens_per_call=4096,
            maximum_provider_input_tokens=131072,
            maximum_provider_output_tokens=8192,
            input_cost_usd_per_million_tokens=10,
            output_cost_usd_per_million_tokens=30,
            maximum_contract_cost_usd=1.0,
            maximum_context_tokens=64000,
        )
        request = DeepSeekSolverPreflightAuthorizationRequestV1(
            campaign_id="matched", fixture_tree_sha256="a" * 64,
            solver_budget=budget.model_dump(mode="json"), campaign_manifest_sha256="b" * 64,
            parity_report_path="parity.json", parity_report_sha256="c" * 64,
            source_fingerprint="d" * 64,
        )
        self.assertEqual(request.provider_sdk_retries, 0)
        self.assertEqual(request.runner_retries, 0)
        self.assertFalse(request.private_packages_uploaded)
        self.assertFalse(request.grader_authorized)

    def test_deepseek_preflight_receipt_cannot_expand_authority(self):
        receipt = DeepSeekSolverPreflightAuthorizationReceiptV1(
            campaign_id="matched", authorization_request_sha256="a" * 64,
            fixture_tree_sha256="b" * 64, campaign_manifest_sha256="c" * 64,
            parity_report_sha256="d" * 64, source_fingerprint="e" * 64,
            authorized_by_user=True,
            authorization_statement="I authorize this exact public fixture request.",
            issued_at="2026-07-21T00:00:00+00:00",
            expires_at="2026-07-22T00:00:00+00:00",
        )
        self.assertFalse(receipt.private_package_upload_authorized)
        self.assertFalse(receipt.business_execution_authorized)
        self.assertFalse(receipt.grader_authorized)

    def test_deepseek_preflight_fixture_rejects_private_or_extra_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / "case"
            (case / "reference_files").mkdir(parents=True)
            (case / "dataset_row.json").write_text(json.dumps({
                "task_id": "solver_tool_preflight",
                "reference_files": ["reference_files/copy_template.xlsx"],
                "deliverable_files": [
                    "deliverable_files/created_workbook.xlsx",
                    "deliverable_files/edited_template.xlsx",
                ],
                "extra": {"tool_only_preflight": True, "business_task": False, "grader_authorized": False},
            }), encoding="utf-8")
            (case / "deliverable_contract.json").write_text("{}", encoding="utf-8")
            (case / "prompt.md").write_text("public", encoding="utf-8")
            (case / "reference_files" / "copy_template.xlsx").write_bytes(b"xlsx")
            MatchedSolverPreflightGovernance._validate_public_fixture(Path(temporary))
            (case / "private_package.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                MatchedSolverPreflightGovernance._validate_public_fixture(Path(temporary))

    def test_solver_selection_prefers_deepseek_then_gemini(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deepseek = root / "deepseek.json"
            gemini = root / "gemini.json"
            gemini.write_text(json.dumps({"solver_model": "gemini-3.1-pro-preview", "status": "pass", "eligible_for_business_eval": True}), encoding="utf-8")
            deepseek.write_text(json.dumps({"solver_model": "deepseek-v4-pro", "status": "pass", "eligible_for_business_eval": True}), encoding="utf-8")
            selected = select_screening_solver(deepseek_preflight_path=deepseek, retained_gemini_preflight_path=gemini)
            self.assertEqual(selected.selected_model, "deepseek-v4-pro")
            deepseek.write_text(json.dumps({"solver_model": "deepseek-v4-pro", "status": "fail", "eligible_for_business_eval": False}), encoding="utf-8")
            selected = select_screening_solver(deepseek_preflight_path=deepseek, retained_gemini_preflight_path=gemini)
            self.assertEqual(selected.selected_model, "gemini-3.1-pro-preview")

    def _observations(self, *, infrastructure=True, failing_route=None):
        rows = []
        for route in ("skill_guided_llm", "llm_led_hybrid"):
            for index, motif in enumerate(("fan_in_reconciliation", "cross_check_validation", "policy_application") * 2):
                passes = route != failing_route
                rows.append(ScreeningTaskObservationV1(
                    blind_task_id=f"{route}_{index}", route_id=route, motif=motif,
                    replicate_id="a" if index < 3 else "b",
                    infrastructure_complete=infrastructure,
                    offline_validity_pass=True, exact_valid_delivery=passes,
                    major_defect=False, professional_plausibility_pass=passes,
                    productive_complexity_pass=passes, skill_causal_pass=True,
                    effective_rubric_dimensions=7, weighted_score=0.7,
                ))
        return rows

    def test_screening_decisions(self):
        analyzer = MatchedScreeningAnalyzer()
        self.assertEqual(analyzer.analyze("c", self._observations()).decision, "confirmation_ready_both")
        self.assertEqual(analyzer.analyze("c", self._observations(failing_route="skill_guided_llm")).decision, "single_route_confirmation_candidate")
        self.assertEqual(analyzer.analyze("c", self._observations(infrastructure=False)).decision, "incomplete")

    def test_grader_score_is_recomputed(self):
        criteria = []
        criterion_ids = (
            "criterion_factual_accuracy",
            "criterion_evidence_traceability",
            "criterion_method_process",
            "criterion_exception_handling",
            "criterion_reproducibility",
            "criterion_structural_usability",
            "criterion_professional_expression",
        )
        for criterion_id in criterion_ids:
            criteria.append(
                {
                    "criterion_id": criterion_id,
                    "score": 1.0,
                    "rationale": "The bound evidence demonstrates the required behavior.",
                    "evidence_locators": ["deliverable:sheet!A1"],
                }
            )
        review = ScreeningGraderReviewV1(
            blind_task_id="blind",
            criteria=criteria,
            major_defect=False,
            professional_plausibility="pass",
            effective_rubric_dimensions=7,
            weighted_score=1.0,
        )
        self.assertEqual(review.weighted_score, 1.0)
        with self.assertRaises(ValueError):
            ScreeningGraderReviewV1(
                blind_task_id="blind",
                criteria=criteria,
                major_defect=False,
                professional_plausibility="pass",
                effective_rubric_dimensions=7,
                weighted_score=0.5,
            )

    def test_generation_recovery_scope_is_single_call_and_fail_closed(self):
        request = MatchedGenerationRecoveryAuthorizationRequestV1(
            campaign_id="campaign",
            blind_task_id="blind-policy-b",
            maximum_total_cost_usd=2.0,
            prior_failure_report_sha256="a" * 64,
            consumed_request_sha256="b" * 64,
            campaign_manifest_sha256="c" * 64,
            source_fingerprint="d" * 64,
            parity_report_path="parity.json",
            parity_report_sha256="e" * 64,
            excluded_authorities=[
                "other_assignments", "reality_review", "solver_execution",
                "grader_execution", "training", "registry_mutation",
                "release_activation", "promotion",
            ],
        )
        self.assertEqual(request.maximum_provider_calls, 1)
        self.assertEqual(request.sdk_retries, 0)
        with self.assertRaises(ValueError):
            MatchedGenerationRecoveryAuthorizationRequestV1(
                **{**request.model_dump(), "excluded_authorities": ["training"]}
            )
        with tempfile.TemporaryDirectory() as temporary:
            model, path, request_sha = MatchedScreeningCampaign(temporary)._write_request(
                "generation_recovery", request.model_dump(mode="json")
            )
            self.assertEqual(model.blind_task_id, "blind-policy-b")
            self.assertEqual(path.name, f"{request_sha}.json")
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
