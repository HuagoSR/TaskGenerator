import json
from collections import Counter
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v2_schema import FileSpec, SheetSpec, TaskBlueprint
from task_generator.v3_pipeline_b_sampler import PipelineBSubgraph
from task_generator.v3_source_schema import load_json_file


EvidenceVisibility = Literal["candidate_visible", "teacher_only"]
GeneratorStatus = Literal["planned_only", "ready_for_deterministic_generation", "needs_template_design"]
GenerationStrategy = Literal[
    "deterministic_structured",
    "llm_structured_prose",
    "stirrup_agentic_file",
    "external_or_imported",
]
EvidenceDossierRole = Literal[
    "primary_evidence",
    "policy_reference",
    "manager_notes",
    "outdated_version",
    "distractor_source",
    "missing_attachment",
    "conflict_source",
]
NoiseLevel = Literal["low", "medium", "high"]


class ReferenceFilePlanRequest(BaseModel):
    blueprint_path: str
    subgraph_report_path: Optional[str] = None


class PlannedColumn(BaseModel):
    column_id: str
    name: str
    semantic_type: str
    evidence_role: str
    candidate_visible: bool = True
    source_resource_ids: List[str] = Field(default_factory=list)


class PlannedTable(BaseModel):
    table_id: str
    sheet_name: str
    row_count_target: int
    columns: List[PlannedColumn] = Field(default_factory=list)
    linked_resource_ids: List[str] = Field(default_factory=list)
    generator_notes: List[str] = Field(default_factory=list)


class PlannedTextSection(BaseModel):
    section_id: str
    heading: str
    evidence_role: str
    clause_id: Optional[str] = None
    candidate_visible: bool = True
    linked_resource_ids: List[str] = Field(default_factory=list)
    generator_notes: List[str] = Field(default_factory=list)


class ValidationContract(BaseModel):
    required_checks: List[str] = Field(default_factory=list)
    requires_evidence_mapping: bool = True
    locator_scheme: str = "file_heading_or_column"
    proposal_allowed: bool = False


class EvidenceAnchor(BaseModel):
    evidence_id: str
    file_id: str
    locator: str
    visibility: EvidenceVisibility = "candidate_visible"
    semantic_type: str
    linked_skill_ids: List[str] = Field(default_factory=list)
    linked_resource_ids: List[str] = Field(default_factory=list)
    provenance_notes: List[str] = Field(default_factory=list)


class EvidenceDossierFileRole(BaseModel):
    file_id: str
    role: EvidenceDossierRole
    noise_level: NoiseLevel = "low"
    contains_conflict: bool = False
    contains_missing_fields: bool = False
    version_relation: Optional[str] = None


class EvidenceDossierConstraint(BaseModel):
    constraint_id: str
    description: str
    constraint_type: str
    linked_file_ids: List[str] = Field(default_factory=list)


class EvidenceDossierDistractor(BaseModel):
    distractor_id: str
    distractor_type: str
    description: str
    linked_file_ids: List[str] = Field(default_factory=list)


class ExpectedEvidencePath(BaseModel):
    evidence_id: str
    file_id: str
    locator: str
    semantic_type: str


class EvidenceDossierSyntheticArtifact(BaseModel):
    artifact_id: str
    role: EvidenceDossierRole
    title: str
    candidate_visible: bool = True
    realization_mode: str = "metadata_only"
    description: str
    linked_file_ids: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)


class EvidenceDossierPlan(BaseModel):
    dossier_id: str
    business_context: str
    candidate_visible_files: List[str] = Field(default_factory=list)
    teacher_only_files: List[str] = Field(default_factory=list)
    file_roles: List[EvidenceDossierFileRole] = Field(default_factory=list)
    cross_file_constraints: List[EvidenceDossierConstraint] = Field(default_factory=list)
    distractor_items: List[EvidenceDossierDistractor] = Field(default_factory=list)
    expected_evidence_paths: List[ExpectedEvidencePath] = Field(default_factory=list)
    synthetic_artifacts: List[EvidenceDossierSyntheticArtifact] = Field(default_factory=list)


