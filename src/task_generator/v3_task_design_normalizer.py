from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from task_generator.v3_task_design_frontend import (
    CapabilityBriefV1,
    DeliverableIntentV1,
    EvidenceFieldSpecV1,
    EvidenceFieldComparisonV1,
    EvidenceRelationProposalV1,
    EvidenceScalar,
    ProposalAuthorityBoundaryV1,
    RequiredJudgmentProposalV1,
    SkillBindingProposalV1,
    TaskDesignProposalV1,
)


class SemanticEvidenceArtifactSpecV1(BaseModel):
    """Provider-owned semantics without execution-only record wrappers."""

    model_config = ConfigDict(extra="forbid")
    fact_origin: Literal[
        "governed_scenario_fact",
        "public_source_fact",
        "methodological_context",
    ]
    record_type: str = Field(min_length=3)
    primary_key_field: str
    fields: List[EvidenceFieldSpecV1] = Field(min_length=4)
    records: List[Dict[str, EvidenceScalar]] = Field(min_length=3)
    methodological_source_ref_ids: List[str] = Field(default_factory=list)


class SemanticEvidenceNodeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    artifact_role: str = Field(min_length=3)
    source_ref_ids: List[str] = Field(min_length=1)
    intended_contents: str = Field(min_length=8)
    artifact_spec: SemanticEvidenceArtifactSpecV1


class TaskDesignSemanticDraftProposalV1(BaseModel):
    """Parseable provider draft retained only for governed feedback repair."""

    model_config = ConfigDict(extra="forbid")
    semantic_proposal_version: Literal["v3.task_design_semantic_proposal.1"] = (
        "v3.task_design_semantic_proposal.1"
    )
    proposal_id: str
    brief_id: str
    source_ref_ids: List[str] = Field(min_length=1)
    scenario: str = Field(min_length=20)
    actor_role: str = Field(min_length=3)
    trigger_event: str = Field(min_length=8)
    evidence_nodes: List[SemanticEvidenceNodeV1] = Field(min_length=2)
    evidence_relations: List[EvidenceRelationProposalV1] = Field(min_length=1)
    required_judgments: List[RequiredJudgmentProposalV1] = Field(min_length=1)
    skill_bindings: List[SkillBindingProposalV1] = Field(min_length=1)
    deliverable_intent: DeliverableIntentV1
    productive_complexity: List[str] = Field(min_length=1)
    accidental_difficulty_to_avoid: List[str] = Field(min_length=1)
    deterministic_fact_constraints: List[str] = Field(min_length=1)
    assumptions_not_allowed: List[str] = Field(min_length=1)
    unresolved_design_questions: List[str] = Field(default_factory=list)


class SemanticEvidenceRelationV1(BaseModel):
    """Provider relation contract with mandatory deterministic join semantics."""

    model_config = ConfigDict(extra="forbid")
    relation_id: str
    from_node_id: str
    to_node_id: str
    relation_type: str = Field(min_length=3)
    solver_must_infer: bool = True
    from_join_field: str = Field(min_length=1)
    to_join_field: str = Field(min_length=1)
    comparison_fields: List[EvidenceFieldComparisonV1] = Field(
        default_factory=list
    )


class TaskDesignSemanticProposalV1(TaskDesignSemanticDraftProposalV1):
    """Complete LLM semantic contract normalized into strict proposal V2."""

    evidence_relations: List[SemanticEvidenceRelationV1] = Field(min_length=1)


class ProposalNormalizationFindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: List[str] = Field(default_factory=list)
    finding_type: str
    message: str


class TaskDesignNormalizationReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.task_design_normalization.1"] = (
        "v3.task_design_normalization.1"
    )
    decision: Literal["pass", "blocked"]
    brief_id: str
    proposal_id: Optional[str] = None
    source_interface_version: str = "v3.task_design_semantic_proposal.1"
    target_contract_version: Literal["v3.task_design_proposal.2"] = (
        "v3.task_design_proposal.2"
    )
    source_payload_sha256: str
    normalized_proposal_sha256: Optional[str] = None
    provider_semantics_source_sha256: Optional[str] = None
    provider_semantics_normalized_sha256: Optional[str] = None
    evidence_node_count: int = 0
    evidence_relation_count: int = 0
    source_record_count: int = 0
    normalized_record_count: int = 0
    facts_added: int = 0
    facts_removed: int = 0
    semantic_loss_detected: bool = False
    productive_complexity_preserved: bool = False
    authority_boundary_stamped_by_program: bool = False
    normalization_actions: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    findings: List[ProposalNormalizationFindingV1] = Field(default_factory=list)
    raw_provider_values_in_findings: Literal[False] = False
    materialization_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


