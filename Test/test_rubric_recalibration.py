from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from src.task_generator.v3_rubric_scoring_audit import RubricScoringAuthorityAuditor
from src.task_generator.v3_rubric_recalibration_campaign import (
    RubricRecalibrationAuthorizationRequestV1,
    RubricRecalibrationAuthorizationReceiptV1,
    RubricRecalibrationCampaign,
    RubricRecalibrationManifestV1,
    detect_reviewer_inconsistency,
)
from src.task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
)
from task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError as RuntimeSemanticReviewExecutionError,
    SemanticReviewExecutor as RuntimeSemanticReviewExecutor,
)
from task_generator.v3_validity_utility import (
    RubricFocusRealityReviewV3 as RuntimeRubricFocusRealityReviewV3,
    RubricFocusRealityReviewV4 as RuntimeRubricFocusRealityReviewV4,
)
from src.task_generator.v3_skill_extractor import ProviderConfig
from src.task_generator.v3_validity_utility import (
    CandidateBlindRealityReviewV2,
    RealityReviewDimensionV2,
    RubricFocusRealityReviewV3,
    RubricFocusRealityReviewV4,
    RubricPairAssessmentV3,
)


CRITERIA = [
    ("criterion_evidence_traceability", "evidence_traceability"),
    ("criterion_exception_handling", "exception_handling"),
    ("criterion_factual_accuracy", "factual_accuracy"),
    ("criterion_method_process", "method_process"),
    ("criterion_professional_expression", "professional_expression"),
    ("criterion_reproducibility", "reproducibility"),
    ("criterion_structural_usability", "structural_usability"),
]


def _criterion(criterion_id: str, dimension: str, index: int) -> dict:
    weights = {
        "factual_accuracy": 0.2,
        "evidence_traceability": 0.15,
        "method_process": 0.15,
        "exception_handling": 0.15,
        "reproducibility": 0.15,
        "structural_usability": 0.1,
        "professional_expression": 0.1,
    }
    return {
        "criterion_id": criterion_id,
        "dimension": dimension,
        "axis": "validity" if dimension == "factual_accuracy" else "utility",
        "weight": weights[dimension],
        "observable_behavior": f"Distinct observable professional behavior number {index}.",
        "independent_failure_signal": f"distinct_failure_signal_{index}",
        "evidence_requirements": [f"Inspect evidence family {index}."],
        "evidence_or_judgment_ids": ["shared_evidence"] if index in {0, 1} else [f"evidence_{index}"],
        "skill_ids": [] if dimension == "factual_accuracy" else ["shared_skill"],
        "capability_ids": [] if dimension == "factual_accuracy" else ["shared_capability"],
        "partial_score_bands": [
            {"score_ratio": 0.0, "meaning": "Required evidence is absent or the failure signal is present."},
            {"score_ratio": 0.5, "meaning": "The behavior is materially present but incomplete or inconsistent."},
            {"score_ratio": 1.0, "meaning": "The behavior is complete, consistent, and supported by evidence."},
        ],
        "professional_evidence_ceiling": "deterministic" if dimension == "factual_accuracy" else "structural_proxy",
    }


