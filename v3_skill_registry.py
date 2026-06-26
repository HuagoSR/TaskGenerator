import hashlib
import re
from typing import List

from v3_source_schema import ExtractedSkillCandidate, SkillRegistryEntry


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "skill"


class SkillRegistryBuilder:
    """First-pass registry builder with deterministic name-based deduplication."""

    def build_entries(self, candidates: List[ExtractedSkillCandidate]) -> List[SkillRegistryEntry]:
        merged = {}
        for candidate in candidates:
            key = slugify(candidate.proposed_name)
            if key not in merged:
                merged[key] = self._entry_from_candidate(candidate)
            else:
                self._merge_candidate(merged[key], candidate)
        return list(merged.values())

    def _entry_from_candidate(self, candidate: ExtractedSkillCandidate) -> SkillRegistryEntry:
        evidence_refs = [
            evidence.evidence_id
            for evidence in candidate.evidence
        ]
        return SkillRegistryEntry(
            skill_id=stable_id("skill", slugify(candidate.proposed_name)),
            canonical_name=candidate.proposed_name,
            domain_tags=candidate.domain_tags,
            capability_tags=candidate.capability_tags,
            difficulty_tags=candidate.difficulty_tags,
            input_contract=candidate.input_contract,
            output_contract=candidate.output_contract,
            business_meaning=candidate.business_meaning,
            hidden_difficulty=candidate.hidden_difficulty,
            failure_modes=candidate.common_failure_modes,
            evidence_refs=evidence_refs,
            assembly_hints=candidate.assembly_hints,
            source_candidate_ids=[candidate.candidate_id],
        )

    def _merge_candidate(self, entry: SkillRegistryEntry, candidate: ExtractedSkillCandidate) -> None:
        entry.domain_tags = sorted(set(entry.domain_tags + candidate.domain_tags))
        entry.capability_tags = sorted(set(entry.capability_tags + candidate.capability_tags))
        entry.difficulty_tags = sorted(set(entry.difficulty_tags + candidate.difficulty_tags))
        entry.failure_modes = sorted(set(entry.failure_modes + candidate.common_failure_modes))
        entry.assembly_hints = sorted(set(entry.assembly_hints + candidate.assembly_hints))
        entry.evidence_refs = sorted(
            set(entry.evidence_refs + [evidence.evidence_id for evidence in candidate.evidence])
        )
        entry.source_candidate_ids = sorted(set(entry.source_candidate_ids + [candidate.candidate_id]))

