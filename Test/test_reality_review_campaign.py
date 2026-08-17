from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from openpyxl import Workbook
from pydantic import ValidationError

from src.task_generator.v3_reality_review_campaign import (
    RealityReviewAuthorizationRequestV1,
    RealityReviewCampaign,
    RealityReviewCampaignManifestV1,
    RealityReviewSelectionV1,
)
from src.task_generator.v3_external_model_policy import (
    ExternalModelPolicyError,
    enforce_external_model_policy,
)
from src.task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
)
from src.task_generator.v3_skill_extractor import ProviderConfig
from src.task_generator.v3_validity_utility import (
    CandidateBlindRealityReviewV2,
    RealityCaseReviewV2,
    RealityCohortReviewV2,
    RealityReviewCallEvidenceV2,
    RealityReviewDimensionV2,
    RubricFocusRealityReviewV2,
)


DIMENSIONS = [
    "role_realism",
    "information_sufficiency",
    "natural_difficulty",
    "professional_judgment",
    "deliverable_realism",
]


def _dimension(name: str, decision: str = "pass") -> RealityReviewDimensionV2:
    return RealityReviewDimensionV2(
        dimension=name,
        decision=decision,
        rationale="The supplied evidence supports this review decision.",
        evidence_locators=["reference.xlsx:Evidence!A1"],
    )


def _evidence(stage: str) -> RealityReviewCallEvidenceV2:
    return RealityReviewCallEvidenceV2(
        stage=stage,
        input_sha256="a" * 64,
        raw_output_sha256="b" * 64,
        parsed_output_sha256="c" * 64,
        prompt_tokens=100,
        completion_tokens=50,
        duration_seconds=1.0,
    )


def _case(case_id: str, decision: str = "pass") -> RealityCaseReviewV2:
    candidate_decision = decision if decision != "pass" else "pass"
    candidate = CandidateBlindRealityReviewV2(
        case_id=case_id,
        dimensions=[
            _dimension(name, candidate_decision if index == 0 else "pass")
            for index, name in enumerate(DIMENSIONS)
        ],
    )
    rubric = RubricFocusRealityReviewV2(
        case_id=case_id,
        dimension=_dimension("rubric_focus"),
    )
    return RealityCaseReviewV2(
        case_id=case_id,
        motif="cross_check_validation",
        candidate_review=candidate,
        rubric_review=rubric,
        call_evidence=[_evidence("candidate_blind"), _evidence("rubric_focus")],
        overall_decision=decision,
    )


