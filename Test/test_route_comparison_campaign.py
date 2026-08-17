from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_route_comparison_campaign import (
    CampaignAuthorizationRequestV1,
    CampaignAuthorizationReceiptV1,
    ComparisonExecutionPolicyV1,
    RouteComparisonCampaign,
)
from task_generator.v3_formal_brief_admission import (
    FormalBriefCohortAdmissionReportV1,
)
from task_generator.v3_route_generation import StrictTemplateProposalCompiler
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_task_design_executor import (
    TaskDesignExecutionRequestV1,
    TaskDesignProposalExecutor,
    TaskDesignProviderDiagnosticsV1,
)
from task_generator.v3_task_design_frontend import CapabilityBriefV1


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
    / "capability_brief.json"
)


class FakeCampaignProposalExecutor(TaskDesignProposalExecutor):
    def _call_provider(self, prompt, config, max_tokens, timeout_seconds):
        marker = "CapabilityBrief JSON:\n"
        brief = CapabilityBriefV1.model_validate(
            json.loads(prompt.split(marker, 1)[1])
        )
        proposal = StrictTemplateProposalCompiler().compile(brief)
        payload = proposal.model_dump(mode="json")
        payload["proposal_id"] = (
            f"fixture_llm_{brief.brief_id}_{abs(hash(prompt))}"
        )
        payload["proposal_origin"] = "llm"
        return payload, TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            response_char_count=len(json.dumps(payload)),
            response_sha256="fixture",
        )


class RepairAwareCampaignProposalExecutor(TaskDesignProposalExecutor):
    def __init__(self):
        self.prompts: list[str] = []

    def _call_provider(self, prompt, config, max_tokens, timeout_seconds):
        self.prompts.append(prompt)
        marker = "CapabilityBrief JSON:\n"
        brief = CapabilityBriefV1.model_validate(
            json.loads(prompt.split(marker, 1)[1])
        )
        proposal = StrictTemplateProposalCompiler().compile(brief)
        payload = proposal.model_dump(mode="json")
        payload["proposal_id"] = f"fixture_repair_{len(self.prompts)}"
        payload["proposal_origin"] = "llm"
        if "Governed repair attempt:" not in prompt:
            payload["skill_bindings"][0]["bound_element_ids"] = [
                "deliverable_intent"
            ]
        return payload, TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            response_char_count=len(json.dumps(payload)),
            response_sha256="fixture",
        )


class DuplicateBindingRepairAwareCampaignProposalExecutor(
    TaskDesignProposalExecutor
):
    def __init__(self):
        self.prompts: list[str] = []

    def _call_provider(self, prompt, config, max_tokens, timeout_seconds):
        self.prompts.append(prompt)
        marker = "CapabilityBrief JSON:\n"
        brief = CapabilityBriefV1.model_validate(
            json.loads(prompt.split(marker, 1)[1])
        )
        proposal = StrictTemplateProposalCompiler().compile(brief)
        payload = proposal.model_dump(mode="json")
        payload["proposal_id"] = (
            f"fixture_duplicate_binding_{len(self.prompts)}"
        )
        payload["proposal_origin"] = "llm"
        if "Governed repair attempt:" not in prompt:
            payload["skill_bindings"].append(
                json.loads(json.dumps(payload["skill_bindings"][0]))
            )
        return payload, TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            response_char_count=len(json.dumps(payload)),
            response_sha256="fixture",
        )


class SemanticRepairAwareCampaignProposalExecutor(TaskDesignProposalExecutor):
    def __init__(self):
        self.prompts: list[str] = []

    def _call_provider(self, prompt, config, max_tokens, timeout_seconds):
        self.prompts.append(prompt)
        marker = "CapabilityBrief JSON:\n"
        brief = CapabilityBriefV1.model_validate(
            json.loads(prompt.split(marker, 1)[1])
        )
        proposal = StrictTemplateProposalCompiler().compile(brief)
        payload = proposal.model_dump(mode="json")
        payload.pop("proposal_version", None)
        payload.pop("proposal_origin", None)
        payload.pop("authority", None)
        payload["semantic_proposal_version"] = (
            "v3.task_design_semantic_proposal.1"
        )
        payload["proposal_id"] = f"fixture_semantic_repair_{len(self.prompts)}"
        for node in payload["evidence_nodes"]:
            node.pop("candidate_visible", None)
            node["artifact_spec"].pop("spec_version", None)
            node["artifact_spec"]["records"] = [
                record["values"]
                for record in node["artifact_spec"]["records"]
            ]
        if "Governed repair attempt:" not in prompt:
            payload["evidence_relations"][0].pop("from_join_field")
        return payload, TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            response_char_count=len(json.dumps(payload)),
            response_sha256="fixture-semantic-repair",
        )


class SchemaInvalidCampaignProposalExecutor(TaskDesignProposalExecutor):
    def __init__(self):
        self.call_count = 0

    def _call_provider(self, prompt, config, max_tokens, timeout_seconds):
        self.call_count += 1
        return {"proposal_id": "incomplete"}, TaskDesignProviderDiagnosticsV1(
            provider=config.provider_name,
            model=config.model,
            finish_reason="stop",
            response_char_count=29,
            response_sha256="fixture-invalid",
        )


