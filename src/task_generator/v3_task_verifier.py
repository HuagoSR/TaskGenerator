from collections import Counter
from pathlib import Path
import re
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field

from task_generator.v2_schema import TaskBlueprint
from task_generator.v3_global_task_validity import (
    ExecutionPlanDAGReport,
    TaskConstraintGraphReport,
)
from task_generator.v3_pipeline_b_quality_gate import PipelineBQualityReport
from task_generator.v3_rubric_builder import (
    DOSSIER_DIAGNOSTIC_SIGNALS,
    PIPELINE_A_DIAGNOSTIC_SIGNALS,
    RubricArtifact,
    RubricCriterion,
)
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_teacher_input_builder import TeacherInputManifest
from task_generator.v3_teacher_runner import GoldenRun


VerifierSeverity = Literal["blocking", "revise", "warning"]
VerifierStatus = Literal["blocking", "revise", "pass"]


class TaskVerifierRequest(BaseModel):
    blueprint_path: str
    teacher_input_manifest_path: str
    golden_run_path: str
    rubric_path: str
    task_constraint_graph_report_path: str
    execution_plan_dag_report_path: str
    quality_report_path: Optional[str] = None
    output_dir: str


class TaskVerifierFinding(BaseModel):
    finding_id: str
    check_name: str
    reason_code: str
    severity: VerifierSeverity
    message: str
    artifact_refs: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class TaskVerifierDiagnostics(BaseModel):
    finding_count: int = 0
    blocking_count: int = 0
    revise_count: int = 0
    warning_count: int = 0
    candidate_visible_evidence_count: int = 0
    golden_step_count: int = 0
    final_check_count: int = 0
    candidate_rubric_criterion_count: int = 0
    diagnostic_rubric_criterion_count: int = 0
    reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TaskVerifierReport(BaseModel):
    task_verifier_version: str = "v3.task_verifier.1"
    request: TaskVerifierRequest
    blueprint_id: str
    case_id: str
    diagnostic_only: bool = True
    verifier_status: VerifierStatus = "pass"
    findings: List[TaskVerifierFinding] = Field(default_factory=list)
    diagnostics: TaskVerifierDiagnostics
    notes: List[str] = Field(default_factory=list)