class RealityReviewCampaignTest(unittest.TestCase):
    def test_format_failure_gets_one_governed_retry_and_preserves_first_failure(self) -> None:
        case_ids = [f"case_{index}_{route}" for index in range(3) for route in ("skill_guided_llm", "llm_led_hybrid")]
        motifs = ["fan_in_reconciliation", "cross_check_validation", "policy_application"]
        selection_payload = {
            "manifest_version": "v3.reality_cohort_selection.1", "cohort_id": "cohort",
            "selection_status": "frozen", "selection_rule": "balanced", "case_count": 6,
            "routes": ["skill_guided_llm", "llm_led_hybrid"], "motifs": motifs,
            "experimental_evidence_to_deliverable_excluded": True,
            "review_dimensions": [*DIMENSIONS, "rubric_focus"],
            "reviewer_route_blinding_required": True, "independent_reviewer_required": True,
            "professional_review_executed": False, "external_calls_made": False,
            "training_admission_authorized": False, "promotion_authorized": False,
            "cases": [
                {"case_id": case_id, "brief_id": f"brief_{index // 2}", "motif": motifs[index // 2],
                 "route_id": case_id.rsplit("_", 1)[-1] if False else ("skill_guided_llm" if index % 2 == 0 else "llm_led_hybrid"),
                 "package_fingerprint": "d" * 64}
                for index, case_id in enumerate(case_ids)
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection_path = root / "selection.json"
            selection_path.write_text(json.dumps(selection_payload), encoding="utf-8")
            request = RealityReviewAuthorizationRequestV1(
                cohort_id="cohort", selected_case_ids=case_ids,
                package_fingerprints={case_id: "a" * 64 for case_id in case_ids},
                candidate_input_tree_sha256={case_id: "b" * 64 for case_id in case_ids},
                rubric_input_sha256={case_id: "c" * 64 for case_id in case_ids},
                selection_manifest_path=str(selection_path), selection_manifest_sha256="d" * 64,
                campaign_manifest_sha256="e" * 64, blind_staging_report_sha256="f" * 64,
                container_parity_report_path="parity.json", container_parity_report_sha256="0" * 64,
                source_fingerprint="9" * 64,
                user_action_required="Explicit authorization is required for DeepSeek review.",
            )
            output = root / "output"
            manifest_path = output / "campaign_manifest.json"
            manifest = RealityReviewCampaignManifestV1(
                cohort_id="cohort", authorization_request_sha256="a" * 64,
                authorization_receipt_sha256="b" * 64, status="running", completed_calls=0,
                created_at=datetime.now(timezone.utc).isoformat(), updated_at=datetime.now(timezone.utc).isoformat(),
            )
            campaign = RealityReviewCampaign(root)
            call_count = {"candidate": 0}

            def candidate(executor, payload, *, format_feedback=None):
                from task_generator.v3_validity_utility import CandidateBlindRealityReviewV2 as RuntimeCandidateReview, RealityReviewDimensionV2 as RuntimeDimension
                call_count["candidate"] += 1
                executor.last_diagnostics = {"prompt_tokens": 100, "completion_tokens": 50, "duration_seconds": 1.0}
                if call_count["candidate"] == 1:
                    executor.last_raw_response_content = "not-json"
                    raise SemanticReviewExecutionError("bad json", retry_eligible=True, failure_code="invalid_json")
                executor.last_raw_response_content = "{}"
                return RuntimeCandidateReview(case_id=payload["case_id"], dimensions=[RuntimeDimension.model_validate(_dimension(name).model_dump()) for name in DIMENSIONS])

            def rubric(executor, payload, *, format_feedback=None):
                from task_generator.v3_validity_utility import RubricFocusRealityReviewV2 as RuntimeRubricReview, RealityReviewDimensionV2 as RuntimeDimension
                executor.last_diagnostics = {"prompt_tokens": 100, "completion_tokens": 50, "duration_seconds": 1.0}
                executor.last_raw_response_content = "{}"
                return RuntimeRubricReview(case_id=payload["case_id"], dimension=RuntimeDimension.model_validate(_dimension("rubric_focus").model_dump()))

            with patch.object(campaign, "_candidate_payload", side_effect=lambda case_id: {"case_id": case_id}), \
                 patch.object(campaign, "_rubric_payload", side_effect=lambda case_id, selected: {"case_id": case_id}), \
                 patch("task_generator.v3_semantic_review_executor.SemanticReviewExecutor.review_reality_candidate_blind", new=candidate), \
                 patch("task_generator.v3_semantic_review_executor.SemanticReviewExecutor.review_reality_rubric_focus", new=rubric):
                cases = campaign._execute_calls(request, ProviderConfig(provider_name="deepseek", model="deepseek-v4-pro", base_url="https://api.deepseek.com", api_key="secret"), output, manifest, manifest_path)
            self.assertEqual(len(cases), 6)
            self.assertEqual(manifest.completed_calls, 12)
            self.assertEqual(manifest.provider_calls_made, 13)
            self.assertEqual(manifest.controlled_retries_used, 1)
            self.assertEqual(cases[0].call_evidence[0].attempt_count, 2)
            self.assertTrue(cases[0].call_evidence[0].first_attempt_failure_sha256)

    def test_deepseek_request_requires_fresh_full_cohort_and_bounded_retry(self) -> None:
        case_ids = [f"case_{index}" for index in range(6)]
        all_stages = {
            f"{case_id}:{stage}"
            for stage in ("candidate_blind", "rubric_focus")
            for case_id in case_ids
        }
        request = RealityReviewAuthorizationRequestV1(
            cohort_id="cohort",
            selected_case_ids=case_ids,
            package_fingerprints={case_id: "a" * 64 for case_id in case_ids},
            candidate_input_tree_sha256={case_id: "b" * 64 for case_id in case_ids},
            rubric_input_sha256={case_id: "c" * 64 for case_id in case_ids},
            selection_manifest_path="selection.json",
            selection_manifest_sha256="d" * 64,
            campaign_manifest_sha256="e" * 64,
            blind_staging_report_sha256="f" * 64,
            container_parity_report_path="parity.json",
            container_parity_report_sha256="0" * 64,
            source_fingerprint="9" * 64,
            authorized_stage_keys=sorted(all_stages),
            user_action_required="Explicit authorization is required for DeepSeek review.",
        )
        self.assertEqual(request.maximum_provider_calls, 24)
        self.assertEqual(request.maximum_attempts_per_stage, 2)
        self.assertEqual(request.maximum_total_cost_usd, 0.25)
        self.assertEqual(set(request.authorized_stage_keys), all_stages)
        self.assertFalse(request.retained_call_sha256)

    def _review_with_response(
        self, content: str, finish_reason: str = "stop", payload=None
    ):
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        )
        create = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        executor = SemanticReviewExecutor(
            ProviderConfig(
                provider_name="deepseek",
                model="deepseek-v4-pro",
                base_url="https://example.invalid/v1",
                api_key="secret",
            ),
            max_retries=0,
        )
        with patch("openai.OpenAI", return_value=client):
            review = executor.review_reality_candidate_blind(
                payload or {"case_id": "case"}
            )
        kwargs = create.call_args.kwargs
        self.assertNotIn("temperature", kwargs)
        self.assertEqual(kwargs["reasoning_effort"], "high")
        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled"}})
        return review

    def test_project_model_policy_blocks_expensive_models(self) -> None:
        with self.assertRaises(ExternalModelPolicyError):
            enforce_external_model_policy("tuzi", "claude-sonnet-4-6")
        with self.assertRaises(ExternalModelPolicyError):
            enforce_external_model_policy("tuzi", "gpt-5.4-pro")
        enforce_external_model_policy("deepseek", "deepseek-v4-pro")

    def test_empty_invalid_truncated_and_missing_dimensions_fail_closed(self) -> None:
        with self.assertRaisesRegex(SemanticReviewExecutionError, "empty"):
            self._review_with_response("")
        with self.assertRaisesRegex(SemanticReviewExecutionError, "contract violation"):
            self._review_with_response("not-json")
        with self.assertRaisesRegex(SemanticReviewExecutionError, "truncated"):
            self._review_with_response("{}", finish_reason="length")
        with self.assertRaisesRegex(SemanticReviewExecutionError, "contract violation"):
            self._review_with_response(json.dumps({"dimensions": []}))

    def test_xlsx_datetime_values_are_serialized_before_provider_call(self) -> None:
        response = {
            "dimensions": [
                {
                    "dimension": name,
                    "decision": "pass",
                    "rationale": "The supplied evidence supports this review decision.",
                    "evidence_locators": ["reference.xlsx:Evidence!A1"],
                }
                for name in DIMENSIONS
            ]
        }
        review = self._review_with_response(
            json.dumps(response),
            payload={
                "case_id": "case",
                "reference_contents": [
                    {"value": datetime(2026, 7, 19, tzinfo=timezone.utc)}
                ],
            },
        )
        self.assertEqual(review.case_id, "case")

    def test_llm_proxy_all_pass_is_screening_only(self) -> None:
        cohort = RealityCohortReviewV2(
            cohort_id="cohort",
            cases=[_case(f"case_{index}") for index in range(6)],
            decision="screening_ready",
            screening_eligible=True,
        )
        self.assertTrue(cohort.screening_eligible)
        self.assertEqual(cohort.professional_validity_status, "provisional")
        self.assertFalse(cohort.expert_evidence_present)
        self.assertFalse(cohort.training_admission_authorized)
        self.assertFalse(cohort.promotion_authorized)

    def test_blocked_case_requires_redesign(self) -> None:
        cases = [_case(f"case_{index}") for index in range(5)] + [_case("case_5", "blocked")]
        cohort = RealityCohortReviewV2(
            cohort_id="cohort",
            cases=cases,
            decision="redesign_required",
            screening_eligible=False,
        )
        self.assertEqual(cohort.decision, "redesign_required")

    def test_incomplete_cohort_cannot_be_screening_ready(self) -> None:
        with self.assertRaisesRegex(ValidationError, "decision_mismatch"):
            RealityCohortReviewV2(
                cohort_id="cohort",
                cases=[_case("one")],
                decision="screening_ready",
                screening_eligible=True,
            )

    def test_selection_requires_balanced_nonexperimental_cases(self) -> None:
        payload = {
            "manifest_version": "v3.reality_cohort_selection.1",
            "cohort_id": "cohort",
            "selection_status": "frozen",
            "selection_rule": "balanced",
            "case_count": 6,
            "routes": ["skill_guided_llm", "llm_led_hybrid"],
            "motifs": ["fan_in_reconciliation", "cross_check_validation", "policy_application"],
            "experimental_evidence_to_deliverable_excluded": True,
            "cases": [],
            "review_dimensions": [*DIMENSIONS, "rubric_focus"],
            "reviewer_route_blinding_required": True,
            "independent_reviewer_required": True,
            "professional_review_executed": False,
            "external_calls_made": False,
            "training_admission_authorized": False,
            "promotion_authorized": False,
        }
        for index, motif in enumerate(payload["motifs"]):
            for route in payload["routes"]:
                payload["cases"].append({
                    "case_id": f"case_{index}_{route}",
                    "brief_id": f"brief_{index}",
                    "motif": motif,
                    "route_id": route,
                    "package_fingerprint": "d" * 64,
                })
        self.assertEqual(len(RealityReviewSelectionV1.model_validate(payload).cases), 6)

    def test_payloads_preserve_candidate_teacher_and_route_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case_id = "blind_case"
            blind = root / "blind_staging" / "candidate_packages" / case_id
            refs = blind / "reference_files"
            refs.mkdir(parents=True)
            (blind / "dataset_row.json").write_text(json.dumps({"task_id": case_id, "prompt": "Review evidence"}), encoding="utf-8")
            (blind / "deliverable_contract.json").write_text(json.dumps({"required": ["result.xlsx"]}), encoding="utf-8")
            workbook = Workbook()
            workbook.active.append(["Evidence", "Value"])
            workbook.save(refs / "reference.xlsx")
            route = root / "route_packages" / "brief" / "skill_guided_llm"
            teacher = route / "teacher"
            teacher.mkdir(parents=True)
            (teacher / "rubric_plan_v2.json").write_text(json.dumps({"criteria": ["quality"]}), encoding="utf-8")
            (teacher / "rubric_binding_plan.json").write_text(json.dumps({"bindings": ["quality"]}), encoding="utf-8")
            (root / "campaign_manifest.json").write_text(json.dumps({"assignments": [{"blind_task_id": case_id, "package_root": str(route)}]}), encoding="utf-8")
            campaign = RealityReviewCampaign(root)
            candidate = campaign._candidate_payload(case_id)
            rubric = campaign._rubric_payload(case_id, None)  # selection metadata is never serialized
            candidate_text = json.dumps(candidate, default=str)
            rubric_text = json.dumps(rubric, default=str)
            self.assertNotIn("teacher", candidate_text)
            self.assertNotIn("skill_guided_llm", candidate_text)
            self.assertNotIn("skill_guided_llm", rubric_text)
            self.assertNotIn("provider", rubric_text)
            self.assertIn("rubric_plan", rubric)


if __name__ == "__main__":
    unittest.main()
