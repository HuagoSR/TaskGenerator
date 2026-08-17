from __future__ import annotations

import unittest

from src.task_generator.v3_pipeline_b_batch_runner import PipelineBBatchCaseSummary
from src.task_generator.v3_production_batch_runner import ProductionBatchRunner


class ReconstructionProductionGateTests(unittest.TestCase):
    def _case(self, **updates):
        values = {
            "case_index": 1,
            "case_id": "case",
            "case_dir": "case",
            "status": "completed",
            "motif": "cross_check_validation",
            "quality_decision": "candidate_ready",
            "verifier_status": "pass",
            "validation_status": "candidate_ready_compatible",
            "global_validity_status": "diagnostic_only",
        }
        values.update(updates)
        return PipelineBBatchCaseSummary(**values)

    def test_legacy_candidate_ready_semantics_remain_compatible(self):
        self.assertTrue(
            ProductionBatchRunner()._is_candidate_ready(self._case())
        )

    def test_reconstruction_awaiting_provider_is_not_candidate_ready(self):
        case = self._case(
            design_frontend_status="offline_context_ready_legacy_materialization_only",
            proposal_validation_decision="awaiting_provider",
        )
        self.assertFalse(ProductionBatchRunner()._is_candidate_ready(case))

    def test_proposal_pass_without_hybrid_materialization_is_not_ready(self):
        case = self._case(
            design_frontend_status="proposal_validated",
            proposal_validation_decision="pass",
            hybrid_materialization_decision=None,
        )
        self.assertFalse(ProductionBatchRunner()._is_candidate_ready(case))

    def test_reconstruction_requires_both_proposal_and_hybrid_pass(self):
        case = self._case(
            design_frontend_status="proposal_validated",
            proposal_validation_decision="pass",
            hybrid_materialization_decision="pass",
            r5_offline_governance_pass=True,
            validity_overall_status="pass",
            utility_profile_status="pass",
            rubric_plan_decision="pass",
        )
        self.assertTrue(ProductionBatchRunner()._is_candidate_ready(case))

    def test_reconstruction_provisional_validity_is_not_ready(self):
        case = self._case(
            design_frontend_status="proposal_validated_hybrid_materialized",
            proposal_validation_decision="pass",
            hybrid_materialization_decision="pass",
            r5_offline_governance_pass=True,
            validity_overall_status="provisional",
            utility_profile_status="provisional",
            rubric_plan_decision="pass",
        )
        self.assertFalse(ProductionBatchRunner()._is_candidate_ready(case))


if __name__ == "__main__":
    unittest.main()
