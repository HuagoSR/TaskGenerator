from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file
from task_generator.v3_workflow_episode_proposer import (
    WorkflowEpisodeProposal,
    WorkflowEpisodeProposalReport,
)


ExperimentalStatus = Literal["experimental"]
PrototypeConfidence = Literal["low", "medium", "high"]


ARCHETYPE_SEEDS: List[Dict[str, Any]] = [
    {
        "name": "internal_control_exception_documentation",
        "priority": 50,
        "actor_keywords": ["auditor", "control", "compliance"],
        "trigger_keywords": ["exception", "testing", "supporting evidence", "control"],
        "deliverables": ["memo", "analysis", "workpaper"],
        "motifs": [],
        "constraints": ["exception_handling", "missing_info_escalation"],
        "context_keywords": ["internal control", "audit engagement", "testing"],
    },
    {
        "name": "policy_clause_application_review",
        "priority": 40,
        "actor_keywords": ["compliance", "reviewer", "analyst", "preparer"],
        "trigger_keywords": ["policy", "clause", "regulation", "jurisdiction", "apply"],
        "deliverables": ["review", "memo", "analysis"],
        "motifs": ["policy_application"],
        "constraints": ["jurisdiction_specific_rule"],
        "context_keywords": ["policy", "regulation", "clause", "withholding", "irs"],
    },
    {
        "name": "multi_source_reconciliation_memo",
        "priority": 30,
        "actor_keywords": ["accountant", "analyst", "finance lead", "staff accountant"],
        "trigger_keywords": ["reconcile", "tie out", "variance", "multiple sources"],
        "deliverables": ["memo", "report", "analysis"],
        "motifs": ["fan_in_reconciliation"],
        "constraints": ["cross_period_comparison"],
        "context_keywords": ["reconcile", "variance", "multiple sources", "month-end", "summary"],
    },
    {
        "name": "missing_evidence_escalation_review",
        "priority": 20,
        "actor_keywords": ["auditor", "reviewer", "cfo", "manager"],
        "trigger_keywords": ["missing", "flag", "notify", "before finalizing", "escalate"],
        "deliverables": ["review", "briefing", "memo"],
        "motifs": ["exception_escalation"],
        "constraints": ["missing_info_escalation", "exception_handling"],
        "context_keywords": ["missing information", "notify", "flag", "doesn't match expectations"],
    },
    {
        "name": "evidence_based_manager_briefing",
        "priority": 10,
        "actor_keywords": ["manager", "finance lead", "cfo", "executive"],
        "trigger_keywords": ["decision-making", "executive", "manager", "oversight"],
        "deliverables": ["briefing", "report", "summary"],
        "motifs": [],
        "constraints": ["formatting_expectation"],
        "context_keywords": ["executive", "production company", "decision-making", "oversight", "leadership"],
    },
]


class WorkflowArchetypeRegistryRequest(BaseModel):
    episode_report_paths: List[str] = Field(default_factory=list)
    output_path: str


class WorkflowArchetypeRecord(BaseModel):
    workflow_archetype_id: str
    name: str
    domain: str = "unknown"
    typical_actor_roles: List[str] = Field(default_factory=list)
    trigger_events: List[str] = Field(default_factory=list)
    common_input_artifacts: List[str] = Field(default_factory=list)
    common_motifs: List[str] = Field(default_factory=list)
    common_deliverables: List[str] = Field(default_factory=list)
    typical_constraints: List[str] = Field(default_factory=list)
    source_episode_ids: List[str] = Field(default_factory=list)
    status: ExperimentalStatus = "experimental"
    episode_count: int = 0
    source_count: int = 0
    prototype_confidence: PrototypeConfidence = "low"
    notes: List[str] = Field(default_factory=list)


class WorkflowArchetypeRegistryDiagnostics(BaseModel):
    episode_report_count: int = 0
    input_episode_count: int = 0
    accepted_episode_count: int = 0
    archetype_count: int = 0
    unmatched_episode_count: int = 0
    warning_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class WorkflowArchetypeRegistryArtifact(BaseModel):
    workflow_archetype_registry_version: str = "v3.workflow_archetype_registry.1"
    request: WorkflowArchetypeRegistryRequest
    archetypes: List[WorkflowArchetypeRecord] = Field(default_factory=list)
    diagnostics: WorkflowArchetypeRegistryDiagnostics = Field(
        default_factory=WorkflowArchetypeRegistryDiagnostics
    )
    notes: List[str] = Field(default_factory=list)


