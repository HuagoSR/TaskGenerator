from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_generator.v3_skill_registry import SkillRegistryBuilder
from task_generator.v3_source_schema import SkillRegistryEntry, load_json_file


TARGET_MOTIFS = [
    "evidence_to_deliverable",
    "cross_check_validation",
    "fan_in_reconciliation",
    "policy_application",
]

TARGET_DOMAINS = {"audit", "compliance", "finance", "accounting", "tax", "reporting"}
BLOCKING_READINESS = {"exclude_until_revised"}


class PipelineBSeedSetBuilder:
    """Report-only selector for the first Pipeline B skill-sampling slice."""

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()

    def build_report(
        self,
        registry_path: str | Path,
        readiness_report_path: str | Path,
        target_count: int = 20,
        caution_limit: int = 5,
    ) -> Dict[str, Any]:
        entries = self.registry_builder.load_registry(registry_path)
        readiness_payload = load_json_file(str(readiness_report_path))
        readiness_by_skill = {
            record.get("skill_id", ""): record
            for record in readiness_payload.get("records", [])
            if record.get("skill_id")
        }
        scored = [
            self._score_entry(entry, readiness_by_skill.get(entry.skill_id, {}))
            for entry in entries
        ]
        selectable = [
            record
            for record in scored
            if record["readiness_decision"] not in BLOCKING_READINESS
        ]
        selectable.sort(key=lambda record: (-record["seed_score"], record["canonical_name"].lower()))

        selected = []
        caution_count = 0
        motif_counts: Counter[str] = Counter()
        domain_counts: Counter[str] = Counter()
        for record in selectable:
            if record["readiness_decision"] == "sample_with_caution":
                if caution_count >= caution_limit:
                    continue
                caution_count += 1
            selected.append(record)
            motif_counts.update(record["motif_hints"])
            domain_counts.update(record["domain_tags"])
            if len(selected) >= target_count:
                break

        excluded = [
            {
                "skill_id": record["skill_id"],
                "canonical_name": record["canonical_name"],
                "readiness_decision": record["readiness_decision"],
                "reason_codes": record["reason_codes"],
                "exclusion_reason": self._exclusion_reason(record),
            }
            for record in scored
            if record not in selected
        ]

        return {
            "seed_set_report_version": "v3.pipeline_b_seed_set.1",
            "registry_path": str(registry_path),
            "readiness_report_path": str(readiness_report_path),
            "target_count": target_count,
            "caution_limit": caution_limit,
            "registry_entry_count": len(entries),
            "selected_count": len(selected),
            "selected_readiness_counts": dict(sorted(Counter(r["readiness_decision"] for r in selected).items())),
            "selected_domain_counts": dict(sorted(domain_counts.items())),
            "selected_motif_counts": dict(sorted(motif_counts.items())),
            "seed_records": selected,
            "excluded_or_deferred_count": len(excluded),
            "excluded_or_deferred_records": excluded,
            "notes": [
                "This report is non-destructive and does not modify SkillRegistryEntry records.",
                "The seed set is a first Pipeline B sampling slice, not a full endorsement of the registry.",
                "Pipeline B should treat sample_with_caution seeds as exploratory and keep provenance visible.",
            ],
        }

    def _score_entry(self, entry: SkillRegistryEntry, readiness: Dict[str, Any]) -> Dict[str, Any]:
        readiness_decision = readiness.get("readiness_decision", "unknown")
        reason_codes = list(readiness.get("reason_codes", []))
        required_count = len(entry.input_contract.required_resources)
        provided_count = len(entry.output_contract.provided_resources)
        optional_count = len(entry.input_contract.optional_resources) + len(entry.output_contract.optional_resources)
        motif_hints = self._motif_hints(entry)
        role_hints = self._role_hints(entry, required_count, provided_count)

        score = 0.0
        score += {"sample_ready": 60.0, "sample_with_caution": 35.0}.get(readiness_decision, 0.0)
        score += min(float(readiness.get("sampling_weight", 0.0)), 1.0) * 15.0
        if required_count:
            score += 8.0
        if provided_count:
            score += 8.0
        if required_count and provided_count:
            score += 6.0
        score += min(optional_count, 2) * 1.0
        score += len(set(entry.domain_tags) & TARGET_DOMAINS) * 1.5
        score += min(len(motif_hints), 2) * 3.0
        score += min(len(role_hints), 2) * 1.5
        if "single_source_support" in reason_codes:
            score -= 3.0
        if readiness_decision == "sample_with_caution":
            score -= 5.0

        resource_types = sorted(
            {
                resource.resource_type
                for resource in [
                    *entry.input_contract.required_resources,
                    *entry.input_contract.optional_resources,
                    *entry.output_contract.provided_resources,
                ]
                if resource.resource_type
            }
        )
        return {
            "skill_id": entry.skill_id,
            "canonical_name": entry.canonical_name,
            "readiness_decision": readiness_decision,
            "sampling_weight": readiness.get("sampling_weight", 0.0),
            "seed_score": round(score, 4),
            "seed_tier": self._seed_tier(readiness_decision, score),
            "domain_tags": entry.domain_tags,
            "capability_tags": entry.capability_tags,
            "difficulty_tags": entry.difficulty_tags,
            "resource_types": resource_types,
            "required_resource_count": required_count,
            "provided_resource_count": provided_count,
            "motif_hints": motif_hints,
            "graph_role_hints": role_hints,
            "reason_codes": reason_codes,
            "selection_rationale": self._selection_rationale(readiness_decision, motif_hints, role_hints, resource_types),
            "risk_notes": self._risk_notes(readiness_decision, reason_codes, required_count, provided_count),
        }

    def _motif_hints(self, entry: SkillRegistryEntry) -> List[str]:
        text = " ".join(
            [
                entry.canonical_name,
                " ".join(entry.capability_tags),
                " ".join(entry.assembly_hints),
                entry.business_meaning,
                entry.hidden_difficulty,
            ]
        ).lower()
        motifs = []
        if any(term in text for term in ["reconcile", "tie", "reconciling", "variance"]):
            motifs.append("fan_in_reconciliation")
        if any(term in text for term in ["validate", "verify", "cross-check", "corroborate", "reperform", "test"]):
            motifs.append("cross_check_validation")
        if any(term in text for term in ["policy", "rule", "requirement", "compliance", "withholding"]):
            motifs.append("policy_application")
        if any(term in text for term in ["report", "deliverable", "document", "memo", "section", "summarize"]):
            motifs.append("evidence_to_deliverable")
        return [motif for motif in TARGET_MOTIFS if motif in motifs]

    def _role_hints(self, entry: SkillRegistryEntry, required_count: int, provided_count: int) -> List[str]:
        text = " ".join([entry.canonical_name, " ".join(entry.capability_tags), entry.business_meaning]).lower()
        roles = []
        if required_count <= 1 and provided_count:
            roles.append("starter")
        if required_count and provided_count:
            roles.append("transform")
        if required_count >= 2:
            roles.append("fan_in")
        if any(term in text for term in ["validate", "verify", "test", "exception", "finding", "classify"]):
            roles.append("validator")
        if any(term in text for term in ["report", "document", "memo", "summarize", "deliverable"]):
            roles.append("synthesis")
        return sorted(set(roles or ["unclassified"]))

    def _seed_tier(self, readiness_decision: str, score: float) -> str:
        if readiness_decision == "sample_ready" and score >= 85:
            return "core"
        if readiness_decision == "sample_ready":
            return "supporting"
        if readiness_decision == "sample_with_caution":
            return "exploratory_caution"
        return "deferred"

    def _selection_rationale(
        self,
        readiness_decision: str,
        motif_hints: List[str],
        role_hints: List[str],
        resource_types: List[str],
    ) -> str:
        parts = [f"readiness={readiness_decision}"]
        if resource_types:
            parts.append(f"resources={','.join(resource_types[:5])}")
        if motif_hints:
            parts.append(f"motifs={','.join(motif_hints)}")
        if role_hints:
            parts.append(f"roles={','.join(role_hints)}")
        return "; ".join(parts)

    def _risk_notes(
        self,
        readiness_decision: str,
        reason_codes: List[str],
        required_count: int,
        provided_count: int,
    ) -> List[str]:
        notes = []
        if readiness_decision == "sample_with_caution":
            notes.append("Use only in exploratory Pipeline B batches.")
        if "single_source_support" in reason_codes:
            notes.append("Single-source support; keep source provenance visible.")
        if not required_count or not provided_count:
            notes.append("Resource contract is incomplete for graph assembly.")
        return notes

    def _exclusion_reason(self, record: Dict[str, Any]) -> str:
        if record["readiness_decision"] in BLOCKING_READINESS:
            return "readiness_excludes_sampling"
        if record["readiness_decision"] == "sample_with_caution":
            return "caution_limit_reached"
        return "lower_seed_score"

