from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field


GraphShape = Literal["chain", "fan_in", "fan_out", "dag", "constraint_graph"]
RoleKind = Literal["source", "skill", "validator", "deliverable", "exception_handler", "support"]
ConstraintSeverity = Literal["low", "medium", "high"]
MotifType = Literal[
    "policy_application",
    "fan_in_reconciliation",
    "evidence_to_deliverable",
    "cross_check_validation",
]


class MotifRoleDefinition(BaseModel):
    role_name: str
    role_kind: RoleKind
    description: str
    required_resource_types: List[str] = Field(default_factory=list)
    provided_resource_types: List[str] = Field(default_factory=list)
    typical_graph_roles: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MotifExecutionStage(BaseModel):
    stage_id: str
    stage_name: str
    required_roles: List[str] = Field(default_factory=list)
    expected_outputs: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MotifValidationConstraint(BaseModel):
    constraint_id: str
    description: str
    severity: ConstraintSeverity = "medium"
    reason_codes: List[str] = Field(default_factory=list)


class MotifGraphGrammarRecord(BaseModel):
    motif_grammar_id: str
    motif_type: MotifType
    required_roles: List[MotifRoleDefinition] = Field(default_factory=list)
    optional_roles: List[MotifRoleDefinition] = Field(default_factory=list)
    required_resource_types: List[str] = Field(default_factory=list)
    provided_resource_types: List[str] = Field(default_factory=list)
    expected_graph_shape: GraphShape
    execution_stage_template: List[MotifExecutionStage] = Field(default_factory=list)
    validation_constraints: List[MotifValidationConstraint] = Field(default_factory=list)
    common_failure_modes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MotifGraphGrammarDiagnostics(BaseModel):
    grammar_count: int = 0
    motif_types: List[str] = Field(default_factory=list)
    warning_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MotifGraphGrammarArtifact(BaseModel):
    motif_graph_grammar_version: str = "v3.motif_graph_grammar.1"
    grammars: List[MotifGraphGrammarRecord] = Field(default_factory=list)
    diagnostics: MotifGraphGrammarDiagnostics = Field(default_factory=MotifGraphGrammarDiagnostics)
    notes: List[str] = Field(default_factory=list)


