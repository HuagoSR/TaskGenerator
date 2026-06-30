import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from task_generator.v3_skill_registry import SkillRegistryBuilder
from task_generator.v3_skill_registry_audit import SkillRegistryAuditor
from task_generator.v3_source_schema import SkillRegistryEntry, load_json_file, load_skill_candidates


ReadinessDecision = str


class RegistrySamplingReadinessAssessor:
    """Report-only bridge from Pipeline A registry governance to future Pipeline B sampling."""

    blocking_audit_decisions = {"quarantine_recommended", "revise_recommended"}
    caution_audit_decisions = {"keep_pending_manual_review", "manual_review_needed"}
    blocking_calibration_decisions = {"revise", "reject"}
    caution_reason_codes = {
        "web_source_batch_governance_attention",
        "stale_due_to_reviewer_calibration",
        "manual_review_needed",
    }
    blocking_reason_codes = {
        "source_collection_leakage",
        "broad_deliverable_or_task_level",
        "visual_or_presentation_deliverable",
        "weak_atomic_action",
        "broad_documentation_deliverable",
        "broad_control_assessment",
        "weak_action_granularity",
        "task_level_overbreadth",
        "low_atomicity",
    }

    def __init__(self, repo_root: Optional[str | Path] = None) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
        self.registry_builder = SkillRegistryBuilder()
        self.auditor = SkillRegistryAuditor()

    def assess(
        self,
        registry_path: str | Path,
        audit_report_paths: Optional[List[str | Path]] = None,
        calibration_report_paths: Optional[List[str | Path]] = None,
    ) -> Dict[str, Any]:
        registry_path = Path(registry_path)
        entries = self.registry_builder.load_registry(registry_path)
        audit_by_skill = self._load_audit_records(audit_report_paths or [])
        calibration_by_ref, calibration_by_name = self._load_calibration_records(
            calibration_report_paths or []
        )

        records = [
            self._assess_entry(entry, audit_by_skill, calibration_by_ref, calibration_by_name)
            for entry in entries
        ]
        decision_counts = Counter(record["readiness_decision"] for record in records)
        reason_counts = Counter(reason for record in records for reason in record["reason_codes"])
        domain_counts = self._decision_by_tag(records, "domain_tags")
        capability_counts = self._decision_by_tag(records, "capability_tags")

        return {
            "readiness_version": "v3.registry_sampling_readiness.1",
            "registry_path": str(registry_path),
            "audit_report_paths": [str(path) for path in (audit_report_paths or [])],
            "calibration_report_paths": [str(path) for path in (calibration_report_paths or [])],
            "registry_entry_count": len(entries),
            "readiness_decision_counts": dict(sorted(decision_counts.items())),
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "domain_readiness_counts": domain_counts,
            "capability_readiness_counts": capability_counts,
            "records": records,
            "notes": [
                "This report is non-destructive and does not modify SkillRegistryEntry records.",
                "Decisions are sampling governance hints for future Pipeline B, not ground-truth skill quality labels.",
                "Pipeline B should default to sample_ready entries, downweight sample_with_caution entries, and avoid exclude_until_revised entries.",
            ],
        }

    def _assess_entry(
        self,
        entry: SkillRegistryEntry,
        audit_by_skill: Dict[str, List[Dict[str, Any]]],
        calibration_by_ref: Dict[str, List[Dict[str, Any]]],
        calibration_by_name: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        reason_codes: Set[str] = set()
        evidence_ref_count = len(entry.evidence_refs)
        source_candidate_count = len(entry.source_candidate_ids)
        usage_count = entry.stats.usage_count

        if evidence_ref_count == 0:
            reason_codes.add("missing_evidence_refs")
        if source_candidate_count == 0:
            reason_codes.add("missing_source_candidate_refs")
        if usage_count <= 1:
            reason_codes.add("single_source_support")
        if not self.auditor._has_atomic_signal(entry):
            reason_codes.add("weak_atomic_action")

        audit_records = audit_by_skill.get(entry.skill_id, [])
        for record in audit_records:
            reason_codes.update(record.get("reason_codes", []))
            decision = record.get("audit_decision", "")
            if decision:
                reason_codes.add(f"audit_{decision}")

        calibration_records = self._calibration_records_for_entry(
            entry,
            calibration_by_ref,
            calibration_by_name,
        )
        for record in calibration_records:
            reason_codes.update(record.get("reason_codes", []))
            decision = record.get("new_decision", "")
            if decision in self.blocking_calibration_decisions:
                reason_codes.add(f"calibration_{decision}")

        decision = self._readiness_decision(reason_codes, audit_records, calibration_records)
        sampling_weight = self._sampling_weight(decision, reason_codes)
        return {
            "skill_id": entry.skill_id,
            "canonical_name": entry.canonical_name,
            "readiness_decision": decision,
            "sampling_weight": sampling_weight,
            "reason_codes": sorted(reason_codes),
            "suggested_sampling_action": self._suggested_sampling_action(decision, reason_codes),
            "domain_tags": entry.domain_tags,
            "capability_tags": entry.capability_tags,
            "difficulty_tags": entry.difficulty_tags,
            "evidence_ref_count": evidence_ref_count,
            "source_candidate_id_count": source_candidate_count,
            "usage_count": usage_count,
            "audit_signal_count": len(audit_records),
            "calibration_signal_count": len(calibration_records),
            "source_candidate_ids": entry.source_candidate_ids,
        }

    def _readiness_decision(
        self,
        reason_codes: Set[str],
        audit_records: List[Dict[str, Any]],
        calibration_records: List[Dict[str, Any]],
    ) -> ReadinessDecision:
        if reason_codes & self.blocking_reason_codes:
            return "exclude_until_revised"
        if any(record.get("audit_decision") in self.blocking_audit_decisions for record in audit_records):
            return "exclude_until_revised"
        if any(record.get("new_decision") in self.blocking_calibration_decisions for record in calibration_records):
            return "exclude_until_revised"
        if reason_codes & self.caution_reason_codes:
            return "sample_with_caution"
        if any(record.get("audit_decision") in self.caution_audit_decisions for record in audit_records):
            return "sample_with_caution"
        return "sample_ready"

    def _sampling_weight(self, decision: ReadinessDecision, reason_codes: Set[str]) -> float:
        if decision == "sample_ready":
            return 0.8 if "single_source_support" in reason_codes else 1.0
        if decision == "sample_with_caution":
            return 0.35 if "single_source_support" in reason_codes else 0.5
        return 0.0

    def _suggested_sampling_action(self, decision: ReadinessDecision, reason_codes: Set[str]) -> str:
        if decision == "sample_ready":
            if "single_source_support" in reason_codes:
                return "Eligible for default Pipeline B sampling with provenance visible; prefer higher support when available."
            return "Eligible for default Pipeline B sampling."
        if decision == "sample_with_caution":
            if "web_source_batch_governance_attention" in reason_codes:
                return "Downweight and inspect before using in Pipeline B because this came from a calibrated web-source batch."
            if "single_source_support" in reason_codes:
                return "Downweight until the skill is supported by another source batch or GDPVal prompt batch."
            return "Use only in exploratory Pipeline B batches with report-visible provenance."
        if "source_collection_leakage" in reason_codes:
            return "Do not sample as a task skill; reframe as source collection or evidence-normalization infrastructure."
        if reason_codes & {"broad_deliverable_or_task_level", "broad_documentation_deliverable", "broad_control_assessment"}:
            return "Do not sample until decomposed into smaller semantic input-output skills."
        if "weak_atomic_action" in reason_codes:
            return "Do not sample until renamed or decomposed into a single reusable action."
        return "Exclude from Pipeline B sampling until manually revised."

    def _load_audit_records(self, paths: List[str | Path]) -> Dict[str, List[Dict[str, Any]]]:
        by_skill: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for path in paths:
            report_path = self._resolve_path(path)
            if not report_path.exists():
                continue
            payload = load_json_file(str(report_path))
            for record in payload.get("records", []):
                skill_id = record.get("skill_id")
                if skill_id:
                    by_skill[skill_id].append(record)
        return by_skill

    def _load_calibration_records(
        self,
        paths: List[str | Path],
    ) -> tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        by_ref: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for path in paths:
            report_path = self._resolve_path(path)
            if not report_path.exists():
                continue
            payload = load_json_file(str(report_path))
            for record in payload.get("records", []):
                proposed_name = record.get("proposed_name", "")
                if proposed_name:
                    by_name[proposed_name.strip().lower()].append(record)
                candidate_ref = self._candidate_ref_from_calibration_record(record)
                if candidate_ref:
                    by_ref[candidate_ref].append(record)
        return by_ref, by_name

    def _candidate_ref_from_calibration_record(self, record: Dict[str, Any]) -> str:
        source_path = record.get("source_path")
        candidate_id = record.get("candidate_id")
        proposed_name = record.get("proposed_name")
        if not source_path or not candidate_id or not proposed_name:
            return ""
        candidate_path = self._resolve_path(source_path)
        if not candidate_path.exists():
            return ""
        for candidate in load_skill_candidates(str(candidate_path)):
            if candidate.candidate_id == candidate_id and candidate.proposed_name == proposed_name:
                return self.registry_builder._candidate_ref(candidate)
        return ""

    def _calibration_records_for_entry(
        self,
        entry: SkillRegistryEntry,
        calibration_by_ref: Dict[str, List[Dict[str, Any]]],
        calibration_by_name: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        seen = set()
        for source_ref in entry.source_candidate_ids:
            for record in calibration_by_ref.get(source_ref, []):
                key = (record.get("source_path"), record.get("candidate_id"), record.get("proposed_name"))
                if key not in seen:
                    seen.add(key)
                    records.append(record)
        for record in calibration_by_name.get(entry.canonical_name.strip().lower(), []):
            key = (record.get("source_path"), record.get("candidate_id"), record.get("proposed_name"))
            if key not in seen:
                seen.add(key)
                records.append(record)
        return records

    def _decision_by_tag(self, records: List[Dict[str, Any]], field_name: str) -> Dict[str, Dict[str, int]]:
        counts: Dict[str, Counter[str]] = defaultdict(Counter)
        for record in records:
            for tag in record.get(field_name, []):
                counts[tag].update([record["readiness_decision"]])
        return {tag: dict(sorted(counter.items())) for tag, counter in sorted(counts.items())}

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.repo_root / candidate


def default_existing_reports(repo_root: str | Path) -> Dict[str, List[Path]]:
    root = Path(repo_root)
    registry_dir = root / "SkillRegistry"
    audit_names = [
        "v3_skill_registry_audit_report.json",
        "v3_web_source_registry_audit_report.json",
    ]
    calibration_names = [
        "v3_skill_reviewer_calibration_report.json",
    ]
    return {
        "audit_report_paths": [registry_dir / name for name in audit_names if (registry_dir / name).exists()],
        "calibration_report_paths": [
            registry_dir / name for name in calibration_names if (registry_dir / name).exists()
        ],
    }


def write_sampling_readiness_report(path: str | Path, report: Dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

