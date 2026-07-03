import json
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from task_generator.v2_schema import TaskBlueprint
from task_generator.v3_pipeline_b_prototype import DEFAULT_MOTIF_PRIORITY
from task_generator.v3_pipeline_b_quality_gate import PipelineBQualityReport
from task_generator.v3_reference_file_generator import GeneratedFileManifest
from task_generator.v3_reference_file_planner import ReferenceFilePlan
from task_generator.v3_rubric_builder import RubricArtifact
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_teacher_input_builder import TeacherInputManifest
from task_generator.v3_teacher_runner import GoldenRun


RecommendedNextLayer = Literal["pipeline_a", "workflow_graph", "package_generation", "validity_feedback"]
RecommendationLabel = Literal["revise", "diagnostic_only", "promising_but_non_binding"]
NodeType = Literal[
    "reference_file",
    "evidence_item",
    "deliverable_section",
    "intermediate_artifact",
    "skill_step",
    "relationship",
]
EdgeType = Literal["provides", "supports", "must_cite", "derived_from", "validates"]
GraphShape = Literal["chain", "dag", "constraint_graph"]


class GlobalTaskValidityRequest(BaseModel):
    blueprint_path: str
    reference_file_plan_path: str
    generated_file_manifest_path: str
    teacher_input_manifest_path: str
    golden_run_path: str
    rubric_path: str
    quality_report_path: str
    prototype_report_path: Optional[str] = None
    subgraph_report_path: Optional[str] = None
    output_dir: str


class TaskConstraintGraphNode(BaseModel):
    node_id: str
    node_type: NodeType
    label: str
    source_ref: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskConstraintGraphEdge(BaseModel):
    edge_id: str
    edge_type: EdgeType
    from_node_id: str
    to_node_id: str
    reason: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskConstraintGraphReport(BaseModel):
    task_constraint_graph_version: str = "v3.task_constraint_graph.1"
    blueprint_id: str
    task_constraint_graph_id: str
    nodes: List[TaskConstraintGraphNode] = Field(default_factory=list)
    edges: List[TaskConstraintGraphEdge] = Field(default_factory=list)
    graph_shape: GraphShape = "chain"
    unsupported_required_nodes: List[str] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ExecutionPlanStage(BaseModel):
    stage_id: str
    stage_name: str
    depends_on: List[str] = Field(default_factory=list)
    source_ref: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionPlanDAGReport(BaseModel):
    execution_plan_dag_version: str = "v3.execution_plan_dag.1"
    blueprint_id: str
    execution_plan_id: str
    stages: List[ExecutionPlanStage] = Field(default_factory=list)
    dag_valid: bool = True
    topological_order: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    validation_notes: List[str] = Field(default_factory=list)


class RealWorldnessDimensions(BaseModel):
    business_context_plausibility: float = 0.0
    artifact_ecology_realism: float = 0.0
    evidence_noise_and_conflict: float = 0.0
    decision_consequence: float = 0.0
    deliverable_realism: float = 0.0
    anti_template_score: float = 0.0


class RealWorldnessReport(BaseModel):
    real_worldness_version: str = "v3.real_worldness.1"
    blueprint_id: str
    real_worldness_score: float = 0.0
    dimensions: RealWorldnessDimensions = Field(default_factory=RealWorldnessDimensions)
    findings: List[str] = Field(default_factory=list)
    recommendation: RecommendationLabel = "diagnostic_only"
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class DifficultyAxes(BaseModel):
    evidence_retrieval: int = 0
    cross_file_reasoning: int = 0
    numerical_reasoning: int = 0
    policy_application: int = 0
    ambiguity_management: int = 0
    deliverable_complexity: int = 0
    robustness_requirement: int = 0


class DifficultyProfileReport(BaseModel):
    difficulty_profile_version: str = "v3.difficulty_profile.1"
    blueprint_id: str
    difficulty_axes: DifficultyAxes = Field(default_factory=DifficultyAxes)
    overall_difficulty: float = 0.0
    findings: List[str] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class GlobalTaskValidityReport(BaseModel):
    global_task_validity_version: str = "v3.global_task_validity.1"
    blueprint_id: str
    case_id: str
    diagnostic_only: bool = True
    real_worldness: RealWorldnessReport
    difficulty_profile: DifficultyProfileReport
    task_constraint_graph: TaskConstraintGraphReport
    execution_plan_dag: ExecutionPlanDAGReport
    artifact_errors: List[str] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    recommended_next_layer: RecommendedNextLayer = "validity_feedback"
    notes: List[str] = Field(default_factory=list)


