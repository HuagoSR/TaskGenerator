from __future__ import annotations

import json
import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.evaluation.compact_grader import (  # noqa: E402
    CompactGraderBindingV2,
    CompactExceptionalEvidenceV2,
    CompactFindingV2,
    CompactGraderDraftV2,
    CompactGraderReviewV2,
    CompactGraderScopeV2,
    CompactScoreVectorV2,
    CompactScreeningGraderV2,
    RepresentativeScreeningResultV1,
)
from task_generator.evaluation.matched_screening import ScreeningTaskObservationV1
from task_generator.evaluation.semantic_review import (
    SemanticReviewExecutor,
)
from task_generator.substrate.skill_extractor import ProviderConfig


def scores(**overrides: int) -> CompactScoreVectorV2:
    values = {
        "factual_accuracy": 3,
        "evidence_traceability": 3,
        "method_process": 3,
        "exception_handling": 3,
        "reproducibility": 3,
        "structural_usability": 3,
        "professional_expression": 3,
    }
    values.update(overrides)
    return CompactScoreVectorV2(**values)


class CompactScreeningGraderTests(unittest.TestCase):
    def test_v2_1_restores_four_thousand_completion_tokens(self):
        schema = CompactGraderScopeV2.model_json_schema()
        properties = schema["properties"]
        self.assertEqual(
            properties["maximum_completion_tokens_per_call"]["default"],
            4000,
        )
        self.assertEqual(
            properties["scope_version"]["default"],
            "v3.compact_screening_grader_scope.2.1",
        )
        self.assertEqual(
            properties["output_contract"]["default"],
            "compact_scores_findings_v2_1",
        )

    def test_v2_scope_remains_readable_but_mixed_contract_is_rejected(self):
        bindings = [
            CompactGraderBindingV2(
                blind_task_id=f"ms_{index}",
                route_id=route,
                motif=motif,
                replicate_id=replicate,
                candidate_package_path="candidate",
                teacher_package_path="teacher",
                solver_outcome_sha256="a" * 64,
                delivery_path="delivery.xlsx",
                delivery_sha256="b" * 64,
                rubric_sha256="c" * 64,
                fact_anchors_sha256="d" * 64,
            )
            for index, (route, motif, replicate) in enumerate(
                (
                    (route, motif, replicate)
                    for route in ("skill_guided_llm", "llm_led_hybrid")
                    for motif in (
                        "fan_in_reconciliation",
                        "cross_check_validation",
                        "policy_application",
                    )
                    for replicate in ("a", "b")
                )
            )
        ]
        common = {
            "campaign_id": "campaign",
            "solver_manifest_path": "solver.json",
            "solver_manifest_sha256": "e" * 64,
            "parity_report_path": "parity.json",
            "parity_report_sha256": "f" * 64,
            "source_fingerprint": "1" * 64,
            "bindings": bindings,
        }
        legacy = CompactGraderScopeV2(
            **common,
            scope_version="v3.compact_screening_grader_scope.2",
            output_contract="compact_scores_findings_v2",
            maximum_completion_tokens_per_call=2000,
        )
        self.assertEqual(legacy.maximum_completion_tokens_per_call, 2000)
        with self.assertRaises(ValidationError):
            CompactGraderScopeV2(
                **common,
                scope_version="v3.compact_screening_grader_scope.2.1",
                output_contract="compact_scores_findings_v2_1",
                maximum_completion_tokens_per_call=2000,
            )

    def test_representative_scope_requires_complete_twenty_four_cell_matrix(self):
        bindings = [
            CompactGraderBindingV2(
                blind_task_id=f"rp_{index}",
                route_id=route,
                motif=motif,
                replicate_id=replicate,
                domain=domain,
                candidate_package_path="candidate",
                teacher_package_path="teacher",
                solver_outcome_sha256="a" * 64,
                delivery_path="delivery.xlsx",
                delivery_sha256="b" * 64,
                rubric_sha256="c" * 64,
                fact_anchors_sha256="d" * 64,
            )
            for index, (domain, route, motif, replicate) in enumerate(
                (
                    (domain, route, motif, replicate)
                    for domain in (
                        "audit_compliance",
                        "procurement_operations",
                    )
                    for route in (
                        "skill_guided_llm",
                        "llm_led_hybrid",
                    )
                    for motif in (
                        "fan_in_reconciliation",
                        "cross_check_validation",
                        "policy_application",
                    )
                    for replicate in ("a", "b")
                )
            )
        ]
        scope = CompactGraderScopeV2(
            scope_version="v3.compact_screening_grader_scope.3",
            cohort_kind="representative_production_pilot",
            campaign_id="representative",
            solver_manifest_path="solver.json",
            solver_manifest_sha256="e" * 64,
            parity_report_path="parity.json",
            parity_report_sha256="f" * 64,
            source_fingerprint="1" * 64,
            bindings=bindings,
        )
        self.assertEqual(len(scope.bindings), 24)
        with self.assertRaises(ValidationError):
            CompactGraderScopeV2(
                **{
                    **scope.model_dump(mode="json"),
                    "bindings": bindings[:-1],
                }
            )
        non_thinking = CompactGraderScopeV2(
            **{
                **scope.model_dump(mode="json"),
                "scope_version": "v3.compact_screening_grader_scope.3.1",
                "deepseek_reasoning_mode": "disabled",
            }
        )
        self.assertEqual(non_thinking.deepseek_reasoning_mode, "disabled")
        with self.assertRaises(ValidationError):
            CompactGraderScopeV2(
                **{
                    **scope.model_dump(mode="json"),
                    "deepseek_reasoning_mode": "disabled",
                }
            )

    def test_deepseek_disabled_mode_omits_reasoning_effort_and_temperature(self):
        content = CompactGraderDraftV2(
            blind_task_id="rp_test",
            scores=scores(),
            major_defect=False,
        ).model_dump_json()
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        )
        create = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        )
        executor = SemanticReviewExecutor(
            ProviderConfig(
                provider_name="deepseek",
                model="deepseek-v4-pro",
                base_url="https://example.invalid",
                api_key="secret",
                reasoning_mode="disabled",
            ),
            max_retries=0,
        )
        with patch("openai.OpenAI", return_value=client):
            draft = executor._call(
                "Return JSON.",
                {"blind_task_id": "rp_test"},
                CompactGraderDraftV2,
                {"blind_task_id": "rp_test"},
            )
        self.assertEqual(draft.blind_task_id, "rp_test")
        kwargs = create.call_args.kwargs
        self.assertNotIn("reasoning_effort", kwargs)
        self.assertNotIn("temperature", kwargs)
        self.assertEqual(
            kwargs["extra_body"], {"thinking": {"type": "disabled"}}
        )

    def test_representative_analyzer_scales_absolute_gates_and_reports_domains(self):
        domains = ("audit_compliance", "procurement_operations")
        routes = ("skill_guided_llm", "llm_led_hybrid")
        motifs = (
            "fan_in_reconciliation",
            "cross_check_validation",
            "policy_application",
        )
        bindings = []
        observations = []
        index = 0
        for domain in domains:
            for route in routes:
                for motif in motifs:
                    for replicate in ("a", "b"):
                        task_id = f"rp_{index}"
                        index += 1
                        bindings.append(
                            CompactGraderBindingV2(
                                blind_task_id=task_id,
                                route_id=route,
                                motif=motif,
                                replicate_id=replicate,
                                domain=domain,
                                candidate_package_path="candidate",
                                teacher_package_path="teacher",
                                solver_outcome_sha256="a" * 64,
                                delivery_path="delivery.xlsx",
                                delivery_sha256="b" * 64,
                                rubric_sha256="c" * 64,
                                fact_anchors_sha256="d" * 64,
                            )
                        )
                        observations.append(
                            ScreeningTaskObservationV1(
                                blind_task_id=task_id,
                                route_id=route,
                                motif=motif,
                                replicate_id=replicate,
                                infrastructure_complete=True,
                                offline_validity_pass=True,
                                exact_valid_delivery=True,
                                major_defect=False,
                                professional_plausibility_pass=True,
                                productive_complexity_pass=True,
                                skill_causal_pass=True,
                                effective_rubric_dimensions=7,
                                weighted_score=0.75,
                            )
                        )
        grader = object.__new__(CompactScreeningGraderV2)
        grader.scope = CompactGraderScopeV2(
            scope_version="v3.compact_screening_grader_scope.3",
            cohort_kind="representative_production_pilot",
            campaign_id="representative",
            solver_manifest_path="solver.json",
            solver_manifest_sha256="e" * 64,
            parity_report_path="parity.json",
            parity_report_sha256="f" * 64,
            source_fingerprint="1" * 64,
            bindings=bindings,
        )
        result = grader._analyze_representative(observations)
        self.assertIsInstance(result, RepresentativeScreeningResultV1)
        self.assertEqual(result.decision, "production_candidate_both")
        self.assertEqual(result.comparable_pair_count, 12)
        self.assertTrue(
            all(item.absolute_gate_pass for item in result.route_summaries)
        )
        self.assertEqual(
            {item.completed_grade_count for item in result.domain_summaries},
            {12},
        )

    def test_professionally_adequate_default_is_not_saturated(self):
        review = CompactGraderReviewV2(
            blind_task_id="ms_test",
            scores=scores(),
            findings=[],
            exceptional_evidence=[],
            major_defect=False,
            weighted_score=0.75,
            professional_plausibility="pass",
        )
        self.assertEqual(review.weighted_score, 0.75)
        self.assertLess(review.weighted_score, 0.9)

    def test_score_four_requires_specific_exceptional_evidence(self):
        with self.assertRaises(ValidationError):
            CompactGraderDraftV2(
                blind_task_id="ms_test",
                scores=scores(factual_accuracy=4),
                findings=[],
                exceptional_evidence=[],
                major_defect=False,
            )
        draft = CompactGraderDraftV2(
            blind_task_id="ms_test",
            scores=scores(factual_accuracy=4),
            findings=[],
            exceptional_evidence=[
                CompactExceptionalEvidenceV2(
                    criterion_id="criterion_factual_accuracy",
                    locator="Summary!A2",
                    evidence="Independent reconciliation exceeds the required checks.",
                )
            ],
            major_defect=False,
        )
        self.assertEqual(draft.scores.factual_accuracy, 4)

    def test_score_two_or_lower_requires_finding(self):
        with self.assertRaises(ValidationError):
            CompactGraderDraftV2(
                blind_task_id="ms_test",
                scores=scores(reproducibility=2),
                findings=[],
                exceptional_evidence=[],
                major_defect=False,
            )
        draft = CompactGraderDraftV2(
            blind_task_id="ms_test",
            scores=scores(reproducibility=2),
            findings=[
                CompactFindingV2(
                    criterion_id="criterion_reproducibility",
                    severity="material",
                    locator="Method!B4",
                    issue="The transformation cannot be independently reproduced.",
                )
            ],
            exceptional_evidence=[],
            major_defect=False,
        )
        self.assertEqual(draft.scores.reproducibility, 2)

    def test_major_defect_and_major_finding_are_consistent(self):
        finding = CompactFindingV2(
            criterion_id="criterion_factual_accuracy",
            severity="major",
            locator="Summary!C8",
            issue="The conclusion contradicts a deterministic fact anchor.",
        )
        with self.assertRaises(ValidationError):
            CompactGraderDraftV2(
                blind_task_id="ms_test",
                scores=scores(factual_accuracy=1),
                findings=[finding],
                exceptional_evidence=[],
                major_defect=False,
            )
        draft = CompactGraderDraftV2(
            blind_task_id="ms_test",
            scores=scores(factual_accuracy=1),
            findings=[finding],
            exceptional_evidence=[],
            major_defect=True,
        )
        self.assertTrue(draft.major_defect)

    def test_weighted_score_and_plausibility_are_programmed(self):
        with self.assertRaises(ValidationError):
            CompactGraderReviewV2(
                blind_task_id="ms_test",
                scores=scores(),
                findings=[],
                exceptional_evidence=[],
                major_defect=False,
                weighted_score=1.0,
                professional_plausibility="pass",
            )
        with self.assertRaises(ValidationError):
            CompactGraderReviewV2(
                blind_task_id="ms_test",
                scores=scores(),
                findings=[],
                exceptional_evidence=[],
                major_defect=False,
                weighted_score=0.75,
                professional_plausibility="fail",
            )

    def test_standard_response_is_compact(self):
        draft = CompactGraderDraftV2(
            blind_task_id="ms_test",
            scores=scores(),
            findings=[],
            exceptional_evidence=[],
            major_defect=False,
        )
        rendered = draft.model_dump_json()
        self.assertLess(len(rendered), 1000)
        self.assertNotIn("rationale", rendered)

    def test_prompt_anchors_three_as_normal_pass_and_forbids_total(self):
        prompt = CompactScreeningGraderV2.SYSTEM_PROMPT
        self.assertIn("Use 3 for a professionally adequate", prompt)
        self.assertIn("completeness or matching fact anchors alone never earns 4", prompt)
        self.assertIn("Do not write", prompt)
        self.assertNotIn("route_id", prompt)

    def test_schema_rejects_extra_fields_and_oversized_findings(self):
        payload = {
            "blind_task_id": "ms_test",
            "scores": scores().model_dump(),
            "findings": [],
            "exceptional_evidence": [],
            "major_defect": False,
            "route_identity_seen": False,
            "total_score": 3.0,
        }
        with self.assertRaises(ValidationError):
            CompactGraderDraftV2.model_validate(payload)
        schema = CompactGraderDraftV2.model_json_schema()
        rendered = json.dumps(schema)
        self.assertIn('"maxItems": 5', rendered)
        self.assertIn('"maxItems": 2', rendered)

    def test_binding_validation_accepts_persisted_string_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            delivery = root / "delivery.xlsx"
            rubric = root / "teacher" / "rubric_plan_v2.json"
            anchors = root / "teacher" / "deterministic_fact_anchors.json"
            rubric.parent.mkdir(parents=True)
            delivery.write_bytes(b"xlsx-placeholder")
            rubric.write_text("{}", encoding="utf-8")
            anchors.write_text("{}", encoding="utf-8")
            import hashlib

            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            binding = CompactGraderBindingV2(
                blind_task_id="ms_test",
                route_id="skill_guided_llm",
                motif="fan_in_reconciliation",
                replicate_id="a",
                candidate_package_path=str(root),
                teacher_package_path=str(root),
                solver_outcome_sha256="a" * 64,
                delivery_path=str(delivery),
                delivery_sha256=digest(delivery),
                rubric_sha256=digest(rubric),
                fact_anchors_sha256=digest(anchors),
            )
            grader = object.__new__(CompactScreeningGraderV2)
            grader._validate_binding(binding)


if __name__ == "__main__":
    unittest.main()
