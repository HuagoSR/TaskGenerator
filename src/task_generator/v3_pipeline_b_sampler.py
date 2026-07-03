import json
import re
from hashlib import sha1
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_motif_graph_grammar import (
    MotifGraphGrammarArtifact,
    MotifGraphGrammarRecord,
    MotifRoleDefinition,
)
from task_generator.v3_pipeline_b_prototype import DEFAULT_MOTIF_PRIORITY, RESOURCE_ALIASES
from task_generator.v3_skill_registry import SkillRegistryBuilder
from task_generator.v3_source_schema import SemanticResource, SkillRegistryEntry, load_json_file


ReadinessDecision = Literal["sample_ready", "sample_with_caution", "exclude_until_revised", "unknown"]
ResourceDirection = Literal["required", "optional", "provided"]
ResourceEvidenceMode = Literal["typed", "legacy_inferred"]
EdgeEvidenceMode = Literal["typed_resource_match", "legacy_resource_overlap", "role_sequence", "motif_cooccurrence"]
SamplerConfidence = Literal["blocked", "low_due_to_resource_fallback", "medium_with_pipeline_a_gaps", "medium", "high"]
WorkflowContextFit = Literal["low", "medium", "high"]
TaskGraphShapeAssumption = Literal["chain", "tree", "fan_in", "dag", "constraint_graph"]
RoleFitStatus = Literal["filled", "partial", "missing"]

ROLE_PRIORITY = ["starter", "transform", "fan_in", "validator", "synthesis"]
BLOCKING_READINESS = {"exclude_until_revised"}
DEFAULT_MOTIF_GRAMMAR_PATH = Path("SkillRegistry") / "v3_motif_graph_grammar.experimental.json"


class PipelineBSamplingRequest(BaseModel):
    registry_path: str
    seed_report_path: str
    motif: Optional[str] = None
    skill_count: int = 4
    allow_caution: bool = False
    workflow_archetype: Optional[str] = None
    motif_grammar_path: Optional[str] = None
    target_difficulty_profile: Optional[str] = None


class PipelineBSelectedSkill(BaseModel):
    skill_id: str
    canonical_name: str
    readiness_decision: ReadinessDecision = "unknown"
    seed_score: float = 0.0
    sampling_weight: float = 0.0
    domain_tags: List[str] = Field(default_factory=list)
    capability_tags: List[str] = Field(default_factory=list)
    motif_hints: List[str] = Field(default_factory=list)
    graph_role_hints: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    selection_reason: str = ""


class PipelineBResourceNode(BaseModel):
    resource_id: str
    resource_type: str
    direction: ResourceDirection
    skill_id: str
    evidence_mode: ResourceEvidenceMode
    subtype: str = ""
    domain: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    source_text: str = ""


class PipelineBSubgraphEdge(BaseModel):
    edge_id: str
    from_id: str
    to_id: str
    relation_type: str
    evidence_mode: EdgeEvidenceMode
    confidence: float = 0.5
    reason_codes: List[str] = Field(default_factory=list)


class PipelineBRoleFitScore(BaseModel):
    role_name: str
    role_kind: str
    status: RoleFitStatus = "missing"
    score: float = 0.0
    matched_skill_ids: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PipelineBSamplingDiagnostics(BaseModel):
    selected_motif: str
    readiness_counts: Dict[str, int] = Field(default_factory=dict)
    role_coverage: Dict[str, int] = Field(default_factory=dict)
    motif_coverage: Dict[str, int] = Field(default_factory=dict)
    resource_coverage: Dict[str, int] = Field(default_factory=dict)
    edge_counts: Dict[str, int] = Field(default_factory=dict)
    fallback_evidence: List[str] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)
    missing_or_weak_pipeline_a_signals: List[str] = Field(default_factory=list)
    confidence: SamplerConfidence = "blocked"
    workflow_archetype_id: Optional[str] = None
    motif_grammar_id: Optional[str] = None
    filled_roles: List[str] = Field(default_factory=list)
    missing_roles: List[str] = Field(default_factory=list)
    role_fit_scores: List[PipelineBRoleFitScore] = Field(default_factory=list)
    workflow_context_fit: WorkflowContextFit = "low"
    task_graph_shape_assumption: TaskGraphShapeAssumption = "chain"
    sampler_policy_version: str = "role_filling_v1"
    role_assignment_fallback_reasons: List[str] = Field(default_factory=list)