class GlobalTaskValidityBuilder:
    """Build report-only global validity diagnostics from existing Pipeline B artifacts."""

    def build(
        self,
        blueprint_path: str | Path,
        reference_file_plan_path: str | Path,
        generated_file_manifest_path: str | Path,
        teacher_input_manifest_path: str | Path,
        golden_run_path: str | Path,
        rubric_path: str | Path,
        quality_report_path: str | Path,
        output_dir: str | Path,
        prototype_report_path: Optional[str | Path] = None,
        subgraph_report_path: Optional[str | Path] = None,
    ) -> Tuple[
        GlobalTaskValidityReport,
        RealWorldnessReport,
        DifficultyProfileReport,
        TaskConstraintGraphReport,
        ExecutionPlanDAGReport,
    ]:
        request = GlobalTaskValidityRequest(
            blueprint_path=str(blueprint_path),
            reference_file_plan_path=str(reference_file_plan_path),
            generated_file_manifest_path=str(generated_file_manifest_path),
            teacher_input_manifest_path=str(teacher_input_manifest_path),
            golden_run_path=str(golden_run_path),
            rubric_path=str(rubric_path),
            quality_report_path=str(quality_report_path),
            prototype_report_path=str(prototype_report_path) if prototype_report_path else None,
            subgraph_report_path=str(subgraph_report_path) if subgraph_report_path else None,
            output_dir=str(output_dir),
        )

        artifact_errors: List[str] = []
        blueprint = self._load_model(blueprint_path, TaskBlueprint, artifact_errors, "blueprint")
        reference_plan = self._load_model(
            reference_file_plan_path,
            ReferenceFilePlan,
            artifact_errors,
            "reference_file_plan",
        )
        generated_manifest = self._load_model(
            generated_file_manifest_path,
            GeneratedFileManifest,
            artifact_errors,
            "generated_file_manifest",
        )
        teacher_input = self._load_model(
            teacher_input_manifest_path,
            TeacherInputManifest,
            artifact_errors,
            "teacher_input_manifest",
        )
        golden_run = self._load_model(golden_run_path, GoldenRun, artifact_errors, "golden_run")
        rubric = self._load_model(rubric_path, RubricArtifact, artifact_errors, "rubric")
        quality_report = self._load_model(
            quality_report_path,
            PipelineBQualityReport,
            artifact_errors,
            "quality_report",
        )
        prototype_report = self._load_optional_json(prototype_report_path, artifact_errors, "prototype_report")
        subgraph_report = self._load_optional_json(subgraph_report_path, artifact_errors, "subgraph_report")

        blueprint_id = blueprint.blueprint_id if blueprint else "unknown"
        case_id = self._infer_case_id(output_dir, blueprint_id)

        task_constraint_graph = self._task_constraint_graph(
            blueprint=blueprint,
            reference_plan=reference_plan,
            generated_manifest=generated_manifest,
            teacher_input=teacher_input,
            rubric=rubric,
        )
        execution_plan_dag = self._execution_plan_dag(
            blueprint_id=blueprint_id,
            teacher_input=teacher_input,
            golden_run=golden_run,
        )
        real_worldness = self._real_worldness(
            blueprint=blueprint,
            reference_plan=reference_plan,
            generated_manifest=generated_manifest,
            teacher_input=teacher_input,
            golden_run=golden_run,
            quality_report=quality_report,
            task_constraint_graph=task_constraint_graph,
        )
        difficulty_profile = self._difficulty_profile(
            blueprint=blueprint,
            reference_plan=reference_plan,
            generated_manifest=generated_manifest,
            teacher_input=teacher_input,
            golden_run=golden_run,
            rubric=rubric,
            quality_report=quality_report,
            task_constraint_graph=task_constraint_graph,
            prototype_report=prototype_report,
            subgraph_report=subgraph_report,
        )
        findings = self._findings(
            artifact_errors=artifact_errors,
            real_worldness=real_worldness,
            difficulty=difficulty_profile,
            task_constraint_graph=task_constraint_graph,
            execution_plan_dag=execution_plan_dag,
            quality_report=quality_report,
        )
        recommended_next_layer = self._recommended_next_layer(
            artifact_errors=artifact_errors,
            real_worldness=real_worldness,
            task_constraint_graph=task_constraint_graph,
            execution_plan_dag=execution_plan_dag,
            quality_report=quality_report,
        )

        global_report = GlobalTaskValidityReport(
            blueprint_id=blueprint_id,
            case_id=case_id,
            diagnostic_only=True,
            real_worldness=real_worldness,
            difficulty_profile=difficulty_profile,
            task_constraint_graph=task_constraint_graph,
            execution_plan_dag=execution_plan_dag,
            artifact_errors=artifact_errors,
            findings=findings,
            recommended_next_layer=recommended_next_layer,
            notes=[
                "This report is diagnostic-only and does not change quality-gate, package, export, or sampler behavior.",
                "Heuristics are intentionally simple and deterministic in V1.",
                "Use this report to decide whether the next fix belongs in Pipeline A, workflow graph design, package generation, or validity/feedback.",
            ],
        )

        return (
            global_report,
            real_worldness,
            difficulty_profile,
            task_constraint_graph,
            execution_plan_dag,
        )

    def write_outputs(
        self,
        global_report: GlobalTaskValidityReport,
        real_worldness: RealWorldnessReport,
        difficulty_profile: DifficultyProfileReport,
        task_constraint_graph: TaskConstraintGraphReport,
        execution_plan_dag: ExecutionPlanDAGReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        global_path = output_path / "global_task_validity_report.json"
        real_path = output_path / "real_worldness_report.json"
        difficulty_path = output_path / "difficulty_profile_report.json"
        graph_path = output_path / "task_constraint_graph_report.json"
        dag_path = output_path / "execution_plan_dag_report.json"
        global_path.write_text(global_report.model_dump_json(indent=2), encoding="utf-8")
        real_path.write_text(real_worldness.model_dump_json(indent=2), encoding="utf-8")
        difficulty_path.write_text(difficulty_profile.model_dump_json(indent=2), encoding="utf-8")
        graph_path.write_text(task_constraint_graph.model_dump_json(indent=2), encoding="utf-8")
        dag_path.write_text(execution_plan_dag.model_dump_json(indent=2), encoding="utf-8")
        return {
            "global_task_validity_report_path": str(global_path),
            "real_worldness_report_path": str(real_path),
            "difficulty_profile_report_path": str(difficulty_path),
            "task_constraint_graph_report_path": str(graph_path),
            "execution_plan_dag_report_path": str(dag_path),
        }

    def _load_model(self, path: str | Path, model_type, errors: List[str], label: str):
        try:
            return model_type.model_validate(load_json_file(str(path)))
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{path}")
            return None

    def _load_optional_json(
        self,
        path: Optional[str | Path],
        errors: List[str],
        label: str,
    ) -> Optional[Dict[str, Any]]:
        if not path:
            return None
        try:
            return load_json_file(str(path))
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{path}")
            return None

    def _infer_case_id(self, output_dir: str | Path, blueprint_id: str) -> str:
        output_path = Path(output_dir)
        if output_path.name == "global_validity" and output_path.parent.name:
            return output_path.parent.name
        if output_path.parent.name:
            return output_path.parent.name
        return blueprint_id

    def _task_constraint_graph(
        self,
        blueprint: Optional[TaskBlueprint],
        reference_plan: Optional[ReferenceFilePlan],
        generated_manifest: Optional[GeneratedFileManifest],
        teacher_input: Optional[TeacherInputManifest],
        rubric: Optional[RubricArtifact],
    ) -> TaskConstraintGraphReport:
        blueprint_id = blueprint.blueprint_id if blueprint else "unknown"
        nodes: List[TaskConstraintGraphNode] = []
        edges: List[TaskConstraintGraphEdge] = []
        unsupported_required_nodes: List[str] = []

        file_node_ids: List[str] = []
        evidence_node_ids: List[str] = []
        intermediate_node_ids: List[str] = []
        deliverable_node_ids: List[str] = []
        skill_node_ids: List[str] = []

        file_id_by_name: Dict[str, str] = {}
        evidence_ids_by_file: Dict[str, List[str]] = {}
        intermediate_node_id_by_name: Dict[str, str] = {}

        if reference_plan:
            for planned_file in reference_plan.planned_files:
                node_id = self._stable_id("node_file", [blueprint_id, planned_file.file_id])
                file_id_by_name[planned_file.file_name] = node_id
                file_node_ids.append(node_id)
                nodes.append(
                    TaskConstraintGraphNode(
                        node_id=node_id,
                        node_type="reference_file",
                        label=planned_file.file_name,
                        source_ref=f"reference_file_plan:{planned_file.file_id}",
                        metadata={
                            "file_role": planned_file.file_role,
                            "file_format": planned_file.file_format,
                            "candidate_visible": planned_file.candidate_visible,
                        },
                    )
                )
                for anchor in planned_file.evidence_anchors:
                    ev_node_id = self._stable_id("node_evidence", [blueprint_id, anchor.evidence_id])
                    evidence_node_ids.append(ev_node_id)
                    evidence_ids_by_file.setdefault(planned_file.file_name, []).append(ev_node_id)
                    nodes.append(
                        TaskConstraintGraphNode(
                            node_id=ev_node_id,
                            node_type="evidence_item",
                            label=anchor.evidence_id,
                            source_ref=f"reference_file_plan:{anchor.evidence_id}",
                            metadata={
                                "file_name": planned_file.file_name,
                                "locator": anchor.locator,
                                "semantic_type": anchor.semantic_type,
                                "visibility": anchor.visibility,
                            },
                        )
                    )
                    edges.append(
                        TaskConstraintGraphEdge(
                            edge_id=self._stable_id("edge", [node_id, ev_node_id, "provides"]),
                            edge_type="provides",
                            from_node_id=node_id,
                            to_node_id=ev_node_id,
                            reason="planned_file_contains_evidence_anchor",
                        )
                    )

        if generated_manifest and not evidence_node_ids:
            for mapping in generated_manifest.evidence_index:
                ev_node_id = self._stable_id("node_evidence", [blueprint_id, mapping.evidence_id])
                evidence_node_ids.append(ev_node_id)
                evidence_ids_by_file.setdefault(mapping.file_name, []).append(ev_node_id)
                nodes.append(
                    TaskConstraintGraphNode(
                        node_id=ev_node_id,
                        node_type="evidence_item",
                        label=mapping.evidence_id,
                        source_ref=f"generated_file_manifest:{mapping.evidence_id}",
                        metadata={
                            "file_name": mapping.file_name,
                            "locator": mapping.locator,
                            "semantic_type": mapping.semantic_type,
                        },
                    )
                )
                file_node_id = file_id_by_name.get(mapping.file_name)
                if file_node_id:
                    edges.append(
                        TaskConstraintGraphEdge(
                            edge_id=self._stable_id("edge", [file_node_id, ev_node_id, "provides"]),
                            edge_type="provides",
                            from_node_id=file_node_id,
                            to_node_id=ev_node_id,
                            reason="generated_manifest_evidence_mapping",
                        )
                    )

        if teacher_input:
            for state_name in teacher_input.teacher_view.required_intermediate_states:
                node_id = self._stable_id("node_state", [blueprint_id, state_name])
                intermediate_node_id_by_name[state_name] = node_id
                intermediate_node_ids.append(node_id)
                nodes.append(
                    TaskConstraintGraphNode(
                        node_id=node_id,
                        node_type="intermediate_artifact",
                        label=state_name,
                        source_ref=f"teacher_input:{state_name}",
                        metadata={"state_name": state_name},
                    )
                )

        if blueprint:
            for skill_id in blueprint.selected_skills:
                node_id = self._stable_id("node_skill", [blueprint_id, skill_id])
                skill_node_ids.append(node_id)
                nodes.append(
                    TaskConstraintGraphNode(
                        node_id=node_id,
                        node_type="skill_step",
                        label=skill_id,
                        source_ref=f"blueprint:selected_skill:{skill_id}",
                        metadata={"skill_id": skill_id},
                    )
                )
            for index, relationship in enumerate(blueprint.data_spec.data_relationships, start=1):
                rel_node_id = self._stable_id(
                    "node_rel",
                    [blueprint_id, relationship.relation_type, relationship.left, relationship.right, str(index)],
                )
                nodes.append(
                    TaskConstraintGraphNode(
                        node_id=rel_node_id,
                        node_type="relationship",
                        label=relationship.relation_type,
                        source_ref=f"blueprint:data_relationship:{index}",
                        metadata={"left": relationship.left, "right": relationship.right},
                    )
                )

        deliverable_requirements: List[Dict[str, Any]] = []
        if reference_plan:
            deliverable_requirements.extend(reference_plan.deliverable_expectations)
        elif blueprint:
            for deliverable in blueprint.deliverable_spec:
                deliverable_requirements.append(
                    {
                        "file_name": deliverable.file_name,
                        "file_role": deliverable.file_role,
                        "requirements": deliverable.requirements,
                    }
                )
        if rubric:
            rubric_candidate_count = 0
            for section in rubric.sections:
                for criterion in section.criteria:
                    if criterion.audience == "candidate" and criterion.export_to_rw_task:
                        rubric_candidate_count += 1
            if deliverable_requirements:
                deliverable_requirements[0]["rubric_candidate_criteria_count"] = rubric_candidate_count

        for deliverable in deliverable_requirements:
            for requirement in deliverable.get("requirements", []):
                node_id = self._stable_id(
                    "node_deliverable",
                    [blueprint_id, deliverable.get("file_name", ""), requirement],
                )
                deliverable_node_ids.append(node_id)
                nodes.append(
                    TaskConstraintGraphNode(
                        node_id=node_id,
                        node_type="deliverable_section",
                        label=requirement,
                        source_ref=f"deliverable:{deliverable.get('file_name', '')}",
                        metadata={
                            "file_name": deliverable.get("file_name"),
                            "file_role": deliverable.get("file_role"),
                        },
                    )
                )

        if file_node_ids and intermediate_node_ids:
            for file_name, file_node_id in file_id_by_name.items():
                for evidence_node_id in evidence_ids_by_file.get(file_name, []):
                    for state_name, state_node_id in intermediate_node_id_by_name.items():
                        if self._state_matches_evidence(state_name):
                            edges.append(
                                TaskConstraintGraphEdge(
                                    edge_id=self._stable_id(
                                        "edge",
                                        [evidence_node_id, state_node_id, "supports"],
                                    ),
                                    edge_type="supports",
                                    from_node_id=evidence_node_id,
                                    to_node_id=state_node_id,
                                    reason="evidence_supports_intermediate_state",
                                )
                            )

        if intermediate_node_ids and deliverable_node_ids:
            for state_node_id in intermediate_node_ids:
                for deliverable_node_id in deliverable_node_ids:
                    edges.append(
                        TaskConstraintGraphEdge(
                            edge_id=self._stable_id("edge", [state_node_id, deliverable_node_id, "supports"]),
                            edge_type="supports",
                            from_node_id=state_node_id,
                            to_node_id=deliverable_node_id,
                            reason="intermediate_state_supports_deliverable",
                        )
                    )

        if skill_node_ids and intermediate_node_ids:
            sorted_states = sorted(intermediate_node_id_by_name.items())
            for index, skill_node_id in enumerate(skill_node_ids):
                if sorted_states:
                    target_state_id = sorted_states[min(index, len(sorted_states) - 1)][1]
                    edges.append(
                        TaskConstraintGraphEdge(
                            edge_id=self._stable_id("edge", [skill_node_id, target_state_id, "provides"]),
                            edge_type="provides",
                            from_node_id=skill_node_id,
                            to_node_id=target_state_id,
                            reason="selected_skill_expected_to_provide_intermediate_state",
                        )
                    )

        if deliverable_node_ids and evidence_node_ids:
            for deliverable_node_id in deliverable_node_ids:
                for evidence_node_id in evidence_node_ids:
                    edges.append(
                        TaskConstraintGraphEdge(
                            edge_id=self._stable_id("edge", [deliverable_node_id, evidence_node_id, "must_cite"]),
                            edge_type="must_cite",
                            from_node_id=deliverable_node_id,
                            to_node_id=evidence_node_id,
                            reason="deliverable_should_remain_evidence_grounded",
                        )
                    )

        if reference_plan:
            for relationship in reference_plan.data_relationships:
                edge_type: EdgeType = (
                    "validates"
                    if any(token in relationship["relation_type"].lower() for token in ["validate", "check", "reconcile"])
                    else "derived_from"
                )
                left_node = self._find_best_relationship_target(relationship["left"], nodes)
                right_node = self._find_best_relationship_target(relationship["right"], nodes)
                if left_node and right_node:
                    edges.append(
                        TaskConstraintGraphEdge(
                            edge_id=self._stable_id(
                                "edge",
                                [left_node.node_id, right_node.node_id, edge_type, relationship["relation_type"]],
                            ),
                            edge_type=edge_type,
                            from_node_id=left_node.node_id,
                            to_node_id=right_node.node_id,
                            reason=relationship["relation_type"],
                        )
                    )

        if teacher_input:
            for state_name in teacher_input.teacher_view.required_intermediate_states:
                if state_name not in intermediate_node_id_by_name:
                    unsupported_required_nodes.append(f"intermediate_artifact:{state_name}")
            for check_name in teacher_input.teacher_view.required_final_checks:
                if not deliverable_node_ids:
                    unsupported_required_nodes.append(f"deliverable_section:{check_name}")

        graph_shape = self._graph_shape(edges)
        return TaskConstraintGraphReport(
            blueprint_id=blueprint_id,
            task_constraint_graph_id=self._stable_id("tcg", [blueprint_id]),
            nodes=nodes,
            edges=edges,
            graph_shape=graph_shape,
            unsupported_required_nodes=sorted(set(unsupported_required_nodes)),
            diagnostics={
                "reference_file_count": len(file_node_ids),
                "evidence_item_count": len(evidence_node_ids),
                "deliverable_section_count": len(deliverable_node_ids),
                "intermediate_artifact_count": len(intermediate_node_ids),
                "skill_step_count": len(skill_node_ids),
                "edge_count": len(edges),
            },
        )

    def _execution_plan_dag(
        self,
        blueprint_id: str,
        teacher_input: Optional[TeacherInputManifest],
        golden_run: Optional[GoldenRun],
    ) -> ExecutionPlanDAGReport:
        stages: List[ExecutionPlanStage] = []
        if teacher_input:
            for index, state_name in enumerate(teacher_input.teacher_view.required_intermediate_states, start=1):
                depends_on: List[str] = []
                if stages:
                    depends_on = [stages[-1].stage_id]
                stages.append(
                    ExecutionPlanStage(
                        stage_id=f"stage_{index:02d}",
                        stage_name=state_name,
                        depends_on=depends_on,
                        source_ref=f"teacher_input:{state_name}",
                    )
                )

        final_deliverable_stage_id = f"stage_{len(stages) + 1:02d}"
        stages.append(
            ExecutionPlanStage(
                stage_id=final_deliverable_stage_id,
                stage_name="final_deliverable",
                depends_on=[stage.stage_id for stage in stages],
                source_ref="derived:final_deliverable",
            )
        )

        if golden_run and golden_run.final_checks:
            stages.append(
                ExecutionPlanStage(
                    stage_id=f"stage_{len(stages) + 1:02d}",
                    stage_name="final_validation",
                    depends_on=[final_deliverable_stage_id],
                    source_ref="golden_run:final_checks",
                    metadata={"final_check_count": len(golden_run.final_checks)},
                )
            )

        dag_valid, topological_order, missing_inputs, validation_notes = self._validate_dag(stages)
        return ExecutionPlanDAGReport(
            blueprint_id=blueprint_id,
            execution_plan_id=self._stable_id("exec", [blueprint_id]),
            stages=stages,
            dag_valid=dag_valid,
            topological_order=topological_order,
            missing_inputs=missing_inputs,
            validation_notes=validation_notes,
        )

    def _real_worldness(
        self,
        blueprint: Optional[TaskBlueprint],
        reference_plan: Optional[ReferenceFilePlan],
        generated_manifest: Optional[GeneratedFileManifest],
        teacher_input: Optional[TeacherInputManifest],
        golden_run: Optional[GoldenRun],
        quality_report: Optional[PipelineBQualityReport],
        task_constraint_graph: TaskConstraintGraphReport,
    ) -> RealWorldnessReport:
        blueprint_id = blueprint.blueprint_id if blueprint else "unknown"
        dimensions = RealWorldnessDimensions(
            business_context_plausibility=self._business_context_plausibility(blueprint),
            artifact_ecology_realism=self._artifact_ecology_realism(reference_plan, generated_manifest, teacher_input),
            evidence_noise_and_conflict=self._evidence_noise_and_conflict(blueprint, golden_run, quality_report),
            decision_consequence=self._decision_consequence(blueprint),
            deliverable_realism=self._deliverable_realism(blueprint, reference_plan),
            anti_template_score=self._anti_template_score(blueprint, task_constraint_graph, teacher_input),
        )
        scores = [
            dimensions.business_context_plausibility,
            dimensions.artifact_ecology_realism,
            dimensions.evidence_noise_and_conflict,
            dimensions.decision_consequence,
            dimensions.deliverable_realism,
            dimensions.anti_template_score,
        ]
        score = round(sum(scores) / len(scores), 2)
        if score < 0.4:
            recommendation: RecommendationLabel = "revise"
        elif score < 0.7:
            recommendation = "diagnostic_only"
        else:
            recommendation = "promising_but_non_binding"

        findings: List[str] = []
        if dimensions.business_context_plausibility < 1.0:
            findings.append("Business context remains under-specified or weakly role-grounded.")
        if dimensions.artifact_ecology_realism < 0.5:
            findings.append("Artifact ecology still looks too thin for a realistic case package.")
        if dimensions.evidence_noise_and_conflict < 0.5:
            findings.append("Evidence package shows limited visible ambiguity, noise, or conflict.")
        if dimensions.anti_template_score < 0.5:
            findings.append("Task still risks feeling template-like rather than workflow-grounded.")

        return RealWorldnessReport(
            blueprint_id=blueprint_id,
            real_worldness_score=score,
            dimensions=dimensions,
            findings=findings,
            recommendation=recommendation,
            diagnostics={
                "candidate_file_count": len(teacher_input.candidate_view.reference_files) if teacher_input else 0,
                "deliverable_requirement_count": sum(
                    len(item.requirements) for item in blueprint.deliverable_spec
                )
                if blueprint
                else 0,
                "graph_shape": task_constraint_graph.graph_shape,
            },
        )

    def _difficulty_profile(
        self,
        blueprint: Optional[TaskBlueprint],
        reference_plan: Optional[ReferenceFilePlan],
        generated_manifest: Optional[GeneratedFileManifest],
        teacher_input: Optional[TeacherInputManifest],
        golden_run: Optional[GoldenRun],
        rubric: Optional[RubricArtifact],
        quality_report: Optional[PipelineBQualityReport],
        task_constraint_graph: TaskConstraintGraphReport,
        prototype_report: Optional[Dict[str, Any]],
        subgraph_report: Optional[Dict[str, Any]],
    ) -> DifficultyProfileReport:
        blueprint_id = blueprint.blueprint_id if blueprint else "unknown"
        evidence_anchor_count = sum(len(file.evidence_anchors) for file in reference_plan.planned_files) if reference_plan else 0
        candidate_file_count = len(teacher_input.candidate_view.reference_files) if teacher_input else 0
        graph_edge_count = len(task_constraint_graph.edges)
        xlsx_present = False
        if generated_manifest:
            xlsx_present = any(record.file_name.lower().endswith(".xlsx") for record in generated_manifest.generated_files)
        motif = None
        if subgraph_report:
            motif = subgraph_report.get("selected_motif") or subgraph_report.get("motif")
        elif prototype_report:
            motif = prototype_report.get("motif")
        else:
            motif = self._motif_from_blueprint(blueprint)

        axes = DifficultyAxes(
            evidence_retrieval=self._cap_score_from_count(evidence_anchor_count, (3, 8)),
            cross_file_reasoning=self._cap_score_from_count(candidate_file_count + graph_edge_count, (4, 9)),
            numerical_reasoning=self._numerical_reasoning_score(
                xlsx_present=xlsx_present,
                reference_plan=reference_plan,
                task_constraint_graph=task_constraint_graph,
            ),
            policy_application=self._policy_application_score(
                motif=motif,
                generated_manifest=generated_manifest,
                rubric=rubric,
            ),
            ambiguity_management=self._ambiguity_management_score(blueprint, teacher_input, golden_run, quality_report),
            deliverable_complexity=self._deliverable_complexity_score(blueprint, reference_plan),
            robustness_requirement=self._robustness_requirement_score(blueprint, golden_run, rubric),
        )
        values = [
            axes.evidence_retrieval,
            axes.cross_file_reasoning,
            axes.numerical_reasoning,
            axes.policy_application,
            axes.ambiguity_management,
            axes.deliverable_complexity,
            axes.robustness_requirement,
        ]
        overall = round(sum(values) / len(values), 2)

        findings: List[str] = []
        if axes.cross_file_reasoning <= 1:
            findings.append("Cross-file reasoning burden remains light.")
        if axes.ambiguity_management <= 1:
            findings.append("Ambiguity management pressure remains limited.")
        if axes.robustness_requirement <= 1:
            findings.append("Robustness requirements are still relatively shallow.")

        return DifficultyProfileReport(
            blueprint_id=blueprint_id,
            difficulty_axes=axes,
            overall_difficulty=overall,
            findings=findings,
            diagnostics={
                "evidence_anchor_count": evidence_anchor_count,
                "candidate_file_count": candidate_file_count,
                "graph_edge_count": graph_edge_count,
                "detected_motif": motif,
            },
        )

    def _findings(
        self,
        artifact_errors: List[str],
        real_worldness: RealWorldnessReport,
        difficulty: DifficultyProfileReport,
        task_constraint_graph: TaskConstraintGraphReport,
        execution_plan_dag: ExecutionPlanDAGReport,
        quality_report: Optional[PipelineBQualityReport],
    ) -> List[str]:
        findings: List[str] = []
        if artifact_errors:
            findings.append("One or more upstream artifacts were unreadable; diagnostic confidence is reduced.")
        findings.extend(real_worldness.findings)
        findings.extend(difficulty.findings)
        if task_constraint_graph.unsupported_required_nodes:
            findings.append("Some required graph nodes could not be grounded in current artifacts.")
        if not execution_plan_dag.dag_valid:
            findings.append("Execution plan DAG validation failed.")
        if quality_report and quality_report.decision.reason_codes:
            findings.append(
                "Current quality-gate reason codes remain visible: "
                + ", ".join(sorted(set(quality_report.decision.reason_codes[:5])))
            )
        return findings

    def _recommended_next_layer(
        self,
        artifact_errors: List[str],
        real_worldness: RealWorldnessReport,
        task_constraint_graph: TaskConstraintGraphReport,
        execution_plan_dag: ExecutionPlanDAGReport,
        quality_report: Optional[PipelineBQualityReport],
    ) -> RecommendedNextLayer:
        reason_codes = set(quality_report.decision.reason_codes) if quality_report else set()
        if reason_codes.intersection({"low_subgraph_confidence", "single_source_support", "pipeline_a_signal_gaps"}):
            return "pipeline_a"
        if artifact_errors or task_constraint_graph.unsupported_required_nodes or not execution_plan_dag.dag_valid:
            return "package_generation"
        if real_worldness.dimensions.business_context_plausibility < 0.5 or real_worldness.dimensions.anti_template_score < 0.5:
            return "workflow_graph"
        return "validity_feedback"

    def _business_context_plausibility(self, blueprint: Optional[TaskBlueprint]) -> float:
        if not blueprint:
            return 0.0
        has_role = bool(blueprint.scenario_spec.role.strip())
        has_context = bool(blueprint.scenario_spec.business_context.strip())
        has_title = bool(blueprint.task_metadata.scenario_title.strip())
        requirement_count = sum(len(deliverable.requirements) for deliverable in blueprint.deliverable_spec)
        if has_role and has_context and has_title and requirement_count > 0:
            return 1.0
        if sum([has_role, has_context, has_title]) >= 2:
            return 0.5
        return 0.0

    def _artifact_ecology_realism(
        self,
        reference_plan: Optional[ReferenceFilePlan],
        generated_manifest: Optional[GeneratedFileManifest],
        teacher_input: Optional[TeacherInputManifest],
    ) -> float:
        candidate_files = teacher_input.candidate_view.reference_files if teacher_input else []
        visible_count = len(candidate_files)
        file_roles = {
            file_view.file_role
            for file_view in candidate_files
            if getattr(file_view, "file_role", None)
        }
        structured_present = False
        explanatory_present = False
        if generated_manifest:
            for record in generated_manifest.generated_files:
                lower = record.file_name.lower()
                if lower.endswith((".xlsx", ".csv", ".tsv")):
                    structured_present = True
                if lower.endswith((".docx", ".md", ".txt")):
                    explanatory_present = True
        if visible_count >= 2 and len(file_roles) >= 2 and structured_present and explanatory_present:
            return 1.0
        if visible_count >= 2 and (structured_present or explanatory_present):
            return 0.5
        if reference_plan and len(reference_plan.planned_files) >= 2:
            return 0.5
        return 0.0

    def _evidence_noise_and_conflict(
        self,
        blueprint: Optional[TaskBlueprint],
        golden_run: Optional[GoldenRun],
        quality_report: Optional[PipelineBQualityReport],
    ) -> float:
        trap_count = len(blueprint.trap_spec) if blueprint else 0
        unresolved_gaps = len(golden_run.unresolved_gaps) if golden_run else 0
        quality_codes = set(quality_report.decision.reason_codes) if quality_report else set()
        noisy = trap_count > 0 or unresolved_gaps > 0
        ambiguity_codes = {"single_source_support", "partial_intermediate_state", "pipeline_a_signal_gaps"}
        if noisy and quality_codes.intersection(ambiguity_codes):
            return 1.0
        if noisy or quality_codes.intersection(ambiguity_codes):
            return 0.5
        return 0.0

    def _decision_consequence(self, blueprint: Optional[TaskBlueprint]) -> float:
        if not blueprint:
            return 0.0
        text = " ".join(
            blueprint.prompt_spec.visible_requirements
            + [item for deliverable in blueprint.deliverable_spec for item in deliverable.requirements]
        ).lower()
        consequence_hits = [
            "conclusion",
            "exception",
            "unresolved",
            "follow-up",
            "manager",
            "memo",
            "review",
        ]
        hit_count = sum(1 for hit in consequence_hits if hit in text)
        if hit_count >= 4:
            return 1.0
        if hit_count >= 2:
            return 0.5
        return 0.0

    def _deliverable_realism(
        self,
        blueprint: Optional[TaskBlueprint],
        reference_plan: Optional[ReferenceFilePlan],
    ) -> float:
        deliverables = blueprint.deliverable_spec if blueprint else []
        if not deliverables:
            return 0.0
        realistic_role = any(
            any(token in deliverable.file_name.lower() for token in ["memo", "workpaper", "report", "review"])
            or "final_deliverable" in str(deliverable.file_role)
            for deliverable in deliverables
        )
        requirement_count = sum(len(deliverable.requirements) for deliverable in deliverables)
        if realistic_role and requirement_count >= 2:
            return 1.0
        if realistic_role or requirement_count >= 1:
            return 0.5
        if reference_plan and reference_plan.deliverable_expectations:
            return 0.5
        return 0.0

    def _anti_template_score(
        self,
        blueprint: Optional[TaskBlueprint],
        task_constraint_graph: TaskConstraintGraphReport,
        teacher_input: Optional[TeacherInputManifest],
    ) -> float:
        file_count = len(teacher_input.candidate_view.reference_files) if teacher_input else 0
        relationship_count = len(blueprint.data_spec.data_relationships) if blueprint else 0
        state_count = len(teacher_input.teacher_view.required_intermediate_states) if teacher_input else 0
        if file_count >= 2 and relationship_count >= 1 and state_count >= 3:
            return 1.0
        if file_count >= 2 and (relationship_count >= 1 or task_constraint_graph.graph_shape != "chain"):
            return 0.5
        return 0.0

    def _cap_score_from_count(self, count: int, thresholds: Tuple[int, int]) -> int:
        low, high = thresholds
        if count >= high:
            return 3
        if count >= low:
            return 2
        if count > 0:
            return 1
        return 0

    def _numerical_reasoning_score(
        self,
        xlsx_present: bool,
        reference_plan: Optional[ReferenceFilePlan],
        task_constraint_graph: TaskConstraintGraphReport,
    ) -> int:
        if not xlsx_present and not reference_plan:
            return 0
        table_count = sum(len(file.tables) for file in reference_plan.planned_files) if reference_plan else 0
        monetary_signal = any(
            "monetary" in json.dumps(node.metadata).lower() or "reconciliation" in json.dumps(node.metadata).lower()
            for node in task_constraint_graph.nodes
        )
        if xlsx_present and table_count >= 1 and monetary_signal:
            return 3
        if xlsx_present and table_count >= 1:
            return 2
        if xlsx_present:
            return 1
        return 0

    def _policy_application_score(
        self,
        motif: Optional[str],
        generated_manifest: Optional[GeneratedFileManifest],
        rubric: Optional[RubricArtifact],
    ) -> int:
        policy_locator = False
        if generated_manifest:
            policy_locator = any(
                "pol-" in mapping.locator.lower() or "policy" in mapping.semantic_type.lower()
                for mapping in generated_manifest.evidence_index
            )
        rubric_policy = False
        if rubric:
            rubric_policy = any(
                any(
                    "policy" in requirement.get("semantic_type", "").lower()
                    or "pol-" in requirement.get("locator", "").lower()
                    for requirement in criterion.evidence_requirements
                )
                for section in rubric.sections
                for criterion in section.criteria
            )
        if motif == "policy_application" and (policy_locator or rubric_policy):
            return 3
        if motif == "policy_application" or policy_locator or rubric_policy:
            return 2
        return 0

    def _ambiguity_management_score(
        self,
        blueprint: Optional[TaskBlueprint],
        teacher_input: Optional[TeacherInputManifest],
        golden_run: Optional[GoldenRun],
        quality_report: Optional[PipelineBQualityReport],
    ) -> int:
        trap_count = len(blueprint.trap_spec) if blueprint else 0
        missing_signal_count = len(teacher_input.teacher_view.missing_or_weak_pipeline_a_signals) if teacher_input else 0
        unresolved_gap_count = len(golden_run.unresolved_gaps) if golden_run else 0
        quality_codes = set(quality_report.decision.reason_codes) if quality_report else set()
        if trap_count >= 1 and unresolved_gap_count >= 1 and quality_codes:
            return 3
        if trap_count >= 1 or unresolved_gap_count >= 1 or missing_signal_count >= 1:
            return 2
        if quality_codes.intersection({"single_source_support", "pipeline_a_signal_gaps"}):
            return 1
        return 0

    def _deliverable_complexity_score(
        self,
        blueprint: Optional[TaskBlueprint],
        reference_plan: Optional[ReferenceFilePlan],
    ) -> int:
        requirement_count = sum(len(deliverable.requirements) for deliverable in blueprint.deliverable_spec) if blueprint else 0
        section_count = sum(len(file.text_sections) for file in reference_plan.planned_files) if reference_plan else 0
        if requirement_count >= 6 or section_count >= 4:
            return 3
        if requirement_count >= 3 or section_count >= 2:
            return 2
        if requirement_count >= 1:
            return 1
        return 0

    def _robustness_requirement_score(
        self,
        blueprint: Optional[TaskBlueprint],
        golden_run: Optional[GoldenRun],
        rubric: Optional[RubricArtifact],
    ) -> int:
        trap_count = len(blueprint.trap_spec) if blueprint else 0
        final_check_count = len(golden_run.final_checks) if golden_run else 0
        criterion_count = sum(len(section.criteria) for section in rubric.sections) if rubric else 0
        if trap_count >= 2 or (final_check_count >= 5 and criterion_count >= 20):
            return 3
        if trap_count >= 1 or (final_check_count >= 3 and criterion_count >= 10):
            return 2
        if final_check_count > 0 or criterion_count > 0:
            return 1
        return 0

    def _motif_from_blueprint(self, blueprint: Optional[TaskBlueprint]) -> Optional[str]:
        if not blueprint:
            return None
        template_family = blueprint.template_family.lower()
        for motif in DEFAULT_MOTIF_PRIORITY:
            if motif.replace("_", "") in template_family.replace("_", ""):
                return motif
        return None

    def _state_matches_evidence(self, state_name: str) -> bool:
        return any(
            token in state_name.lower()
            for token in ["evidence", "policy", "conclusion", "exception", "deliverable", "map", "outline"]
        )

    def _find_best_relationship_target(
        self,
        label: str,
        nodes: List[TaskConstraintGraphNode],
    ) -> Optional[TaskConstraintGraphNode]:
        label_lower = label.lower()
        for node in nodes:
            if label_lower and label_lower in node.label.lower():
                return node
        for node in nodes:
            source_text = node.source_ref.lower()
            if label_lower and label_lower in source_text:
                return node
        return None

    def _graph_shape(self, edges: List[TaskConstraintGraphEdge]) -> GraphShape:
        if not edges:
            return "chain"
        outgoing: Dict[str, int] = {}
        incoming: Dict[str, int] = {}
        must_cite_or_validate = 0
        for edge in edges:
            outgoing[edge.from_node_id] = outgoing.get(edge.from_node_id, 0) + 1
            incoming[edge.to_node_id] = incoming.get(edge.to_node_id, 0) + 1
            if edge.edge_type in {"must_cite", "validates"}:
                must_cite_or_validate += 1
        if must_cite_or_validate >= 3:
            return "constraint_graph"
        if any(count > 1 for count in incoming.values()) or any(count > 1 for count in outgoing.values()):
            return "dag"
        return "chain"

    def _validate_dag(
        self,
        stages: List[ExecutionPlanStage],
    ) -> Tuple[bool, List[str], List[str], List[str]]:
        validation_notes: List[str] = []
        missing_inputs: List[str] = []
        ids = [stage.stage_id for stage in stages]
        if len(ids) != len(set(ids)):
            validation_notes.append("duplicate_stage_id")
        graph = {stage.stage_id: list(stage.depends_on) for stage in stages}
        for stage in stages:
            if stage.stage_id in stage.depends_on:
                validation_notes.append(f"self_cycle:{stage.stage_id}")
            for dep in stage.depends_on:
                if dep not in graph:
                    missing_inputs.append(dep)

        in_degree = {stage_id: 0 for stage_id in graph}
        for deps in graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] = in_degree.get(dep, 0)
        reverse_adj: Dict[str, List[str]] = {stage_id: [] for stage_id in graph}
        for stage_id, deps in graph.items():
            in_degree[stage_id] = len([dep for dep in deps if dep in graph])
            for dep in deps:
                if dep in reverse_adj:
                    reverse_adj[dep].append(stage_id)

        queue = [stage_id for stage_id, degree in in_degree.items() if degree == 0]
        order: List[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            for follower in reverse_adj.get(current, []):
                in_degree[follower] -= 1
                if in_degree[follower] == 0:
                    queue.append(follower)

        dag_valid = len(order) == len(graph) and not validation_notes and not missing_inputs
        if len(order) != len(graph):
            validation_notes.append("cycle_or_unresolved_dependency_detected")
        return dag_valid, order, sorted(set(missing_inputs)), validation_notes

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        key = "||".join(parts)
        return f"{prefix}_{sha1(key.encode('utf-8')).hexdigest()[:10]}"
