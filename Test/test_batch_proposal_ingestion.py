from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_pipeline_b_batch_runner import (
    BatchTaskDesignProposalManifestV1,
    PipelineBBatchRunner,
)
from src.task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    TaskDesignProposalV1,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "SkillRegistry" / "v3_skill_registry.json"
SEED_REPORT = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
MOTIF_GRAMMAR = (
    ROOT / "SkillRegistry" / "v3_motif_graph_grammar.experimental.json"
)


class BatchProposalIngestionTests(unittest.TestCase):
    def test_manifest_is_rejected_outside_reconstruction_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_path = root / "proposal.json"
            proposal_path.write_text("{}", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "case_id": "case",
                                "proposal_path": str(proposal_path),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "proposal_input_manifest_requires_reconstruction_experimental",
            ):
                PipelineBBatchRunner().run(
                    registry_path=REGISTRY,
                    seed_report_path=SEED_REPORT,
                    output_dir=root / "out",
                    motifs=["fan_in_reconciliation"],
                    max_cases=1,
                    proposal_input_manifest_path=manifest_path,
                )

    def test_manifest_must_cover_exact_selected_batch_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_path = root / "proposal.json"
            proposal_path.write_text("{}", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "case_id": "unknown_case",
                                "proposal_path": str(proposal_path),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "proposal_manifest_missing_cases",
            ):
                PipelineBBatchRunner().run(
                    registry_path=REGISTRY,
                    seed_report_path=SEED_REPORT,
                    output_dir=root / "out",
                    motifs=["fan_in_reconciliation"],
                    max_cases=1,
                    target_difficulty_profile="reconstruction_experimental",
                    proposal_input_manifest_path=manifest_path,
                )

    def test_manifest_hash_and_brief_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            brief = self._fixture_brief()
            proposal = self._proposal_for_brief(brief)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(
                proposal.model_dump_json(indent=2),
                encoding="utf-8",
            )
            manifest = BatchTaskDesignProposalManifestV1.model_validate(
                {
                    "proposals": [
                        {
                            "case_id": brief.case_id,
                            "proposal_path": str(proposal_path),
                            "expected_brief_id": brief.brief_id,
                            "proposal_sha256": "0" * 64,
                        }
                    ]
                }
            )
            with self.assertRaisesRegex(
                ValueError,
                "batch_proposal_sha256_mismatch",
            ):
                PipelineBBatchRunner()._resolve_batch_proposal(
                    case_id=brief.case_id,
                    brief=brief,
                    manifest=manifest,
                    manifest_path=root / "manifest.json",
                )

            payload = proposal.model_dump(mode="json")
            payload["brief_id"] = "wrong_brief"
            wrong = TaskDesignProposalV1.model_validate(payload)
            proposal_path.write_text(
                wrong.model_dump_json(indent=2),
                encoding="utf-8",
            )
            digest = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
            manifest.proposals[0].proposal_sha256 = digest
            with self.assertRaisesRegex(
                ValueError,
                "batch_proposal_brief_id_mismatch",
            ):
                PipelineBBatchRunner()._resolve_batch_proposal(
                    case_id=brief.case_id,
                    brief=brief,
                    manifest=manifest,
                    manifest_path=root / "manifest.json",
                )

    def test_validated_proposal_uses_hybrid_route_not_legacy_materialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context_run = PipelineBBatchRunner().run(
                registry_path=REGISTRY,
                seed_report_path=SEED_REPORT,
                output_dir=root / "context",
                motifs=["fan_in_reconciliation"],
                max_cases=1,
                skill_count=2,
                motif_grammar_path=MOTIF_GRAMMAR,
                target_difficulty_profile="reconstruction_experimental",
            )
            self.assertEqual(context_run.cases[0].status, "completed")
            case_id = context_run.cases[0].case_id
            brief_path = (
                Path(context_run.cases[0].case_dir)
                / "task_design_frontend"
                / "capability_brief.json"
            )
            brief = CapabilityBriefV1.model_validate_json(
                brief_path.read_text(encoding="utf-8")
            )
            proposal = self._proposal_for_brief(brief)
            proposal_dir = root / "proposal_inputs"
            proposal_dir.mkdir()
            proposal_path = proposal_dir / f"{case_id}.json"
            proposal_path.write_text(
                proposal.model_dump_json(indent=2),
                encoding="utf-8",
            )
            digest = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
            manifest_path = proposal_dir / "proposal_input_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest_version": "v3.batch_task_design_proposals.1",
                        "proposals": [
                            {
                                "case_id": case_id,
                                "proposal_path": proposal_path.name,
                                "expected_brief_id": brief.brief_id,
                                "proposal_sha256": digest,
                            }
                        ],
                        "external_provider_calls_authorized": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = PipelineBBatchRunner().run(
                registry_path=REGISTRY,
                seed_report_path=SEED_REPORT,
                output_dir=root / "hybrid",
                motifs=["fan_in_reconciliation"],
                max_cases=1,
                skill_count=2,
                motif_grammar_path=MOTIF_GRAMMAR,
                target_difficulty_profile="reconstruction_experimental",
                proposal_input_manifest_path=manifest_path,
            )
            case = report.cases[0]
            case_root = Path(case.case_dir)
            self.assertEqual(case.status, "completed")
            self.assertEqual(
                case.design_frontend_status,
                "proposal_validated_hybrid_materialized",
            )
            self.assertEqual(case.proposal_validation_decision, "pass")
            self.assertEqual(case.hybrid_materialization_decision, "pass")
            self.assertTrue(case.r5_offline_governance_pass)
            self.assertEqual(case.validity_overall_status, "provisional")
            self.assertEqual(case.utility_profile_status, "provisional")
            self.assertEqual(case.rubric_plan_decision, "pass")
            self.assertEqual(case.package_readiness, "draft_revise_only")
            self.assertEqual(case.validation_status, "draft_compatible")
            self.assertEqual(case.eval_run_status, "dry_run_ready")
            self.assertTrue(
                (
                    case_root
                    / "hybrid_materialization"
                    / "governance"
                    / "r5_governance_bundle.json"
                ).is_file()
            )
            self.assertFalse((case_root / "prototype").exists())
            self.assertFalse((case_root / "teacher_runner").exists())

    def _fixture_brief(self) -> CapabilityBriefV1:
        path = (
            ROOT
            / "Test"
            / "fixtures"
            / "pipeline_reconstruction"
            / "task_design"
            / "capability_brief.json"
        )
        return CapabilityBriefV1.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def _proposal_for_brief(
        self,
        brief: CapabilityBriefV1,
    ) -> TaskDesignProposalV1:
        source_ids = [item.source_ref_id for item in brief.source_refs]
        evidence_nodes = []
        for index, source_id in enumerate(source_ids, start=1):
            evidence_nodes.append(
                {
                    "node_id": f"evidence_{index}",
                    "artifact_role": f"Evidence register {index}",
                    "candidate_visible": True,
                    "source_ref_ids": [source_id],
                    "intended_contents": (
                        "Candidate-visible records needed for cross-checking."
                    ),
                }
            )
        if len(evidence_nodes) == 1:
            evidence_nodes.append(
                {
                    "node_id": "evidence_2",
                    "artifact_role": "Independent comparison register",
                    "candidate_visible": True,
                    "source_ref_ids": [source_ids[0]],
                    "intended_contents": (
                        "A second candidate-visible view used for reconciliation."
                    ),
                }
            )
        relations = [
            {
                "relation_id": f"relation_{index}",
                "from_node_id": evidence_nodes[index - 1]["node_id"],
                "to_node_id": evidence_nodes[index]["node_id"],
                "relation_type": "cross_check",
                "solver_must_infer": True,
            }
            for index in range(1, len(evidence_nodes))
        ]
        judgments = []
        bindings = []
        for index, skill in enumerate(brief.selected_skills, start=1):
            judgment_id = f"judgment_{index}"
            judgments.append(
                {
                    "judgment_id": judgment_id,
                    "description": (
                        "Assess the candidate-visible evidence and document "
                        "material exceptions with a traceable rationale."
                    ),
                    "input_node_ids": [
                        evidence_nodes[0]["node_id"],
                        evidence_nodes[1]["node_id"],
                    ],
                    "observable_output": (
                        "A review-ready conclusion with evidence trace and exception status."
                    ),
                    "capability_ids": list(skill.required_capability_ids),
                }
            )
            bindings.append(
                {
                    "skill_id": skill.skill_id,
                    "binding_types": ["required_judgment"],
                    "bound_element_ids": [judgment_id],
                    "observable_behavior": (
                        "The candidate applies this skill to produce a distinct "
                        "evidence-backed professional judgment."
                    ),
                }
            )
        return TaskDesignProposalV1.model_validate(
            {
                "proposal_id": f"proposal_{brief.case_id}",
                "brief_id": brief.brief_id,
                "proposal_origin": "tracked_fixture",
                "source_ref_ids": source_ids,
                "scenario": (
                    "A review team received several evidence registers and must "
                    "prepare a decision-ready reconciliation for its manager."
                ),
                "actor_role": brief.business_role,
                "trigger_event": brief.trigger_event,
                "evidence_nodes": evidence_nodes,
                "evidence_relations": relations,
                "required_judgments": judgments,
                "skill_bindings": bindings,
                "deliverable_intent": {
                    "artifact_kind": "validation workpaper",
                    "intended_audience": "review manager",
                    "business_use": (
                        "Support review, exception follow-up, and documented sign-off."
                    ),
                    "required_sections_or_views": [
                        "Evidence reconciliation",
                        "Exceptions",
                        "Review trail",
                    ],
                    "allowed_formats": ["xlsx"],
                },
                "productive_complexity": list(
                    brief.productive_complexity_floor
                ),
                "accidental_difficulty_to_avoid": [
                    "Do not hide required fields or submission instructions.",
                    "Do not require unsupported file tools.",
                ],
                "deterministic_fact_constraints": [
                    "All exact counts and comparisons must be recomputed from candidate-visible evidence."
                ],
                "assumptions_not_allowed": [
                    "Do not invent missing balances, thresholds, policies, or identifiers."
                ],
                "unresolved_design_questions": [],
            }
        )


if __name__ == "__main__":
    unittest.main()
