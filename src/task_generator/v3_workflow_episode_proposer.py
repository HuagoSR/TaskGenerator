from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import (
    ExtractedSkillCandidate,
    NormalizedSource,
    SemanticResource,
    SkillExtractionPromptPackage,
    SkillMotifHint,
    SkillTraceEdge,
    load_json_file,
    load_skill_candidates,
    load_skill_motif_hints,
    load_skill_trace_edges,
)


EpisodeConfidence = Literal["low", "medium", "high"]
EpisodeReviewStatus = Literal["proposed"]
StepType = Literal["consume_or_analyze", "transform", "synthesize_or_deliver"]


ROLE_PATTERNS = [
    re.compile(
        r"\bYou are (?:an?|the) (?P<role>.+?)(?:\s+and\s+as part of|\s+and\s+are\s+responsible for|[.,\n])",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bAs (?!follows\b)(?:our\s+)?(?P<role>.+?)(?:,|\s+you(?:'|’)re|\s+you are|[.\n])",
        re.IGNORECASE,
    ),
]
TRIGGER_PATTERNS = [
    re.compile(r"\btasked with (?P<trigger>[^.\n]+)", re.IGNORECASE),
    re.compile(r"\basked to (?P<trigger>[^.\n]+)", re.IGNORECASE),
    re.compile(r"\bresponsible for (?P<trigger>[^.\n]+)", re.IGNORECASE),
]
KEYWORD_TRIGGERS = [
    "exception",
    "month-end",
    "review",
    "prepare",
    "reconcile",
    "testing",
]
DELIVERABLE_KEYWORDS = [
    "memo",
    "report",
    "workbook",
    "spreadsheet",
    "schedule",
    "form",
    "briefing",
    "analysis",
]
CONSTRAINT_KEYWORDS = {
    "reconciliation_required": ["reconcile", "reconciliation", "tie out"],
    "cross_period_comparison": ["quarter", "month-end", "year-to-date", "variance"],
    "jurisdiction_specific_rule": ["jurisdiction", "irs", "country", "tax withholding", "regulation"],
    "coverage_requirement": ["ensure coverage", "across all", "coverage", "representative subset"],
    "formatting_expectation": ["formatting", "professional", "easy to read", "header"],
    "exception_handling": ["exception", "flag", "notify", "missing information", "inconsistencies"],
    "missing_info_escalation": ["missing information", "notify", "before finalizing", "doesn't match expectations"],
}


class WorkflowEpisodeProposalRequest(BaseModel):
    prompt_package_path: str
    candidates_path: str
    trace_edges_path: Optional[str] = None
    motif_hints_path: Optional[str] = None
    graph_diagnostics_path: Optional[str] = None
    output_dir: str


class WorkflowEpisodeStep(BaseModel):
    step_id: str
    step_type: StepType
    candidate_id: str
    skill_name: str
    role_hint: str
    input_resources: List[Dict[str, Any]] = Field(default_factory=list)
    output_resources: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class WorkflowEpisodeProposal(BaseModel):
    workflow_episode_id: str
    source_id: str
    normalized_source_id: str = ""
    title: str = ""
    domain: str = ""
    business_context: str = ""
    actor_role: str = ""
    trigger_event: str = ""
    input_artifacts: List[str] = Field(default_factory=list)
    steps: List[WorkflowEpisodeStep] = Field(default_factory=list)
    motif_hints: List[Dict[str, Any]] = Field(default_factory=list)
    deliverable_type: str = ""
    observed_constraints: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: EpisodeConfidence = "low"
    review_status: EpisodeReviewStatus = "proposed"


class WorkflowEpisodeProposalDiagnostics(BaseModel):
    source_count: int = 0
    candidate_count: int = 0
    trace_edge_count: int = 0
    motif_hint_count: int = 0
    episode_count: int = 0
    low_confidence_episode_count: int = 0
    orphan_candidate_count: int = 0
    missing_source_count: int = 0
    warning_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class WorkflowEpisodeProposalReport(BaseModel):
    workflow_episode_proposal_version: str = "v3.workflow_episode_proposal.1"
    request: WorkflowEpisodeProposalRequest
    episodes: List[WorkflowEpisodeProposal] = Field(default_factory=list)
    diagnostics: WorkflowEpisodeProposalDiagnostics = Field(
        default_factory=WorkflowEpisodeProposalDiagnostics
    )
    notes: List[str] = Field(default_factory=list)


class WorkflowEpisodeProposer:
    """Build report-only WorkflowEpisode proposals from existing Pipeline A extraction artifacts."""

    def build(
        self,
        prompt_package_path: str | Path,
        candidates_path: str | Path,
        output_dir: str | Path,
        trace_edges_path: Optional[str | Path] = None,
        motif_hints_path: Optional[str | Path] = None,
        graph_diagnostics_path: Optional[str | Path] = None,
    ) -> WorkflowEpisodeProposalReport:
        request = WorkflowEpisodeProposalRequest(
            prompt_package_path=str(prompt_package_path),
            candidates_path=str(candidates_path),
            trace_edges_path=str(trace_edges_path) if trace_edges_path else None,
            motif_hints_path=str(motif_hints_path) if motif_hints_path else None,
            graph_diagnostics_path=str(graph_diagnostics_path) if graph_diagnostics_path else None,
            output_dir=str(output_dir),
        )

        prompt_package = SkillExtractionPromptPackage.model_validate(load_json_file(str(prompt_package_path)))
        candidates = load_skill_candidates(str(candidates_path))
        trace_edges = self._load_optional_trace_edges(trace_edges_path)
        motif_hints = self._load_optional_motif_hints(motif_hints_path)
        graph_diagnostics = self._load_optional_json(graph_diagnostics_path)

        source_by_id = {source.source_id: source for source in prompt_package.normalized_sources}
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        motifs_by_candidate = self._motifs_by_candidate(motif_hints)

        warning_codes: Set[str] = set()
        notes: List[str] = []
        missing_source_candidate_ids: List[str] = []
        orphan_candidate_count = 0
        episodes: List[WorkflowEpisodeProposal] = []

        candidates_by_source: Dict[str, List[ExtractedSkillCandidate]] = defaultdict(list)
        for candidate in candidates:
            source_ids = candidate.source_ids or [e.source_id for e in candidate.evidence if e.source_id]
            if not source_ids:
                missing_source_candidate_ids.append(candidate.candidate_id)
                orphan_candidate_count += 1
                continue
            assigned = False
            for source_id in source_ids:
                if source_id in source_by_id:
                    candidates_by_source[source_id].append(candidate)
                    assigned = True
            if not assigned:
                missing_source_candidate_ids.append(candidate.candidate_id)
                orphan_candidate_count += 1

        if missing_source_candidate_ids:
            warning_codes.add("missing_source_mapping")
            notes.append(
                f"{len(missing_source_candidate_ids)} candidates could not be mapped to a prompt-package source."
            )

        for source_id, source_candidates in candidates_by_source.items():
            source = source_by_id[source_id]
            source_trace_edges = self._source_trace_edges(source_candidates, trace_edges)
            if len(source_candidates) > 1 and not source_trace_edges:
                warning_codes.add("missing_trace_structure")

            for component_ids in self._components_for_source(source_candidates, source_trace_edges):
                ordered_candidates, component_edges = self._ordered_component(
                    component_ids,
                    source_candidates,
                    source_trace_edges,
                    candidate_by_id,
                )
                episode = self._build_episode(
                    source=source,
                    ordered_candidates=ordered_candidates,
                    component_edges=component_edges,
                    motifs_by_candidate=motifs_by_candidate,
                )
                episodes.append(episode)

        diagnostics = WorkflowEpisodeProposalDiagnostics(
            source_count=len(prompt_package.normalized_sources),
            candidate_count=len(candidates),
            trace_edge_count=len(trace_edges),
            motif_hint_count=len(motif_hints),
            episode_count=len(episodes),
            low_confidence_episode_count=sum(1 for episode in episodes if episode.confidence == "low"),
            orphan_candidate_count=orphan_candidate_count,
            missing_source_count=len(missing_source_candidate_ids),
            warning_codes=sorted(warning_codes),
            notes=self._diagnostic_notes(
                prompt_package=prompt_package,
                trace_edges=trace_edges,
                motif_hints=motif_hints,
                graph_diagnostics=graph_diagnostics,
            ),
        )
        report = WorkflowEpisodeProposalReport(
            request=request,
            episodes=episodes,
            diagnostics=diagnostics,
            notes=notes + [
                "This report is proposal-only and does not mutate SkillRegistry or upstream extraction artifacts.",
                "WorkflowEpisode V1 is derived heuristically from source metadata, extracted candidates, local trace edges, and motif hints.",
                "Low-confidence episodes should remain visible for review rather than being filtered out silently.",
            ],
        )
        return report

    def write_outputs(
        self,
        report: WorkflowEpisodeProposalReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        proposals_path = output_path / "workflow_episode_proposals.json"
        report_path = output_path / "workflow_episode_proposal_report.json"
        proposals_path.write_text(
            self._dump_json({"episodes": [episode.model_dump(mode="json") for episode in report.episodes]}),
            encoding="utf-8",
        )
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "workflow_episode_proposals_path": str(proposals_path),
            "workflow_episode_proposal_report_path": str(report_path),
        }

    def _build_episode(
        self,
        source: NormalizedSource,
        ordered_candidates: List[ExtractedSkillCandidate],
        component_edges: List[SkillTraceEdge],
        motifs_by_candidate: Dict[str, List[SkillMotifHint]],
    ) -> WorkflowEpisodeProposal:
        actor_role = self._actor_role(source)
        trigger_event = self._trigger_event(source)
        deliverable_type = self._deliverable_type(source, ordered_candidates)
        business_context = self._business_context(source, ordered_candidates, actor_role, trigger_event)
        motif_hints = self._episode_motifs(ordered_candidates, motifs_by_candidate)
        observed_constraints = self._observed_constraints(source, ordered_candidates)
        evidence_refs = sorted(
            {
                evidence.evidence_id
                for candidate in ordered_candidates
                for evidence in candidate.evidence
                if evidence.evidence_id
            }
        )
        input_artifacts = self._input_artifacts(source, ordered_candidates)
        steps = [
            self._step(index=index, candidate=candidate)
            for index, candidate in enumerate(ordered_candidates, start=1)
        ]
        confidence = self._confidence(
            source=source,
            steps=steps,
            actor_role=actor_role,
            business_context=business_context,
            deliverable_type=deliverable_type,
            has_trace=bool(component_edges),
            has_motif=bool(motif_hints),
        )
        domain = source.domain_tags[0] if source.domain_tags else (
            ordered_candidates[0].domain_tags[0] if ordered_candidates and ordered_candidates[0].domain_tags else ""
        )
        episode_seed = "|".join([source.source_id] + [candidate.candidate_id for candidate in ordered_candidates])
        return WorkflowEpisodeProposal(
            workflow_episode_id=f"wfep_{sha1(episode_seed.encode('utf-8')).hexdigest()[:12]}",
            source_id=source.source_id,
            normalized_source_id=source.normalized_source_id,
            title=source.title,
            domain=domain,
            business_context=business_context,
            actor_role=actor_role,
            trigger_event=trigger_event,
            input_artifacts=input_artifacts,
            steps=steps,
            motif_hints=motif_hints,
            deliverable_type=deliverable_type,
            observed_constraints=observed_constraints,
            evidence_refs=evidence_refs,
            confidence=confidence,
            review_status="proposed",
        )

    def _step(self, index: int, candidate: ExtractedSkillCandidate) -> WorkflowEpisodeStep:
        input_resources = self._resource_payloads(
            candidate.input_contract.required_resources,
            candidate.input_contract.requires_semantics,
        )
        output_resources = self._resource_payloads(
            candidate.output_contract.provided_resources,
            candidate.output_contract.provides_semantics,
        )
        role_hint = self._role_hint(candidate, input_resources, output_resources)
        evidence_refs = sorted({evidence.evidence_id for evidence in candidate.evidence if evidence.evidence_id})
        notes = list(candidate.assembly_hints[:2])
        return WorkflowEpisodeStep(
            step_id=f"step_{index:02d}_{candidate.candidate_id}",
            step_type=role_hint,
            candidate_id=candidate.candidate_id,
            skill_name=candidate.proposed_name,
            role_hint=role_hint,
            input_resources=input_resources,
            output_resources=output_resources,
            evidence_refs=evidence_refs,
            notes=notes,
        )

    def _resource_payloads(
        self,
        typed_resources: List[SemanticResource],
        legacy_semantics: List[str],
    ) -> List[Dict[str, Any]]:
        if typed_resources:
            return [resource.model_dump(mode="json") for resource in typed_resources]
        return [
            {
                "resource_type": "LegacySemantic",
                "subtype": semantic,
                "attributes": {},
                "domain": "",
                "evidence_refs": [],
            }
            for semantic in legacy_semantics
        ]

    def _role_hint(
        self,
        candidate: ExtractedSkillCandidate,
        input_resources: List[Dict[str, Any]],
        output_resources: List[Dict[str, Any]],
    ) -> StepType:
        input_count = len(input_resources)
        output_count = len(output_resources)
        text = " ".join(
            [
                candidate.proposed_name,
                " ".join(candidate.common_deliverables),
                " ".join(candidate.output_contract.provides_semantics),
            ]
        ).lower()
        if output_count > 0 and ("report" in text or "memo" in text or "workbook" in text or "form" in text):
            return "synthesize_or_deliver"
        if input_count > 0 and output_count > 0:
            return "transform"
        return "consume_or_analyze"

    def _business_context(
        self,
        source: NormalizedSource,
        ordered_candidates: List[ExtractedSkillCandidate],
        actor_role: str,
        trigger_event: str,
    ) -> str:
        text = self._source_text(source)
        if text:
            first_sentence = self._first_sentence(text)
            if first_sentence:
                return first_sentence
        candidate_meanings = [candidate.business_meaning for candidate in ordered_candidates if candidate.business_meaning]
        if candidate_meanings:
            summary = "; ".join(candidate_meanings[:2])
            return summary[:280]
        parts = [part for part in [actor_role, trigger_event, source.title] if part]
        return " | ".join(parts)[:280]

    def _actor_role(self, source: NormalizedSource) -> str:
        text = self._source_text(source)
        for pattern in ROLE_PATTERNS:
            match = pattern.search(text)
            if match:
                candidate = self._clean_phrase(match.group("role"))
                if self._looks_like_actor_role(candidate):
                    return candidate
        return ""

    def _trigger_event(self, source: NormalizedSource) -> str:
        text = self._source_text(source)
        for pattern in TRIGGER_PATTERNS:
            match = pattern.search(text)
            if match:
                return self._clean_phrase(match.group("trigger"))
        lower_text = text.lower()
        for keyword in KEYWORD_TRIGGERS:
            if keyword in lower_text:
                return keyword
        return ""

    def _deliverable_type(
        self,
        source: NormalizedSource,
        ordered_candidates: List[ExtractedSkillCandidate],
    ) -> str:
        for candidate in ordered_candidates:
            for deliverable in candidate.common_deliverables:
                match = self._match_keyword(deliverable, DELIVERABLE_KEYWORDS)
                if match:
                    return match
        match = self._match_keyword(self._source_text(source), DELIVERABLE_KEYWORDS)
        if match:
            return match
        return ""

    def _input_artifacts(
        self,
        source: NormalizedSource,
        ordered_candidates: List[ExtractedSkillCandidate],
    ) -> List[str]:
        artifacts = [artifact.description or artifact.path for artifact in source.detected_artifacts if artifact.path]
        if artifacts:
            return sorted(set(artifacts))
        inferred = set()
        for candidate in ordered_candidates:
            for resource in candidate.input_contract.required_resources:
                label = resource.subtype or resource.resource_type
                if label:
                    inferred.add(label)
            for semantic in candidate.input_contract.requires_semantics:
                if semantic:
                    inferred.add(semantic)
        return sorted(inferred)

    def _episode_motifs(
        self,
        ordered_candidates: List[ExtractedSkillCandidate],
        motifs_by_candidate: Dict[str, List[SkillMotifHint]],
    ) -> List[Dict[str, Any]]:
        seen_keys: Set[Tuple[str, Tuple[str, ...], str]] = set()
        records: List[Dict[str, Any]] = []
        for candidate in ordered_candidates:
            for hint in motifs_by_candidate.get(candidate.candidate_id, []):
                key = (hint.motif_type, tuple(sorted(hint.candidate_ids)), hint.summary)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                records.append(
                    {
                        "motif_type": hint.motif_type,
                        "candidate_ids": hint.candidate_ids,
                        "evidence_block_ids": hint.evidence_block_ids,
                        "confidence": hint.confidence,
                        "reason_codes": hint.reason_codes,
                        "summary": hint.summary,
                    }
                )
        return records

    def _observed_constraints(
        self,
        source: NormalizedSource,
        ordered_candidates: List[ExtractedSkillCandidate],
    ) -> List[str]:
        text_parts = [self._source_text(source)]
        for candidate in ordered_candidates:
            text_parts.append(candidate.hidden_difficulty)
            text_parts.extend(candidate.common_failure_modes)
        blob = " ".join(part for part in text_parts if part).lower()
        constraints = []
        for label, keywords in CONSTRAINT_KEYWORDS.items():
            if any(keyword in blob for keyword in keywords):
                constraints.append(label)
        return sorted(set(constraints))

    def _confidence(
        self,
        source: NormalizedSource,
        steps: List[WorkflowEpisodeStep],
        actor_role: str,
        business_context: str,
        deliverable_type: str,
        has_trace: bool,
        has_motif: bool,
    ) -> EpisodeConfidence:
        has_source_metadata = bool(source.source_id and source.normalized_source_id and source.title)
        stable_fields = sum(1 for item in [business_context, actor_role, deliverable_type] if item)
        if has_source_metadata and len(steps) >= 2 and (has_trace or has_motif):
            return "high"
        if has_source_metadata and steps and stable_fields >= 2:
            return "medium"
        return "low"

    def _components_for_source(
        self,
        source_candidates: List[ExtractedSkillCandidate],
        source_trace_edges: List[SkillTraceEdge],
    ) -> List[Set[str]]:
        candidate_ids = {candidate.candidate_id for candidate in source_candidates}
        if not source_trace_edges:
            return [{candidate.candidate_id} for candidate in source_candidates]

        adjacency: Dict[str, Set[str]] = {candidate_id: set() for candidate_id in candidate_ids}
        for edge in source_trace_edges:
            if edge.from_candidate_id in candidate_ids and edge.to_candidate_id in candidate_ids:
                adjacency[edge.from_candidate_id].add(edge.to_candidate_id)
                adjacency[edge.to_candidate_id].add(edge.from_candidate_id)

        visited: Set[str] = set()
        components: List[Set[str]] = []
        for candidate in source_candidates:
            candidate_id = candidate.candidate_id
            if candidate_id in visited:
                continue
            queue = deque([candidate_id])
            component: Set[str] = set()
            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                queue.extend(sorted(adjacency.get(current, set()) - visited))
            components.append(component)
        return components

    def _ordered_component(
        self,
        component_ids: Set[str],
        source_candidates: List[ExtractedSkillCandidate],
        source_trace_edges: List[SkillTraceEdge],
        candidate_by_id: Dict[str, ExtractedSkillCandidate],
    ) -> Tuple[List[ExtractedSkillCandidate], List[SkillTraceEdge]]:
        index_by_id = {candidate.candidate_id: index for index, candidate in enumerate(source_candidates)}
        component_edges = [
            edge
            for edge in source_trace_edges
            if edge.from_candidate_id in component_ids and edge.to_candidate_id in component_ids
        ]
        if not component_edges:
            ordered_ids = sorted(component_ids, key=lambda candidate_id: index_by_id.get(candidate_id, 10**9))
            return [candidate_by_id[candidate_id] for candidate_id in ordered_ids], []

        incoming_count = Counter(edge.to_candidate_id for edge in component_edges)
        outgoing_ids: Dict[str, List[str]] = defaultdict(list)
        for edge in component_edges:
            outgoing_ids[edge.from_candidate_id].append(edge.to_candidate_id)
        for values in outgoing_ids.values():
            values.sort(key=lambda candidate_id: index_by_id.get(candidate_id, 10**9))

        queue = [
            candidate_id
            for candidate_id in sorted(component_ids, key=lambda cid: index_by_id.get(cid, 10**9))
            if incoming_count.get(candidate_id, 0) == 0
        ]
        ordered_ids: List[str] = []
        incoming_left = Counter(incoming_count)
        while queue:
            current = queue.pop(0)
            if current in ordered_ids:
                continue
            ordered_ids.append(current)
            for neighbor in outgoing_ids.get(current, []):
                incoming_left[neighbor] -= 1
                if incoming_left[neighbor] <= 0:
                    queue.append(neighbor)
            queue.sort(key=lambda cid: index_by_id.get(cid, 10**9))

        remaining = [
            candidate_id
            for candidate_id in sorted(component_ids, key=lambda cid: index_by_id.get(cid, 10**9))
            if candidate_id not in ordered_ids
        ]
        ordered_ids.extend(remaining)
        return [candidate_by_id[candidate_id] for candidate_id in ordered_ids], component_edges

    def _source_trace_edges(
        self,
        source_candidates: List[ExtractedSkillCandidate],
        trace_edges: List[SkillTraceEdge],
    ) -> List[SkillTraceEdge]:
        candidate_ids = {candidate.candidate_id for candidate in source_candidates}
        return [
            edge
            for edge in trace_edges
            if edge.from_candidate_id in candidate_ids and edge.to_candidate_id in candidate_ids
        ]

    def _motifs_by_candidate(self, motif_hints: List[SkillMotifHint]) -> Dict[str, List[SkillMotifHint]]:
        mapping: Dict[str, List[SkillMotifHint]] = defaultdict(list)
        for hint in motif_hints:
            for candidate_id in hint.candidate_ids:
                mapping[candidate_id].append(hint)
        return mapping

    def _diagnostic_notes(
        self,
        prompt_package: SkillExtractionPromptPackage,
        trace_edges: List[SkillTraceEdge],
        motif_hints: List[SkillMotifHint],
        graph_diagnostics: Optional[Dict[str, Any]],
    ) -> List[str]:
        notes = [
            "Episode grouping uses source-local trace-edge connected components when available.",
            "Candidates without trace edges fall back to single-step proposals to preserve source-grounded workflow hints.",
        ]
        if not trace_edges and len(prompt_package.normalized_sources) > 0:
            notes.append("No trace edges were provided; all proposals were built from source-local fallback ordering.")
        if not motif_hints:
            notes.append("No motif hints were provided; episode motif fields are empty but proposals remain valid.")
        if graph_diagnostics:
            warning_count = len(graph_diagnostics.get("warnings", []))
            notes.append(f"Upstream graph extraction diagnostics were available with {warning_count} warnings.")
        return notes

    def _source_text(self, source: NormalizedSource) -> str:
        return "\n".join(block.text for block in source.blocks if block.text)

    def _first_sentence(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if not compact:
            return ""
        sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0]
        return sentence[:280]

    def _clean_phrase(self, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip(" \t\n\r-,:;.")
        for marker in [
            " and as part of ",
            " and are responsible for ",
            " and you are responsible for ",
            " and as ",
        ]:
            marker_index = cleaned.lower().find(marker)
            if marker_index > 0:
                cleaned = cleaned[:marker_index]
                break
        return cleaned[:160]

    def _match_keyword(self, text: str, keywords: List[str]) -> str:
        lower_text = text.lower()
        for keyword in keywords:
            if keyword in lower_text:
                return keyword
        return ""

    def _looks_like_actor_role(self, candidate: str) -> bool:
        lower_candidate = candidate.lower()
        if not candidate:
            return False
        if lower_candidate.startswith("of "):
            return False
        if "header" in lower_candidate:
            return False
        if re.search(r"\d", candidate) and ("as of" in lower_candidate or "/" in candidate):
            return False
        return True

    def _load_optional_json(self, path: Optional[str | Path]) -> Optional[Dict[str, Any]]:
        if path is None or not Path(path).exists():
            return None
        return load_json_file(str(path))

    def _load_optional_trace_edges(self, path: Optional[str | Path]) -> List[SkillTraceEdge]:
        if path is None or not Path(path).exists():
            return []
        return load_skill_trace_edges(str(path))

    def _load_optional_motif_hints(self, path: Optional[str | Path]) -> List[SkillMotifHint]:
        if path is None or not Path(path).exists():
            return []
        return load_skill_motif_hints(str(path))

    def _dump_json(self, payload: Dict[str, Any]) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, indent=2)