class PlannedReferenceFile(BaseModel):
    file_id: str
    file_name: str
    file_role: str
    file_format: str
    generator_status: GeneratorStatus
    preferred_generation_strategy: GenerationStrategy = "deterministic_structured"
    supported_generation_strategies: List[GenerationStrategy] = Field(default_factory=list)
    validation_contract: ValidationContract = Field(default_factory=ValidationContract)
    tables: List[PlannedTable] = Field(default_factory=list)
    text_sections: List[PlannedTextSection] = Field(default_factory=list)
    evidence_anchors: List[EvidenceAnchor] = Field(default_factory=list)
    candidate_visible: bool = True
    generation_constraints: List[str] = Field(default_factory=list)
    provenance_hooks: List[str] = Field(default_factory=list)


class ReferenceFilePlanDiagnostics(BaseModel):
    blueprint_file_count: int = 0
    planned_file_count: int = 0
    planned_table_count: int = 0
    planned_text_section_count: int = 0
    planned_evidence_anchor_count: int = 0
    selected_skill_count: int = 0
    subgraph_id: Optional[str] = None
    subgraph_confidence: Optional[str] = None
    resource_counts_by_mode: Dict[str, int] = Field(default_factory=dict)
    resource_counts_by_direction: Dict[str, int] = Field(default_factory=dict)
    missing_or_weak_pipeline_a_signals: List[str] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)
    planner_warnings: List[str] = Field(default_factory=list)


class ReferenceFilePlan(BaseModel):
    reference_file_plan_version: str = "v3.reference_file_plan.1"
    request: ReferenceFilePlanRequest
    blueprint_id: str
    template_family: str
    selected_skill_ids: List[str] = Field(default_factory=list)
    planned_files: List[PlannedReferenceFile] = Field(default_factory=list)
    evidence_dossier: EvidenceDossierPlan
    deliverable_expectations: List[Dict[str, Any]] = Field(default_factory=list)
    data_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: ReferenceFilePlanDiagnostics
    notes: List[str] = Field(default_factory=list)


