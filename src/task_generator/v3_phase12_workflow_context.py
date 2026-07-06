from __future__ import annotations

import json
from collections import Counter
from datetime import date
from hashlib import sha1
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_global_pipeline_dashboard import GlobalPipelineDashboardBuilder
from task_generator.v3_motif_graph_grammar import (
    MotifExecutionStage,
    MotifGraphGrammarArtifact,
    MotifGraphGrammarDiagnostics,
    MotifGraphGrammarRecord,
    MotifRoleDefinition,
    MotifValidationConstraint,
)
from task_generator.v3_pipeline_a_substrate_audit import PipelineASubstrateAuditor
from task_generator.v3_pipeline_b_batch_feedback_analyzer import PipelineBBatchFeedbackAnalyzer
from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunner
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_typed_resource_patch_proposal import TypedResourcePatchProposalBuilder


ContextRating = Literal["low", "medium", "high"]


class Phase12WorkflowContextRequest(BaseModel):
    batch_report_path: str
    dashboard_report_path: str
    registry_path: str
    seed_report_path: str
    readiness_report_path: str
    transition_graph_report_path: str
    composition_readiness_report_path: str
    output_dir: str
    max_cases: int = 5
    allow_caution: bool = False
    base_motif_grammar_path: Optional[str] = None
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str
    python_exe: str


class WorkflowCaseReview(BaseModel):
    case_id: str
    blueprint_id: str
    motif: str
    workflow_context_fit_before: str
    real_worldness_score_before: Optional[float] = None
    actor_role_naturalness: ContextRating = "medium"
    trigger_event_naturalness: ContextRating = "medium"
    artifact_ecology_realism: ContextRating = "medium"
    deliverable_realism: ContextRating = "medium"
    decision_consequence_clarity: ContextRating = "medium"
    section_filling_risk: ContextRating = "medium"
    findings: List[str] = Field(default_factory=list)
    recommended_archetype_name: Optional[str] = None
    recommended_context_actions: List[str] = Field(default_factory=list)


