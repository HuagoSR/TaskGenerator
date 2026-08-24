from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from task_generator.evaluation.model_comparison import (
    JudgeScoreV1,
    ModelTaskEvaluationV1,
    aggregate_production_model_comparison,
)
from task_generator.production.campaign import (
    ProductionBriefRecordV1,
    ProductionSourceRecordV1,
    ProductionTaskCohortV1,
)


class HuagoConeProductionContractTests(unittest.TestCase):
    def _sources(self):
        values = []
        for index in range(6):
            audit = index < 3
            values.append(
                ProductionSourceRecordV1(
                    source_id=f"source_{index}",
                    domain="audit_compliance" if audit else "procurement_operations",
                    canonical_url=(
                        f"https://pcaobus.org/source-{index}"
                        if audit
                        else f"https://www.acquisition.gov/source-{index}"
                    ),
                    allowed_host="pcaobus.org" if audit else "www.acquisition.gov",
                    collected_path=f"/tmp/source-{index}",
                    content_sha256=f"{index + 1:064x}",
                    collected_at="2026-08-17T00:00:00Z",
                )
            )
        return values

    def _briefs(self):
        motifs = [
            "cross_check_validation",
            "cross_check_validation",
            "fan_in_reconciliation",
            "policy_application",
            "policy_application",
            "cross_check_validation",
            "cross_check_validation",
            "fan_in_reconciliation",
            "fan_in_reconciliation",
            "policy_application",
        ]
        values = []
        for index, motif in enumerate(motifs):
            domain = "audit_compliance" if index < 5 else "procurement_operations"
            source_offset = 0 if index < 5 else 3
            values.append(
                ProductionBriefRecordV1(
                    brief_id=f"brief_{index}",
                    blind_task_id=f"task_{index}",
                    domain=domain,
                    motif=motif,
                    brief_path=f"/tmp/brief-{index}.json",
                    brief_sha256=f"{index + 20:064x}",
                    source_ids=[f"source_{source_offset}", f"source_{source_offset + 1}"],
                )
            )
        return values

    def test_fixed_ten_task_shape_passes(self):
        value = ProductionTaskCohortV1(
            campaign_id="r9", sources=self._sources(), briefs=self._briefs()
        )
        self.assertEqual(len(value.briefs), 10)
        self.assertEqual(value.professional_validity, "assumed_for_model_comparison")
        self.assertFalse(value.training_authorized)

    def test_wrong_motif_distribution_fails(self):
        briefs = self._briefs()
        briefs[0] = briefs[0].model_copy(update={"motif": "fan_in_reconciliation"})
        with self.assertRaises(ValidationError):
            ProductionTaskCohortV1(campaign_id="r9", sources=self._sources(), briefs=briefs)

    def test_unknown_source_fails(self):
        briefs = self._briefs()
        briefs[0] = briefs[0].model_copy(update={"source_ids": ["unknown"]})
        with self.assertRaises(ValidationError):
            ProductionTaskCohortV1(campaign_id="r9", sources=self._sources(), briefs=briefs)

    def test_three_model_dual_judge_complete_and_discriminative(self):
        solvers = [
            "gpt-5.6-sol@chatgpt_codex",
            "deepseek-v4-pro@official_opencode",
            "gemini-3.1-pro-preview@tuzi_opencode",
        ]
        records = []
        for task in range(10):
            for solver_index, solver in enumerate(solvers):
                score = 0.9 - solver_index * 0.12
                records.append(
                    ModelTaskEvaluationV1(
                        task_id=f"task_{task}",
                        solver_id=solver,
                        delivery_valid=True,
                        judges=[
                            JudgeScoreV1(
                                judge_id="gpt-5.6-sol@chatgpt_codex",
                                valid=True,
                                weighted_score=score,
                                major_defect=False,
                            ),
                            JudgeScoreV1(
                                judge_id="deepseek-v4-pro@official_opencode",
                                valid=True,
                                weighted_score=score - 0.02,
                                major_defect=False,
                            ),
                        ],
                    )
                )
        result = aggregate_production_model_comparison(records)
        self.assertEqual(result.decision, "comparison_complete")
        self.assertEqual(result.common_task_count, 10)
        self.assertEqual(result.discrimination_decision, "usefully_discriminative")

    def test_partial_requires_two_models_and_eight_common_tasks(self):
        records = []
        for task in range(8):
            for solver in (
                "gpt-5.6-sol@chatgpt_codex",
                "deepseek-v4-pro@official_opencode",
            ):
                records.append(
                    ModelTaskEvaluationV1(
                        task_id=f"task_{task}",
                        solver_id=solver,
                        delivery_valid=True,
                        judges=[
                            JudgeScoreV1(judge_id="gpt-5.6-sol@chatgpt_codex", valid=True, weighted_score=0.8, major_defect=False),
                            JudgeScoreV1(judge_id="deepseek-v4-pro@official_opencode", valid=True, weighted_score=0.8, major_defect=False),
                        ],
                    )
                )
        result = aggregate_production_model_comparison(records)
        self.assertEqual(result.decision, "comparison_partial")
        self.assertEqual(result.discrimination_decision, "insufficient")


class HuagoConeReleaseDefinitionTests(unittest.TestCase):
    def test_eval_image_pins_agent_versions(self):
        text = (Path(__file__).parents[2] / "deploy" / "docker" / "Dockerfile.agent-eval").read_text(encoding="utf-8")
        self.assertIn("CODEX_VERSION=0.146.0", text)
        self.assertIn("OPENCODE_VERSION=1.17.13", text)

    def test_compose_is_read_only_and_single_concurrency(self):
        text = (Path(__file__).parents[2] / "deploy" / "docker" / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("read_only: true", text)
        self.assertIn('TASKGEN_EXECUTION_CONCURRENCY: "1"', text)
        self.assertIn("mem_limit: 2560m", text)
        self.assertIn("mem_limit: 3g", text)
        self.assertIn("cpus: 2.0", text)
        self.assertIn("/home/taskgenerator/.local:size=134217728", text)
        self.assertIn("/home/taskgenerator/.config:size=67108864", text)

    def test_release_runner_never_copies_auth_or_secret_into_context(self):
        text = (Path(__file__).parents[2] / "src" / "task_generator" / "cli" / "release.py").read_text(encoding="utf-8")
        self.assertIn('"auth.json"', text)
        self.assertIn('"deepseek-key.txt"', text)
        self.assertIn("never copy the source env file", text)
        self.assertIn("codex_auth_touched\": False", text)
        self.assertIn("_prune_forbidden_context(taskgenerator)", text)
        self.assertIn("PYTHONPATH=/opt/taskgenerator/src", text)


if __name__ == "__main__":
    unittest.main()
