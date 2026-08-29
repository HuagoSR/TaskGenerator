"""Deterministic, report-only R10 Scenario-First static admission."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from task_generator.core.scenario_first import (
    EvidenceProjectionPlanV1,
    ScenarioBibleV1,
    ScenarioFirstAdmissionFindingV1,
    ScenarioFirstAdmissionReportV1,
    TaskDecisionMatrixV1,
    WorkSeedV1,
    ProfessionalRuleSetV1,
)


_LEAKAGE_TOKENS = {
    "questionable", "exception", "requires follow up", "requires follow-up",
    "requires_follow_up", "answer", "correct treatment",
}


class ScenarioFirstAdmissionValidator:
    """Validates contract relationships without materializing candidate files."""

    def evaluate(
        self,
        *,
        work_seed: WorkSeedV1,
        rule_set: ProfessionalRuleSetV1,
        bible: ScenarioBibleV1,
        projection: EvidenceProjectionPlanV1,
        matrix: TaskDecisionMatrixV1,
        known_skill_ids: Iterable[str],
    ) -> ScenarioFirstAdmissionReportV1:
        findings: list[ScenarioFirstAdmissionFindingV1] = []
        add = lambda category, passed, reason_code, **details: findings.append(
            ScenarioFirstAdmissionFindingV1(
                finding_id=f"finding_{len(findings) + 1:03d}", category=category,
                passed=passed, reason_code=reason_code, details=details,
            )
        )

        input_sha256 = self._input_sha256(work_seed, rule_set, bible, projection, matrix)
        trace_ok = bool(work_seed.public_sources) and all(
            source.block_ids and source.locator.startswith("https://")
            for source in work_seed.public_sources
        )
        add("source_traceability", trace_ok, "source_traceability_complete" if trace_ok else "missing_public_source_trace")

        rule_ids = {rule.rule_id for rule in rule_set.rules}
        role_ids = {role.role_id for role in bible.roles}
        authorities_by_role = {role.role_id: set(role.authorities) for role in bible.roles}
        fact_ids = {fact.fact_id for fact in bible.facts}
        bible_refs_ok = (
            bible.work_seed_id == work_seed.seed_id
            and bible.rule_set_id == rule_set.rule_set_id
            and all(not fact.actor_role_id or fact.actor_role_id in role_ids for fact in bible.facts)
            and all(
                not fact.authority_required
                or (fact.actor_role_id is not None and fact.authority_required in authorities_by_role[fact.actor_role_id])
                for fact in bible.facts
            )
            and all(set(fact.rule_ids) <= rule_ids for fact in bible.facts)
        )
        temporal_ok = self._timeline_is_feasible(bible)
        add("world_consistency", bible_refs_ok and temporal_ok,
            "world_consistent" if bible_refs_ok and temporal_ok else "world_reference_or_timeline_invalid")

        artifacts_by_id = {artifact.artifact_id: artifact for artifact in projection.artifacts}
        projected_records = [record for artifact in projection.artifacts for record in artifact.records]
        all_fact_refs_ok = all(set(record.fact_ids) <= fact_ids for record in projected_records)
        roles_ok = all(artifact.producer_role_id in role_ids for artifact in projection.artifacts)
        artifact_count_ok = 4 <= len(projection.artifacts) <= 7
        record_count_ok = 20 <= len(projected_records) <= 60
        normal_count = sum(record.record_class == "normal" for record in projected_records)
        normal_majority = normal_count > len(projected_records) / 2
        projection_ok = (
            projection.scenario_id == bible.scenario_id and all_fact_refs_ok and roles_ok
            and artifact_count_ok and record_count_ok and normal_majority
        )
        add("projection_integrity", projection_ok,
            "projection_integrity_complete" if projection_ok else "projection_shape_or_fact_reference_invalid",
            artifact_count=len(projection.artifacts), record_count=len(projected_records), normal_record_count=normal_count)

        leaked = self._leaked_tokens(projection)
        add("answer_leakage", not leaked, "no_answer_label_leakage" if not leaked else "answer_label_leakage", tokens=sorted(leaked))

        teacher_only_text = {
            value.strip().casefold()
            for value in bible.correct_treatments
            if value.strip()
        }
        visible_strings = {
            value.strip().casefold()
            for artifact in projection.artifacts
            for record in artifact.records
            for value in record.values.values()
            if isinstance(value, str) and value.strip()
        }
        direct_teacher_leak = sorted(teacher_only_text & visible_strings)
        add("isolation", not direct_teacher_leak,
            "candidate_teacher_isolation_complete" if not direct_teacher_leak else "teacher_only_treatment_leaked",
            leaked_values=direct_teacher_leak)

        record_index = {
            (artifact.artifact_id, record.record_id): record
            for artifact in projection.artifacts for record in artifact.records
        }
        skill_ids = set(known_skill_ids)
        decisions = matrix.decision_points
        decision_shape_ok = 3 <= len(decisions) <= 5 and matrix.scenario_id == bible.scenario_id
        references_ok = all(
            all(
                (ref.artifact_id, ref.record_id) in record_index
                and set(ref.field_names) <= set(record_index[(ref.artifact_id, ref.record_id)].values)
                and set(ref.field_names) <= set(artifacts_by_id[ref.artifact_id].candidate_visible_fields)
                for ref in point.evidence_refs
            )
            and set(point.rule_ids) <= rule_ids
            and set(point.skill_ids) <= skill_ids
            for point in decisions
        )
        decision_ok = decision_shape_ok and references_ok
        add("decision_coverage", decision_ok,
            "decision_coverage_complete" if decision_ok else "decision_reference_or_count_invalid")

        uncertainty_required = any(fact.knowledge == "unresolved" for fact in bible.facts)
        uncertainty_ok = not uncertainty_required or any(
            point.allowed_uncertainty_conclusions for point in decisions
        )
        add("solvability", uncertainty_ok,
            "solvability_complete" if uncertainty_ok else "unresolved_fact_requires_uncertainty_conclusion")

        decision = "pass" if all(item.passed for item in findings) else "blocked"
        return ScenarioFirstAdmissionReportV1(
            scenario_id=bible.scenario_id, decision=decision, input_sha256=input_sha256, findings=findings,
        )

    @staticmethod
    def _timeline_is_feasible(bible: ScenarioBibleV1) -> bool:
        # Facts may share a business timestamp, but an anomaly cannot precede
        # every referenced normal business fact in this first static contract.
        normal_times = [item.occurred_at for item in bible.facts if item.kind == "normal_background"]
        anomaly_times = [item.occurred_at for item in bible.facts if item.kind == "anomaly"]
        if normal_times and anomaly_times and min(anomaly_times) < min(normal_times):
            return False
        treatment_times = [item.occurred_at for item in bible.facts if item.kind == "treatment"]
        return not anomaly_times or not treatment_times or min(treatment_times) >= max(anomaly_times)

    @staticmethod
    def _leaked_tokens(projection: EvidenceProjectionPlanV1) -> set[str]:
        tokens: set[str] = set()
        for artifact in projection.artifacts:
            candidates = list(artifact.candidate_visible_fields)
            for record in artifact.records:
                candidates.extend(str(key) for key in record.values)
                candidates.extend(value for value in record.values.values() if isinstance(value, str))
            for value in candidates:
                normalized = value.replace("_", " ").strip().casefold()
                if normalized in _LEAKAGE_TOKENS:
                    tokens.add(normalized)
        return tokens

    @staticmethod
    def _input_sha256(*models: object) -> str:
        payload = [model.model_dump(mode="json", exclude_none=False) for model in models]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
