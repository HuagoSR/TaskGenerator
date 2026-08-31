from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.core.deliverable_contract import DeliverableContractCompiler
from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1, TaskDecisionMatrixV1
from task_generator.planning.scenario_task_compiler import (
    ScenarioTaskAdmissionValidator,
    ScenarioTaskCompilationPlanV1,
    ScenarioTaskCompilationPlanV2,
    ScenarioTaskSpecV1,
    TaskCompilationOutputV1,
    TaskSpecificRubricV1,
    TeacherTruthPointV1,
    tree_sha256,
    compiler_prompt,
)


def _bible() -> ScenarioBibleV1:
    return ScenarioBibleV1.model_validate({
        "scenario_id": "scenario-audit", "work_seed_id": "seed-audit", "rule_set_id": "rules-audit", "organization_name": "Example Co",
        "roles": [{"role_id": "senior", "title": "Audit Senior", "authorities": ["document evidence"]}],
        "facts": [
            {"fact_id": "f1", "kind": "normal_background", "statement": "The client provided a report.", "occurred_at": 1},
            {"fact_id": "f2", "kind": "open_issue", "statement": "The source population is not available.", "occurred_at": 2, "knowledge": "unresolved", "rule_ids": ["rule-1"]},
        ],
        "correct_treatments": ["Obtain corroborating evidence before relying on the report."],
    })


def _rules() -> ProfessionalRuleSetV1:
    return ProfessionalRuleSetV1.model_validate({
        "rule_set_id": "rules-audit", "domain": "audit_compliance", "rules": [{
            "rule_id": "rule-1", "title": "Reliable evidence", "source_refs": [{"source_id": "s", "normalized_source_id": "n", "block_ids": ["b"], "locator": "https://example.test/rule", "abstraction_note": "method only"}],
            "applicability_conditions": ["report used as evidence"], "evidence_requirements": ["corroborate"], "forbidden_assumptions": ["report is self-validating"], "acceptable_handling": ["follow up"],
        }],
    })


def _output() -> TaskCompilationOutputV1:
    points = []
    truth = []
    criteria = []
    for number in range(1, 4):
        decision_id = f"d{number}"
        points.append({
            "decision_id": decision_id, "question": f"Assess issue {number}.",
            "evidence_refs": [{"artifact_id": "report.txt", "record_id": "whole_document", "field_names": ["content"]}],
            "rule_ids": ["rule-1"], "skill_ids": ["r10.audit-evidence-reliability"], "acceptable_conclusions": ["The evidence needs corroboration."],
            "major_errors": ["Treat the report as self-validating."], "allowed_uncertainty_conclusions": ["Evidence is insufficient pending follow-up."], "required_follow_up_actions": ["Request source population."],
        })
        truth.append(TeacherTruthPointV1(decision_id=decision_id, conclusion="Evidence is not sufficient alone.", evidence_paths=["report.txt"], fact_ids=["f1", "f2"], rule_ids=["rule-1"], required_follow_up_actions=["Request source population."]))
        criteria.append({"criterion_id": f"c{number}", "decision_id": decision_id, "weight": 1 / 3, "description": "Documents a supported professional judgment.", "major_error_blocks_credit": True})
    return TaskCompilationOutputV1(
        base_prompt="You are an audit senior. Review the client records and prepare a concise workpaper for the audit manager explaining the reliability of the evidence and the procedures still needed.",
        teacher_truth=truth,
        decision_matrix=TaskDecisionMatrixV1(scenario_id="scenario-audit", decision_points=points),
        task_specific_rubric=TaskSpecificRubricV1(criteria=criteria),
    )


