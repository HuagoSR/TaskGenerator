import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_generator.v2_schema import (
    ColumnSpec,
    DataRelationship,
    DataSpec,
    DeliverableSpec,
    FileSpec,
    GoldenPlan,
    PromptSpec,
    ScenarioSpec,
    SheetSpec,
    TaskBlueprint,
    TaskMetadata,
)
from task_generator.v3_skill_registry import SkillRegistryBuilder
from task_generator.v3_source_schema import SkillRegistryEntry, load_json_file


DEFAULT_MOTIF_PRIORITY = [
    "evidence_to_deliverable",
    "cross_check_validation",
    "fan_in_reconciliation",
    "policy_application",
]

MOTIF_BLUEPRINT_HINTS = {
    "evidence_to_deliverable": {
        "template_family": "evidence_package_to_business_deliverable",
        "deliverable_name": "evidence_review_memo.docx",
        "deliverable_requirements": [
            "summarize the evidence reviewed",
            "state the conclusion supported by the evidence",
            "flag unresolved exceptions or missing support",
        ],
        "scenario_goal": "Prepare a concise evidence-backed deliverable for manager review.",
    },
    "cross_check_validation": {
        "template_family": "cross_source_validation_workpaper",
        "deliverable_name": "validation_workpaper.xlsx",
        "deliverable_requirements": [
            "show independent checks used to validate the conclusion",
            "separate matched, unmatched, and unresolved items",
            "document judgment calls and follow-up needs",
        ],
        "scenario_goal": "Validate a business conclusion by cross-checking independent evidence paths.",
    },
    "fan_in_reconciliation": {
        "template_family": "multi_source_reconciliation_workpaper",
        "deliverable_name": "reconciliation_workpaper.xlsx",
        "deliverable_requirements": [
            "reconcile source totals to the requested reporting view",
            "explain material differences",
            "identify evidence gaps that affect confidence",
        ],
        "scenario_goal": "Reconcile multiple evidence sources into one review-ready workpaper.",
    },
    "policy_application": {
        "template_family": "policy_application_review",
        "deliverable_name": "policy_application_memo.docx",
        "deliverable_requirements": [
            "identify the applicable policy or requirement",
            "apply the rule to the provided cases",
            "separate compliant, exception, and uncertain items",
        ],
        "scenario_goal": "Apply stated policy requirements to concrete evidence and document exceptions.",
    },
}

RESOURCE_ALIASES = {
    "audit": "ControlEvidence",
    "compliance": "ComplianceRequirement",
    "control": "ControlEvidence",
    "currency": "MonetaryAmount",
    "deliverable": "DeliverableSection",
    "document": "SourceDocument",
    "evidence": "ControlEvidence",
    "exception": "ExceptionRecord",
    "finding": "AuditFinding",
    "financial": "FinancialMetric",
    "jurisdiction": "Jurisdiction",
    "policy": "PolicyRule",
    "reconcile": "ReconciliationDifference",
    "reconciliation": "ReconciliationDifference",
    "report": "DeliverableSection",
    "requirement": "ComplianceRequirement",
    "revenue": "MonetaryAmount",
    "sample": "AuditSample",
    "table": "StructuredTable",
    "tax": "PolicyRule",
    "time": "TimePeriod",
    "variance": "ReconciliationDifference",
}