class TaskDesignProposalNormalizer:
    """Normalize syntax only; never generate business fields, values, or relations."""

    MAX_SEMANTIC_PAYLOAD_CHARS = 100_000

    def normalize_payload(
        self,
        payload: Dict[str, Any],
        brief: CapabilityBriefV1,
    ) -> Tuple[Optional[TaskDesignProposalV1], TaskDesignNormalizationReportV1]:
        source_sha = self._sha256(payload)
        if len(self._canonical(payload)) > self.MAX_SEMANTIC_PAYLOAD_CHARS:
            return None, TaskDesignNormalizationReportV1(
                decision="blocked",
                brief_id=brief.brief_id,
                source_payload_sha256=source_sha,
                blocking_reasons=["semantic_proposal_payload_too_large"],
            )
        try:
            semantic = TaskDesignSemanticProposalV1.model_validate(payload)
        except Exception as exc:
            return None, TaskDesignNormalizationReportV1(
                decision="blocked",
                brief_id=brief.brief_id,
                source_payload_sha256=source_sha,
                blocking_reasons=["semantic_proposal_schema_invalid"],
                findings=self._sanitized_findings(exc),
            )

        if semantic.brief_id != brief.brief_id:
            return None, self._blocked_semantic_report(
                semantic,
                source_sha,
                "semantic_proposal_brief_mismatch",
            )

        node_payloads: List[Dict[str, Any]] = []
        source_records: List[Dict[str, EvidenceScalar]] = []
        blocking: List[str] = []
        for node in semantic.evidence_nodes:
            spec = node.artifact_spec
            field_names = [field.field_name for field in spec.fields]
            if len(field_names) != len(set(field_names)):
                blocking.append(f"duplicate_semantic_field:{node.node_id}")
            field_set = set(field_names)
            if spec.primary_key_field not in field_set:
                blocking.append(f"unknown_semantic_primary_key:{node.node_id}")
            wrapped_records: List[Dict[str, Any]] = []
            for record_index, values in enumerate(spec.records):
                source_records.append(dict(values))
                unknown = set(values) - field_set
                if unknown:
                    blocking.append(
                        f"unknown_semantic_record_field:{node.node_id}:{record_index}"
                    )
                missing = {
                    field.field_name
                    for field in spec.fields
                    if field.required and field.field_name not in values
                }
                if missing:
                    blocking.append(
                        f"missing_semantic_record_field:{node.node_id}:{record_index}"
                    )
                primary_value = values.get(spec.primary_key_field)
                if primary_value is None or str(primary_value).strip() == "":
                    blocking.append(
                        f"missing_semantic_primary_key_value:{node.node_id}:{record_index}"
                    )
                    continue
                wrapped_records.append(
                    {
                        "record_id": str(primary_value),
                        "values": dict(values),
                    }
                )
            node_payloads.append(
                {
                    "node_id": node.node_id,
                    "artifact_role": node.artifact_role,
                    "candidate_visible": True,
                    "source_ref_ids": node.source_ref_ids,
                    "intended_contents": node.intended_contents,
                    "artifact_spec": {
                        "spec_version": "v3.evidence_artifact_spec.1",
                        "fact_origin": spec.fact_origin,
                        "record_type": spec.record_type,
                        "primary_key_field": spec.primary_key_field,
                        "fields": [
                            field.model_dump(mode="json") for field in spec.fields
                        ],
                        "records": wrapped_records,
                        "methodological_source_ref_ids": (
                            spec.methodological_source_ref_ids
                        ),
                    },
                }
            )

        if blocking:
            return None, self._blocked_semantic_report(
                semantic,
                source_sha,
                *sorted(set(blocking)),
            )

        normalized_payload = {
            "proposal_version": "v3.task_design_proposal.2",
            "proposal_id": semantic.proposal_id,
            "brief_id": semantic.brief_id,
            "proposal_origin": "llm",
            "source_ref_ids": semantic.source_ref_ids,
            "scenario": semantic.scenario,
            "actor_role": semantic.actor_role,
            "trigger_event": semantic.trigger_event,
            "evidence_nodes": node_payloads,
            "evidence_relations": [
                relation.model_dump(mode="json")
                for relation in semantic.evidence_relations
            ],
            "required_judgments": [
                judgment.model_dump(mode="json")
                for judgment in semantic.required_judgments
            ],
            "skill_bindings": [
                binding.model_dump(mode="json")
                for binding in semantic.skill_bindings
            ],
            "deliverable_intent": semantic.deliverable_intent.model_dump(
                mode="json"
            ),
            "productive_complexity": semantic.productive_complexity,
            "accidental_difficulty_to_avoid": (
                semantic.accidental_difficulty_to_avoid
            ),
            "deterministic_fact_constraints": (
                semantic.deterministic_fact_constraints
            ),
            "assumptions_not_allowed": semantic.assumptions_not_allowed,
            "unresolved_design_questions": semantic.unresolved_design_questions,
            "authority": ProposalAuthorityBoundaryV1().model_dump(mode="json"),
        }
        try:
            proposal = TaskDesignProposalV1.model_validate(normalized_payload)
        except Exception as exc:
            return None, TaskDesignNormalizationReportV1(
                decision="blocked",
                brief_id=brief.brief_id,
                proposal_id=semantic.proposal_id,
                source_payload_sha256=source_sha,
                evidence_node_count=len(semantic.evidence_nodes),
                evidence_relation_count=len(semantic.evidence_relations),
                source_record_count=len(source_records),
                blocking_reasons=["normalized_v2_contract_invalid"],
                findings=self._sanitized_findings(exc),
            )

        normalized_records = [
            dict(record.values)
            for node in proposal.evidence_nodes
            if node.artifact_spec
            for record in node.artifact_spec.records
        ]
        source_semantics = self._semantic_projection(semantic)
        normalized_semantics = self._normalized_projection(proposal)
        source_semantics_sha = self._sha256(source_semantics)
        normalized_semantics_sha = self._sha256(normalized_semantics)
        semantic_loss = source_semantics_sha != normalized_semantics_sha
        complexity_preserved = (
            proposal.productive_complexity == semantic.productive_complexity
        )
        if semantic_loss or not complexity_preserved:
            facts_added, facts_removed = self._semantic_fact_delta(
                source_semantics,
                normalized_semantics,
            )
            reasons = []
            if semantic_loss:
                reasons.append("normalization_semantic_loss_detected")
            if not complexity_preserved:
                reasons.append("normalization_productive_complexity_loss")
            return None, TaskDesignNormalizationReportV1(
                decision="blocked",
                brief_id=brief.brief_id,
                proposal_id=semantic.proposal_id,
                source_payload_sha256=source_sha,
                provider_semantics_source_sha256=source_semantics_sha,
                provider_semantics_normalized_sha256=normalized_semantics_sha,
                evidence_node_count=len(semantic.evidence_nodes),
                evidence_relation_count=len(semantic.evidence_relations),
                source_record_count=len(source_records),
                normalized_record_count=len(normalized_records),
                facts_added=facts_added,
                facts_removed=facts_removed,
                semantic_loss_detected=semantic_loss,
                productive_complexity_preserved=complexity_preserved,
                blocking_reasons=reasons,
            )

        return proposal, TaskDesignNormalizationReportV1(
            decision="pass",
            brief_id=brief.brief_id,
            proposal_id=semantic.proposal_id,
            source_payload_sha256=source_sha,
            normalized_proposal_sha256=self._sha256(
                proposal.model_dump(mode="json")
            ),
            provider_semantics_source_sha256=source_semantics_sha,
            provider_semantics_normalized_sha256=normalized_semantics_sha,
            evidence_node_count=len(semantic.evidence_nodes),
            evidence_relation_count=len(semantic.evidence_relations),
            source_record_count=len(source_records),
            normalized_record_count=len(normalized_records),
            facts_added=0,
            facts_removed=0,
            semantic_loss_detected=False,
            productive_complexity_preserved=True,
            authority_boundary_stamped_by_program=True,
            normalization_actions=[
                "stamp_proposal_and_artifact_contract_versions",
                "stamp_zero_authority_boundary",
                "wrap_flat_records_using_explicit_primary_key_values",
                "stamp_candidate_visible_true",
            ],
        )

    @staticmethod
    def _blocked_semantic_report(
        semantic: TaskDesignSemanticProposalV1,
        source_sha: str,
        *reasons: str,
    ) -> TaskDesignNormalizationReportV1:
        return TaskDesignNormalizationReportV1(
            decision="blocked",
            brief_id=semantic.brief_id,
            proposal_id=semantic.proposal_id,
            source_payload_sha256=source_sha,
            evidence_node_count=len(semantic.evidence_nodes),
            evidence_relation_count=len(semantic.evidence_relations),
            source_record_count=sum(
                len(node.artifact_spec.records)
                for node in semantic.evidence_nodes
            ),
            blocking_reasons=list(reasons),
        )

    @staticmethod
    def _sanitized_findings(exc: Exception) -> List[ProposalNormalizationFindingV1]:
        if isinstance(exc, ValidationError):
            return [
                ProposalNormalizationFindingV1(
                    location=[str(part) for part in error.get("loc", ())],
                    finding_type=str(error.get("type", "validation_error")),
                    message=str(error.get("msg", "invalid value")),
                )
                for error in exc.errors(include_url=False, include_input=False)
            ]
        return [
            ProposalNormalizationFindingV1(
                finding_type=type(exc).__name__,
                message="contract validation failed without safe structured findings",
            )
        ]

    @staticmethod
    def _semantic_projection(
        semantic: TaskDesignSemanticProposalV1,
    ) -> Dict[str, Any]:
        return {
            "proposal_id": semantic.proposal_id,
            "brief_id": semantic.brief_id,
            "source_ref_ids": semantic.source_ref_ids,
            "scenario": semantic.scenario,
            "actor_role": semantic.actor_role,
            "trigger_event": semantic.trigger_event,
            "evidence_nodes": [
                {
                    "node_id": node.node_id,
                    "artifact_role": node.artifact_role,
                    "source_ref_ids": node.source_ref_ids,
                    "intended_contents": node.intended_contents,
                    "artifact_spec": node.artifact_spec.model_dump(mode="json"),
                }
                for node in semantic.evidence_nodes
            ],
            "evidence_relations": [
                item.model_dump(mode="json")
                for item in semantic.evidence_relations
            ],
            "required_judgments": [
                item.model_dump(mode="json")
                for item in semantic.required_judgments
            ],
            "skill_bindings": [
                item.model_dump(mode="json") for item in semantic.skill_bindings
            ],
            "deliverable_intent": semantic.deliverable_intent.model_dump(
                mode="json"
            ),
            "productive_complexity": semantic.productive_complexity,
            "accidental_difficulty_to_avoid": (
                semantic.accidental_difficulty_to_avoid
            ),
            "deterministic_fact_constraints": (
                semantic.deterministic_fact_constraints
            ),
            "assumptions_not_allowed": semantic.assumptions_not_allowed,
            "unresolved_design_questions": semantic.unresolved_design_questions,
        }

    @staticmethod
    def _normalized_projection(proposal: TaskDesignProposalV1) -> Dict[str, Any]:
        return {
            "proposal_id": proposal.proposal_id,
            "brief_id": proposal.brief_id,
            "source_ref_ids": proposal.source_ref_ids,
            "scenario": proposal.scenario,
            "actor_role": proposal.actor_role,
            "trigger_event": proposal.trigger_event,
            "evidence_nodes": [
                {
                    "node_id": node.node_id,
                    "artifact_role": node.artifact_role,
                    "source_ref_ids": node.source_ref_ids,
                    "intended_contents": node.intended_contents,
                    "artifact_spec": {
                        "fact_origin": node.artifact_spec.fact_origin,
                        "record_type": node.artifact_spec.record_type,
                        "primary_key_field": (
                            node.artifact_spec.primary_key_field
                        ),
                        "fields": [
                            field.model_dump(mode="json")
                            for field in node.artifact_spec.fields
                        ],
                        "records": [
                            dict(record.values)
                            for record in node.artifact_spec.records
                        ],
                        "methodological_source_ref_ids": (
                            node.artifact_spec.methodological_source_ref_ids
                        ),
                    },
                }
                for node in proposal.evidence_nodes
                if node.artifact_spec is not None
            ],
            "evidence_relations": [
                item.model_dump(mode="json")
                for item in proposal.evidence_relations
            ],
            "required_judgments": [
                item.model_dump(mode="json")
                for item in proposal.required_judgments
            ],
            "skill_bindings": [
                item.model_dump(mode="json") for item in proposal.skill_bindings
            ],
            "deliverable_intent": proposal.deliverable_intent.model_dump(
                mode="json"
            ),
            "productive_complexity": proposal.productive_complexity,
            "accidental_difficulty_to_avoid": (
                proposal.accidental_difficulty_to_avoid
            ),
            "deterministic_fact_constraints": (
                proposal.deterministic_fact_constraints
            ),
            "assumptions_not_allowed": proposal.assumptions_not_allowed,
            "unresolved_design_questions": proposal.unresolved_design_questions,
        }

    @classmethod
    def _semantic_fact_delta(
        cls,
        source: Any,
        normalized: Any,
    ) -> Tuple[int, int]:
        source_facts = Counter(cls._flatten_semantic_facts(source))
        normalized_facts = Counter(cls._flatten_semantic_facts(normalized))
        return (
            sum((normalized_facts - source_facts).values()),
            sum((source_facts - normalized_facts).values()),
        )

    @classmethod
    def _flatten_semantic_facts(
        cls,
        value: Any,
        path: str = "$",
    ) -> List[str]:
        if isinstance(value, dict):
            facts: List[str] = []
            for key in sorted(value):
                facts.extend(
                    cls._flatten_semantic_facts(value[key], f"{path}.{key}")
                )
            return facts
        if isinstance(value, list):
            facts = []
            for index, item in enumerate(value):
                facts.extend(
                    cls._flatten_semantic_facts(item, f"{path}[{index}]")
                )
            return facts
        return [f"{path}={cls._canonical(value)}"]

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _sha256(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical(value).encode("utf-8")).hexdigest()