class RubricRecalibrationTests(unittest.TestCase):
    def _write_inputs(
        self,
        root: Path,
        *,
        duplicate_signal: bool = False,
        duplicate_criterion: bool = False,
        binding_authority: str = "program_compiled_binding_not_final_weight",
        effective_dimension_count: int = 7,
    ) -> tuple[Path, Path]:
        criteria = [_criterion(criterion_id, dimension, index) for index, (criterion_id, dimension) in enumerate(CRITERIA)]
        if duplicate_signal:
            criteria[1]["independent_failure_signal"] = criteria[0]["independent_failure_signal"]
        if duplicate_criterion:
            criteria[1]["criterion_id"] = criteria[0]["criterion_id"]
        rubric = {
            "rubric_version": "v3.rubric_plan.2", "case_id": "case", "proposal_id": "proposal",
            "criteria": criteria, "decision": "pass", "total_weight": 1.0,
            "factual_weight_ratio": 0.2, "effective_dimension_count": effective_dimension_count,
            "duplicate_fact_anchor_assignments": [], "duplicate_failure_signals": [],
            "final_weights_frozen_before_results": True, "notes": [],
        }
        bindings = {
            "plan_version": "v3.hybrid_rubric_binding_plan.1", "proposal_id": "proposal",
            "bindings": [{
                "criterion_id": "criterion_skill_trace", "criterion_type": "reasoning",
                "observable_behavior": "Trace-only behavior annotation for one selected skill.",
                "skill_ids": ["shared_skill"], "capability_ids": ["shared_capability"],
                "evidence_or_judgment_ids": ["shared_evidence"],
                "scoring_authority": binding_authority,
            }],
            "final_weights_assigned": False,
        }
        rubric_path = root / "rubric.json"
        binding_path = root / "bindings.json"
        rubric_path.write_text(json.dumps(rubric), encoding="utf-8")
        binding_path.write_text(json.dumps(bindings), encoding="utf-8")
        return rubric_path, binding_path

    def test_shared_skill_and_evidence_do_not_imply_duplicate_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rubric, bindings = self._write_inputs(Path(directory))
            audit = RubricScoringAuthorityAuditor().compile(rubric_plan_path=rubric, rubric_binding_plan_path=bindings, case_id="blind_case")
        self.assertEqual(audit.decision, "pass")
        self.assertEqual(audit.final_scoring_criteria_count, 7)
        self.assertEqual(audit.annotation_bindings_count, 1)
        self.assertTrue(audit.annotation_bindings_non_scoring)
        self.assertTrue(audit.criterion_count_valid)
        self.assertTrue(audit.rubric_metadata_valid)
        self.assertEqual(len(audit.pair_audits), 21)
        shared = [item for item in audit.pair_audits if item.shared_evidence_or_judgment_ids]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0].deterministic_class, "shared_trace_evidence")

    def test_duplicate_signal_and_binding_authority_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric, bindings = self._write_inputs(root, duplicate_signal=True)
            audit = RubricScoringAuthorityAuditor().compile(rubric_plan_path=rubric, rubric_binding_plan_path=bindings)
            self.assertEqual(audit.decision, "blocked")
            rubric, bindings = self._write_inputs(root, binding_authority="final_weight")
            audit = RubricScoringAuthorityAuditor().compile(rubric_plan_path=rubric, rubric_binding_plan_path=bindings)
            self.assertEqual(audit.decision, "blocked")
            self.assertFalse(audit.binding_authority_valid)

    def test_duplicate_criterion_and_bad_metadata_persist_as_blocked_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric, bindings = self._write_inputs(root, duplicate_criterion=True)
            audit = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=rubric, rubric_binding_plan_path=bindings
            )
            self.assertEqual(audit.decision, "blocked")
            self.assertFalse(audit.criterion_count_valid)
            self.assertTrue(audit.duplicate_criterion_ids)
            rubric, bindings = self._write_inputs(root, effective_dimension_count=6)
            audit = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=rubric, rubric_binding_plan_path=bindings
            )
            self.assertEqual(audit.decision, "blocked")
            self.assertFalse(audit.rubric_metadata_valid)

    def test_semantic_signature_tracks_scoring_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric, bindings = self._write_inputs(root)
            first = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=rubric, rubric_binding_plan_path=bindings
            )
            payload = json.loads(rubric.read_text(encoding="utf-8"))
            payload["criteria"][0]["observable_behavior"] += " Materially changed."
            rubric.write_text(json.dumps(payload), encoding="utf-8")
            second = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=rubric, rubric_binding_plan_path=bindings
            )
            self.assertNotEqual(
                first.scoring_semantic_signature,
                second.scoring_semantic_signature,
            )

    def _review_payload(self, risky: str | None = None) -> dict:
        ids = sorted(item[0] for item in CRITERIA)
        assessments = []
        for left, right in combinations(ids, 2):
            assessment = (
                risky
                if risky and not assessments
                else "shared_evidence_distinct_behavior"
                if not assessments
                else "distinct"
            )
            assessments.append({
                "criterion_a": left, "criterion_b": right, "assessment": assessment,
                "rationale": "The two criteria have distinct observable behaviors and failure signals.",
                "evidence_locators": [f"rubric:{left}", f"rubric:{right}"],
            })
        return {
            "case_id": "case", "final_scoring_criterion_ids": ids,
            "final_scoring_criteria_count": 7,
            "annotation_bindings_recognized_non_scoring": True,
            "pair_assessments": assessments,
            "decision": "blocked" if risky == "duplicate" else "revise" if risky == "potential_duplicate" else "pass",
            "rationale": "The complete pairwise scoring-authority review supports this decision.",
        }

    def _review_payload_v4(self, risky: str | None = None) -> dict:
        ids = sorted(item[0] for item in CRITERIA)
        assessments = []
        risk_findings = []
        for left, right in combinations(ids, 2):
            assessment = (
                risky
                if risky and not assessments
                else "shared_evidence_distinct_behavior"
                if not assessments
                else "distinct"
            )
            assessments.append({
                "criterion_a": left,
                "criterion_b": right,
                "assessment": assessment,
            })
            if assessment in {"potential_duplicate", "duplicate"}:
                risk_findings.append({
                    "criterion_a": left,
                    "criterion_b": right,
                    "assessment": assessment,
                    "rationale": f"{left} and {right} materially overlap in scored behavior.",
                    "evidence_locators": [f"rubric:{left}", f"rubric:{right}"],
                })
        return {
            "case_id": "case",
            "final_scoring_criterion_ids": ids,
            "final_scoring_criteria_count": 7,
            "annotation_bindings_recognized_non_scoring": True,
            "pair_assessments": assessments,
            "risk_findings": risk_findings,
            "decision": "blocked" if risky == "duplicate" else "revise" if risky else "pass",
            "summary": "The compact exhaustive pair review supports this decision.",
        }

    def test_v3_requires_all_pairs_and_risky_pair_for_revise(self) -> None:
        review = RubricFocusRealityReviewV3.model_validate(self._review_payload())
        self.assertEqual(len(review.pair_assessments), 21)
        revise = RubricFocusRealityReviewV3.model_validate(self._review_payload("potential_duplicate"))
        self.assertEqual(revise.decision, "revise")
        missing = self._review_payload()
        missing["pair_assessments"].pop()
        with self.assertRaisesRegex(ValidationError, "21_pairs"):
            RubricFocusRealityReviewV3.model_validate(missing)
        inconsistent = self._review_payload()
        inconsistent["decision"] = "revise"
        with self.assertRaisesRegex(ValidationError, "decision_mismatch"):
            RubricFocusRealityReviewV3.model_validate(inconsistent)

    def test_v4_compacts_pass_pairs_and_requires_risk_details(self) -> None:
        review = RubricFocusRealityReviewV4.model_validate(
            self._review_payload_v4()
        )
        self.assertEqual(len(review.pair_assessments), 21)
        self.assertFalse(review.risk_findings)
        revise = RubricFocusRealityReviewV4.model_validate(
            self._review_payload_v4("potential_duplicate")
        )
        self.assertEqual(revise.decision, "revise")
        self.assertEqual(len(revise.risk_findings), 1)
        missing = self._review_payload_v4("potential_duplicate")
        missing["risk_findings"] = []
        with self.assertRaisesRegex(ValidationError, "risk_findings"):
            RubricFocusRealityReviewV4.model_validate(missing)
        self.assertLess(
            len(json.dumps(self._review_payload_v4())),
            len(json.dumps(self._review_payload())) * 0.55,
        )

    def test_same_structure_with_different_decisions_is_reviewer_inconsistency(self) -> None:
        signature = "a" * 64
        pass_review = RubricFocusRealityReviewV3.model_validate(self._review_payload())
        revise_review = RubricFocusRealityReviewV3.model_validate(
            self._review_payload("potential_duplicate")
        )
        cases = [
            SimpleNamespace(scoring_semantic_signature=signature, overall_decision="pass", rubric_review=pass_review),
            SimpleNamespace(scoring_semantic_signature=signature, overall_decision="revise", rubric_review=revise_review),
        ]
        self.assertEqual(detect_reviewer_inconsistency(cases), [signature])
        cases[1].overall_decision = "pass"
        cases[1].rubric_review = pass_review
        self.assertEqual(detect_reviewer_inconsistency(cases), [])

    def test_v2_rubric_review_entrypoint_remains_compatible(self) -> None:
        executor = SemanticReviewExecutor.__new__(SemanticReviewExecutor)
        executor._call = Mock(return_value="v2-result")
        result = executor.review_reality_rubric_focus({"case_id": "case"})
        self.assertEqual(result, "v2-result")
        self.assertEqual(executor._call.call_args.args[2].__name__, "RubricFocusRealityReviewV2")

    def test_full_message_budget_blocks_before_provider_client(self) -> None:
        executor = SemanticReviewExecutor(
            ProviderConfig(
                provider_name="deepseek",
                model="deepseek-v4-pro",
                base_url="https://example.invalid",
                api_key="secret",
            ),
            input_token_hard_limit=10,
            max_retries=0,
        )
        with patch("openai.OpenAI") as client:
            with self.assertRaisesRegex(
                SemanticReviewExecutionError, "token ceiling"
            ):
                executor.review_reality_rubric_focus_v3({"case_id": "case"})
        client.assert_not_called()
        self.assertGreater(executor.last_diagnostics["estimated_input_tokens"], 10)

    def test_v4_full_message_is_smaller_and_v1_request_remains_readable(self) -> None:
        executor = SemanticReviewExecutor(
            ProviderConfig(
                provider_name="deepseek",
                model="deepseek-v4-pro",
                base_url="https://example.invalid",
                api_key="secret",
            ),
            input_token_hard_limit=12000,
            max_retries=0,
        )
        payload = {"case_id": "case", "rubric_plan": {"criteria": []}}
        self.assertLess(
            executor.estimate_reality_rubric_focus_v4_input_tokens(payload),
            executor.estimate_reality_rubric_focus_v3_input_tokens(payload),
        )
        case_ids = [f"case_{index}" for index in range(6)]
        repeated = {case_id: "a" * 64 for case_id in case_ids}
        request = RubricRecalibrationAuthorizationRequestV1(
            request_version="v3.rubric_recalibration_authorization_request.1",
            requested_scope="rubric_focus_recalibration",
            cohort_id="cohort",
            selected_case_ids=case_ids,
            authorized_stage_keys=[
                f"{case_id}:rubric_focus_v3" for case_id in case_ids
            ],
            prior_completed_manifest_path="prior.json",
            prior_completed_manifest_sha256="a" * 64,
            prior_cohort_result_path="result.json",
            prior_cohort_result_sha256="b" * 64,
            retained_candidate_call_tree_sha256=repeated,
            retained_candidate_review_sha256=repeated,
            rubric_input_sha256=repeated,
            scoring_audit_path={case_id: "audit.json" for case_id in case_ids},
            scoring_audit_sha256=repeated,
            scoring_structure_signature=repeated,
            scoring_semantic_signature=repeated,
            selection_manifest_path="selection.json",
            selection_manifest_sha256="c" * 64,
            campaign_manifest_sha256="d" * 64,
            container_parity_report_path="parity.json",
            container_parity_report_sha256="e" * 64,
            source_fingerprint="f" * 64,
            user_action_required="Explicit authorization is required before provider execution.",
        )
        self.assertTrue(request.request_version.endswith(".1"))

    def test_review_must_align_with_frozen_shared_evidence_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rubric, bindings = self._write_inputs(Path(directory))
            audit = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=rubric, rubric_binding_plan_path=bindings
            )
        payload = self._review_payload()
        payload["pair_assessments"][0]["assessment"] = "distinct"
        review = RubricFocusRealityReviewV3.model_validate(payload)
        with self.assertRaisesRegex(
            RuntimeSemanticReviewExecutionError, "shared-evidence"
        ):
            RubricRecalibrationCampaign._validate_review_against_audit(
                review, audit
            )

    def test_campaign_uses_one_controlled_format_retry_and_reuses_candidates(self) -> None:
        case_ids = [f"case_{index}" for index in range(6)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rubric, bindings = self._write_inputs(root)
            base_audit = RubricScoringAuthorityAuditor().compile(
                rubric_plan_path=rubric,
                rubric_binding_plan_path=bindings,
                case_id=case_ids[0],
            )
            audit_paths = {}
            for case_id in case_ids:
                audit = base_audit.model_copy(update={"case_id": case_id})
                path = root / f"{case_id}_audit.json"
                path.write_text(audit.model_dump_json(), encoding="utf-8")
                audit_paths[case_id] = str(path)
            candidate_dimensions = [
                RealityReviewDimensionV2(
                    dimension=name,
                    decision="pass",
                    rationale="The retained candidate review passed this dimension.",
                    evidence_locators=["candidate:fixture"],
                )
                for name in (
                    "role_realism",
                    "information_sufficiency",
                    "natural_difficulty",
                    "professional_judgment",
                    "deliverable_realism",
                )
            ]
            prior_result = root / "prior.json"
            prior_result.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": case_id,
                                "candidate_review": CandidateBlindRealityReviewV2(
                                    case_id=case_id,
                                    dimensions=candidate_dimensions,
                                ).model_dump(mode="json"),
                            }
                            for case_id in case_ids
                        ]
                    }
                ),
                encoding="utf-8",
            )
            repeated = {case_id: "a" * 64 for case_id in case_ids}
            request = RubricRecalibrationAuthorizationRequestV1(
                cohort_id="cohort",
                selected_case_ids=case_ids,
                authorized_stage_keys=[
                    f"{case_id}:rubric_focus_v4_compact" for case_id in case_ids
                ],
                prior_completed_manifest_path=str(root / "prior_manifest.json"),
                prior_completed_manifest_sha256="a" * 64,
                prior_cohort_result_path=str(prior_result),
                prior_cohort_result_sha256="b" * 64,
                retained_candidate_call_tree_sha256=repeated,
                retained_candidate_review_sha256=repeated,
                rubric_input_sha256=repeated,
                scoring_audit_path=audit_paths,
                scoring_audit_sha256=repeated,
                scoring_structure_signature={
                    case_id: base_audit.structure_signature for case_id in case_ids
                },
                scoring_semantic_signature={
                    case_id: base_audit.scoring_semantic_signature
                    for case_id in case_ids
                },
                selection_manifest_path=str(root / "selection.json"),
                selection_manifest_sha256="c" * 64,
                campaign_manifest_sha256="d" * 64,
                container_parity_report_path=str(root / "parity.json"),
                container_parity_report_sha256="e" * 64,
                source_fingerprint="f" * 64,
                user_action_required="Explicit authorization is required before provider execution.",
            )
            output = root / "output"
            manifest_path = output / "campaign_manifest.json"
            manifest = RubricRecalibrationManifestV1(
                cohort_id="cohort",
                authorization_request_sha256="a" * 64,
                authorization_receipt_sha256="b" * 64,
                status="running",
                completed_stages=0,
                provider_calls_made=0,
                controlled_retries_used=0,
                created_at="2026-07-20T00:00:00+00:00",
                updated_at="2026-07-20T00:00:00+00:00",
            )
            campaign = RubricRecalibrationCampaign(root)
            calls = {"count": 0}

            def review(executor, payload, *, format_feedback=None):
                calls["count"] += 1
                executor.last_diagnostics = {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "duration_seconds": 1.0,
                }
                if calls["count"] == 1:
                    executor.last_raw_response_content = "not-json"
                    raise RuntimeSemanticReviewExecutionError(
                        "invalid JSON fixture",
                        retry_eligible=True,
                        failure_code="invalid_json",
                    )
                review_payload = self._review_payload_v4()
                review_payload["case_id"] = payload["case_id"]
                executor.last_raw_response_content = json.dumps(review_payload)
                return RuntimeRubricFocusRealityReviewV4.model_validate(review_payload)

            with patch.object(
                campaign,
                "_rubric_payload",
                side_effect=lambda case_id, req: {"case_id": case_id},
            ), patch.object(
                RuntimeSemanticReviewExecutor,
                "estimate_reality_rubric_focus_v4_input_tokens",
                return_value=100,
            ), patch.object(
                RuntimeSemanticReviewExecutor,
                "review_reality_rubric_focus_v4",
                new=review,
            ):
                result = campaign._execute_reviews(
                    request,
                    ProviderConfig(
                        provider_name="deepseek",
                        model="deepseek-v4-pro",
                        base_url="https://example.invalid",
                        api_key="secret",
                    ),
                    output,
                    manifest,
                    manifest_path,
                )
            self.assertEqual(result.decision, "screening_ready")
            self.assertEqual(manifest.completed_stages, 6)
            self.assertEqual(manifest.provider_calls_made, 7)
            self.assertEqual(manifest.controlled_retries_used, 1)
            self.assertEqual(manifest.reserved_cost_ceiling_usd, 0.07)
            self.assertEqual(
                result.cases[0].retained_candidate_call_tree_sha256,
                "a" * 64,
            )

            failed_output = root / "failed_output"
            failed_manifest_path = failed_output / "campaign_manifest.json"
            failed_manifest = RubricRecalibrationManifestV1(
                cohort_id="cohort",
                authorization_request_sha256="a" * 64,
                authorization_receipt_sha256="b" * 64,
                status="running",
                completed_stages=0,
                provider_calls_made=0,
                controlled_retries_used=0,
                created_at="2026-07-20T00:00:00+00:00",
                updated_at="2026-07-20T00:00:00+00:00",
            )

            def always_invalid(executor, payload, *, format_feedback=None):
                executor.last_raw_response_content = "not-json"
                executor.last_diagnostics = {}
                raise RuntimeSemanticReviewExecutionError(
                    "invalid JSON fixture",
                    retry_eligible=True,
                    failure_code="invalid_json",
                )

            with patch.object(
                campaign,
                "_rubric_payload",
                side_effect=lambda case_id, req: {"case_id": case_id},
            ), patch.object(
                RuntimeSemanticReviewExecutor,
                "estimate_reality_rubric_focus_v4_input_tokens",
                return_value=100,
            ), patch.object(
                RuntimeSemanticReviewExecutor,
                "review_reality_rubric_focus_v4",
                new=always_invalid,
            ):
                with self.assertRaises(RuntimeSemanticReviewExecutionError):
                    campaign._execute_reviews(
                        request,
                        ProviderConfig(
                            provider_name="deepseek",
                            model="deepseek-v4-pro",
                            base_url="https://example.invalid",
                            api_key="secret",
                        ),
                        failed_output,
                        failed_manifest,
                        failed_manifest_path,
                    )
            self.assertEqual(failed_manifest.provider_calls_made, 2)
            self.assertEqual(failed_manifest.controlled_retries_used, 1)
            self.assertEqual(failed_manifest.completed_stages, 0)
            self.assertEqual(failed_manifest.reserved_cost_ceiling_usd, 0.02)

            drifted_receipt = RubricRecalibrationAuthorizationReceiptV1(
                authorization_id="fixture",
                authorization_request_sha256="0" * 64,
                cohort_id="cohort",
                authorized_case_ids=case_ids,
                authorized_model="deepseek-v4-pro",
                maximum_provider_calls=12,
                maximum_total_cost_usd=0.13,
                authorized_by_user=True,
                authorization_statement="The exact fixture request is authorized.",
                issued_at="2026-07-20T00:00:00+00:00",
            )
            with self.assertRaisesRegex(PermissionError, "scope_mismatch"):
                campaign._validate_receipt(request, "a" * 64, drifted_receipt)


if __name__ == "__main__":
    unittest.main()
