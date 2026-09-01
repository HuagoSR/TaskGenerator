"""Thin R10.6 task/truth compilation contracts and static admission.

The compiler consumes a frozen derived evidence bundle.  It never authors or
edits candidate evidence: its only semantic output is teacher-only task
supervision.  Delivery paths remain program-controlled through the existing
DeliverableContract.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from task_generator.core.deliverable_contract import DeliverableContractV1, DeliverableContractValidator
from task_generator.core.scenario_first import (
    ProfessionalRuleSetV1,
    ScenarioBibleV1,
    ScenarioFirstModel,
    TaskDecisionMatrixV1,
)
from task_generator.planning.scenario_evidence_experiment import ScenarioExtensionRegistryV1


TaskCompilationDecision = Literal["pass", "blocked", "incomplete"]
_FORBIDDEN_CANDIDATE_TEXT = (
    "professional_skill", "scenario_bible", "correct treatment", "correct_treatment",
    "teacher/", "with_skill", "without_skill", "questionable", "requires follow up",
    "requires-follow-up", "requires_follow_up",
)


class TeacherTruthPointV1(ScenarioFirstModel):
    decision_id: str = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    evidence_paths: list[str] = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    required_follow_up_actions: list[str] = Field(min_length=1)


class TaskSpecificRubricCriterionV1(ScenarioFirstModel):
    criterion_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    weight: float = Field(gt=0, le=1)
    description: str = Field(min_length=1)
    major_error_blocks_credit: bool = True


class TaskSpecificRubricV1(ScenarioFirstModel):
    rubric_version: Literal["r10.task_specific_rubric.1"] = "r10.task_specific_rubric.1"
    criteria: list[TaskSpecificRubricCriterionV1] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def validate_unique_criteria_and_weights(self) -> "TaskSpecificRubricV1":
        ids = [item.criterion_id for item in self.criteria]
        decisions = [item.decision_id for item in self.criteria]
        if len(ids) != len(set(ids)) or len(decisions) != len(set(decisions)):
            raise ValueError("duplicate_task_specific_rubric_criterion")
        if abs(sum(item.weight for item in self.criteria) - 1.0) > 0.00001:
            raise ValueError("task_specific_rubric_weights_must_sum_to_one")
        return self


class TaskCompilationOutputV1(ScenarioFirstModel):
    output_version: Literal["r10.task_compilation_output.1"] = "r10.task_compilation_output.1"
    base_prompt: str = Field(min_length=80)
    teacher_truth: list[TeacherTruthPointV1] = Field(min_length=3, max_length=5)
    decision_matrix: TaskDecisionMatrixV1
    task_specific_rubric: TaskSpecificRubricV1

    @model_validator(mode="after")
    def require_aligned_teacher_material(self) -> "TaskCompilationOutputV1":
        decision_ids = [item.decision_id for item in self.decision_matrix.decision_points]
        truth_ids = [item.decision_id for item in self.teacher_truth]
        rubric_ids = [item.decision_id for item in self.task_specific_rubric.criteria]
        if len(truth_ids) != len(set(truth_ids)):
            raise ValueError("duplicate_teacher_truth_decision")
        if set(truth_ids) != set(decision_ids) or set(rubric_ids) != set(decision_ids):
            raise ValueError("task_compilation_decision_alignment_invalid")
        return self


class ScenarioTaskSpecV1(ScenarioFirstModel):
    task_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    domain: Literal["audit_compliance", "procurement_operations"]
    parent_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    skill_id: str = Field(min_length=1)
    deliverable_contract: DeliverableContractV1


class ScenarioTaskCompilationPlanV1(ScenarioFirstModel):
    plan_version: Literal["r10.scenario_task_compilation_plan.1"] = "r10.scenario_task_compilation_plan.1"
    tasks: list[ScenarioTaskSpecV1] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_audit_and_procurement_pair(self) -> "ScenarioTaskCompilationPlanV1":
        ids = [item.task_id for item in self.tasks]
        domains = {item.domain for item in self.tasks}
        if len(ids) != len(set(ids)) or domains != {"audit_compliance", "procurement_operations"}:
            raise ValueError("r10_task_compilation_requires_unique_cross_domain_pair")
        return self


class ScenarioTaskCompilationPlanV2(ScenarioFirstModel):
    """A bounded production cohort; V1 remains the immutable two-task pilot."""

    plan_version: Literal["r10.scenario_task_compilation_plan.2"] = "r10.scenario_task_compilation_plan.2"
    tasks: list[ScenarioTaskSpecV1] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def require_unique_task_ids(self) -> "ScenarioTaskCompilationPlanV2":
        ids = [item.task_id for item in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("r10_task_compilation_task_ids_not_unique")
        return self


class ScenarioTaskCompilationScopeV1(ScenarioFirstModel):
    scope_version: Literal["r10.scenario_task_compilation_scope.1"] = "r10.scenario_task_compilation_scope.1"
    campaign_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image: str = Field(min_length=1)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiler_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    task_attempt_limit: Literal[2] = 2
    private_upload_authorization_required: Literal[True] = True
    excluded_actions: list[str] = Field(default_factory=lambda: ["candidate_evidence_mutation", "solver", "grader", "release", "training", "registry_mutation"])


class TaskAdmissionFindingV1(ScenarioFirstModel):
    code: str = Field(min_length=1)
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ScenarioTaskAdmissionReportV1(ScenarioFirstModel):
    report_version: Literal["r10.scenario_task_admission_report.1"] = "r10.scenario_task_admission_report.1"
    task_id: str = Field(min_length=1)
    decision: TaskCompilationDecision
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    findings: list[TaskAdmissionFindingV1] = Field(default_factory=list)
    first_failure: str | None = None


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def productive_workload_rubric_errors(output: TaskCompilationOutputV1) -> list[str]:
    """Small extra gate for the R10 compiler-revision experiment only.

    The stable V1 contract intentionally remains readable for the frozen pilot.
    This helper is opt-in so its clearer scoring-boundary requirement cannot
    invalidate historical packages.
    """

    errors: list[str] = []
    for criterion in output.task_specific_rubric.criteria:
        description = criterion.description.casefold()
        if not all(token in description for token in ("met:", "partial:", "not met:")):
            errors.append(f"rubric_boundary_missing:{criterion.criterion_id}")
    major_errors = [error.casefold().strip() for point in output.decision_matrix.decision_points for error in point.major_errors]
    if len(major_errors) != len(set(major_errors)):
        errors.append("decision_matrix_major_error_duplicate")
    return errors


def compile_scope(*, campaign_id: str, source_commit: str, plan: ScenarioTaskCompilationPlanV1 | ScenarioTaskCompilationPlanV2, image: str, image_sha256: str) -> ScenarioTaskCompilationScopeV1:
    return ScenarioTaskCompilationScopeV1(campaign_id=campaign_id, source_commit=source_commit, plan_sha256=plan.canonical_sha256(), image=image, image_sha256=image_sha256)


class ScenarioTaskAdmissionValidator:
    """Verify hard package boundaries without judging a preferred answer."""

    def validate(
        self,
        *,
        spec: ScenarioTaskSpecV1,
        package_root: Path,
        bible: ScenarioBibleV1,
        rules: ProfessionalRuleSetV1,
        output: TaskCompilationOutputV1,
    ) -> ScenarioTaskAdmissionReportV1:
        findings: list[TaskAdmissionFindingV1] = []
        add = lambda code, passed, **details: findings.append(TaskAdmissionFindingV1(code=code, passed=passed, details=details))
        candidate_root = package_root / "reference_files"
        original_root = package_root / "_frozen_candidate"
        candidate_ok = candidate_root.is_dir() and original_root.is_dir() and tree_sha256(candidate_root) == tree_sha256(original_root) == spec.candidate_tree_sha256
        add("candidate_bundle_unchanged", candidate_ok)
        teacher_root = package_root / "teacher"
        isolation_ok = teacher_root.is_dir() and not any(path.is_relative_to(candidate_root) for path in teacher_root.rglob("*"))
        add("candidate_teacher_isolation", isolation_ok)
        prompt = (package_root / "TASK.md").read_text(encoding="utf-8") if (package_root / "TASK.md").is_file() else ""
        forbidden = sorted(token for token in _FORBIDDEN_CANDIDATE_TEXT if token in prompt.casefold())
        add("prompt_answer_and_teacher_leakage_absent", not forbidden, tokens=forbidden)
        contract = spec.deliverable_contract
        contract_report = DeliverableContractValidator().validate(contract, prompt, [path.relative_to(candidate_root).as_posix() for path in candidate_root.rglob("*") if path.is_file()])
        add("deliverable_contract_compiled", contract_report.validation_status == "pass", blocking_count=contract_report.blocking_count)
        fact_ids = {fact.fact_id for fact in bible.facts}
        extension_ids: set[str] = set()
        extension_valid = True
        try:
            extension = ScenarioExtensionRegistryV1.model_validate_json((teacher_root / "scenario_extension.json").read_text(encoding="utf-8"))
            extension_ids = {fact.fact_id for fact in extension.facts}
        except Exception:
            extension_valid = False
        allowed_fact_ids = fact_ids | extension_ids
        fact_paths: dict[str, set[str]] = {}
        evidence_map_valid = True
        try:
            evidence_map = json.loads((teacher_root / "evidence_map.json").read_text(encoding="utf-8"))
            for artifact in evidence_map["artifacts"]:
                path = str(artifact["path"])
                if not path.startswith("candidate/"):
                    raise ValueError("evidence_map_candidate_path_invalid")
                candidate_path = path.removeprefix("candidate/")
                for fact_id in artifact["fact_ids"]:
                    fact_paths.setdefault(str(fact_id), set()).add(candidate_path)
        except Exception:
            evidence_map_valid = False
        rule_ids = {rule.rule_id for rule in rules.rules}
        candidate_names = {path.name for path in candidate_root.rglob("*") if path.is_file()}
        evidence_paths = {path.relative_to(candidate_root).as_posix() for path in candidate_root.rglob("*") if path.is_file()}
        normalized_truth_paths = {
            path: self._normalize_candidate_path(path)
            for item in output.teacher_truth for path in item.evidence_paths
        }
        invalid_truth_facts = sorted({fact_id for item in output.teacher_truth for fact_id in item.fact_ids if fact_id not in allowed_fact_ids})
        invalid_truth_rules = sorted({rule_id for item in output.teacher_truth for rule_id in item.rule_ids if rule_id not in rule_ids})
        invalid_truth_paths = sorted({path for path, normalized in normalized_truth_paths.items() if normalized not in evidence_paths})
        invisible_truth_facts = sorted({fact_id for item in output.teacher_truth for fact_id in item.fact_ids if not ({normalized_truth_paths[path] for path in item.evidence_paths} & fact_paths.get(fact_id, set()))})
        truth_ok = extension_valid and evidence_map_valid and not invalid_truth_facts and not invalid_truth_rules and not invalid_truth_paths and not invisible_truth_facts
        add("teacher_truth_references_closed", truth_ok, extension_registry_valid=extension_valid, evidence_map_valid=evidence_map_valid, invalid_fact_ids=invalid_truth_facts, invalid_rule_ids=invalid_truth_rules, invalid_evidence_paths=invalid_truth_paths, invisible_fact_ids=invisible_truth_facts)
        matrix = output.decision_matrix
        matrix_ok = matrix.scenario_id == bible.scenario_id and 3 <= len(matrix.decision_points) <= 5 and all(
            set(point.rule_ids) <= rule_ids and point.skill_ids == [spec.skill_id]
            and all(ref.artifact_id in candidate_names and ref.record_id == "whole_document" and ref.field_names == ["content"] for ref in point.evidence_refs)
            for point in matrix.decision_points
        )
        add("decision_matrix_references_closed", matrix_ok)
        uncertainty_needed = any(fact.knowledge == "unresolved" for fact in bible.facts)
        uncertainty_ok = not uncertainty_needed or any(point.allowed_uncertainty_conclusions for point in matrix.decision_points)
        add("supported_uncertainty_preserved", uncertainty_ok)
        rubric_ok = len(output.task_specific_rubric.criteria) == len(matrix.decision_points)
        add("task_specific_rubric_aligned", rubric_ok)
        decision = "pass" if all(item.passed for item in findings) else "blocked"
        return ScenarioTaskAdmissionReportV1(task_id=spec.task_id, decision=decision, output_sha256=output.canonical_sha256(), findings=findings)

    @staticmethod
    def _normalize_candidate_path(value: str) -> str:
        return value.replace("\\", "/").removeprefix("candidate/")


def compiler_prompt(*, spec: ScenarioTaskSpecV1, productive_workload: bool = False) -> str:
    deliverable = spec.deliverable_contract.deliverables[0]
    domain_instruction = (
        "Construct an audit work task. The candidate must reach supportable conclusions from visible evidence, preserve evidence limits, and propose consequential follow-up procedures."
        if spec.domain == "audit_compliance"
        else "Construct a procurement work task. The candidate must reach supportable conclusions from visible evidence, preserve evidence limits and authorization boundaries, and document consequential follow-up procedures. Do not ask the candidate to select a supplier."
    )
    workload_instruction = """
