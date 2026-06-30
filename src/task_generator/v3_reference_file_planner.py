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
    candidate_visible: bool = True
    linked_resource_ids: List[str] = Field(default_factory=list)
    generator_notes: List[str] = Field(default_factory=list)


class EvidenceAnchor(BaseModel):
    evidence_id: str
    file_id: str
    locator: str
    visibility: EvidenceVisibility = "candidate_visible"
    semantic_type: str
    linked_skill_ids: List[str] = Field(default_factory=list)
    linked_resource_ids: List[str] = Field(default_factory=list)
    provenance_notes: List[str] = Field(default_factory=list)


class PlannedReferenceFile(BaseModel):
    file_id: str
    file_name: str
    file_role: str
    file_format: str
    generator_status: GeneratorStatus
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
                    locator=f"{file_spec.file_name}:{section.heading}",
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
        if file_format in {"md", "txt"}:
            return "ready_for_deterministic_generation"
        return "needs_template_design"

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

    def _tokens(self, text: str) -> set[str]:
        return {token for token in "".join(char.lower() if char.isalnum() else " " for char in text).split() if token}

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        digest = sha1("::".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"