class PipelineBSubgraph(BaseModel):
    subgraph_id: str
    sampler_version: str = "v3.pipeline_b_sampler.1"
    request: PipelineBSamplingRequest
    selected_motif: str
    selected_skills: List[PipelineBSelectedSkill] = Field(default_factory=list)
    resource_nodes: List[PipelineBResourceNode] = Field(default_factory=list)
    subgraph_edges: List[PipelineBSubgraphEdge] = Field(default_factory=list)
    diagnostics: PipelineBSamplingDiagnostics
    notes: List[str] = Field(default_factory=list)


class PipelineBSubgraphSampler:
    """Report-first sampler for a small Pipeline B skill-resource subgraph."""

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()

    def build_subgraph(
        self,
        registry_path: str | Path,
        seed_report_path: str | Path,
        motif: Optional[str] = None,
        skill_count: int = 4,
        allow_caution: bool = False,
        workflow_archetype: Optional[str] = None,
        motif_grammar_path: Optional[str | Path] = None,
        target_difficulty_profile: Optional[str] = None,
    ) -> PipelineBSubgraph:
        resolved_motif_grammar_path = self._resolve_motif_grammar_path(motif_grammar_path)
        request = PipelineBSamplingRequest(
            registry_path=str(registry_path),
            seed_report_path=str(seed_report_path),
            motif=motif,
            skill_count=skill_count,
            allow_caution=allow_caution,
            workflow_archetype=workflow_archetype,
            motif_grammar_path=str(resolved_motif_grammar_path) if resolved_motif_grammar_path else None,
            target_difficulty_profile=target_difficulty_profile,
        )
        entries = self.registry_builder.load_registry(registry_path)
        entry_by_id = {entry.skill_id: entry for entry in entries}
        seed_report = load_json_file(str(seed_report_path))
        selected_motif = motif or self._choose_motif(seed_report)
        motif_grammar = self.load_motif_graph_grammar(resolved_motif_grammar_path).get(selected_motif)
        seed_records = list(seed_report.get("seed_records", []))
        selected_records = self._select_records(seed_records, selected_motif, skill_count, allow_caution)
        selected_entries = [
            entry_by_id[record["skill_id"]]
            for record in selected_records
            if record.get("skill_id") in entry_by_id
        ]
        selected_skills = [
            self._selected_skill(record, selected_motif)
            for record in selected_records
            if record.get("skill_id") in entry_by_id
        ]
        resource_nodes = self._resource_nodes(selected_entries)
        subgraph_edges = self._subgraph_edges(selected_skills, resource_nodes, selected_motif)
        diagnostics = self._diagnostics(
            selected_motif=selected_motif,
            selected_skills=selected_skills,
            resource_nodes=resource_nodes,
            subgraph_edges=subgraph_edges,
            workflow_archetype=workflow_archetype,
            motif_grammar=motif_grammar,
        )

        return PipelineBSubgraph(
            subgraph_id=self._stable_id("subgraph", [selected_motif, *[skill.skill_id for skill in selected_skills]]),
            request=request,
            selected_motif=selected_motif,
            selected_skills=selected_skills,
            resource_nodes=resource_nodes,
            subgraph_edges=subgraph_edges,
            diagnostics=diagnostics,
            notes=[
                "Report-only sampler output; no SkillRegistry files are mutated.",
                "Typed resources are preferred; legacy keyword resources are diagnostic fallback evidence.",
                "This sampler is deterministic/static and does not implement UCB, bandit, or learned priors.",
                "Motif grammar alignment is report-only in V1 and does not yet change the core selection policy.",
            ],
        )

    def load_motif_graph_grammar(
        self,
        motif_grammar_path: Optional[str | Path] = None,
    ) -> Dict[str, MotifGraphGrammarRecord]:
        resolved_path = self._resolve_motif_grammar_path(motif_grammar_path)
        if not resolved_path or not resolved_path.exists():
            return {}
        artifact = MotifGraphGrammarArtifact.model_validate(load_json_file(str(resolved_path)))
        return {record.motif_type: record for record in artifact.grammars}

    def build_feedback(self, subgraph: PipelineBSubgraph) -> Dict[str, Any]:
        diagnostics = subgraph.diagnostics
        feedback_items = []
        missing = set(diagnostics.missing_or_weak_pipeline_a_signals)
        if "persistent_registry_typed_resources" in missing:
            feedback_items.append(
                {
                    "feedback_code": "missing_typed_resources",
                    "severity": "high",
                    "message": "Selected registry entries do not expose typed SemanticResource contracts.",
                }
            )
        if "multi_source_evidence_support" in missing:
            feedback_items.append(
                {
                    "feedback_code": "single_source_support",
                    "severity": "medium",
                    "message": "Selected skills include single-source support risk; keep provenance visible.",
                }
            )
        if "full_motif_coverage_for_selected_subgraph" in missing:
            feedback_items.append(
                {
                    "feedback_code": "weak_motif_coverage",
                    "severity": "medium",
                    "message": "Not every selected skill has the selected motif hint.",
                }
            )
        if "usable_graph_role_coverage" in missing or "missing_core_graph_roles" in missing:
            feedback_items.append(
                {
                    "feedback_code": "missing_graph_roles",
                    "severity": "medium",
                    "message": "Selected skills do not cover enough starter/transform/fan-in/validator/synthesis roles.",
                }
            )
        if "transition_evidence" in missing:
            feedback_items.append(
                {
                    "feedback_code": "absent_transition_evidence",
                    "severity": "medium",
                    "message": "No typed-resource or explicit transition evidence connected selected skills.",
                }
            )
        if not feedback_items:
            feedback_items.append(
                {
                    "feedback_code": "signals_sufficient_for_subgraph_smoke",
                    "severity": "info",
                    "message": "Sampler found enough signals for a report-only subgraph smoke.",
                }
            )

        return {
            "pipeline_a_feedback_version": "v3.pipeline_b_feedback.1",
            "subgraph_id": subgraph.subgraph_id,
            "selected_motif": subgraph.selected_motif,
            "confidence": diagnostics.confidence,
            "sampled_skill_ids": [skill.skill_id for skill in subgraph.selected_skills],
            "sampled_edge_ids": [edge.edge_id for edge in subgraph.subgraph_edges],
            "sampled_resource_ids": [resource.resource_id for resource in subgraph.resource_nodes],
            "missing_or_weak_pipeline_a_signals": diagnostics.missing_or_weak_pipeline_a_signals,
            "feedback_items": feedback_items,
            "future_prior_update": {
                "eligible": False,
                "reason": "No generated task-quality outcome exists yet.",
            },
        }

    def write_outputs(self, subgraph: PipelineBSubgraph, output_dir: str | Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        subgraph_path = output_path / "pipeline_b_subgraph_report.json"
        feedback_path = output_path / "pipeline_a_feedback.json"
        feedback = self.build_feedback(subgraph)
        subgraph_path.write_text(subgraph.model_dump_json(indent=2), encoding="utf-8")
        feedback_path.write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "subgraph_report_path": str(subgraph_path),
            "pipeline_a_feedback_path": str(feedback_path),
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
        allow_caution: bool,
    ) -> List[Dict[str, Any]]:
        eligible = []
        for record in seed_records:
            readiness = record.get("readiness_decision", "unknown")
            if readiness in BLOCKING_READINESS:
                continue
            if readiness == "sample_with_caution" and not allow_caution:
                continue
            eligible.append(record)

        matching = [record for record in eligible if motif in record.get("motif_hints", [])]
        matching.sort(key=self._record_sort_key)
        selected = self._role_balanced_pick(matching, skill_count)

        if len(selected) < skill_count:
            seen = {record.get("skill_id") for record in selected}
            fallback = sorted(eligible, key=self._record_sort_key)
            for record in fallback:
                if record.get("skill_id") in seen:
                    continue
                selected.append(record)
                seen.add(record.get("skill_id"))
                if len(selected) >= skill_count:
                    break

        return selected

    def _record_sort_key(self, record: Dict[str, Any]) -> Tuple[float, str]:
        return (-float(record.get("seed_score", 0.0)), record.get("canonical_name", ""))

    def _role_balanced_pick(self, records: List[Dict[str, Any]], skill_count: int) -> List[Dict[str, Any]]:
        selected = []
        seen = set()
        for role in ROLE_PRIORITY:
            match = next(
                (
                    record
                    for record in records
                    if record.get("skill_id") not in seen and role in record.get("graph_role_hints", [])
                ),
                None,
            )
            if match:
                selected.append(match)
                seen.add(match.get("skill_id"))
            if len(selected) >= skill_count:
                return selected

        for record in records:
            if record.get("skill_id") in seen:
                continue
            selected.append(record)
            seen.add(record.get("skill_id"))
            if len(selected) >= skill_count:
                break
        return selected

    def _selected_skill(self, record: Dict[str, Any], motif: str) -> PipelineBSelectedSkill:
        reasons = [f"readiness={record.get('readiness_decision', 'unknown')}"]
        if motif in record.get("motif_hints", []):
            reasons.append(f"motif={motif}")
        if record.get("graph_role_hints"):
            reasons.append("roles=" + ",".join(record.get("graph_role_hints", [])))
        return PipelineBSelectedSkill(
            skill_id=record.get("skill_id", ""),
            canonical_name=record.get("canonical_name", ""),
            readiness_decision=record.get("readiness_decision", "unknown"),
            seed_score=float(record.get("seed_score", 0.0)),
            sampling_weight=float(record.get("sampling_weight", 0.0)),
            domain_tags=list(record.get("domain_tags", [])),
            capability_tags=list(record.get("capability_tags", [])),
            motif_hints=list(record.get("motif_hints", [])),
            graph_role_hints=list(record.get("graph_role_hints", [])),
            reason_codes=list(record.get("reason_codes", [])),
            selection_reason="; ".join(reasons),
        )

    def _resource_nodes(self, entries: List[SkillRegistryEntry]) -> List[PipelineBResourceNode]:
        nodes: List[PipelineBResourceNode] = []
        for entry in entries:
            for direction, resources in [
                ("required", entry.input_contract.required_resources),
                ("optional", entry.input_contract.optional_resources),
                ("provided", entry.output_contract.provided_resources),
            ]:
                for index, resource in enumerate(resources):
                    nodes.append(self._typed_resource_node(entry.skill_id, direction, index, resource))

            if not self._has_typed_resources(entry):
                inferred = self._infer_legacy_resources(entry)
                for index, resource_type in enumerate(sorted(inferred)):
                    nodes.append(
                        PipelineBResourceNode(
                            resource_id=self._stable_id("legacy_resource", [entry.skill_id, resource_type, str(index)]),
                            resource_type=resource_type,
                            direction="provided",
                            skill_id=entry.skill_id,
                            evidence_mode="legacy_inferred",
                            source_text="legacy semantic contract and keyword inference",
                        )
                    )
        return nodes

    def _typed_resource_node(
        self,
        skill_id: str,
        direction: ResourceDirection,
        index: int,
        resource: SemanticResource,
    ) -> PipelineBResourceNode:
        return PipelineBResourceNode(
            resource_id=self._stable_id(
                "resource",
                [skill_id, direction, resource.resource_type, resource.subtype, resource.domain, str(index)],
            ),
            resource_type=resource.resource_type,
            direction=direction,
            skill_id=skill_id,
            evidence_mode="typed",
            subtype=resource.subtype,
            domain=resource.domain,
            attributes=resource.attributes,
            evidence_refs=resource.evidence_refs,
        )

    def _has_typed_resources(self, entry: SkillRegistryEntry) -> bool:
        return bool(
            entry.input_contract.required_resources
            or entry.input_contract.optional_resources
            or entry.output_contract.provided_resources
        )

    def _infer_legacy_resources(self, entry: SkillRegistryEntry) -> Set[str]:
        text_items = [
            *entry.input_contract.requires_semantics,
            *entry.input_contract.optional_semantics,
            *entry.output_contract.provides_semantics,
            entry.canonical_name,
            entry.business_meaning,
            entry.hidden_difficulty,
            " ".join(entry.capability_tags),
            " ".join(entry.assembly_hints),
        ]
        compact = " ".join(text_items).lower()
        return {
            resource_type
            for key, resource_type in RESOURCE_ALIASES.items()
            if key in compact
        }

    def _subgraph_edges(
        self,
        selected_skills: List[PipelineBSelectedSkill],
        resources: List[PipelineBResourceNode],
        motif: str,
    ) -> List[PipelineBSubgraphEdge]:
        edges: List[PipelineBSubgraphEdge] = []
        resource_edges = self._resource_compatibility_edges(resources)
        edges.extend(resource_edges)
        if not resource_edges:
            edges.extend(self._role_sequence_edges(selected_skills))
        edges.extend(self._motif_edges(selected_skills, motif))
        return self._dedupe_edges(edges)

    def _resource_compatibility_edges(self, resources: List[PipelineBResourceNode]) -> List[PipelineBSubgraphEdge]:
        provided = [resource for resource in resources if resource.direction == "provided"]
        required = [resource for resource in resources if resource.direction in {"required", "optional"}]
        edges = []
        for source in provided:
            for target in required:
                if source.skill_id == target.skill_id:
                    continue
                if self._resource_compatible(source, target):
                    mode: EdgeEvidenceMode = (
                        "typed_resource_match"
                        if source.evidence_mode == "typed" and target.evidence_mode == "typed"
                        else "legacy_resource_overlap"
                    )
                    edges.append(
                        PipelineBSubgraphEdge(
                            edge_id=self._stable_id("edge", [source.resource_id, target.resource_id, mode]),
                            from_id=source.resource_id,
                            to_id=target.resource_id,
                            relation_type="resource_compatible",
                            evidence_mode=mode,
                            confidence=0.8 if mode == "typed_resource_match" else 0.45,
                            reason_codes=[source.resource_type],
                        )
                    )
        return edges

    def _resource_compatible(self, source: PipelineBResourceNode, target: PipelineBResourceNode) -> bool:
        if source.resource_type != target.resource_type:
            return False
        if source.domain and target.domain and source.domain != target.domain:
            return False
        if source.subtype and target.subtype and source.subtype != target.subtype:
            return False
        return True

    def _role_sequence_edges(self, selected_skills: List[PipelineBSelectedSkill]) -> List[PipelineBSubgraphEdge]:
        ranked = sorted(
            selected_skills,
            key=lambda skill: min(
                [ROLE_PRIORITY.index(role) for role in skill.graph_role_hints if role in ROLE_PRIORITY] or [len(ROLE_PRIORITY)]
            ),
        )
        edges = []
        for source, target in zip(ranked, ranked[1:]):
            edges.append(
                PipelineBSubgraphEdge(
                    edge_id=self._stable_id("edge", [source.skill_id, target.skill_id, "role_sequence"]),
                    from_id=source.skill_id,
                    to_id=target.skill_id,
                    relation_type="role_sequence_fallback",
                    evidence_mode="role_sequence",
                    confidence=0.3,
                    reason_codes=["no_resource_edge_available"],
                )
            )
        return edges

    def _motif_edges(self, selected_skills: List[PipelineBSelectedSkill], motif: str) -> List[PipelineBSubgraphEdge]:
        edges = []
        motif_skills = [skill for skill in selected_skills if motif in skill.motif_hints]
        for source, target in zip(motif_skills, motif_skills[1:]):
            edges.append(
                PipelineBSubgraphEdge(
                    edge_id=self._stable_id("edge", [source.skill_id, target.skill_id, motif]),
                    from_id=source.skill_id,
                    to_id=target.skill_id,
                    relation_type="motif_cooccurrence",
                    evidence_mode="motif_cooccurrence",
                    confidence=0.35,
                    reason_codes=[motif],
                )
            )
        return edges

    def _dedupe_edges(self, edges: List[PipelineBSubgraphEdge]) -> List[PipelineBSubgraphEdge]:
        deduped = {}
        for edge in edges:
            deduped[edge.edge_id] = edge
        return list(deduped.values())

    def _diagnostics(
        self,
        selected_motif: str,
        selected_skills: List[PipelineBSelectedSkill],
        resource_nodes: List[PipelineBResourceNode],
        subgraph_edges: List[PipelineBSubgraphEdge],
        workflow_archetype: Optional[str],
        motif_grammar: Optional[MotifGraphGrammarRecord],
    ) -> PipelineBSamplingDiagnostics:
        readiness_counts = Counter(skill.readiness_decision for skill in selected_skills)
        role_counts = Counter(role for skill in selected_skills for role in skill.graph_role_hints)
        motif_counts = Counter(motif for skill in selected_skills for motif in skill.motif_hints)
        resource_counts = Counter(f"{node.evidence_mode}_{node.direction}" for node in resource_nodes)
        edge_counts = Counter(edge.evidence_mode for edge in subgraph_edges)
        reason_counts = Counter(reason for skill in selected_skills for reason in skill.reason_codes)
        missing = []
        gaps = []

        typed_count = sum(1 for node in resource_nodes if node.evidence_mode == "typed")
        fallback_count = sum(1 for node in resource_nodes if node.evidence_mode == "legacy_inferred")
        typed_edge_count = edge_counts.get("typed_resource_match", 0)
        resource_edge_count = typed_edge_count + edge_counts.get("legacy_resource_overlap", 0)

        if not selected_skills:
            missing.append("selected_skills")
            gaps.append("No eligible seed records were selected.")
        if typed_count == 0:
            missing.append("persistent_registry_typed_resources")
            gaps.append("No selected registry entry exposed typed SemanticResource nodes.")
        if motif_counts.get(selected_motif, 0) < len(selected_skills):
            missing.append("full_motif_coverage_for_selected_subgraph")
            gaps.append("At least one selected skill lacks the selected motif hint.")
        if "single_source_support" in reason_counts:
            missing.append("multi_source_evidence_support")
        missing_roles = [role for role in ROLE_PRIORITY if role not in role_counts]
        if len(missing_roles) >= 3:
            missing.append("missing_core_graph_roles")
            gaps.append("Missing graph roles: " + ", ".join(missing_roles))
        if resource_edge_count == 0:
            missing.append("transition_evidence")
            gaps.append("No typed or legacy resource compatibility edges connected selected resources.")

        fallback_evidence = []
        if fallback_count:
            fallback_evidence.append("legacy_keyword_resource_inference")
        if edge_counts.get("role_sequence", 0):
            fallback_evidence.append("role_sequence_fallback_edges")
        if edge_counts.get("motif_cooccurrence", 0):
            fallback_evidence.append("motif_cooccurrence_edges")

        role_alignment = self._role_alignment(
            selected_motif=selected_motif,
            selected_skills=selected_skills,
            resource_nodes=resource_nodes,
            motif_grammar=motif_grammar,
        )
        task_graph_shape_assumption = self._task_graph_shape_assumption(
            motif_grammar=motif_grammar,
            selected_motif=selected_motif,
            subgraph_edges=subgraph_edges,
        )
        role_assignment_fallback_reasons = self._role_assignment_fallback_reasons(
            motif_grammar=motif_grammar,
            role_alignment=role_alignment,
            typed_count=typed_count,
            edge_counts=edge_counts,
        )

        return PipelineBSamplingDiagnostics(
            selected_motif=selected_motif,
            readiness_counts=dict(sorted(readiness_counts.items())),
            role_coverage=dict(sorted(role_counts.items())),
            motif_coverage=dict(sorted(motif_counts.items())),
            resource_coverage=dict(sorted(resource_counts.items())),
            edge_counts=dict(sorted(edge_counts.items())),
            fallback_evidence=sorted(fallback_evidence),
            unresolved_gaps=gaps,
            missing_or_weak_pipeline_a_signals=sorted(set(missing)),
            confidence=self._confidence(selected_skills, missing, typed_count, typed_edge_count),
            workflow_archetype_id=workflow_archetype,
            motif_grammar_id=motif_grammar.motif_grammar_id if motif_grammar else None,
            filled_roles=role_alignment["filled_roles"],
            missing_roles=role_alignment["missing_roles"],
            role_fit_scores=role_alignment["role_fit_scores"],
            workflow_context_fit=self._workflow_context_fit(
                motif_grammar=motif_grammar,
                selected_skills=selected_skills,
                filled_role_count=len(role_alignment["filled_roles"]),
                required_role_count=role_alignment["required_role_count"],
                typed_count=typed_count,
            ),
            task_graph_shape_assumption=task_graph_shape_assumption,
            role_assignment_fallback_reasons=role_assignment_fallback_reasons,
        )

    def _confidence(
        self,
        selected_skills: List[PipelineBSelectedSkill],
        missing: List[str],
        typed_count: int,
        typed_edge_count: int,
    ) -> SamplerConfidence:
        if not selected_skills:
            return "blocked"
        if typed_count == 0:
            return "low_due_to_resource_fallback"
        if typed_edge_count and not missing:
            return "high"
        if len(set(missing)) >= 2:
            return "medium_with_pipeline_a_gaps"
        return "medium"

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        raw = "__".join(str(part) for part in parts if str(part))
        compact = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
        digest = sha1(raw.encode("utf-8")).hexdigest()[:10]
        if len(compact) > 72:
            compact = compact[:72].rstrip("_")
        return f"{prefix}_{compact or 'empty'}_{digest}"

    def _resolve_motif_grammar_path(self, motif_grammar_path: Optional[str | Path]) -> Optional[Path]:
        if motif_grammar_path is None:
            candidate = Path(DEFAULT_MOTIF_GRAMMAR_PATH)
            return candidate if candidate.exists() else None
        candidate = Path(motif_grammar_path)
        return candidate

    def _role_alignment(
        self,
        selected_motif: str,
        selected_skills: List[PipelineBSelectedSkill],
        resource_nodes: List[PipelineBResourceNode],
        motif_grammar: Optional[MotifGraphGrammarRecord],
    ) -> Dict[str, Any]:
        if motif_grammar is None:
            return {
                "filled_roles": [],
                "missing_roles": [],
                "role_fit_scores": [],
                "required_role_count": 0,
            }

        skill_profiles = self._skill_profiles(selected_skills, resource_nodes)
        role_fit_scores: List[PipelineBRoleFitScore] = []
        filled_roles: List[str] = []
        missing_roles: List[str] = []

        for role in motif_grammar.required_roles:
            fit = self._best_role_fit(role, skill_profiles, selected_motif)
            role_fit_scores.append(fit)
            if fit.status == "filled":
                filled_roles.append(role.role_name)
            else:
                missing_roles.append(role.role_name)

        for role in motif_grammar.optional_roles:
            role_fit_scores.append(self._best_role_fit(role, skill_profiles, selected_motif))

        return {
            "filled_roles": filled_roles,
            "missing_roles": missing_roles,
            "role_fit_scores": role_fit_scores,
            "required_role_count": len(motif_grammar.required_roles),
        }

    def _skill_profiles(
        self,
        selected_skills: List[PipelineBSelectedSkill],
        resource_nodes: List[PipelineBResourceNode],
    ) -> Dict[str, Dict[str, Any]]:
        grouped_resources: Dict[str, Dict[str, Set[str]]] = {}
        for node in resource_nodes:
            skill_bucket = grouped_resources.setdefault(
                node.skill_id,
                {"required": set(), "optional": set(), "provided": set(), "typed": set(), "legacy": set()},
            )
            skill_bucket[node.direction].add(node.resource_type)
            skill_bucket["typed" if node.evidence_mode == "typed" else "legacy"].add(node.resource_type)

        profiles: Dict[str, Dict[str, Any]] = {}
        for skill in selected_skills:
            resources = grouped_resources.get(
                skill.skill_id,
                {"required": set(), "optional": set(), "provided": set(), "typed": set(), "legacy": set()},
            )
            profiles[skill.skill_id] = {
                "skill": skill,
                "required": resources["required"],
                "optional": resources["optional"],
                "provided": resources["provided"],
                "all_resources": set(resources["required"]) | set(resources["optional"]) | set(resources["provided"]),
                "typed": resources["typed"],
                "legacy": resources["legacy"],
            }
        return profiles

    def _best_role_fit(
        self,
        role: MotifRoleDefinition,
        skill_profiles: Dict[str, Dict[str, Any]],
        selected_motif: str,
    ) -> PipelineBRoleFitScore:
        best_score = 0.0
        best_skill_ids: List[str] = []
        best_notes: List[str] = []

        for skill_id, profile in skill_profiles.items():
            skill: PipelineBSelectedSkill = profile["skill"]
            graph_overlap = 1.0 if set(role.typical_graph_roles) & set(skill.graph_role_hints) else 0.0
            all_resources = set(profile["all_resources"])
            provided_resources = set(profile["provided"])
            required_overlap = self._overlap_score(role.required_resource_types, all_resources)
            provided_overlap = self._overlap_score(role.provided_resource_types, provided_resources)
            score = min(1.0, 0.45 * graph_overlap + 0.3 * required_overlap + 0.25 * provided_overlap)
            if selected_motif in skill.motif_hints and score > 0.0:
                score = min(1.0, score + 0.05)

            notes: List[str] = []
            if graph_overlap:
                notes.append("matched_graph_role_hint")
            if required_overlap:
                notes.append("matched_required_resource_types")
            if provided_overlap:
                notes.append("matched_provided_resource_types")
            if profile["legacy"] and not profile["typed"] and score > 0:
                notes.append("legacy_resource_fallback")

            if score > best_score:
                best_score = score
                best_skill_ids = [skill_id]
                best_notes = notes
            elif score > 0 and abs(score - best_score) < 1e-9:
                best_skill_ids.append(skill_id)
                best_notes = sorted(set(best_notes + notes))

        status: RoleFitStatus
        if best_score >= 0.6:
            status = "filled"
        elif best_score >= 0.35:
            status = "partial"
        else:
            status = "missing"

        if not best_notes and not best_skill_ids:
            best_notes = ["no_candidate_skill_match"]

        return PipelineBRoleFitScore(
            role_name=role.role_name,
            role_kind=role.role_kind,
            status=status,
            score=round(best_score, 2),
            matched_skill_ids=sorted(best_skill_ids),
            notes=best_notes,
        )

    def _overlap_score(self, expected: List[str], observed: Set[str]) -> float:
        if not expected:
            return 1.0
        expected_set = {item for item in expected if item}
        if not expected_set:
            return 1.0
        matched = sum(1 for item in expected_set if item in observed)
        return matched / len(expected_set)

    def _workflow_context_fit(
        self,
        motif_grammar: Optional[MotifGraphGrammarRecord],
        selected_skills: List[PipelineBSelectedSkill],
        filled_role_count: int,
        required_role_count: int,
        typed_count: int,
    ) -> WorkflowContextFit:
        if motif_grammar is None or required_role_count == 0 or not selected_skills:
            return "low"
        role_fill_ratio = filled_role_count / max(required_role_count, 1)
        motif_cover_ratio = (
            sum(1 for skill in selected_skills if motif_grammar.motif_type in skill.motif_hints) / len(selected_skills)
        )
        if role_fill_ratio >= 0.8 and motif_cover_ratio >= 0.5 and typed_count > 0:
            return "high"
        if role_fill_ratio >= 0.4:
            return "medium"
        return "low"

    def _task_graph_shape_assumption(
        self,
        motif_grammar: Optional[MotifGraphGrammarRecord],
        selected_motif: str,
        subgraph_edges: List[PipelineBSubgraphEdge],
    ) -> TaskGraphShapeAssumption:
        if motif_grammar is not None:
            return motif_grammar.expected_graph_shape
        evidence_modes = {edge.evidence_mode for edge in subgraph_edges}
        if "typed_resource_match" in evidence_modes and len(subgraph_edges) >= 3:
            return "dag"
        if "role_sequence" in evidence_modes and len(evidence_modes) == 1:
            return "chain"
        if "reconciliation" in selected_motif or "fan_in" in selected_motif:
            return "fan_in"
        return "chain"

    def _role_assignment_fallback_reasons(
        self,
        motif_grammar: Optional[MotifGraphGrammarRecord],
        role_alignment: Dict[str, Any],
        typed_count: int,
        edge_counts: Counter,
    ) -> List[str]:
        reasons: List[str] = []
        if motif_grammar is None:
            reasons.append("motif_grammar_unavailable")
        if typed_count == 0:
            reasons.append("role_matching_under_typed_resource_gaps")
        if edge_counts.get("role_sequence", 0):
            reasons.append("role_sequence_fallback_edges")
        if any(fit.status == "partial" for fit in role_alignment.get("role_fit_scores", [])):
            reasons.append("partial_role_fit_detected")
        return sorted(set(reasons))
