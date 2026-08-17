from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from pathlib import Path
from typing import Any

from task_generator.v3_validity_utility import (
    RubricCriterionPairAuditV1,
    RubricPlanV2,
    RubricScoringAuthorityAuditV1,
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def _json_sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class RubricScoringAuthorityAuditor:
    """Deterministically separate weighted rubric criteria from trace-only bindings."""

    def compile(
        self,
        *,
        rubric_plan_path: str | Path,
        rubric_binding_plan_path: str | Path,
        case_id: str | None = None,
    ) -> RubricScoringAuthorityAuditV1:
        rubric = RubricPlanV2.model_validate_json(
            Path(rubric_plan_path).read_text(encoding="utf-8")
        )
        bindings = json.loads(Path(rubric_binding_plan_path).read_text(encoding="utf-8"))
        criteria = sorted(rubric.criteria, key=lambda item: item.criterion_id)
        criterion_ids = [item.criterion_id for item in criteria]
        unique_criteria = []
        seen_criterion_ids: set[str] = set()
        for criterion in criteria:
            if criterion.criterion_id not in seen_criterion_ids:
                unique_criteria.append(criterion)
                seen_criterion_ids.add(criterion.criterion_id)
        binding_items = list(bindings.get("bindings") or [])
        binding_ids = sorted(str(item.get("criterion_id") or "") for item in binding_items)
        binding_authority_valid = (
            bindings.get("final_weights_assigned") is False
            and all(
                item.get("scoring_authority") == "program_compiled_binding_not_final_weight"
                for item in binding_items
            )
        )
        pair_audits: list[RubricCriterionPairAuditV1] = []
        signature_rows: list[dict[str, Any]] = []
        for left, right in combinations(unique_criteria, 2):
            shared_skills = sorted(set(left.skill_ids) & set(right.skill_ids))
            shared_capabilities = sorted(set(left.capability_ids) & set(right.capability_ids))
            shared_evidence = sorted(
                set(left.evidence_or_judgment_ids) & set(right.evidence_or_judgment_ids)
            )
            behavior_match = _normalized(left.observable_behavior) == _normalized(right.observable_behavior)
            signal_match = _normalized(left.independent_failure_signal) == _normalized(right.independent_failure_signal)
            deterministic_class = (
                "duplicate_scoring"
                if behavior_match or signal_match
                else "shared_trace_evidence"
                if shared_evidence
                else "distinct"
            )
            pair_audits.append(
                RubricCriterionPairAuditV1(
                    criterion_a=left.criterion_id,
                    criterion_b=right.criterion_id,
                    shared_skill_ids=shared_skills,
                    shared_capability_ids=shared_capabilities,
                    shared_evidence_or_judgment_ids=shared_evidence,
                    observable_behavior_exact_match=behavior_match,
                    independent_failure_signal_exact_match=signal_match,
                    deterministic_class=deterministic_class,
                )
            )
            signature_rows.append(
                {
                    "criterion_a": left.criterion_id,
                    "criterion_b": right.criterion_id,
                    "shared_skill": bool(shared_skills),
                    "shared_capability": bool(shared_capabilities),
                    "shared_evidence": bool(shared_evidence),
                    "behavior_exact": behavior_match,
                    "signal_exact": signal_match,
                    "class": deterministic_class,
                }
            )
        duplicate_ids = _duplicates(criterion_ids)
        duplicate_signals = _duplicates(
            [_normalized(item.independent_failure_signal) for item in criteria]
        )
        duplicate_behaviors = _duplicates(
            [_normalized(item.observable_behavior) for item in criteria]
        )
        actual_weight = sum(item.weight for item in criteria)
        factual_weight = sum(
            item.weight for item in criteria if item.dimension == "factual_accuracy"
        )
        weight_sum_valid = abs(actual_weight - 1.0) <= 1e-6
        criterion_count_valid = len(criteria) == 7 and len(set(criterion_ids)) == 7
        rubric_metadata_valid = bool(
            rubric.decision == "pass"
            and abs(rubric.total_weight - actual_weight) <= 1e-6
            and abs(rubric.factual_weight_ratio - factual_weight) <= 1e-6
            and rubric.effective_dimension_count
            == len({item.dimension for item in criteria})
            == 7
        )
        semantic_rows = [
            {
                "criterion_id": item.criterion_id,
                "dimension": item.dimension,
                "axis": item.axis,
                "weight": round(item.weight, 9),
                "observable_behavior": _normalized(item.observable_behavior),
                "independent_failure_signal": _normalized(
                    item.independent_failure_signal
                ),
            }
            for item in criteria
        ]
        reasons: list[str] = []
        if duplicate_ids:
            reasons.append("duplicate_final_criterion_ids")
        if duplicate_signals:
            reasons.append("duplicate_independent_failure_signals")
        if duplicate_behaviors:
            reasons.append("duplicate_observable_behaviors")
        if not weight_sum_valid:
            reasons.append("final_weight_sum_invalid")
        if not criterion_count_valid:
            reasons.append("final_criterion_count_or_identity_invalid")
        if not rubric_metadata_valid:
            reasons.append("rubric_weight_or_dimension_metadata_invalid")
        if not binding_authority_valid:
            reasons.append("annotation_binding_scoring_authority_invalid")
        return RubricScoringAuthorityAuditV1(
            case_id=case_id or rubric.case_id,
            final_scoring_criterion_ids=criterion_ids,
            final_scoring_criteria_count=len(criterion_ids),
            annotation_binding_ids=binding_ids,
            annotation_bindings_count=len(binding_ids),
            annotation_bindings_non_scoring=binding_authority_valid,
            pair_audits=pair_audits,
            structure_signature=_json_sha(signature_rows),
            scoring_semantic_signature=_json_sha(semantic_rows),
            duplicate_criterion_ids=duplicate_ids,
            duplicate_failure_signals=duplicate_signals,
            duplicate_observable_behaviors=duplicate_behaviors,
            weight_sum_valid=weight_sum_valid,
            criterion_count_valid=criterion_count_valid,
            rubric_metadata_valid=rubric_metadata_valid,
            binding_authority_valid=binding_authority_valid,
            decision="blocked" if reasons else "pass",
            blocking_reasons=reasons,
        )
