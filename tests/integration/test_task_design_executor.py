from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.substrate.skill_extractor import ProviderConfig
from task_generator.planning.task_design_executor import (
    TaskDesignExecutionRequestV1,
    TaskDesignProposalExecutor,
    TaskDesignProviderDiagnosticsV1,
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"

    / "task_design"
)


def _upgrade_to_v2(payload):
    upgraded = json.loads(json.dumps(payload))
    upgraded["proposal_version"] = "v3.task_design_proposal.2"
    for node in upgraded["evidence_nodes"]:
        node["artifact_spec"] = {
            "fact_origin": "governed_scenario_fact",
            "record_type": node["artifact_role"],
            "primary_key_field": "record_id",
            "fields": [
                {
                    "field_name": "record_id",
                    "display_name": "Record ID",
                    "data_type": "identifier",
                    "description": "Stable candidate-visible record identifier.",
                },
                {
                    "field_name": "case_id",
                    "display_name": "Case ID",
                    "data_type": "identifier",
                    "description": "Shared key for cross-file analysis.",
                },
                {
                    "field_name": "business_period",
                    "display_name": "Business Period",
                    "data_type": "text",
                    "description": "Applicable business reporting period.",
                },
                {
                    "field_name": "record_status",
                    "display_name": "Record Status",
                    "data_type": "enum",
                    "description": "Candidate-visible business record status.",
                },
            ],
            "records": [
                {
                    "record_id": f"REC-{index:03d}",
                    "values": {
                        "record_id": f"REC-{index:03d}",
                        "case_id": f"CASE-{index:03d}",
                        "business_period": "2026-Q1",
                        "record_status": "open" if index == 3 else "complete",
                    },
                }
                for index in range(1, 4)
            ],
            "methodological_source_ref_ids": node["source_ref_ids"],
        }
    for relation in upgraded["evidence_relations"]:
        relation["from_join_field"] = "case_id"
        relation["to_join_field"] = "case_id"
        relation["comparison_fields"] = []
    return upgraded


def _to_semantic_payload(payload):
    semantic = json.loads(json.dumps(payload))
    semantic.pop("proposal_version", None)
    semantic.pop("proposal_origin", None)
    semantic.pop("authority", None)
    semantic["semantic_proposal_version"] = (
        "v3.task_design_semantic_proposal.1"
    )
    for node in semantic["evidence_nodes"]:
        node.pop("candidate_visible", None)
        spec = node["artifact_spec"]
        spec.pop("spec_version", None)
        spec["records"] = [record["values"] for record in spec["records"]]
    return semantic


class FakeTaskDesignExecutor(TaskDesignProposalExecutor):
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def _call_provider(self, prompt, config, max_tokens, timeout_seconds):
        self.prompts.append(prompt)
        return self.payload, TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            response_char_count=len(json.dumps(self.payload)),
            response_sha256="fixture",
        )


class TaskDesignExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_payload = _upgrade_to_v2(
            json.loads(
                (FIXTURE_ROOT / "valid_proposal.json").read_text(encoding="utf-8")
            )
        )

    def _config(self, model="gpt-5.6-sol"):
        return ProviderConfig(
            provider_name="fixture",
            base_url="https://example.invalid",
            api_key=("fixture" + "-credential"),
            model=model,
            timeout_seconds=60,
        )

    def _request(self, root: Path, **updates):
        values = {
            "capability_brief_path": str(
                FIXTURE_ROOT / "capability_brief.json"
            ),
            "output_dir": str(root),
            "allow_external_provider": True,
        }
        values.update(updates)
        return TaskDesignExecutionRequestV1(**values)

    def test_external_provider_requires_explicit_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = self._request(
                Path(directory), allow_external_provider=False
            )
            with self.assertRaisesRegex(PermissionError, "not_authorized"):
                FakeTaskDesignExecutor(self.valid_payload).run(
                    request, self._config()
                )

    def test_expensive_claude_model_is_blocked_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = self._request(
                Path(directory), model="claude-sonnet-4-6"
            )
            with self.assertRaisesRegex(PermissionError, "expensive"):
                FakeTaskDesignExecutor(self.valid_payload).run(
                    request, self._config("claude-sonnet-4-6")
                )

    def test_valid_proposal_is_persisted_without_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = FakeTaskDesignExecutor(self.valid_payload).run(
                self._request(root), self._config()
            )
            self.assertEqual(report.status, "completed")
            self.assertFalse(report.materialization_triggered)
            self.assertFalse(report.registry_mutation_triggered)
            self.assertFalse(report.promotion_triggered)
            self.assertTrue((root / "task_design_proposal.json").is_file())
            self.assertFalse((root / "rw_task_export").exists())
            diagnostics = json.loads(
                (root / "task_design_provider_diagnostics.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(diagnostics["raw_response_included"])

    def test_persisted_proposal_replay_is_offline_and_revalidates_current_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal = json.loads(json.dumps(self.valid_payload))
            proposal["evidence_nodes"][0]["artifact_spec"][
                "methodological_source_ref_ids"
            ] = []
            proposal_path = root / "persisted_proposal.json"
            proposal_path.write_text(
                json.dumps(proposal),
                encoding="utf-8",
            )
            output_root = root / "offline_replay"

            report = TaskDesignProposalExecutor().replay_persisted_proposal(
                capability_brief_path=FIXTURE_ROOT / "capability_brief.json",
                proposal_path=proposal_path,
                output_dir=output_root,
                route_id="llm_led_hybrid",
            )

            self.assertEqual(report.status, "proposal_blocked")
            self.assertFalse(report.request.allow_external_provider)
            self.assertIsNone(report.provider_diagnostics_path)
            self.assertFalse(
                (output_root / "task_design_provider_diagnostics.json").exists()
            )
            self.assertFalse(report.materialization_triggered)
            validation = json.loads(
                (output_root / "task_design_validation_report.json").read_text(
                    encoding="utf-8"
                )
            )
            findings = {
                finding["check_name"]: finding
                for finding in validation["findings"]
            }
            self.assertEqual(
                findings["artifact_provenance_projection"]["severity"],
                "blocking",
            )

    def test_semantic_proposal_is_normalized_and_both_contracts_are_persisted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            semantic_payload = _to_semantic_payload(self.valid_payload)
            report = FakeTaskDesignExecutor(semantic_payload).run(
                self._request(root),
                self._config(),
            )
            self.assertEqual(report.status, "completed")
            self.assertEqual(
                report.proposal_interface_mode,
                "semantic_normalized_v1",
            )
            self.assertTrue((root / "task_design_semantic_proposal.json").is_file())
            self.assertTrue((root / "task_design_normalization_report.json").is_file())
            self.assertTrue((root / "task_design_proposal.json").is_file())
            normalization = json.loads(
                (root / "task_design_normalization_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(normalization["decision"], "pass")
            self.assertEqual(normalization["facts_added"], 0)
            self.assertEqual(normalization["facts_removed"], 0)
            self.assertEqual(
                normalization["provider_semantics_source_sha256"],
                normalization["provider_semantics_normalized_sha256"],
            )

    def test_incomplete_semantic_join_contract_is_preserved_for_one_repair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incomplete = _to_semantic_payload(self.valid_payload)
            incomplete["evidence_relations"][0].pop("from_join_field")
            first_executor = FakeTaskDesignExecutor(incomplete)
            first = first_executor.run(
                self._request(root / "attempt_01"),
                self._config(),
            )
            self.assertEqual(first.status, "semantic_proposal_blocked")
            self.assertIsNotNone(first.semantic_proposal_path)
            self.assertTrue(
                (root / "attempt_01" / "task_design_semantic_proposal.json").is_file()
            )
            self.assertFalse(
                (root / "attempt_01" / "task_design_proposal.json").exists()
            )
            self.assertTrue(
                any(
                    finding["location"][-1:] == ["from_join_field"]
                    for finding in first.contract_validation_findings
                )
            )

            repair_executor = FakeTaskDesignExecutor(
                _to_semantic_payload(self.valid_payload)
            )
            second = repair_executor.run(
                self._request(
                    root / "attempt_02",
                    repair_from_execution_report_path=str(
                        root
                        / "attempt_01"
                        / "task_design_execution_report.json"
                    ),
                ),
                self._config(),
            )
            self.assertEqual(second.status, "completed")
            repair_prompt = repair_executor.prompts[0]
            self.assertIn("Governed repair attempt:", repair_prompt)
            self.assertIn('"prior_semantic_proposal"', repair_prompt)
            self.assertIn('"from_join_field"', repair_prompt)
            self.assertIn(
                '"valid_bound_element_ids_from_prior_proposal"',
                repair_prompt,
            )

            readiness = TaskDesignProposalExecutor().compile_repair_readiness(
                [
                    root
                    / "attempt_01"
                    / "task_design_execution_report.json"
                ],
                root / "semantic_repair_readiness.json",
            )
            self.assertEqual(readiness.decision, "pass")
            self.assertEqual(
                readiness.cases[0].prior_status,
                "semantic_proposal_blocked",
            )

    def test_invalid_provider_proposal_is_preserved_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = json.loads(json.dumps(self.valid_payload))
            payload["unresolved_design_questions"] = ["Which threshold applies?"]
            report = FakeTaskDesignExecutor(payload).run(
                self._request(Path(directory)), self._config()
            )
            self.assertEqual(report.status, "proposal_blocked")
            self.assertFalse(report.materialization_triggered)

    def test_schema_invalid_output_fails_closed_and_keeps_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = FakeTaskDesignExecutor({"proposal_id": "incomplete"}).run(
                self._request(root), self._config()
            )
            self.assertEqual(report.status, "contract_failed")
            self.assertFalse((root / "task_design_proposal.json").exists())
            self.assertTrue(
                (root / "task_design_provider_diagnostics.json").is_file()
            )
            self.assertTrue(report.contract_validation_findings)
            self.assertEqual(
                report.proposal_interface_mode,
                "semantic_normalized_v1",
            )
            self.assertTrue(
                (root / "task_design_normalization_report.json").is_file()
            )
            self.assertTrue(
                all("input" not in finding for finding in report.contract_validation_findings)
            )

    def test_legacy_v1_provider_proposal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            legacy_payload = json.loads(
                (FIXTURE_ROOT / "valid_proposal.json").read_text(encoding="utf-8")
            )
            report = FakeTaskDesignExecutor(legacy_payload).run(
                self._request(Path(directory)),
                self._config(),
            )
            self.assertEqual(report.status, "contract_failed")
            self.assertFalse((Path(directory) / "task_design_proposal.json").exists())

    def test_prompt_declares_exact_bound_element_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executor = FakeTaskDesignExecutor(self.valid_payload)
            executor.run(self._request(Path(directory)), self._config())
            prompt = executor.prompts[0]
            self.assertIn(
                "deliverable:<exact deliverable_intent.required_sections_or_views entry>",
                prompt,
            )
            self.assertIn("Raw section text", prompt)
            self.assertIn("`deliverable_section_*`", prompt)
            self.assertIn("`v3.task_design_proposal.2`", prompt)
            self.assertIn("`v3.task_design_semantic_proposal.1`", prompt)
            self.assertIn("governed fictional scenario facts", prompt)
            self.assertIn("Candidate-authored conclusions", prompt)
            self.assertIn("Never omit either key", prompt)
            self.assertIn("never use null", prompt)
            self.assertIn("exactly one skill_bindings entry", prompt)
            self.assertIn("do not repeat the same skill_id", prompt)

    def test_repair_prompt_contains_preserved_failure_and_allowed_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_payload = json.loads(json.dumps(self.valid_payload))
            invalid_payload["skill_bindings"][0]["bound_element_ids"] = [
                "deliverable_intent"
            ]
            first_executor = FakeTaskDesignExecutor(invalid_payload)
            first = first_executor.run(
                self._request(root / "attempt_01"),
                self._config(),
            )
            self.assertEqual(first.status, "proposal_blocked")

            repair_executor = FakeTaskDesignExecutor(self.valid_payload)
            second = repair_executor.run(
                self._request(
                    root / "attempt_02",
                    repair_from_execution_report_path=str(
                        root
                        / "attempt_01"
                        / "task_design_execution_report.json"
                    ),
                ),
                self._config(),
            )
            self.assertEqual(second.status, "completed")
            repair_prompt = repair_executor.prompts[0]
            self.assertIn("Governed repair attempt:", repair_prompt)
            self.assertIn('"deliverable_intent"', repair_prompt)
            self.assertIn(
                '"valid_bound_element_ids_from_prior_proposal"',
                repair_prompt,
            )
            self.assertNotEqual(first_executor.prompts[0], repair_prompt)
            persisted_prompt = (
                root
                / "attempt_02"
                / "task_design_proposal_prompt.md"
            ).read_text(encoding="utf-8")
            self.assertEqual(persisted_prompt, repair_prompt)

    def test_contract_failure_cannot_be_used_as_repair_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = FakeTaskDesignExecutor({"proposal_id": "incomplete"}).run(
                self._request(root / "attempt_01"),
                self._config(),
            )
            self.assertEqual(first.status, "contract_failed")
            repair_executor = FakeTaskDesignExecutor(self.valid_payload)
            with self.assertRaisesRegex(
                ValueError,
                "requires_persisted_blocked_proposal",
            ):
                repair_executor.run(
                    self._request(
                        root / "attempt_02",
                        repair_from_execution_report_path=str(
                            root
                            / "attempt_01"
                            / "task_design_execution_report.json"
                        ),
                    ),
                    self._config(),
                )
            self.assertEqual(repair_executor.prompts, [])

    def test_repair_readiness_report_is_offline_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_payload = json.loads(json.dumps(self.valid_payload))
            invalid_payload["skill_bindings"][0]["bound_element_ids"] = [
                "deliverable_intent"
            ]
            first = FakeTaskDesignExecutor(invalid_payload).run(
                self._request(root / "attempt_01"),
                self._config(),
            )
            self.assertEqual(first.status, "proposal_blocked")
            report = TaskDesignProposalExecutor().compile_repair_readiness(
                [
                    root
                    / "attempt_01"
                    / "task_design_execution_report.json"
                ],
                root / "nested" / "repair_readiness.json",
            )
            self.assertEqual(report.decision, "pass")
            self.assertEqual(report.case_count, 1)
            self.assertEqual(report.passed_case_count, 1)
            self.assertFalse(report.external_provider_calls_made)
            self.assertTrue(
                (root / "nested" / "repair_readiness.json").is_file()
            )
            case = report.cases[0]
            self.assertTrue(case.prompt_changed)
            self.assertTrue(case.repair_marker_present)
            self.assertTrue(case.prior_proposal_included)
            self.assertGreater(
                case.blocking_validation_finding_count,
                0,
            )
            self.assertGreater(
                case.canonical_bound_element_id_count,
                0,
            )
            verification = (
                TaskDesignProposalExecutor().verify_repair_readiness(
                    root / "nested" / "repair_readiness.json"
                )
            )
            self.assertEqual(verification.decision, "pass")
            self.assertEqual(verification.replayed_case_count, 1)

            payload = json.loads(
                (
                    root / "nested" / "repair_readiness.json"
                ).read_text(encoding="utf-8")
            )
            payload["cases"][0]["repair_prompt_sha256"] = "0" * 64
            tampered_path = root / "nested" / "tampered_readiness.json"
            tampered_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            tampered = (
                TaskDesignProposalExecutor().verify_repair_readiness(
                    tampered_path
                )
            )
            self.assertEqual(tampered.decision, "blocked")
            self.assertIn(
                "case_1:repair_prompt_sha256_mismatch",
                tampered.blocking_reasons,
            )

    def test_portable_repair_bundle_survives_source_removal_and_detects_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source_attempt"
            invalid_payload = json.loads(json.dumps(self.valid_payload))
            invalid_payload["skill_bindings"][0]["bound_element_ids"] = [
                "deliverable_intent"
            ]
            first = FakeTaskDesignExecutor(invalid_payload).run(
                self._request(source_root),
                self._config(),
            )
            self.assertEqual(first.status, "proposal_blocked")
            report_path = root / "portable_readiness.json"
            bundle_root = root / "portable_bundle"
            report = TaskDesignProposalExecutor().compile_repair_readiness(
                [source_root / "task_design_execution_report.json"],
                report_path,
                portable_bundle_dir=bundle_root,
            )
            self.assertEqual(report.evidence_mode, "portable_bundle")
            self.assertTrue(report.bundle_file_sha256)
            import shutil

            shutil.rmtree(source_root)
            verification = (
                TaskDesignProposalExecutor().verify_repair_readiness(
                    report_path
                )
            )
            self.assertEqual(verification.decision, "pass")
            bundled_proposal = (
                bundle_root / "case_01" / "task_design_proposal.json"
            )
            bundled_proposal.write_text(
                bundled_proposal.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            tampered = (
                TaskDesignProposalExecutor().verify_repair_readiness(
                    report_path
                )
            )
            self.assertEqual(tampered.decision, "blocked")
            self.assertIn(
                "repair_bundle_file_hashes_mismatch",
                tampered.blocking_reasons,
            )


if __name__ == "__main__":
    unittest.main()
