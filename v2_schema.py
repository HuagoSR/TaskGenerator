import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SkillType = Literal["fact", "reasoning", "robustness", "compliance", "hybrid"]
DeliverableRole = Literal["source_data", "reference_table", "intermediate_artifact", "final_deliverable"]
TargetType = Literal["exact_or_tolerance_check", "binary_check", "reasoning_check", "reasoning_or_robustness_check"]


class SemanticPortContract(BaseModel):
    requires_semantics: List[str] = Field(default_factory=list)
    optional_semantics: List[str] = Field(default_factory=list)
    provides_semantics: List[str] = Field(default_factory=list)


class SemanticIntent(BaseModel):
    goal: str
    business_meaning: str
    hidden_difficulty: str


class UsagePriors(BaseModel):
    common_scenarios: List[str] = Field(default_factory=list)
    common_deliverables: List[str] = Field(default_factory=list)
    common_traps: List[str] = Field(default_factory=list)


class AssemblyHints(BaseModel):
    preferred_task_roles: List[str] = Field(default_factory=list)
    preferred_evidence: List[str] = Field(default_factory=list)
    suggested_intermediate_artifacts: List[str] = Field(default_factory=list)


class SemanticSkill(BaseModel):
    skill_id: str
    skill_name: str
    skill_type: SkillType
    version: str = "2.0"
    domain_tags: List[str] = Field(default_factory=list)
    capability_tags: List[str] = Field(default_factory=list)
    difficulty_tags: List[str] = Field(default_factory=list)
    input_contract: SemanticPortContract = Field(default_factory=SemanticPortContract)
    output_contract: SemanticPortContract = Field(default_factory=SemanticPortContract)
    semantic_intent: SemanticIntent
    usage_priors: UsagePriors = Field(default_factory=UsagePriors)
    assembly_hints: AssemblyHints = Field(default_factory=AssemblyHints)


class ColumnSpec(BaseModel):
    name: str
    semantic_type: str


class SheetSpec(BaseModel):
    sheet_name: str
    columns: List[ColumnSpec] = Field(default_factory=list)
    row_count_target: int


class FileSpec(BaseModel):
    file_name: str
    file_role: DeliverableRole
    sheet_specs: List[SheetSpec] = Field(default_factory=list)


class DataRelationship(BaseModel):
    relation_type: str
    left: str
    right: str


class InjectionTarget(BaseModel):
    file_name: str
    sheet_name: str
    columns: List[str] = Field(default_factory=list)


class InjectionPolicy(BaseModel):
    pattern: str
    severity: str
    affected_row_count: Optional[int] = None
    affected_entities: List[str] = Field(default_factory=list)


class TrapSpec(BaseModel):
    trap_id: str
    source_skill_id: str
    trap_type: str
    injection_target: InjectionTarget
    injection_policy: InjectionPolicy
    expected_solver_behavior: str


class DeliverableSpec(BaseModel):
    file_name: str
    file_role: DeliverableRole
    requirements: List[str] = Field(default_factory=list)


class PromptSpec(BaseModel):
    visible_requirements: List[str] = Field(default_factory=list)
    hidden_requirements: List[str] = Field(default_factory=list)
    style_constraints: List[str] = Field(default_factory=list)


class GoldenPlan(BaseModel):
    required_intermediate_states: List[str] = Field(default_factory=list)
    required_final_checks: List[str] = Field(default_factory=list)


class TaskMetadata(BaseModel):
    sector: str
    occupation: str
    scenario_title: str
    task_goal: str
    difficulty_level: str


class ScenarioSpec(BaseModel):
    role: str
    business_context: str
    time_context: str
    tone: str


class DataSpec(BaseModel):
    reference_files: List[FileSpec] = Field(default_factory=list)
    data_relationships: List[DataRelationship] = Field(default_factory=list)


class TaskBlueprint(BaseModel):
    blueprint_id: str
    template_family: str
    task_metadata: TaskMetadata
    selected_skills: List[str] = Field(default_factory=list)
    scenario_spec: ScenarioSpec
    data_spec: DataSpec
    trap_spec: List[TrapSpec] = Field(default_factory=list)
    deliverable_spec: List[DeliverableSpec] = Field(default_factory=list)
    prompt_spec: PromptSpec
    golden_plan: GoldenPlan


class CapabilityProfile(BaseModel):
    primary_capabilities: List[str] = Field(default_factory=list)
    secondary_capabilities: List[str] = Field(default_factory=list)


class SupervisionTarget(BaseModel):
    target_id: str
    target_type: TargetType
    description: str


class SupervisionTargets(BaseModel):
    final_outcomes: List[SupervisionTarget] = Field(default_factory=list)
    intermediate_outcomes: List[SupervisionTarget] = Field(default_factory=list)


class FailureMode(BaseModel):
    failure_id: str
    description: str


class RubricProjection(BaseModel):
    fact_checks: List[str] = Field(default_factory=list)
    reasoning_checks: List[str] = Field(default_factory=list)
    robustness_checks: List[str] = Field(default_factory=list)
    compliance_checks: List[str] = Field(default_factory=list)


class TrainingAnnotation(BaseModel):
    annotation_id: str
    blueprint_id: str
    capability_profile: CapabilityProfile
    supervision_targets: SupervisionTargets
    failure_modes: List[FailureMode] = Field(default_factory=list)
    rubric_projection: RubricProjection


class V2DatasetPackage(BaseModel):
    task_id: str
    prompt: str
    reference_files: List[str] = Field(default_factory=list)
    deliverable_files: List[str] = Field(default_factory=list)
    rubric: str
    rubric_json: str
    extra: Dict[str, Any] = Field(default_factory=dict)


def dump_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def dump_json_file(model: BaseModel, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump_json(model))


def load_semantic_skills(path: str) -> List[SemanticSkill]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return [SemanticSkill.model_validate(item) for item in payload]