class RouteComparisonCampaignTests(unittest.TestCase):
    def _authorization_binding(
        self,
        campaign: RouteComparisonCampaign,
        authorized_ids: list[str],
        maximum_cost: float,
    ) -> dict:
        manifest = campaign.read()
        assignments = [
            item
            for item in manifest.assignments
            if item.blind_task_id in set(authorized_ids)
        ]
        request = CampaignAuthorizationRequestV1(
            comparison_id=manifest.comparison_id,
            requested_blind_task_ids=authorized_ids,
            requested_brief_id=assignments[0].brief_id,
            requested_routes=sorted(
                {item.route_id for item in assignments}
            ),
            maximum_provider_cost_usd=maximum_cost,
            maximum_attempts_per_assignment=2,
            campaign_manifest_sha256=hashlib.sha256(
                campaign.manifest_path.read_bytes()
            ).hexdigest(),
            route_comparison_manifest_sha256=(
                manifest.route_comparison_manifest_sha256
            ),
            execution_policy_sha256=manifest.execution_policy_sha256,
            source_snapshot_sha256=manifest.source_snapshot_sha256,
            brief_admission_report_sha256=(
                manifest.brief_admission_report_sha256 or ""
            ),
            repair_readiness_report_sha256=(
                manifest.repair_readiness_report_sha256 or ""
            ),
            repair_readiness_verification_sha256=(
                manifest.repair_readiness_verification_sha256 or ""
            ),
            excluded_authorities=[
                "solver_execution",
                "grader_execution",
                "professional_review",
                "registry_mutation",
                "release_activation",
                "promotion",
            ],
            user_action_required=(
                "Fixture request binds the exact provider assignments."
            ),
        )
        request_path = (
            campaign.root
            / "governance"
            / "provider_smoke_authorization_request.json"
        )
        request_path.write_text(
            request.model_dump_json(indent=2),
            encoding="utf-8",
        )
        request_sha256 = hashlib.sha256(
            request_path.read_bytes()
        ).hexdigest()
        immutable_request_path = (
            campaign.root
            / "governance"
            / "authorization_requests"
            / f"{request_sha256}.json"
        )
        immutable_request_path.parent.mkdir(parents=True, exist_ok=True)
        immutable_request_path.write_bytes(request_path.read_bytes())
        return {
            "authorization_request_sha256": request_sha256,
            "route_comparison_manifest_sha256": (
                manifest.route_comparison_manifest_sha256
            ),
            "execution_policy_sha256": manifest.execution_policy_sha256,
            "source_snapshot_sha256": manifest.source_snapshot_sha256,
            "brief_admission_report_sha256": (
                manifest.brief_admission_report_sha256
            ),
        }

    def _inputs(self, root: Path):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        briefs = []
        for index, motif in enumerate(
            [
                "fan_in_reconciliation",
                "cross_check_validation",
                "policy_application",
                "evidence_to_deliverable",
            ],
            start=1,
        ):
            item = json.loads(json.dumps(payload))
            item["brief_id"] = f"campaign_brief_{index}"
            item["case_id"] = f"campaign_case_{index}"
            item["motif"] = motif
            path = root / f"brief_{index}.json"
            path.write_text(json.dumps(item), encoding="utf-8")
            briefs.append(path)
        source = root / "source_snapshot.json"
        source.write_text(
            json.dumps({"snapshot": "tracked-public-fixture"}),
            encoding="utf-8",
        )
        return briefs, source

    def _prepare(
        self, root: Path, formal: bool = False
    ) -> RouteComparisonCampaign:
        briefs, source = self._inputs(root)
        admission_path = None
        repair_readiness_path = None
        if formal:
            brief_ids = [
                CapabilityBriefV1.model_validate_json(
                    path.read_text(encoding="utf-8")
                ).brief_id
                for path in briefs
            ]
            admission = FormalBriefCohortAdmissionReportV1(
                cohort_id="fixture_formal_cohort",
                decision="pass",
                expected_brief_count=4,
                observed_brief_count=4,
                admitted_brief_ids=brief_ids,
            )
            admission_path = root / "formal_admission.json"
            admission_path.write_text(
                admission.model_dump_json(indent=2),
                encoding="utf-8",
            )
            failed_root = root / "failed_proposal"
            failed_report = RepairAwareCampaignProposalExecutor().run(
                TaskDesignExecutionRequestV1(
                    capability_brief_path=str(briefs[0]),
                    output_dir=str(failed_root),
                    route_id="skill_guided_llm",
                    allow_external_provider=True,
                ),
                ProviderConfig(
                    provider_name="fixture",
                    base_url="https://example.invalid",
                    api_key="fixture-credential",
                    model="gpt-5.6-sol",
                    timeout_seconds=60,
                ),
            )
            self.assertEqual(failed_report.status, "proposal_blocked")
            repair_readiness_path = root / "repair_readiness.json"
            TaskDesignProposalExecutor().compile_repair_readiness(
                [failed_root / "task_design_execution_report.json"],
                repair_readiness_path,
                portable_bundle_dir=root / "repair_evidence_bundle",
            )
        campaign = RouteComparisonCampaign(root / "campaign")
        campaign.prepare(
            comparison_id="r6_campaign_fixture",
            brief_paths=briefs,
            source_snapshot_path=source,
            environment_contract_id="fixed-linux-amd64-v1",
            solver_preflight_contract_path="governance/panel.json",
            grader_calibration_contract_path="governance/grader.json",
            maximum_provider_cost_usd=40.0,
            input_class=(
                "formal_public_source" if formal else "contract_only"
            ),
            brief_admission_report_path=admission_path,
            repair_readiness_report_path=repair_readiness_path,
        )
        return campaign

    def test_prepare_freezes_three_real_route_contracts_and_blocks_claude(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._prepare(Path(directory))
            manifest = campaign.read()
            self.assertEqual(len(manifest.assignments), 12)
            policy = ComparisonExecutionPolicyV1.model_validate_json(
                Path(manifest.execution_policy_path).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(policy.design_model, "gpt-5.6-sol")
            self.assertIn("claude-sonnet-4-6", policy.hard_blocked_models)
            self.assertFalse(policy.external_execution_authorized)
            self.assertEqual(
                policy.proposal_second_attempt_mode,
                "feedback_conditioned_repair",
            )
            self.assertTrue(
                policy.repair_requires_prior_execution_report
            )
            self.assertTrue(
                all(
                    route.maximum_completion_tokens_per_attempt >= 16000
                    for route in policy.routes
                    if route.provider_required
                )
            )

    def test_formal_prepare_rejects_non_replayable_repair_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            briefs, source = self._inputs(root)
            brief_ids = [
                CapabilityBriefV1.model_validate_json(
                    path.read_text(encoding="utf-8")
                ).brief_id
                for path in briefs
            ]
            admission = FormalBriefCohortAdmissionReportV1(
                cohort_id="fixture_formal_cohort",
                decision="pass",
                expected_brief_count=4,
                observed_brief_count=4,
                admitted_brief_ids=brief_ids,
            )
            admission_path = root / "formal_admission.json"
            admission_path.write_text(
                admission.model_dump_json(indent=2),
                encoding="utf-8",
            )
            fabricated = root / "fabricated_readiness.json"
            fabricated.write_text(
                json.dumps(
                    {
                        "report_version": (
                            "v3.task_design_repair_readiness.1"
                        ),
                        "decision": "pass",
                        "case_count": 1,
                        "passed_case_count": 1,
                        "cases": [
                            {
                                "prior_execution_report_path": (
                                    str(root / "missing_execution.json")
                                ),
                                "prior_execution_report_sha256": "a" * 64,
                                "brief_id": brief_ids[0],
                                "route_id": "skill_guided_llm",
                                "prior_status": "proposal_blocked",
                                "initial_prompt_sha256": "b" * 64,
                                "repair_prompt_sha256": "c" * 64,
                                "prompt_changed": True,
                                "repair_marker_present": True,
                                "prior_proposal_included": True,
                                "blocking_validation_finding_count": 1,
                                "authority_blocking_reason_count": 0,
                                "canonical_bound_element_id_count": 3,
                                "decision": "pass",
                                "blocking_reasons": [],
                            }
                        ],
                        "external_provider_calls_made": False,
                        "materialization_triggered": False,
                        "registry_mutation_triggered": False,
                        "promotion_triggered": False,
                    }
                ),
                encoding="utf-8",
            )
            campaign_root = root / "campaign"
            with self.assertRaisesRegex(
                ValueError,
                "repair_readiness_report_not_pass",
            ):
                RouteComparisonCampaign(campaign_root).prepare(
                    comparison_id="r6_fabricated_repair_fixture",
                    brief_paths=briefs,
                    source_snapshot_path=source,
                    environment_contract_id="fixed-linux-amd64-v1",
                    solver_preflight_contract_path="governance/panel.json",
                    grader_calibration_contract_path="governance/grader.json",
                    maximum_provider_cost_usd=40.0,
                    input_class="formal_public_source",
                    brief_admission_report_path=admission_path,
                    repair_readiness_report_path=fabricated,
                )
            self.assertFalse(campaign_root.exists())

    def test_strict_controls_materialize_and_preflight_stops_at_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._prepare(Path(directory))
            manifest = campaign.materialize_strict_template_controls()
            strict = [
                item
                for item in manifest.assignments
                if item.route_id == "strict_template"
            ]
            self.assertEqual(
                [item.stage for item in strict],
                ["materialized"] * 4,
            )
            self.assertTrue(all(item.package_fingerprint for item in strict))
            report = campaign.preflight()
            self.assertEqual(report.structural_decision, "pass")
            self.assertEqual(
                report.execution_decision,
                "authorization_required",
            )
            self.assertTrue(report.strict_v2_semantic_controls_pass)
            self.assertEqual(report.strict_motif_signature_count, 4)
            self.assertFalse(report.external_calls_made)

    def test_preflight_blocks_homogenized_strict_motif_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._prepare(Path(directory))
            manifest = campaign.materialize_strict_template_controls()
            strict = [
                item
                for item in manifest.assignments
                if item.route_id == "strict_template"
            ]
            source_path = (
                Path(strict[0].package_root)
                / "governance"
                / "task_design_proposal.json"
            )
            target_path = (
                Path(strict[1].package_root)
                / "governance"
                / "task_design_proposal.json"
            )
            source = json.loads(source_path.read_text(encoding="utf-8"))
            target = json.loads(target_path.read_text(encoding="utf-8"))
            for source_node, target_node in zip(
                source["evidence_nodes"],
                target["evidence_nodes"],
            ):
                target_node["artifact_spec"] = source_node["artifact_spec"]
            for source_relation, target_relation in zip(
                source["evidence_relations"],
                target["evidence_relations"],
            ):
                target_relation["from_join_field"] = source_relation[
                    "from_join_field"
                ]
                target_relation["to_join_field"] = source_relation[
                    "to_join_field"
                ]
                target_relation["comparison_fields"] = source_relation[
                    "comparison_fields"
                ]
            target_path.write_text(
                json.dumps(target, indent=2),
                encoding="utf-8",
            )
            report = campaign.preflight()
            self.assertEqual(report.structural_decision, "blocked")
            self.assertIn(
                "strict_motif_semantic_signatures_not_distinct",
                report.blocking_reasons,
            )
            self.assertEqual(report.strict_motif_signature_count, 3)

    def test_preflight_detects_materialized_package_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._prepare(Path(directory))
            manifest = campaign.materialize_strict_template_controls()
            strict = next(
                item
                for item in manifest.assignments
                if item.route_id == "strict_template"
            )
            prompt_path = Path(strict.package_root) / "candidate" / "prompt.md"
            prompt_path.write_text(
                prompt_path.read_text(encoding="utf-8")
                + "\nmutated after materialization\n",
                encoding="utf-8",
            )
            report = campaign.preflight()
            self.assertEqual(report.structural_decision, "blocked")
            self.assertFalse(report.manifest_fingerprints_match)

    def test_authorization_cannot_reintroduce_hard_blocked_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-authorization",
                **self._authorization_binding(
                    campaign,
                    [
                        item.blind_task_id
                        for item in campaign.read().assignments
                        if item.route_id != "strict_template"
                    ],
                    40.0,
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=[
                    "gpt-5.6-sol",
                    "claude-sonnet-4-6",
                ],
                authorized_blind_task_ids=[
                    item.blind_task_id
                    for item in campaign.read().assignments
                    if item.route_id != "strict_template"
                ],
                maximum_provider_cost_usd=40.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization used only to test fail-closed policy."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "authorization.json"
            receipt_path.write_text(
                receipt.model_dump_json(indent=2),
                encoding="utf-8",
            )
            report = campaign.preflight(receipt_path)
            self.assertEqual(report.execution_decision, "blocked")
            self.assertTrue(
                any(
                    reason.startswith("authorization_receipt_invalid")
                    for reason in report.blocking_reasons
                )
            )

    def test_first_failure_is_preserved_and_retry_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            assignment = campaign.read().assignments[0]
            failure = root / "failure.json"
            failure.write_text('{"failure":"first"}', encoding="utf-8")
            campaign.record_stage_result(
                blind_task_id=assignment.blind_task_id,
                stage="provider_proposal",
                decision="failed",
                evidence_path=failure,
                failure_type="fixture_failure",
            )
            failure.write_text('{"failure":"second"}', encoding="utf-8")
            campaign.record_stage_result(
                blind_task_id=assignment.blind_task_id,
                stage="provider_proposal",
                decision="failed",
                evidence_path=failure,
                failure_type="fixture_failure",
            )
            with self.assertRaisesRegex(RuntimeError, "retry_limit"):
                campaign.record_stage_result(
                    blind_task_id=assignment.blind_task_id,
                    stage="provider_proposal",
                    decision="failed",
                    evidence_path=failure,
                    failure_type="fixture_failure",
                )
            record = next(
                item
                for item in campaign.read().assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            preserved = Path(record.first_failure_evidence_path or "")
            self.assertEqual(
                json.loads(preserved.read_text(encoding="utf-8"))["failure"],
                "first",
            )

    def test_preflight_detects_code_fingerprint_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = self._prepare(Path(directory))
            campaign.materialize_strict_template_controls()
            manifest_path = Path(
                campaign.read().route_comparison_manifest_path
            )
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["code_fingerprint"] = "stale-code"
            manifest_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            # Keep the outer file fingerprint aligned to isolate the embedded
            # code-fingerprint check.
            campaign_payload = json.loads(
                campaign.manifest_path.read_text(encoding="utf-8")
            )
            import hashlib

            campaign_payload["route_comparison_manifest_sha256"] = (
                hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            )
            campaign.manifest_path.write_text(
                json.dumps(campaign_payload),
                encoding="utf-8",
            )
            report = campaign.preflight()
            self.assertEqual(report.structural_decision, "blocked")
            self.assertFalse(report.manifest_fingerprints_match)

    def test_preflight_replays_and_detects_repair_bundle_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            self.assertEqual(
                campaign.preflight().structural_decision,
                "pass",
            )
            readiness = json.loads(
                Path(
                    campaign.read().repair_readiness_report_path or ""
                ).read_text(encoding="utf-8")
            )
            bundle_root = Path(readiness["bundle_root"])
            proposal_path = (
                bundle_root / "case_01" / "task_design_proposal.json"
            )
            proposal_path.write_text(
                proposal_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            report = campaign.preflight()
            self.assertEqual(report.structural_decision, "blocked")
            self.assertFalse(report.manifest_fingerprints_match)

    def test_authorized_provider_routes_use_gpt_policy_and_resume_to_packages_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-valid-authorization",
                **self._authorization_binding(
                    campaign,
                    [
                        item.blind_task_id
                        for item in campaign.read().assignments
                        if item.route_id != "strict_template"
                    ],
                    40.0,
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=[
                    item.blind_task_id
                    for item in campaign.read().assignments
                    if item.route_id != "strict_template"
                ],
                maximum_provider_cost_usd=40.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization validates the governed provider route."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "valid_authorization.json"
            receipt_path.write_text(
                receipt.model_dump_json(indent=2),
                encoding="utf-8",
            )
            self.assertEqual(
                campaign.preflight(receipt_path).execution_decision,
                "ready",
            )
            partial = campaign.generate_provider_routes(
                config=ProviderConfig(
                    provider_name="fixture",
                    base_url="https://example.invalid",
                    api_key="fixture-credential",
                    model="gpt-5.6-sol",
                    timeout_seconds=60,
                ),
                executor=FakeCampaignProposalExecutor(),
                maximum_assignments=2,
            )
            self.assertEqual(partial.provider_attempt_count, 2)
            self.assertEqual(
                sum(
                    item.stage == "materialized"
                    for item in partial.assignments
                    if item.route_id != "strict_template"
                ),
                2,
            )
            result = campaign.generate_provider_routes(
                config=ProviderConfig(
                    provider_name="fixture",
                    base_url="https://example.invalid",
                    api_key="fixture-credential",
                    model="gpt-5.6-sol",
                    timeout_seconds=60,
                ),
                executor=FakeCampaignProposalExecutor(),
            )
            self.assertEqual(result.status, "packages_ready")
            self.assertEqual(result.provider_attempt_count, 8)
            self.assertEqual(
                result.provider_cost_ceiling_reserved_usd,
                16.0,
            )
            self.assertTrue(
                all(item.stage == "materialized" for item in result.assignments)
            )
            self.assertFalse(result.solver_calls_made)
            self.assertFalse(result.grader_calls_made)
            screening = campaign.write_provider_screening_outcome()
            self.assertEqual(
                screening.decision,
                "proceed_to_behavioral_evaluation",
            )
            self.assertEqual(screening.provider_materialized_count, 8)
            staged = campaign.stage_route_blind_packages()
            self.assertEqual(staged.status, "evaluation_ready")
            self.assertTrue(
                all(item.stage == "blind_staged" for item in staged.assignments)
            )
            self.assertEqual(
                len(
                    list(
                        (
                            root
                            / "campaign"
                            / "blind_staging"
                            / "candidate_packages"
                        ).iterdir()
                    )
                ),
                12,
            )

    def test_second_provider_attempt_is_feedback_conditioned_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            assignment = next(
                item
                for item in campaign.read().assignments
                if item.route_id != "strict_template"
            )
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-repair-authorization",
                **self._authorization_binding(
                    campaign,
                    [assignment.blind_task_id],
                    4.0,
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=[assignment.blind_task_id],
                maximum_provider_cost_usd=4.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization covers one initial attempt and one repair."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "repair_authorization.json"
            receipt_path.write_text(
                receipt.model_dump_json(indent=2),
                encoding="utf-8",
            )
            self.assertEqual(
                campaign.preflight(receipt_path).execution_decision,
                "ready",
            )
            executor = RepairAwareCampaignProposalExecutor()
            config = ProviderConfig(
                provider_name="fixture",
                base_url="https://example.invalid",
                api_key="fixture-credential",
                model="gpt-5.6-sol",
                timeout_seconds=60,
            )
            first = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            first_record = next(
                item
                for item in first.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            self.assertEqual(first_record.stage, "blocked")
            second = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            second_record = next(
                item
                for item in second.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            self.assertEqual(second_record.stage, "materialized")
            self.assertEqual(len(executor.prompts), 2)
            self.assertNotEqual(executor.prompts[0], executor.prompts[1])
            self.assertNotIn(
                "Governed repair attempt:",
                executor.prompts[0],
            )
            self.assertIn(
                "Governed repair attempt:",
                executor.prompts[1],
            )
            self.assertIn('"deliverable_intent"', executor.prompts[1])
            provider_attempts = [
                item
                for item in second_record.attempts
                if item.stage == "provider_proposal"
            ]
            self.assertEqual(len(provider_attempts), 2)
            self.assertEqual(
                [item.decision for item in provider_attempts],
                ["failed", "pass"],
            )
            screening = campaign.write_provider_screening_outcome()
            self.assertEqual(screening.decision, "redesign_again")
            self.assertEqual(
                screening.feedback_conditioned_retry_count,
                1,
            )
            self.assertEqual(screening.unconditioned_retry_count, 0)

    def test_duplicate_skill_binding_has_distinct_screening_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            assignment = next(
                item
                for item in campaign.read().assignments
                if item.route_id != "strict_template"
            )
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-cardinality-authorization",
                **self._authorization_binding(
                    campaign,
                    [assignment.blind_task_id],
                    4.0,
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=[assignment.blind_task_id],
                maximum_provider_cost_usd=4.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization covers cardinality repair."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "cardinality_authorization.json"
            receipt_path.write_text(
                receipt.model_dump_json(indent=2),
                encoding="utf-8",
            )
            self.assertEqual(
                campaign.preflight(receipt_path).execution_decision,
                "ready",
            )
            executor = DuplicateBindingRepairAwareCampaignProposalExecutor()
            config = ProviderConfig(
                provider_name="fixture",
                base_url="https://example.invalid",
                api_key="fixture-credential",
                model="gpt-5.6-sol",
                timeout_seconds=60,
            )
            first = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            first_record = next(
                item
                for item in first.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            self.assertEqual(first_record.stage, "blocked")
            second = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            second_record = next(
                item
                for item in second.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            self.assertEqual(second_record.stage, "materialized")
            screening = campaign.write_provider_screening_outcome()
            self.assertIn(
                "skill_binding_cardinality_contract_underspecified",
                screening.reason_codes,
            )
            self.assertNotIn(
                "bound_element_reference_contract_underspecified",
                screening.reason_codes,
            )
            self.assertEqual(screening.feedback_conditioned_retry_count, 1)
            self.assertEqual(screening.unconditioned_retry_count, 0)

    def test_contract_failure_is_not_retried_as_proposal_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            assignment = next(
                item for item in campaign.read().assignments
                if item.route_id != "strict_template"
            )
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-contract-failure",
                **self._authorization_binding(
                    campaign, [assignment.blind_task_id], 4.0
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=[assignment.blind_task_id],
                maximum_provider_cost_usd=4.0,
                authorized_by_user=True,
                authorization_statement="Fixture contract-failure authorization.",
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "contract_failure_authorization.json"
            receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
            self.assertEqual(
                campaign.preflight(receipt_path).execution_decision,
                "ready",
            )
            executor = SchemaInvalidCampaignProposalExecutor()
            config = ProviderConfig(
                provider_name="fixture",
                base_url="https://example.invalid",
                api_key="fixture-credential",
                model="gpt-5.6-sol",
                timeout_seconds=60,
            )
            campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            result = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            self.assertEqual(executor.call_count, 1)
            self.assertEqual(result.provider_attempt_count, 1)
            self.assertEqual(result.provider_cost_ceiling_reserved_usd, 2.0)

    def test_semantic_contract_failure_gets_one_feedback_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            assignment = next(
                item
                for item in campaign.read().assignments
                if item.route_id != "strict_template"
            )
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-semantic-repair",
                **self._authorization_binding(
                    campaign,
                    [assignment.blind_task_id],
                    4.0,
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=[assignment.blind_task_id],
                maximum_provider_cost_usd=4.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization covers one semantic repair."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "semantic_repair_authorization.json"
            receipt_path.write_text(
                receipt.model_dump_json(indent=2),
                encoding="utf-8",
            )
            self.assertEqual(
                campaign.preflight(receipt_path).execution_decision,
                "ready",
            )
            executor = SemanticRepairAwareCampaignProposalExecutor()
            config = ProviderConfig(
                provider_name="fixture",
                base_url="https://example.invalid",
                api_key="fixture-credential",
                model="gpt-5.6-sol",
                timeout_seconds=60,
            )
            first = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            first_record = next(
                item
                for item in first.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            self.assertEqual(first_record.stage, "blocked")
            first_report = json.loads(
                Path(first_record.attempts[-1].evidence_path).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                first_report["status"],
                "semantic_proposal_blocked",
            )

            second = campaign.generate_provider_routes(
                config=config,
                executor=executor,
                blind_task_ids=[assignment.blind_task_id],
            )
            second_record = next(
                item
                for item in second.assignments
                if item.blind_task_id == assignment.blind_task_id
            )
            self.assertEqual(second_record.stage, "materialized")
            self.assertEqual(len(executor.prompts), 2)
            self.assertIn(
                '"prior_semantic_proposal"',
                executor.prompts[1],
            )
            screening = campaign.write_provider_screening_outcome()
            self.assertEqual(
                screening.feedback_conditioned_retry_count,
                1,
            )
            self.assertEqual(screening.unconditioned_retry_count, 0)

    def test_smoke_authorization_request_is_exact_and_non_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            manifest = campaign.read()
            brief_id = manifest.assignments[0].brief_id
            request = campaign.write_provider_smoke_authorization_request(
                brief_id=brief_id,
                maximum_provider_cost_usd=8.0,
            )
            self.assertEqual(len(request.requested_blind_task_ids), 2)
            self.assertEqual(
                set(request.requested_routes),
                {"skill_guided_llm", "llm_led_hybrid"},
            )
            self.assertEqual(
                request.second_attempt_mode,
                "feedback_conditioned_repair",
            )
            self.assertTrue(
                request.repair_requires_prior_execution_report
            )
            self.assertFalse(request.external_calls_made)
            self.assertIn("solver_execution", request.excluded_authorities)
            request_paths = list(
                (
                    campaign.root
                    / "governance"
                    / "authorization_requests"
                ).glob("*.json")
            )
            self.assertEqual(len(request_paths), 1)
            self.assertEqual(
                hashlib.sha256(request_paths[0].read_bytes()).hexdigest(),
                request_paths[0].stem,
            )
            self.assertEqual(
                campaign.preflight().execution_decision,
                "authorization_required",
            )
            partial = campaign.write_provider_screening_outcome()
            self.assertEqual(
                partial.decision,
                "awaiting_provider_completion",
            )
            self.assertEqual(
                partial.reason_codes,
                ["provider_campaign_incomplete"],
            )

    def test_authorization_receipt_compiles_from_immutable_request_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            brief_id = campaign.read().assignments[0].brief_id
            request = campaign.write_provider_smoke_authorization_request(
                brief_id=brief_id,
                maximum_provider_cost_usd=8.0,
            )
            request_path = next(
                (
                    campaign.root
                    / "governance"
                    / "authorization_requests"
                ).glob("*.json")
            )
            output = root / "compiled_receipt.json"
            receipt = campaign.compile_authorization_receipt(
                authorization_request_path=request_path,
                authorization_id="user-approved-fixture",
                authorization_statement=(
                    "User explicitly approved this exact fixture request."
                ),
                expires_at="2099-01-01T00:00:00+00:00",
                output_path=output,
            )
            self.assertEqual(
                receipt.authorized_blind_task_ids,
                sorted(request.requested_blind_task_ids),
            )
            self.assertEqual(receipt.authorized_models, ["gpt-5.6-sol"])
            self.assertEqual(receipt.maximum_provider_cost_usd, 8.0)
            self.assertTrue(output.is_file())
            self.assertEqual(
                campaign.read().status,
                "authorization_required",
            )
            self.assertEqual(
                campaign.preflight(output).execution_decision,
                "ready",
            )

    def test_authorization_receipt_rejects_request_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            brief_id = campaign.read().assignments[0].brief_id
            campaign.write_provider_smoke_authorization_request(
                brief_id=brief_id,
                maximum_provider_cost_usd=8.0,
            )
            request_path = next(
                (
                    campaign.root
                    / "governance"
                    / "authorization_requests"
                ).glob("*.json")
            )
            copied_request = root / request_path.name
            copied_request.write_bytes(request_path.read_bytes())
            with self.assertRaisesRegex(
                ValueError,
                "immutable_request_path",
            ):
                campaign.compile_authorization_receipt(
                    authorization_request_path=copied_request,
                    authorization_id="user-approved-fixture",
                    authorization_statement=(
                        "User explicitly approved this exact fixture request."
                    ),
                    expires_at="2099-01-01T00:00:00+00:00",
                    output_path=root / "receipt.json",
                )

    def test_authorization_receipt_compiles_for_sequential_slice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            manifest = campaign.read()
            manifest.status = "package_generation_in_progress"
            campaign._write(manifest)
            brief_id = manifest.assignments[0].brief_id
            request = campaign.write_provider_smoke_authorization_request(
                brief_id=brief_id,
                maximum_provider_cost_usd=8.0,
            )
            request_path = next(
                (
                    campaign.root
                    / "governance"
                    / "authorization_requests"
                ).glob("*.json")
            )
            output = root / "sequential_slice_receipt.json"
            receipt = campaign.compile_authorization_receipt(
                authorization_request_path=request_path,
                authorization_id="user-approved-sequential-fixture",
                authorization_statement=(
                    "User explicitly approved this exact sequential fixture request."
                ),
                expires_at="2099-01-01T00:00:00+00:00",
                output_path=output,
            )
            self.assertEqual(
                receipt.authorized_blind_task_ids,
                sorted(request.requested_blind_task_ids),
            )
            self.assertEqual(
                campaign.read().status,
                "package_generation_in_progress",
            )

    def test_old_receipt_cannot_activate_new_sequential_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            provider_by_brief: dict[str, list] = {}
            for assignment in campaign.read().assignments:
                if assignment.route_id == "strict_template":
                    continue
                provider_by_brief.setdefault(
                    assignment.brief_id,
                    [],
                ).append(assignment)
            first_pair, second_pair = list(provider_by_brief.values())[:2]

            campaign.write_provider_smoke_authorization_request(
                brief_id=first_pair[0].brief_id,
                maximum_provider_cost_usd=8.0,
            )
            active_request = (
                campaign.root
                / "governance"
                / "provider_smoke_authorization_request.json"
            )
            first_request_sha = hashlib.sha256(
                active_request.read_bytes()
            ).hexdigest()
            first_receipt_path = root / "first_receipt.json"
            campaign.compile_authorization_receipt(
                authorization_request_path=(
                    campaign.root
                    / "governance"
                    / "authorization_requests"
                    / f"{first_request_sha}.json"
                ),
                authorization_id="first-sequential-authorization",
                authorization_statement="First exact sequential request.",
                expires_at="2099-01-01T00:00:00+00:00",
                output_path=first_receipt_path,
            )
            self.assertEqual(
                campaign.preflight(first_receipt_path).execution_decision,
                "ready",
            )
            campaign.generate_provider_routes(
                config=ProviderConfig(
                    provider_name="fixture",
                    base_url="https://example.invalid",
                    api_key="fixture-credential",
                    model="gpt-5.6-sol",
                    timeout_seconds=60,
                ),
                executor=FakeCampaignProposalExecutor(),
                blind_task_ids=[item.blind_task_id for item in first_pair],
            )
            self.assertEqual(
                campaign.read().status,
                "package_generation_in_progress",
            )

            campaign.write_provider_smoke_authorization_request(
                brief_id=second_pair[0].brief_id,
                maximum_provider_cost_usd=8.0,
            )
            second_request_sha = hashlib.sha256(
                active_request.read_bytes()
            ).hexdigest()
            self.assertNotEqual(first_request_sha, second_request_sha)
            blocked = campaign.preflight(first_receipt_path)
            self.assertEqual(blocked.execution_decision, "blocked")
            self.assertIn(
                "authorization_receipt_active_request_mismatch",
                blocked.blocking_reasons,
            )
            self.assertEqual(
                campaign.read().status,
                "package_generation_in_progress",
            )

            second_receipt_path = root / "second_receipt.json"
            second_receipt = campaign.compile_authorization_receipt(
                authorization_request_path=(
                    campaign.root
                    / "governance"
                    / "authorization_requests"
                    / f"{second_request_sha}.json"
                ),
                authorization_id="second-sequential-authorization",
                authorization_statement="Second exact sequential request.",
                expires_at="2099-01-01T00:00:00+00:00",
                output_path=second_receipt_path,
            )
            self.assertEqual(
                second_receipt.authorized_blind_task_ids,
                sorted(item.blind_task_id for item in second_pair),
            )

    def test_receipt_limits_provider_generation_to_exact_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            provider_assignments = [
                item
                for item in campaign.read().assignments
                if item.route_id != "strict_template"
            ]
            authorized_ids = [
                provider_assignments[0].blind_task_id,
                provider_assignments[1].blind_task_id,
            ]
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-scoped-authorization",
                **self._authorization_binding(
                    campaign,
                    authorized_ids,
                    8.0,
                ),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=authorized_ids,
                maximum_provider_cost_usd=8.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization is limited to one matched route pair."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            receipt_path = root / "scoped_authorization.json"
            receipt_path.write_text(
                receipt.model_dump_json(indent=2),
                encoding="utf-8",
            )
            self.assertEqual(
                campaign.preflight(receipt_path).execution_decision,
                "ready",
            )
            result = campaign.generate_provider_routes(
                config=ProviderConfig(
                    provider_name="fixture",
                    base_url="https://example.invalid",
                    api_key="fixture-credential",
                    model="gpt-5.6-sol",
                    timeout_seconds=60,
                ),
                executor=FakeCampaignProposalExecutor(),
            )
            materialized_provider_ids = {
                item.blind_task_id
                for item in result.assignments
                if item.route_id != "strict_template"
                and item.stage == "materialized"
            }
            self.assertEqual(materialized_provider_ids, set(authorized_ids))
            self.assertTrue(campaign.preflight().external_calls_made)
            with self.assertRaisesRegex(
                PermissionError,
                "outside_authorized_scope",
            ):
                campaign.generate_provider_routes(
                    config=ProviderConfig(
                        provider_name="fixture",
                        base_url="https://example.invalid",
                        api_key="fixture-credential",
                        model="gpt-5.6-sol",
                        timeout_seconds=60,
                    ),
                    executor=FakeCampaignProposalExecutor(),
                    blind_task_ids=[provider_assignments[2].blind_task_id],
                )

    def test_receipt_tampering_after_preflight_blocks_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            provider_ids = [
                item.blind_task_id
                for item in campaign.read().assignments
                if item.route_id != "strict_template"
            ][:2]
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-tamper-check",
                **self._authorization_binding(campaign, provider_ids, 8.0),
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=provider_ids,
                maximum_provider_cost_usd=8.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization validates immutable receipt handling."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
            )
            path = root / "tamper_receipt.json"
            path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
            self.assertEqual(
                campaign.preflight(path).execution_decision,
                "ready",
            )
            canonical_path = Path(
                campaign.read().authorization_receipt_path or ""
            )
            self.assertNotEqual(canonical_path, path)
            payload = json.loads(canonical_path.read_text(encoding="utf-8"))
            payload["authorization_statement"] += " changed"
            canonical_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                PermissionError,
                "receipt_tampered",
            ):
                campaign.generate_provider_routes(
                    config=ProviderConfig(
                        provider_name="fixture",
                        base_url="https://example.invalid",
                        api_key="fixture-credential",
                        model="gpt-5.6-sol",
                        timeout_seconds=60,
                    ),
                    executor=FakeCampaignProposalExecutor(),
                )

    def test_sequential_authorizations_preserve_requests_and_reset_slice_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            provider_by_brief: dict[str, list] = {}
            for assignment in campaign.read().assignments:
                if assignment.route_id == "strict_template":
                    continue
                provider_by_brief.setdefault(
                    assignment.brief_id,
                    [],
                ).append(assignment)
            brief_pairs = list(provider_by_brief.values())[:2]
            for index, assignments in enumerate(brief_pairs, start=1):
                authorized_ids = [
                    item.blind_task_id for item in assignments
                ]
                receipt = CampaignAuthorizationReceiptV1(
                    comparison_id="r6_campaign_fixture",
                    authorization_id=f"fixture-slice-{index}",
                    **self._authorization_binding(
                        campaign,
                        authorized_ids,
                        8.0,
                    ),
                    authorized_scopes=["provider_proposal_generation"],
                    authorized_models=["gpt-5.6-sol"],
                    authorized_blind_task_ids=authorized_ids,
                    maximum_provider_cost_usd=8.0,
                    authorized_by_user=True,
                    authorization_statement=(
                        "Fixture authorization preserves one immutable slice."
                    ),
                    issued_at="2020-01-01T00:00:00+00:00",
                )
                receipt_path = root / f"slice_{index}.json"
                receipt_path.write_text(
                    receipt.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                self.assertEqual(
                    campaign.preflight(receipt_path).execution_decision,
                    "ready",
                )
                campaign.generate_provider_routes(
                    config=ProviderConfig(
                        provider_name="fixture",
                        base_url="https://example.invalid",
                        api_key="fixture-credential",
                        model="gpt-5.6-sol",
                        timeout_seconds=60,
                    ),
                    executor=FakeCampaignProposalExecutor(),
                )
            manifest = campaign.read()
            self.assertEqual(manifest.provider_attempt_count, 4)
            self.assertEqual(
                manifest.provider_cost_ceiling_reserved_usd,
                8.0,
            )
            self.assertEqual(
                manifest.provider_cost_ceiling_reserved_by_authorization_usd,
                {
                    "fixture-slice-1": 4.0,
                    "fixture-slice-2": 4.0,
                },
            )
            self.assertEqual(
                len(
                    list(
                        (
                            campaign.root
                            / "governance"
                            / "authorization_requests"
                        ).glob("*.json")
                    )
                ),
                2,
            )
            self.assertEqual(
                len(
                    list(
                        (
                            campaign.root
                            / "governance"
                            / "authorization_receipts"
                        ).glob("*.json")
                    )
                ),
                2,
            )

    def test_expired_or_wrong_fingerprint_receipt_fails_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = self._prepare(root, formal=True)
            campaign.materialize_strict_template_controls()
            provider_ids = [
                item.blind_task_id
                for item in campaign.read().assignments
                if item.route_id != "strict_template"
            ][:2]
            binding = self._authorization_binding(
                campaign, provider_ids, 8.0
            )
            binding["source_snapshot_sha256"] = "0" * 64
            receipt = CampaignAuthorizationReceiptV1(
                comparison_id="r6_campaign_fixture",
                authorization_id="fixture-expired-check",
                **binding,
                authorized_scopes=["provider_proposal_generation"],
                authorized_models=["gpt-5.6-sol"],
                authorized_blind_task_ids=provider_ids,
                maximum_provider_cost_usd=8.0,
                authorized_by_user=True,
                authorization_statement=(
                    "Fixture authorization validates expiry and fingerprint checks."
                ),
                issued_at="2020-01-01T00:00:00+00:00",
                expires_at="2021-01-01T00:00:00+00:00",
            )
            path = root / "expired_receipt.json"
            path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
            report = campaign.preflight(path)
            self.assertEqual(report.execution_decision, "blocked")
            self.assertTrue(
                any(
                    reason.startswith("authorization_receipt_invalid")
                    for reason in report.blocking_reasons
                )
            )


if __name__ == "__main__":
    unittest.main()
