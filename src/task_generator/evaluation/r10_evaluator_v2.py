"""Rubric-aware, counterbalanced evaluation contracts for R10.10.

The module is deliberately evaluator-only.  It does not mutate a task's
teacher truth or historical rubric.  A campaign profile atomizes that frozen
supervision, deterministic checks handle facts that are actually computable,
and paired LLM reviews retain professional judgement and comparison evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.core.scenario_first import TaskDecisionMatrixV1
from task_generator.planning.scenario_task_compiler import TaskSpecificRubricV1


Rating = Literal["met", "partial", "not_met"]
CriterionKind = Literal["objective_fact", "professional_judgment", "deliverable_quality"]
JudgeId = Literal[
    "gpt-5.6-terra@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "gpt-5.6-luna@chatgpt_codex",
]
SolverId = Literal[
    "gpt-5.6-sol@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "deepseek-v4-flash@official_opencode",
    "gpt-5.6-luna@chatgpt_codex",
]


class RatingAnchorsV2(ScenarioFirstModel):
    met: str = Field(min_length=10)
    partial: str = Field(min_length=10)
    not_met: str = Field(min_length=10)


class AtomicCriterionV2(ScenarioFirstModel):
    criterion_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    parent_decision_id: str = Field(min_length=1)
    kind: CriterionKind
    weight: float = Field(gt=0, le=1)
    requirement: str = Field(min_length=10)
    anchors: RatingAnchorsV2
    deterministic_check_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_checks(self) -> "AtomicCriterionV2":
        if len(self.deterministic_check_ids) != len(set(self.deterministic_check_ids)):
            raise ValueError("atomic_criterion_check_ids_not_unique")
        if self.kind != "objective_fact" and self.deterministic_check_ids:
            raise ValueError("only_objective_criteria_may_bind_deterministic_checks")
        return self


class DeterministicCheckV2(ScenarioFirstModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    criterion_id: str = Field(min_length=1)
    operation: Literal[
        "equals", "within_tolerance", "greater_than", "less_than",
        "date_on_or_before", "date_on_or_after", "required_content",
    ]
    expected_number: float | None = None
    tolerance: float | None = Field(default=None, ge=0)
    expected_date: date | None = None
    expected_text: str | None = None

    @model_validator(mode="after")
    def require_operation_operand(self) -> "DeterministicCheckV2":
        numeric = {"equals", "within_tolerance", "greater_than", "less_than"}
        dates = {"date_on_or_before", "date_on_or_after"}
        if self.operation in numeric and self.expected_number is None:
            raise ValueError("deterministic_numeric_operand_missing")
        if self.operation == "within_tolerance" and self.tolerance is None:
            raise ValueError("deterministic_tolerance_missing")
        if self.operation in dates and self.expected_date is None:
            raise ValueError("deterministic_date_operand_missing")
        if self.operation == "required_content" and not self.expected_text:
            raise ValueError("deterministic_text_operand_missing")
        return self


class MajorErrorRuleV2(ScenarioFirstModel):
    error_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    affected_criterion_ids: list[str] = Field(min_length=1)
    trigger_fact: str = Field(min_length=10)
    necessary_evidence: list[str] = Field(min_length=1)
    business_consequence: str = Field(min_length=10)
    deterministic_check_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_references(self) -> "MajorErrorRuleV2":
        if len(self.affected_criterion_ids) != len(set(self.affected_criterion_ids)):
            raise ValueError("major_error_criterion_ids_not_unique")
        if len(self.deterministic_check_ids) != len(set(self.deterministic_check_ids)):
            raise ValueError("major_error_check_ids_not_unique")
        return self


class EvaluatorProfileV2(ScenarioFirstModel):
    profile_version: Literal["r10.evaluator_profile.2"] = "r10.evaluator_profile.2"
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    task_id: str = Field(min_length=1)
    source_task_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_teacher_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    iteration: Literal["v2.0", "v2.1", "v2.2"]
    criteria: list[AtomicCriterionV2] = Field(min_length=3, max_length=30)
    deterministic_checks: list[DeterministicCheckV2] = Field(default_factory=list)
    major_error_rules: list[MajorErrorRuleV2] = Field(default_factory=list)

    @model_validator(mode="after")
    def close_profile_references(self) -> "EvaluatorProfileV2":
        criterion_ids = [item.criterion_id for item in self.criteria]
        check_ids = [item.check_id for item in self.deterministic_checks]
        error_ids = [item.error_id for item in self.major_error_rules]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("evaluator_criterion_ids_not_unique")
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("evaluator_check_ids_not_unique")
        if len(error_ids) != len(set(error_ids)):
            raise ValueError("evaluator_major_error_ids_not_unique")
        if not math.isclose(sum(item.weight for item in self.criteria), 1.0, abs_tol=1e-6):
            raise ValueError("evaluator_criterion_weights_must_sum_to_one")
        criteria = set(criterion_ids)
        checks = set(check_ids)
        if any(item.criterion_id not in criteria for item in self.deterministic_checks):
            raise ValueError("deterministic_check_criterion_unknown")
        if any(not set(item.deterministic_check_ids) <= checks for item in self.criteria):
            raise ValueError("atomic_criterion_check_unknown")
        for rule in self.major_error_rules:
            if not set(rule.affected_criterion_ids) <= criteria:
                raise ValueError("major_error_criterion_unknown")
            if not set(rule.deterministic_check_ids) <= checks:
                raise ValueError("major_error_check_unknown")
        return self


class DeterministicCheckResultV2(ScenarioFirstModel):
    check_id: str
    passed: bool
    observed: str
    expected: str


class AtomicAssessmentV2(ScenarioFirstModel):
    criterion_id: str
    rating: Rating
    evidence_paths: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=10, max_length=3000)


class AnonymousBundleAssessmentV2(ScenarioFirstModel):
    slot: Literal["slot_1", "slot_2"]
    assessments: list[AtomicAssessmentV2] = Field(min_length=3)
    alleged_major_error_ids: list[str] = Field(default_factory=list)


class CounterbalancedPairReviewV2(ScenarioFirstModel):
    review_version: Literal["r10.counterbalanced_pair_review.2"] = "r10.counterbalanced_pair_review.2"
    task_id: str
    judge_id: JudgeId
    order_id: Literal["a_b", "b_a"]
    preference: Literal["slot_1", "slot_2", "tie"]
    bundles: list[AnonymousBundleAssessmentV2] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_two_complete_slots(self) -> "CounterbalancedPairReviewV2":
        if {item.slot for item in self.bundles} != {"slot_1", "slot_2"}:
            raise ValueError("paired_review_requires_two_slots")
        return self


class SolverStackConfigV1(ScenarioFirstModel):
    solver_id: SolverId
    model: str
    transport: Literal["chatgpt_codex", "official_opencode"]
    reasoning: Literal["none", "medium", "high", "max"]

    @model_validator(mode="after")
    def require_frozen_solver_configuration(self) -> "SolverStackConfigV1":
        expected = {
            "gpt-5.6-sol@chatgpt_codex": ("gpt-5.6-sol", "chatgpt_codex", "none"),
            "deepseek-v4-pro@official_opencode": ("deepseek-v4-pro", "official_opencode", "max"),
            "deepseek-v4-flash@official_opencode": ("deepseek-v4-flash", "official_opencode", "high"),
            "gpt-5.6-luna@chatgpt_codex": ("gpt-5.6-luna", "chatgpt_codex", "medium"),
        }[self.solver_id]
        if (self.model, self.transport, self.reasoning) != expected:
            raise ValueError("r10_10_solver_configuration_not_frozen")
        return self


class CalibrationSplitV1(ScenarioFirstModel):
    split_version: Literal["r10.evaluator_calibration_split.1"] = "r10.evaluator_calibration_split.1"
    r10_development_task_ids: list[str] = Field(min_length=2, max_length=2)
    r10_holdout_task_ids: list[str] = Field(min_length=2, max_length=2)
    gdpval_development_task_ids: list[str] = Field(min_length=6, max_length=6)
    gdpval_holdout_task_ids: list[str] = Field(min_length=6, max_length=6)
    holdout_opened: bool = False

    @model_validator(mode="after")
    def disjoint_splits(self) -> "CalibrationSplitV1":
        groups = [
            self.r10_development_task_ids, self.r10_holdout_task_ids,
            self.gdpval_development_task_ids, self.gdpval_holdout_task_ids,
        ]
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("calibration_split_ids_not_unique")
        if set(groups[0]) & set(groups[1]) or set(groups[2]) & set(groups[3]):
            raise ValueError("calibration_development_holdout_overlap")
        return self


def canonical_sha256(value: Any) -> str:
    if isinstance(value, ScenarioFirstModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def profile_from_frozen_supervision(
    *, task_id: str, task_tree_sha256: str, teacher_tree_sha256: str,
    matrix: TaskDecisionMatrixV1, rubric: TaskSpecificRubricV1,
    iteration: Literal["v2.0", "v2.1", "v2.2"] = "v2.0",
) -> EvaluatorProfileV2:
    """Atomize a frozen R10 decision rubric without changing its semantics.

    Each parent decision yields separate conclusion/evidence/follow-up criteria.
    This deliberately removes document polish from core professional credit.  A
    task may later add explicit deterministic checks, but this conversion never
    pretends that unstructured file facts were verified by code.
    """

    decisions = {item.decision_id: item for item in matrix.decision_points}
    rubric_by_decision = {item.decision_id: item for item in rubric.criteria}
    if set(decisions) != set(rubric_by_decision):
        raise ValueError("evaluator_source_supervision_not_aligned")
    criteria: list[AtomicCriterionV2] = []
    major_rules: list[MajorErrorRuleV2] = []
    for decision_id, decision in decisions.items():
        parent = rubric_by_decision[decision_id]
        stem = _safe_identifier(decision_id)
        splits = (
            ("conclusion", "professional_judgment", 0.50,
             "Reach a professionally supportable conclusion and preserve material uncertainty.",
             "States a supportable conclusion consistent with the visible record.",
             "Reaches the right direction but omits a material limitation or qualification.",
             "Omits the conclusion or reaches an unsupported or contrary conclusion."),
            ("evidence", "objective_fact", 0.30,
             "Use and reconcile the candidate-visible evidence needed for this decision.",
             "Uses the relevant visible evidence accurately and traces the conclusion to it.",
             "Uses some relevant evidence but misses a material source, conflict, or limitation.",
             "Misstates, ignores, or fails to use the evidence needed for the decision."),
            ("follow_up", "professional_judgment", 0.20,
             "Specify proportionate follow-up or escalation that resolves the remaining risk.",
             "Specifies a feasible follow-up that addresses the identified evidence gap or risk.",
             "Suggests a relevant action but does not fully resolve the gap, owner, or consequence.",
             "Provides no consequential follow-up or recommends an action inconsistent with the record."),
        )
        child_ids: list[str] = []
        for suffix, kind, share, requirement, met, partial, not_met in splits:
            criterion_id = f"{stem}_{suffix}"
            child_ids.append(criterion_id)
            criteria.append(AtomicCriterionV2(
                criterion_id=criterion_id, parent_decision_id=decision_id,
                kind=kind, weight=round(parent.weight * share, 10),
                requirement=requirement,
                anchors=RatingAnchorsV2(met=met, partial=partial, not_met=not_met),
            ))
        evidence = sorted({ref.artifact_id for ref in decision.evidence_refs})
        for index, major in enumerate(decision.major_errors, start=1):
            major_rules.append(MajorErrorRuleV2(
                error_id=f"{stem}_major_{index}", affected_criterion_ids=child_ids[:2],
                trigger_fact=major,
                necessary_evidence=evidence,
                business_consequence=(
                    "The work product could cause its intended reviewer to rely on an unsupported "
                    "professional conclusion or omit necessary follow-up."
                ),
            ))
    return EvaluatorProfileV2(
        profile_id=f"{_safe_identifier(task_id)}_{iteration.replace('.', '_')}",
        task_id=task_id, source_task_tree_sha256=task_tree_sha256,
        source_teacher_tree_sha256=teacher_tree_sha256, iteration=iteration,
        criteria=criteria, major_error_rules=major_rules,
    )


def _safe_identifier(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value.casefold())
    normalized = "_".join(filter(None, normalized.split("_")))
    if not normalized or not normalized[0].isalpha():
        normalized = f"item_{normalized}"
    return normalized


def evaluate_deterministic_checks(
    checks: list[DeterministicCheckV2], observations: dict[str, Any],
) -> list[DeterministicCheckResultV2]:
    """Evaluate only supplied structured observations; never infer file facts."""

    results: list[DeterministicCheckResultV2] = []
    for check in checks:
        if check.check_id not in observations:
            results.append(DeterministicCheckResultV2(
                check_id=check.check_id, passed=False, observed="missing", expected=check.operation,
            ))
            continue
        observed = observations[check.check_id]
        if check.operation in {"equals", "within_tolerance", "greater_than", "less_than"}:
            number = float(observed)
            expected = float(check.expected_number)
            if check.operation == "equals":
                passed = math.isclose(number, expected, abs_tol=1e-9)
            elif check.operation == "within_tolerance":
                passed = abs(number - expected) <= float(check.tolerance)
            elif check.operation == "greater_than":
                passed = number > expected
            else:
                passed = number < expected
            expected_text = str(expected)
        elif check.operation in {"date_on_or_before", "date_on_or_after"}:
            observed_date = date.fromisoformat(str(observed))
            expected_date = check.expected_date
            passed = observed_date <= expected_date if check.operation == "date_on_or_before" else observed_date >= expected_date
            expected_text = expected_date.isoformat()
        else:
            needle = str(check.expected_text).casefold()
            passed = needle in str(observed).casefold()
            expected_text = str(check.expected_text)
        results.append(DeterministicCheckResultV2(
            check_id=check.check_id, passed=passed, observed=str(observed), expected=expected_text,
        ))
    return results


def score_bundle(
    *, profile: EvaluatorProfileV2, bundle: AnonymousBundleAssessmentV2,
    deterministic_results: list[DeterministicCheckResultV2] | None = None,
) -> float:
    criteria = {item.criterion_id: item for item in profile.criteria}
    assessments = {item.criterion_id: item for item in bundle.assessments}
    if set(criteria) != set(assessments):
        raise ValueError("evaluator_assessments_do_not_match_profile")
    check_results = {item.check_id: item for item in deterministic_results or []}
    rating_values = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
    score = 0.0
    for criterion_id, criterion in criteria.items():
        rating = assessments[criterion_id].rating
        if criterion.deterministic_check_ids:
            bound = [check_results.get(check_id) for check_id in criterion.deterministic_check_ids]
            if any(item is None for item in bound):
                raise ValueError("evaluator_deterministic_result_missing")
            rating = "met" if all(item.passed for item in bound) else "not_met"
        score += criterion.weight * rating_values[rating]
    return round(score, 6)


def normalize_pair_review(
    review: CounterbalancedPairReviewV2,
) -> dict[str, AnonymousBundleAssessmentV2 | str]:
    by_slot = {item.slot: item for item in review.bundles}
    candidate_for_slot = (
        {"slot_1": "candidate_a", "slot_2": "candidate_b"}
        if review.order_id == "a_b" else
        {"slot_1": "candidate_b", "slot_2": "candidate_a"}
    )
    normalized: dict[str, AnonymousBundleAssessmentV2 | str] = {
        candidate_for_slot[slot]: value for slot, value in by_slot.items()
    }
    normalized["preference"] = (
        "tie" if review.preference == "tie" else candidate_for_slot[review.preference]
    )
    return normalized


def confirm_major_errors(
    *, profile: EvaluatorProfileV2, reviews: list[CounterbalancedPairReviewV2],
    deterministic_results_by_candidate: dict[str, list[DeterministicCheckResultV2]],
) -> dict[str, list[str]]:
    """Confirm majors by deterministic failure or a stable Judge majority.

    Each Judge contributes at most one vote per candidate/error, even when that
    Judge reviewed both presentation orders.
    """

    rules = {item.error_id: item for item in profile.major_error_rules}
    confirmed: dict[str, set[str]] = {"candidate_a": set(), "candidate_b": set()}
    for candidate, results in deterministic_results_by_candidate.items():
        failed = {item.check_id for item in results if not item.passed}
        for rule in rules.values():
            if rule.deterministic_check_ids and set(rule.deterministic_check_ids) <= failed:
                confirmed[candidate].add(rule.error_id)
    votes: dict[tuple[str, str], set[str]] = defaultdict(set)
    judge_ids = {review.judge_id for review in reviews}
    for review in reviews:
        normalized = normalize_pair_review(review)
        for candidate in ("candidate_a", "candidate_b"):
            bundle = normalized[candidate]
            for error_id in bundle.alleged_major_error_ids:
                if error_id not in rules:
                    raise ValueError("paired_review_major_error_unknown")
                votes[(candidate, error_id)].add(review.judge_id)
    majority = len(judge_ids) // 2 + 1
    for (candidate, error_id), voters in votes.items():
        if len(voters) >= majority:
            confirmed[candidate].add(error_id)
    return {key: sorted(value) for key, value in confirmed.items()}


def assess_counterbalance_stability(
    reviews: list[CounterbalancedPairReviewV2],
) -> dict[str, Any]:
    """Report per-Judge order stability without inventing a tiebreaker."""

    by_judge: dict[str, list[CounterbalancedPairReviewV2]] = defaultdict(list)
    for review in reviews:
        by_judge[review.judge_id].append(review)
    judge_results: dict[str, dict[str, Any]] = {}
    for judge, items in by_judge.items():
        preferences = [normalize_pair_review(item)["preference"] for item in items]
        orders = {item.order_id for item in items}
        stable = orders == {"a_b", "b_a"} and len(set(preferences)) == 1
        judge_results[judge] = {"stable": stable, "preferences": preferences, "orders": sorted(orders)}
    return {
        "stable": bool(judge_results) and all(item["stable"] for item in judge_results.values()),
        "judges": judge_results,
    }


def bootstrap_mean_interval(
    values: list[float], *, seed: int, samples: int = 2000, confidence: float = 0.95,
) -> tuple[float, float]:
    if not values:
        raise ValueError("bootstrap_values_required")
    rng = random.Random(seed)
    means = sorted(
        sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples)
    )
    tail = (1 - confidence) / 2
    low = means[max(0, int(samples * tail))]
    high = means[min(samples - 1, int(samples * (1 - tail)) - 1)]
    return round(low, 6), round(high, 6)


def ordinal_agreement(
    observed_wins: dict[str, int], reference_order: list[str],
) -> dict[str, Any]:
    """Compare pairwise direction only; this is intentionally not Elo."""

    common = [model for model in reference_order if model in observed_wins]
    pair_total = 0
    pair_agree = 0
    for index, better in enumerate(common):
        for worse in common[index + 1:]:
            pair_total += 1
            if observed_wins[better] > observed_wins[worse]:
                pair_agree += 1
    return {
        "common_models": common,
        "pair_count": pair_total,
        "agreeing_pairs": pair_agree,
        "agreement": round(pair_agree / pair_total, 6) if pair_total else None,
    }


def luna_solver_required(
    *, main_solver_completed: dict[str, int], pro_flash_indistinguishable: bool,
    ranked_main_models: int,
) -> bool:
    allowed = {
        "gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode",
        "deepseek-v4-flash@official_opencode",
    }
    if set(main_solver_completed) != allowed:
        raise ValueError("main_solver_matrix_incomplete")
    return (
        any(count < 10 for count in main_solver_completed.values())
        or pro_flash_indistinguishable
        or ranked_main_models <= 2
    )
