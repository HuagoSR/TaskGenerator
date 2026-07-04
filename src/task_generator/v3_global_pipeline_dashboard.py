from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_a_substrate_audit import PipelineASubstrateAuditReport
from task_generator.v3_pipeline_b_batch_feedback_analyzer import PipelineBBatchFeedbackReport
from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunReport
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_typed_resource_patch_proposal import TypedResourcePatchProposalReport


OwnerLayer = Literal[
    "pipeline_a",
    "workflow_graph",
    "package_generation",
    "teacher_operationalization",
    "rubric_and_quality",
    "evaluation",
    "promotion_governance",
]
FocusPriority = Literal["high", "medium", "low"]


class GlobalPipelineDashboardRequest(BaseModel):
    batch_report_path: str
    batch_feedback_report_path: str
    substrate_audit_report_path: str
    typed_resource_patch_proposal_report_path: str
    promotion_report_path: Optional[str] = None
    output_dir: str


class DashboardArtifactSnapshot(BaseModel):
    case_id: str
    motif: str
    case_dir: str
    quality_decision: Optional[str] = None
    package_readiness: Optional[str] = None
    subgraph_confidence: Optional[str] = None
    workflow_context_fit: Optional[str] = None
    real_worldness_score: Optional[float] = None
    difficulty_overall: Optional[float] = None
    recommended_next_layer: Optional[str] = None
    execution_dag_valid: Optional[bool] = None
    unsupported_task_constraint_count: int = 0
    verifier_status: Optional[str] = None
    verifier_blocking_count: int = 0
    verifier_revise_count: int = 0
    verifier_reason_codes: List[str] = Field(default_factory=list)
    artifact_read_errors: List[str] = Field(default_factory=list)


