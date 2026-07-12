import json
import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_end_to_end_pipeline import EndToEndRequest, STAGE_ORDER
from src.task_generator.v3_semantic_validity import (
    BlindRequirementReview,
    CandidateBlindReview,
    SemanticClaim,
    SemanticDependency,
    SemanticFinding,
    SemanticContractDraftBuilder,
    SemanticRequirement,
    SemanticReviewPackageBuilder,
    SemanticRevisionController,
    SecondaryFindingDecision,
    SecondarySemanticReview,
    SemanticValidityGate,
    TaskSemanticContract,
    TeacherRubricReview,
)


class SemanticValidityGateTests(unittest.TestCase):
    def _contract(self, *, rule=True, rubric=True, visible=True):
        dependencies = [
            SemanticDependency(
                dependency_id="dep_data",
                description="candidate data",
                source_kind="candidate_file" if visible else "teacher_only",
                file_name="data.xlsx",
                locator="Sheet1:A:B",
                candidate_visible=visible,
            )
        ]
        if rule:
            dependencies.append(
                SemanticDependency(
                    dependency_id="dep_rule",
                    description="candidate rule",
                    source_kind="candidate_rule",
                    file_name="policy.docx",
                    locator="POL-001",
                )
            )
        return TaskSemanticContract(
            task_id="task_1",
            created_at="2026-07-12T00:00:00Z",
            requirements=[SemanticRequirement(requirement_id="req_1", prompt_text="Classify exceptions", deliverable_file="out.xlsx", claim_ids=["claim_1"])],
            claims=[
                SemanticClaim(
                    claim_id="claim_1",
                    requirement_id="req_1",
                    claim_type="classification",
                    determinism="exact",
                    description="exception status",
                    dependency_ids=[item.dependency_id for item in dependencies],
                    rubric_criterion_ids=["R_001"] if rubric else [],
                )
            ],
            dependencies=dependencies,
        )

    def _blind(self, findings=None):
        return CandidateBlindReview(
            task_id="task_1",
            model="deepseek-v4-pro",
            provider="deepseek",
            created_at="2026-07-12T00:01:00Z",
            prompt_package_sha256="a" * 64,
            requirement_reviews=[BlindRequirementReview(requirement_id="req_1", answerability="supported")],
            findings=findings or [],
        )

    def _teacher(self, ratio=0.7, findings=None):
        return TeacherRubricReview(
            task_id="task_1",
            model="deepseek-v4-pro",
            provider="deepseek",
            created_at="2026-07-12T00:02:00Z",
            blind_review_sha256="b" * 64,
            teacher_truth_consistent=True,
            goldenrun_covers_requirements=True,
            rubric_fact_weight_ratio=ratio,
            findings=findings or [],
        )

    def test_complete_supported_contract_passes(self):
        report = SemanticValidityGate().build(self._contract(), self._blind(), self._teacher(), "blocking")
        self.assertEqual(report.decision, "pass")
        self.assertTrue(report.semantic_gate_pass)

    def test_missing_rule_and_fact_rubric_block(self):
        report = SemanticValidityGate().build(self._contract(rule=False, rubric=False), self._blind(), self._teacher(), "blocking")
        self.assertIn("underdefined_decision_rule", report.reason_codes)
        self.assertIn("rubric_missing_fact_coverage", report.reason_codes)
        self.assertEqual(report.decision, "revise")

    def test_teacher_only_dependency_blocks(self):
        report = SemanticValidityGate().build(self._contract(visible=False), self._blind(), self._teacher(), "blocking")
        self.assertIn("hidden_assumption_required", report.reason_codes)

    def test_low_fact_weight_blocks(self):
        report = SemanticValidityGate().build(self._contract(), self._blind(), self._teacher(0.59), "blocking")
        self.assertIn("rubric_weight_imbalance", report.reason_codes)

    def test_uncorroborated_llm_blocker_requires_secondary(self):
        finding = SemanticFinding(
            finding_code="ambiguous_requirement",
            severity="blocking",
            message="two reasonable interpretations",
            confidence=0.9,
        )
        report = SemanticValidityGate().build(self._contract(), self._blind([finding]), self._teacher(), "blocking")
        self.assertEqual(report.decision, "needs_secondary_review")
        self.assertTrue(report.secondary_review_required)

    def test_blind_package_rejects_teacher_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forbidden = root / "rubric.json"
            forbidden.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                SemanticReviewPackageBuilder().build_blind_package(
                    "task_1", "prompt", {"out.xlsx": ["requirement"]}, [forbidden], root / "package.json"
                )

    def test_blind_package_contains_no_teacher_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "input.txt"
            reference.write_text("candidate data", encoding="utf-8")
            path = root / "package.json"
            SemanticReviewPackageBuilder().build_blind_package(
                "task_1", "prompt", {"out.xlsx": ["requirement"]}, [reference], path
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(payload).lower()
            self.assertNotIn("golden_run_payload", text)
            self.assertNotIn("answer_key_payload", text)
            self.assertEqual(payload["reference_files"][0]["file_name"], "input.txt")

    def test_pipeline_stage_and_permissions_are_frozen(self):
        self.assertEqual(
            STAGE_ORDER,
            ["source_to_skills", "registry_prepare", "task_generation", "semantic_validation", "production_review", "rw_task_eval"],
        )
        request = EndToEndRequest(run_id="test", selected_stages=["semantic_validation"])
        self.assertEqual(request.semantic_review_mode, "disabled")
        self.assertFalse(request.semantic_review_execute)
        self.assertFalse(request.allow_external_semantic_review)

    def test_revision_is_versioned_and_invalidates_downstream(self):
        finding = SemanticFinding(
            finding_code="missing_candidate_input",
            severity="blocking",
            message="missing input",
            deterministic_corroboration=True,
        )
        plan = SemanticRevisionController().plan_revision("task", 0, [finding])
        self.assertTrue(plan["next_revision_dir"].endswith("revision_01"))
        self.assertFalse(plan["in_place_edit_allowed"])
        self.assertIn("reference_files", plan["invalidated_artifacts"])
        self.assertIn("production_qa", plan["invalidated_artifacts"])

    def test_revision_stops_after_two_attempts(self):
        plan = SemanticRevisionController().plan_revision("task", 2, [])
        self.assertEqual(plan["decision"], "blocked")
        self.assertIsNone(plan["next_revision_dir"])

    def test_legacy_contract_does_not_certify_teacher_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "transactions.xlsx"
            reference.write_bytes(b"placeholder")
            contract = SemanticContractDraftBuilder().build_from_legacy_dataset(
                {
                    "task_id": "legacy_1",
                    "prompt": "Visible requirements:\n- Classify each exception.\nReference files:\n- transactions.xlsx",
                    "deliverable_files": ["deliverable_files/out.xlsx"],
                },
                [reference],
            )
            self.assertEqual(contract.task_id, "legacy_1")
            self.assertEqual(len(contract.requirements), 1)
            self.assertEqual(contract.claims[0].determinism, "judgmental")
            self.assertIn("does not certify teacher truth", contract.notes[0])

    def test_finding_code_is_exposed_as_json_schema_enum(self):
        schema = CandidateBlindReview.model_json_schema()
        finding_ref = schema["$defs"]["SemanticFinding"]["properties"]["finding_code"]
        self.assertIn("missing_candidate_input", finding_ref["enum"])
        self.assertIn("rubric_weight_imbalance", finding_ref["enum"])

    def test_compact_secondary_agreement_confirms_revision(self):
        finding = SemanticFinding(
            finding_code="ambiguous_requirement",
            severity="blocking",
            message="two interpretations",
            requirement_id="req_1",
        )
        secondary = SecondarySemanticReview(
            task_id="task_1",
            review_scope="candidate_blind",
            model="gpt-5.4-pro",
            provider="tuzi",
            created_at="now",
            decisions=[SecondaryFindingDecision(
                requirement_id="req_1",
                finding_family="decision_ambiguity",
                material=True,
                confidence=0.9,
                rationale="Both interpretations remain candidate-visible.",
            )],
        )
        report = SemanticValidityGate().build(
            self._contract(), self._blind([finding]), self._teacher(), "blocking",
            secondary_compact_reviews=[secondary],
        )
        self.assertEqual(report.decision, "revise")

    def test_deterministic_family_does_not_require_secondary(self):
        finding = SemanticFinding(
            finding_code="missing_candidate_input",
            severity="blocking",
            message="missing field",
            requirement_id="req_1",
        )
        deterministic = SemanticFinding(
            finding_code="missing_candidate_input",
            severity="blocking",
            message="header check confirmed missing field",
            deterministic_corroboration=True,
        )
        report = SemanticValidityGate().build(
            self._contract(), self._blind([finding]), self._teacher(), "blocking",
            deterministic_findings=[deterministic],
        )
        self.assertEqual(report.decision, "revise")
        self.assertFalse(report.secondary_review_required)


if __name__ == "__main__":
    unittest.main()
