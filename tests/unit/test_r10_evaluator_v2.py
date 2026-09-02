from __future__ import annotations

import unittest

from pydantic import ValidationError

from task_generator.evaluation.r10_evaluator_v2 import (
    AnonymousBundleAssessmentV2,
    AtomicAssessmentV2,
    AtomicCriterionV2,
    CalibrationSplitV1,
    CounterbalancedPairReviewV2,
    DeterministicCheckV2,
    EvaluatorProfileV2,
    MajorErrorRuleV2,
    RatingAnchorsV2,
    SolverStackConfigV1,
    assess_counterbalance_stability,
    bootstrap_mean_interval,
    confirm_major_errors,
    evaluate_deterministic_checks,
    luna_solver_required,
    normalize_pair_review,
    ordinal_agreement,
    profile_from_frozen_supervision,
    score_bundle,
)
from task_generator.core.scenario_first import CandidateEvidenceRefV1, DecisionPointV1, TaskDecisionMatrixV1
from task_generator.planning.scenario_task_compiler import TaskSpecificRubricCriterionV1, TaskSpecificRubricV1


SHA = "a" * 64


def anchors() -> RatingAnchorsV2:
    return RatingAnchorsV2(
        met="Correctly states and supports the required conclusion.",
        partial="States a qualified conclusion with incomplete visible support.",
        not_met="Omits the conclusion or contradicts the visible evidence.",
    )


def profile() -> EvaluatorProfileV2:
    return EvaluatorProfileV2(
        profile_id="audit_profile_v2_0", task_id="task_a",
        source_task_tree_sha256=SHA, source_teacher_tree_sha256=SHA, iteration="v2.0",
        criteria=[
            AtomicCriterionV2(
                criterion_id="amount_accuracy", parent_decision_id="d1",
                kind="objective_fact", weight=0.4,
                requirement="Report the computed exception rate accurately.",
                anchors=anchors(), deterministic_check_ids=["rate_check"],
            ),
            AtomicCriterionV2(
                criterion_id="evidence_weighting", parent_decision_id="d1",
                kind="professional_judgment", weight=0.4,
                requirement="Weigh conflicting evidence and bound the conclusion.", anchors=anchors(),
            ),
            AtomicCriterionV2(
                criterion_id="audience_usability", parent_decision_id="d2",
                kind="deliverable_quality", weight=0.2,
                requirement="Present a review-ready work product for the named audience.", anchors=anchors(),
            ),
        ],
        deterministic_checks=[
            DeterministicCheckV2(
                check_id="rate_check", criterion_id="amount_accuracy",
                operation="within_tolerance", expected_number=0.075, tolerance=0.0001,
            )
        ],
        major_error_rules=[
            MajorErrorRuleV2(
                error_id="wrong_rate_conclusion", affected_criterion_ids=["amount_accuracy"],
                trigger_fact="The delivered exception rate is outside the accepted tolerance.",
                necessary_evidence=["The tested population and exception count are visible."],
                business_consequence="The reviewer could accept a population that exceeds policy tolerance.",
                deterministic_check_ids=["rate_check"],
            )
        ],
    )


def bundle(slot: str, *, alleged: list[str] | None = None) -> AnonymousBundleAssessmentV2:
    return AnonymousBundleAssessmentV2(
        slot=slot,
        assessments=[
            AtomicAssessmentV2(
                criterion_id=criterion, rating="met", evidence_paths=["workpaper.xlsx"],
                rationale="The work product visibly states and supports this required element.",
            )
            for criterion in ("amount_accuracy", "evidence_weighting", "audience_usability")
        ],
        alleged_major_error_ids=alleged or [],
    )


def review(judge: str, order: str, preference: str, *, a_major: bool = False) -> CounterbalancedPairReviewV2:
    # a_major is mapped to the presentation slot containing candidate A.
    major_1 = a_major if order == "a_b" else False
    major_2 = a_major if order == "b_a" else False
    return CounterbalancedPairReviewV2(
        task_id="task_a", judge_id=judge, order_id=order, preference=preference,
        bundles=[
            bundle("slot_1", alleged=["wrong_rate_conclusion"] if major_1 else []),
            bundle("slot_2", alleged=["wrong_rate_conclusion"] if major_2 else []),
        ],
    )