class PipelineBPrototypeBuilder:
    """Minimal report-only Pipeline B assembler for Pipeline A handoff artifacts."""

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()

    def build_report(
        self,
        registry_path: str | Path,
        seed_report_path: str | Path,
        motif: Optional[str] = None,
        skill_count: int = 4,
    ) -> Dict[str, Any]:
        entries = self.registry_builder.load_registry(registry_path)
        entry_by_id = {entry.skill_id: entry for entry in entries}
        seed_report = load_json_file(str(seed_report_path))
        seed_records = list(seed_report.get("seed_records", []))
        selected_motif = motif or self._choose_motif(seed_report)
        selected_records = self._select_records(seed_records, selected_motif, skill_count)
        selected_entries = [
            entry_by_id[record["skill_id"]]
            for record in selected_records
            if record.get("skill_id") in entry_by_id
        ]
        blueprint = self._build_blueprint(selected_motif, selected_records, selected_entries)
        diagnostics = self._diagnose_signals(selected_motif, selected_records, selected_entries)

        return {
            "pipeline_b_prototype_version": "v3.pipeline_b_prototype.1",
            "run_mode": "report_only",
            "registry_path": str(registry_path),
            "seed_report_path": str(seed_report_path),
            "motif": selected_motif,
            "requested_skill_count": skill_count,
            "selected_skill_count": len(selected_records),
            "selected_skills": selected_records,
            "draft_task_blueprint": blueprint.model_dump(),
            "assembly_diagnostics": diagnostics,
            "next_pipeline_a_feedback": self._feedback_items(diagnostics),
            "notes": [
                "This prototype does not mutate SkillRegistryEntry records.",
                "The draft blueprint is intentionally pre-GoldenRun and pre-rw-task export.",
                "Typed resource fields are preferred when present; legacy semantic contracts are used as fallback signals.",
            ],
        }

    def build_report_from_subgraph_report(
        self,
        subgraph_report_path: str | Path,
        registry_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        from task_generator.v3_pipeline_b_sampler import PipelineBSubgraph

        subgraph_payload = load_json_file(str(subgraph_report_path))
        subgraph = PipelineBSubgraph.model_validate(subgraph_payload)
        effective_registry_path = registry_path or subgraph.request.registry_path
        entries = self.registry_builder.load_registry(effective_registry_path)
        entry_by_id = {entry.skill_id: entry for entry in entries}
        selected_records = self._records_from_subgraph(subgraph, entry_by_id)
        selected_entries = [
            entry_by_id[record["skill_id"]]
            for record in selected_records
            if record.get("skill_id") in entry_by_id
        ]
        blueprint = self._build_blueprint(subgraph.selected_motif, selected_records, selected_entries)
        self._apply_subgraph_context(blueprint, subgraph)
        diagnostics = self._diagnose_subgraph_signals(subgraph, selected_records)

        return {
            "pipeline_b_prototype_version": "v3.pipeline_b_prototype.2",
            "run_mode": "report_only",
            "assembly_source": "pipeline_b_subgraph",
            "registry_path": str(effective_registry_path),
            "seed_report_path": subgraph.request.seed_report_path,
            "subgraph_report_path": str(subgraph_report_path),
            "subgraph_id": subgraph.subgraph_id,
            "subgraph_confidence": subgraph.diagnostics.confidence,
            "subgraph_missing_signals": subgraph.diagnostics.missing_or_weak_pipeline_a_signals,
            "motif": subgraph.selected_motif,
            "requested_skill_count": subgraph.request.skill_count,
            "selected_skill_count": len(selected_records),
            "selected_skills": selected_records,
            "draft_task_blueprint": blueprint.model_dump(),
            "assembly_diagnostics": diagnostics,
            "next_pipeline_a_feedback": self._feedback_items(diagnostics),
            "notes": [
                "This prototype consumes a report-only PipelineBSubgraph and does not mutate registry files.",
                "The draft blueprint is intentionally pre-GoldenRun and pre-rw-task export.",
                "Subgraph confidence and missing signals are preserved for downstream generators.",
            ],
        }

    def write_outputs(self, report: Dict[str, Any], output_dir: str | Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "pipeline_b_prototype_report.json"
        blueprint_path = output_path / "draft_task_blueprint.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        blueprint_path.write_text(
            json.dumps(report["draft_task_blueprint"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "report_path": str(report_path),
            "blueprint_path": str(blueprint_path),
        }

    def _records_from_subgraph(self, subgraph, entry_by_id: Dict[str, SkillRegistryEntry]) -> List[Dict[str, Any]]:
        records = []
        for skill in subgraph.selected_skills:
            entry = entry_by_id.get(skill.skill_id)
            records.append(
                {
                    "skill_id": skill.skill_id,
                    "canonical_name": skill.canonical_name,
                    "readiness_decision": skill.readiness_decision,
                    "sampling_weight": skill.sampling_weight,
                    "seed_score": skill.seed_score,
                    "seed_tier": "subgraph_selected",
                    "domain_tags": skill.domain_tags,
                    "capability_tags": skill.capability_tags,
                    "difficulty_tags": entry.difficulty_tags if entry else [],
                    "resource_types": sorted(
                        {
                            node.resource_type
                            for node in subgraph.resource_nodes
                            if node.skill_id == skill.skill_id and node.resource_type
                        }
                    ),
                    "required_resource_count": sum(
                        1
                        for node in subgraph.resource_nodes
                        if node.skill_id == skill.skill_id and node.direction == "required"
                    ),
                    "provided_resource_count": sum(
                        1
                        for node in subgraph.resource_nodes
                        if node.skill_id == skill.skill_id and node.direction == "provided"
                    ),
                    "motif_hints": skill.motif_hints,
                    "graph_role_hints": skill.graph_role_hints,
                    "reason_codes": skill.reason_codes,
                    "selection_rationale": skill.selection_reason,
                    "risk_notes": self._subgraph_skill_risk_notes(skill, subgraph),
                }
            )
        return records

    def _subgraph_skill_risk_notes(self, skill, subgraph) -> List[str]:
        notes = []
        if "single_source_support" in skill.reason_codes:
            notes.append("Single-source support; keep source provenance visible.")
        if subgraph.diagnostics.confidence == "low_due_to_resource_fallback":
            notes.append("Subgraph uses fallback resource inference; typed resources are missing or incomplete.")
        if not any(node.skill_id == skill.skill_id and node.evidence_mode == "typed" for node in subgraph.resource_nodes):
            notes.append("No typed SemanticResource nodes found for this selected skill.")
        return notes

    def _apply_subgraph_context(self, blueprint: TaskBlueprint, subgraph) -> None:
        resource_types = sorted({node.resource_type for node in subgraph.resource_nodes if node.resource_type})
        edge_modes = sorted({edge.evidence_mode for edge in subgraph.subgraph_edges})
        if resource_types:
            blueprint.prompt_spec.visible_requirements.append(
                "The task should exercise evidence/resource types: " + ", ".join(resource_types[:8]) + "."
            )
        if subgraph.diagnostics.confidence == "low_due_to_resource_fallback":
            blueprint.prompt_spec.hidden_requirements.append(
                "Treat current resource compatibility as provisional because it was inferred from legacy semantics."
            )
        if subgraph.diagnostics.unresolved_gaps:
            blueprint.golden_plan.required_intermediate_states.append("pipeline_a_signal_gap_review")
        if edge_modes:
            blueprint.golden_plan.required_intermediate_states.append(
                "subgraph_edge_evidence_review:" + ",".join(edge_modes[:5])
            )

    def _diagnose_subgraph_signals(self, subgraph, selected_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        reason_counts = Counter(reason for record in selected_records for reason in record.get("reason_codes", []))
        resource_types = sorted({node.resource_type for node in subgraph.resource_nodes if node.resource_type})
        typed_counts = Counter(node.direction for node in subgraph.resource_nodes if node.evidence_mode == "typed")
        legacy_counts = Counter(node.direction for node in subgraph.resource_nodes if node.evidence_mode == "legacy_inferred")
        return {
            "selected_motif": subgraph.selected_motif,
            "readiness_counts": subgraph.diagnostics.readiness_counts,
            "selected_motif_counts": subgraph.diagnostics.motif_coverage,
            "graph_role_counts": subgraph.diagnostics.role_coverage,
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "typed_resource_counts": {
                "required": typed_counts.get("required", 0),
                "optional": typed_counts.get("optional", 0),
                "provided": typed_counts.get("provided", 0),
            },
            "legacy_inferred_resource_counts": {
                "required": legacy_counts.get("required", 0),
                "optional": legacy_counts.get("optional", 0),
                "provided": legacy_counts.get("provided", 0),
            },
            "inferred_legacy_resource_types": resource_types,
            "edge_counts": subgraph.diagnostics.edge_counts,
            "fallback_evidence": subgraph.diagnostics.fallback_evidence,
            "unresolved_gaps": subgraph.diagnostics.unresolved_gaps,
            "missing_or_weak_pipeline_a_signals": subgraph.diagnostics.missing_or_weak_pipeline_a_signals,
            "prototype_confidence": subgraph.diagnostics.confidence,
        }

    def _choose_motif(self, seed_report: Dict[str, Any]) -> str:
        counts = seed_report.get("selected_motif_counts", {})
        for motif in DEFAULT_MOTIF_PRIORITY:
            if counts.get(motif, 0) > 0:
                return motif
        return "evidence_to_deliverable"

    def _select_records(
        self,
        seed_records: List[Dict[str, Any]],
        motif: str,
        skill_count: int,
    ) -> List[Dict[str, Any]]:
        matching = [record for record in seed_records if motif in record.get("motif_hints", [])]
        matching.sort(key=lambda record: (-float(record.get("seed_score", 0.0)), record.get("canonical_name", "")))

        selected: List[Dict[str, Any]] = []
        seen = set()
        for record in matching:
            selected.append(record)
            seen.add(record.get("skill_id"))
            if len(selected) >= skill_count:
                break

        if len(selected) < skill_count:
            fallback = sorted(
                seed_records,
                key=lambda record: (-float(record.get("seed_score", 0.0)), record.get("canonical_name", "")),
            )
            for record in fallback:
                if record.get("skill_id") in seen:
                    continue
                selected.append(record)
                seen.add(record.get("skill_id"))
                if len(selected) >= skill_count:
                    break

        return selected

    def _build_blueprint(
        self,
        motif: str,
        selected_records: List[Dict[str, Any]],
        selected_entries: List[SkillRegistryEntry],
    ) -> TaskBlueprint:
        hints = MOTIF_BLUEPRINT_HINTS.get(motif, MOTIF_BLUEPRINT_HINTS["evidence_to_deliverable"])
        skill_names = [record.get("canonical_name", "") for record in selected_records]
        selected_skill_ids = [record.get("skill_id", "") for record in selected_records if record.get("skill_id")]
        domain_counts = Counter(domain for entry in selected_entries for domain in entry.domain_tags)
        primary_domain = domain_counts.most_common(1)[0][0] if domain_counts else "finance"
        occupation = self._infer_occupation(primary_domain, selected_entries)

        return TaskBlueprint(
            blueprint_id=f"bp_pipeline_b_{uuid.uuid4().hex[:8]}",
            template_family=hints["template_family"],
            task_metadata=TaskMetadata(
                sector=self._title(primary_domain),
                occupation=occupation,
                scenario_title=self._scenario_title(motif, primary_domain),
                task_goal=hints["scenario_goal"],
                difficulty_level=self._difficulty_level(selected_records),
            ),
            selected_skills=selected_skill_ids,
            scenario_spec=ScenarioSpec(
                role=f"You are a {occupation} preparing a review package for a manager.",
                business_context=self._business_context(motif, skill_names),
                time_context="Current-period review with all source evidence provided in the reference package.",
                tone="professional, business-realistic, non-tutorial",
            ),
            data_spec=DataSpec(
                reference_files=self._reference_files(motif, selected_entries),
                data_relationships=self._data_relationships(motif, selected_entries),
            ),
            trap_spec=[],
            deliverable_spec=[
                DeliverableSpec(
                    file_name=hints["deliverable_name"],
                    file_role="final_deliverable",
                    requirements=hints["deliverable_requirements"],
                )
            ],
            prompt_spec=PromptSpec(
                visible_requirements=self._visible_requirements(
                    motif, skill_names, hints["deliverable_name"], selected_entries
                ),
                hidden_requirements=self._hidden_requirements(motif, selected_entries),
                style_constraints=[
                    "realistic business memo tone",
                    "no trap disclosure",
                    "use only the provided reference files",
                ],
            ),
            golden_plan=GoldenPlan(
                required_intermediate_states=self._intermediate_states(motif, selected_entries),
                required_final_checks=self._final_checks(motif, selected_entries),
            ),
        )

    def _reference_files(self, motif: str, entries: List[SkillRegistryEntry]) -> List[FileSpec]:
        files = [
            FileSpec(
                file_name="source_evidence.xlsx",
                file_role="source_data",
                sheet_specs=[
                    SheetSpec(
                        sheet_name="Evidence_Items",
                        row_count_target=18,
                        columns=[
                            ColumnSpec(name="Evidence_ID", semantic_type="identifier"),
                            ColumnSpec(name="Source", semantic_type="source_label"),
                            ColumnSpec(name="Entity_or_Item", semantic_type="business_entity"),
                            ColumnSpec(name="Observed_Value", semantic_type="mixed_fact"),
                            ColumnSpec(name="Period", semantic_type="time_period"),
                        ],
                    )
                ],
            )
        ]
        if motif in {"policy_application", "cross_check_validation"} or self._mentions(entries, ["policy", "requirement", "tax"]):
            files.append(
                FileSpec(
                    file_name="policy_reference.docx",
                    file_role="reference_table",
                    sheet_specs=[],
                )
            )
        if motif in {"fan_in_reconciliation", "cross_check_validation"}:
            files.append(
                FileSpec(
                    file_name="control_totals.xlsx",
                    file_role="reference_table",
                    sheet_specs=[
                        SheetSpec(
                            sheet_name="Control_Totals",
                            row_count_target=8,
                            columns=[
                                ColumnSpec(name="Control_ID", semantic_type="identifier"),
                                ColumnSpec(name="Expected_Total", semantic_type="amount_or_count"),
                                ColumnSpec(name="Basis", semantic_type="free_text_description"),
                            ],
                        )
                    ],
                )
            )
        return files

    def _data_relationships(self, motif: str, entries: List[SkillRegistryEntry]) -> List[DataRelationship]:
        relationships = [
            DataRelationship(
                relation_type="evidence_trace",
                left="source_evidence.xlsx:Evidence_Items.Evidence_ID",
                right="final_deliverable:evidence_citations",
            )
        ]
        if motif in {"fan_in_reconciliation", "cross_check_validation"}:
            relationships.append(
                DataRelationship(
                    relation_type="cross_check",
                    left="source_evidence.xlsx:Evidence_Items.Observed_Value",
                    right="control_totals.xlsx:Control_Totals.Expected_Total",
                )
            )
        if motif == "policy_application" or self._mentions(entries, ["policy", "requirement", "tax"]):
            relationships.append(
                DataRelationship(
                    relation_type="policy_lookup",
                    left="source_evidence.xlsx:Evidence_Items.Entity_or_Item",
                    right="policy_reference.docx:applicable_requirements",
                )
            )
        return relationships

    def _visible_requirements(
        self,
        motif: str,
        skill_names: List[str],
        deliverable_name: str,
        entries: List[SkillRegistryEntry],
    ) -> List[str]:
        requirements = [
            "Review the provided reference files and produce the requested deliverable.",
            f"Write the final deliverable as `{deliverable_name}` and keep the content manager-ready.",
            "Cite the evidence IDs or source labels that support each material conclusion.",
            "Flag items that cannot be resolved from the provided evidence.",
            "Separate supported conclusions, confirmed exceptions, and unresolved items instead of blending them together.",
            "Include an `Evidence inventory` section before the final conclusions; list each material evidence ID, source file, observed item, and intended use.",
            "Include a `Deliverable outline` section before drafting conclusions; use headings for evidence reviewed, supported conclusions, confirmed exceptions, unresolved items, policy mapping, and follow-up.",
            "Include an `Evidence-to-conclusion map` that links each material conclusion to the specific evidence IDs used.",
            "In `Supported conclusions`, `Confirmed exceptions`, and `Unresolved items`, end every material bullet with bracketed local support such as `[Evidence: EV-###]` or `[Evidence: EV-###; Policy: POL-###]`.",
            "Do not place evidence citations only in a separate appendix; each conclusion must carry its own local evidence or policy locator.",
        ]
        if motif == "fan_in_reconciliation":
            requirements.append("Reconcile source evidence to the control totals and explain material differences.")
        elif motif == "cross_check_validation":
            requirements.append("Use at least two independent evidence paths before marking a conclusion as validated.")
        elif motif == "policy_application":
            requirements.append("Apply the stated policy requirements to each relevant evidence item.")
        elif motif == "evidence_to_deliverable":
            requirements.append("Synthesize the evidence into a manager-ready deliverable rather than a raw notes list.")
        if self._mentions(entries, ["policy", "requirement", "tax", "compliance"]):
            requirements.append(
                "For each policy-sensitive conclusion, cite both the supporting evidence ID and the applicable policy clause ID."
            )
            requirements.append(
                "Include a `Policy clause mapping` section with columns or bullets for clause ID, governed evidence ID, applied conclusion, and any unresolved policy uncertainty."
            )
            requirements.append(
                "For every policy-sensitive bullet in the final deliverable, include both local evidence support and local policy support in the same bullet."
            )
        if skill_names:
            requirements.append("The task should exercise: " + "; ".join(skill_names[:4]) + ".")
        return requirements

    def _hidden_requirements(self, motif: str, entries: List[SkillRegistryEntry]) -> List[str]:
        hidden = [
            "Do not reward unsupported conclusions that lack visible evidence citations.",
            "Do not reward conclusion bullets whose evidence support appears only elsewhere in the deliverable.",
            "Treat unresolved evidence gaps separately from confirmed exceptions.",
            "The expected deliverable should be supportable from candidate-visible reference files, not hidden teacher assumptions.",
        ]
        if motif in {"cross_check_validation", "fan_in_reconciliation"}:
            hidden.append("The teacher run should expose intermediate cross-check or reconciliation states.")
        if self._mentions(entries, ["policy", "requirement", "tax", "compliance"]):
            hidden.append("Exact grading anchors must be traceable to visible policy or requirement evidence.")
            hidden.append("Policy-grounded claims should cite explicit clause IDs together with the evidence they govern.")
        return hidden

    def _intermediate_states(self, motif: str, entries: List[SkillRegistryEntry]) -> List[str]:
        states = ["evidence_inventory", "deliverable_outline", "evidence_to_conclusion_map"]
        if motif in {"fan_in_reconciliation", "cross_check_validation"}:
            states.append("cross_check_matrix")
        if motif == "fan_in_reconciliation":
            states.append("reconciliation_difference_log")
        if motif == "policy_application" or self._mentions(entries, ["policy", "requirement", "tax"]):
            states.append("policy_requirement_mapping")
            states.append("policy_clause_evidence_map")
        if self._mentions(entries, ["exception", "finding"]):
            states.append("exception_classification_log")
        return states

    def _final_checks(self, motif: str, entries: List[SkillRegistryEntry]) -> List[str]:
        checks = [
            "deliverable_presence",
            "deliverable_requirement_coverage",
            "evidence_traceability",
            "conclusion_supported_by_visible_evidence",
        ]
        if motif == "policy_application" or self._mentions(entries, ["policy", "requirement", "tax", "compliance"]):
            checks.insert(3, "policy_clause_traceability")
        return checks

    def _diagnose_signals(
        self,
        motif: str,
        selected_records: List[Dict[str, Any]],
        selected_entries: List[SkillRegistryEntry],
    ) -> Dict[str, Any]:
        typed_required = sum(len(entry.input_contract.required_resources) for entry in selected_entries)
        typed_optional = sum(len(entry.input_contract.optional_resources) for entry in selected_entries)
        typed_provided = sum(len(entry.output_contract.provided_resources) for entry in selected_entries)
        legacy_required = sum(len(entry.input_contract.requires_semantics) for entry in selected_entries)
        legacy_provided = sum(len(entry.output_contract.provides_semantics) for entry in selected_entries)
        inferred_resources = self._infer_legacy_resources(selected_entries)
        readiness_counts = Counter(record.get("readiness_decision", "unknown") for record in selected_records)
        reason_counts = Counter(reason for record in selected_records for reason in record.get("reason_codes", []))
        role_counts = Counter(role for record in selected_records for role in record.get("graph_role_hints", []))
        motif_counts = Counter(item for record in selected_records for item in record.get("motif_hints", []))

        missing = []
        if typed_required + typed_optional + typed_provided == 0:
            missing.append("persistent_registry_typed_resources")
        if not any(role in role_counts for role in ["starter", "transform", "fan_in", "validator", "synthesis"]):
            missing.append("usable_graph_role_coverage")
        if motif_counts.get(motif, 0) < len(selected_records):
            missing.append("full_motif_coverage_for_selected_subgraph")
        if "single_source_support" in reason_counts:
            missing.append("multi_source_evidence_support")

        return {
            "selected_motif": motif,
            "readiness_counts": dict(sorted(readiness_counts.items())),
            "selected_motif_counts": dict(sorted(motif_counts.items())),
            "graph_role_counts": dict(sorted(role_counts.items())),
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "typed_resource_counts": {
                "required": typed_required,
                "optional": typed_optional,
                "provided": typed_provided,
            },
            "legacy_semantic_contract_counts": {
                "requires": legacy_required,
                "provides": legacy_provided,
            },
            "inferred_legacy_resource_types": sorted(inferred_resources),
            "missing_or_weak_pipeline_a_signals": missing,
            "prototype_confidence": self._prototype_confidence(missing, selected_records),
        }

    def _feedback_items(self, diagnostics: Dict[str, Any]) -> List[str]:
        feedback = []
        missing = set(diagnostics.get("missing_or_weak_pipeline_a_signals", []))
        if "persistent_registry_typed_resources" in missing:
            feedback.append("Backfill or admit typed SemanticResource contracts into persistent registry entries.")
        if "full_motif_coverage_for_selected_subgraph" in missing:
            feedback.append("Improve motif hints so a sampled local subgraph has explicit motif coverage for every selected skill.")
        if "multi_source_evidence_support" in missing:
            feedback.append("Prefer or create registry entries with support from more than one source before broad Pipeline B sampling.")
        if not feedback:
            feedback.append("Pipeline A signals were sufficient for a report-only draft blueprint; next blocker is GoldenRun design.")
        feedback.append("Pipeline B still needs a general reference-file generator, TeacherRunner, rubric builder, and quality gate.")
        return feedback

    def _infer_legacy_resources(self, entries: List[SkillRegistryEntry]) -> set[str]:
        resources = set()
        for entry in entries:
            text_items = [
                *entry.input_contract.requires_semantics,
                *entry.input_contract.optional_semantics,
                *entry.output_contract.provides_semantics,
                entry.canonical_name,
                entry.business_meaning,
            ]
            compact = " ".join(text_items).lower()
            for key, resource_type in RESOURCE_ALIASES.items():
                if key in compact:
                    resources.add(resource_type)
        return resources

    def _prototype_confidence(self, missing: List[str], selected_records: List[Dict[str, Any]]) -> str:
        if not selected_records:
            return "blocked"
        if "persistent_registry_typed_resources" in missing:
            return "low_due_to_resource_fallback"
        if len(missing) >= 2:
            return "medium_with_pipeline_a_gaps"
        return "medium"

    def _difficulty_level(self, selected_records: List[Dict[str, Any]]) -> str:
        text = " ".join(" ".join(record.get("difficulty_tags", [])) for record in selected_records).lower()
        if any(term in text for term in ["hard", "advanced", "complex"]):
            return "hard"
        if any(term in text for term in ["medium", "reasoning", "compliance"]):
            return "medium"
        return "medium"

    def _infer_occupation(self, primary_domain: str, entries: List[SkillRegistryEntry]) -> str:
        text = " ".join([primary_domain, *[tag for entry in entries for tag in entry.domain_tags]]).lower()
        if "audit" in text:
            return "Senior Auditor"
        if "compliance" in text:
            return "Compliance Analyst"
        if "tax" in text:
            return "Tax Associate"
        if "finance" in text or "accounting" in text:
            return "Financial Analyst"
        return "Business Analyst"

    def _business_context(self, motif: str, skill_names: List[str]) -> str:
        base = "The team has received a compact evidence package and needs a review-ready conclusion with clear provenance."
        if skill_names:
            return base + " The sampled capabilities include " + "; ".join(skill_names[:4]) + "."
        return base + f" The task shape follows the {motif} motif."

    def _scenario_title(self, motif: str, primary_domain: str) -> str:
        words = re.sub(r"[_-]+", " ", motif).title()
        return f"{self._title(primary_domain)} {words} Review"

    def _mentions(self, entries: List[SkillRegistryEntry], terms: List[str]) -> bool:
        parts = []
        for entry in entries:
            parts.extend(
                [
                    entry.canonical_name,
                    " ".join(entry.domain_tags),
                    " ".join(entry.capability_tags),
                    entry.business_meaning,
                    entry.hidden_difficulty,
                ]
            )
        text = " ".join(parts).lower()
        return any(term in text for term in terms)

    def _title(self, text: str) -> str:
        return re.sub(r"[_-]+", " ", text).title()