class MotifGraphGrammarBuilder:
    """Build deterministic experimental motif graph grammars."""

    def build(self) -> MotifGraphGrammarArtifact:
        grammars = [
            self._policy_application_grammar(),
            self._fan_in_reconciliation_grammar(),
            self._evidence_to_deliverable_grammar(),
            self._cross_check_validation_grammar(),
        ]
        return MotifGraphGrammarArtifact(
            grammars=grammars,
            diagnostics=MotifGraphGrammarDiagnostics(
                grammar_count=len(grammars),
                motif_types=[grammar.motif_type for grammar in grammars],
                warning_codes=[],
                notes=[
                    "V1 grammar is deterministic and hand-written; it is a stable contract draft rather than a learned ontology.",
                    "These records are intended to support later sampler role coverage and role-filling work without changing current selection behavior.",
                ],
            ),
            notes=[
                "This artifact is experimental and report-first.",
                "Motif graph grammars describe role/resource/stage expectations and should not be treated as fixed task templates.",
            ],
        )

    def write_output(self, artifact: MotifGraphGrammarArtifact, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def _policy_application_grammar(self) -> MotifGraphGrammarRecord:
        motif_type = "policy_application"
        return MotifGraphGrammarRecord(
            motif_grammar_id=self._stable_id(motif_type),
            motif_type=motif_type,
            required_roles=[
                MotifRoleDefinition(
                    role_name="policy_source",
                    role_kind="source",
                    description="Expose the governing policy text, clause structure, or rule reference.",
                    required_resource_types=["PolicyRule"],
                    provided_resource_types=["PolicyRule"],
                    typical_graph_roles=["starter"],
                    notes=["Usually maps to policy docs, compliance references, or rule catalogs."],
                ),
                MotifRoleDefinition(
                    role_name="rule_extraction_skill",
                    role_kind="skill",
                    description="Extract the applicable rule from a broader policy source.",
                    required_resource_types=["PolicyRule"],
                    provided_resource_types=["PolicyRule"],
                    typical_graph_roles=["transform"],
                ),
                MotifRoleDefinition(
                    role_name="case_evidence_source",
                    role_kind="source",
                    description="Provide the case facts or candidate-visible evidence to which the rule applies.",
                    required_resource_types=["CaseEvidence"],
                    provided_resource_types=["CaseEvidence"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="rule_application_skill",
                    role_kind="skill",
                    description="Apply the extracted rule to the available case evidence.",
                    required_resource_types=["PolicyRule", "CaseEvidence"],
                    provided_resource_types=["AppliedPolicyAssessment"],
                    typical_graph_roles=["transform", "fan_in"],
                ),
                MotifRoleDefinition(
                    role_name="uncertainty_or_exception_handler",
                    role_kind="exception_handler",
                    description="Handle ambiguity, missing evidence, or exception classification before final output.",
                    required_resource_types=["AppliedPolicyAssessment"],
                    provided_resource_types=["ExceptionClassification"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="final_deliverable_skill",
                    role_kind="deliverable",
                    description="Synthesize a manager-ready finding, memo, or conclusion from the applied rule and exception status.",
                    required_resource_types=["AppliedPolicyAssessment", "ExceptionClassification"],
                    provided_resource_types=["ManagerReadyFinding"],
                    typical_graph_roles=["synthesis"],
                ),
            ],
            optional_roles=[
                MotifRoleDefinition(
                    role_name="conflicting_policy_detector",
                    role_kind="support",
                    description="Identify when multiple policy clauses or guidance sources conflict.",
                    required_resource_types=["PolicyRule"],
                    provided_resource_types=["PolicyRule"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="missing_evidence_detector",
                    role_kind="support",
                    description="Flag gaps between the policy test and the available supporting evidence.",
                    required_resource_types=["CaseEvidence"],
                    provided_resource_types=["ExceptionClassification"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="cross_check_validator",
                    role_kind="validator",
                    description="Cross-check the applied conclusion against supporting evidence and cited clauses.",
                    required_resource_types=["AppliedPolicyAssessment"],
                    provided_resource_types=["AppliedPolicyAssessment"],
                    typical_graph_roles=["validator"],
                ),
            ],
            required_resource_types=["PolicyRule", "CaseEvidence"],
            provided_resource_types=["AppliedPolicyAssessment", "ExceptionClassification", "ManagerReadyFinding"],
            expected_graph_shape="constraint_graph",
            execution_stage_template=[
                MotifExecutionStage(
                    stage_id="stage_extract_rule",
                    stage_name="extract applicable rule",
                    required_roles=["policy_source", "rule_extraction_skill"],
                    expected_outputs=["PolicyRule"],
                ),
                MotifExecutionStage(
                    stage_id="stage_collect_evidence",
                    stage_name="collect case evidence",
                    required_roles=["case_evidence_source"],
                    expected_outputs=["CaseEvidence"],
                ),
                MotifExecutionStage(
                    stage_id="stage_apply_rule",
                    stage_name="apply rule to evidence",
                    required_roles=["rule_application_skill"],
                    expected_outputs=["AppliedPolicyAssessment"],
                ),
                MotifExecutionStage(
                    stage_id="stage_resolve_uncertainty",
                    stage_name="resolve uncertainty or exception",
                    required_roles=["uncertainty_or_exception_handler"],
                    expected_outputs=["ExceptionClassification"],
                ),
                MotifExecutionStage(
                    stage_id="stage_synthesize_deliverable",
                    stage_name="synthesize final deliverable",
                    required_roles=["final_deliverable_skill"],
                    expected_outputs=["ManagerReadyFinding"],
                ),
            ],
            validation_constraints=[
                MotifValidationConstraint(
                    constraint_id="must_cite_policy_clause",
                    description="The final output must cite the specific policy clause or rule used for the conclusion.",
                    severity="high",
                    reason_codes=["missing_policy_locator"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_cite_supporting_evidence",
                    description="The final output must tie the conclusion to candidate-visible supporting evidence.",
                    severity="high",
                    reason_codes=["missing_evidence_locator"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_separate_confirmed_from_unresolved",
                    description="Confirmed findings must be separated from unresolved issues or evidence gaps.",
                    severity="medium",
                    reason_codes=["flattened_uncertainty"],
                ),
            ],
            common_failure_modes=[
                "policy quoted without application",
                "evidence cited without clause mapping",
                "exception path omitted",
                "unresolved ambiguity flattened into false certainty",
            ],
            notes=[
                "Designed to support policy-heavy review tasks without hard-coding one fixed deliverable surface.",
            ],
        )

    def _fan_in_reconciliation_grammar(self) -> MotifGraphGrammarRecord:
        motif_type = "fan_in_reconciliation"
        return MotifGraphGrammarRecord(
            motif_grammar_id=self._stable_id(motif_type),
            motif_type=motif_type,
            required_roles=[
                MotifRoleDefinition(
                    role_name="source_a_extractor",
                    role_kind="source",
                    description="Extract the first source dataset, schedule, or evidence stream.",
                    required_resource_types=["SourceRecord"],
                    provided_resource_types=["SourceRecord"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="source_b_extractor",
                    role_kind="source",
                    description="Extract the second source dataset, schedule, or evidence stream.",
                    required_resource_types=["SourceRecord"],
                    provided_resource_types=["SourceRecord"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="normalizer",
                    role_kind="skill",
                    description="Normalize records into a comparable basis before differences are calculated.",
                    required_resource_types=["SourceRecord"],
                    provided_resource_types=["NormalizedRecord"],
                    typical_graph_roles=["transform"],
                ),
                MotifRoleDefinition(
                    role_name="difference_calculator",
                    role_kind="skill",
                    description="Compute the reconciled differences between aligned sources.",
                    required_resource_types=["NormalizedRecord", "ReconciliationBasis"],
                    provided_resource_types=["DifferenceSet"],
                    typical_graph_roles=["fan_in", "transform"],
                ),
                MotifRoleDefinition(
                    role_name="exception_explainer",
                    role_kind="exception_handler",
                    description="Explain why differences remain and classify unresolved exceptions.",
                    required_resource_types=["DifferenceSet"],
                    provided_resource_types=["ExceptionExplanation"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="deliverable_synthesizer",
                    role_kind="deliverable",
                    description="Turn reconciled differences and explanations into a memo or summary deliverable.",
                    required_resource_types=["DifferenceSet", "ExceptionExplanation"],
                    provided_resource_types=["ReconciliationSummary"],
                    typical_graph_roles=["synthesis"],
                ),
            ],
            optional_roles=[
                MotifRoleDefinition(
                    role_name="policy_checker",
                    role_kind="support",
                    description="Verify whether differences are acceptable under policy or accounting rules.",
                    required_resource_types=["DifferenceSet"],
                    provided_resource_types=["ExceptionExplanation"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="cross_check_validator",
                    role_kind="validator",
                    description="Cross-check the reconciled results against a third source or validation basis.",
                    required_resource_types=["ReconciliationSummary"],
                    provided_resource_types=["ReconciliationSummary"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="missing_evidence_detector",
                    role_kind="support",
                    description="Distinguish missing support from actual calculation discrepancies.",
                    required_resource_types=["SourceRecord"],
                    provided_resource_types=["ExceptionExplanation"],
                    typical_graph_roles=["validator"],
                ),
            ],
            required_resource_types=["SourceRecord", "NormalizedRecord", "ReconciliationBasis"],
            provided_resource_types=["DifferenceSet", "ExceptionExplanation", "ReconciliationSummary"],
            expected_graph_shape="fan_in",
            execution_stage_template=[
                MotifExecutionStage(
                    stage_id="stage_extract_source_a",
                    stage_name="extract source A",
                    required_roles=["source_a_extractor"],
                    expected_outputs=["SourceRecord"],
                ),
                MotifExecutionStage(
                    stage_id="stage_extract_source_b",
                    stage_name="extract source B",
                    required_roles=["source_b_extractor"],
                    expected_outputs=["SourceRecord"],
                ),
                MotifExecutionStage(
                    stage_id="stage_normalize_records",
                    stage_name="normalize and align records",
                    required_roles=["normalizer"],
                    expected_outputs=["NormalizedRecord"],
                ),
                MotifExecutionStage(
                    stage_id="stage_calculate_differences",
                    stage_name="calculate differences",
                    required_roles=["difference_calculator"],
                    expected_outputs=["DifferenceSet"],
                ),
                MotifExecutionStage(
                    stage_id="stage_explain_exceptions",
                    stage_name="explain exceptions",
                    required_roles=["exception_explainer"],
                    expected_outputs=["ExceptionExplanation"],
                ),
                MotifExecutionStage(
                    stage_id="stage_synthesize_deliverable",
                    stage_name="synthesize deliverable",
                    required_roles=["deliverable_synthesizer"],
                    expected_outputs=["ReconciliationSummary"],
                ),
            ],
            validation_constraints=[
                MotifValidationConstraint(
                    constraint_id="must_preserve_source_provenance",
                    description="The reconciled result must preserve which source each record or figure came from.",
                    severity="high",
                    reason_codes=["lost_source_provenance"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_explain_unresolved_differences",
                    description="Unresolved differences must be explained instead of being silently absorbed.",
                    severity="high",
                    reason_codes=["unexplained_difference"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_distinguish_missing_from_mismatch",
                    description="Missing support must be distinguished from genuine calculation or data mismatches.",
                    severity="medium",
                    reason_codes=["missing_vs_mismatch_confusion"],
                ),
            ],
            common_failure_modes=[
                "source normalization skipped",
                "differences listed without explanation",
                "missing evidence confused with actual discrepancy",
                "final memo lacks reconciliation basis",
            ],
            notes=[
                "Designed for multi-source reconciliation and variance tasks where provenance and exception handling are both first-class.",
            ],
        )

    def _evidence_to_deliverable_grammar(self) -> MotifGraphGrammarRecord:
        motif_type = "evidence_to_deliverable"
        return MotifGraphGrammarRecord(
            motif_grammar_id=self._stable_id(motif_type),
            motif_type=motif_type,
            required_roles=[
                MotifRoleDefinition(
                    role_name="evidence_source",
                    role_kind="source",
                    description="Expose the candidate-visible source documents, schedules, or raw evidence package.",
                    required_resource_types=["SourceDocument"],
                    provided_resource_types=["SourceDocument"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="evidence_extractor",
                    role_kind="skill",
                    description="Extract the salient evidence facts, control findings, or report-line support from the source package.",
                    required_resource_types=["SourceDocument"],
                    provided_resource_types=["ControlEvidence", "CaseEvidence"],
                    typical_graph_roles=["transform"],
                ),
                MotifRoleDefinition(
                    role_name="reconciliation_or_policy_applier",
                    role_kind="skill",
                    description="Translate extracted evidence into a decision-ready basis through reconciliation, policy application, or scoped calculations.",
                    required_resource_types=["ControlEvidence", "PolicyRule", "Dataset"],
                    provided_resource_types=["ReconciliationDifference", "AppliedPolicyAssessment", "DeliverableSection"],
                    typical_graph_roles=["transform", "fan_in"],
                    notes=["This role keeps the motif broad enough for finance and audit evidence packages without collapsing into one task template."],
                ),
                MotifRoleDefinition(
                    role_name="exception_or_issue_handler",
                    role_kind="exception_handler",
                    description="Handle exceptions, unresolved support, or evidence gaps before the final output is synthesized.",
                    required_resource_types=["ReconciliationDifference", "ExceptionRecord", "AppliedPolicyAssessment"],
                    provided_resource_types=["ExceptionRecord", "DeliverableSection"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="deliverable_synthesizer",
                    role_kind="deliverable",
                    description="Turn the evidence-backed basis into a memo, review note, or manager-ready deliverable section.",
                    required_resource_types=["DeliverableSection", "ExceptionRecord", "AppliedPolicyAssessment"],
                    provided_resource_types=["ManagerReadyFinding", "DeliverableSection"],
                    typical_graph_roles=["synthesis"],
                ),
            ],
            optional_roles=[
                MotifRoleDefinition(
                    role_name="cross_check_validator",
                    role_kind="validator",
                    description="Cross-check the emerging conclusion against the raw source package or supporting schedules.",
                    required_resource_types=["ControlEvidence", "DeliverableSection"],
                    provided_resource_types=["DeliverableSection"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="evidence_gap_detector",
                    role_kind="support",
                    description="Flag where the source package is incomplete for a clean deliverable conclusion.",
                    required_resource_types=["SourceDocument"],
                    provided_resource_types=["ExceptionRecord"],
                    typical_graph_roles=["validator"],
                ),
            ],
            required_resource_types=["SourceDocument", "ControlEvidence", "DeliverableSection"],
            provided_resource_types=["ManagerReadyFinding", "DeliverableSection", "ExceptionRecord"],
            expected_graph_shape="chain",
            execution_stage_template=[
                MotifExecutionStage(
                    stage_id="stage_collect_source_package",
                    stage_name="collect source package",
                    required_roles=["evidence_source"],
                    expected_outputs=["SourceDocument"],
                ),
                MotifExecutionStage(
                    stage_id="stage_extract_evidence",
                    stage_name="extract evidence",
                    required_roles=["evidence_extractor"],
                    expected_outputs=["ControlEvidence", "CaseEvidence"],
                ),
                MotifExecutionStage(
                    stage_id="stage_translate_to_decision_basis",
                    stage_name="translate evidence into decision basis",
                    required_roles=["reconciliation_or_policy_applier"],
                    expected_outputs=["ReconciliationDifference", "AppliedPolicyAssessment", "DeliverableSection"],
                ),
                MotifExecutionStage(
                    stage_id="stage_handle_issues",
                    stage_name="handle issues and unresolved support",
                    required_roles=["exception_or_issue_handler"],
                    expected_outputs=["ExceptionRecord"],
                ),
                MotifExecutionStage(
                    stage_id="stage_synthesize_deliverable",
                    stage_name="synthesize deliverable",
                    required_roles=["deliverable_synthesizer"],
                    expected_outputs=["ManagerReadyFinding", "DeliverableSection"],
                ),
            ],
            validation_constraints=[
                MotifValidationConstraint(
                    constraint_id="must_trace_deliverable_to_evidence",
                    description="The deliverable must stay traceable to candidate-visible source evidence.",
                    severity="high",
                    reason_codes=["missing_evidence_traceability"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_preserve_exception_visibility",
                    description="Open issues or exception paths must remain visible in the final deliverable.",
                    severity="medium",
                    reason_codes=["flattened_exception_handling"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_not_skip_intermediate_basis",
                    description="The task should not jump from raw evidence directly to prose without an intermediate decision basis.",
                    severity="medium",
                    reason_codes=["missing_intermediate_basis"],
                ),
            ],
            common_failure_modes=[
                "raw evidence copied into deliverable without synthesis",
                "conclusion stated without traceable support",
                "exception path omitted from final memo",
                "intermediate reconciliation or policy basis skipped",
            ],
            notes=[
                "Designed for source-package-to-deliverable tasks where the main challenge is turning messy evidence into a review-ready artifact.",
            ],
        )

    def _cross_check_validation_grammar(self) -> MotifGraphGrammarRecord:
        motif_type = "cross_check_validation"
        return MotifGraphGrammarRecord(
            motif_grammar_id=self._stable_id(motif_type),
            motif_type=motif_type,
            required_roles=[
                MotifRoleDefinition(
                    role_name="primary_source_collector",
                    role_kind="source",
                    description="Provide the primary schedule, workbook, or evidence source under review.",
                    required_resource_types=["Dataset", "SpreadsheetWorkbook", "SourceDocument"],
                    provided_resource_types=["Dataset", "SpreadsheetWorkbook", "SourceDocument"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="secondary_support_source",
                    role_kind="source",
                    description="Provide a second evidence basis for cross-checking the primary source.",
                    required_resource_types=["ControlEvidence", "FinancialStatement", "SourceDocument"],
                    provided_resource_types=["ControlEvidence", "FinancialStatement", "SourceDocument"],
                    typical_graph_roles=["starter"],
                ),
                MotifRoleDefinition(
                    role_name="normalizer_or_mapper",
                    role_kind="skill",
                    description="Normalize or map the two sources into a comparable structure before validation.",
                    required_resource_types=["Dataset", "SpreadsheetWorkbook", "MappingTable"],
                    provided_resource_types=["NormalizedRecord", "MappingTable"],
                    typical_graph_roles=["transform"],
                ),
                MotifRoleDefinition(
                    role_name="cross_check_engine",
                    role_kind="skill",
                    description="Run the actual cross-check and surface mismatches, exceptions, or confirmation signals.",
                    required_resource_types=["NormalizedRecord", "ControlEvidence", "FinancialStatement"],
                    provided_resource_types=["ReconciliationDifference", "ControlEvidence", "ExceptionRecord"],
                    typical_graph_roles=["fan_in", "transform"],
                ),
                MotifRoleDefinition(
                    role_name="validation_synthesizer",
                    role_kind="deliverable",
                    description="Produce the validation workpaper or conclusion artifact from the cross-check results.",
                    required_resource_types=["ReconciliationDifference", "ExceptionRecord", "DeliverableSection"],
                    provided_resource_types=["DeliverableSection", "ManagerReadyFinding"],
                    typical_graph_roles=["synthesis"],
                ),
            ],
            optional_roles=[
                MotifRoleDefinition(
                    role_name="exception_classifier",
                    role_kind="exception_handler",
                    description="Classify whether a mismatch is a true exception, acceptable variance, or missing-support issue.",
                    required_resource_types=["ReconciliationDifference"],
                    provided_resource_types=["ExceptionRecord"],
                    typical_graph_roles=["validator"],
                ),
                MotifRoleDefinition(
                    role_name="sampling_or_threshold_checker",
                    role_kind="validator",
                    description="Apply threshold or sample-size logic before a mismatch is escalated.",
                    required_resource_types=["AuditSample", "ComplianceRequirement"],
                    provided_resource_types=["ExceptionRecord"],
                    typical_graph_roles=["validator"],
                ),
            ],
            required_resource_types=["Dataset", "ControlEvidence", "ReconciliationDifference"],
            provided_resource_types=["ExceptionRecord", "DeliverableSection", "ManagerReadyFinding"],
            expected_graph_shape="dag",
            execution_stage_template=[
                MotifExecutionStage(
                    stage_id="stage_collect_primary_source",
                    stage_name="collect primary source",
                    required_roles=["primary_source_collector"],
                    expected_outputs=["Dataset", "SpreadsheetWorkbook", "SourceDocument"],
                ),
                MotifExecutionStage(
                    stage_id="stage_collect_secondary_source",
                    stage_name="collect secondary support",
                    required_roles=["secondary_support_source"],
                    expected_outputs=["ControlEvidence", "FinancialStatement", "SourceDocument"],
                ),
                MotifExecutionStage(
                    stage_id="stage_normalize_for_validation",
                    stage_name="normalize for validation",
                    required_roles=["normalizer_or_mapper"],
                    expected_outputs=["NormalizedRecord", "MappingTable"],
                ),
                MotifExecutionStage(
                    stage_id="stage_run_cross_check",
                    stage_name="run cross-check",
                    required_roles=["cross_check_engine"],
                    expected_outputs=["ReconciliationDifference", "ExceptionRecord"],
                ),
                MotifExecutionStage(
                    stage_id="stage_summarize_validation",
                    stage_name="summarize validation",
                    required_roles=["validation_synthesizer"],
                    expected_outputs=["DeliverableSection", "ManagerReadyFinding"],
                ),
            ],
            validation_constraints=[
                MotifValidationConstraint(
                    constraint_id="must_name_validation_basis",
                    description="The validation artifact must preserve what the primary source was checked against.",
                    severity="high",
                    reason_codes=["missing_validation_basis"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_distinguish_confirmed_from_exception",
                    description="Confirmed matches must be separated from true exceptions or unsupported items.",
                    severity="high",
                    reason_codes=["match_exception_blur"],
                ),
                MotifValidationConstraint(
                    constraint_id="must_keep_threshold_logic_explicit",
                    description="Any sample-size or threshold-based escalation logic should remain visible.",
                    severity="medium",
                    reason_codes=["hidden_threshold_logic"],
                ),
            ],
            common_failure_modes=[
                "primary and secondary sources never normalized onto one basis",
                "cross-check result lists mismatches without validation basis",
                "sample-threshold logic hidden from the final workpaper",
                "summary collapses confirmed and unresolved items together",
            ],
            notes=[
                "Designed for tasks where the deliverable should visibly prove that a cross-check or validation pass actually happened.",
            ],
        )

    def _stable_id(self, motif_type: str) -> str:
        return f"mgg_{sha1(motif_type.encode('utf-8')).hexdigest()[:12]}"
