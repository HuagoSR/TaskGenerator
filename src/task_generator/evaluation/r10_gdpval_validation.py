"""Public GDPval calibration contracts for the R10.10 evaluator.

GDPval material is evaluation-only.  These contracts deliberately retain the
human-authored rubric items instead of converting them into R10 task-generation
contracts or broad decision points.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from typing import Any, Literal

from pydantic import Field, StrictInt, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel


GDPvalSolverId = Literal[
    "gpt-5.6-sol@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "deepseek-v4-flash@official_opencode",
    "gpt-5.6-luna@chatgpt_codex",
]
GDPvalJudgeId = Literal[
    "gpt-5.6-terra@chatgpt_codex",
    "deepseek-v4-pro@official_opencode",
    "gpt-5.6-luna@chatgpt_codex",
]


class GDPvalRubricItemV1(ScenarioFirstModel):
    rubric_item_id: str = Field(min_length=1)
    score: float = Field(gt=0)
    criterion: str = Field(min_length=3)
    author_type: str = "human"


class GDPvalTaskBindingV1(ScenarioFirstModel):
    binding_version: Literal["r10.gdpval_task_binding.1"] = "r10.gdpval_task_binding.1"
    task_id: str
    sector: str
    occupation: Literal[
        "Accountants and Auditors", "Buyers and Purchasing Agents", "Compliance Officers"
    ]
    split: Literal["development", "holdout"]
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_files: list[str]
    expected_deliverables: list[str] = Field(min_length=1)
    rubric_items: list[GDPvalRubricItemV1] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_and_human_authored(self) -> "GDPvalTaskBindingV1":
        ids = [item.rubric_item_id for item in self.rubric_items]
        if len(ids) != len(set(ids)):
            raise ValueError("gdpval_rubric_item_ids_not_unique")
        if any(item.author_type != "human" for item in self.rubric_items):
            raise ValueError("gdpval_rubric_must_be_human_authored")
        if len(self.expected_deliverables) != len(set(self.expected_deliverables)):
            raise ValueError("gdpval_expected_deliverables_not_unique")
        return self

    def canonical_sha256(self) -> str:
        return canonical_sha256(self)


class GDPvalItemAssessmentV1(ScenarioFirstModel):
    rubric_item_id: str
    rating: Literal["met", "partial", "not_met"]
    evidence_paths: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5, max_length=2000)


class GDPvalAnonymousAssessmentV1(ScenarioFirstModel):
    slot: Literal["slot_1", "slot_2"]
    assessments: list[GDPvalItemAssessmentV1] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "GDPvalAnonymousAssessmentV1":
        ids = [item.rubric_item_id for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("gdpval_duplicate_rubric_assessment")
        return self


class GDPvalPairReviewV1(ScenarioFirstModel):
    review_version: Literal["r10.gdpval_pair_review.1"] = "r10.gdpval_pair_review.1"
    task_id: str
    judge_id: GDPvalJudgeId
    pair_id: str
    order_id: Literal["a_b", "b_a"]
    preference: Literal["slot_1", "slot_2", "tie"]
    bundles: list[GDPvalAnonymousAssessmentV1] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def complete_slots_and_rubrics(self) -> "GDPvalPairReviewV1":
        if {bundle.slot for bundle in self.bundles} != {"slot_1", "slot_2"}:
            raise ValueError("gdpval_pair_review_requires_two_slots")
        return self


class GDPvalRankingSnapshotV1(ScenarioFirstModel):
    snapshot_version: Literal["r10.gdpval_aa_snapshot.1"] = "r10.gdpval_aa_snapshot.1"
    source_url: str
    captured_at: str
    scores: dict[GDPvalSolverId, float]
    reference_order: list[GDPvalSolverId]

    @model_validator(mode="after")
    def scores_match_order(self) -> "GDPvalRankingSnapshotV1":
        if set(self.scores) != set(self.reference_order):
            raise ValueError("gdpval_snapshot_models_mismatch")
        if len(self.reference_order) != len(set(self.reference_order)):
            raise ValueError("gdpval_snapshot_models_not_unique")
        if any(self.scores[first] <= self.scores[second]
               for first, second in zip(self.reference_order, self.reference_order[1:])):
            raise ValueError("gdpval_snapshot_order_not_descending")
        return self


def canonical_sha256(value: Any) -> str:
    if isinstance(value, ScenarioFirstModel):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def score_gdpval_bundle(
    binding: GDPvalTaskBindingV1, bundle: GDPvalAnonymousAssessmentV1,
) -> float:
    items = {item.rubric_item_id: item for item in binding.rubric_items}
    assessments = {item.rubric_item_id: item for item in bundle.assessments}
    if set(items) != set(assessments):
        raise ValueError("gdpval_assessments_do_not_match_human_rubric")
    values = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
    earned = sum(items[item_id].score * values[value.rating] for item_id, value in assessments.items())
    total = sum(item.score for item in items.values())
    return round(earned / total, 6)


class GDPvalSingleItemV1(ScenarioFirstModel):
    rubric_item_id: str
    awarded: StrictInt = Field(ge=0)
    applicability: Literal["applicable", "not_triggered", "unresolved"]
    evidence_paths: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5, max_length=1200)


class GDPvalSingleReviewV1(ScenarioFirstModel):
    review_version: Literal["r10.gdpval_single_review.1"] = "r10.gdpval_single_review.1"
    material_status: Literal["complete", "incomplete"]
    material_notes: str
    assessments: list[GDPvalSingleItemV1] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "GDPvalSingleReviewV1":
        ids = [row.rubric_item_id for row in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("gdpval_duplicate_rubric_assessment")
        return self


class GDPvalMaterialIncomplete(ValueError):
    """Semantic evidence gap: never eligible for a formatting redraw."""


def score_gdpval_single(binding: GDPvalTaskBindingV1, review: GDPvalSingleReviewV1) -> float:
    items = {row.rubric_item_id: row for row in binding.rubric_items}
    rows = {row.rubric_item_id: row for row in review.assessments}
    if set(items) != set(rows):
        raise ValueError("gdpval_assessments_do_not_match_human_rubric")
    if review.material_status != "complete" or any(row.applicability == "unresolved" for row in rows.values()):
        raise GDPvalMaterialIncomplete("gdpval_material_or_applicability_incomplete")
    for ident, row in rows.items():
        maximum = items[ident].score
        if not float(maximum).is_integer() or row.awarded > maximum:
            raise ValueError("gdpval_single_awarded_out_of_range")
        if row.applicability == "not_triggered" and row.awarded != maximum:
            raise ValueError("gdpval_untriggered_condition_must_not_lose_points")
    return round(sum(row.awarded for row in rows.values()) / sum(row.score for row in items.values()), 6)


def summarize_single_scores(rows: list[dict[str, Any]], assignments: list[dict[str, str]]) -> dict[str, Any]:
    expected = {row["assignment_id"]: row for row in assignments}
    if len(expected) != len(assignments) or len({r["assignment_id"] for r in rows}) != len(rows):
        raise ValueError("gdpval_single_duplicate_assignment")
    for row in rows:
        spec = expected.get(row["assignment_id"])
        if spec is None or any(row[k] != spec[k] for k in ("task_id", "solver_id", "judge_id", "role")):
            raise ValueError("gdpval_single_assignment_identity_drift")
    primary = [row for row in rows if row["role"] == "primary"]
    means = {}
    for model in sorted({a["solver_id"] for a in assignments}):
        required = {a["task_id"] for a in assignments if a["role"] == "primary" and a["solver_id"] == model}
        found = [r for r in primary if r["solver_id"] == model]
        if {r["task_id"] for r in found} == required and len(found) == len(required):
            means[model] = round(sum(r["score"] for r in found) / len(found), 6)
    comparisons = []
    models = sorted(means)
    for i, first in enumerate(models):
        for second in models[i + 1:]:
            delta = round(means[first] - means[second], 6)
            comparisons.append({"model_a": first, "model_b": second, "delta": delta,
                                "interpretation": "difference_unclear" if abs(delta) < .05 else "descriptive_difference"})
    checks = []
    for check in (r for r in rows if r["role"] == "check"):
        main = next((r for r in primary if (r["task_id"], r["solver_id"]) == (check["task_id"], check["solver_id"])), None)
        if main:
            checks.append({"task_id": check["task_id"], "solver_id": check["solver_id"],
                           "primary_score": main["score"], "check_score": check["score"],
                           "delta": round(check["score"] - main["score"], 6)})
    return {"status": "preliminary_scoring_complete" if len(rows) == len(assignments) else "preliminary_scoring_partial",
            "completed": len(rows), "planned": len(assignments), "primary_means": means,
            "comparisons": comparisons, "cross_judge_checks": checks, "results": rows,
            "evaluator_validated": False, "evidence_level": "exploratory_development_subset_llm_proxy"}


def normalize_pair_review(review: GDPvalPairReviewV1) -> dict[str, Any]:
    slots = {bundle.slot: bundle for bundle in review.bundles}
    mapping = (
        {"slot_1": "candidate_a", "slot_2": "candidate_b"}
        if review.order_id == "a_b" else
        {"slot_1": "candidate_b", "slot_2": "candidate_a"}
    )
    return {
        mapping[slot]: bundle for slot, bundle in slots.items()
    } | {
        "preference": "tie" if review.preference == "tie" else mapping[review.preference]
    }


def balanced_order(*, task_id: str, pair_id: str, seed: int) -> Literal["a_b", "b_a"]:
    digest = hashlib.sha256(f"{seed}:{task_id}:{pair_id}".encode()).digest()
    return "a_b" if digest[0] % 2 == 0 else "b_a"


def bootstrap_model_order(
    task_preferences: list[dict[str, str]], *, models: list[str], seed: int, samples: int = 2000,
) -> dict[str, Any]:
    """Aggregate pairwise wins and a task-bootstrap interval for each model."""

    if not task_preferences:
        raise ValueError("gdpval_preferences_required")
    by_task: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in task_preferences:
        by_task[row["task_id"]].append((row["candidate_a"], row["candidate_b"], row["preference"]))
    tasks = sorted(by_task)

    def wins(sampled: list[str]) -> dict[str, float]:
        result = {model: 0.0 for model in models}
        for task in sampled:
            for first, second, preference in by_task[task]:
                if preference == first:
                    result[first] += 1.0
                elif preference == second:
                    result[second] += 1.0
                else:
                    result[first] += 0.5
                    result[second] += 0.5
        return result

    observed = wins(tasks)
    rng = random.Random(seed)
    distributions = {model: [] for model in models}
    for _ in range(samples):
        sample = [rng.choice(tasks) for _ in tasks]
        value = wins(sample)
        for model in models:
            distributions[model].append(value[model])
    intervals = {}
    for model, values in distributions.items():
        ordered = sorted(values)
        intervals[model] = [ordered[int(samples * .025)], ordered[min(samples - 1, int(samples * .975))]]
    order = sorted(models, key=lambda model: (-observed[model], model))
    return {"wins": observed, "bootstrap_95": intervals, "observed_order": order}


def ordinal_direction_agreement(observed_order: list[str], reference_order: list[str]) -> dict[str, Any]:
    common = [model for model in reference_order if model in observed_order]
    position = {model: index for index, model in enumerate(observed_order)}
    total = agree = 0
    for index, better in enumerate(common):
        for worse in common[index + 1:]:
            total += 1
            agree += position[better] < position[worse]
    return {"agree": agree, "total": total, "rate": round(agree / total, 6) if total else None}
