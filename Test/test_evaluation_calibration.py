from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.task_generator.v3_evaluation_calibration import (
    EvaluationCalibrationCompiler,
    GraderScoreObservationV1,
    ProfessionalValidityReviewV1,
    SolverPanelMemberV1,
)


class EvaluationCalibrationTests(unittest.TestCase):
    def test_solver_panel_requires_distinct_preflight_passed_gradient(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            members = [
                self._member(root, "weak-model", "weak"),
                self._member(root, "medium-model", "medium"),
                self._member(root, "strong-model", "strong"),
            ]
            panel = EvaluationCalibrationCompiler().freeze_solver_panel(
                panel_id="panel",
                members=members,
            )
            self.assertEqual(panel.decision, "pass")
            self.assertFalse(panel.external_execution_authorized)

            failed = self._member(
                root, "failed-model", "strong", passing=False
            )
            blocked = EvaluationCalibrationCompiler().freeze_solver_panel(
                panel_id="blocked",
                members=[members[0], members[1], failed],
            )
            self.assertEqual(blocked.decision, "blocked")
            self.assertIn(
                "solver_preflight_not_pass:failed-model",
                blocked.blocking_reasons,
            )

    def test_solver_panel_blocks_mutated_preflight_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = self._member(root, "weak-model", "weak")
            Path(member.preflight_report_path).write_text(
                json.dumps(
                    {
                        "solver_model": "weak-model",
                        "environment_id": "changed-environment",
                        "status": "pass",
                        "eligible_for_business_eval": True,
                    }
                ),
                encoding="utf-8",
            )
            panel = EvaluationCalibrationCompiler().freeze_solver_panel(
                panel_id="panel",
                members=[
                    member,
                    self._member(root, "medium-model", "medium"),
                    self._member(root, "strong-model", "strong"),
                ],
            )
            self.assertEqual(panel.decision, "blocked")
            self.assertIn(
                "solver_preflight_evidence_mismatch:weak-model",
                panel.blocking_reasons,
            )

    def test_llm_proxy_cannot_issue_expert_pass_or_training_authority(self):
        with self.assertRaises(ValidationError):
            ProfessionalValidityReviewV1(
                blind_task_id="task",
                reviewer_type="llm_proxy",
                reviewer_id="proxy",
                generator_independent=True,
                decision="pass",
                evidence_paths=["review.json"],
                rationale="The proxy considers the work professionally plausible.",
            )
        with self.assertRaises(ValidationError):
            ProfessionalValidityReviewV1(
                blind_task_id="task",
                reviewer_type="llm_proxy",
                reviewer_id="proxy",
                generator_independent=True,
                decision="provisional",
                evidence_paths=["review.json"],
                rationale="The proxy considers the work professionally plausible.",
                training_admission_authority=True,
            )

    def test_stable_repeated_grading_passes_frozen_thresholds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations = []
            scores = {
                "task_1": {
                    "weak-model": [0.20, 0.22],
                    "medium-model": [0.55, 0.56],
                    "strong-model": [0.80, 0.81],
                },
                "task_2": {
                    "weak-model": [0.30, 0.31],
                    "medium-model": [0.60, 0.61],
                    "strong-model": [0.85, 0.86],
                },
            }
            for task_id, model_scores in scores.items():
                for model, repeats in model_scores.items():
                    for repeat, score in enumerate(repeats, start=1):
                        observations.append(
                            self._observation(
                                root,
                                task_id,
                                model,
                                repeat,
                                score,
                            )
                        )
            report = EvaluationCalibrationCompiler().analyze_grader_stability(
                observations=observations
            )
            self.assertEqual(report.decision, "pass")
            self.assertEqual(report.repeated_pair_count, 6)
            self.assertEqual(report.stable_pair_count, 6)
            self.assertEqual(report.grader_disagreement_rate, 0.0)
            self.assertEqual(report.score_saturation_rate, 0.0)
            self.assertEqual(report.informative_case_rate, 1.0)

    def test_invalid_delivery_never_enters_grader_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            observation = self._observation(
                Path(directory),
                "task",
                "model",
                1,
                0.5,
            )
            observation.valid_delivery = False
            report = EvaluationCalibrationCompiler().analyze_grader_stability(
                observations=[observation]
            )
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "grader_observation_contains_invalid_delivery",
                report.blocking_reasons,
            )

    def test_saturation_and_missing_repeats_are_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations = [
                self._observation(root, "task", "weak-model", 1, 0.96),
                self._observation(root, "task", "strong-model", 1, 0.99),
            ]
            report = EvaluationCalibrationCompiler().analyze_grader_stability(
                observations=observations
            )
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "grader_repeat_pairs_incomplete",
                report.blocking_reasons,
            )
            self.assertIn(
                "score_saturation_above_threshold",
                report.blocking_reasons,
            )

    def test_mutated_grader_output_is_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observation = self._observation(
                root, "task", "model", 1, 0.5
            )
            Path(observation.grader_output_path).write_text(
                "mutated", encoding="utf-8"
            )
            report = EvaluationCalibrationCompiler().analyze_grader_stability(
                observations=[observation]
            )
            self.assertEqual(report.decision, "blocked")
            self.assertTrue(
                any(
                    item.startswith("grader_output_sha256_mismatch:")
                    for item in report.blocking_reasons
                )
            )

    def _member(
        self,
        root: Path,
        model: str,
        stratum: str,
        *,
        passing: bool = True,
    ):
        preflight = {
            "solver_model": model,
            "environment_id": "fixed-environment",
            "status": "pass" if passing else "fail",
            "eligible_for_business_eval": passing,
        }
        preflight_path = root / f"{model}_preflight.json"
        preflight_path.write_text(json.dumps(preflight), encoding="utf-8")
        return SolverPanelMemberV1(
            solver_model=model,
            stratum=stratum,
            preflight_report_path=str(preflight_path),
            preflight_report=preflight,
            provider="fixture",
            maximum_cost_per_task_usd=1.0,
        )

    @staticmethod
    def _observation(
        root: Path,
        task_id: str,
        solver_model: str,
        repeat: int,
        score: float,
    ):
        output = root / f"{task_id}_{solver_model}_{repeat}.json"
        output.write_text(
            json.dumps({"score": score}),
            encoding="utf-8",
        )
        return GraderScoreObservationV1(
            blind_task_id=task_id,
            solver_model=solver_model,
            grader_model="grader",
            repeat_index=repeat,
            overall_score_ratio=score,
            dimension_score_ratios={
                "factual_accuracy": score,
                "professional_expression": max(0.0, score - 0.02),
            },
            valid_delivery=True,
            grader_output_path=str(output),
            grader_output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
