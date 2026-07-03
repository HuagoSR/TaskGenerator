from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_b_batch_feedback_analyzer import PipelineBBatchFeedbackReport
from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunReport
from task_generator.v3_source_schema import SkillRegistryEntry, load_json_file


DiagnosisCode = Literal[
    "missing_typed_resources",
    "weak_support_diversity",
    "transition_evidence_absent_or_local_only",
    "missing_graph_role",
    "candidate_ready_for_manual_resource_patch",
    "candidate_needs_new_source_evidence",
    "candidate_should_remain_sampled_with_caution",
    "do_not_patch_without_reviewer_or_source_evidence",
]
RemediationActionType = Literal[
    "manual_resource_patch",
    "new_source_evidence",
    "transition_evidence_calibration",
    "sampler_caution",
    "hold_for_review",
]


class PipelineASubstrateAuditRequest(BaseModel):
    batch_feedback_report_path: str
    batch_report_path: str
    registry_path: str
    readiness_report_path: str
    transition_graph_report_path: str
    composition_readiness_report_path: str
    output_dir: str


class SkillTransitionEvidenceSummary(BaseModel):
    incoming_usable_count: int = 0
    outgoing_usable_count: int = 0
    incoming_caution_count: int = 0
    outgoing_caution_count: int = 0
    incoming_blocked_count: int = 0
    outgoing_blocked_count: int = 0
    local_only_edge_count: int = 0
    transition_edge_ids: List[str] = Field(default_factory=list)
    transition_reason_codes: List[str] = Field(default_factory=list)


class SkillSubstrateAuditRecord(BaseModel):
    skill_id: str
    canonical_name: str = ""
    domain_tags: List[str] = Field(default_factory=list)
    capability_tags: List[str] = Field(default_factory=list)
    difficulty_tags: List[str] = Field(default_factory=list)
    batch_case_ids: List[str] = Field(default_factory=list)
    batch_motifs: List[str] = Field(default_factory=list)
    batch_selected_count: int = 0
    readiness_decision: Optional[str] = None
    readiness_reason_codes: List[str] = Field(default_factory=list)
    suggested_sampling_action: str = ""
    sampling_weight: Optional[float] = None
    registry_source_candidate_count: int = 0
    registry_source_candidate_ids: List[str] = Field(default_factory=list)
    registry_evidence_ref_count: int = 0
    typed_required_resource_count: int = 0
    typed_optional_resource_count: int = 0
    typed_provided_resource_count: int = 0
    legacy_required_semantics: List[str] = Field(default_factory=list)
    legacy_optional_semantics: List[str] = Field(default_factory=list)
    legacy_provided_semantics: List[str] = Field(default_factory=list)
    composition_graph_role_hints: List[str] = Field(default_factory=list)
    composition_readiness_decision: Optional[str] = None
    composition_required_resource_count: int = 0
    composition_provided_resource_count: int = 0
    composition_reason_codes: List[str] = Field(default_factory=list)
    transition_evidence: SkillTransitionEvidenceSummary = Field(
        default_factory=SkillTransitionEvidenceSummary
    )
    motif_participation: List[str] = Field(default_factory=list)
    diagnoses: List[DiagnosisCode] = Field(default_factory=list)
    recommended_action_types: List[RemediationActionType] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PipelineASubstrateRemediationAction(BaseModel):
    action_id: str
    priority: int
    action_type: RemediationActionType
    title: str
    rationale: str
    skill_ids: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    suggested_next_step: str = ""