class WorkflowArchetypeRegistryBuilder:
    """Build an experimental workflow archetype registry from WorkflowEpisode proposal reports."""

    def build(
        self,
        episode_report_paths: Iterable[str | Path],
        output_path: str | Path,
    ) -> WorkflowArchetypeRegistryArtifact:
        paths = [Path(path) for path in episode_report_paths]
        request = WorkflowArchetypeRegistryRequest(
            episode_report_paths=[str(path) for path in paths],
            output_path=str(output_path),
        )
        reports = [self._load_report(path) for path in paths]
        episodes = [episode for report in reports for episode in report.episodes]
        warning_codes = set()
        notes: List[str] = []

        matches: Dict[str, List[WorkflowEpisodeProposal]] = defaultdict(list)
        unmatched_episodes: List[str] = []
        ambiguous_episode_ids: List[str] = []

        for episode in episodes:
            match_name, ambiguous = self._match_archetype(episode)
            if ambiguous:
                warning_codes.add("ambiguous_episode_match")
                ambiguous_episode_ids.append(episode.workflow_episode_id)
            if match_name is None:
                unmatched_episodes.append(episode.workflow_episode_id)
                continue
            matches[match_name].append(episode)

        if not paths:
            warning_codes.add("no_episode_reports")
            notes.append("No workflow episode proposal reports were provided.")
        if not episodes:
            warning_codes.add("no_episodes_loaded")
            notes.append("Input episode reports contained no episodes.")
        if unmatched_episodes:
            warning_codes.add("unmatched_episodes_present")
            notes.append(
                f"{len(unmatched_episodes)} episodes did not match any seeded workflow archetype."
            )
        if ambiguous_episode_ids:
            notes.append(
                f"{len(ambiguous_episode_ids)} episodes matched multiple seeded archetypes and were resolved by priority."
            )

        archetypes = [
            self._build_archetype_record(seed=seed, episodes=matches.get(seed["name"], []))
            for seed in ARCHETYPE_SEEDS
            if matches.get(seed["name"])
        ]

        diagnostics = WorkflowArchetypeRegistryDiagnostics(
            episode_report_count=len(paths),
            input_episode_count=len(episodes),
            accepted_episode_count=sum(len(group) for group in matches.values()),
            archetype_count=len(archetypes),
            unmatched_episode_count=len(unmatched_episodes),
            warning_codes=sorted(warning_codes),
            notes=self._diagnostic_notes(archetypes, unmatched_episodes, ambiguous_episode_ids),
        )
        artifact = WorkflowArchetypeRegistryArtifact(
            request=request,
            archetypes=archetypes,
            diagnostics=diagnostics,
            notes=notes
            + [
                "This registry is experimental and report-only; it does not change sampler, readiness, transition priors, or task packaging behavior.",
                "Workflow archetypes provide context for future workflow-conditioned sampling and reporting, not fixed task templates.",
            ],
        )
        return artifact

    def write_output(
        self,
        artifact: WorkflowArchetypeRegistryArtifact,
        output_path: str | Path,
    ) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def collect_episode_reports(
        self,
        episode_report_paths: Iterable[str | Path],
        episode_report_dirs: Iterable[str | Path],
    ) -> List[Path]:
        results: List[Path] = []
        seen: set[str] = set()
        for raw_path in episode_report_paths:
            path = Path(raw_path)
            resolved = str(path.resolve()) if path.exists() else str(path)
            if resolved not in seen:
                seen.add(resolved)
                results.append(path)
        for raw_dir in episode_report_dirs:
            directory = Path(raw_dir)
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("workflow_episode_proposal_report.json")):
                resolved = str(path.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    results.append(path)
        return results

    def _load_report(self, path: Path) -> WorkflowEpisodeProposalReport:
        return WorkflowEpisodeProposalReport.model_validate(load_json_file(str(path)))

    def _match_archetype(
        self,
        episode: WorkflowEpisodeProposal,
    ) -> Tuple[Optional[str], bool]:
        scores: List[Tuple[int, int, str]] = []
        for index, seed in enumerate(ARCHETYPE_SEEDS):
            score = self._score_episode_against_seed(episode, seed)
            if score > 0:
                scores.append((score, seed["priority"], seed["name"]))
        if not scores:
            return None, False

        scores.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_score, best_priority, best_name = scores[0]
        ambiguous = len(scores) > 1 and scores[1][0] == best_score and scores[1][1] == best_priority
        return best_name, ambiguous

    def _score_episode_against_seed(self, episode: WorkflowEpisodeProposal, seed: Dict[str, Any]) -> int:
        score = 0
        actor_text = episode.actor_role.lower()
        trigger_text = episode.trigger_event.lower()
        context_text = episode.business_context.lower()
        deliverable_text = episode.deliverable_type.lower()
        motifs = {record.get("motif_type", "") for record in episode.motif_hints}
        constraints = set(episode.observed_constraints)

        if any(keyword in actor_text for keyword in seed["actor_keywords"]):
            score += 2
        if any(keyword in trigger_text for keyword in seed["trigger_keywords"]):
            score += 3
        if any(keyword in context_text for keyword in seed["context_keywords"]):
            score += 2
        if deliverable_text and any(keyword == deliverable_text for keyword in seed["deliverables"]):
            score += 2
        if any(motif in motifs for motif in seed["motifs"]):
            score += 4
        if any(constraint in constraints for constraint in seed["constraints"]):
            score += 2
        return score

    def _build_archetype_record(
        self,
        seed: Dict[str, Any],
        episodes: List[WorkflowEpisodeProposal],
    ) -> WorkflowArchetypeRecord:
        archetype_id = f"wfa_{sha1(seed['name'].encode('utf-8')).hexdigest()[:12]}"
        source_ids = {episode.source_id for episode in episodes if episode.source_id}
        domain = self._mode_or_default([episode.domain for episode in episodes if episode.domain], "unknown")
        actor_roles = self._top_strings([episode.actor_role for episode in episodes if episode.actor_role], 5)
        trigger_events = self._top_strings([episode.trigger_event for episode in episodes if episode.trigger_event], 5)
        input_artifacts = self._top_strings(
            [artifact for episode in episodes for artifact in episode.input_artifacts if artifact],
            8,
        )
        common_motifs = self._top_strings(
            [record.get("motif_type", "") for episode in episodes for record in episode.motif_hints if record.get("motif_type")],
            6,
        )
        deliverables = self._top_strings(
            [episode.deliverable_type for episode in episodes if episode.deliverable_type],
            5,
        )
        constraints = self._top_strings(
            [constraint for episode in episodes for constraint in episode.observed_constraints],
            8,
        )
        source_episode_ids = [episode.workflow_episode_id for episode in episodes]
        prototype_confidence = self._prototype_confidence(episodes, common_motifs, deliverables)
        notes = [
            f"Built from {len(episodes)} workflow episodes using seeded semi-automatic classification.",
        ]
        if not common_motifs:
            notes.append("This archetype currently has no stable motif signal and is supported mainly by context/deliverable heuristics.")

        return WorkflowArchetypeRecord(
            workflow_archetype_id=archetype_id,
            name=seed["name"],
            domain=domain,
            typical_actor_roles=actor_roles,
            trigger_events=trigger_events,
            common_input_artifacts=input_artifacts,
            common_motifs=common_motifs,
            common_deliverables=deliverables,
            typical_constraints=constraints,
            source_episode_ids=source_episode_ids,
            status="experimental",
            episode_count=len(episodes),
            source_count=len(source_ids),
            prototype_confidence=prototype_confidence,
            notes=notes,
        )

    def _prototype_confidence(
        self,
        episodes: List[WorkflowEpisodeProposal],
        common_motifs: List[str],
        deliverables: List[str],
    ) -> PrototypeConfidence:
        if len(episodes) >= 2 and common_motifs and deliverables:
            return "high"
        if len(episodes) >= 1 and (deliverables or common_motifs):
            return "medium"
        return "low"

    def _mode_or_default(self, values: List[str], default: str) -> str:
        if not values:
            return default
        return Counter(values).most_common(1)[0][0]

    def _top_strings(self, values: List[str], limit: int) -> List[str]:
        counter = Counter(value for value in values if value)
        return [value for value, _ in counter.most_common(limit)]

    def _diagnostic_notes(
        self,
        archetypes: List[WorkflowArchetypeRecord],
        unmatched_episode_ids: List[str],
        ambiguous_episode_ids: List[str],
    ) -> List[str]:
        notes = [
            "Archetype classification is seeded and heuristic in V1; unmatched episodes are expected and should guide future coverage expansion.",
            "Archetypes remain contextual workflow summaries and should not be treated as fixed file or prompt templates.",
        ]
        if archetypes:
            notes.append(f"Generated {len(archetypes)} experimental archetypes from matched workflow episodes.")
        if unmatched_episode_ids:
            notes.append(f"Unmatched episodes: {', '.join(unmatched_episode_ids[:5])}")
        if ambiguous_episode_ids:
            notes.append(f"Ambiguous episodes resolved by priority: {', '.join(ambiguous_episode_ids[:5])}")
        return notes
