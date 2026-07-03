from __future__ import annotations

import re
from collections import Counter
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_a_substrate_audit import (
    PipelineASubstrateAuditReport,
    SkillSubstrateAuditRecord,
)
from task_generator.v3_source_schema import SemanticResource, load_json_file


ResourcePatchStatus = Literal["requires_review", "needs_source_evidence", "blocked"]
ResourcePatchConfidence = Literal["medium", "low"]
ResourcePatchRole = Literal["required", "optional", "provided"]


RESOURCE_ALIAS_RULES: List[Tuple[str, str]] = [
    ("withholdingtaxrate", "PolicyRule"),
    ("taxrate", "PolicyRule"),
    ("policyrule", "PolicyRule"),
    ("policy", "PolicyRule"),
    ("rule", "PolicyRule"),
    ("requirement", "ComplianceRequirement"),
    ("controldefinition", "ControlEvidence"),
    ("control", "ControlEvidence"),
    ("evidencecollection", "ControlEvidence"),
    ("evidence", "ControlEvidence"),
    ("procedures", "AuditProcedure"),
    ("procedure", "AuditProcedure"),
    ("sampleresult", "AuditSample"),
    ("sample", "AuditSample"),
    ("exceptionanalysis", "ExceptionRecord"),
    ("exception", "ExceptionRecord"),
    ("deviation", "ExceptionRecord"),
    ("finding", "AuditFinding"),
    ("variance", "ReconciliationDifference"),
    ("difference", "ReconciliationDifference"),
    ("reconcile", "ReconciliationDifference"),
    ("reconciled", "ReconciliationDifference"),
    ("grossrevenue", "MonetaryAmount"),
    ("netrevenue", "MonetaryAmount"),
    ("revenue", "MonetaryAmount"),
    ("amount", "MonetaryAmount"),
    ("financialstatement", "FinancialStatement"),
    ("statement", "FinancialStatement"),
    ("lineitem", "FinancialStatementLineItem"),
    ("reportline", "FinancialStatementLineItem"),
    ("report", "DeliverableSection"),
    ("schedule", "DeliverableSection"),
    ("workbook", "SpreadsheetWorkbook"),
    ("spreadsheet", "SpreadsheetWorkbook"),
    ("mapping", "MappingTable"),
    ("account", "AccountMapping"),
    ("branchleveldata", "Dataset"),
    ("aggregateview", "AggregatedView"),
    ("aggregatedview", "AggregatedView"),
    ("datafile", "Dataset"),
    ("sourcefile", "Dataset"),
    ("transactiondata", "Dataset"),
    ("populationdata", "Dataset"),
    ("rowwisedata", "Dataset"),
    ("columns", "Dataset"),
    ("data", "Dataset"),
    ("period", "TimePeriod"),
    ("quarter", "TimePeriod"),
    ("country", "Jurisdiction"),
    ("jurisdiction", "Jurisdiction"),
    ("confidencelevel", "SamplingParameter"),
    ("tolerableerror", "SamplingParameter"),
    ("samplesize", "AuditSample"),
    ("calculation", "ComputationTrace"),
    ("explanation", "Explanation"),
]


class TypedResourcePatchProposalRequest(BaseModel):
    substrate_audit_report_path: str
    output_dir: str
    include_low_confidence: bool = True


class ProposedTypedResource(BaseModel):
    proposal_id: str
    skill_id: str
    role: ResourcePatchRole
    source_semantic: str
    target_contract_path: str
    proposed_resource: SemanticResource
    confidence: ResourcePatchConfidence
    status: ResourcePatchStatus = "requires_review"
    inference_reason_codes: List[str] = Field(default_factory=list)
    review_notes: List[str] = Field(default_factory=list)


class SkillTypedResourcePatchProposal(BaseModel):
    skill_id: str
    canonical_name: str
    source_candidate_count: int = 0
    source_candidate_ids: List[str] = Field(default_factory=list)
    batch_case_ids: List[str] = Field(default_factory=list)
    batch_motifs: List[str] = Field(default_factory=list)
    registry_typed_resource_counts_before: Dict[str, int] = Field(default_factory=dict)
    proposed_required_resources: List[ProposedTypedResource] = Field(default_factory=list)
    proposed_optional_resources: List[ProposedTypedResource] = Field(default_factory=list)
    proposed_provided_resources: List[ProposedTypedResource] = Field(default_factory=list)
    proposal_status: ResourcePatchStatus = "requires_review"
    risk_reason_codes: List[str] = Field(default_factory=list)
    review_checklist: List[str] = Field(default_factory=list)