The candidate-facing assignment must name a real business outcome and its audience, then direct the candidate to inspect the available work records. Do not enumerate each hidden discrepancy, prescribe the preferred conclusion, or turn the prompt into a checklist of teacher decisions. Ask for a usable work product that shows evidence traceability, necessary reconciliation or analysis, appropriately bounded conclusions, and consequential follow-up.

The decision points are teacher-only. Make them independently observable from candidate-visible evidence. Their major errors must be concrete wrong actions or unsupported claims, not vague quality concerns. In every rubric description, state `Met:`, `Partial:`, and `Not met:` boundaries. Presentation quality may support usability but must never compensate for a missed core professional judgment.
""" if productive_workload else ""
    return f"""You are a factory-side R10 task compiler. Read only teacher/ inputs. Do not edit reference_files/ or _frozen_candidate/.

{domain_instruction}

{workload_instruction}

Write exactly one JSON object to teacher/task_compilation.json with this shape:
{{
  "output_version": "r10.task_compilation_output.1",
  "base_prompt": "candidate-facing role, trigger, business audience, evidence files to inspect, substantive analysis work, and requested professional output; do not mention teacher material, rules, Skills, answer keys, or the final correct conclusion",
  "teacher_truth": [{{"decision_id":"...","conclusion":"...","evidence_paths":["file"],"fact_ids":["..."],"rule_ids":["..."],"required_follow_up_actions":["..."]}}],
  "decision_matrix": {{"contract_version":"r10.task_decision_matrix.1","scenario_id":"{spec.scenario_id}","decision_points":[{{"decision_id":"...","question":"...","evidence_refs":[{{"artifact_id":"candidate file basename","record_id":"whole_document","field_names":["content"]}}],"rule_ids":["..."],"skill_ids":["{spec.skill_id}"],"acceptable_conclusions":["..."],"major_errors":["..."],"allowed_uncertainty_conclusions":["..."],"required_follow_up_actions":["..."]}}]}},
  "task_specific_rubric": {{"rubric_version":"r10.task_specific_rubric.1","criteria":[{{"criterion_id":"...","decision_id":"...","weight":0.25,"description":"Met: ... Partial: ... Not met: ...","major_error_blocks_credit":true}}]}}
}}

Use three to five decision points and one rubric criterion per decision point; weights must sum exactly to 1.0. Cite only visible reference file basenames in evidence refs. In each teacher-truth item, cite only Bible or extension fact IDs that the supplied evidence_map projects into that item's listed visible evidence paths; do not cite teacher-only policy, consequence, treatment, or unseen background facts as factual support. Acknowledging insufficient evidence and requesting follow-up is valid when justified. The candidate's final deliverable must be a {deliverable.format.upper()} named `{deliverable.file_name}`; do not write it yourself.
"""