class TaskVerifier:
    """Deterministic structural verifier for current Pipeline B artifacts."""

    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "by",
        "do",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "use",
        "with",
        "must",
        "should",
        "your",
    }

    def build(
        self,
        blueprint_path: str | Path,
        teacher_input_manifest_path: str | Path,
        golden_run_path: str | Path,
        rubric_path: str | Path,
        task_constraint_graph_report_path: str | Path,
        execution_plan_dag_report_path: str | Path,
        output_dir: str | Path,
        quality_report_path: Optional[str | Path] = None,
    ) -> TaskVerifierReport:
        request = TaskVerifierRequest(
            blueprint_path=str(blueprint_path),
            teacher_input_manifest_path=str(teacher_input_manifest_path),
            golden_run_path=str(golden_run_path),
            rubric_path=str(rubric_path),
            task_constraint_graph_report_path=str(task_constraint_graph_report_path),
            execution_plan_dag_report_path=str(execution_plan_dag_report_path),
            quality_report_path=str(quality_report_path) if quality_report_path else None,
            output_dir=str(output_dir),
        )

        blueprint = TaskBlueprint.model_validate(load_json_file(str(blueprint_path)))
        teacher_input = TeacherInputManifest.model_validate(load_json_file(str(teacher_input_manifest_path)))
        golden_run = GoldenRun.model_validate(load_json_file(str(golden_run_path)))
        rubric = RubricArtifact.model_validate(load_json_file(str(rubric_path)))
        task_constraint_graph = TaskConstraintGraphReport.model_validate(
            load_json_file(str(task_constraint_graph_report_path))
        )
        execution_plan_dag = ExecutionPlanDAGReport.model_validate(
            load_json_file(str(execution_plan_dag_report_path))
        )
        quality_report = (
            PipelineBQualityReport.model_validate(load_json_file(str(quality_report_path)))
            if quality_report_path
            else None
        )

        findings: List[TaskVerifierFinding] = []
        evidence_contract_ids = {item.evidence_id for item in teacher_input.teacher_view.evidence_contract}
        candidate_visible_evidence_ids = {
            item.evidence_id
            for item in teacher_input.teacher_view.evidence_contract
            if item.file_name in {file.file_name for file in teacher_input.candidate_view.reference_files}
        }
        policy_visible_evidence_ids = {
            item.evidence_id
            for item in teacher_input.teacher_view.evidence_contract
            if item.file_name == "policy_reference.docx"
            or item.semantic_type in {"policy_rule", "decision_rule"}
        }
        candidate_criteria = self._candidate_criteria(rubric)
        diagnostic_criteria = self._diagnostic_criteria(rubric)
        used_evidence_ids = self._golden_used_evidence_ids(golden_run)

        findings.extend(
            self._evidence_contract_findings(
                golden_run=golden_run,
                evidence_contract_ids=evidence_contract_ids,
            )
        )
        findings.extend(
            self._policy_support_findings(
                golden_run=golden_run,
                rubric=rubric,
                quality_report=quality_report,
                policy_visible_evidence_ids=policy_visible_evidence_ids,
            )
        )
        findings.extend(
            self._deliverable_coverage_findings(
                teacher_input=teacher_input,
                candidate_criteria=candidate_criteria,
            )
        )
        findings.extend(
            self._constraint_alignment_findings(
                task_constraint_graph=task_constraint_graph,
                execution_plan_dag=execution_plan_dag,
                candidate_criteria=candidate_criteria,
            )
        )
        findings.extend(
            self._candidate_rubric_hygiene_findings(
                candidate_criteria=candidate_criteria,
                candidate_visible_evidence_ids=candidate_visible_evidence_ids,
            )
        )
        findings.extend(
            self._rubric_evidence_usage_findings(
                candidate_criteria=candidate_criteria,
                used_evidence_ids=used_evidence_ids,
            )
        )

        diagnostics = self._diagnostics(
            findings=findings,
            candidate_visible_evidence_count=len(candidate_visible_evidence_ids),
            golden_step_count=len(golden_run.steps),
            final_check_count=len(golden_run.final_checks),
            candidate_rubric_criterion_count=len(candidate_criteria),
            diagnostic_rubric_criterion_count=len(diagnostic_criteria),
        )
        report = TaskVerifierReport(
            request=request,
            blueprint_id=blueprint.blueprint_id,
            case_id=self._infer_case_id(output_dir, blueprint.blueprint_id),
            diagnostic_only=True,
            verifier_status=self._status(findings),
            findings=findings,
            diagnostics=diagnostics,
            notes=[
                "TaskVerifier V1 is deterministic and report-only.",
                "Verifier findings do not change quality-gate, package, export, or sampler decisions in this slice.",
                "Use this report to distinguish unsupported-task structure from ordinary partial teacher readiness.",
            ],
        )
        return report

    def write_outputs(self, report: TaskVerifierReport, output_dir: str | Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "task_verifier_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {"task_verifier_report_path": str(report_path)}

    def _evidence_contract_findings(
        self,
        golden_run: GoldenRun,
        evidence_contract_ids: Set[str],
    ) -> List[TaskVerifierFinding]:
        findings: List[TaskVerifierFinding] = []
        for state in golden_run.intermediate_states:
            missing = sorted(set(state.required_evidence_ids) - evidence_contract_ids)
            if missing:
                findings.append(
                    self._finding(
                        check_name="evidence_contract_closure",
                        reason_code="missing_declared_evidence_reference",
                        severity="blocking",
                        message=f"Intermediate state `{state.state_name}` references evidence IDs outside the declared evidence contract.",
                        artifact_refs=["golden_run", "teacher_input_manifest"],
                        evidence_ids=missing,
                        details={"state_name": state.state_name},
                    )
                )
        for step in golden_run.steps:
            step_ids = [item.evidence_id for item in step.evidence_uses]
            missing = sorted(set(step_ids) - evidence_contract_ids)
            if missing:
                findings.append(
                    self._finding(
                        check_name="evidence_contract_closure",
                        reason_code="missing_declared_evidence_reference",
                        severity="blocking",
                        message=f"Golden step `{step.skill_name}` references evidence IDs outside the declared evidence contract.",
                        artifact_refs=["golden_run", "teacher_input_manifest"],
                        evidence_ids=missing,
                        details={"step_id": step.step_id, "skill_id": step.skill_id},
                    )
                )
            if step.status == "complete" and not step.evidence_uses:
                findings.append(
                    self._finding(
                        check_name="supported_complete_steps",
                        reason_code="unsupported_complete_step",
                        severity="blocking",
                        message=f"Golden step `{step.skill_name}` is marked complete without any evidence use.",
                        artifact_refs=["golden_run"],
                        details={"step_id": step.step_id, "skill_id": step.skill_id},
                    )
                )
        for check in golden_run.final_checks:
            missing = sorted(set(check.supporting_evidence_ids) - evidence_contract_ids)
            if missing:
                findings.append(
                    self._finding(
                        check_name="evidence_contract_closure",
                        reason_code="missing_declared_evidence_reference",
                        severity="blocking",
                        message=f"Final check `{check.check_name}` references evidence IDs outside the declared evidence contract.",
                        artifact_refs=["golden_run", "teacher_input_manifest"],
                        evidence_ids=missing,
                        details={"final_check": check.check_name},
                    )
                )
            if check.status == "pass" and not check.supporting_evidence_ids:
                findings.append(
                    self._finding(
                        check_name="supported_pass_final_checks",
                        reason_code="unsupported_pass_final_check",
                        severity="blocking",
                        message=f"Final check `{check.check_name}` passes without supporting evidence IDs.",
                        artifact_refs=["golden_run"],
                        details={"final_check": check.check_name},
                    )
                )
        return findings

    def _policy_support_findings(
        self,
        golden_run: GoldenRun,
        rubric: RubricArtifact,
        quality_report: Optional[PipelineBQualityReport],
        policy_visible_evidence_ids: Set[str],
    ) -> List[TaskVerifierFinding]:
        findings: List[TaskVerifierFinding] = []
        policy_checks = [check for check in golden_run.final_checks if check.check_name == "policy_clause_traceability"]
        policy_criteria = [criterion for criterion in self._candidate_criteria(rubric) if self._is_policy_sensitive(criterion)]
        if (policy_checks or policy_criteria) and not policy_visible_evidence_ids:
            findings.append(
                self._finding(
                    check_name="policy_visible_support",
                    reason_code="missing_policy_visible_support",
                    severity="blocking",
                    message="Policy-sensitive checks exist, but no candidate-visible policy clause evidence is available.",
                    artifact_refs=["golden_run", "rubric", "teacher_input_manifest"],
                    details={
                        "policy_final_check_count": len(policy_checks),
                        "policy_candidate_criterion_count": len(policy_criteria),
                    },
                )
            )
        quality_codes = set(quality_report.decision.reason_codes) if quality_report else set()
        for check in policy_checks:
            if check.status != "pass" or quality_codes.intersection({"relationship:policy_lookup", "deferred_policy_reference"}):
                findings.append(
                    self._finding(
                        check_name="policy_visible_support",
                        reason_code="policy_support_only_partial",
                        severity="revise",
                        message="Policy-sensitive verification remains partial and should not be treated as fully grounded yet.",
                        artifact_refs=["golden_run", "quality_report"] if quality_report else ["golden_run"],
                        evidence_ids=list(check.supporting_evidence_ids),
                        details={
                            "final_check_status": check.status,
                            "quality_reason_codes": sorted(
                                quality_codes.intersection({"relationship:policy_lookup", "deferred_policy_reference"})
                            ),
                        },
                    )
                )
        return findings

    def _deliverable_coverage_findings(
        self,
        teacher_input: TeacherInputManifest,
        candidate_criteria: List[RubricCriterion],
    ) -> List[TaskVerifierFinding]:
        findings: List[TaskVerifierFinding] = []
        deliverables = teacher_input.candidate_view.deliverables
        if deliverables and not candidate_criteria:
            findings.append(
                self._finding(
                    check_name="deliverable_rubric_coverage",
                    reason_code="deliverable_without_candidate_criteria",
                    severity="blocking",
                    message="Deliverable requirements exist, but the rubric contains no candidate-facing criteria.",
                    artifact_refs=["teacher_input_manifest", "rubric"],
                )
            )
            return findings

        criterion_tokens = [
            self._tokenize(f"{criterion.description} {criterion.pass_condition}")
            for criterion in candidate_criteria
        ]
        for deliverable in deliverables:
            for requirement in deliverable.get("requirements", []):
                required_tokens = self._tokenize(requirement)
                covered = any(len(required_tokens.intersection(tokens)) >= 2 for tokens in criterion_tokens)
                if not covered:
                    findings.append(
                        self._finding(
                            check_name="deliverable_rubric_coverage",
                            reason_code="deliverable_requirement_undercovered",
                            severity="revise",
                            message=f"Deliverable requirement is not clearly covered by candidate-facing rubric criteria: {requirement}",
                            artifact_refs=["teacher_input_manifest", "rubric"],
                            details={
                                "deliverable_file_name": deliverable.get("file_name"),
                                "requirement": requirement,
                            },
                        )
                    )
        return findings

    def _constraint_alignment_findings(
        self,
        task_constraint_graph: TaskConstraintGraphReport,
        execution_plan_dag: ExecutionPlanDAGReport,
        candidate_criteria: List[RubricCriterion],
    ) -> List[TaskVerifierFinding]:
        findings: List[TaskVerifierFinding] = []
        if not execution_plan_dag.dag_valid:
            findings.append(
                self._finding(
                    check_name="execution_plan_alignment",
                    reason_code="execution_dag_invalid",
                    severity="blocking",
                    message="Execution plan DAG is invalid and should not be treated as an executable teacher plan.",
                    artifact_refs=["execution_plan_dag_report"],
                    details={"validation_notes": execution_plan_dag.validation_notes},
                )
            )
        if task_constraint_graph.unsupported_required_nodes:
            findings.append(
                self._finding(
                    check_name="constraint_graph_alignment",
                    reason_code="unsupported_task_constraints",
                    severity="revise",
                    message="Task constraint graph contains required nodes that are not grounded in current artifacts.",
                    artifact_refs=["task_constraint_graph_report"],
                    details={"unsupported_required_nodes": task_constraint_graph.unsupported_required_nodes},
                )
            )
        candidate_text = " ".join(
            f"{criterion.section} {criterion.description} {criterion.pass_condition}"
            for criterion in candidate_criteria
        ).lower()
        for node in task_constraint_graph.nodes:
            if node.node_type != "deliverable_section":
                continue
            label_tokens = self._tokenize(node.label)
            if len(label_tokens.intersection(self._tokenize(candidate_text))) < 1:
                findings.append(
                    self._finding(
                        check_name="deliverable_section_mapping",
                        reason_code="deliverable_section_unmapped",
                        severity="revise",
                        message=f"Deliverable section node is not clearly mapped to candidate-facing rubric coverage: {node.label}",
                        artifact_refs=["task_constraint_graph_report", "rubric"],
                        details={"node_id": node.node_id, "label": node.label},
                    )
                )
        return findings

    def _candidate_rubric_hygiene_findings(
        self,
        candidate_criteria: List[RubricCriterion],
        candidate_visible_evidence_ids: Set[str],
    ) -> List[TaskVerifierFinding]:
        findings: List[TaskVerifierFinding] = []
        diagnostic_signals = set(PIPELINE_A_DIAGNOSTIC_SIGNALS).union(DOSSIER_DIAGNOSTIC_SIGNALS)
        for criterion in candidate_criteria:
            if criterion.export_to_rw_task and criterion.audience != "candidate":
                findings.append(
                    self._finding(
                        check_name="candidate_rubric_hygiene",
                        reason_code="candidate_rubric_exports_invisible_criterion",
                        severity="blocking",
                        message=f"Rubric criterion `{criterion.criterion_id}` is exportable but not candidate-facing.",
                        artifact_refs=["rubric"],
                        details={"criterion_id": criterion.criterion_id, "audience": criterion.audience},
                    )
                )
            offending_signals = sorted(set(criterion.failure_signals).intersection(diagnostic_signals))
            if offending_signals:
                findings.append(
                    self._finding(
                        check_name="candidate_rubric_hygiene",
                        reason_code="candidate_rubric_contains_diagnostic_signal",
                        severity="blocking",
                        message=f"Candidate-facing rubric criterion `{criterion.criterion_id}` contains diagnostic-only failure signals.",
                        artifact_refs=["rubric"],
                        details={"criterion_id": criterion.criterion_id, "failure_signals": offending_signals},
                    )
                )
            invisible = sorted(
                {
                    requirement.get("evidence_id", "")
                    for requirement in criterion.evidence_requirements
                    if requirement.get("evidence_id") and requirement.get("evidence_id") not in candidate_visible_evidence_ids
                }
            )
            if invisible:
                findings.append(
                    self._finding(
                        check_name="candidate_rubric_hygiene",
                        reason_code="candidate_rubric_evidence_not_visible",
                        severity="blocking",
                        message=f"Candidate-facing rubric criterion `{criterion.criterion_id}` requires non-visible evidence IDs.",
                        artifact_refs=["rubric", "teacher_input_manifest"],
                        evidence_ids=invisible,
                        details={"criterion_id": criterion.criterion_id},
                    )
                )
        return findings

    def _rubric_evidence_usage_findings(
        self,
        candidate_criteria: List[RubricCriterion],
        used_evidence_ids: Set[str],
    ) -> List[TaskVerifierFinding]:
        findings: List[TaskVerifierFinding] = []
        for criterion in candidate_criteria:
            required_ids = {
                requirement.get("evidence_id", "")
                for requirement in criterion.evidence_requirements
                if requirement.get("evidence_id")
            }
            unused = sorted(required_ids - used_evidence_ids)
            if unused:
                findings.append(
                    self._finding(
                        check_name="rubric_evidence_usage",
                        reason_code="rubric_requires_unused_evidence",
                        severity="revise",
                        message=f"Candidate-facing rubric criterion `{criterion.criterion_id}` requires evidence that GoldenRun never uses explicitly.",
                        artifact_refs=["rubric", "golden_run"],
                        evidence_ids=unused,
                        details={"criterion_id": criterion.criterion_id},
                    )
                )
        return findings

    def _candidate_criteria(self, rubric: RubricArtifact) -> List[RubricCriterion]:
        return [
            criterion
            for section in rubric.sections
            for criterion in section.criteria
            if criterion.audience == "candidate"
        ]

    def _diagnostic_criteria(self, rubric: RubricArtifact) -> List[RubricCriterion]:
        return [
            criterion
            for section in rubric.sections
            for criterion in section.criteria
            if criterion.audience != "candidate"
        ]

    def _golden_used_evidence_ids(self, golden_run: GoldenRun) -> Set[str]:
        used = set()
        for step in golden_run.steps:
            used.update(item.evidence_id for item in step.evidence_uses)
        for check in golden_run.final_checks:
            used.update(check.supporting_evidence_ids)
        return used

    def _is_policy_sensitive(self, criterion: RubricCriterion) -> bool:
        if criterion.section == "compliance_checks":
            return True
        haystack = " ".join(
            [
                criterion.description,
                criterion.pass_condition,
                " ".join(criterion.failure_signals),
                " ".join(req.get("semantic_type", "") for req in criterion.evidence_requirements),
            ]
        ).lower()
        return any(token in haystack for token in ["policy", "clause", "jurisdiction", "regulation"])

    def _diagnostics(
        self,
        findings: List[TaskVerifierFinding],
        candidate_visible_evidence_count: int,
        golden_step_count: int,
        final_check_count: int,
        candidate_rubric_criterion_count: int,
        diagnostic_rubric_criterion_count: int,
    ) -> TaskVerifierDiagnostics:
        severity_counts = Counter(item.severity for item in findings)
        return TaskVerifierDiagnostics(
            finding_count=len(findings),
            blocking_count=severity_counts.get("blocking", 0),
            revise_count=severity_counts.get("revise", 0),
            warning_count=severity_counts.get("warning", 0),
            candidate_visible_evidence_count=candidate_visible_evidence_count,
            golden_step_count=golden_step_count,
            final_check_count=final_check_count,
            candidate_rubric_criterion_count=candidate_rubric_criterion_count,
            diagnostic_rubric_criterion_count=diagnostic_rubric_criterion_count,
            reason_codes=sorted({item.reason_code for item in findings}),
            notes=[
                "Verifier V1 only performs deterministic structural checks.",
                "Unsupported conclusion is approximated by complete/pass artifacts that lack declared evidence support.",
            ],
        )

    def _status(self, findings: List[TaskVerifierFinding]) -> VerifierStatus:
        if any(item.severity == "blocking" for item in findings):
            return "blocking"
        if any(item.severity == "revise" for item in findings):
            return "revise"
        return "pass"

    def _tokenize(self, text: str) -> Set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token not in self.STOPWORDS and len(token) > 1
        }

    def _infer_case_id(self, output_dir: str | Path, blueprint_id: str) -> str:
        path = Path(output_dir)
        if path.name == "task_verifier":
            return path.parent.name
        return path.name or blueprint_id

    def _finding(
        self,
        check_name: str,
        reason_code: str,
        severity: VerifierSeverity,
        message: str,
        artifact_refs: Optional[List[str]] = None,
        evidence_ids: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> TaskVerifierFinding:
        raw = "|".join([check_name, reason_code, severity, message, ",".join(sorted(evidence_ids or []))])
        import hashlib

        return TaskVerifierFinding(
            finding_id=f"tvf_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}",
            check_name=check_name,
            reason_code=reason_code,
            severity=severity,
            message=message,
            artifact_refs=artifact_refs or [],
            evidence_ids=sorted(set(evidence_ids or [])),
            details=details or {},
        )