class TypedResourcePatchProposalDiagnostics(BaseModel):
    audited_skill_count: int = 0
    proposal_skill_count: int = 0
    proposed_resource_count: int = 0
    proposed_required_resource_count: int = 0
    proposed_optional_resource_count: int = 0
    proposed_provided_resource_count: int = 0
    low_confidence_resource_count: int = 0
    unknown_resource_type_count: int = 0
    needs_source_evidence_skill_count: int = 0
    status_counts: Dict[str, int] = Field(default_factory=dict)
    resource_type_counts: Dict[str, int] = Field(default_factory=dict)
    risk_reason_counts: Dict[str, int] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class TypedResourcePatchProposalReport(BaseModel):
    proposal_version: str = "v3.typed_resource_patch_proposal.1"
    request: TypedResourcePatchProposalRequest
    substrate_audit_summary: Dict[str, Any] = Field(default_factory=dict)
    skill_patch_proposals: List[SkillTypedResourcePatchProposal] = Field(default_factory=list)
    diagnostics: TypedResourcePatchProposalDiagnostics
    notes: List[str] = Field(default_factory=list)


class TypedResourcePatchProposalBuilder:
    """Build reviewed typed-resource patch proposals without mutating the registry."""

    def build(
        self,
        substrate_audit_report_path: str | Path,
        output_dir: str | Path,
        include_low_confidence: bool = True,
    ) -> TypedResourcePatchProposalReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = TypedResourcePatchProposalRequest(
            substrate_audit_report_path=str(substrate_audit_report_path),
            output_dir=str(output_path),
            include_low_confidence=include_low_confidence,
        )
        audit = PipelineASubstrateAuditReport.model_validate(
            load_json_file(str(substrate_audit_report_path))
        )
        proposals = [
            self._skill_proposal(record, include_low_confidence=include_low_confidence)
            for record in audit.skill_records
            if "manual_resource_patch" in record.recommended_action_types
        ]
        proposals = [proposal for proposal in proposals if self._resource_count(proposal) > 0]
        report = TypedResourcePatchProposalReport(
            request=request,
            substrate_audit_summary={
                "audited_skill_count": audit.diagnostics.audited_skill_count,
                "missing_typed_resource_skill_count": audit.diagnostics.missing_typed_resource_skill_count,
                "manual_resource_patch_candidate_count": audit.diagnostics.manual_resource_patch_candidate_count,
                "new_source_evidence_candidate_count": audit.diagnostics.new_source_evidence_candidate_count,
            },
            skill_patch_proposals=proposals,
            diagnostics=self._diagnostics(audit, proposals),
            notes=[
                "This report is a patch proposal only; it does not modify SkillRegistry/v3_skill_registry.json.",
                "Every proposed resource keeps its original legacy semantic string and requires review before application.",
                "Low-confidence and UnknownResource proposals are intentionally retained when include_low_confidence is true so reviewers can see gaps instead of hidden omissions.",
            ],
        )
        self.write_outputs(report, output_path)
        return report

    def write_outputs(
        self, report: TypedResourcePatchProposalReport, output_dir: str | Path
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "typed_resource_patch_proposals.json"
        summary_path = output_path / "typed_resource_patch_proposal_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        summary_payload = {
            "proposal_version": report.proposal_version,
            "request": report.request.model_dump(),
            "diagnostics": report.diagnostics.model_dump(),
            "skill_ids": [proposal.skill_id for proposal in report.skill_patch_proposals],
            "notes": report.notes,
        }
        summary_path.write_text(
            self._json_dumps(summary_payload),
            encoding="utf-8",
        )
        return {
            "typed_resource_patch_proposals_path": str(report_path),
            "typed_resource_patch_proposal_report_path": str(summary_path),
        }

    def _skill_proposal(
        self,
        record: SkillSubstrateAuditRecord,
        include_low_confidence: bool,
    ) -> SkillTypedResourcePatchProposal:
        required = [
            self._proposed_resource(record, "required", item)
            for item in record.legacy_required_semantics
        ]
        optional = [
            self._proposed_resource(record, "optional", item)
            for item in record.legacy_optional_semantics
        ]
        provided = [
            self._proposed_resource(record, "provided", item)
            for item in record.legacy_provided_semantics
        ]
        if not include_low_confidence:
            required = [item for item in required if item.confidence != "low"]
            optional = [item for item in optional if item.confidence != "low"]
            provided = [item for item in provided if item.confidence != "low"]
        risk_codes = self._risk_codes(record, required + optional + provided)
        status: ResourcePatchStatus = (
            "needs_source_evidence"
            if "candidate_needs_new_source_evidence" in record.diagnoses
            else "requires_review"
        )
        return SkillTypedResourcePatchProposal(
            skill_id=record.skill_id,
            canonical_name=record.canonical_name,
            source_candidate_count=record.registry_source_candidate_count,
            source_candidate_ids=record.registry_source_candidate_ids,
            batch_case_ids=record.batch_case_ids,
            batch_motifs=record.batch_motifs,
            registry_typed_resource_counts_before={
                "required": record.typed_required_resource_count,
                "optional": record.typed_optional_resource_count,
                "provided": record.typed_provided_resource_count,
            },
            proposed_required_resources=required,
            proposed_optional_resources=optional,
            proposed_provided_resources=provided,
            proposal_status=status,
            risk_reason_codes=risk_codes,
            review_checklist=self._review_checklist(record, risk_codes),
        )

    def _proposed_resource(
        self,
        record: SkillSubstrateAuditRecord,
        role: ResourcePatchRole,
        source_semantic: str,
    ) -> ProposedTypedResource:
        resource_type, subtype, reason_codes = self._infer_type_and_subtype(source_semantic)
        confidence: ResourcePatchConfidence = (
            "medium"
            if resource_type != "UnknownResource"
            and record.registry_source_candidate_count >= 2
            and (
                record.composition_required_resource_count
                or record.composition_provided_resource_count
                or "typed_resources_inferred_from_legacy_semantics" in record.composition_reason_codes
            )
            else "low"
        )
        status: ResourcePatchStatus = (
            "needs_source_evidence"
            if record.registry_source_candidate_count < 2
            else "requires_review"
        )
        target_path = {
            "required": "input_contract.required_resources",
            "optional": "input_contract.optional_resources",
            "provided": "output_contract.provided_resources",
        }[role]
        resource = SemanticResource(
            resource_type=resource_type,
            subtype=subtype,
            attributes={
                "role": role,
                "source_semantic": source_semantic,
                "proposal_source": "pipeline_a_substrate_audit",
                "proposal_status": status,
            },
            domain=record.domain_tags[0] if record.domain_tags else "",
            evidence_refs=record.registry_source_candidate_ids,
        )
        review_notes = [
            "Verify resource type and subtype against the original source evidence before applying.",
        ]
        if resource_type == "UnknownResource":
            review_notes.append("Resource type could not be confidently inferred from aliases.")
        if record.registry_source_candidate_count < 2:
            review_notes.append("Skill has exact single-source support; collect more evidence before registry patch.")
        return ProposedTypedResource(
            proposal_id=self._proposal_id(record.skill_id, role, source_semantic),
            skill_id=record.skill_id,
            role=role,
            source_semantic=source_semantic,
            target_contract_path=target_path,
            proposed_resource=resource,
            confidence=confidence,
            status=status,
            inference_reason_codes=reason_codes,
            review_notes=review_notes,
        )

    def _infer_type_and_subtype(self, source_semantic: str) -> Tuple[str, str, List[str]]:
        text = source_semantic.strip()
        reason_codes: List[str] = []
        if ":" in text:
            namespace, subtype = [part.strip() for part in text.split(":", 1)]
            reason_codes.append("legacy_namespace_split")
            resource_type, alias_reason = self._infer_resource_type(subtype)
            if alias_reason:
                reason_codes.append(alias_reason)
                return resource_type, subtype or text, reason_codes
            return namespace or "UnknownResource", subtype or text, reason_codes
        resource_type, alias_reason = self._infer_resource_type(text)
        if alias_reason:
            reason_codes.append(alias_reason)
            return resource_type, text, reason_codes
        reason_codes.append("unknown_resource_type")
        return "UnknownResource", text, reason_codes

    def _infer_resource_type(self, text: str) -> Tuple[str, str]:
        compact = re.sub(r"[^a-z0-9]+", "", text.lower())
        for alias, resource_type in RESOURCE_ALIAS_RULES:
            if alias in compact:
                return resource_type, f"inferred_from_alias:{alias}"
        return "", ""

    def _risk_codes(
        self,
        record: SkillSubstrateAuditRecord,
        resources: List[ProposedTypedResource],
    ) -> List[str]:
        risks = set()
        if record.registry_source_candidate_count < 2:
            risks.add("single_source_support")
        if "transition_evidence_absent_or_local_only" in record.diagnoses:
            risks.add("transition_evidence_absent_or_local_only")
        if not record.composition_graph_role_hints:
            risks.add("missing_graph_role")
        if any(resource.proposed_resource.resource_type == "UnknownResource" for resource in resources):
            risks.add("unknown_resource_type")
        if any(resource.confidence == "low" for resource in resources):
            risks.add("low_confidence_patch")
        return sorted(risks)

    def _review_checklist(
        self,
        record: SkillSubstrateAuditRecord,
        risk_codes: List[str],
    ) -> List[str]:
        checklist = [
            "Compare each proposed resource with the original accepted candidate evidence.",
            "Confirm whether the resource is candidate-visible, teacher-only, or internal workflow state.",
            "Confirm that provided resources can satisfy at least one downstream required resource before raising sampler confidence.",
        ]
        if "single_source_support" in risk_codes:
            checklist.append("Collect or admit additional source evidence before applying this patch.")
        if "missing_graph_role" in risk_codes:
            checklist.append("Assign or review graph role hints before relying on this skill in composed subgraphs.")
        if record.transition_evidence.transition_edge_ids:
            checklist.append("Review existing local transition edge IDs before turning them into durable priors.")
        return checklist

    def _diagnostics(
        self,
        audit: PipelineASubstrateAuditReport,
        proposals: List[SkillTypedResourcePatchProposal],
    ) -> TypedResourcePatchProposalDiagnostics:
        resources = []
        status_counts = Counter()
        risk_counts = Counter()
        for proposal in proposals:
            all_resources = (
                proposal.proposed_required_resources
                + proposal.proposed_optional_resources
                + proposal.proposed_provided_resources
            )
            resources.extend(all_resources)
            status_counts[proposal.proposal_status] += 1
            risk_counts.update(proposal.risk_reason_codes)
        resource_type_counts = Counter(
            resource.proposed_resource.resource_type for resource in resources
        )
        return TypedResourcePatchProposalDiagnostics(
            audited_skill_count=audit.diagnostics.audited_skill_count,
            proposal_skill_count=len(proposals),
            proposed_resource_count=len(resources),
            proposed_required_resource_count=sum(
                len(proposal.proposed_required_resources) for proposal in proposals
            ),
            proposed_optional_resource_count=sum(
                len(proposal.proposed_optional_resources) for proposal in proposals
            ),
            proposed_provided_resource_count=sum(
                len(proposal.proposed_provided_resources) for proposal in proposals
            ),
            low_confidence_resource_count=sum(
                1 for resource in resources if resource.confidence == "low"
            ),
            unknown_resource_type_count=resource_type_counts["UnknownResource"],
            needs_source_evidence_skill_count=status_counts["needs_source_evidence"],
            status_counts=dict(sorted(status_counts.items())),
            resource_type_counts=dict(sorted(resource_type_counts.items())),
            risk_reason_counts=dict(sorted(risk_counts.items())),
            notes=[
                "Proposal counts are based on legacy semantic strings and audit-inferred patch candidates.",
                "Applying proposals to the persistent registry requires a separate reviewed apply step.",
            ],
        )

    def _resource_count(self, proposal: SkillTypedResourcePatchProposal) -> int:
        return (
            len(proposal.proposed_required_resources)
            + len(proposal.proposed_optional_resources)
            + len(proposal.proposed_provided_resources)
        )

    def _proposal_id(self, skill_id: str, role: str, source_semantic: str) -> str:
        digest = sha1(f"{skill_id}|{role}|{source_semantic}".encode("utf-8")).hexdigest()[:10]
        return f"typed_resource_patch_{digest}"

    def _json_dumps(self, payload: Dict[str, Any]) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, indent=2)