class ReferenceFilePlanner:
    """Plan candidate-visible reference files without generating concrete file contents."""

    def build_plan(
        self,
        blueprint_path: str | Path,
        subgraph_report_path: Optional[str | Path] = None,
    ) -> ReferenceFilePlan:
        blueprint_payload = load_json_file(str(blueprint_path))
        blueprint = TaskBlueprint.model_validate(blueprint_payload)
        subgraph = self._load_subgraph(subgraph_report_path)
        resource_nodes = subgraph.resource_nodes if subgraph else []
        selected_skill_ids = list(blueprint.selected_skills)
        planned_files = [
            self._planned_file(file_spec, blueprint, subgraph, resource_nodes)
            for file_spec in blueprint.data_spec.reference_files
        ]
        evidence_dossier = self._evidence_dossier(blueprint, subgraph, planned_files)
        diagnostics = self._diagnostics(blueprint, subgraph, planned_files)

        return ReferenceFilePlan(
            request=ReferenceFilePlanRequest(
                blueprint_path=str(blueprint_path),
                subgraph_report_path=str(subgraph_report_path) if subgraph_report_path else None,
            ),
            blueprint_id=blueprint.blueprint_id,
            template_family=blueprint.template_family,
            selected_skill_ids=selected_skill_ids,
            planned_files=planned_files,
            evidence_dossier=evidence_dossier,
            deliverable_expectations=[
                {
                    "file_name": deliverable.file_name,
                    "file_role": deliverable.file_role,
                    "requirements": deliverable.requirements,
                }
                for deliverable in blueprint.deliverable_spec
            ],
            data_relationships=[
                {
                    "relation_type": relationship.relation_type,
                    "left": relationship.left,
                    "right": relationship.right,
                }
                for relationship in blueprint.data_spec.data_relationships
            ],
            diagnostics=diagnostics,
            notes=[
                "This is a planning artifact only; no reference files are generated.",
                "Stable IDs are intended to become provenance anchors for future file generation and GoldenRun.",
                "Candidate-visible evidence is separated from teacher-only notes before concrete files exist.",
                "Evidence dossier metadata describes the intended evidence ecology without requiring new file generators in V1.",
            ],
        )

    def write_outputs(self, plan: ReferenceFilePlan, output_dir: str | Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        plan_path = output_path / "reference_file_plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        return {"reference_file_plan_path": str(plan_path)}

    def _load_subgraph(self, subgraph_report_path: Optional[str | Path]) -> Optional[PipelineBSubgraph]:
        if not subgraph_report_path:
            return None
        return PipelineBSubgraph.model_validate(load_json_file(str(subgraph_report_path)))

    def _planned_file(
        self,
        file_spec: FileSpec,
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
        resource_nodes: List[Any],
    ) -> PlannedReferenceFile:
        file_id = self._stable_id("file", [blueprint.blueprint_id, file_spec.file_name])
        file_format = self._file_format(file_spec.file_name)
        linked_resources = self._resources_for_file(file_spec, resource_nodes)
        tables = [
            self._planned_table(file_id, file_spec, sheet_spec, linked_resources)
            for sheet_spec in file_spec.sheet_specs
        ]
        text_sections = []
        if not file_spec.sheet_specs:
            text_sections = self._text_sections(file_id, file_spec, linked_resources)

        anchors = []
        for table in tables:
            anchors.extend(
                self._table_anchors(file_id, file_spec.file_name, table, blueprint.selected_skills)
            )
        for section in text_sections:
            anchors.append(
                EvidenceAnchor(
                    evidence_id=self._stable_id("ev", [file_id, section.section_id]),
                    file_id=file_id,
                    locator=self._text_anchor_locator(file_spec.file_name, section),
                    visibility="candidate_visible",
                    semantic_type=section.evidence_role,
                    linked_skill_ids=blueprint.selected_skills,
                    linked_resource_ids=section.linked_resource_ids,
                    provenance_notes=["Text-section evidence anchor planned from blueprint file spec."],
                )
            )

        return PlannedReferenceFile(
            file_id=file_id,
            file_name=file_spec.file_name,
            file_role=file_spec.file_role,
            file_format=file_format,
            generator_status=self._generator_status(file_format, file_spec.sheet_specs),
            preferred_generation_strategy=self._preferred_generation_strategy(file_spec, file_format),
            supported_generation_strategies=self._supported_generation_strategies(file_spec, file_format),
            validation_contract=self._validation_contract(file_spec, file_format),
            tables=tables,
            text_sections=text_sections,
            evidence_anchors=anchors,
            candidate_visible=file_spec.file_role != "final_deliverable",
            generation_constraints=self._generation_constraints(file_spec, subgraph),
            provenance_hooks=self._provenance_hooks(file_spec, linked_resources),
        )

    def _planned_table(
        self,
        file_id: str,
        file_spec: FileSpec,
        sheet_spec: SheetSpec,
        linked_resources: List[Any],
    ) -> PlannedTable:
        table_id = self._stable_id("table", [file_id, sheet_spec.sheet_name])
        resource_ids = [resource.resource_id for resource in linked_resources]
        columns = [
            PlannedColumn(
                column_id=self._stable_id("col", [table_id, column.name]),
                name=column.name,
                semantic_type=column.semantic_type,
                evidence_role=self._column_evidence_role(column.semantic_type),
                candidate_visible=True,
                source_resource_ids=resource_ids,
            )
            for column in sheet_spec.columns
        ]
        return PlannedTable(
            table_id=table_id,
            sheet_name=sheet_spec.sheet_name,
            row_count_target=sheet_spec.row_count_target,
            columns=columns,
            linked_resource_ids=resource_ids,
            generator_notes=[
                "Generate deterministic rows that satisfy the blueprint relationships.",
                "Reserve evidence IDs for future GoldenRun citation checks.",
            ],
        )

    def _text_sections(self, file_id: str, file_spec: FileSpec, linked_resources: List[Any]) -> List[PlannedTextSection]:
        resource_ids = [resource.resource_id for resource in linked_resources]
        if file_spec.file_name.lower() == "policy_reference.docx":
            clause_specs = [
                ("POL-001", "Applicable Requirements", "policy_rule"),
                ("POL-002", "Evidence Interpretation Rules", "policy_rule"),
                ("POL-003", "Decision Rules", "decision_rule"),
                ("POL-004", "Exception Escalation", "contextual_reference"),
            ]
            return [
                PlannedTextSection(
                    section_id=self._stable_id("section", [file_id, clause_id]),
                    heading=heading,
                    evidence_role=evidence_role,
                    clause_id=clause_id,
                    candidate_visible=True,
                    linked_resource_ids=resource_ids,
                    generator_notes=[
                        "Write this section as a stable policy clause with deterministic wording.",
                        "Keep the clause ID visible in the rendered document.",
                    ],
                )
                for clause_id, heading, evidence_role in clause_specs
            ]

        headings = ["Purpose", "Applicable Guidance", "Evidence Interpretation"]
        if file_spec.file_role == "reference_table":
            headings.append("Decision Rules")
        return [
            PlannedTextSection(
                section_id=self._stable_id("section", [file_id, heading]),
                heading=heading,
                evidence_role=self._section_evidence_role(file_spec.file_name, heading),
                candidate_visible=True,
                linked_resource_ids=resource_ids,
                generator_notes=["Use stable wording; do not hide numeric grading targets in prose."],
            )
            for heading in headings
        ]

    def _table_anchors(
        self,
        file_id: str,
        file_name: str,
        table: PlannedTable,
        selected_skill_ids: List[str],
    ) -> List[EvidenceAnchor]:
        anchors = []
        for column in table.columns:
            anchors.append(
                EvidenceAnchor(
                    evidence_id=self._stable_id("ev", [file_id, table.table_id, column.column_id]),
                    file_id=file_id,
                    locator=f"{file_name}:{table.sheet_name}.{column.name}",
                    visibility="candidate_visible",
                    semantic_type=column.semantic_type,
                    linked_skill_ids=selected_skill_ids,
                    linked_resource_ids=column.source_resource_ids,
                    provenance_notes=["Column-level evidence anchor planned before concrete data generation."],
                )
            )
        return anchors

    def _resources_for_file(self, file_spec: FileSpec, resource_nodes: List[Any]) -> List[Any]:
        if not resource_nodes:
            return []
        file_tokens = self._tokens(file_spec.file_name)
        role_tokens = self._tokens(file_spec.file_role)
        scored = []
        for resource in resource_nodes:
            resource_tokens = self._tokens(resource.resource_type + " " + resource.subtype + " " + resource.source_text)
            score = len((file_tokens | role_tokens) & resource_tokens)
            if file_spec.file_role == "source_data" and resource.direction in {"required", "provided"}:
                score += 1
            if file_spec.file_role == "reference_table" and resource.resource_type in {
                "PolicyRule",
                "ComplianceRequirement",
                "ControlEvidence",
                "StructuredTable",
            }:
                score += 2
            if score > 0:
                scored.append((score, resource.resource_id, resource))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [resource for _, _, resource in scored[:8]]

    def _diagnostics(
        self,
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
        planned_files: List[PlannedReferenceFile],
    ) -> ReferenceFilePlanDiagnostics:
        resource_nodes = subgraph.resource_nodes if subgraph else []
        mode_counts = Counter(resource.evidence_mode for resource in resource_nodes)
        direction_counts = Counter(resource.direction for resource in resource_nodes)
        warnings = []
        if not blueprint.data_spec.reference_files:
            warnings.append("blueprint_has_no_reference_files")
        if subgraph is None:
            warnings.append("subgraph_report_not_provided")
        elif subgraph.diagnostics.confidence == "low_due_to_resource_fallback":
            warnings.append("resource_plan_uses_low_confidence_fallback")
        if resource_nodes and mode_counts.get("typed", 0) == 0:
            warnings.append("no_typed_resources_available_for_file_plan")
        if not any(file.evidence_anchors for file in planned_files):
            warnings.append("no_evidence_anchors_planned")

        return ReferenceFilePlanDiagnostics(
            blueprint_file_count=len(blueprint.data_spec.reference_files),
            planned_file_count=len(planned_files),
            planned_table_count=sum(len(file.tables) for file in planned_files),
            planned_text_section_count=sum(len(file.text_sections) for file in planned_files),
            planned_evidence_anchor_count=sum(len(file.evidence_anchors) for file in planned_files),
            selected_skill_count=len(blueprint.selected_skills),
            subgraph_id=subgraph.subgraph_id if subgraph else None,
            subgraph_confidence=subgraph.diagnostics.confidence if subgraph else None,
            resource_counts_by_mode=dict(sorted(mode_counts.items())),
            resource_counts_by_direction=dict(sorted(direction_counts.items())),
            missing_or_weak_pipeline_a_signals=(
                subgraph.diagnostics.missing_or_weak_pipeline_a_signals if subgraph else []
            ),
            unresolved_gaps=subgraph.diagnostics.unresolved_gaps if subgraph else [],
            planner_warnings=warnings,
        )

    def _generation_constraints(
        self,
        file_spec: FileSpec,
        subgraph: Optional[PipelineBSubgraph],
    ) -> List[str]:
        constraints = [
            "Use stable evidence IDs that can be cited in the candidate deliverable.",
            "Keep candidate-visible facts sufficient for teacher verification.",
        ]
        if file_spec.sheet_specs:
            constraints.append("Generated rows must match each sheet's declared columns and target row counts.")
        else:
            constraints.append("Generated prose must expose policy or guidance anchors without revealing answers.")
        if file_spec.file_name.lower() == "policy_reference.docx":
            constraints.extend(
                [
                    "Render stable visible clause IDs such as POL-001 and POL-002.",
                    "Expose at least one applicable-requirement clause for policy lookup.",
                    "Keep the policy document candidate-visible and suitable for evidence citation.",
                ]
            )
        if subgraph and subgraph.diagnostics.confidence == "low_due_to_resource_fallback":
            constraints.append("Resource coverage is provisional because compatibility was inferred from legacy text.")
        return constraints

    def _provenance_hooks(self, file_spec: FileSpec, linked_resources: List[Any]) -> List[str]:
        hooks = [f"blueprint_file:{file_spec.file_name}", f"blueprint_role:{file_spec.file_role}"]
        hooks.extend(f"resource:{resource.resource_id}" for resource in linked_resources)
        return hooks

    def _generator_status(self, file_format: str, sheet_specs: List[SheetSpec]) -> GeneratorStatus:
        if file_format in {"xlsx", "csv", "json"} and sheet_specs:
            return "ready_for_deterministic_generation"
        if file_format in {"md", "txt", "docx"}:
            return "ready_for_deterministic_generation"
        return "needs_template_design"

    def _preferred_generation_strategy(self, file_spec: FileSpec, file_format: str) -> GenerationStrategy:
        if file_format in {"xlsx", "csv", "json"}:
            return "deterministic_structured"
        if file_spec.file_name.lower() == "policy_reference.docx":
            return "deterministic_structured"
        if file_format in {"md", "txt", "docx"}:
            return "llm_structured_prose"
        return "stirrup_agentic_file"

    def _supported_generation_strategies(
        self,
        file_spec: FileSpec,
        file_format: str,
    ) -> List[GenerationStrategy]:
        if file_format in {"xlsx", "csv", "json"}:
            return ["deterministic_structured", "external_or_imported"]
        if file_spec.file_name.lower() == "policy_reference.docx":
            return ["deterministic_structured", "llm_structured_prose", "stirrup_agentic_file"]
        if file_format in {"md", "txt", "docx"}:
            return ["deterministic_structured", "llm_structured_prose", "stirrup_agentic_file"]
        return ["stirrup_agentic_file", "external_or_imported"]

    def _validation_contract(self, file_spec: FileSpec, file_format: str) -> ValidationContract:
        if file_format in {"xlsx", "csv", "json"}:
            return ValidationContract(
                required_checks=["file_exists", "table_shape", "evidence_mapping_nonempty"],
                requires_evidence_mapping=True,
                locator_scheme="table_column_locator",
                proposal_allowed=True,
            )
        if file_spec.file_name.lower() == "policy_reference.docx":
            return ValidationContract(
                required_checks=[
                    "file_exists",
                    "clause_ids_present",
                    "required_sections_present",
                    "evidence_mapping_nonempty",
                ],
                requires_evidence_mapping=True,
                locator_scheme="clause_locator",
                proposal_allowed=True,
            )
        return ValidationContract(
            required_checks=["file_exists", "section_presence", "evidence_mapping_nonempty"],
            requires_evidence_mapping=True,
            locator_scheme="section_locator",
            proposal_allowed=True,
        )

    def _file_format(self, file_name: str) -> str:
        suffix = Path(file_name).suffix.lower().lstrip(".")
        return suffix or "unknown"

    def _column_evidence_role(self, semantic_type: str) -> str:
        lowered = semantic_type.lower()
        if "identifier" in lowered:
            return "citation_key"
        if "amount" in lowered or "value" in lowered or "count" in lowered:
            return "quantitative_fact"
        if "period" in lowered or "time" in lowered:
            return "time_context"
        return "qualitative_fact"

    def _section_evidence_role(self, file_name: str, heading: str) -> str:
        text = f"{file_name} {heading}".lower()
        if "policy" in text or "guidance" in text or "rule" in text:
            return "policy_rule"
        if "decision" in text:
            return "decision_rule"
        return "contextual_reference"

    def _text_anchor_locator(self, file_name: str, section: PlannedTextSection) -> str:
        if section.clause_id:
            return f"{file_name}:{section.clause_id}"
        return f"{file_name}:{section.heading}"

    def _evidence_dossier(
        self,
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
        planned_files: List[PlannedReferenceFile],
    ) -> EvidenceDossierPlan:
        selected_motif = subgraph.selected_motif if subgraph else blueprint.template_family
        business_context = blueprint.scenario_spec.business_context.strip() or f"{blueprint.template_family}:{selected_motif}"
        file_roles = self._dossier_file_roles(planned_files, blueprint, subgraph)
        constraints = self._dossier_constraints(planned_files, blueprint, subgraph)
        distractors = self._dossier_distractors(file_roles, constraints)
        synthetic_artifacts = self._dossier_synthetic_artifacts(
            blueprint=blueprint,
            subgraph=subgraph,
            file_roles=file_roles,
            constraints=constraints,
            distractors=distractors,
        )
        expected_paths = [
            ExpectedEvidencePath(
                evidence_id=anchor.evidence_id,
                file_id=anchor.file_id,
                locator=anchor.locator,
                semantic_type=anchor.semantic_type,
            )
            for planned_file in planned_files
            for anchor in planned_file.evidence_anchors
        ]
        return EvidenceDossierPlan(
            dossier_id=self._stable_id("dos", [blueprint.blueprint_id, selected_motif]),
            business_context=business_context,
            candidate_visible_files=[planned.file_id for planned in planned_files if planned.candidate_visible],
            teacher_only_files=[],
            file_roles=file_roles,
            cross_file_constraints=constraints,
            distractor_items=distractors,
            expected_evidence_paths=expected_paths,
            synthetic_artifacts=synthetic_artifacts,
        )

    def _dossier_file_roles(
        self,
        planned_files: List[PlannedReferenceFile],
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
    ) -> List[EvidenceDossierFileRole]:
        selected_motif = subgraph.selected_motif if subgraph else ""
        missing_support = self._dossier_has_missing_support(blueprint, subgraph)
        primary_ids = [
            planned.file_id
            for planned in planned_files
            if self._dossier_role_for_file(planned) == "primary_evidence"
        ]
        conflict_enabled = selected_motif in {"fan_in_reconciliation", "cross_check_validation"} and bool(primary_ids)
        conflict_file_id = primary_ids[0] if conflict_enabled else None
        missing_file_id = primary_ids[-1] if missing_support and primary_ids else None
        roles: List[EvidenceDossierFileRole] = []
        for planned in planned_files:
            role = self._dossier_role_for_file(planned)
            roles.append(
                EvidenceDossierFileRole(
                    file_id=planned.file_id,
                    role=role,
                    noise_level=self._dossier_noise_level(planned),
                    contains_conflict=planned.file_id == conflict_file_id,
                    contains_missing_fields=planned.file_id == missing_file_id,
                    version_relation=self._dossier_version_relation(role, primary_ids),
                )
            )
        return roles

    def _dossier_role_for_file(self, planned: PlannedReferenceFile) -> EvidenceDossierRole:
        file_name = planned.file_name.lower()
        if file_name == "policy_reference.docx":
            return "policy_reference"
        if any(token in file_name for token in ["notes", "memo", "manager"]):
            return "manager_notes"
        if any(token in file_name for token in ["old", "prior", "archived"]):
            return "outdated_version"
        if planned.file_role in {"source_data", "reference_table", "supporting_data"} or planned.file_format in {"xlsx", "csv", "json"}:
            return "primary_evidence"
        return "primary_evidence"

    def _dossier_noise_level(self, planned: PlannedReferenceFile) -> NoiseLevel:
        if planned.file_format in {"xlsx", "csv", "json"}:
            return "low"
        return "medium"

    def _dossier_has_missing_support(
        self,
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
    ) -> bool:
        context = " ".join(
            [
                blueprint.scenario_spec.business_context,
                blueprint.scenario_spec.role,
                blueprint.scenario_spec.time_context,
            ]
        ).lower()
        explicit_missing_signals = [
            "missing attachment",
            "missing support",
            "support gap",
            "incomplete evidence",
            "incomplete support",
            "absent attachment",
            "attachment gap",
            "not provided",
            "not yet provided",
            "supporting document missing",
        ]
        if any(signal in context for signal in explicit_missing_signals):
            return True
        return False

    def _dossier_version_relation(
        self,
        role: EvidenceDossierRole,
        primary_ids: List[str],
    ) -> Optional[str]:
        if role == "outdated_version" and primary_ids:
            return f"outdated_of:{primary_ids[0]}"
        if role == "conflict_source" and primary_ids:
            return f"conflicts_with:{primary_ids[0]}"
        if role in {"primary_evidence", "policy_reference", "manager_notes"}:
            return "current"
        return None

    def _dossier_constraints(
        self,
        planned_files: List[PlannedReferenceFile],
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
    ) -> List[EvidenceDossierConstraint]:
        file_ids = [planned.file_id for planned in planned_files if planned.candidate_visible]
        constraints: List[EvidenceDossierConstraint] = []
        for index, relationship in enumerate(blueprint.data_spec.data_relationships, start=1):
            constraints.append(
                EvidenceDossierConstraint(
                    constraint_id=self._stable_id("dossier_constraint", [blueprint.blueprint_id, str(index)]),
                    description=f"{relationship.relation_type} must remain traceable between {relationship.left} and {relationship.right}.",
                    constraint_type=relationship.relation_type,
                    linked_file_ids=file_ids,
                )
            )
        motif = subgraph.selected_motif if subgraph else ""
        if motif == "fan_in_reconciliation":
            constraints.append(
                EvidenceDossierConstraint(
                    constraint_id=self._stable_id("dossier_constraint", [blueprint.blueprint_id, "reconciliation"]),
                    description="At least one primary evidence file should require cross-file reconciliation against another source.",
                    constraint_type="reconciliation_required",
                    linked_file_ids=file_ids,
                )
            )
        if motif == "policy_application":
            constraints.append(
                EvidenceDossierConstraint(
                    constraint_id=self._stable_id("dossier_constraint", [blueprint.blueprint_id, "policy_link"]),
                    description="Candidate-visible evidence should be interpretable alongside the policy reference clauses.",
                    constraint_type="policy_evidence_linking",
                    linked_file_ids=file_ids,
                )
            )
        return constraints

    def _dossier_distractors(
        self,
        file_roles: List[EvidenceDossierFileRole],
        constraints: List[EvidenceDossierConstraint],
    ) -> List[EvidenceDossierDistractor]:
        distractors: List[EvidenceDossierDistractor] = []
        if any(role.contains_conflict for role in file_roles):
            linked = [role.file_id for role in file_roles if role.contains_conflict]
            distractors.append(
                EvidenceDossierDistractor(
                    distractor_id=self._stable_id("distractor", [*linked, "conflict"]),
                    distractor_type="conflicting_signal",
                    description="One candidate-visible evidence source may push toward a conflicting interpretation that still needs reconciliation.",
                    linked_file_ids=linked,
                )
            )
        if any(role.contains_missing_fields for role in file_roles):
            linked = [role.file_id for role in file_roles if role.contains_missing_fields]
            distractors.append(
                EvidenceDossierDistractor(
                    distractor_id=self._stable_id("distractor", [*linked, "missing"]),
                    distractor_type="missing_support",
                    description="A file may appear complete at first glance but still omit fields needed for a fully supported conclusion.",
                    linked_file_ids=linked,
                )
            )
        if constraints and not distractors:
            linked = constraints[0].linked_file_ids[:2]
            distractors.append(
                EvidenceDossierDistractor(
                    distractor_id=self._stable_id("distractor", [*(linked or ["none"]), "ambient"]),
                    distractor_type="ambient_noise",
                    description="The dossier is simple in V1, but future versions may attach a stale or low-signal supporting source around these files.",
                    linked_file_ids=linked,
                )
            )
        return distractors[:2]

    def _dossier_synthetic_artifacts(
        self,
        blueprint: TaskBlueprint,
        subgraph: Optional[PipelineBSubgraph],
        file_roles: List[EvidenceDossierFileRole],
        constraints: List[EvidenceDossierConstraint],
        distractors: List[EvidenceDossierDistractor],
    ) -> List[EvidenceDossierSyntheticArtifact]:
        selected_motif = subgraph.selected_motif if subgraph else blueprint.template_family
        context_tokens = self._tokens(
            " ".join(
                [
                    blueprint.scenario_spec.role,
                    blueprint.scenario_spec.business_context,
                    blueprint.task_metadata.scenario_title,
                    " ".join(requirement for deliverable in blueprint.deliverable_spec for requirement in deliverable.requirements),
                    " ".join(deliverable.file_role for deliverable in blueprint.deliverable_spec),
                ]
            )
        )
        primary_file_ids = [role.file_id for role in file_roles if role.role == "primary_evidence"]
        policy_file_ids = [role.file_id for role in file_roles if role.role == "policy_reference"]
        conflict_file_ids = [role.file_id for role in file_roles if role.contains_conflict]
        missing_file_ids = [role.file_id for role in file_roles if role.contains_missing_fields]

        synthetic_artifacts: List[EvidenceDossierSyntheticArtifact] = []

        def add_artifact(
            role: EvidenceDossierRole,
            title: str,
            description: str,
            linked_file_ids: List[str],
            reason_codes: List[str],
            candidate_visible: bool = True,
        ) -> None:
            artifact = EvidenceDossierSyntheticArtifact(
                artifact_id=self._stable_id("dos_artifact", [blueprint.blueprint_id, role, title]),
                role=role,
                title=title,
                candidate_visible=candidate_visible,
                description=description,
                linked_file_ids=linked_file_ids,
                reason_codes=reason_codes,
            )
            if artifact.artifact_id not in {item.artifact_id for item in synthetic_artifacts}:
                synthetic_artifacts.append(artifact)

        manager_context_signals = {
            "manager",
            "leadership",
            "executive",
            "cfo",
            "controller",
        }
        escalation_signals = {
            "escalate",
            "escalation",
            "approval",
            "approve",
            "reviewthread",
            "review_thread",
            "managernotes",
            "managernotes",
            "manageremail",
            "manager_email",
            "followuprequired",
        }
        has_explicit_manager_context = bool(context_tokens & manager_context_signals)
        has_explicit_escalation_signal = bool(context_tokens & escalation_signals)
        if has_explicit_manager_context and has_explicit_escalation_signal:
            add_artifact(
                role="manager_notes",
                title="Manager Review Notes Placeholder",
                description="The dossier implies a manager-facing note or review thread, but V1 keeps it as metadata only.",
                linked_file_ids=primary_file_ids[:2] or policy_file_ids[:1],
                reason_codes=["manager_facing_context"],
            )

        if missing_file_ids:
            add_artifact(
                role="missing_attachment",
                title="Missing Attachment Placeholder",
                description="The dossier should communicate that at least one supporting attachment is referenced or expected but absent from the visible file set.",
                linked_file_ids=missing_file_ids,
                reason_codes=["missing_support_signal", "metadata_only_gap"],
            )

        if conflict_file_ids or selected_motif in {"fan_in_reconciliation", "cross_check_validation"}:
            add_artifact(
                role="conflict_source",
                title="Conflict Source Placeholder",
                description="The dossier should preserve that one source may disagree with another and require reconciliation or validation.",
                linked_file_ids=conflict_file_ids or primary_file_ids[:2],
                reason_codes=["conflict_signal", f"motif:{selected_motif}"],
            )

        outdated_signals = {"prior", "old", "outdated", "archived", "legacy", "previous"}
        has_explicit_outdated_file = any(role.role == "outdated_version" for role in file_roles)
        if not has_explicit_outdated_file and context_tokens & outdated_signals:
            linked_file_ids = policy_file_ids[:1] or primary_file_ids[:1]
            if linked_file_ids:
                add_artifact(
                    role="outdated_version",
                    title="Outdated Version Placeholder",
                    description="The dossier may later include a prior version or stale copy that should not be treated as the governing source.",
                    linked_file_ids=linked_file_ids,
                    reason_codes=["version_ecology_signal", f"motif:{selected_motif}"],
                )

        if distractors:
            linked_file_ids = []
            for distractor in distractors:
                linked_file_ids.extend(distractor.linked_file_ids)
            add_artifact(
                role="distractor_source",
                title="Distractor Source Placeholder",
                description="The dossier reserves room for a low-signal or partially misleading supporting source without forcing V1 physical file generation.",
                linked_file_ids=list(dict.fromkeys(linked_file_ids))[:2],
                reason_codes=["distractor_metadata", f"distractor_count:{len(distractors)}"],
            )

        if constraints and selected_motif == "policy_application" and not policy_file_ids:
            add_artifact(
                role="policy_reference",
                title="Policy Reference Placeholder",
                description="The dossier contract expects a policy or rules source even if the current planned file set has not materialized it as a separate document.",
                linked_file_ids=primary_file_ids[:1],
                reason_codes=["policy_constraint_without_file"],
            )

        return synthetic_artifacts

    def _tokens(self, text: str) -> set[str]:
        return {token for token in "".join(char.lower() if char.isalnum() else " " for char in text).split() if token}

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        digest = sha1("::".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"
