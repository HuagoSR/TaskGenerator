from __future__ import annotations

import unittest

from pydantic import ValidationError

from task_generator.evaluation.r10_gdpval_validation import (
    GDPvalAnonymousAssessmentV1,
    GDPvalItemAssessmentV1,
    GDPvalPairReviewV1,
    GDPvalRankingSnapshotV1,
    GDPvalRubricItemV1,
    GDPvalTaskBindingV1,
    balanced_order,
    bootstrap_model_order,
    normalize_pair_review,
    ordinal_direction_agreement,
    score_gdpval_bundle,
)


def binding() -> GDPvalTaskBindingV1:
    return GDPvalTaskBindingV1(
        task_id="task-1", sector="Government", occupation="Compliance Officers",
        split="development", prompt_sha256="a" * 64,
        reference_tree_sha256="b" * 64, gold_tree_sha256="c" * 64,
        reference_files=[], expected_deliverables=["report.docx"],
        rubric_items=[
            GDPvalRubricItemV1(rubric_item_id="r1", score=2, criterion="Contains required title"),
            GDPvalRubricItemV1(rubric_item_id="r2", score=1, criterion="Explains the decision clearly"),
        ],
    )


def bundle(slot: str, first: str, second: str) -> GDPvalAnonymousAssessmentV1:
    return GDPvalAnonymousAssessmentV1(slot=slot, assessments=[
        GDPvalItemAssessmentV1(rubric_item_id="r1", rating=first, evidence_paths=["x.docx"], rationale="Visible title evidence."),
        GDPvalItemAssessmentV1(rubric_item_id="r2", rating=second, evidence_paths=["x.docx"], rationale="Visible narrative evidence."),
    ])


class GDPvalValidationTests(unittest.TestCase):
    def test_binding_is_strict_and_human_authored(self):
        value = binding()
        self.assertEqual(value.canonical_sha256(), GDPvalTaskBindingV1.model_validate_json(value.model_dump_json()).canonical_sha256())
        with self.assertRaises(ValidationError):
            GDPvalTaskBindingV1.model_validate({**value.model_dump(), "extra": True})
        bad = value.model_dump()
        bad["rubric_items"][0]["author_type"] = "model"
        with self.assertRaises(ValidationError):
            GDPvalTaskBindingV1.model_validate(bad)

    def test_score_uses_human_item_weights(self):
        self.assertEqual(score_gdpval_bundle(binding(), bundle("slot_1", "met", "partial")), round(2.5 / 3, 6))
        with self.assertRaises(ValueError):
            score_gdpval_bundle(binding(), GDPvalAnonymousAssessmentV1(
                slot="slot_1", assessments=[bundle("slot_1", "met", "met").assessments[0]]
            ))

    def test_pair_normalization_and_balancing(self):
        review = GDPvalPairReviewV1(
            task_id="task-1", judge_id="gpt-5.6-terra@chatgpt_codex",
            pair_id="a_vs_b", order_id="b_a", preference="slot_1",
            bundles=[bundle("slot_1", "met", "met"), bundle("slot_2", "partial", "not_met")],
        )
        normalized = normalize_pair_review(review)
        self.assertEqual(normalized["preference"], "candidate_b")
        self.assertEqual(balanced_order(task_id="x", pair_id="y", seed=5), balanced_order(task_id="x", pair_id="y", seed=5))

    def test_snapshot_and_ordinal_direction(self):
        snapshot = GDPvalRankingSnapshotV1(
            source_url="https://example.test", captured_at="2026-09-03T00:00:00Z",
            scores={
                "gpt-5.6-sol@chatgpt_codex": 1379,
                "deepseek-v4-pro@official_opencode": 1306,
                "deepseek-v4-flash@official_opencode": 1153,
            },
            reference_order=[
                "gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode",
                "deepseek-v4-flash@official_opencode",
            ],
        )
        self.assertEqual(ordinal_direction_agreement(snapshot.reference_order, snapshot.reference_order)["rate"], 1.0)

    def test_bootstrap_model_order(self):
        rows = [
            {"task_id": "t1", "candidate_a": "a", "candidate_b": "b", "preference": "a"},
            {"task_id": "t2", "candidate_a": "a", "candidate_b": "b", "preference": "a"},
        ]
        result = bootstrap_model_order(rows, models=["a", "b"], seed=7, samples=100)
        self.assertEqual(result["observed_order"], ["a", "b"])
        self.assertEqual(result["wins"]["a"], 2)


if __name__ == "__main__":
    unittest.main()
