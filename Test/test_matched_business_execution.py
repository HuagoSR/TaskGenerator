from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_matched_business_execution import (
    MatchedBusinessAuthorizationReceiptV1,
    MatchedBusinessExecutionManifestV1,
    MatchedBusinessGovernance,
    MatchedBusinessTaskRecordV1,
    ScreeningGraderDraftV1,
    validate_single_case_dataset,
)
from src.task_generator.v3_matched_screening import (
    MatchedScreeningAnalyzer,
    ScreeningCriterionGradeV1,
    ScreeningGraderReviewV1,
    ScreeningTaskObservationV1,
)
from src.task_generator.v3_skill_extractor import ProviderConfig


CRITERIA = (
    "criterion_factual_accuracy",
    "criterion_evidence_traceability",
    "criterion_method_process",
    "criterion_exception_handling",
    "criterion_reproducibility",
    "criterion_structural_usability",
    "criterion_professional_expression",
)


class MatchedBusinessExecutionTests(unittest.TestCase):
    def _grades(self, score: float = 1.0):
        return [
            ScreeningCriterionGradeV1(
                criterion_id=criterion,
                score=score,
                rationale="The submitted workbook provides sufficient evidence.",
                evidence_locators=["Workbook!A1"],
            ).model_dump(mode="json")
            for criterion in CRITERIA
        ]

    def test_receipt_cannot_expand_business_authority(self):
        receipt = MatchedBusinessAuthorizationReceiptV1(
            campaign_id="campaign",
            authorization_request_sha256="a" * 64,
            campaign_manifest_sha256="b" * 64,
            staging_report_sha256="c" * 64,
            solver_selection_sha256="d" * 64,
            parity_report_sha256="e" * 64,
            source_fingerprint="f" * 64,
            blind_package_fingerprints={f"task-{i}": "1" * 64 for i in range(12)},
            candidate_tree_sha256={f"task-{i}": "2" * 64 for i in range(12)},
            reality_evidence_sha256={f"task-{i}": "3" * 64 for i in range(12)},
            authorized_by_user=True,
            authorization_statement="User authorizes this exact matched screening request.",
            issued_at="2026-07-21T00:00:00+00:00",
            expires_at="2026-07-22T00:00:00+00:00",
        )
        self.assertFalse(receipt.expert_review_authorized)
        self.assertFalse(receipt.training_authorized)
        self.assertFalse(receipt.promotion_authorized)

    def test_grader_draft_has_no_authoritative_total(self):
        draft = ScreeningGraderDraftV1(
            blind_task_id="blind",
            criteria=self._grades(1.0),
            major_defect=False,
            professional_plausibility="pass",
            effective_rubric_dimensions=7,
        )
        self.assertNotIn("weighted_score", draft.model_dump())
        review = ScreeningGraderReviewV1(
            **draft.model_dump(mode="json"), weighted_score=1.0
        )
        self.assertEqual(review.weighted_score, 1.0)

    def test_grader_route_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            ScreeningGraderDraftV1(
                blind_task_id="blind",
                criteria=self._grades(),
                major_defect=False,
                professional_plausibility="pass",
                effective_rubric_dimensions=7,
                route_identity_seen=True,
            )

    def test_one_non_delivery_can_still_meet_five_of_six_gate(self):
        observations = []
        for route in ("skill_guided_llm", "llm_led_hybrid"):
            for index in range(6):
                delivered = index != 5
                observations.append(
                    ScreeningTaskObservationV1(
                        blind_task_id=f"{route}-{index}",
                        route_id=route,
                        motif=("fan_in_reconciliation", "cross_check_validation", "policy_application")[index // 2],
                        replicate_id="a" if index % 2 == 0 else "b",
                        infrastructure_complete=True,
                        offline_validity_pass=True,
                        exact_valid_delivery=delivered,
                        major_defect=False,
                        professional_plausibility_pass=delivered,
                        productive_complexity_pass=True,
                        skill_causal_pass=True,
                        effective_rubric_dimensions=7 if delivered else 0,
                        weighted_score=0.8 if delivered else None,
                    )
                )
        result = MatchedScreeningAnalyzer().analyze("campaign", observations)
        self.assertEqual(result.decision, "confirmation_ready_both")

    def test_infrastructure_failure_forces_incomplete(self):
        rows = []
        for route in ("skill_guided_llm", "llm_led_hybrid"):
            for index in range(6):
                rows.append(ScreeningTaskObservationV1(
                    blind_task_id=f"{route}-{index}", route_id=route,
                    motif=("fan_in_reconciliation", "cross_check_validation", "policy_application")[index // 2],
                    replicate_id="a" if index % 2 == 0 else "b",
                    infrastructure_complete=not (route == "skill_guided_llm" and index == 0),
                    offline_validity_pass=True, exact_valid_delivery=True,
                    major_defect=False, professional_plausibility_pass=True,
                    productive_complexity_pass=True, skill_causal_pass=True,
                    effective_rubric_dimensions=7, weighted_score=0.8,
                ))
        self.assertEqual(MatchedScreeningAnalyzer().analyze("campaign", rows).decision, "incomplete")

    def _grader_fixture(self, root: Path):
        from openpyxl import Workbook

        output = root / "output"
        delivery = output / "solver" / "blind" / "run_blind" / "deliverable_files" / "result.xlsx"
        delivery.parent.mkdir(parents=True)
        workbook = Workbook()
        workbook.active["A1"] = "evidence"
        workbook.save(delivery)
        candidate = root / "candidate"
        candidate.mkdir()
        (candidate / "dataset_row.json").write_text(
            json.dumps({"prompt": "Prepare the governed workpaper."}), encoding="utf-8"
        )
        teacher = root / "teacher_package" / "teacher"
        teacher.mkdir(parents=True)
        (teacher / "rubric_plan_v2.json").write_text(json.dumps({"criteria": []}), encoding="utf-8")
        (teacher / "deterministic_fact_anchors.json").write_text(json.dumps({"anchors": []}), encoding="utf-8")
        record = MatchedBusinessTaskRecordV1(
            blind_task_id="blind", solver_status="succeeded", solver_attempt_count=1,
            command=["solver"], budget_path="budget.json",
            solver_input_root="input", solver_input_tree_sha256="a" * 64,
            delivery_valid=True,
            grader_status="pending",
        )
        manifest = MatchedBusinessExecutionManifestV1(
            campaign_id="campaign", authorization_request_sha256="a" * 64,
            authorization_receipt_sha256="b" * 64, status="running",
            records=[record] * 12, created_at="2026-07-21T00:00:00+00:00",
            updated_at="2026-07-21T00:00:00+00:00",
        )
        config = ProviderConfig(
            provider_name="deepseek", base_url="https://api.deepseek.com",
            api_key="not-used", model="deepseek-v4-pro", timeout_seconds=60,
        )
        return output, candidate, teacher.parent, record, manifest, config

    def test_grader_format_failure_gets_one_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._grader_fixture(Path(temporary))
            calls = []
            def grader(payload, system, feedback):
                calls.append(feedback)
                if len(calls) == 1:
                    raise ValueError("invalid JSON")
                return ScreeningGraderDraftV1(
                    blind_task_id="blind", criteria=self._grades(0.5),
                    major_defect=False, professional_plausibility="pass",
                    effective_rubric_dimensions=7,
                )
            MatchedBusinessGovernance(Path(temporary))._grade(
                fixture[3], fixture[0], fixture[1], fixture[2], fixture[5], grader, fixture[4]
            )
            self.assertEqual(len(calls), 2)
            self.assertEqual(fixture[3].grader_status, "completed")
            self.assertEqual(fixture[4].grader_provider_calls, 2)

    def test_single_case_dataset_requires_parent_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = root / "blind"
            case.mkdir()
            (case / "dataset_row.json").write_text(json.dumps({"task_id": "blind"}), encoding="utf-8")
            self.assertEqual(validate_single_case_dataset(root, "blind"), case)
            with self.assertRaises(ValueError):
                validate_single_case_dataset(case, "blind")

    def test_substantive_low_score_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._grader_fixture(Path(temporary))
            calls = []
            def grader(payload, system, feedback):
                calls.append(feedback)
                return ScreeningGraderDraftV1(
                    blind_task_id="blind", criteria=self._grades(0.0),
                    major_defect=True, major_defect_reason="Material evidence is absent.",
                    professional_plausibility="fail", effective_rubric_dimensions=2,
                )
            MatchedBusinessGovernance(Path(temporary))._grade(
                fixture[3], fixture[0], fixture[1], fixture[2], fixture[5], grader, fixture[4]
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(fixture[3].grader_status, "completed")


if __name__ == "__main__":
    unittest.main()
