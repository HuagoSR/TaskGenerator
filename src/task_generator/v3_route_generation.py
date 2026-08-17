from __future__ import annotations

from typing import Dict, List

from task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    DeliverableIntentV1,
    EvidenceArtifactSpecV1,
    EvidenceFieldComparisonV1,
    EvidenceFieldSpecV1,
    EvidenceNodeProposalV1,
    EvidenceRelationProposalV1,
    EvidenceScenarioRecordV1,
    RequiredJudgmentProposalV1,
    SkillBindingProposalV1,
    TaskDesignProposalV1,
)


class StrictTemplateProposalCompiler:
    """Compile a deterministic route from the same frozen CapabilityBrief.

    The compiler deliberately uses a fixed scenario/topology/deliverable
    grammar. It exists as the strict-template control for R6; it does not call
    a provider and it receives no authority over truth or promotion.
    """

    def compile(self, brief: CapabilityBriefV1) -> TaskDesignProposalV1:
        node_count = max(
            2,
            len(brief.workflow_context.resource_node_ids),
        )
        relation_count = max(
            1,
            len(brief.workflow_context.edge_ids),
        )
        source_ids = [item.source_ref_id for item in brief.source_refs]
        nodes = [
            EvidenceNodeProposalV1(
                node_id=f"template_evidence_{index:02d}",
                artifact_role=self._artifact_role(brief.motif, index),
                source_ref_ids=list(source_ids),
                intended_contents=self._intended_contents(brief.motif),
                artifact_spec=self._artifact_spec(
                    brief.motif,
                    index,
                    source_ids,
                ),
            )
            for index in range(1, node_count + 1)
        ]
        relations: List[EvidenceRelationProposalV1] = []
        for index in range(1, relation_count + 1):
            from_index = ((index - 1) % node_count) + 1
            to_index = (index % node_count) + 1
            relations.append(
                EvidenceRelationProposalV1(
                    relation_id=f"template_relation_{index:02d}",
                    from_node_id=f"template_evidence_{from_index:02d}",
                    to_node_id=f"template_evidence_{to_index:02d}",
                    relation_type="template-governed cross-document check",
                    solver_must_infer=True,
                    from_join_field=self._join_field(brief.motif),
                    to_join_field=self._join_field(brief.motif),
                    comparison_fields=[
                        EvidenceFieldComparisonV1(
                            from_field=self._comparison_field(brief.motif),
                            to_field=self._comparison_field(brief.motif),
                            operator="equal",
                        )
                    ],
                )
            )
        judgments = [
            RequiredJudgmentProposalV1(
                judgment_id=f"template_judgment_{index:02d}",
                description=(
                    f"Apply {capability.capability_name} to the candidate-visible "
                    "evidence and document the supported conclusion."
                ),
                input_node_ids=[item.node_id for item in nodes],
                observable_output=capability.observable_behavior,
                capability_ids=[capability.capability_id],
            )
            for index, capability in enumerate(
                brief.required_capabilities,
                start=1,
            )
        ]
        judgment_by_capability = {
            judgment.capability_ids[0]: judgment.judgment_id
            for judgment in judgments
        }
        bindings = []
        for skill in brief.selected_skills:
            bound = [
                judgment_by_capability[capability_id]
                for capability_id in skill.required_capability_ids
                if capability_id in judgment_by_capability
            ]
            bindings.append(
                SkillBindingProposalV1(
                    skill_id=skill.skill_id,
                    binding_types=["required_judgment"],
                    bound_element_ids=bound,
                    observable_behavior=(
                        f"The candidate visibly applies {skill.canonical_name} "
                        "within the frozen template workflow."
                    ),
                )
            )
        allowed_formats = [
            value.lower().lstrip(".")
            for value in brief.allowed_output_file_types
        ]
        return TaskDesignProposalV1(
            proposal_version="v3.task_design_proposal.2",
            proposal_id=f"strict_template_{brief.brief_id}",
            brief_id=brief.brief_id,
            proposal_origin="program",
            source_ref_ids=source_ids,
            scenario=(
                f"{brief.business_role} responds to the frozen trigger and "
                f"completes a template-governed {brief.motif} task for review."
            ),
            actor_role=brief.business_role,
            trigger_event=brief.trigger_event,
            evidence_nodes=nodes,
            evidence_relations=relations,
            required_judgments=judgments,
            skill_bindings=bindings,
            deliverable_intent=DeliverableIntentV1(
                artifact_kind="structured review workpaper",
                intended_audience="business reviewer",
                business_use=brief.business_goal,
                required_sections_or_views=[
                    "Summary",
                    "Evidence Review",
                    "Judgments",
                    "Exceptions",
                ],
                allowed_formats=allowed_formats,
            ),
            productive_complexity=list(brief.productive_complexity_floor),
            accidental_difficulty_to_avoid=list(brief.forbidden_shortcuts),
            deterministic_fact_constraints=[
                "All task facts and expected values must be materialized and "
                "recomputed from candidate-visible evidence by deterministic code."
            ],
            assumptions_not_allowed=[
                "Do not assume facts, policies, thresholds, mappings, or paths "
                "that are absent from the frozen CapabilityBrief and materialized files."
            ],
            unresolved_design_questions=[],
        )

    @classmethod
    def _artifact_spec(
        cls,
        motif: str,
        node_index: int,
        source_ids: List[str],
    ) -> EvidenceArtifactSpecV1:
        fields = cls._fields_for_motif(motif)
        records = [
            EvidenceScenarioRecordV1(
                record_id=f"STRICT-{node_index:02d}-{record_index:03d}",
                values=cls._record_values(
                    motif,
                    node_index,
                    record_index,
                ),
            )
            for record_index in range(1, 5)
        ]
        return EvidenceArtifactSpecV1(
            fact_origin="governed_scenario_fact",
            record_type=cls._record_type(motif),
            primary_key_field="record_id",
            fields=fields,
            records=records,
            methodological_source_ref_ids=list(source_ids),
        )

    @staticmethod
    def _base_fields(join_field: str, join_display: str) -> List[EvidenceFieldSpecV1]:
        return [
            EvidenceFieldSpecV1(
                field_name="record_id",
                display_name="Record ID",
                data_type="identifier",
                description="Stable identifier for this candidate-visible evidence record.",
            ),
            EvidenceFieldSpecV1(
                field_name=join_field,
                display_name=join_display,
                data_type="identifier",
                description="Stable business key used for cross-file analysis.",
            ),
        ]

    @classmethod
    def _fields_for_motif(cls, motif: str) -> List[EvidenceFieldSpecV1]:
        if motif == "fan_in_reconciliation":
            return cls._base_fields("transaction_id", "Transaction ID") + [
                EvidenceFieldSpecV1(
                    field_name="source_document",
                    display_name="Source Document",
                    data_type="text",
                    description="Document or system extract supplying the transaction evidence.",
                ),
                EvidenceFieldSpecV1(
                    field_name="ledger_account",
                    display_name="Ledger Account",
                    data_type="identifier",
                    description="Ledger account associated with the transaction.",
                ),
                EvidenceFieldSpecV1(
                    field_name="source_amount",
                    display_name="Source Amount",
                    data_type="currency",
                    description="Candidate-visible monetary amount reported by this evidence source.",
                    unit="USD",
                ),
                EvidenceFieldSpecV1(
                    field_name="posting_date",
                    display_name="Posting Date",
                    data_type="date",
                    description="Business date on which the transaction was posted.",
                ),
                EvidenceFieldSpecV1(
                    field_name="reconciliation_status",
                    display_name="Reconciliation Status",
                    data_type="enum",
                    description="Observed matching state before candidate-authored conclusions.",
                ),
            ]
        if motif == "policy_application":
            return cls._base_fields("control_id", "Control ID") + [
                EvidenceFieldSpecV1(
                    field_name="policy_requirement",
                    display_name="Policy Requirement",
                    data_type="text",
                    description="Requirement that must be applied to the control evidence.",
                ),
                EvidenceFieldSpecV1(
                    field_name="threshold_value",
                    display_name="Required Threshold",
                    data_type="percentage",
                    description="Governed policy threshold used for the compliance assessment.",
                    unit="percent",
                ),
                EvidenceFieldSpecV1(
                    field_name="observed_value",
                    display_name="Observed Value",
                    data_type="percentage",
                    description="Candidate-visible observed performance for the control.",
                    unit="percent",
                ),
                EvidenceFieldSpecV1(
                    field_name="control_owner",
                    display_name="Control Owner",
                    data_type="text",
                    description="Documented owner responsible for operating the control.",
                ),
                EvidenceFieldSpecV1(
                    field_name="exception_allowed",
                    display_name="Exception Permitted",
                    data_type="enum",
                    description="Whether the policy explicitly permits a documented exception.",
                ),
                EvidenceFieldSpecV1(
                    field_name="compliance_status",
                    display_name="Compliance Status",
                    data_type="enum",
                    description="Observed rule-application state before final candidate judgment.",
                ),
            ]
        if motif == "evidence_to_deliverable":
            return cls._base_fields("finding_id", "Finding ID") + [
                EvidenceFieldSpecV1(
                    field_name="evidence_summary",
                    display_name="Evidence Summary",
                    data_type="text",
                    description="Concise candidate-visible summary of the underlying evidence.",
                ),
                EvidenceFieldSpecV1(
                    field_name="risk_rating",
                    display_name="Risk Rating",
                    data_type="enum",
                    description="Governed preliminary risk classification supported by the evidence.",
                ),
                EvidenceFieldSpecV1(
                    field_name="quantified_exposure",
                    display_name="Quantified Exposure",
                    data_type="currency",
                    description="Candidate-visible monetary exposure associated with the finding.",
                    unit="USD",
                ),
                EvidenceFieldSpecV1(
                    field_name="recommended_action",
                    display_name="Recommended Action Input",
                    data_type="text",
                    description="Management-provided action input, not a candidate-authored conclusion.",
                ),
                EvidenceFieldSpecV1(
                    field_name="action_owner",
                    display_name="Action Owner",
                    data_type="text",
                    description="Documented owner for the proposed management action.",
                ),
                EvidenceFieldSpecV1(
                    field_name="target_date",
                    display_name="Target Date",
                    data_type="date",
                    description="Documented target date for management action.",
                ),
                EvidenceFieldSpecV1(
                    field_name="disposition_status",
                    display_name="Disposition Status",
                    data_type="enum",
                    description="Observed disposition state available for deliverable preparation.",
                ),
            ]
        return cls._base_fields("control_id", "Control ID") + [
            EvidenceFieldSpecV1(
                field_name="assertion_tested",
                display_name="Assertion Tested",
                data_type="text",
                description="Business assertion independently tested by this evidence path.",
            ),
            EvidenceFieldSpecV1(
                field_name="evidence_type",
                display_name="Evidence Type",
                data_type="text",
                description="Type of independent evidence used for the cross-check.",
            ),
            EvidenceFieldSpecV1(
                field_name="observed_result",
                display_name="Observed Result",
                data_type="enum",
                description="Observed result from the independent evidence path.",
            ),
            EvidenceFieldSpecV1(
                field_name="evidence_date",
                display_name="Evidence Date",
                data_type="date",
                description="Date on which the supporting evidence was recorded.",
            ),
            EvidenceFieldSpecV1(
                field_name="evidence_owner",
                display_name="Evidence Owner",
                data_type="text",
                description="Documented owner of the independent evidence path.",
            ),
            EvidenceFieldSpecV1(
                field_name="validation_status",
                display_name="Validation Status",
                data_type="enum",
                description="Cross-check state before the candidate documents a conclusion.",
            ),
        ]

    @staticmethod
    def _record_values(motif: str, node_index: int, record_index: int) -> Dict[str, object]:
        record_id = f"STRICT-{node_index:02d}-{record_index:03d}"
        if motif == "fan_in_reconciliation":
            amount = 1000.0 + record_index * 275.0
            status = "Matched"
            if record_index == 3:
                status = "Missing source" if node_index % 2 else "Amount variance"
                if node_index % 2 == 0:
                    amount += 125.0
            return {
                "record_id": record_id,
                "transaction_id": f"TXN-{record_index:04d}",
                "source_document": f"Source {node_index:02d} document {record_index}",
                "ledger_account": f"41{record_index:02d}",
                "source_amount": amount,
                "posting_date": f"2026-03-{10 + record_index:02d}",
                "reconciliation_status": status,
            }
        if motif == "policy_application":
            observed = 0.98 - record_index / 100.0
            status = "Compliant"
            exception_allowed = "No"
            if record_index == 3:
                observed = 0.82 if node_index % 2 else 0.88
                status = "Exception required" if node_index % 2 else "Non-compliant"
                exception_allowed = "Yes" if node_index % 2 else "No"
            return {
                "record_id": record_id,
                "control_id": f"CTRL-{record_index:03d}",
                "policy_requirement": f"Control evidence coverage requirement {record_index}",
                "threshold_value": 0.95,
                "observed_value": observed,
                "control_owner": f"Control Owner {record_index}",
                "exception_allowed": exception_allowed,
                "compliance_status": status,
            }
        if motif == "evidence_to_deliverable":
            risk = ["low", "medium", "high", "medium"][record_index - 1]
            disposition = "Ready for review"
            if record_index == 3:
                risk = "critical" if node_index % 2 else "high"
                disposition = "Evidence gap" if node_index % 2 else "Management response pending"
            return {
                "record_id": record_id,
                "finding_id": f"FIND-{record_index:03d}",
                "evidence_summary": f"Evidence summary {record_index} from source path {node_index}",
                "risk_rating": risk,
                "quantified_exposure": 2500.0 * record_index,
                "recommended_action": f"Management action input {record_index}",
                "action_owner": f"Action Owner {record_index}",
                "target_date": f"2026-0{6 + record_index}-15",
                "disposition_status": disposition,
            }
        observed = "Matches independent path"
        status = "Validated"
        if record_index == 3:
            observed = "Missing support" if node_index % 2 else "Variance detected"
            status = "Follow-up required"
        return {
            "record_id": record_id,
            "control_id": f"CTRL-{record_index:03d}",
            "assertion_tested": f"Control assertion {record_index}",
            "evidence_type": f"Independent evidence path {node_index}",
            "observed_result": observed,
            "evidence_date": f"2026-03-{10 + record_index:02d}",
            "evidence_owner": f"Evidence Owner {record_index}",
            "validation_status": status,
        }

    @staticmethod
    def _comparison_field(motif: str) -> str:
        return {
            "fan_in_reconciliation": "source_amount",
            "policy_application": "compliance_status",
            "evidence_to_deliverable": "risk_rating",
            "cross_check_validation": "observed_result",
        }.get(motif, "observed_result")

    @staticmethod
    def _join_field(motif: str) -> str:
        return {
            "fan_in_reconciliation": "transaction_id",
            "policy_application": "control_id",
            "evidence_to_deliverable": "finding_id",
            "cross_check_validation": "control_id",
        }.get(motif, "control_id")

    @staticmethod
    def _record_type(motif: str) -> str:
        return {
            "fan_in_reconciliation": "reconciliation source transaction",
            "policy_application": "policy control assessment evidence",
            "evidence_to_deliverable": "manager-review finding evidence",
            "cross_check_validation": "independent validation evidence",
        }.get(motif, "independent validation evidence")

    @staticmethod
    def _artifact_role(motif: str, node_index: int) -> str:
        primary = node_index == 1
        return {
            "fan_in_reconciliation": "primary reconciliation source amount" if primary else "independent reconciliation source amount",
            "policy_application": "primary policy requirement control evidence" if primary else "independent control compliance evidence",
            "evidence_to_deliverable": "primary finding risk evidence" if primary else "supporting finding disposition evidence",
            "cross_check_validation": "primary assertion validation evidence" if primary else "independent observed validation evidence",
        }.get(motif, "primary observed validation evidence" if primary else "independent observed validation evidence")

    @staticmethod
    def _intended_contents(motif: str) -> str:
        return {
            "fan_in_reconciliation": "Candidate-visible transaction identifiers, source documents, ledger accounts, monetary amounts, posting dates and reconciliation states.",
            "policy_application": "Candidate-visible control identifiers, policy requirements, thresholds, observed performance, control ownership, exception permissions and compliance states.",
            "evidence_to_deliverable": "Candidate-visible findings, evidence summaries, preliminary risk ratings, quantified exposure, management action inputs, owners, dates and disposition states.",
            "cross_check_validation": "Candidate-visible control assertions, independent evidence types, observed results, evidence dates, owners and validation states.",
        }.get(motif, "Candidate-visible assertions, independent observed evidence and validation states.")
