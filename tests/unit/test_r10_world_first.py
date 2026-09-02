from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from pydantic import ValidationError

from task_generator.planning.scenario_task_compiler import (
    TaskSpecificRubricCriterionV1,
    TaskSpecificRubricV1,
)
from task_generator.production.r10_world_first import (
    PairedDecisionAssessmentV1,
    PairedJudgeReviewV1,
    ProfessionDifficultyMutationV1,
    ProfessionDifficultyPlanV1,
    WorldFirstCaseStateV1,
    WorldFirstPilotManifestV1,
    advance_world_first_case,
    judge_calibration_errors,
    paired_task_discrimination,
    world_first_pilot_decision,
    recompute_paired_review,
    resumable_case_ids,
    validate_world_candidate_tree,
    write_manifest,
)


SHA = "a" * 64
COMMIT = "b" * 40


def paired_review(*, preference: str, judge: str = "gpt-5.6-sol@chatgpt_codex") -> PairedJudgeReviewV1:
    return PairedJudgeReviewV1(
        task_id="task", judge_id=judge, preference=preference,
        assessments=[
            PairedDecisionAssessmentV1(
                decision_id=decision, bundle_1_rating="met", bundle_2_rating="partial",
                bundle_1_major_error=False, bundle_2_major_error=False,
                bundle_1_evidence_paths=["one.xlsx"], bundle_2_evidence_paths=["two.xlsx"],
                rationale="The anonymous work products differ in visible decision coverage and support.",
            ) for decision in ("d1", "d2", "d3")
        ],
        bundle_1_weighted_score=0.9, bundle_2_weighted_score=0.7,
        bundle_1_major_defect=False, bundle_2_major_defect=False,
    )


def cases() -> list[WorldFirstCaseStateV1]:
    return [
        WorldFirstCaseStateV1(case_id="audit_base", pair_id="audit_pair", domain="audit_compliance", variant="baseline", deliverable_format="xlsx", seed_sha256=SHA, rules_sha256=SHA),
        WorldFirstCaseStateV1(case_id="audit_hard", pair_id="audit_pair", domain="audit_compliance", variant="adversarial", deliverable_format="xlsx", seed_sha256=SHA, rules_sha256=SHA),
        WorldFirstCaseStateV1(case_id="proc_base", pair_id="proc_pair", domain="procurement_operations", variant="baseline", deliverable_format="docx", seed_sha256=SHA, rules_sha256=SHA),
        WorldFirstCaseStateV1(case_id="proc_hard", pair_id="proc_pair", domain="procurement_operations", variant="adversarial", deliverable_format="docx", seed_sha256=SHA, rules_sha256=SHA),
    ]


def manifest() -> WorldFirstPilotManifestV1:
    return WorldFirstPilotManifestV1(campaign_id="r10_9_test", source_commit=COMMIT, image="eval:test", image_sha256=SHA, cases=cases())


