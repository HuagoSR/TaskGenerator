from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from v3_skill_registry import SkillRegistryBuilder
from v3_skill_reviewer import SkillCandidateReviewer
from v3_source_schema import ExtractedSkillCandidate, load_skill_candidates


BLOCKING_REVIEW_CODES = {
    "broad_documentation_deliverable",
    "broad_control_assessment",
    "weak_action_granularity",
    "task_level_overbreadth",
    "low_atomicity",
    "weak_atomic_action",
}


class CalibrationRegistryAdmissionReviewer:
    """Report-only admission review for graph calibration candidates."""

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()
        self.reviewer = SkillCandidateReviewer()

    def build_report(
        self,
        registry_path: str | Path,
        accepted_candidate_paths: List[str | Path],
    ) -> Dict[str, Any]:
        entries = self.registry_builder.load_registry(registry_path)
        records = []
        for path in accepted_candidate_paths:
            candidate_path = Path(path)
            if not candidate_path.exists():
                records.append(
                    {
                        "source_path": str(candidate_path),
                        "status": "missing_candidate_file",
                        "admission_decision": "do_not_admit",
                        "reason_codes": ["missing_candidate_file"],
                    }
                )
                continue
            for candidate in load_skill_candidates(str(candidate_path)):
                records.append(self._candidate_record(candidate, candidate_path, entries))

        decision_counts = Counter(record.get("admission_decision", "unknown") for record in records)
        reason_counts = Counter(reason for record in records for reason in record.get("reason_codes", []))
        return {
            "admission_report_version": "v3.calibration_registry_admission.1",
            "registry_path": str(registry_path),
            "accepted_candidate_paths": [str(path) for path in accepted_candidate_paths],
            "candidate_count": len([record for record in records if record.get("status") != "missing_candidate_file"]),
            "admission_decision_counts": dict(sorted(decision_counts.items())),
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "records": records,
            "notes": [
                "This report is non-destructive and does not update SkillRegistry/v3_skill_registry.json.",
                "recommend_admit means the candidate looks suitable for a later selected registry update, not that it has been persisted.",
                "merge_existing candidates may still be useful as additional evidence, but should not be counted as new registry growth.",
            ],
        }

    def _candidate_record(
        self,
        candidate: ExtractedSkillCandidate,
        source_path: Path,
        entries: List[Any],
    ) -> Dict[str, Any]:
        review = self.reviewer.review(candidate)
        match = self.registry_builder._find_match(entries, candidate)
        resource_summary = self._resource_summary(candidate)
        reason_codes = set(review.reason_codes)
        admission_decision = "recommend_admit"
        admission_action = "selected_registry_update_candidate"
        duplicate_match = None

        if review.decision != "accept":
            admission_decision = "do_not_admit"
            admission_action = "revise_before_registry_update"
            reason_codes.add(f"review_{review.decision}")
        elif reason_codes & BLOCKING_REVIEW_CODES:
            admission_decision = "manual_review_before_admit"
            admission_action = "inspect_atomicity_and_scope"
        elif not resource_summary["has_required_resources"] or not resource_summary["has_provided_resources"]:
            admission_decision = "manual_review_before_admit"
            admission_action = "complete_resource_contract"
            reason_codes.add("incomplete_typed_resource_contract")

        if match is not None:
            entry, match_reason, match_score = match
            duplicate_match = {
                "skill_id": entry.skill_id,
                "canonical_name": entry.canonical_name,
                "match_reason": match_reason,
                "match_score": round(match_score, 4),
            }
            if admission_decision == "recommend_admit":
                admission_decision = "merge_existing"
                admission_action = "merge_as_additional_evidence"
            reason_codes.add("matches_existing_registry_entry")

        return {
            "status": "reviewed",
            "source_path": str(source_path),
            "candidate_id": candidate.candidate_id,
            "proposed_name": candidate.proposed_name,
            "domain_tags": candidate.domain_tags,
            "capability_tags": candidate.capability_tags,
            "review_decision": review.decision,
            "review_total_score": review.scores.total_score,
            "admission_decision": admission_decision,
            "admission_action": admission_action,
            "reason_codes": sorted(reason_codes),
            "duplicate_match": duplicate_match,
            "resource_summary": resource_summary,
            "common_deliverables": candidate.common_deliverables,
            "assembly_hints": candidate.assembly_hints,
        }

    def _resource_summary(self, candidate: ExtractedSkillCandidate) -> Dict[str, Any]:
        required = candidate.input_contract.required_resources
        optional = candidate.input_contract.optional_resources
        provided = candidate.output_contract.provided_resources
        resource_types = sorted(
            {
                resource.resource_type
                for resource in [*required, *optional, *provided]
                if resource.resource_type
            }
        )
        return {
            "required_resource_count": len(required),
            "optional_resource_count": len(optional),
            "provided_resource_count": len(provided),
            "has_required_resources": bool(required),
            "has_provided_resources": bool(provided),
            "resource_types": resource_types,
        }
