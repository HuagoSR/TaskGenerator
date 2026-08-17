from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignFrontend,
    TaskDesignProposalV1,
)
from src.task_generator.v3_validity_utility import (
    RealityCaseReviewV1,
    RealityCohortReviewV1,
    RealityDimensionReviewV1,
    ValidityUtilityCompiler,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
)


class ValidityUtilityCompilerTests(unittest.TestCase):
    def test_reality_cohort_requires_six_independently_passing_cases(self):
        dimensions = [
            "role_realism",
            "information_sufficiency",
            "natural_difficulty",
            "professional_judgment",
            "deliverable_realism",
            "rubric_focus",
        ]
        cases = [
            RealityCaseReviewV1(
                case_id=f"reality_{index}",
                motif="cross_check" if index < 3 else "policy_application",
                reviewer_id=f"reviewer_{index}",
                reviewer_independent_from_generator=True,
                dimensions=[
                    RealityDimensionReviewV1(
                        dimension=dimension,
                        decision="pass",
                        evidence_paths=[f"reviews/reality_{index}.md"],
                        rationale="Independent review found the task credible and usable.",
                    )
                    for dimension in dimensions
                ],
                overall_decision="pass",
            )
            for index in range(6)
        ]
        cohort = RealityCohortReviewV1(
            cohort_id="reality_gold_v1",
            cases=cases,
            decision="pass",
            protocol_merge_eligible=True,
        )
        self.assertTrue(cohort.protocol_merge_eligible)
        self.assertFalse(cohort.training_admission_authorized)

    def test_reality_case_cannot_self_certify_a_pass(self):
        dimensions = [
            RealityDimensionReviewV1(
                dimension=dimension,
                decision="pass",
                rationale="The reviewed dimension has sufficient independent evidence.",
            )
            for dimension in (
                "role_realism",
                "information_sufficiency",
                "natural_difficulty",
                "professional_judgment",
                "deliverable_realism",
                "rubric_focus",
            )
        ]
        with self.assertRaisesRegex(ValueError, "independent_reviewer"):
            RealityCaseReviewV1(
                case_id="self_reviewed",
                motif="cross_check",
                reviewer_id="generator",
                reviewer_independent_from_generator=False,
                dimensions=dimensions,
                overall_decision="pass",
            )

    def test_compiles_separate_validity_utility_and_rubric_axes(self):
        brief, proposal = self._fixture()
        validation = TaskDesignFrontend().validate_proposal(brief, proposal)
        bundle = ValidityUtilityCompiler().compile(
            brief=brief,
            proposal=proposal,
            proposal_validation=validation,
            deterministic_fact_anchors=self._anchors(),
            deliverable_contract_valid=True,
            evidence_paths={
                "proposal": "governance/task_design_proposal.json",
                "proposal_validation": "governance/task_design_validation_report.json",
                "fact_anchors": "teacher/deterministic_fact_anchors.json",
                "deliverable_contract_validation": (
                    "governance/deliverable_contract_validation_report.json"
                ),
            },
        )
        validity = {
            item.dimension: item for item in bundle.validity_vector.dimensions
        }
        self.assertEqual(validity["factual_validity"].status, "provisional")
        self.assertEqual(validity["semantic_validity"].status, "provisional")
        self.assertEqual(validity["behavioral_validity"].status, "not_evaluated")
        self.assertEqual(validity["professional_validity"].status, "not_evaluated")
        self.assertFalse(bundle.validity_vector.training_admission_eligible)

        self.assertEqual(bundle.utility_profile.profile_status, "provisional")
        self.assertEqual(bundle.utility_profile.productive_complexity_coverage, 1.0)
        self.assertEqual(bundle.utility_profile.skill_causal_coverage, 1.0)
        self.assertTrue(
            all(
                item.contribution_status == "causal"
                for item in bundle.utility_profile.skill_contributions
            )
        )

        rubric = bundle.rubric_plan
        self.assertEqual(rubric.decision, "pass")
        self.assertEqual(rubric.total_weight, 1.0)
        self.assertEqual(rubric.factual_weight_ratio, 0.2)
        self.assertEqual(rubric.effective_dimension_count, 7)
        self.assertFalse(rubric.duplicate_fact_anchor_assignments)
        self.assertFalse(rubric.duplicate_failure_signals)
        self.assertTrue(
            all(
                [band.score_ratio for band in criterion.partial_score_bands]
                == [0.0, 0.5, 1.0]
                for criterion in rubric.criteria
            )
        )
        self.assertEqual(bundle.offline_decision, "pass")
        self.assertFalse(bundle.promotion_authorized)
        self.assertFalse(bundle.training_admission_authorized)

    def test_hidden_truth_blocks_validity_and_accidental_difficulty(self):
        brief, proposal = self._fixture()
        validation = TaskDesignFrontend().validate_proposal(brief, proposal)
        anchors = self._anchors()
        anchors["all_inputs_candidate_visible"] = False
        bundle = ValidityUtilityCompiler().compile(
            brief=brief,
            proposal=proposal,
            proposal_validation=validation,
            deterministic_fact_anchors=anchors,
            deliverable_contract_valid=True,
        )
        factual = next(
            item
            for item in bundle.validity_vector.dimensions
            if item.dimension == "factual_validity"
        )
        hidden = next(
            item
            for item in bundle.utility_profile.accidental_difficulty_findings
            if item.finding_code == "hidden_primary_truth"
        )
        self.assertEqual(factual.status, "blocked")
        self.assertEqual(hidden.status, "blocked")
        self.assertEqual(bundle.offline_decision, "blocked")

    def test_ablation_marks_fully_redundant_skill_as_decorative(self):
        brief, proposal = self._fixture()
        proposal_payload = proposal.model_dump(mode="json")
        proposal_payload["skill_bindings"][1]["bound_element_ids"] = list(
            proposal_payload["skill_bindings"][0]["bound_element_ids"]
        )
        brief_payload = brief.model_dump(mode="json")
        brief_payload["selected_skills"][1]["required_capability_ids"] = list(
            brief_payload["selected_skills"][0]["required_capability_ids"]
        )
        duplicate_brief = CapabilityBriefV1.model_validate(brief_payload)
        duplicate_proposal = TaskDesignProposalV1.model_validate(proposal_payload)
        validation = TaskDesignFrontend().validate_proposal(
            duplicate_brief,
            duplicate_proposal,
        )
        bundle = ValidityUtilityCompiler().compile(
            brief=duplicate_brief,
            proposal=duplicate_proposal,
            proposal_validation=validation,
            deterministic_fact_anchors=self._anchors(),
            deliverable_contract_valid=True,
        )
        self.assertTrue(
            any(
                item.contribution_status == "decorative"
                for item in bundle.utility_profile.skill_contributions
            )
        )
        self.assertEqual(bundle.utility_profile.profile_status, "blocked")

    def _fixture(self):
        brief = CapabilityBriefV1.model_validate(
            json.loads(
                (FIXTURE_ROOT / "capability_brief.json").read_text(encoding="utf-8")
            )
        )
        proposal = TaskDesignProposalV1.model_validate(
            json.loads(
                (FIXTURE_ROOT / "valid_proposal.json").read_text(encoding="utf-8")
            )
        )
        return brief, proposal

    @staticmethod
    def _anchors():
        return {
            "all_inputs_candidate_visible": True,
            "anchors": [
                {
                    "anchor_id": "anchor_row_count",
                    "candidate_visible_inputs": ["reference_files/input.xlsx"],
                },
                {
                    "anchor_id": "anchor_crosscheck",
                    "candidate_visible_inputs": [
                        "reference_files/input.xlsx",
                        "reference_files/detail.xlsx",
                    ],
                },
            ],
        }


if __name__ == "__main__":
    unittest.main()