class ScoreDistribution(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    low_count: int = 0
    medium_count: int = 0
    high_count: int = 0


class BatchHealthSummary(BaseModel):
    attempted_case_count: int = 0
    completed_case_count: int = 0
    failed_case_count: int = 0
    quality_decision_counts: Dict[str, int] = Field(default_factory=dict)
    package_readiness_counts: Dict[str, int] = Field(default_factory=dict)
    repeated_reason_codes: List[str] = Field(default_factory=list)
    motif_failure_distribution: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class PipelineASubstrateHealthSummary(BaseModel):
    audited_skill_count: int = 0
    missing_typed_resource_skill_count: int = 0
    weak_support_skill_count: int = 0
    transition_gap_skill_count: int = 0
    manual_resource_patch_candidate_count: int = 0
    new_source_evidence_candidate_count: int = 0
    typed_resource_promotion_candidate_count: int = 0
    eligible_typed_resource_promotion_count: int = 0
    applied_typed_resource_promotion_count: int = 0


class TaskRealismHealthSummary(BaseModel):
    real_worldness_case_count: int = 0
    real_worldness_score_distribution: ScoreDistribution = Field(default_factory=ScoreDistribution)
    business_context_plausibility_distribution: ScoreDistribution = Field(default_factory=ScoreDistribution)
    artifact_ecology_realism_distribution: ScoreDistribution = Field(default_factory=ScoreDistribution)
    anti_template_score_distribution: ScoreDistribution = Field(default_factory=ScoreDistribution)
    recommended_next_layer_counts: Dict[str, int] = Field(default_factory=dict)


class TaskExecutabilityHealthSummary(BaseModel):
    execution_dag_valid_case_count: int = 0
    execution_dag_invalid_case_count: int = 0
    unsupported_task_constraint_case_count: int = 0
    verifier_case_count: int = 0
    verifier_blocking_case_count: int = 0
    verifier_revise_case_count: int = 0
    verifier_reason_coverage: Dict[str, int] = Field(default_factory=dict)


class TrainingEvaluationReadinessSummary(BaseModel):
    candidate_ready_count: int = 0
    revise_only_count: int = 0
    draft_external_eval_candidate_count: int = 0
    verifier_pass_count: int = 0
    model_separation_evidence_count: int = 0
    promotion_ready_count: int = 0


class DashboardHealthSummary(BaseModel):
    batch_health: BatchHealthSummary
    pipeline_a_substrate_health: PipelineASubstrateHealthSummary
    task_realism_health: TaskRealismHealthSummary
    task_executability_health: TaskExecutabilityHealthSummary
    training_evaluation_readiness: TrainingEvaluationReadinessSummary


class DashboardFocusArea(BaseModel):
    focus_id: str
    owner_layer: OwnerLayer
    priority: FocusPriority
    title: str
    rationale: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    recommended_next_step: str


class GlobalPipelineDashboardDiagnostics(BaseModel):
    case_count: int = 0
    snapshot_count: int = 0
    snapshot_error_case_count: int = 0
    missing_global_validity_case_count: int = 0
    missing_verifier_case_count: int = 0
    missing_promotion_report: bool = False
    focus_area_count: int = 0
    artifact_read_errors: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GlobalPipelineDashboardReport(BaseModel):
    global_pipeline_dashboard_version: str = "v3.global_pipeline_dashboard.1"
    request: GlobalPipelineDashboardRequest
    case_snapshots: List[DashboardArtifactSnapshot] = Field(default_factory=list)
    health_summary: DashboardHealthSummary
    focus_areas: List[DashboardFocusArea] = Field(default_factory=list)
    diagnostics: GlobalPipelineDashboardDiagnostics
    notes: List[str] = Field(default_factory=list)


class GlobalPipelineDashboardBuilder:
    """Aggregate current report-first pipeline diagnostics into one global dashboard."""

    DOSSIER_REASON_CODES = {
        "dossier_missing_attachment_metadata",
        "dossier_conflict_source_metadata",
        "dossier_outdated_version_metadata",
        "dossier_manager_notes_metadata",
    }
    RUBRIC_REASON_CODES = {
        "deliverable_requirement_undercovered",
        "deliverable_section_unmapped",
        "deliverable_without_candidate_criteria",
        "candidate_rubric_exports_invisible_criterion",
        "candidate_rubric_contains_diagnostic_signal",
        "candidate_rubric_evidence_not_visible",
        "rubric_requires_unused_evidence",
    }
    TEACHER_REASON_CODES = {
        "missing_declared_evidence_reference",
        "unsupported_complete_step",
        "unsupported_pass_final_check",
    }
    LAYER_PRECEDENCE = {
        "pipeline_a": 0,
        "workflow_graph": 1,
        "package_generation": 2,
        "teacher_operationalization": 3,
        "rubric_and_quality": 4,
        "evaluation": 5,
        "promotion_governance": 6,
    }
    PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

    def build(
        self,
        batch_report_path: str | Path,
        batch_feedback_report_path: str | Path,
        substrate_audit_report_path: str | Path,
        typed_resource_patch_proposal_report_path: str | Path,
        output_dir: str | Path,
        promotion_report_path: Optional[str | Path] = None,
    ) -> GlobalPipelineDashboardReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = GlobalPipelineDashboardRequest(
            batch_report_path=str(batch_report_path),
            batch_feedback_report_path=str(batch_feedback_report_path),
            substrate_audit_report_path=str(substrate_audit_report_path),
            typed_resource_patch_proposal_report_path=str(typed_resource_patch_proposal_report_path),
            promotion_report_path=str(promotion_report_path) if promotion_report_path else None,
            output_dir=str(output_path),
        )

        batch_report = PipelineBBatchRunReport.model_validate(load_json_file(str(batch_report_path)))
        batch_feedback = PipelineBBatchFeedbackReport.model_validate(load_json_file(str(batch_feedback_report_path)))
        substrate_audit = PipelineASubstrateAuditReport.model_validate(
            load_json_file(str(substrate_audit_report_path))
        )
        typed_patch_report = TypedResourcePatchProposalReport.model_validate(
            load_json_file(str(typed_resource_patch_proposal_report_path))
        )
        promotion_report = (
            load_json_file(str(promotion_report_path))
            if promotion_report_path and Path(promotion_report_path).exists()
            else None
        )

        artifact_errors: List[str] = []
        snapshots = [self._snapshot(case, artifact_errors) for case in batch_report.cases]
        health_summary = self._health_summary(
            batch_report=batch_report,
            batch_feedback=batch_feedback,
            substrate_audit=substrate_audit,
            typed_patch_report=typed_patch_report,
            promotion_report=promotion_report,
            snapshots=snapshots,
        )
        focus_areas = self._focus_areas(
            batch_report=batch_report,
            batch_feedback=batch_feedback,
            substrate_audit=substrate_audit,
            promotion_report=promotion_report,
            snapshots=snapshots,
        )
        diagnostics = self._diagnostics(
            batch_report=batch_report,
            snapshots=snapshots,
            focus_areas=focus_areas,
            promotion_report=promotion_report,
            artifact_errors=artifact_errors,
        )
        report = GlobalPipelineDashboardReport(
            request=request,
            case_snapshots=snapshots,
            health_summary=health_summary,
            focus_areas=focus_areas,
            diagnostics=diagnostics,
            notes=[
                "Global Pipeline Dashboard V1 is a deterministic JSON-only aggregation layer.",
                "This dashboard does not mutate registry, sampler, quality gate, or evaluation settings.",
                "Model separation evidence remains intentionally zero until a dedicated artifact exists.",
            ],
        )
        self.write_outputs(report, output_path)
        return report

    def write_outputs(
        self,
        report: GlobalPipelineDashboardReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "global_pipeline_dashboard_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {"global_pipeline_dashboard_report_path": str(report_path)}

    def _snapshot(
        self,
        case: Any,
        artifact_errors: List[str],
    ) -> DashboardArtifactSnapshot:
        case_dir = Path(case.case_dir)
        errors: List[str] = []
        global_validity = self._load_optional(
            case_dir / "global_validity" / "global_task_validity_report.json",
            errors,
            "global_task_validity_report",
        )
        real_worldness = self._load_optional(
            case_dir / "global_validity" / "real_worldness_report.json",
            errors,
            "real_worldness_report",
        )
        execution_plan = self._load_optional(
            case_dir / "global_validity" / "execution_plan_dag_report.json",
            errors,
            "execution_plan_dag_report",
        )
        task_constraint_graph = self._load_optional(
            case_dir / "global_validity" / "task_constraint_graph_report.json",
            errors,
            "task_constraint_graph_report",
        )
        verifier = self._load_optional(
            case_dir / "task_verifier" / "task_verifier_report.json",
            errors,
            "task_verifier_report",
        )
        if errors:
            artifact_errors.extend(f"{case.case_id}:{item}" for item in errors)
        return DashboardArtifactSnapshot(
            case_id=case.case_id,
            motif=case.motif,
            case_dir=case.case_dir,
            quality_decision=case.quality_decision,
            package_readiness=case.package_readiness,
            subgraph_confidence=case.subgraph_confidence,
            workflow_context_fit=case.workflow_context_fit,
            real_worldness_score=self._float_or_none(
                ((real_worldness or {}).get("real_worldness_score"))
                if real_worldness
                else case.real_worldness_score
            ),
            difficulty_overall=self._float_or_none(case.difficulty_overall),
            recommended_next_layer=(global_validity or {}).get(
                "recommended_next_layer",
                case.recommended_next_layer,
            ),
            execution_dag_valid=(execution_plan or {}).get("dag_valid"),
            unsupported_task_constraint_count=len(
                ((task_constraint_graph or {}).get("unsupported_required_nodes") or [])
            ),
            verifier_status=(verifier or {}).get("verifier_status", case.verifier_status),
            verifier_blocking_count=int(
                (((verifier or {}).get("diagnostics") or {}).get("blocking_count") or case.verifier_blocking_count or 0)
            ),
            verifier_revise_count=int(
                (((verifier or {}).get("diagnostics") or {}).get("revise_count") or case.verifier_revise_count or 0)
            ),
            verifier_reason_codes=list(
                (((verifier or {}).get("diagnostics") or {}).get("reason_codes") or case.verifier_reason_codes or [])
            ),
            artifact_read_errors=errors,
        )

    def _health_summary(
        self,
        batch_report: PipelineBBatchRunReport,
        batch_feedback: PipelineBBatchFeedbackReport,
        substrate_audit: PipelineASubstrateAuditReport,
        typed_patch_report: TypedResourcePatchProposalReport,
        promotion_report: Optional[Dict[str, Any]],
        snapshots: List[DashboardArtifactSnapshot],
    ) -> DashboardHealthSummary:
        promotion_diagnostics = (promotion_report or {}).get("diagnostics") or {}
        batch_health = BatchHealthSummary(
            attempted_case_count=batch_report.diagnostics.case_count,
            completed_case_count=batch_report.diagnostics.completed_case_count,
            failed_case_count=batch_report.diagnostics.failed_case_count,
            quality_decision_counts=batch_report.diagnostics.quality_decision_counts,
            package_readiness_counts=batch_report.diagnostics.package_readiness_counts,
            repeated_reason_codes=batch_report.diagnostics.repeated_reason_codes,
            motif_failure_distribution=self._motif_failure_distribution(batch_report, batch_feedback, snapshots),
        )
        pipeline_a_health = PipelineASubstrateHealthSummary(
            audited_skill_count=substrate_audit.diagnostics.audited_skill_count,
            missing_typed_resource_skill_count=substrate_audit.diagnostics.missing_typed_resource_skill_count,
            weak_support_skill_count=substrate_audit.diagnostics.weak_support_skill_count,
            transition_gap_skill_count=substrate_audit.diagnostics.transition_gap_skill_count,
            manual_resource_patch_candidate_count=substrate_audit.diagnostics.manual_resource_patch_candidate_count,
            new_source_evidence_candidate_count=substrate_audit.diagnostics.new_source_evidence_candidate_count,
            typed_resource_promotion_candidate_count=int(promotion_diagnostics.get("promotion_count") or 0),
            eligible_typed_resource_promotion_count=int(
                promotion_diagnostics.get("eligible_promotion_count") or 0
            ),
            applied_typed_resource_promotion_count=int(
                promotion_diagnostics.get("applied_promotion_count") or 0
            ),
        )

        real_worldness_scores = [value for value in [s.real_worldness_score for s in snapshots] if value is not None]
        business_context_values = self._dimension_values(batch_report, "business_context_plausibility")
        artifact_ecology_values = self._dimension_values(batch_report, "artifact_ecology_realism")
        anti_template_values = self._dimension_values(batch_report, "anti_template_score")
        recommended_next_layer_counts = Counter(
            snapshot.recommended_next_layer for snapshot in snapshots if snapshot.recommended_next_layer
        )
        realism_health = TaskRealismHealthSummary(
            real_worldness_case_count=len(real_worldness_scores),
            real_worldness_score_distribution=self._distribution(real_worldness_scores),
            business_context_plausibility_distribution=self._distribution(business_context_values),
            artifact_ecology_realism_distribution=self._distribution(artifact_ecology_values),
            anti_template_score_distribution=self._distribution(anti_template_values),
            recommended_next_layer_counts=dict(sorted(recommended_next_layer_counts.items())),
        )

        verifier_reason_coverage = Counter()
        for snapshot in snapshots:
            for reason_code in set(snapshot.verifier_reason_codes):
                verifier_reason_coverage[reason_code] += 1
        executability_health = TaskExecutabilityHealthSummary(
            execution_dag_valid_case_count=sum(1 for s in snapshots if s.execution_dag_valid is True),
            execution_dag_invalid_case_count=sum(1 for s in snapshots if s.execution_dag_valid is False),
            unsupported_task_constraint_case_count=sum(
                1 for s in snapshots if s.unsupported_task_constraint_count > 0
            ),
            verifier_case_count=sum(1 for s in snapshots if s.verifier_status is not None),
            verifier_blocking_case_count=sum(1 for s in snapshots if s.verifier_blocking_count > 0),
            verifier_revise_case_count=sum(1 for s in snapshots if s.verifier_revise_count > 0),
            verifier_reason_coverage=dict(sorted(verifier_reason_coverage.items())),
        )

        training_readiness = TrainingEvaluationReadinessSummary(
            candidate_ready_count=sum(1 for case in batch_report.cases if case.quality_decision == "candidate_ready"),
            revise_only_count=sum(1 for case in batch_report.cases if case.package_readiness == "revise_only"),
            draft_external_eval_candidate_count=batch_feedback.diagnostics.external_eval_candidate_count,
            verifier_pass_count=sum(1 for s in snapshots if s.verifier_status == "pass"),
            model_separation_evidence_count=0,
            promotion_ready_count=int(promotion_diagnostics.get("eligible_promotion_count") or 0),
        )
        return DashboardHealthSummary(
            batch_health=batch_health,
            pipeline_a_substrate_health=pipeline_a_health,
            task_realism_health=realism_health,
            task_executability_health=executability_health,
            training_evaluation_readiness=training_readiness,
        )

    def _focus_areas(
        self,
        batch_report: PipelineBBatchRunReport,
        batch_feedback: PipelineBBatchFeedbackReport,
        substrate_audit: PipelineASubstrateAuditReport,
        promotion_report: Optional[Dict[str, Any]],
        snapshots: List[DashboardArtifactSnapshot],
    ) -> List[DashboardFocusArea]:
        focus_areas: List[DashboardFocusArea] = []
        case_count = max(len(batch_report.cases), 1)

        if (
            substrate_audit.diagnostics.missing_typed_resource_skill_count > 0
            or substrate_audit.diagnostics.transition_gap_skill_count > 0
        ):
            substrate_case_ids = {
                case_id
                for record in substrate_audit.skill_records
                for case_id in record.batch_case_ids
            }
            focus_areas.append(
                DashboardFocusArea(
                    focus_id="focus_pipeline_a_substrate",
                    owner_layer="pipeline_a",
                    priority="high",
                    title="Strengthen typed-resource and transition substrate before widening task batches.",
                    rationale="Pipeline A substrate gaps are still showing up in the sampled skills, so downstream package improvements would be working around missing composition signals.",
                    evidence={
                        "case_coverage": len(substrate_case_ids),
                        "missing_typed_resource_skill_count": substrate_audit.diagnostics.missing_typed_resource_skill_count,
                        "transition_gap_skill_count": substrate_audit.diagnostics.transition_gap_skill_count,
                        "manual_resource_patch_candidate_count": substrate_audit.diagnostics.manual_resource_patch_candidate_count,
                    },
                    recommended_next_step="Review substrate audit and typed-resource patch proposals first, then promote reviewed resource additions before widening batch diversity.",
                )
            )

        teacher_reasons = Counter()
        teacher_cases = set()
        for snapshot in snapshots:
            for reason_code in set(snapshot.verifier_reason_codes):
                if reason_code in self.TEACHER_REASON_CODES:
                    teacher_reasons[reason_code] += 1
                    teacher_cases.add(snapshot.case_id)
        if teacher_reasons:
            focus_areas.append(
                DashboardFocusArea(
                    focus_id="focus_teacher_evidence_closure",
                    owner_layer="teacher_operationalization",
                    priority="high",
                    title="Tighten teacher evidence closure before trusting solved-state artifacts.",
                    rationale="Verifier is still surfacing teacher-side unsupported complete/pass signals, which points to evidence-closure problems rather than ordinary package polish.",
                    evidence={
                        "case_coverage": len(teacher_cases),
                        "reason_coverage": dict(sorted(teacher_reasons.items())),
                    },
                    recommended_next_step="Revisit teacher evidence contract, complete-step marking, and final-check support discipline so solved states close against declared evidence ids.",
                )
            )

        rubric_reasons = Counter()
        rubric_cases = set()
        for snapshot in snapshots:
            for reason_code in set(snapshot.verifier_reason_codes):
                if reason_code in self.RUBRIC_REASON_CODES:
                    rubric_reasons[reason_code] += 1
                    rubric_cases.add(snapshot.case_id)
        if rubric_reasons:
            priority: FocusPriority = "high" if len(rubric_cases) >= max(1, case_count // 2) else "medium"
            focus_areas.append(
                DashboardFocusArea(
                    focus_id="focus_rubric_alignment",
                    owner_layer="rubric_and_quality",
                    priority=priority,
                    title="Repair deliverable-to-rubric alignment before expanding candidate-facing evaluation.",
                    rationale="Verifier findings show that visible deliverable obligations and candidate-facing rubric coverage are still not aligned cleanly.",
                    evidence={
                        "case_coverage": len(rubric_cases),
                        "reason_coverage": dict(sorted(rubric_reasons.items())),
                    },
                    recommended_next_step="Review blueprint deliverable requirements, rubric section mapping, and candidate-visible criterion hygiene before expanding evaluation use.",
                )
            )

        dossier_case_ids = set()
        dossier_reason_counts = Counter()
        for finding in batch_feedback.findings:
            if finding.reason_code in self.DOSSIER_REASON_CODES and len(finding.affected_case_ids) >= 2:
                dossier_reason_counts[finding.reason_code] += len(set(finding.affected_case_ids))
                dossier_case_ids.update(finding.affected_case_ids)
        if dossier_reason_counts:
            focus_areas.append(
                DashboardFocusArea(
                    focus_id="focus_evidence_dossier_ecology",
                    owner_layer="package_generation",
                    priority="medium",
                    title="Strengthen evidence dossier ecology and file-role design.",
                    rationale="Repeated dossier findings across multiple cases suggest evidence ecology weaknesses that are broader than any single prompt or rubric issue.",
                    evidence={
                        "case_coverage": len(dossier_case_ids),
                        "reason_coverage": dict(sorted(dossier_reason_counts.items())),
                    },
                    recommended_next_step="Inspect repeated dossier signals for missing attachments, stale-vs-current ambiguity, unresolved conflict sources, and weak manager-facing escalation context.",
                )
            )

        workflow_case_ids = {
            snapshot.case_id
            for snapshot in snapshots
            if snapshot.workflow_context_fit == "low" or snapshot.recommended_next_layer == "workflow_graph"
        }
        missing_role_total = sum(len(case.missing_roles) for case in batch_report.cases)
        if workflow_case_ids or missing_role_total > 0:
            focus_areas.append(
                DashboardFocusArea(
                    focus_id="focus_workflow_graph_structure",
                    owner_layer="workflow_graph",
                    priority="medium",
                    title="Improve workflow-conditioned subgraph structure before tuning downstream package layers.",
                    rationale="Low workflow context fit or recurring role gaps indicate the selected subgraphs are still under-structured relative to the workflow layer.",
                    evidence={
                        "case_coverage": len(workflow_case_ids),
                        "workflow_context_low_case_count": len(workflow_case_ids),
                        "missing_role_total": missing_role_total,
                        "recommended_next_layer_case_count": sum(
                            1 for snapshot in snapshots if snapshot.recommended_next_layer == "workflow_graph"
                        ),
                    },
                    recommended_next_step="Use workflow-context diagnostics to decide whether the next gain should come from sampler structure, workflow episode coverage, or motif-grammar enrichment.",
                )
            )

        promotion_diagnostics = (promotion_report or {}).get("diagnostics") or {}
        if int(promotion_diagnostics.get("eligible_promotion_count") or 0) > 0:
            focus_areas.append(
                DashboardFocusArea(
                    focus_id="focus_promotion_governance",
                    owner_layer="promotion_governance",
                    priority="low",
                    title="Review eligible typed-resource promotions instead of keeping repeated substrate gaps purely diagnostic.",
                    rationale="There are already reviewed promotion candidates that can be moved through explicit governance instead of leaving them indefinitely in report-only limbo.",
                    evidence={
                        "promotion_count": int(promotion_diagnostics.get("promotion_count") or 0),
                        "eligible_promotion_count": int(promotion_diagnostics.get("eligible_promotion_count") or 0),
                        "applied_promotion_count": int(promotion_diagnostics.get("applied_promotion_count") or 0),
                    },
                    recommended_next_step="Review apply-eligible typed-resource promotions on a scratch registry copy, then decide whether to promote selected substrate fixes into durable state.",
                )
            )

        return sorted(
            focus_areas,
            key=lambda item: (
                self.PRIORITY_RANK[item.priority],
                -int(item.evidence.get("case_coverage", 0)),
                self.LAYER_PRECEDENCE[item.owner_layer],
            ),
        )

    def _diagnostics(
        self,
        batch_report: PipelineBBatchRunReport,
        snapshots: List[DashboardArtifactSnapshot],
        focus_areas: List[DashboardFocusArea],
        promotion_report: Optional[Dict[str, Any]],
        artifact_errors: List[str],
    ) -> GlobalPipelineDashboardDiagnostics:
        return GlobalPipelineDashboardDiagnostics(
            case_count=batch_report.diagnostics.case_count,
            snapshot_count=len(snapshots),
            snapshot_error_case_count=sum(1 for snapshot in snapshots if snapshot.artifact_read_errors),
            missing_global_validity_case_count=sum(
                1
                for snapshot in snapshots
                if any("global_task_validity_report" in error for error in snapshot.artifact_read_errors)
            ),
            missing_verifier_case_count=sum(
                1
                for snapshot in snapshots
                if any("task_verifier_report" in error for error in snapshot.artifact_read_errors)
            ),
            missing_promotion_report=promotion_report is None,
            focus_area_count=len(focus_areas),
            artifact_read_errors=artifact_errors,
            notes=[
                "Case-level validity and verifier artifacts are discovered from case_dir paths in the batch report.",
                "Missing case-level artifacts are tolerated and retained as diagnostic signals instead of blocking dashboard generation.",
            ],
        )

    def _motif_failure_distribution(
        self,
        batch_report: PipelineBBatchRunReport,
        batch_feedback: PipelineBBatchFeedbackReport,
        snapshots: List[DashboardArtifactSnapshot],
    ) -> Dict[str, Dict[str, Any]]:
        by_motif: Dict[str, List[Any]] = defaultdict(list)
        snapshot_by_case = {snapshot.case_id: snapshot for snapshot in snapshots}
        for case in batch_report.cases:
            by_motif[case.motif].append(case)
        distribution: Dict[str, Dict[str, Any]] = {}
        for motif, cases in sorted(by_motif.items()):
            reason_counts = Counter()
            verifier_blocking_count = 0
            revise_count = 0
            failed_case_count = 0
            case_ids = {case.case_id for case in cases}
            for case in cases:
                if case.status == "failed":
                    failed_case_count += 1
                if case.quality_decision == "revise":
                    revise_count += 1
                snapshot = snapshot_by_case.get(case.case_id)
                if snapshot and snapshot.verifier_blocking_count > 0:
                    verifier_blocking_count += 1
            for finding in batch_feedback.findings:
                if motif in finding.affected_motifs:
                    reason_counts[finding.reason_code] += len(set(finding.affected_case_ids) & case_ids)
            distribution[motif] = {
                "case_count": len(cases),
                "failed_case_count": failed_case_count,
                "revise_count": revise_count,
                "verifier_blocking_count": verifier_blocking_count,
                "top_reason_codes": [reason for reason, _ in reason_counts.most_common(5)],
            }
        return distribution

    def _distribution(self, values: List[float]) -> ScoreDistribution:
        if not values:
            return ScoreDistribution()
        low_count = sum(1 for value in values if value < 0.4)
        medium_count = sum(1 for value in values if 0.4 <= value < 0.7)
        high_count = sum(1 for value in values if value >= 0.7)
        return ScoreDistribution(
            min=min(values),
            max=max(values),
            mean=round(mean(values), 4),
            low_count=low_count,
            medium_count=medium_count,
            high_count=high_count,
        )

    def _dimension_values(self, batch_report: PipelineBBatchRunReport, field_name: str) -> List[float]:
        values: List[float] = []
        for case in batch_report.cases:
            path = Path(case.case_dir) / "global_validity" / "real_worldness_report.json"
            if not path.exists():
                continue
            try:
                payload = load_json_file(str(path))
            except Exception:
                continue
            value = ((payload.get("dimensions") or {}).get(field_name))
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    def _load_optional(
        self,
        path: Path,
        errors: List[str],
        label: str,
    ) -> Optional[Dict[str, Any]]:
        if not path.exists():
            errors.append(f"{label}:missing")
            return None
        try:
            return load_json_file(str(path))
        except Exception as exc:
            errors.append(f"{label}:unreadable:{type(exc).__name__}")
            return None

    def _float_or_none(self, value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        return None