class WorldFirstContractsTest(unittest.TestCase):
    def test_manifest_requires_two_complete_matched_pairs(self) -> None:
        value = cases()
        value[-1] = value[-1].model_copy(update={"variant": "baseline"})
        with self.assertRaises(ValidationError):
            WorldFirstPilotManifestV1(campaign_id="x", source_commit=COMMIT, image="eval:test", image_sha256=SHA, cases=value)

    def test_difficulty_plan_closes_selected_mutations_and_sources(self) -> None:
        mutation = ProfessionDifficultyMutationV1(
            mutation_id="cross_system_timing", professional_cause="The two operational systems close at different controlled times.",
            business_event="A late approved transaction reaches only one reporting extract before close.",
            candidate_evidence_effect="Visible extracts contain a plausible timing difference that requires provenance analysis.",
            targeted_shortcut="Treating a numerical tie as proof of completeness.", source_ids=["src_a"],
            fairness_rationale="The timestamps and extraction notes are visible in ordinary business records.",
            solvability_rationale="A worker can identify the limitation and request the exact resolving evidence.",
        )
        plan = ProfessionDifficultyPlanV1(domain="audit_compliance", seed_id="seed", skill_id="skill", available_source_ids=["src_a"], mutations=[mutation], selected_mutation_ids=[mutation.mutation_id])
        self.assertEqual(plan.selected_mutation_ids, ["cross_system_timing"])
        with self.assertRaises(ValidationError):
            plan.model_copy(update={"selected_mutation_ids": ["unknown"]}).__class__.model_validate({**plan.model_dump(), "selected_mutation_ids": ["unknown"]})

    def test_only_not_started_cases_are_resumable_and_terminal_cannot_revive(self) -> None:
        current = manifest()
        advanced = advance_world_first_case(current, case_id="audit_base", stage="world_frozen", world_tree_sha256=SHA, candidate_tree_sha256=SHA)
        self.assertNotIn("audit_base", resumable_case_ids(advanced))
        with self.assertRaises(ValueError):
            advance_world_first_case(advanced, case_id="audit_base", stage="skill_deliberated")
        blocked = advance_world_first_case(current, case_id="audit_base", stage="blocked", first_failure="task_not_natural")
        with self.assertRaises(ValueError):
            advance_world_first_case(blocked, case_id="audit_base", stage="world_frozen", world_tree_sha256=SHA, candidate_tree_sha256=SHA)

    def test_manifest_atomic_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            write_manifest(path, manifest())
            loaded = WorldFirstPilotManifestV1.model_validate_json(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded.canonical_sha256(), manifest().canonical_sha256())

    def test_paired_review_scores_are_program_recomputed(self) -> None:
        rubric = TaskSpecificRubricV1(criteria=[
            TaskSpecificRubricCriterionV1(criterion_id="c1", decision_id="d1", weight=0.4, description="Met: yes Partial: some Not met: no"),
            TaskSpecificRubricCriterionV1(criterion_id="c2", decision_id="d2", weight=0.3, description="Met: yes Partial: some Not met: no"),
            TaskSpecificRubricCriterionV1(criterion_id="c3", decision_id="d3", weight=0.3, description="Met: yes Partial: some Not met: no"),
        ])
        assessments = [
            PairedDecisionAssessmentV1(decision_id=decision, bundle_1_rating="met", bundle_2_rating="not_met" if decision == "d1" else "partial", bundle_1_major_error=False, bundle_2_major_error=decision == "d1", bundle_1_evidence_paths=["good.xlsx"], bundle_2_evidence_paths=["weak.xlsx"], rationale="The visible work products support different levels of professional coverage." )
            for decision in ("d1", "d2", "d3")
        ]
        draft = PairedJudgeReviewV1(task_id="task", judge_id="gpt-5.6-sol@chatgpt_codex", preference="bundle_1", assessments=assessments, bundle_1_weighted_score=0, bundle_2_weighted_score=1, bundle_1_major_defect=True, bundle_2_major_defect=False)
        scored = recompute_paired_review(draft, rubric=rubric)
        self.assertEqual(scored.bundle_1_weighted_score, 1.0)
        self.assertEqual(scored.bundle_2_weighted_score, 0.3)
        self.assertFalse(scored.bundle_1_major_defect)
        self.assertTrue(scored.bundle_2_major_defect)

    def test_candidate_tree_checks_transport_not_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "note.txt").write_text("Routine receiving note", encoding="utf-8")
            with zipfile.ZipFile(root / "records.xlsx", "w") as archive:
                archive.writestr("xl/workbook.xml", "<workbook/>")
            self.assertEqual(validate_world_candidate_tree(root), [])
            (root / "leak.txt").write_text("Questionable record", encoding="utf-8")
            self.assertIn("candidate_answer_leakage:leak.txt", validate_world_candidate_tree(root))

    def test_calibration_requires_monotonic_controls(self) -> None:
        def tiers() -> dict:
            return {
                "reference_quality": {"weighted_score": 0.95, "major_defect": False, "assessments": [{"decision_id": "d1"}]},
                "plausible_incomplete": {"weighted_score": 0.70, "major_defect": False, "assessments": [{"decision_id": "d1"}]},
                "shortcut_critical_error": {"weighted_score": 0.35, "major_defect": True, "assessments": [{"decision_id": "d1"}]},
            }
        reviews = [{"judge_id": "gpt", "tiers": tiers()}, {"judge_id": "deepseek", "tiers": tiers()}]
        self.assertEqual(judge_calibration_errors(reviews, decision_ids={"d1"}), [])
        reviews[1]["tiers"]["shortcut_critical_error"]["major_defect"] = False
        self.assertIn("calibration_shortcut_major_not_detected:deepseek", judge_calibration_errors(reviews, decision_ids={"d1"}))

    def test_paired_discrimination_rejects_judge_ambiguity(self) -> None:
        first = paired_review(preference="bundle_1")
        second = paired_review(preference="bundle_2", judge="deepseek-v4-pro@official_opencode")
        result = paired_task_discrimination([first, second], bundle_1_solver="gpt", bundle_2_solver="deepseek")
        self.assertEqual(result["classification"], "judge_ambiguous")

    def test_pilot_decision_prioritizes_evaluator_ambiguity(self) -> None:
        results = {
            "audit_base": {"classification": "judge_ambiguous"},
            "audit_hard": {"classification": "cleanly_discriminative"},
            "proc_base": {"classification": "near_tie", "absolute_gap": 0.01},
            "proc_hard": {
                "classification": "cleanly_discriminative",
                "absolute_gap": 0.10,
                "bundle_1_composite": 0.8,
                "bundle_2_composite": 0.7,
                "major_defect_pair": [False, False],
            },
        }
        decision = world_first_pilot_decision(
            results,
            domain_pairs={
                "audit_compliance": ("audit_base", "audit_hard"),
                "procurement_operations": ("proc_base", "proc_hard"),
            },
            targeted_shortcuts={"audit_compliance": [], "procurement_operations": []},
        )
        self.assertEqual(decision, "evaluator_revision_required")


if __name__ == "__main__":
    unittest.main()
