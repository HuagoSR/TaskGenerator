import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from v3_source_schema import ExtractedSkillCandidate, SkillRegistryEntry, SkillRegistryStats, load_json_file


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "skill"


class SkillRegistryBuilder:
    """First-pass registry builder with deterministic name-based deduplication."""

    weak_name_verbs = {
        "apply",
        "build",
        "calculate",
        "compute",
        "consolidate",
        "create",
        "derive",
        "detect",
        "generate",
        "identify",
        "map",
        "prepare",
        "produce",
        "reconcile",
        "select",
        "summarize",
        "validate",
    }

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
            domain_tags=self._normalize_tags(candidate.domain_tags),
            capability_tags=self._normalize_tags(candidate.capability_tags),
            difficulty_tags=self._normalize_tags(candidate.difficulty_tags),
            input_contract=candidate.input_contract,
            output_contract=candidate.output_contract,
            business_meaning=candidate.business_meaning,
            hidden_difficulty=candidate.hidden_difficulty,
            failure_modes=candidate.common_failure_modes,
            evidence_refs=evidence_refs,
            assembly_hints=candidate.assembly_hints,
            stats=SkillRegistryStats(usage_count=1),
            source_candidate_ids=[self._candidate_ref(candidate)],
        )

    def _merge_candidate(self, entry: SkillRegistryEntry, candidate: ExtractedSkillCandidate) -> None:
        candidate_ref = self._candidate_ref(candidate)
        existing_refs = set(entry.source_candidate_ids)
        is_new_candidate = candidate_ref not in existing_refs and candidate.candidate_id not in existing_refs
        entry.domain_tags = self._normalize_tags(entry.domain_tags + candidate.domain_tags)
        entry.capability_tags = self._normalize_tags(entry.capability_tags + candidate.capability_tags)
        entry.difficulty_tags = self._normalize_tags(entry.difficulty_tags + candidate.difficulty_tags)
        entry.failure_modes = sorted(set(entry.failure_modes + candidate.common_failure_modes))
        entry.assembly_hints = sorted(set(entry.assembly_hints + candidate.assembly_hints))
        entry.evidence_refs = sorted(
            set(entry.evidence_refs + [evidence.evidence_id for evidence in candidate.evidence])
        )
        entry.source_candidate_ids = sorted(set(entry.source_candidate_ids + [candidate_ref]))
        if is_new_candidate:
            entry.stats.usage_count += 1

    def load_registry(self, path: str | Path) -> List[SkillRegistryEntry]:
        registry_path = Path(path)
        if not registry_path.exists():
            return []
        payload = load_json_file(str(registry_path))
        if isinstance(payload, dict) and "entries" in payload:
            payload = payload["entries"]
        if not isinstance(payload, list):
            raise ValueError(f"Registry file must contain an entries array: {registry_path}")
        return [self._normalize_entry(SkillRegistryEntry.model_validate(item)) for item in payload]

    def write_registry(self, path: str | Path, entries: List[SkillRegistryEntry]) -> None:
        registry_path = Path(path)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "registry_version": "v3.0",
            "entry_count": len(entries),
            "entries": [entry.model_dump(mode="json") for entry in entries],
        }
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def update_registry(
        self,
        existing_entries: List[SkillRegistryEntry],
        candidates: List[ExtractedSkillCandidate],
    ) -> Tuple[List[SkillRegistryEntry], Dict[str, Any]]:
        entries = [self._normalize_entry(entry.model_copy(deep=True)) for entry in existing_entries]
        report: Dict[str, Any] = {
            "input_candidate_count": len(candidates),
            "existing_entry_count": len(existing_entries),
            "new_entry_count": 0,
            "merged_candidate_count": 0,
            "skipped_candidate_count": 0,
            "final_entry_count": 0,
            "status_counts": {},
            "new_entries": [],
            "merged_candidates": [],
            "skipped_candidates": [],
            "possible_duplicates": [],
            "unmatched_existing_entries": [],
            "unmatched_existing_entry_count": 0,
            "coverage": {},
        }
        touched_skill_ids = set()

        for candidate in candidates:
            status = candidate.extraction_status
            report["status_counts"][status] = report["status_counts"].get(status, 0) + 1
            if status not in {"accepted", "merged"}:
                report["skipped_candidate_count"] += 1
                report["skipped_candidates"].append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "proposed_name": candidate.proposed_name,
                        "status": status,
                        "reason": "only accepted or merged candidates enter the persistent registry",
                    }
                )
                continue

            match = self._find_match(entries, candidate)
            if match is not None:
                entry, match_reason, match_score = match
                self._merge_candidate(entry, candidate)
                report["merged_candidate_count"] += 1
                touched_skill_ids.add(entry.skill_id)
                report["merged_candidates"].append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "proposed_name": candidate.proposed_name,
                        "skill_id": entry.skill_id,
                        "canonical_name": entry.canonical_name,
                        "match_reason": match_reason,
                        "match_score": round(match_score, 4),
                    }
                )
                continue

            near_duplicates = self._possible_duplicates(entries, candidate)
            if near_duplicates:
                report["possible_duplicates"].append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "proposed_name": candidate.proposed_name,
                        "matches": near_duplicates,
                    }
                )

            new_entry = self._entry_from_candidate(candidate)
            entries.append(new_entry)
            touched_skill_ids.add(new_entry.skill_id)
            report["new_entry_count"] += 1
            report["new_entries"].append(
                {
                    "candidate_id": candidate.candidate_id,
                    "proposed_name": candidate.proposed_name,
                    "skill_id": new_entry.skill_id,
                    "canonical_name": new_entry.canonical_name,
                }
            )

        report["final_entry_count"] = len(entries)
        report["unmatched_existing_entries"] = [
            {
                "skill_id": entry.skill_id,
                "canonical_name": entry.canonical_name,
            }
            for entry in entries
            if entry.skill_id not in touched_skill_ids
        ]
        report["unmatched_existing_entry_count"] = len(report["unmatched_existing_entries"])
        report["coverage"] = self.coverage_report(entries)
        return entries, report

    def coverage_report(self, entries: List[SkillRegistryEntry]) -> Dict[str, Any]:
        domain_counts = self._count_tags(entry.domain_tags for entry in entries)
        capability_counts = self._count_tags(entry.capability_tags for entry in entries)
        difficulty_counts = self._count_tags(entry.difficulty_tags for entry in entries)
        low_coverage = [
            tag for tag, count in sorted(capability_counts.items())
            if count == 1
        ][:20]
        return {
            "entry_count": len(entries),
            "domain_tag_counts": domain_counts,
            "capability_tag_counts": capability_counts,
            "difficulty_tag_counts": difficulty_counts,
            "low_coverage_capability_hints": low_coverage,
        }

    def _find_match(
        self,
        entries: List[SkillRegistryEntry],
        candidate: ExtractedSkillCandidate,
    ) -> Optional[Tuple[SkillRegistryEntry, str, float]]:
        candidate_name_key = slugify(candidate.proposed_name)
        candidate_near_name_key = self._near_name_key(candidate.proposed_name)
        candidate_fingerprint = self._candidate_fingerprint(candidate)

        for entry in entries:
            if slugify(entry.canonical_name) == candidate_name_key:
                return entry, "exact_name", 1.0
            if self._near_name_key(entry.canonical_name) == candidate_near_name_key:
                return entry, "near_name", 1.0
            overlap = self._jaccard(self._entry_fingerprint(entry), candidate_fingerprint)
            if overlap >= 0.85 and len(candidate_fingerprint) >= 3:
                return entry, "semantic_fingerprint", overlap
        return None

    def _possible_duplicates(
        self,
        entries: List[SkillRegistryEntry],
        candidate: ExtractedSkillCandidate,
    ) -> List[Dict[str, Any]]:
        candidate_fingerprint = self._candidate_fingerprint(candidate)
        matches = []
        for entry in entries:
            overlap = self._jaccard(self._entry_fingerprint(entry), candidate_fingerprint)
            if 0.55 <= overlap < 0.85:
                matches.append(
                    {
                        "skill_id": entry.skill_id,
                        "canonical_name": entry.canonical_name,
                        "match_reason": "possible_semantic_overlap",
                        "match_score": round(overlap, 4),
                    }
                )
        return matches[:5]

    def _near_name_key(self, name: str) -> str:
        tokens = [token for token in slugify(name).split("_") if token]
        while tokens and tokens[0] in self.weak_name_verbs:
            tokens = tokens[1:]
        return "_".join(tokens) or slugify(name)

    def _candidate_ref(self, candidate: ExtractedSkillCandidate) -> str:
        source_key = ",".join(sorted(candidate.source_ids))
        return stable_id("source_candidate", f"{source_key}::{candidate.candidate_id}::{candidate.proposed_name}")

    def _candidate_fingerprint(self, candidate: ExtractedSkillCandidate) -> set[str]:
        return self._fingerprint(
            candidate.capability_tags,
            candidate.input_contract.requires_semantics,
            candidate.input_contract.optional_semantics,
            candidate.input_contract.provides_semantics,
            candidate.output_contract.requires_semantics,
            candidate.output_contract.optional_semantics,
            candidate.output_contract.provides_semantics,
        )

    def _entry_fingerprint(self, entry: SkillRegistryEntry) -> set[str]:
        return self._fingerprint(
            entry.capability_tags,
            entry.input_contract.requires_semantics,
            entry.input_contract.optional_semantics,
            entry.input_contract.provides_semantics,
            entry.output_contract.requires_semantics,
            entry.output_contract.optional_semantics,
            entry.output_contract.provides_semantics,
        )

    def _fingerprint(self, *groups: List[str]) -> set[str]:
        values = set()
        for group in groups:
            for item in group:
                key = slugify(item)
                if key:
                    values.add(key)
        return values

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _count_tags(self, tag_groups: Iterable[List[str]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for tags in tag_groups:
            for tag in tags:
                normalized = self._normalize_tag(tag)
                if normalized:
                    counts[normalized] = counts.get(normalized, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def _normalize_entry(self, entry: SkillRegistryEntry) -> SkillRegistryEntry:
        entry.domain_tags = self._normalize_tags(entry.domain_tags)
        entry.capability_tags = self._normalize_tags(entry.capability_tags)
        entry.difficulty_tags = self._normalize_tags(entry.difficulty_tags)
        return entry

    def _normalize_tags(self, tags: List[str]) -> List[str]:
        return sorted({normalized for tag in tags if (normalized := self._normalize_tag(tag))})

    def _normalize_tag(self, tag: str) -> str:
        normalized = re.sub(r"\s+", "_", tag.strip().lower())
        normalized = re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")
        return normalized
