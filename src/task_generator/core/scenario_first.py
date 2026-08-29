"""R10 Scenario-First contracts.

These contracts deliberately describe a teacher-only business world before any
candidate package exists.  They are report-only foundations: this module does
not fetch sources, call providers, materialize files, or mutate a registry.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AdmissionDecision = Literal["pass", "blocked"]
FactKnowledge = Literal["confirmed", "unresolved"]
FactKind = Literal[
    "organization", "role", "transaction", "timeline", "policy_application",
    "normal_background", "anomaly", "open_issue", "consequence", "treatment",
]
ArtifactFormat = Literal["xlsx", "csv", "pdf", "docx", "email", "txt"]
FindingCategory = Literal[
    "source_traceability", "world_consistency", "projection_integrity",
    "answer_leakage", "solvability", "decision_coverage", "isolation",
]


class ScenarioFirstModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def canonical_sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=False)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PublicSourceTraceV1(ScenarioFirstModel):
    source_id: str = Field(min_length=1)
    normalized_source_id: str = Field(min_length=1)
    block_ids: list[str] = Field(min_length=1)
    locator: str = Field(min_length=9)
    abstraction_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_https_locator(self) -> "PublicSourceTraceV1":
        if not self.locator.startswith("https://"):
            raise ValueError("public_source_locator_must_use_https")
        if len(set(self.block_ids)) != len(self.block_ids):
            raise ValueError("duplicate_source_block_id")
        return self


class WorkSeedV1(ScenarioFirstModel):
    contract_version: Literal["r10.work_seed.1"] = "r10.work_seed.1"
    seed_id: str = Field(min_length=1)
    domain: Literal["audit_compliance", "procurement_operations"]
    public_sources: list[PublicSourceTraceV1] = Field(min_length=1)
    role: str = Field(min_length=1)
    trigger_event: str = Field(min_length=1)
    business_goal: str = Field(min_length=1)
    typical_inputs: list[str] = Field(min_length=1)
    natural_questions: list[str] = Field(min_length=1)
    expected_deliverable: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    abstraction_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_sources(self) -> "WorkSeedV1":
        source_ids = [item.source_id for item in self.public_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate_work_seed_source_id")
        return self


class ProfessionalRuleV1(ScenarioFirstModel):
    rule_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_refs: list[PublicSourceTraceV1] = Field(min_length=1)
    applicability_conditions: list[str] = Field(min_length=1)
    evidence_requirements: list[str] = Field(min_length=1)
    exceptions: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str] = Field(min_length=1)
    acceptable_handling: list[str] = Field(min_length=1)


class ProfessionalRuleSetV1(ScenarioFirstModel):
    contract_version: Literal["r10.professional_rule_set.1"] = "r10.professional_rule_set.1"
    rule_set_id: str = Field(min_length=1)
    domain: Literal["audit_compliance", "procurement_operations"]
    rules: list[ProfessionalRuleV1] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_rules(self) -> "ProfessionalRuleSetV1":
        ids = [item.rule_id for item in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_professional_rule_id")
        return self


class ScenarioRoleV1(ScenarioFirstModel):
    role_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authorities: list[str] = Field(min_length=1)


class ScenarioFactV1(ScenarioFirstModel):
    fact_id: str = Field(min_length=1)
    kind: FactKind
    statement: str = Field(min_length=1)
    occurred_at: int = Field(ge=0)
    actor_role_id: str | None = None
    authority_required: str | None = None
    knowledge: FactKnowledge = "confirmed"
    rule_ids: list[str] = Field(default_factory=list)


class ScenarioBibleV1(ScenarioFirstModel):
    contract_version: Literal["r10.scenario_bible.1"] = "r10.scenario_bible.1"
    scenario_id: str = Field(min_length=1)
    work_seed_id: str = Field(min_length=1)
    rule_set_id: str = Field(min_length=1)
    organization_name: str = Field(min_length=1)
    roles: list[ScenarioRoleV1] = Field(min_length=1)
    facts: list[ScenarioFactV1] = Field(min_length=1)
    correct_treatments: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_bible_ids(self) -> "ScenarioBibleV1":
        role_ids = [item.role_id for item in self.roles]
        fact_ids = [item.fact_id for item in self.facts]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("duplicate_scenario_role_id")
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("duplicate_scenario_fact_id")
        return self


class ProjectedRecordV1(ScenarioFirstModel):
    record_id: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    values: dict[str, Any] = Field(min_length=1)
    record_class: Literal["normal", "decision_relevant"]


class EvidenceArtifactV1(ScenarioFirstModel):
    artifact_id: str = Field(min_length=1)
    business_purpose: str = Field(min_length=1)
    producer_role_id: str = Field(min_length=1)
    created_at: int = Field(ge=0)
    format: ArtifactFormat
    candidate_visible_fields: list[str] = Field(min_length=1)
    records: list[ProjectedRecordV1] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_artifact_records(self) -> "EvidenceArtifactV1":
        record_ids = [item.record_id for item in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("duplicate_projected_record_id")
        return self


class EvidenceProjectionPlanV1(ScenarioFirstModel):
    contract_version: Literal["r10.evidence_projection_plan.1"] = "r10.evidence_projection_plan.1"
    scenario_id: str = Field(min_length=1)
    artifacts: list[EvidenceArtifactV1] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_artifacts(self) -> "EvidenceProjectionPlanV1":
        artifact_ids = [item.artifact_id for item in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("duplicate_evidence_artifact_id")
        return self


class CandidateEvidenceRefV1(ScenarioFirstModel):
    artifact_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    field_names: list[str] = Field(min_length=1)


class DecisionPointV1(ScenarioFirstModel):
    decision_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    evidence_refs: list[CandidateEvidenceRefV1] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    skill_ids: list[str] = Field(min_length=1)
    acceptable_conclusions: list[str] = Field(min_length=1)
    major_errors: list[str] = Field(min_length=1)
    allowed_uncertainty_conclusions: list[str] = Field(default_factory=list)
    required_follow_up_actions: list[str] = Field(min_length=1)


class TaskDecisionMatrixV1(ScenarioFirstModel):
    contract_version: Literal["r10.task_decision_matrix.1"] = "r10.task_decision_matrix.1"
    scenario_id: str = Field(min_length=1)
    decision_points: list[DecisionPointV1] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_decisions(self) -> "TaskDecisionMatrixV1":
        ids = [item.decision_id for item in self.decision_points]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_decision_point_id")
        return self


class ScenarioFirstAdmissionFindingV1(ScenarioFirstModel):
    finding_id: str = Field(min_length=1)
    category: FindingCategory
    passed: bool
    reason_code: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ScenarioFirstAdmissionReportV1(ScenarioFirstModel):
    report_version: Literal["r10.scenario_first_admission_report.1"] = "r10.scenario_first_admission_report.1"
    scenario_id: str = Field(min_length=1)
    decision: AdmissionDecision
    static_only: Literal[True] = True
    input_sha256: str = Field(min_length=64, max_length=64)
    findings: list[ScenarioFirstAdmissionFindingV1] = Field(default_factory=list)