class WorkflowArchetypePatchProposal(BaseModel):
    motif: str
    recommended_archetype_name: str
    suggested_actor_roles: List[str] = Field(default_factory=list)
    suggested_trigger_events: List[str] = Field(default_factory=list)
    suggested_deliverable_conventions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MotifContextPatchRecord(BaseModel):
    motif: str
    added_motif_grammar_id: str
    expected_graph_shape: str
    required_role_names: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12MotifContextPatchReport(BaseModel):
    phase12_motif_context_patch_version: str = "v1"
    report_date: str
    base_motif_grammar_path: Optional[str] = None
    output_motif_grammar_path: str
    added_motif_count: int = 0
    added_motif_types: List[str] = Field(default_factory=list)
    patch_records: List[MotifContextPatchRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12RealWorldnessComparisonReport(BaseModel):
    phase12_real_worldness_comparison_version: str = "v1"
    report_date: str
    case_count: int = 0
    pre_workflow_context_fit_counts: Dict[str, int] = Field(default_factory=dict)
    post_workflow_context_fit_counts: Dict[str, int] = Field(default_factory=dict)
    improved_case_count: int = 0
    degraded_case_count: int = 0
    real_worldness_mean_before: Optional[float] = None
    real_worldness_mean_after: Optional[float] = None
    candidate_ready_count_before: int = 0
    candidate_ready_count_after: int = 0
    verifier_pass_count_before: int = 0
    verifier_pass_count_after: int = 0
    notes: List[str] = Field(default_factory=list)


class Phase12WorkflowContextReviewReport(BaseModel):
    phase12_workflow_context_review_version: str = "v1"
    request: Phase12WorkflowContextRequest
    workflow_archetype_patch_proposals_path: str
    motif_context_patch_report_path: str
    real_worldness_comparison_report_path: str
    strengthened_batch_report_path: str
    strengthened_batch_feedback_report_path: str
    strengthened_substrate_audit_report_path: str
    strengthened_typed_resource_patch_report_path: str
    strengthened_dashboard_report_path: str
    case_reviews: List[WorkflowCaseReview] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12WorkflowContextStrengthener:
    def run(
        self,
        batch_report_path: str | Path,
        dashboard_report_path: str | Path,
        registry_path: str | Path,
        seed_report_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_dir: str | Path,
        max_cases: int = 5,
        allow_caution: bool = False,
        base_motif_grammar_path: Optional[str | Path] = None,
        model: str = "gpt-5.4-pro",
        workers: int = 1,
        rw_task_root: str | Path = Path(r"E:\THU\2026Spring\SRT\rw-task"),
        python_exe: str | Path = Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
    ) -> Phase12WorkflowContextReviewReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = Phase12WorkflowContextRequest(
            batch_report_path=str(batch_report_path),
            dashboard_report_path=str(dashboard_report_path),
            registry_path=str(registry_path),
            seed_report_path=str(seed_report_path),
            readiness_report_path=str(readiness_report_path),
            transition_graph_report_path=str(transition_graph_report_path),
            composition_readiness_report_path=str(composition_readiness_report_path),
            output_dir=str(output_path),
            max_cases=max_cases,
            allow_caution=allow_caution,
            base_motif_grammar_path=str(base_motif_grammar_path) if base_motif_grammar_path else None,
            model=model,
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
        )

        batch_payload = load_json_file(str(batch_report_path))
        dashboard_payload = load_json_file(str(dashboard_report_path))
        case_reviews = self._case_reviews(batch_payload, dashboard_payload)

        archetype_proposals = self._archetype_patch_proposals(case_reviews)
        archetype_path = output_path / "phase12_workflow_archetype_patch_proposals.json"
        archetype_path.write_text(
            json.dumps(
                {
                    "phase12_workflow_archetype_patch_version": "v1",
                    "report_date": date.today().isoformat(),
                    "proposal_count": len(archetype_proposals),
                    "proposals": [proposal.model_dump() for proposal in archetype_proposals],
                    "notes": [
                        "These are context patch proposals only; they do not overwrite the experimental archetype registry.",
                        "Use them to guide future archetype enrichment without turning archetypes into hard templates.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        motif_patch_report = self._motif_context_patch(
            base_motif_grammar_path=base_motif_grammar_path,
            output_dir=output_path,
        )

        rerun = self._rerun_with_motif_context(
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_root=output_path / f"workflow_strengthened_regression_{max_cases}case",
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_patch_report.output_motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
        )

        comparison = self._real_worldness_comparison(
            pre_batch_payload=batch_payload,
            post_batch_payload=load_json_file(rerun["batch_report_path"]),
        )
        comparison_path = output_path / "phase12_real_worldness_comparison_report.json"
        comparison_path.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")

        report = Phase12WorkflowContextReviewReport(
            request=request,
            workflow_archetype_patch_proposals_path=str(archetype_path),
            motif_context_patch_report_path=str(output_path / "phase12_motif_context_patch_report.json"),
            real_worldness_comparison_report_path=str(comparison_path),
            strengthened_batch_report_path=rerun["batch_report_path"],
            strengthened_batch_feedback_report_path=rerun["batch_feedback_report_path"],
            strengthened_substrate_audit_report_path=rerun["substrate_audit_report_path"],
            strengthened_typed_resource_patch_report_path=rerun["typed_resource_patch_report_path"],
            strengthened_dashboard_report_path=rerun["dashboard_report_path"],
            case_reviews=case_reviews,
            notes=[
                "Workflow-context strengthening uses a local Phase 12 motif grammar extension rather than changing the canonical grammar artifact.",
                "The goal is to raise workflow-context conditioning without converting archetypes into rigid templates.",
                "Real-worldness should remain stable while low workflow_context_fit motifs gain better structural context.",
            ],
        )
        (output_path / "phase12_workflow_context_review_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _case_reviews(
        self,
        batch_payload: Dict[str, Any],
        dashboard_payload: Dict[str, Any],
    ) -> List[WorkflowCaseReview]:
        snapshot_by_case = {
            item.get("case_id"): item for item in (dashboard_payload.get("case_snapshots") or [])
        }
        reviews: List[WorkflowCaseReview] = []
        for case in batch_payload.get("cases") or []:
            if case.get("quality_decision") != "candidate_ready":
                continue
            case_id = str(case.get("case_id") or "unknown")
            case_dir = Path(case.get("case_dir") or "")
            blueprint = load_json_file(str(case_dir / "prototype" / "draft_task_blueprint.json"))
            role_text = str(((blueprint.get("scenario_spec") or {}).get("role")) or "")
            business_context = str(((blueprint.get("scenario_spec") or {}).get("business_context")) or "")
            trigger_hint = str(((blueprint.get("task_metadata") or {}).get("scenario_title")) or "")
            deliverables = list(blueprint.get("deliverable_spec") or [])
            snapshot = snapshot_by_case.get(case_id, {})
            findings: List[str] = []
            actions: List[str] = []

            actor_rating: ContextRating = "high"
            if role_text.startswith("You are a Senior Auditor preparing a review package for a manager"):
                actor_rating = "low"
                findings.append("Actor role is generic and repeated across motifs.")
                actions.append("Use motif-specific actor roles instead of one generic Senior Auditor frame.")

            trigger_rating: ContextRating = "high"
            if "compact evidence package" in business_context.lower() or trigger_hint.endswith("Review"):
                trigger_rating = "low"
                findings.append("Trigger event reads as generic review intake rather than a concrete business event.")
                actions.append("Add motif-specific trigger events such as close review, exception escalation, or control validation request.")

            artifact_rating: ContextRating = "medium"
            if snapshot.get("real_worldness_score", 0) >= 0.8:
                artifact_rating = "high"
            if snapshot.get("workflow_context_fit") == "low":
                artifact_rating = "medium"
                findings.append("Artifact ecology is structurally valid but still too thin for workflow-rich realism.")
                actions.append("Enrich dossier-level artifact ecology with notes, conflict, or escalation context.")

            deliverable_rating: ContextRating = "high"
            if deliverables and any("memo" in str(item.get("file_name", "")).lower() for item in deliverables):
                deliverable_rating = "high"

            consequence_rating: ContextRating = "medium"
            if "manager review" in role_text.lower():
                consequence_rating = "high"
            if "compact evidence package" in business_context.lower():
                consequence_rating = "medium"

            section_filling_risk: ContextRating = "low"
            if snapshot.get("workflow_context_fit") == "low":
                section_filling_risk = "high"
                findings.append("Current case risks feeling like section-filling over a generic evidence bundle.")
                actions.append("Bind the workflow to a more concrete manager or control-review outcome.")

            reviews_archetype = self._suggested_archetype(case.get("motif"))
            reviews.append(
                WorkflowCaseReview(
                    case_id=case_id,
                    blueprint_id=str(case.get("blueprint_id") or "unknown"),
                    motif=str(case.get("motif") or "unknown"),
                    workflow_context_fit_before=str(case.get("workflow_context_fit") or "low"),
                    real_worldness_score_before=snapshot.get("real_worldness_score"),
                    actor_role_naturalness=actor_rating,
                    trigger_event_naturalness=trigger_rating,
                    artifact_ecology_realism=artifact_rating,
                    deliverable_realism=deliverable_rating,
                    decision_consequence_clarity=consequence_rating,
                    section_filling_risk=section_filling_risk,
                    findings=sorted(set(findings)),
                    recommended_archetype_name=reviews_archetype,
                    recommended_context_actions=sorted(set(actions)),
                )
            )
        return reviews

    def _archetype_patch_proposals(
        self,
        reviews: List[WorkflowCaseReview],
    ) -> List[WorkflowArchetypePatchProposal]:
        by_motif: Dict[str, WorkflowArchetypePatchProposal] = {}
        for review in reviews:
            if review.workflow_context_fit_before != "low":
                continue
            if review.motif in by_motif:
                continue
            if review.motif == "evidence_to_deliverable":
                by_motif[review.motif] = WorkflowArchetypePatchProposal(
                    motif=review.motif,
                    recommended_archetype_name="evidence_based_manager_briefing",
                    suggested_actor_roles=["Finance Review Lead", "Audit Senior", "Manager Support Analyst"],
                    suggested_trigger_events=[
                        "manager request for evidence-backed briefing",
                        "current-period exception review before manager sign-off",
                    ],
                    suggested_deliverable_conventions=[
                        "manager briefing memo",
                        "evidence-backed review note",
                    ],
                    notes=["Use context enrichment, not hard template substitution."],
                )
            elif review.motif == "cross_check_validation":
                by_motif[review.motif] = WorkflowArchetypePatchProposal(
                    motif=review.motif,
                    recommended_archetype_name="internal_control_exception_documentation",
                    suggested_actor_roles=["Control Testing Senior", "Audit Manager Delegate"],
                    suggested_trigger_events=[
                        "cross-source validation request",
                        "control-testing exception follow-up",
                    ],
                    suggested_deliverable_conventions=[
                        "validation memo",
                        "exception review workpaper",
                    ],
                    notes=["Preserve cross-check behavior without hard-coding one fixed task template."],
                )
        return list(by_motif.values())

    def _motif_context_patch(
        self,
        base_motif_grammar_path: Optional[str | Path],
        output_dir: Path,
    ) -> Phase12MotifContextPatchReport:
        if base_motif_grammar_path and Path(base_motif_grammar_path).exists():
            base_payload = MotifGraphGrammarArtifact.model_validate(load_json_file(str(base_motif_grammar_path)))
        else:
            base_payload = MotifGraphGrammarArtifact(
                grammars=[],
                diagnostics=MotifGraphGrammarDiagnostics(grammar_count=0, motif_types=[]),
                notes=["Phase 12 started from an empty base grammar artifact."],
            )
        existing = {grammar.motif_type for grammar in base_payload.grammars}
        added: List[MotifGraphGrammarRecord] = []
        patch_records: List[MotifContextPatchRecord] = []
        for grammar in [self._evidence_to_deliverable_grammar(), self._cross_check_validation_grammar()]:
            if grammar.motif_type in existing:
                continue
            added.append(grammar)
            patch_records.append(
                MotifContextPatchRecord(
                    motif=grammar.motif_type,
                    added_motif_grammar_id=grammar.motif_grammar_id,
                    expected_graph_shape=grammar.expected_graph_shape,
                    required_role_names=[role.role_name for role in grammar.required_roles],
                    notes=["Phase 12 local context patch; do not treat as canonical grammar promotion."],
                )
            )
        merged = MotifGraphGrammarArtifact(
            motif_graph_grammar_version=base_payload.motif_graph_grammar_version,
            grammars=list(base_payload.grammars) + added,
            diagnostics=MotifGraphGrammarDiagnostics(
                grammar_count=len(list(base_payload.grammars) + added),
                motif_types=[grammar.motif_type for grammar in list(base_payload.grammars) + added],
                warning_codes=[],
                notes=["Phase 12 local grammar extension adds missing motif context for workflow-fit hardening."],
            ),
            notes=list(base_payload.notes)
            + ["Phase 12 local motif additions are for workflow-context hardening only."],
        )
        grammar_path = output_dir / "phase12_motif_graph_grammar.extended.json"
        grammar_path.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
        report = Phase12MotifContextPatchReport(
            report_date=date.today().isoformat(),
            base_motif_grammar_path=str(base_motif_grammar_path) if base_motif_grammar_path else None,
            output_motif_grammar_path=str(grammar_path),
            added_motif_count=len(added),
            added_motif_types=[item.motif_type for item in added],
            patch_records=patch_records,
            notes=[
                "This patch report extends motif context locally for Phase 12 workflow-fit hardening.",
                "Canonical grammar promotion should remain a separate reviewed step.",
            ],
        )
        (output_dir / "phase12_motif_context_patch_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _evidence_to_deliverable_grammar(self) -> MotifGraphGrammarRecord:
        return MotifGraphGrammarRecord(
            motif_grammar_id=self._stable_id("mgg", "phase12:evidence_to_deliverable"),
            motif_type="evidence_to_deliverable",
            required_roles=[
                MotifRoleDefinition(
                    role_name="evidence_source",
                    role_kind="source",
                    description="Expose candidate-visible evidence items for downstream synthesis.",
                    required_resource_types=["Dataset"],
                    provided_resource_types=["Dataset"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="analysis_or_exception_handler",
                    role_kind="skill",
                    description="Interpret evidence, classify exceptions, and preserve support caveats.",
                    required_resource_types=["Dataset", "ExceptionRecord"],
                    provided_resource_types=["ExceptionRecord"],
                    typical_graph_roles=["transform", "validator"],
                ),
                MotifRoleDefinition(
                    role_name="deliverable_synthesizer",
                    role_kind="deliverable",
                    description="Turn reviewed evidence into a manager-ready deliverable section set.",
                    required_resource_types=["Dataset", "DeliverableSection"],
                    provided_resource_types=["DeliverableSection"],
                    typical_graph_roles=["synthesis"],
                ),
            ],
            optional_roles=[
                MotifRoleDefinition(
                    role_name="policy_reference_support",
                    role_kind="support",
                    description="Link evidence to lightweight policy or rule context when present.",
                    required_resource_types=["PolicyRule"],
                    provided_resource_types=["PolicyRule"],
                    typical_graph_roles=["validator"],
                ),
            ],
            required_resource_types=["Dataset", "DeliverableSection"],
            provided_resource_types=["DeliverableSection", "ExceptionRecord"],
            expected_graph_shape="chain",
            execution_stage_template=[
                MotifExecutionStage(
                    stage_id="stage_collect_evidence",
                    stage_name="collect and inventory evidence",
                    required_roles=["evidence_source"],
                    expected_outputs=["Dataset"],
                ),
                MotifExecutionStage(
                    stage_id="stage_classify_support",
                    stage_name="classify support and exceptions",
                    required_roles=["analysis_or_exception_handler"],
                    expected_outputs=["ExceptionRecord"],
                ),
                MotifExecutionStage(
                    stage_id="stage_synthesize_deliverable",
                    stage_name="synthesize manager-ready deliverable",
                    required_roles=["deliverable_synthesizer"],
                    expected_outputs=["DeliverableSection"],
                ),
            ],
            validation_constraints=[
                MotifValidationConstraint(
                    constraint_id="must_preserve_evidence_traceability",
                    description="Conclusions must remain grounded in candidate-visible evidence IDs.",
                    severity="high",
                    reason_codes=["missing_evidence_locator"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_separate_unresolved_items",
                    description="Unresolved items should stay distinct from supported conclusions.",
                    severity="medium",
                    reason_codes=["flattened_uncertainty"],
                ),
            ],
            common_failure_modes=[
                "generic evidence bundle summarized without concrete business consequence",
                "deliverable reads like section-filling instead of manager-ready synthesis",
                "exceptions collapsed into supported conclusions",
            ],
            notes=["Phase 12 local grammar for workflow-context hardening of evidence-to-deliverable tasks."],
        )

    def _cross_check_validation_grammar(self) -> MotifGraphGrammarRecord:
        return MotifGraphGrammarRecord(
            motif_grammar_id=self._stable_id("mgg", "phase12:cross_check_validation"),
            motif_type="cross_check_validation",
            required_roles=[
                MotifRoleDefinition(
                    role_name="primary_source_extractor",
                    role_kind="source",
                    description="Expose the primary evidence set for downstream validation.",
                    required_resource_types=["Dataset"],
                    provided_resource_types=["Dataset"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="cross_check_validator",
                    role_kind="validator",
                    description="Compare primary evidence against an expected total, control basis, or alternate view.",
                    required_resource_types=["Dataset", "ControlEvidence"],
                    provided_resource_types=["ReconciliationDifference"],
                    typical_graph_roles=["fan_in", "validator"],
                ),
                MotifRoleDefinition(
                    role_name="exception_documenter",
                    role_kind="exception_handler",
                    description="Document material differences, evidence gaps, and validation outcomes.",
                    required_resource_types=["ReconciliationDifference"],
                    provided_resource_types=["ExceptionRecord"],
                    typical_graph_roles=["validator"],
                ),
            ],
            optional_roles=[
                MotifRoleDefinition(
                    role_name="deliverable_synthesizer",
                    role_kind="deliverable",
                    description="Package the validation outcome into a review-ready memo or workpaper.",
                    required_resource_types=["ExceptionRecord"],
                    provided_resource_types=["DeliverableSection"],
                    typical_graph_roles=["synthesis"],
                ),
            ],
            required_resource_types=["Dataset", "ControlEvidence"],
            provided_resource_types=["ReconciliationDifference", "ExceptionRecord"],
            expected_graph_shape="constraint_graph",
            execution_stage_template=[
                MotifExecutionStage(
                    stage_id="stage_extract_primary_source",
                    stage_name="extract primary source evidence",
                    required_roles=["primary_source_extractor"],
                    expected_outputs=["Dataset"],
                ),
                MotifExecutionStage(
                    stage_id="stage_cross_check",
                    stage_name="cross-check against control basis",
                    required_roles=["cross_check_validator"],
                    expected_outputs=["ReconciliationDifference"],
                ),
                MotifExecutionStage(
                    stage_id="stage_document_exceptions",
                    stage_name="document validation exceptions",
                    required_roles=["exception_documenter"],
                    expected_outputs=["ExceptionRecord"],
                ),
            ],
            validation_constraints=[
                MotifValidationConstraint(
                    constraint_id="must_preserve_cross_source_basis",
                    description="Validation output must keep the basis for each cross-check visible.",
                    severity="high",
                    reason_codes=["missing_cross_check_basis"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_explain_gaps",
                    description="Material validation differences should be explained or explicitly marked unresolved.",
                    severity="medium",
                    reason_codes=["unexplained_difference"],
                ),
            ],
            common_failure_modes=[
                "cross-check result presented without basis",
                "exception handling omitted from validation memo",
                "case feels like generic spreadsheet filling instead of a control-review workflow",
            ],
            notes=["Phase 12 local grammar for workflow-context hardening of cross-check validation tasks."],
        )

    def _rerun_with_motif_context(
        self,
        registry_path: str | Path,
        seed_report_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_root: Path,
        max_cases: int,
        allow_caution: bool,
        motif_grammar_path: str | Path,
        model: str,
        workers: int,
        rw_task_root: str | Path,
        python_exe: str | Path,
    ) -> Dict[str, str]:
        batch_dir = output_root / "batch"
        feedback_dir = output_root / "feedback"
        substrate_dir = output_root / "substrate"
        typed_patch_dir = output_root / "typed_resource_review"
        dashboard_dir = output_root / "dashboard"
        PipelineBBatchRunner().run(
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            output_dir=batch_dir,
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
        )
        batch_report_path = batch_dir / "pipeline_b_batch_report.json"
        PipelineBBatchFeedbackAnalyzer().analyze(batch_report_path=batch_report_path, output_dir=feedback_dir)
        batch_feedback_path = feedback_dir / "pipeline_b_batch_feedback_report.json"
        PipelineASubstrateAuditor().audit(
            batch_feedback_report_path=batch_feedback_path,
            batch_report_path=batch_report_path,
            registry_path=registry_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_dir=substrate_dir,
        )
        substrate_report_path = substrate_dir / "pipeline_a_substrate_audit_report.json"
        TypedResourcePatchProposalBuilder().build(
            substrate_audit_report_path=substrate_report_path,
            output_dir=typed_patch_dir,
            include_low_confidence=True,
        )
        typed_patch_report_path = typed_patch_dir / "typed_resource_patch_proposal_report.json"
        GlobalPipelineDashboardBuilder().build(
            batch_report_path=batch_report_path,
            batch_feedback_report_path=batch_feedback_path,
            substrate_audit_report_path=substrate_report_path,
            typed_resource_patch_proposal_report_path=typed_patch_report_path,
            output_dir=dashboard_dir,
        )
        dashboard_report_path = dashboard_dir / "global_pipeline_dashboard_report.json"
        return {
            "batch_report_path": str(batch_report_path),
            "batch_feedback_report_path": str(batch_feedback_path),
            "substrate_audit_report_path": str(substrate_report_path),
            "typed_resource_patch_report_path": str(typed_patch_report_path),
            "dashboard_report_path": str(dashboard_report_path),
        }

    def _real_worldness_comparison(
        self,
        pre_batch_payload: Dict[str, Any],
        post_batch_payload: Dict[str, Any],
    ) -> Phase12RealWorldnessComparisonReport:
        pre_cases = {item.get("case_id"): item for item in (pre_batch_payload.get("cases") or [])}
        post_cases = {item.get("case_id"): item for item in (post_batch_payload.get("cases") or [])}
        pre_fit_counts = Counter(str(item.get("workflow_context_fit") or "unknown") for item in pre_cases.values())
        post_fit_counts = Counter(str(item.get("workflow_context_fit") or "unknown") for item in post_cases.values())
        improved = 0
        degraded = 0
        rank = {"low": 0, "medium": 1, "high": 2}
        for case_id, pre in pre_cases.items():
            post = post_cases.get(case_id)
            if not post:
                continue
            before = rank.get(str(pre.get("workflow_context_fit") or "low"), 0)
            after = rank.get(str(post.get("workflow_context_fit") or "low"), 0)
            if after > before:
                improved += 1
            elif after < before:
                degraded += 1
        pre_scores = [float(item.get("real_worldness_score")) for item in pre_cases.values() if item.get("real_worldness_score") is not None]
        post_scores = [float(item.get("real_worldness_score")) for item in post_cases.values() if item.get("real_worldness_score") is not None]
        pre_diag = pre_batch_payload.get("diagnostics") or {}
        post_diag = post_batch_payload.get("diagnostics") or {}
        return Phase12RealWorldnessComparisonReport(
            report_date=date.today().isoformat(),
            case_count=len(pre_cases),
            pre_workflow_context_fit_counts=dict(sorted(pre_fit_counts.items())),
            post_workflow_context_fit_counts=dict(sorted(post_fit_counts.items())),
            improved_case_count=improved,
            degraded_case_count=degraded,
            real_worldness_mean_before=round(mean(pre_scores), 4) if pre_scores else None,
            real_worldness_mean_after=round(mean(post_scores), 4) if post_scores else None,
            candidate_ready_count_before=(pre_diag.get("quality_decision_counts") or {}).get("candidate_ready", 0),
            candidate_ready_count_after=(post_diag.get("quality_decision_counts") or {}).get("candidate_ready", 0),
            verifier_pass_count_before=(pre_diag.get("verifier_status_counts") or {}).get("pass", 0),
            verifier_pass_count_after=(post_diag.get("verifier_status_counts") or {}).get("pass", 0),
            notes=[
                "Workflow-context fit is expected to improve first; real-worldness may remain flat when only motif conditioning changes.",
                "Candidate-ready and verifier-pass counts should remain stable during realism strengthening.",
            ],
        )

    def _suggested_archetype(self, motif: Any) -> Optional[str]:
        motif_name = str(motif or "")
        if motif_name == "evidence_to_deliverable":
            return "evidence_based_manager_briefing"
        if motif_name == "cross_check_validation":
            return "internal_control_exception_documentation"
        if motif_name == "fan_in_reconciliation":
            return "multi_source_reconciliation_memo"
        if motif_name == "policy_application":
            return "policy_clause_application_review"
        return None

    def _stable_id(self, prefix: str, value: str) -> str:
        return f"{prefix}_{sha1(value.encode('utf-8')).hexdigest()[:12]}"
