import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from v3_skill_registry import SkillRegistryBuilder
from v3_skill_reviewer import SkillCandidateReviewer
from v3_source_schema import SkillRegistryEntry, load_json_file


class SkillRegistryAuditor:
    """Non-destructive audit helper for persistent registry governance."""

    weak_atomic_noun_pattern = re.compile(
        r"\b(analysis|assessment|articulation|aggregation|calculation|computation|modeling|evaluation|"
        r"identification|formulation|validation|configuration|benchmarking|correlation|optimization|"
        r"summarization|comparison)\b",
        re.IGNORECASE,
    )
    visual_deliverable_pattern = re.compile(
        r"\b(presentation|slides?|slide\s+deck|deck|visualizations?|charts?|graphics?)\b",
        re.IGNORECASE,
    )
    profile_deliverable_pattern = re.compile(
        r"\b(company\s+profiles?|profiles?\s+for|compile\s+.*profiles?)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()
        self.reviewer = SkillCandidateReviewer()

    def load_unmatched_skill_ids(self, update_report_path: str | Path) -> Set[str]:
        report_path = Path(update_report_path)
        if not report_path.exists():
            raise FileNotFoundError(f"Registry update report not found: {report_path}")
        payload = load_json_file(str(report_path))
        return {
            str(item.get("skill_id", ""))
            for item in payload.get("unmatched_existing_entries", [])
            if item.get("skill_id")
        }

    def audit_registry(
        self,
        registry_path: str | Path,
        update_report_path: Optional[str | Path] = None,
        include_all: bool = False,
    ) -> Dict[str, Any]:
        entries = self.registry_builder.load_registry(registry_path)
        unmatched_ids: Set[str] = set()
        if update_report_path is not None and Path(update_report_path).exists():
            unmatched_ids = self.load_unmatched_skill_ids(update_report_path)
        elif not include_all:
            raise FileNotFoundError(
                "Auditing only unmatched entries requires an update report with unmatched_existing_entries."
            )

        target_entries = entries if include_all else [entry for entry in entries if entry.skill_id in unmatched_ids]
        records = [self.audit_entry(entry, is_unmatched=entry.skill_id in unmatched_ids) for entry in target_entries]
        decision_counts = Counter(record["audit_decision"] for record in records)
        reason_counts = Counter(reason for record in records for reason in record["reason_codes"])
        return {
            "audit_version": "v3.registry_audit.1",
            "registry_path": str(registry_path),
            "update_report_path": str(update_report_path) if update_report_path is not None else None,
            "include_all": include_all,
            "registry_entry_count": len(entries),
            "audited_entry_count": len(records),
            "unmatched_entry_count": len(unmatched_ids),
            "audit_decision_counts": dict(sorted(decision_counts.items())),
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "records": records,
            "notes": [
                "This audit is non-destructive: it does not delete, rewrite, deactivate, or quarantine registry entries.",
                "Audit decisions are deterministic governance hints, not ground-truth skill quality labels.",
            ],
        }

    def audit_entry(self, entry: SkillRegistryEntry, is_unmatched: bool) -> Dict[str, Any]:
        text = self._entry_text(entry)
        reason_codes: List[str] = []

        if is_unmatched:
            reason_codes.append("stale_due_to_reviewer_calibration")
        if self.reviewer.source_collection_pattern.search(text):
            reason_codes.append("source_collection_leakage")
        if (
            self.reviewer.broad_deliverable_pattern.search(entry.canonical_name)
            or any(term in text for term in self.reviewer.task_level_terms)
            or self.profile_deliverable_pattern.search(text)
        ):
            reason_codes.append("broad_deliverable_or_task_level")
        if self.visual_deliverable_pattern.search(text):
            reason_codes.append("visual_or_presentation_deliverable")
        if not self._has_atomic_signal(entry):
            reason_codes.append("weak_atomic_action")
        if not reason_codes:
            reason_codes.append("manual_review_needed")

        return {
            "skill_id": entry.skill_id,
            "canonical_name": entry.canonical_name,
            "audit_decision": self._audit_decision(reason_codes),
            "reason_codes": sorted(set(reason_codes)),
            "suggested_action": self._suggested_action(reason_codes),
            "suggested_abstraction": self._suggested_abstraction(entry, reason_codes),
            "evidence_summary": self._evidence_summary(entry),
        }

    def _entry_text(self, entry: SkillRegistryEntry) -> str:
        parts: Iterable[str] = [
            entry.canonical_name,
            " ".join(entry.domain_tags),
            " ".join(entry.capability_tags),
            " ".join(entry.difficulty_tags),
            entry.business_meaning,
            entry.hidden_difficulty,
            " ".join(entry.failure_modes),
            " ".join(entry.assembly_hints),
            " ".join(entry.evidence_refs),
        ]
        return " ".join(parts).lower()

    def _has_atomic_signal(self, entry: SkillRegistryEntry) -> bool:
        contract_text = " ".join(
            entry.input_contract.requires_semantics
            + entry.input_contract.optional_semantics
            + entry.input_contract.provides_semantics
            + entry.output_contract.requires_semantics
            + entry.output_contract.optional_semantics
            + entry.output_contract.provides_semantics
        )
        text = f"{entry.canonical_name} {' '.join(entry.capability_tags)} {contract_text}"
        return bool(
            any(term in text.lower() for term in self.reviewer.atomic_action_terms)
            or self.weak_atomic_noun_pattern.search(text)
        )

    def _audit_decision(self, reason_codes: List[str]) -> str:
        reason_set = set(reason_codes)
        if reason_set & {
            "source_collection_leakage",
            "broad_deliverable_or_task_level",
            "visual_or_presentation_deliverable",
        }:
            return "quarantine_recommended"
        if "weak_atomic_action" in reason_set:
            return "revise_recommended"
        if "stale_due_to_reviewer_calibration" in reason_set:
            return "keep_pending_manual_review"
        return "manual_review_needed"

    def _suggested_action(self, reason_codes: List[str]) -> str:
        reason_set = set(reason_codes)
        if "source_collection_leakage" in reason_set:
            return "Do not sample this entry for Pipeline B; re-extract as source normalization or evidence handling skill."
        if "visual_or_presentation_deliverable" in reason_set:
            return "Do not sample as an atomic skill until revised into evidence-to-insight or visualization validation subskills."
        if "broad_deliverable_or_task_level" in reason_set:
            return "Keep for historical trace only; decompose into smaller semantic input-output skills before sampling."
        if "weak_atomic_action" in reason_set:
            return "Manually inspect and rename or decompose before using as a registry sampling unit."
        return "Manual review needed before treating this entry as registry-ready."

    def _suggested_abstraction(self, entry: SkillRegistryEntry, reason_codes: List[str]) -> str:
        text = self._entry_text(entry)
        name = entry.canonical_name.lower()
        reason_set = set(reason_codes)
        if "source_collection_leakage" in reason_set:
            return "Source Evidence Normalization From Candidate-Visible Materials"
        if "visual_or_presentation_deliverable" in reason_set:
            return "Evidence-to-Executive-Insight Structuring or Visualization Consistency Validation"
        if "broad_deliverable_or_task_level" in reason_set and "question" in name:
            return "Compliance Criterion Mapping or Risk-Control Coverage Selection"
        if "broad_deliverable_or_task_level" in reason_set and any(term in name for term in ["profile", "market"]):
            return "Entity Attribute Extraction or Comparable Entity Evidence Mapping"
        if "broad_deliverable_or_task_level" in reason_set and any(term in text for term in ["report", "statement"]):
            return "Source-to-Report Metric Mapping or Financial Statement Component Assembly"
        if "weak_atomic_action" in reason_set:
            return "A single reusable action such as mapping, reconciling, validating, resolving, or allocating one semantic input-output pair"
        return ""

    def _evidence_summary(self, entry: SkillRegistryEntry) -> Dict[str, Any]:
        return {
            "evidence_ref_count": len(entry.evidence_refs),
            "evidence_refs": entry.evidence_refs[:10],
            "source_candidate_id_count": len(entry.source_candidate_ids),
            "source_candidate_ids": entry.source_candidate_ids[:10],
            "usage_count": entry.stats.usage_count,
        }


def write_audit_report(path: str | Path, report: Dict[str, Any]) -> None:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