class EvaluatorV2Tests(unittest.TestCase):
    def test_profile_is_strict_closed_and_stably_hashable(self) -> None:
        value = profile()
        self.assertEqual(value.canonical_sha256(), EvaluatorProfileV2.model_validate_json(value.model_dump_json()).canonical_sha256())
        with self.assertRaises(ValidationError):
            EvaluatorProfileV2.model_validate({**value.model_dump(), "unexpected": True})
        with self.assertRaises(ValidationError):
            EvaluatorProfileV2.model_validate({**value.model_dump(), "criteria": [
                {**item.model_dump(), "weight": 0.1} for item in value.criteria
            ]})

    def test_objective_checks_override_llm_rating(self) -> None:
        value = profile()
        observations = {"rate_check": 0.05}
        checks = evaluate_deterministic_checks(value.deterministic_checks, observations)
        self.assertFalse(checks[0].passed)
        self.assertEqual(score_bundle(profile=value, bundle=bundle("slot_1"), deterministic_results=checks), 0.6)

    def test_frozen_wide_decision_is_atomized_without_mutating_source(self) -> None:
        matrix = TaskDecisionMatrixV1(
            scenario_id="scenario", decision_points=[
                DecisionPointV1(
                    decision_id=f"D{index} Conclusion", question="What conclusion is supported?",
                    evidence_refs=[CandidateEvidenceRefV1(artifact_id="record.xlsx", record_id="Sheet1", field_names=["Amount"])],
                    rule_ids=["rule"], skill_ids=["skill"], acceptable_conclusions=["Qualified conclusion"],
                    major_errors=["Concluding that no exception exists despite the visible conflict."],
                    allowed_uncertainty_conclusions=["Evidence remains incomplete."],
                    required_follow_up_actions=["Obtain the missing controlled record."],
                )
                for index in range(1, 4)
            ],
        )
        rubric = TaskSpecificRubricV1(criteria=[
            TaskSpecificRubricCriterionV1(
                criterion_id=f"C{index}", decision_id=f"D{index} Conclusion", weight=weight,
                description="Met: complete. Partial: incomplete. Not met: wrong.",
            )
            for index, weight in enumerate((0.4, 0.3, 0.3), start=1)
        ])
        value = profile_from_frozen_supervision(
            task_id="task", task_tree_sha256=SHA, teacher_tree_sha256=SHA,
            matrix=matrix, rubric=rubric,
        )
        self.assertEqual(len(value.criteria), 9)
        self.assertEqual({item.kind for item in value.criteria}, {"objective_fact", "professional_judgment"})
        self.assertEqual(len(value.major_error_rules), 3)
        self.assertEqual(rubric.criteria[0].weight, 0.4)

    def test_percentage_anchor_regression(self) -> None:
        value = profile()
        passing = evaluate_deterministic_checks(value.deterministic_checks, {"rate_check": 3 / 40})
        self.assertTrue(passing[0].passed)
        failing = evaluate_deterministic_checks(value.deterministic_checks, {"rate_check": 0.05})
        self.assertFalse(failing[0].passed)

    def test_counterbalanced_review_normalizes_presentation_order(self) -> None:
        first = review("gpt-5.6-terra@chatgpt_codex", "a_b", "slot_1")
        reverse = review("gpt-5.6-terra@chatgpt_codex", "b_a", "slot_2")
        self.assertEqual(normalize_pair_review(first)["preference"], "candidate_a")
        self.assertEqual(normalize_pair_review(reverse)["preference"], "candidate_a")
        stability = assess_counterbalance_stability([first, reverse])
        self.assertTrue(stability["stable"])

    def test_position_effect_is_reported_not_tiebroken(self) -> None:
        first = review("gpt-5.6-terra@chatgpt_codex", "a_b", "slot_1")
        reverse = review("gpt-5.6-terra@chatgpt_codex", "b_a", "slot_1")
        self.assertFalse(assess_counterbalance_stability([first, reverse])["stable"])

    def test_major_requires_deterministic_hit_or_judge_majority(self) -> None:
        value = profile()
        gpt = review("gpt-5.6-terra@chatgpt_codex", "a_b", "slot_1", a_major=True)
        gpt_reverse = review("gpt-5.6-terra@chatgpt_codex", "b_a", "slot_2", a_major=True)
        one_judge = confirm_major_errors(
            profile=value, reviews=[gpt, gpt_reverse],
            deterministic_results_by_candidate={"candidate_a": [], "candidate_b": []},
        )
        # With one distinct Judge, that Judge is the majority.
        self.assertEqual(one_judge["candidate_a"], ["wrong_rate_conclusion"])
        clean_ds = review("deepseek-v4-pro@official_opencode", "a_b", "slot_1")
        split = confirm_major_errors(
            profile=value, reviews=[gpt, gpt_reverse, clean_ds],
            deterministic_results_by_candidate={"candidate_a": [], "candidate_b": []},
        )
        self.assertEqual(split["candidate_a"], [])
        deterministic = confirm_major_errors(
            profile=value, reviews=[clean_ds],
            deterministic_results_by_candidate={
                "candidate_a": evaluate_deterministic_checks(value.deterministic_checks, {"rate_check": 0.05}),
                "candidate_b": [],
            },
        )
        self.assertEqual(deterministic["candidate_a"], ["wrong_rate_conclusion"])

    def test_frozen_solver_reasoning_matrix(self) -> None:
        configs = [
            ("gpt-5.6-sol@chatgpt_codex", "gpt-5.6-sol", "chatgpt_codex", "none"),
            ("deepseek-v4-pro@official_opencode", "deepseek-v4-pro", "official_opencode", "max"),
            ("deepseek-v4-flash@official_opencode", "deepseek-v4-flash", "official_opencode", "high"),
            ("gpt-5.6-luna@chatgpt_codex", "gpt-5.6-luna", "chatgpt_codex", "medium"),
        ]
        for solver_id, model, transport, reasoning in configs:
            SolverStackConfigV1(solver_id=solver_id, model=model, transport=transport, reasoning=reasoning)
        with self.assertRaises(ValidationError):
            SolverStackConfigV1(
                solver_id="gpt-5.6-sol@chatgpt_codex", model="gpt-5.6-sol",
                transport="chatgpt_codex", reasoning="high",
            )

    def test_split_is_disjoint_and_holdout_explicit(self) -> None:
        value = CalibrationSplitV1(
            r10_development_task_ids=["audit_base", "proc_base"],
            r10_holdout_task_ids=["audit_hard", "proc_hard"],
            gdpval_development_task_ids=[f"dev_{i}" for i in range(6)],
            gdpval_holdout_task_ids=[f"hold_{i}" for i in range(6)],
        )
        self.assertFalse(value.holdout_opened)
        with self.assertRaises(ValidationError):
            CalibrationSplitV1.model_validate({
                **value.model_dump(),
                "r10_holdout_task_ids": ["audit_base", "proc_hard"],
            })

    def test_luna_trigger_is_whole_campaign_only(self) -> None:
        complete = {
            "gpt-5.6-sol@chatgpt_codex": 12,
            "deepseek-v4-pro@official_opencode": 12,
            "deepseek-v4-flash@official_opencode": 12,
        }
        self.assertFalse(luna_solver_required(main_solver_completed=complete, pro_flash_indistinguishable=False, ranked_main_models=3))
        self.assertTrue(luna_solver_required(main_solver_completed={**complete, "deepseek-v4-flash@official_opencode": 9}, pro_flash_indistinguishable=False, ranked_main_models=3))

    def test_bootstrap_and_ordinal_direction_are_deterministic(self) -> None:
        self.assertEqual(bootstrap_mean_interval([1.0, 0.0, 1.0], seed=7), bootstrap_mean_interval([1.0, 0.0, 1.0], seed=7))
        result = ordinal_agreement({"sol": 8, "pro": 5, "flash": 2}, ["sol", "pro", "flash"])
        self.assertEqual(result["agreement"], 1.0)


if __name__ == "__main__":
    unittest.main()
