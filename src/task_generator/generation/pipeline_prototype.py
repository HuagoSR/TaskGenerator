import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_generator.core.schema import (
    ColumnSpec,
    DataRelationship,
    DataRelationship,
    DataSpec,
    DeliverableSpec,
    FileSpec,
    GoldenPlan,
    InjectionPolicy,
    InjectionTarget,
    PromptSpec,
    ScenarioSpec,
    SheetSpec,
    TaskBlueprint,
    TaskMetadata,
    TrapSpec,
)
from task_generator.substrate.skill_registry import SkillRegistryBuilder
from task_generator.core.source_schema import SkillRegistryEntry, load_json_file
from task_generator.substrate.domain_profile import DomainProfile, load_domain_profile


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
        phase15_reform_spec_path: Optional[str | Path] = None,
        domain_profile: Optional[DomainProfile] = None,
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
        reform_spec = self._load_phase15_reform_spec(phase15_reform_spec_path, selected_motif)
        domain_profile = domain_profile or load_domain_profile("finance_audit")
        blueprint = self._build_blueprint(selected_motif, selected_records, selected_entries, reform_spec)
        self._apply_domain_profile(blueprint, selected_motif, domain_profile)
        diagnostics = self._diagnose_signals(selected_motif, selected_records, selected_entries)

        return {
            "pipeline_b_prototype_version": "v3.pipeline_b_prototype.1",
            "run_mode": "report_only",
            "registry_path": str(registry_path),
            "seed_report_path": str(seed_report_path),
            "motif": selected_motif,
            "domain_profile_id": domain_profile.profile_id,
            "requested_skill_count": skill_count,
            "selected_skill_count": len(selected_records),
            "selected_skills": selected_records,
            "draft_task_blueprint": blueprint.model_dump(),
            "phase15_generator_reform": self._phase15_reform_metadata(reform_spec),
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
        phase15_reform_spec_path: Optional[str | Path] = None,
        domain_profile: Optional[DomainProfile] = None,
        production_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        from task_generator.planning.pipeline_sampler import PipelineBSubgraph

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
        reform_spec = self._load_phase15_reform_spec(phase15_reform_spec_path, subgraph.selected_motif)
        domain_profile = domain_profile or load_domain_profile("finance_audit")
        blueprint = self._build_blueprint(subgraph.selected_motif, selected_records, selected_entries, reform_spec)
        self._apply_domain_profile(blueprint, subgraph.selected_motif, domain_profile)
        self._apply_subgraph_context(blueprint, subgraph)
        if production_profile == "finance_production_v1":
            self._apply_finance_production_profile(blueprint, subgraph.selected_motif)
        elif production_profile == "finance_semantic_contract_v2":
            self._apply_finance_production_profile(blueprint, subgraph.selected_motif)
            from task_generator.planning.semantic_contract import FinanceSemanticContractAdapter

            blueprint = TaskBlueprint.model_validate(
                FinanceSemanticContractAdapter().prepare_blueprint(
                    blueprint.model_dump(), subgraph.selected_motif
                )
            )
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
            "domain_profile_id": domain_profile.profile_id,
            **({"production_profile": production_profile} if production_profile else {}),
            "requested_skill_count": subgraph.request.skill_count,
            "selected_skill_count": len(selected_records),
            "selected_skills": selected_records,
            "draft_task_blueprint": blueprint.model_dump(),
            "phase15_generator_reform": self._phase15_reform_metadata(reform_spec),
            "assembly_diagnostics": diagnostics,
            "next_pipeline_a_feedback": self._feedback_items(diagnostics),
            "notes": [
                "This prototype consumes a report-only PipelineBSubgraph and does not mutate registry files.",
                "The draft blueprint is intentionally pre-GoldenRun and pre-rw-task export.",
                "Subgraph confidence and missing signals are preserved for downstream generators.",
            ],
        }

    def _apply_finance_production_profile(self, blueprint: TaskBlueprint, motif: str) -> None:
        """Use auditable, motif-specific evidence instead of the generic prototype tables."""
        if motif == "fan_in_reconciliation":
            blueprint.template_family = "finance_cash_reconciliation_v1"
            blueprint.task_metadata.scenario_title = "Month-end cash reconciliation"
            blueprint.task_metadata.task_goal = "Reconcile bank activity to the cash ledger and explain every difference."
            blueprint.scenario_spec.business_context = (
                "The controller needs a month-end cash reconciliation before close. Match bank transactions "
                "to the cash ledger, identify timing items and errors, and calculate the adjusted balances."
            )
            blueprint.data_spec.reference_files = [
                FileSpec(file_name="bank_statement.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Bank_Activity", row_count_target=12, columns=[
                        ColumnSpec(name="Bank_ID", semantic_type="identifier"),
                        ColumnSpec(name="Transaction_Date", semantic_type="date"),
                        ColumnSpec(name="Reference", semantic_type="identifier"),
                        ColumnSpec(name="Description", semantic_type="free_text_description"),
                        ColumnSpec(name="Amount", semantic_type="amount"),
                    ])]),
                FileSpec(file_name="cash_ledger.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Cash_Ledger", row_count_target=12, columns=[
                        ColumnSpec(name="Ledger_ID", semantic_type="identifier"),
                        ColumnSpec(name="Posting_Date", semantic_type="date"),
                        ColumnSpec(name="Reference", semantic_type="identifier"),
                        ColumnSpec(name="Description", semantic_type="free_text_description"),
                        ColumnSpec(name="Amount", semantic_type="amount"),
                    ])]),
                FileSpec(file_name="policy_reference.docx", file_role="reference_table", sheet_specs=[]),
            ]
            deliverable = ("cash_reconciliation.xlsx", [
                "match bank and ledger items by reference and amount",
                "list bank-only and ledger-only items with evidence IDs",
                "calculate adjusted bank and ledger balances and explain whether they agree",
            ])
            relationships = [
                DataRelationship(relation_type="match_key", left="bank_statement.xlsx:Bank_Activity.Reference", right="cash_ledger.xlsx:Cash_Ledger.Reference"),
                DataRelationship(relation_type="cross_check", left="bank_statement.xlsx:Bank_Activity.Amount", right="cash_ledger.xlsx:Cash_Ledger.Amount"),
            ]
        elif motif == "cross_check_validation":
            blueprint.template_family = "finance_three_way_match_v1"
            blueprint.task_metadata.scenario_title = "Accounts payable three-way match review"
            blueprint.task_metadata.task_goal = "Validate supplier invoices against purchase orders and receipts."
            blueprint.scenario_spec.business_context = (
                "Accounts payable has queued invoices for payment. Perform a line-level three-way match and "
                "identify quantity, price, duplicate, and missing-receipt exceptions."
            )
            blueprint.data_spec.reference_files = [
                FileSpec(file_name="purchase_orders.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="PO_Lines", row_count_target=10, columns=[
                        ColumnSpec(name="PO_ID", semantic_type="identifier"), ColumnSpec(name="Item_ID", semantic_type="identifier"),
                        ColumnSpec(name="Ordered_Qty", semantic_type="amount_or_count"), ColumnSpec(name="Unit_Price", semantic_type="amount"),
                    ])]),
                FileSpec(file_name="goods_receipts.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Receipt_Lines", row_count_target=10, columns=[
                        ColumnSpec(name="Receipt_ID", semantic_type="identifier"), ColumnSpec(name="PO_ID", semantic_type="identifier"),
                        ColumnSpec(name="Item_ID", semantic_type="identifier"), ColumnSpec(name="Received_Qty", semantic_type="amount_or_count"),
                    ])]),
                FileSpec(file_name="supplier_invoices.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Invoice_Lines", row_count_target=11, columns=[
                        ColumnSpec(name="Invoice_ID", semantic_type="identifier"), ColumnSpec(name="PO_ID", semantic_type="identifier"),
                        ColumnSpec(name="Item_ID", semantic_type="identifier"), ColumnSpec(name="Invoiced_Qty", semantic_type="amount_or_count"),
                        ColumnSpec(name="Unit_Price", semantic_type="amount"),
                    ])]),
                FileSpec(file_name="policy_reference.docx", file_role="reference_table", sheet_specs=[]),
            ]
            deliverable = ("three_way_match_review.xlsx", [
                "join invoice lines to purchase orders and goods receipts",
                "calculate quantity and unit-price variances",
                "classify every invoice line as clear, hold, or investigate and cite source row IDs",
            ])
            relationships = [
                DataRelationship(relation_type="match_key", left="supplier_invoices.xlsx:Invoice_Lines.PO_ID", right="purchase_orders.xlsx:PO_Lines.PO_ID"),
                DataRelationship(relation_type="cross_check", left="supplier_invoices.xlsx:Invoice_Lines.Invoiced_Qty", right="goods_receipts.xlsx:Receipt_Lines.Received_Qty"),
            ]
        elif motif == "policy_application":
            blueprint.template_family = "finance_expense_policy_review_v1"
            blueprint.task_metadata.scenario_title = "Expense and corporate card policy review"
            blueprint.task_metadata.task_goal = "Apply candidate-visible policy rules to expense transactions."
            blueprint.scenario_spec.business_context = (
                "The finance operations manager needs a review of employee expense and corporate-card transactions. "
                "Apply the supplied thresholds and documentation rules and prepare an exception memo."
            )
            blueprint.data_spec.reference_files = [
                FileSpec(file_name="expense_transactions.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Transactions", row_count_target=14, columns=[
                        ColumnSpec(name="Transaction_ID", semantic_type="identifier"), ColumnSpec(name="Employee_ID", semantic_type="identifier"),
                        ColumnSpec(name="Expense_Date", semantic_type="date"), ColumnSpec(name="Category", semantic_type="status_label"),
                        ColumnSpec(name="Amount", semantic_type="amount"), ColumnSpec(name="Receipt_Available", semantic_type="status_label"),
                        ColumnSpec(name="Approval_Level", semantic_type="status_label"), ColumnSpec(name="Business_Purpose", semantic_type="free_text_description"),
                    ])]),
                FileSpec(file_name="expense_policy.docx", file_role="reference_table", sheet_specs=[]),
            ]
            deliverable = ("expense_exception_memo.docx", [
                "classify every transaction against the supplied policy clauses",
                "state the exception reason and required follow-up with transaction and clause citations",
                "summarize exception counts and amounts without inventing missing facts",
            ])
            relationships = [
                DataRelationship(relation_type="policy_lookup", left="expense_transactions.xlsx:Transactions.Category", right="expense_policy.docx:POL-001"),
            ]
        elif motif == "evidence_to_deliverable":
            blueprint.template_family = "finance_control_testing_summary_v1"
            blueprint.task_metadata.scenario_title = "Internal control testing summary"
            blueprint.task_metadata.task_goal = "Turn control-test evidence into a fact-grounded management summary."
            blueprint.scenario_spec.business_context = (
                "The audit manager needs a concise control-testing summary. Trace every conclusion to the supplied "
                "test result and evidence register, distinguish confirmed exceptions from evidence gaps, and assign "
                "the follow-up specified by the reporting rules."
            )
            blueprint.data_spec.reference_files = [
                FileSpec(file_name="control_test_results.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Control_Tests", row_count_target=10, columns=[
                        ColumnSpec(name="Test_ID", semantic_type="identifier"),
                        ColumnSpec(name="Control_ID", semantic_type="identifier"),
                        ColumnSpec(name="Evidence_ID", semantic_type="identifier"),
                        ColumnSpec(name="Procedure", semantic_type="free_text_description"),
                        ColumnSpec(name="Sample_Size", semantic_type="count"),
                        ColumnSpec(name="Exceptions_Found", semantic_type="count"),
                        ColumnSpec(name="Result", semantic_type="status_label"),
                        ColumnSpec(name="Owner", semantic_type="business_entity"),
                        ColumnSpec(name="Due_Date", semantic_type="date"),
                    ])]),
                FileSpec(file_name="audit_evidence_register.xlsx", file_role="source_data", sheet_specs=[SheetSpec(
                    sheet_name="Evidence_Register", row_count_target=9, columns=[
                        ColumnSpec(name="Evidence_ID", semantic_type="identifier"),
                        ColumnSpec(name="Source", semantic_type="source_label"),
                        ColumnSpec(name="Period", semantic_type="time_period"),
                        ColumnSpec(name="Reliability", semantic_type="status_label"),
                        ColumnSpec(name="Supports_Test_ID", semantic_type="identifier"),
                    ])]),
                FileSpec(file_name="control_reporting_rules.docx", file_role="reference_table", sheet_specs=[]),
            ]
            deliverable = ("control_testing_summary.docx", [
                "report tested, passed, failed, and unresolved-evidence counts",
                "list every confirmed exception and evidence gap with Test_ID, Control_ID, and Evidence_ID",
                "state the required follow-up and cite the applicable reporting rule for every non-pass item",
            ])
            relationships = [
                DataRelationship(relation_type="match_key", left="control_test_results.xlsx:Control_Tests.Evidence_ID", right="audit_evidence_register.xlsx:Evidence_Register.Evidence_ID"),
                DataRelationship(relation_type="policy_lookup", left="control_test_results.xlsx:Control_Tests.Result", right="control_reporting_rules.docx:E2D-001"),
            ]
        else:
            raise ValueError(f"Unsupported finance production motif: {motif}")
        blueprint.data_spec.data_relationships = relationships
        blueprint.trap_spec = []
        blueprint.deliverable_spec = [DeliverableSpec(file_name=deliverable[0], file_role="final_deliverable", requirements=deliverable[1])]
        blueprint.prompt_spec.visible_requirements = list(deliverable[1])
        blueprint.prompt_spec.hidden_requirements = []
        blueprint.prompt_spec.style_constraints = ["professional workpaper style", "use only supplied evidence", "preserve source identifiers"]
        blueprint.golden_plan = GoldenPlan(
            required_intermediate_states=["source_normalization", "record_matching", "exception_classification", "deliverable_reconciliation"],
            required_final_checks=list(deliverable[1]),
        )

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
        phase15_reform_spec: Optional[Dict[str, Any]] = None,
    ) -> TaskBlueprint:
        hints = MOTIF_BLUEPRINT_HINTS.get(motif, MOTIF_BLUEPRINT_HINTS["evidence_to_deliverable"])
        skill_names = [record.get("canonical_name", "") for record in selected_records]
        selected_skill_ids = [record.get("skill_id", "") for record in selected_records if record.get("skill_id")]
        domain_counts = Counter(domain for entry in selected_entries for domain in entry.domain_tags)
        primary_domain = domain_counts.most_common(1)[0][0] if domain_counts else "finance"
        occupation = self._infer_occupation(primary_domain, selected_entries)

        blueprint = TaskBlueprint(
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
            trap_spec=self._trap_spec(motif, selected_skill_ids),
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
        if phase15_reform_spec:
            self._apply_phase15_generator_reform(blueprint, motif, phase15_reform_spec)
        return blueprint

    def _apply_domain_profile(
        self, blueprint: TaskBlueprint, motif: str, domain_profile: DomainProfile
    ) -> None:
        if domain_profile.profile_id == "finance_audit":
            return
        hint = domain_profile.motif_hints[motif]
        schema = domain_profile.reference_schema
        blueprint.template_family = hint.template_family
        blueprint.task_metadata.sector = self._title(domain_profile.domain_scope)
        blueprint.task_metadata.occupation = domain_profile.occupation
        blueprint.task_metadata.scenario_title = f"{self._title(domain_profile.domain_scope)} {self._title(motif)}"
        blueprint.task_metadata.task_goal = hint.scenario_goal
        blueprint.scenario_spec.role = f"You are a {domain_profile.actor_role} preparing an operations review package for a supervisor."
        blueprint.scenario_spec.business_context = domain_profile.business_context
        for deliverable in blueprint.deliverable_spec:
            deliverable.file_name = hint.deliverable_name
            deliverable.requirements = list(hint.deliverable_requirements)

        file_map = {
            "source_evidence.xlsx": schema.source_file_name,
            "control_totals.xlsx": schema.control_file_name,
            "policy_reference.docx": schema.policy_file_name,
        }
        sheet_map = {
            "Evidence_Items": schema.source_sheet_name,
            "Control_Totals": schema.control_sheet_name,
        }
        for file_spec in blueprint.data_spec.reference_files:
            old_name = file_spec.file_name
            file_spec.file_name = file_map.get(old_name, old_name)
            for sheet in file_spec.sheet_specs:
                old_sheet = sheet.sheet_name
                sheet.sheet_name = sheet_map.get(old_sheet, old_sheet)
                if old_name == "source_evidence.xlsx":
                    sheet.columns = [self._domain_column(name) for name in schema.source_columns]
                elif old_name == "control_totals.xlsx":
                    sheet.columns = [self._domain_column(name) for name in schema.control_columns]

        replacements = {**file_map, **sheet_map}
        for relationship in blueprint.data_spec.data_relationships:
            for old, new in replacements.items():
                relationship.left = relationship.left.replace(old, new)
                relationship.right = relationship.right.replace(old, new)
        for trap in blueprint.trap_spec:
            target = trap.injection_target
            old_name = target.file_name
            target.file_name = file_map.get(old_name, old_name)
            target.sheet_name = sheet_map.get(target.sheet_name, target.sheet_name)
            if old_name == "source_evidence.xlsx":
                target.columns = schema.source_columns[-2:]
            elif old_name == "control_totals.xlsx":
                target.columns = schema.control_columns[-2:]
            elif old_name == "policy_reference.docx":
                target.columns = ["RULE-002", "RULE-003"]

    def _domain_column(self, name: str) -> ColumnSpec:
        lowered = name.lower()
        if lowered.endswith("_id") or lowered in {"evidence_id", "record_id"}:
            semantic = "identifier"
        elif "quantity" in lowered:
            semantic = "amount_or_count"
        elif "at" in lowered or "date" in lowered:
            semantic = "time_period"
        elif "status" in lowered or "condition" in lowered:
            semantic = "status_label"
        else:
            semantic = "free_text_description"
        return ColumnSpec(name=name, semantic_type=semantic)

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
        policy_contract = self._requires_policy_contract(motif, entries)
        if policy_contract:
            files.append(
                FileSpec(
                    file_name="policy_reference.docx",
                    file_role="reference_table",
                    sheet_specs=[],
                )
            )
        if motif == "evidence_to_deliverable":
            files.append(
                FileSpec(
                    file_name="manager_request.md",
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

    def _load_phase15_reform_spec(
        self,
        phase15_reform_spec_path: Optional[str | Path],
        motif: str,
    ) -> Optional[Dict[str, Any]]:
        if not phase15_reform_spec_path:
            return None
        spec = load_json_file(str(phase15_reform_spec_path))
        if spec.get("target_motif") != motif:
            return None
        if spec.get("reform_status") != "proposal_ready_for_controlled_experiment":
            return None
        return spec

    def _phase15_reform_metadata(self, reform_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not reform_spec:
            return {
                "enabled": False,
                "application_status": "not_requested",
                "applied_change_ids": [],
            }
        return {
            "enabled": True,
            "application_status": "applied_experiment_flag",
            "target_motif": reform_spec.get("target_motif"),
            "applied_change_ids": [
                str(change.get("change_id"))
                for change in reform_spec.get("deterministic_changes", [])
                if change.get("change_id")
            ],
            "constraints": reform_spec.get("constraints") or [],
        }

    def _apply_phase15_generator_reform(
        self,
        blueprint: TaskBlueprint,
        motif: str,
        reform_spec: Dict[str, Any],
    ) -> None:
        if motif != "evidence_to_deliverable":
            return
        phase16_mode = str(reform_spec.get("phase16_contract_mode") or "")
        if phase16_mode:
            self._apply_phase16_evidence_to_deliverable_contract(blueprint, phase16_mode)
            return
        blueprint.template_family = "evidence_package_to_reviewer_decision_memo_phase15"
        blueprint.task_metadata.scenario_title = "Reviewer decision memo from mixed evidence"
        blueprint.task_metadata.task_goal = (
            "Prepare a reviewer-facing decision memo that separates confirmed findings, unresolved support gaps, "
            "and bounded severity judgments from the visible evidence package."
        )
        blueprint.scenario_spec.role = (
            "You are a finance audit analyst preparing a manager review memo for a controller sign-off meeting."
        )
        blueprint.scenario_spec.business_context = (
            blueprint.scenario_spec.business_context
            + " A manager has asked for a sign-off-ready memo because one evidence item may affect quarter-end review priority."
        )
        blueprint.scenario_spec.time_context = (
            "Current-period review; the controller needs a concise decision memo before the next review checkpoint."
        )
        for file_spec in blueprint.data_spec.reference_files:
            if file_spec.file_name == "source_evidence.xlsx":
                for sheet in file_spec.sheet_specs:
                    if sheet.sheet_name == "Evidence_Items":
                        existing = {column.name for column in sheet.columns}
                        for column_name, semantic_type in [
                            ("Reviewer_Concern", "free_text_description"),
                            ("Severity_Indicator", "decision_category"),
                            ("Support_Status", "status_label"),
                        ]:
                            if column_name not in existing:
                                sheet.columns.append(ColumnSpec(name=column_name, semantic_type=semantic_type))
        if not any(file.file_name == "manager_followup.md" for file in blueprint.data_spec.reference_files):
            blueprint.data_spec.reference_files.append(
                FileSpec(
                    file_name="manager_followup.md",
                    file_role="reference_table",
                    sheet_specs=[],
                )
            )
        if not any(relationship.left.startswith("manager_followup.md") for relationship in blueprint.data_spec.data_relationships):
            blueprint.data_spec.data_relationships.append(
                DataRelationship(
                    relation_type="manager_followup_alignment",
                    left="manager_followup.md:decision_rules",
                    right="final_deliverable:confirmed_unresolved_priority_split",
                )
            )
        for deliverable in blueprint.deliverable_spec:
            deliverable.file_name = "reviewer_decision_memo.docx"
            deliverable.requirements = list(
                dict.fromkeys(
                    deliverable.requirements
                    + [
                        "write for a manager who must decide whether follow-up is required before sign-off",
                        "separate confirmed findings, unresolved evidence gaps, and no-issue items",
                        "assign a bounded severity of high, medium, or low using only visible evidence",
                        "include a short recommended next action for each unresolved or higher-severity item",
                    ]
                )
            )
        reform_requirements = [
            "State the business trigger and reviewer decision needed in the opening context.",
            "Use only these severity labels: `High`, `Medium`, or `Low`; define the evidence basis for each label in the memo.",
            "Create a `Confirmed findings` section, an `Unresolved support gaps` section, and a `Review priority` section before `Follow-up`.",
            "For every unresolved support gap, cite the visible evidence ID and explain what support is missing without inventing facts.",
            "Use `manager_followup.md` as reviewer context; do not treat it as hidden truth.",
        ]
        blueprint.prompt_spec.visible_requirements = list(
            dict.fromkeys(blueprint.prompt_spec.visible_requirements + reform_requirements)
        )
        blueprint.prompt_spec.hidden_requirements = list(
            dict.fromkeys(
                blueprint.prompt_spec.hidden_requirements
                + [
                    "Do not reward severity labels that are not grounded in a candidate-visible evidence item.",
                    "Do not reward memos that collapse confirmed findings and unresolved support gaps into one undifferentiated list.",
                ]
            )
        )
        blueprint.golden_plan.required_intermediate_states = list(
            dict.fromkeys(
                blueprint.golden_plan.required_intermediate_states
                + [
                    "phase15_confirmed_vs_unresolved_split",
                    "phase15_severity_classification_review",
                    "phase15_manager_followup_alignment",
                ]
            )
        )
        blueprint.golden_plan.required_final_checks = list(
            dict.fromkeys(
                blueprint.golden_plan.required_final_checks
                + [
                    "severity labels are bounded and evidence-grounded",
                    "confirmed findings and unresolved gaps are separated",
                    "manager follow-up recommendation is supported by visible evidence",
                ]
            )
        )

    def _apply_phase16_evidence_to_deliverable_contract(
        self,
        blueprint: TaskBlueprint,
        phase16_mode: str,
    ) -> None:
        productive_complexity = phase16_mode == "contract_v2_plus_productive_complexity"
        blueprint.template_family = f"evidence_to_deliverable_{phase16_mode}"
        blueprint.task_metadata.scenario_title = "Manager evidence review with explicit support mapping"
        blueprint.task_metadata.task_goal = (
            "Prepare a manager-facing evidence review that inventories candidate-visible evidence, "
            "separates confirmed and unresolved conclusions, labels support strength, and maps every "
            "material conclusion back to exact evidence IDs."
        )
        blueprint.scenario_spec.role = (
            "You are a finance audit analyst preparing an evidence review for a manager who must decide "
            "whether a finding can be closed or needs follow-up."
        )
        blueprint.scenario_spec.business_context = (
            blueprint.scenario_spec.business_context
            + " The manager needs a traceable deliverable, not an unsupported prose summary."
        )
        blueprint.scenario_spec.time_context = (
            "Current review cycle; the manager needs a concise, traceable recommendation before sign-off."
        )

        section_requirements = [
            "Create an `Evidence inventory` section listing every material Evidence_ID used in the answer.",
            "Create a `Support-strength table` with one of `confirmed`, `partial`, `conflicting`, or `missing` for each material conclusion.",
            "Create a `Conclusion map` that links each supported conclusion to exact candidate-visible Evidence_ID values.",
            "Create an `Unresolved items` section for missing, partial, or conflicting support; do not convert these into confirmed findings.",
            "Create a `Manager-facing deliverable` section with the final recommendation and caveats.",
            "Create a `Traceability appendix` that repeats the Evidence_ID support for every material conclusion.",
        ]
        complexity_requirements = [
            "When evidence is incomplete, state the missing support and the decision consequence.",
            "When evidence conflicts, preserve the conflict and explain what cannot be concluded.",
            "Do not infer values, policy conclusions, or closure status that are not supported by visible evidence.",
            "Separate productive uncertainty from format caveats: unresolved evidence is part of the task, not a formatting failure.",
        ]
        blueprint.prompt_spec.visible_requirements = list(
            dict.fromkeys(
                blueprint.prompt_spec.visible_requirements
                + section_requirements
                + (complexity_requirements if productive_complexity else [])
            )
        )
        blueprint.prompt_spec.hidden_requirements = list(
            dict.fromkeys(
                blueprint.prompt_spec.hidden_requirements
                + [
                    "Do not award credit for material conclusions without exact candidate-visible Evidence_ID support.",
                    "Do not award credit when unresolved, partial, conflicting, or missing support is presented as confirmed.",
                    "Do not require prose style beyond the candidate-visible deliverable contract.",
                ]
            )
        )
        blueprint.golden_plan.required_intermediate_states = list(
            dict.fromkeys(
                blueprint.golden_plan.required_intermediate_states
                + [
                    "phase16_evidence_inventory",
                    "phase16_support_strength_table",
                    "phase16_conclusion_map",
                    "phase16_unresolved_item_register",
                    "phase16_traceability_appendix",
                ]
                + (["phase16_conflict_and_missing_support_review"] if productive_complexity else [])
            )
        )
        blueprint.golden_plan.required_final_checks = list(
            dict.fromkeys(
                blueprint.golden_plan.required_final_checks
                + [
                    "every material conclusion cites exact Evidence_ID support",
                    "confirmed conclusions are separated from unresolved support gaps",
                    "support-strength labels use only the allowed label set",
                    "manager-facing recommendation preserves caveats from the evidence map",
                    "traceability appendix matches the conclusion map",
                ]
                + (["missing or conflicting evidence is preserved instead of resolved by invention"] if productive_complexity else [])
            )
        )
        for deliverable in blueprint.deliverable_spec:
            deliverable.file_name = "manager_evidence_review.docx"
            deliverable.requirements = list(
                dict.fromkeys(
                    deliverable.requirements
                    + [
                        "include Evidence inventory",
                        "include Support-strength table",
                        "include Conclusion map",
                        "include Unresolved items",
                        "include Manager-facing deliverable",
                        "include Traceability appendix",
                    ]
                    + (
                        [
                            "preserve missing-support and conflict caveats in the recommendation",
                            "state decision consequences for unresolved evidence",
                        ]
                        if productive_complexity
                        else []
                    )
                )
            )
        if productive_complexity and not any(file.file_name == "manager_followup.md" for file in blueprint.data_spec.reference_files):
            blueprint.data_spec.reference_files.append(
                FileSpec(
                    file_name="manager_followup.md",
                    file_role="reference_table",
                    sheet_specs=[],
                )
            )
        if not any(relationship.relation_type == "phase16_traceability_contract" for relationship in blueprint.data_spec.data_relationships):
            blueprint.data_spec.data_relationships.append(
                DataRelationship(
                    relation_type="phase16_traceability_contract",
                    left="source_evidence.xlsx:Evidence_Items.Evidence_ID",
                    right="final_deliverable:conclusion_map_and_traceability_appendix",
                )
            )

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
        if self._requires_policy_contract(motif, entries):
            relationships.append(
                DataRelationship(
                    relation_type="policy_lookup",
                    left="source_evidence.xlsx:Evidence_Items.Entity_or_Item",
                    right="policy_reference.docx:applicable_requirements",
                )
            )
        if motif == "evidence_to_deliverable":
            relationships.append(
                DataRelationship(
                    relation_type="review_instruction_alignment",
                    left="manager_request.md:decision_rules",
                    right="final_deliverable:deliverable_outline",
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
        policy_contract = self._requires_policy_contract(motif, entries)
        requirements = [
            "Review the provided reference files and produce the requested deliverable.",
            f"Write the final deliverable as `{deliverable_name}` and keep the content manager-ready.",
            "Cite the exact candidate-visible evidence IDs from the `Evidence_ID` column, such as `EVID-001`; do not use source labels such as `Manager Email` or `Ledger Snapshot` as substitutes for evidence IDs.",
            "Flag items that cannot be resolved from the provided evidence.",
            "Separate supported conclusions, confirmed exceptions, and unresolved items instead of blending them together.",
            "Place the `Evidence inventory` section immediately after the title or opening context and before any supported conclusion, confirmed exception, unresolved item, recommendation, or follow-up.",
            "Format `Evidence inventory` as a table or bullet list with these four explicit fields for every material item: `Evidence_ID`, `Source file`, `Observed item/value`, and `Intended use`.",
            "Do not use placeholder headings for required sections; populate each required section with its complete content where that section appears.",
            "Include an `Evidence-to-conclusion map` that links each material conclusion to the specific evidence IDs used.",
            "In `Supported conclusions`, `Confirmed exceptions`, and `Unresolved items`, end every material bullet with bracketed local support using exact workbook evidence IDs, such as `[Evidence: EVID-001]`.",
            "Do not place evidence citations only in a separate appendix; each conclusion must carry its own local evidence or policy locator.",
        ]
        if policy_contract:
            requirements.insert(
                5,
                "Use this exact top-level section order before any appendix: `Evidence inventory`, `Deliverable outline`, `Evidence reviewed`, `Supported conclusions`, `Confirmed exceptions`, `Unresolved items`, `Policy clause mapping`, `Follow-up`.",
            )
            requirements.insert(
                8,
                "Include a `Deliverable outline` section after `Evidence inventory` and before drafting conclusions; use headings for evidence reviewed, supported conclusions, confirmed exceptions, unresolved items, policy mapping, and follow-up.",
            )
            requirements.insert(
                10,
                "Do not append the detailed Evidence inventory, Evidence-to-conclusion map, or Policy clause mapping after `Follow-up`; write those details inside their named sections.",
            )
            requirements[12] = "In `Supported conclusions`, `Confirmed exceptions`, and `Unresolved items`, end every material bullet with bracketed local support using exact workbook evidence IDs, such as `[Evidence: EVID-001]` or `[Evidence: EVID-001; Policy: POL-003]`."
        else:
            requirements.insert(
                5,
                "Use this exact top-level section order before any appendix: `Evidence inventory`, `Deliverable outline`, `Evidence reviewed`, `Supported conclusions`, `Confirmed exceptions`, `Unresolved items`, `Follow-up`.",
            )
            requirements.insert(
                8,
                "Include a `Deliverable outline` section after `Evidence inventory` and before drafting conclusions; use headings for evidence reviewed, supported conclusions, confirmed exceptions, unresolved items, and follow-up.",
            )
            requirements.insert(
                10,
                "Do not append the detailed Evidence inventory or Evidence-to-conclusion map after `Follow-up`; write those details inside their named sections.",
            )
        if motif == "fan_in_reconciliation":
            requirements.append("Reconcile source evidence to the control totals and explain material differences.")
        elif motif == "cross_check_validation":
            requirements.append("Use at least two independent evidence paths before marking a conclusion as validated.")
        elif motif == "policy_application":
            requirements.append("Apply the stated policy requirements to each relevant evidence item.")
        elif motif == "evidence_to_deliverable":
            requirements.append("Synthesize the evidence into a manager-ready deliverable rather than a raw notes list.")
        if policy_contract:
            requirements.append(
                "For each policy-sensitive conclusion, cite both the exact supporting workbook evidence ID and the applicable policy clause ID."
            )
            requirements.append(
                "Include a `Policy clause mapping` section with columns or bullets for clause ID, governed evidence ID, applied conclusion, and any unresolved policy uncertainty."
            )
            requirements.append(
                "For every policy-sensitive bullet in the final deliverable, include both local evidence support and local policy support in the same bullet; a source label alone is not acceptable evidence support."
            )
        if skill_names:
            requirements.append("The task should exercise: " + "; ".join(skill_names[:4]) + ".")
        return requirements

    def _hidden_requirements(self, motif: str, entries: List[SkillRegistryEntry]) -> List[str]:
        policy_contract = self._requires_policy_contract(motif, entries)
        hidden = [
            "Do not reward unsupported conclusions that lack visible evidence citations.",
            "Do not reward conclusion bullets whose evidence support appears only elsewhere in the deliverable.",
            "Do not reward source-label-only citations when a candidate-visible `Evidence_ID` value is available.",
            "Do not reward deliverables that place the Evidence inventory after final conclusions.",
            "Do not reward deliverables whose Evidence inventory lacks the required fields: Evidence_ID, Source file, Observed item/value, and Intended use.",
            "Do not reward deliverables that place Follow-up before the detailed Evidence inventory.",
            "Do not reward placeholder-only required sections whose actual details are appended later.",
            "Treat unresolved evidence gaps separately from confirmed exceptions.",
            "The expected deliverable should be supportable from candidate-visible reference files, not hidden teacher assumptions.",
        ]
        if policy_contract:
            hidden.append("Do not reward Evidence-to-conclusion or Policy clause mapping details that are moved after Follow-up instead of appearing in their named sections.")
        else:
            hidden.append("Do not reward Evidence-to-conclusion mapping details that are moved after Follow-up instead of appearing in their named section.")
        if motif in {"cross_check_validation", "fan_in_reconciliation"}:
            hidden.append("The teacher run should expose intermediate cross-check or reconciliation states.")
        if policy_contract:
            hidden.append("Exact grading anchors must be traceable to visible policy or requirement evidence.")
            hidden.append("Policy-grounded claims should cite explicit clause IDs together with the evidence they govern.")
        return hidden

    def _trap_spec(self, motif: str, selected_skill_ids: List[str]) -> List[TrapSpec]:
        source_skill_id = selected_skill_ids[0] if selected_skill_ids else "skill_unknown"
        traps = [
            TrapSpec(
                trap_id=f"trap_{motif}_ambiguity",
                source_skill_id=source_skill_id,
                trap_type="ambiguous_support",
                injection_target=InjectionTarget(
                    file_name="source_evidence.xlsx",
                    sheet_name="Evidence_Items",
                    columns=["Observed_Value", "Source"],
                ),
                injection_policy=InjectionPolicy(
                    pattern="conflicting_supporting_signal",
                    severity="medium",
                    affected_row_count=2,
                    affected_entities=["material_line_item", "exception_candidate"],
                ),
                expected_solver_behavior="Identify the ambiguous or conflicting evidence, avoid false certainty, and keep unresolved items separate from supported conclusions.",
            )
        ]
        if motif in {"cross_check_validation", "fan_in_reconciliation"}:
            traps.append(
                TrapSpec(
                    trap_id=f"trap_{motif}_cross_file_mismatch",
                    source_skill_id=source_skill_id,
                    trap_type="cross_file_mismatch",
                    injection_target=InjectionTarget(
                        file_name="control_totals.xlsx",
                        sheet_name="Control_Totals",
                        columns=["Expected_Total", "Basis"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="basis_mismatch_requires_follow_up",
                        severity="medium",
                        affected_row_count=1,
                        affected_entities=["control_total"],
                    ),
                    expected_solver_behavior="Surface the mismatch explicitly and explain whether it reflects a true exception, a basis difference, or missing support.",
                )
            )
        if motif == "policy_application":
            traps.append(
                TrapSpec(
                    trap_id="trap_policy_application_clause_overlap",
                    source_skill_id=source_skill_id,
                    trap_type="policy_clause_overlap",
                    injection_target=InjectionTarget(
                        file_name="policy_reference.docx",
                        sheet_name="",
                        columns=["POL-002", "POL-003"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="partially_overlapping_policy_clauses",
                        severity="medium",
                        affected_entities=["policy_clause_pair"],
                    ),
                    expected_solver_behavior="Resolve which clause governs the case, or mark the policy interpretation as uncertain instead of flattening the ambiguity.",
                )
            )
        if motif == "evidence_to_deliverable":
            traps.append(
                TrapSpec(
                    trap_id="trap_evidence_to_deliverable_manager_request_gap",
                    source_skill_id=source_skill_id,
                    trap_type="instruction_vs_evidence_gap",
                    injection_target=InjectionTarget(
                        file_name="manager_request.md",
                        sheet_name="",
                        columns=["Requested output", "Known evidence gaps"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="manager_request_demands_missing_support",
                        severity="medium",
                        affected_entities=["follow_up_request"],
                    ),
                    expected_solver_behavior="Acknowledge where the manager request cannot be fully satisfied from current evidence and convert the gap into explicit follow-up rather than inventing support.",
                )
            )
        return traps

    def _intermediate_states(self, motif: str, entries: List[SkillRegistryEntry]) -> List[str]:
        states = ["evidence_inventory", "deliverable_outline", "evidence_to_conclusion_map"]
        if motif in {"fan_in_reconciliation", "cross_check_validation"}:
            states.append("cross_check_matrix")
        if motif == "fan_in_reconciliation":
            states.append("reconciliation_difference_log")
        if self._requires_policy_contract(motif, entries):
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
        if self._requires_policy_contract(motif, entries):
            checks.insert(3, "policy_clause_traceability")
        return checks

    def _requires_policy_contract(self, motif: str, entries: List[SkillRegistryEntry]) -> bool:
        if motif in {"policy_application", "cross_check_validation"}:
            return True
        return self._mentions(
            entries,
            ["policy", "tax", "withholding", "jurisdiction", "regulation", "clause"],
        )

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
