from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_f4_from_scratch_campaign import AssistantReviewRecord, F4FromScratchCampaign


class F4FromScratchCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.canonical = root / "canonical.json"; self.canonical.write_text('{"entries":[]}', encoding="utf-8")
        self.spec = root / "spec.json"
        self.spec.write_text(json.dumps({
            "campaign_id":"test", "maximum_system_revisions_per_slot":2,
            "external_effects":{"external_solver_eval":False,"external_grader_eval":False},
            "slots":[
                {"slot":1,"motif":"fan_in_reconciliation","occurrence":0},
                {"slot":2,"motif":"evidence_to_deliverable","occurrence":0,"experimental_motif":True},
            ],
        }), encoding="utf-8")
        self.campaign = F4FromScratchCampaign(root / "run", self.spec, self.canonical)
        self.campaign.initialize(); self.campaign.begin_source_collection()
        source = root / "source.txt"; source.write_text("public", encoding="utf-8")
        run_manifest = root / "source_manifest.json"; run_manifest.write_text('{}', encoding="utf-8")
        self.campaign.registry_path.write_text('{"entries":[{"id":"s"}]}', encoding="utf-8")
        self.campaign.freeze_sources([source], run_manifest)

    def tearDown(self): self.temp.cleanup()

    def test_source_collection_is_single_use_and_frozen(self):
        with self.assertRaises(RuntimeError): self.campaign.begin_source_collection()
        self.campaign.assert_frozen_inputs()

    def test_next_slot_requires_release(self):
        self.campaign.begin_slot(1)
        with self.assertRaises(RuntimeError): self.campaign.begin_slot(2)

    def test_complete_happy_path_and_e2d_stays_experimental(self):
        for slot in (1, 2):
            self.campaign.begin_slot(slot)
            run = Path(self.temp.name) / f"run{slot}.json"; run.write_text('{}', encoding="utf-8")
            self.campaign.mark_generated(slot, run)
            evidence = Path(self.temp.name) / f"evidence{slot}"; evidence.mkdir()
            for name in ("whole_task_revision_bundle.json", "luna_candidate_solve.json", "deterministic_validation.json"):
                (evidence / name).write_text('{}', encoding="utf-8")
            self.campaign.mark_holistic_complete(slot, evidence)
            self.campaign.apply_review(self._review(slot, "pass"))
        manifest = self.campaign.read()
        self.assertEqual(manifest["decision"], "f4_from_scratch_validation_passed")
        self.assertFalse(manifest["slots"][1]["default_promotion_allowed"])

    def test_pass_cannot_bypass_failed_gate(self):
        self.campaign.begin_slot(1)
        run = Path(self.temp.name) / "run.json"; run.write_text('{}', encoding="utf-8")
        self.campaign.mark_generated(1, run)
        evidence = Path(self.temp.name) / "evidence"; evidence.mkdir()
        for name in ("whole_task_revision_bundle.json", "luna_candidate_solve.json", "deterministic_validation.json"):
            (evidence / name).write_text('{}', encoding="utf-8")
        self.campaign.mark_holistic_complete(1, evidence)
        review = self._review(1, "pass"); review.visual_review_pass = False
        with self.assertRaises(ValueError): self.campaign.apply_review(review)

    @staticmethod
    def _review(slot, decision):
        return AssistantReviewRecord(slot=slot, revision=1, decision=decision, candidate_blind_completed=True,
            deterministic_recomputation_pass=True, visual_review_pass=True, teacher_rubric_review_pass=True,
            verifier_export_pass=True, unresolved_material_ambiguity=False, findings=[], responsibility="none",
            reviewed_at="2026-07-13T00:00:00+00:00")


if __name__ == "__main__": unittest.main()