class PipelineASubstrateAuditDiagnostics(BaseModel):
    audited_skill_count: int = 0
    batch_case_count: int = 0
    missing_typed_resource_skill_count: int = 0
    weak_support_skill_count: int = 0
    single_source_skill_count: int = 0
    multi_source_skill_count: int = 0
    transition_gap_skill_count: int = 0
    missing_graph_role_skill_count: int = 0
    manual_resource_patch_candidate_count: int = 0
    new_source_evidence_candidate_count: int = 0
    sampled_with_caution_recommended_count: int = 0
    hold_for_review_count: int = 0
    diagnosis_counts: Dict[str, int] = Field(default_factory=dict)
    action_counts: Dict[str, int] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PipelineASubstrateAuditReport(BaseModel):
    substrate_audit_version: str = "v3.pipeline_a_substrate_audit.1"
    request: PipelineASubstrateAuditRequest
    selected_skill_ids: List[str] = Field(default_factory=list)
    skill_records: List[SkillSubstrateAuditRecord] = Field(default_factory=list)
    remediation_actions: List[PipelineASubstrateRemediationAction] = Field(default_factory=list)
    diagnostics: PipelineASubstrateAuditDiagnostics
    upstream_batch_feedback_summary: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PipelineASubstrateAuditor:
    """Audit Pipeline A substrate signals for skills actually sampled by Pipeline B batch smoke."""

    def audit(
        self,
        batch_feedback_report_path: str | Path,
        batch_report_path: str | Path,
        registry_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_dir: str | Path,
    ) -> PipelineASubstrateAuditReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = PipelineASubstrateAuditRequest(
            batch_feedback_report_path=str(batch_feedback_report_path),
            batch_report_path=str(batch_report_path),
            registry_path=str(registry_path),
            readiness_report_path=str(readiness_report_path),
            transition_graph_report_path=str(transition_graph_report_path),
            composition_readiness_report_path=str(composition_readiness_report_path),
            output_dir=str(output_path),
        )
        batch_report = PipelineBBatchRunReport.model_validate(load_json_file(str(batch_report_path)))
        batch_feedback = PipelineBBatchFeedbackReport.model_validate(
            load_json_file(str(batch_feedback_report_path))
        )
        registry_entries = self._registry_entries(registry_path)
        readiness_records = self._records_by_skill(readiness_report_path)
        composition_records = self._records_by_skill(composition_readiness_report_path)
        transition_graph = load_json_file(str(transition_graph_report_path))

        case_index = self._selected_skill_case_index(batch_report)
        selected_skill_ids = sorted(case_index)
        records = [
            self._skill_record(
                skill_id=skill_id,
                case_index=case_index,
                registry_entries=registry_entries,
                readiness_records=readiness_records,
                composition_records=composition_records,
                transition_graph=transition_graph,
            )
            for skill_id in selected_skill_ids
        ]
        remediation_actions = self._remediation_actions(records)
        diagnostics = self._diagnostics(batch_report, records)
        report = PipelineASubstrateAuditReport(
            request=request,
            selected_skill_ids=selected_skill_ids,
            skill_records=records,
            remediation_actions=remediation_actions,
            diagnostics=diagnostics,
            upstream_batch_feedback_summary={
                "priority_reason_codes": batch_feedback.diagnostics.priority_reason_codes,
                "systemic_finding_count": batch_feedback.diagnostics.systemic_finding_count,
                "external_eval_candidate_count": batch_feedback.diagnostics.external_eval_candidate_count,
            },
            notes=[
                "This audit is report-only and does not mutate SkillRegistry, readiness reports, or transition priors.",
                "It audits the skills that Pipeline B actually sampled in the batch smoke, not the entire registry.",
                "Manual or LLM-assisted typed-resource remediation should be proposed and reviewed before any registry write.",
            ],
        )
        self.write_outputs(report, output_path)
        return report

    def write_outputs(
        self, report: PipelineASubstrateAuditReport, output_dir: str | Path
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "pipeline_a_substrate_audit_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {"substrate_audit_report_path": str(report_path)}

    def _registry_entries(self, registry_path: str | Path) -> Dict[str, SkillRegistryEntry]:
        payload = load_json_file(str(registry_path))
        return {
            entry.skill_id: entry
            for entry in [SkillRegistryEntry.model_validate(raw) for raw in payload.get("entries", [])]
        }

    def _records_by_skill(self, report_path: str | Path) -> Dict[str, Dict[str, Any]]:
        payload = load_json_file(str(report_path))
        records: Dict[str, Dict[str, Any]] = {}
        for record in payload.get("records", []):
            skill_id = record.get("skill_id")
            if skill_id:
                records[skill_id] = record
        return records

    def _selected_skill_case_index(
        self, batch_report: PipelineBBatchRunReport
    ) -> Dict[str, List[Dict[str, str]]]:
        case_index: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for case in batch_report.cases:
            subgraph_path = Path(case.case_dir) / "subgraph_sampler" / "pipeline_b_subgraph_report.json"
            if not subgraph_path.exists():
                continue
            subgraph = load_json_file(str(subgraph_path))
            for skill in subgraph.get("selected_skills", []):
                skill_id = skill.get("skill_id")
                if not skill_id:
                    continue
                case_index[skill_id].append(
                    {
                        "case_id": case.case_id,
                        "motif": case.motif,
                        "subgraph_id": subgraph.get("subgraph_id", ""),
                    }
                )
        return dict(case_index)

    def _skill_record(
        self,
        skill_id: str,
        case_index: Dict[str, List[Dict[str, str]]],
        registry_entries: Dict[str, SkillRegistryEntry],
        readiness_records: Dict[str, Dict[str, Any]],
        composition_records: Dict[str, Dict[str, Any]],
        transition_graph: Dict[str, Any],
    ) -> SkillSubstrateAuditRecord:
        entry = registry_entries.get(skill_id)
        readiness = readiness_records.get(skill_id, {})
        composition = composition_records.get(skill_id, {})
        case_refs = case_index.get(skill_id, [])
        transition = self._transition_summary(skill_id, transition_graph)
        motif_participation = sorted(
            set([case_ref.get("motif", "") for case_ref in case_refs if case_ref.get("motif")])
        )

        typed_required = len(entry.input_contract.required_resources) if entry else 0
        typed_optional = len(entry.input_contract.optional_resources) if entry else 0
        typed_provided = len(entry.output_contract.provided_resources) if entry else 0
        legacy_required = list(entry.input_contract.requires_semantics) if entry else []
        legacy_optional = list(entry.input_contract.optional_semantics) if entry else []
        legacy_provided = list(entry.output_contract.provides_semantics) if entry else []
        source_candidate_ids = list(entry.source_candidate_ids) if entry else []
        evidence_refs = list(entry.evidence_refs) if entry else []
        composition_roles = sorted(set(composition.get("graph_role_hints") or []))
        composition_reason_codes = sorted(set(composition.get("reason_codes") or []))
        readiness_reason_codes = sorted(set(readiness.get("reason_codes") or []))

        diagnoses = self._diagnoses(
            typed_required=typed_required,
            typed_optional=typed_optional,
            typed_provided=typed_provided,
            legacy_required=legacy_required,
            legacy_optional=legacy_optional,
            legacy_provided=legacy_provided,
            source_candidate_count=len(source_candidate_ids),
            readiness_reason_codes=readiness_reason_codes,
            composition_roles=composition_roles,
            composition_required_count=int(composition.get("required_resource_count") or 0),
            composition_provided_count=int(composition.get("provided_resource_count") or 0),
            composition_reason_codes=composition_reason_codes,
            transition=transition,
        )
        actions = self._record_actions(diagnoses)
        notes: List[str] = []
        if entry is None:
            notes.append("Selected skill was not found in the persistent registry.")
        if "missing_typed_resources" in diagnoses and (
            legacy_required or legacy_optional or legacy_provided or composition_reason_codes
        ):
            notes.append(
                "Registry typed resources are empty, but legacy semantics or composition inference provide patch material."
            )
        if len(source_candidate_ids) == 1:
            notes.append("Source support count is exactly 1; do not raise sampler weight without more evidence.")

        return SkillSubstrateAuditRecord(
            skill_id=skill_id,
            canonical_name=entry.canonical_name if entry else readiness.get("canonical_name", ""),
            domain_tags=list(entry.domain_tags) if entry else list(readiness.get("domain_tags") or []),
            capability_tags=list(entry.capability_tags)
            if entry
            else list(readiness.get("capability_tags") or []),
            difficulty_tags=list(entry.difficulty_tags)
            if entry
            else list(readiness.get("difficulty_tags") or []),
            batch_case_ids=sorted({case_ref["case_id"] for case_ref in case_refs}),
            batch_motifs=motif_participation,
            batch_selected_count=len(case_refs),
            readiness_decision=readiness.get("readiness_decision"),
            readiness_reason_codes=readiness_reason_codes,
            suggested_sampling_action=readiness.get("suggested_sampling_action", ""),
            sampling_weight=readiness.get("sampling_weight"),
            registry_source_candidate_count=len(source_candidate_ids),
            registry_source_candidate_ids=source_candidate_ids,
            registry_evidence_ref_count=len(evidence_refs),
            typed_required_resource_count=typed_required,
            typed_optional_resource_count=typed_optional,
            typed_provided_resource_count=typed_provided,
            legacy_required_semantics=legacy_required,
            legacy_optional_semantics=legacy_optional,
            legacy_provided_semantics=legacy_provided,
            composition_graph_role_hints=composition_roles,
            composition_readiness_decision=composition.get("readiness_decision"),
            composition_required_resource_count=int(composition.get("required_resource_count") or 0),
            composition_provided_resource_count=int(composition.get("provided_resource_count") or 0),
            composition_reason_codes=composition_reason_codes,
            transition_evidence=transition,
            motif_participation=motif_participation,
            diagnoses=diagnoses,
            recommended_action_types=actions,
            notes=notes,
        )

    def _transition_summary(
        self, skill_id: str, transition_graph: Dict[str, Any]
    ) -> SkillTransitionEvidenceSummary:
        summary = SkillTransitionEvidenceSummary()
        reason_codes: Set[str] = set()
        edge_ids: List[str] = []
        for edge in transition_graph.get("edges", []):
            from_skill = edge.get("from_skill_id")
            to_skill = edge.get("to_skill_id")
            if from_skill != skill_id and to_skill != skill_id:
                continue
            decision = edge.get("edge_decision") or "unknown"
            if from_skill == skill_id:
                if decision == "usable":
                    summary.outgoing_usable_count += 1
                elif decision == "caution":
                    summary.outgoing_caution_count += 1
                elif decision == "blocked":
                    summary.outgoing_blocked_count += 1
            if to_skill == skill_id:
                if decision == "usable":
                    summary.incoming_usable_count += 1
                elif decision == "caution":
                    summary.incoming_caution_count += 1
                elif decision == "blocked":
                    summary.incoming_blocked_count += 1
            if edge.get("relation_type") == "local_order":
                summary.local_only_edge_count += 1
            edge_ids.append(edge.get("edge_id") or "")
            reason_codes.update(edge.get("reason_codes") or [])
        summary.transition_edge_ids = sorted([edge_id for edge_id in edge_ids if edge_id])
        summary.transition_reason_codes = sorted(reason_codes)
        return summary

    def _diagnoses(
        self,
        typed_required: int,
        typed_optional: int,
        typed_provided: int,
        legacy_required: List[str],
        legacy_optional: List[str],
        legacy_provided: List[str],
        source_candidate_count: int,
        readiness_reason_codes: List[str],
        composition_roles: List[str],
        composition_required_count: int,
        composition_provided_count: int,
        composition_reason_codes: List[str],
        transition: SkillTransitionEvidenceSummary,
    ) -> List[DiagnosisCode]:
        diagnoses: List[DiagnosisCode] = []
        typed_total = typed_required + typed_optional + typed_provided
        legacy_signal = bool(legacy_required or legacy_optional or legacy_provided)
        inferred_signal = bool(
            composition_required_count
            or composition_provided_count
            or "typed_resources_inferred_from_legacy_semantics" in composition_reason_codes
        )
        edge_signal = (
            transition.incoming_usable_count
            + transition.outgoing_usable_count
            + transition.incoming_caution_count
            + transition.outgoing_caution_count
        )
        if typed_total == 0:
            diagnoses.append("missing_typed_resources")
        if source_candidate_count < 2 or "single_source_support" in readiness_reason_codes:
            diagnoses.append("weak_support_diversity")
        if edge_signal == 0 or transition.local_only_edge_count == edge_signal:
            diagnoses.append("transition_evidence_absent_or_local_only")
        if not composition_roles:
            diagnoses.append("missing_graph_role")
        if typed_total == 0 and (legacy_signal or inferred_signal):
            diagnoses.append("candidate_ready_for_manual_resource_patch")
        if source_candidate_count < 2:
            diagnoses.append("candidate_needs_new_source_evidence")
        if "missing_typed_resources" in diagnoses or "weak_support_diversity" in diagnoses:
            diagnoses.append("candidate_should_remain_sampled_with_caution")
        if (
            "candidate_needs_new_source_evidence" in diagnoses
            and not legacy_signal
            and not inferred_signal
        ):
            diagnoses.append("do_not_patch_without_reviewer_or_source_evidence")
        return sorted(set(diagnoses))

    def _record_actions(self, diagnoses: List[DiagnosisCode]) -> List[RemediationActionType]:
        action_types: List[RemediationActionType] = []
        if "candidate_ready_for_manual_resource_patch" in diagnoses:
            action_types.append("manual_resource_patch")
        if "candidate_needs_new_source_evidence" in diagnoses:
            action_types.append("new_source_evidence")
        if "transition_evidence_absent_or_local_only" in diagnoses:
            action_types.append("transition_evidence_calibration")
        if "candidate_should_remain_sampled_with_caution" in diagnoses:
            action_types.append("sampler_caution")
        if "do_not_patch_without_reviewer_or_source_evidence" in diagnoses:
            action_types.append("hold_for_review")
        return sorted(set(action_types))

    def _remediation_actions(
        self, records: List[SkillSubstrateAuditRecord]
    ) -> List[PipelineASubstrateRemediationAction]:
        by_action: Dict[str, List[str]] = defaultdict(list)
        for record in records:
            for action_type in record.recommended_action_types:
                by_action[action_type].append(record.skill_id)
        actions: List[PipelineASubstrateRemediationAction] = []
        if by_action.get("manual_resource_patch"):
            actions.append(
                PipelineASubstrateRemediationAction(
                    action_id="substrate_action_001_manual_typed_resource_patch",
                    priority=1,
                    action_type="manual_resource_patch",
                    title="Draft typed-resource patch proposals for batch-selected skills",
                    rationale=(
                        "Pipeline B repeatedly fell back to legacy resource inference; selected registry entries "
                        "have no persistent SemanticResource interfaces even when composition inference has patch material."
                    ),
                    skill_ids=sorted(by_action["manual_resource_patch"]),
                    reason_codes=["missing_typed_resources", "low_subgraph_confidence"],
                    suggested_next_step=(
                        "Generate reviewed patch proposals from legacy semantics and composition inferred counts; "
                        "do not write them to the registry until reviewed against source evidence."
                    ),
                )
            )
        if by_action.get("new_source_evidence"):
            actions.append(
                PipelineASubstrateRemediationAction(
                    action_id="substrate_action_002_expand_source_support",
                    priority=2,
                    action_type="new_source_evidence",
                    title="Collect or admit additional evidence for single-source sampled skills",
                    rationale="Several sampled skills have only one source candidate ID and should not be up-weighted yet.",
                    skill_ids=sorted(by_action["new_source_evidence"]),
                    reason_codes=["single_source_support", "weak_support_diversity"],
                    suggested_next_step=(
                        "Run targeted Pipeline A source collection or review calibration candidates for these skills."
                    ),
                )
            )
        if by_action.get("transition_evidence_calibration"):
            actions.append(
                PipelineASubstrateRemediationAction(
                    action_id="substrate_action_003_transition_evidence_calibration",
                    priority=3,
                    action_type="transition_evidence_calibration",
                    title="Calibrate transition evidence for sampled skill pairs",
                    rationale=(
                        "Current transition evidence is absent for some selected skills and local-order-only for others; "
                        "Pipeline B cannot yet distinguish robust subgraphs from co-occurrence."
                    ),
                    skill_ids=sorted(by_action["transition_evidence_calibration"]),
                    reason_codes=["transition_evidence_absent_or_local_only", "pipeline_a_signal_gaps"],
                    suggested_next_step=(
                        "Use calibration-only Pipeline A runs or reviewed source traces to propose transition priors."
                    ),
                )
            )
        if by_action.get("sampler_caution"):
            actions.append(
                PipelineASubstrateRemediationAction(
                    action_id="substrate_action_004_keep_sampler_caution",
                    priority=4,
                    action_type="sampler_caution",
                    title="Keep sampled skills visible but caution-tagged until substrate improves",
                    rationale="The batch can continue exploring these skills, but downstream reports should retain low-confidence warnings.",
                    skill_ids=sorted(by_action["sampler_caution"]),
                    reason_codes=["candidate_should_remain_sampled_with_caution"],
                    suggested_next_step="Do not promote these cases to candidate_ready solely from deterministic packaging success.",
                )
            )
        if by_action.get("hold_for_review"):
            actions.append(
                PipelineASubstrateRemediationAction(
                    action_id="substrate_action_005_hold_weak_unbacked_entries",
                    priority=5,
                    action_type="hold_for_review",
                    title="Hold weak entries that lack reviewer or source-backed patch material",
                    rationale="Some entries may need reviewer intervention before any registry patch is safe.",
                    skill_ids=sorted(by_action["hold_for_review"]),
                    reason_codes=["do_not_patch_without_reviewer_or_source_evidence"],
                    suggested_next_step="Keep report-first and request new evidence instead of patching from thin signals.",
                )
            )
        return actions

    def _diagnostics(
        self, batch_report: PipelineBBatchRunReport, records: List[SkillSubstrateAuditRecord]
    ) -> PipelineASubstrateAuditDiagnostics:
        diagnosis_counts = Counter()
        action_counts = Counter()
        for record in records:
            diagnosis_counts.update(record.diagnoses)
            action_counts.update(record.recommended_action_types)
        return PipelineASubstrateAuditDiagnostics(
            audited_skill_count=len(records),
            batch_case_count=len(batch_report.cases),
            missing_typed_resource_skill_count=diagnosis_counts["missing_typed_resources"],
            weak_support_skill_count=diagnosis_counts["weak_support_diversity"],
            single_source_skill_count=sum(
                1 for record in records if record.registry_source_candidate_count == 1
            ),
            multi_source_skill_count=sum(
                1 for record in records if record.registry_source_candidate_count >= 2
            ),
            transition_gap_skill_count=diagnosis_counts["transition_evidence_absent_or_local_only"],
            missing_graph_role_skill_count=diagnosis_counts["missing_graph_role"],
            manual_resource_patch_candidate_count=diagnosis_counts[
                "candidate_ready_for_manual_resource_patch"
            ],
            new_source_evidence_candidate_count=diagnosis_counts["candidate_needs_new_source_evidence"],
            sampled_with_caution_recommended_count=diagnosis_counts[
                "candidate_should_remain_sampled_with_caution"
            ],
            hold_for_review_count=diagnosis_counts["do_not_patch_without_reviewer_or_source_evidence"],
            diagnosis_counts=dict(sorted(diagnosis_counts.items())),
            action_counts=dict(sorted(action_counts.items())),
            notes=[
                "Source support counts distinguish exact single-source entries from merged two-source entries.",
                "Transition evidence counts include local-order report edges but do not treat them as durable priors.",
            ],
        )