class ScenarioTaskCompilerTests(unittest.TestCase):
    def _spec(self, candidate: Path) -> ScenarioTaskSpecV1:
        contract = DeliverableContractCompiler().build(case_id="task-audit", deliverable_specs=[{"file_name": "audit_evidence_workpaper.xlsx", "format": "xlsx"}])
        return ScenarioTaskSpecV1(task_id="task-audit", scenario_id="scenario-audit", domain="audit_compliance", parent_bundle_sha256="a" * 64, candidate_tree_sha256=tree_sha256(candidate), skill_id="r10.audit-evidence-reliability", deliverable_contract=contract)

    def _package(self, root: Path) -> tuple[Path, ScenarioTaskSpecV1, TaskCompilationOutputV1]:
        package = root / "package"
        candidate = package / "reference_files"
        candidate.mkdir(parents=True)
        (candidate / "report.txt").write_text("The controller supplied a revenue report.", encoding="utf-8")
        frozen = package / "_frozen_candidate"
        frozen.mkdir()
        (frozen / "report.txt").write_text("The controller supplied a revenue report.", encoding="utf-8")
        spec, output = self._spec(candidate), _output()
        prompt = DeliverableContractCompiler().compile_prompt(output.base_prompt, spec.deliverable_contract)
        (package / "TASK.md").write_text(prompt, encoding="utf-8")
        (package / "teacher").mkdir()
        (package / "teacher" / "scenario_extension.json").write_text(json.dumps({"facts": []}), encoding="utf-8")
        (package / "teacher" / "evidence_map.json").write_text(json.dumps({"artifacts": [{"path": "candidate/report.txt", "fact_ids": ["f1", "f2"]}]}), encoding="utf-8")
        return package, spec, output

    def test_valid_package_passes_hard_admission(self):
        with tempfile.TemporaryDirectory() as root:
            package, spec, output = self._package(Path(root))
            report = ScenarioTaskAdmissionValidator().validate(spec=spec, package_root=package, bible=_bible(), rules=_rules(), output=output)
        self.assertEqual(report.decision, "pass")

    def test_candidate_mutation_and_prompt_leakage_are_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            package, spec, output = self._package(Path(root))
            (package / "reference_files" / "report.txt").write_text("Changed.", encoding="utf-8")
            (package / "TASK.md").write_text("Read teacher/scenario_bible.json and submit deliverable_files/audit_evidence_workpaper.xlsx.", encoding="utf-8")
            report = ScenarioTaskAdmissionValidator().validate(spec=spec, package_root=package, bible=_bible(), rules=_rules(), output=output)
        self.assertEqual(report.decision, "blocked")
        self.assertEqual({item.code for item in report.findings if not item.passed}, {"candidate_bundle_unchanged", "prompt_answer_and_teacher_leakage_absent"})

    def test_plan_requires_cross_domain_pair(self):
        with tempfile.TemporaryDirectory() as root:
            candidate = Path(root) / "candidate"
            candidate.mkdir()
            (candidate / "report.txt").write_text("x", encoding="utf-8")
            spec = self._spec(candidate)
            with self.assertRaises(ValueError):
                ScenarioTaskCompilationPlanV1(tasks=[spec, spec.model_copy(update={"task_id": "second"})])

    def test_v2_plan_accepts_a_bounded_single_domain_batch_but_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as root:
            candidate = Path(root) / "candidate"
            candidate.mkdir()
            (candidate / "report.txt").write_text("x", encoding="utf-8")
            spec = self._spec(candidate)
            self.assertEqual(len(ScenarioTaskCompilationPlanV2(tasks=[spec]).tasks), 1)
            with self.assertRaises(ValueError):
                ScenarioTaskCompilationPlanV2(tasks=[spec, spec])

    def test_teacher_matrix_and_rubric_must_align(self):
        payload = _output().model_dump(mode="json")
        payload["task_specific_rubric"]["criteria"][0]["decision_id"] = "unknown"
        with self.assertRaises(ValueError):
            TaskCompilationOutputV1.model_validate(payload)

    def test_teacher_truth_may_reference_registered_derived_fact(self):
        with tempfile.TemporaryDirectory() as root:
            package, spec, output = self._package(Path(root))
            (package / "teacher" / "scenario_extension.json").write_text(json.dumps({"facts": [{"fact_id": "fact_ext_1", "statement": "The export lacks report parameters."}]}), encoding="utf-8")
            (package / "teacher" / "evidence_map.json").write_text(json.dumps({"artifacts": [{"path": "candidate/report.txt", "fact_ids": ["f1", "f2", "fact_ext_1"]}]}), encoding="utf-8")
            truth = list(output.teacher_truth)
            truth[0] = truth[0].model_copy(update={"fact_ids": ["f1", "fact_ext_1"]})
            output = output.model_copy(update={"teacher_truth": truth})
            report = ScenarioTaskAdmissionValidator().validate(spec=spec, package_root=package, bible=_bible(), rules=_rules(), output=output)
        self.assertEqual(report.decision, "pass")

    def test_teacher_truth_is_blocked_when_a_fact_is_not_projected_to_its_visible_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            package, spec, output = self._package(Path(root))
            (package / "teacher" / "evidence_map.json").write_text(json.dumps({"artifacts": [{"path": "candidate/report.txt", "fact_ids": ["f1"]}]}), encoding="utf-8")
            report = ScenarioTaskAdmissionValidator().validate(spec=spec, package_root=package, bible=_bible(), rules=_rules(), output=output)
        self.assertEqual(report.decision, "blocked")
        finding = next(item for item in report.findings if item.code == "teacher_truth_references_closed")
        self.assertIn("f2", finding.details["invisible_fact_ids"])

    def test_teacher_truth_accepts_candidate_prefixed_evidence_path(self):
        with tempfile.TemporaryDirectory() as root:
            package, spec, output = self._package(Path(root))
            truth = [item.model_copy(update={"evidence_paths": [f"candidate/{path}" for path in item.evidence_paths]}) for item in output.teacher_truth]
            output = output.model_copy(update={"teacher_truth": truth})
            report = ScenarioTaskAdmissionValidator().validate(spec=spec, package_root=package, bible=_bible(), rules=_rules(), output=output)
        self.assertEqual(report.decision, "pass")

    def test_compiler_prompt_uses_domain_and_loaded_skill_context(self):
        with tempfile.TemporaryDirectory() as root:
            candidate = Path(root) / "candidate"
            candidate.mkdir()
            (candidate / "report.txt").write_text("x", encoding="utf-8")
            spec = self._spec(candidate).model_copy(update={"skill_id": "r10.audit-control-deficiency-evaluation"})
            self.assertIn("Construct an audit work task", compiler_prompt(spec=spec))
            procurement = spec.model_copy(update={"domain": "procurement_operations", "skill_id": "r10.procurement-delivery-acceptance"})
            self.assertIn("Construct a procurement work task", compiler_prompt(spec=procurement))


if __name__ == "__main__":
    unittest.main()
