"""Deterministic aggregation for the R9 three-model comparison."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class JudgeScoreV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    judge_id: Literal["gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"]
    valid: bool
    weighted_score: Optional[float] = Field(default=None, ge=0, le=1)
    major_defect: Optional[bool] = None


class ModelTaskEvaluationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    solver_id: Literal[
        "gpt-5.6-sol@chatgpt_codex",
        "deepseek-v4-pro@official_opencode",
        "gemini-3.1-pro-preview@tuzi_opencode",
    ]
    delivery_valid: bool
    judges: List[JudgeScoreV1] = Field(default_factory=list, max_length=2)


class ModelSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solver_id: str
    valid_delivery_count: int
    dual_graded_count: int
    major_defect_count: int
    mean_composite_score: Optional[float]
    comparison_eligible: bool


class TaskDiscriminationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    model_count: int
    score_range: Optional[float]
    level: Literal["high", "medium", "low", "insufficient"]


class ProductionModelComparisonResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["v3.production_model_comparison.1"] = "v3.production_model_comparison.1"
    model_summaries: List[ModelSummaryV1]
    common_task_count: int
    judge_disagreement_count: int
    task_discrimination: List[TaskDiscriminationV1]
    discrimination_decision: Literal["usefully_discriminative", "low_model_separation", "insufficient"]
    decision: Literal["comparison_complete", "comparison_partial", "comparison_incomplete"]
    training_authorized: Literal[False] = False
    default_solver_change_authorized: Literal[False] = False
    public_release_authorized: Literal[False] = False


def aggregate_production_model_comparison(records: List[ModelTaskEvaluationV1]) -> ProductionModelComparisonResultV1:
    solver_ids = [
        "gpt-5.6-sol@chatgpt_codex",
        "deepseek-v4-pro@official_opencode",
        "gemini-3.1-pro-preview@tuzi_opencode",
    ]
    by_solver: Dict[str, List[ModelTaskEvaluationV1]] = {
        solver_id: [item for item in records if item.solver_id == solver_id]
        for solver_id in solver_ids
    }
    composite: Dict[tuple[str, str], float] = {}
    disagreements = 0
    summaries: List[ModelSummaryV1] = []
    for solver_id in solver_ids:
        values, dual, majors = by_solver[solver_id], [], 0
        for item in values:
            valid_judges = [judge for judge in item.judges if judge.valid and judge.weighted_score is not None]
            if item.delivery_valid and len(valid_judges) == 2:
                score = sum(float(judge.weighted_score) for judge in valid_judges) / 2
                composite[(solver_id, item.task_id)] = score
                dual.append(score)
                major_values = [bool(judge.major_defect) for judge in valid_judges]
                majors += any(major_values)
                disagreements += int(abs(float(valid_judges[0].weighted_score) - float(valid_judges[1].weighted_score)) >= 0.15 or major_values[0] != major_values[1])
        summaries.append(ModelSummaryV1(solver_id=solver_id, valid_delivery_count=sum(item.delivery_valid for item in values), dual_graded_count=len(dual), major_defect_count=majors, mean_composite_score=(sum(dual) / len(dual) if dual else None), comparison_eligible=len(dual) >= 8))
    eligible = [item.solver_id for item in summaries if item.comparison_eligible]
    task_sets = [{task for solver, task in composite if solver == solver_id} for solver_id in eligible]
    common = set.intersection(*task_sets) if task_sets else set()
    discrimination = []
    for task_id in sorted({item.task_id for item in records}):
        scores = [composite[(solver_id, task_id)] for solver_id in solver_ids if (solver_id, task_id) in composite]
        if len(scores) < 2:
            discrimination.append(TaskDiscriminationV1(task_id=task_id, model_count=len(scores), score_range=None, level="insufficient"))
            continue
        spread = max(scores) - min(scores)
        discrimination.append(TaskDiscriminationV1(task_id=task_id, model_count=len(scores), score_range=spread, level="high" if spread >= 0.15 else "medium" if spread >= 0.08 else "low"))
    complete = [item for item in discrimination if item.model_count == 3 and item.score_range is not None]
    useful_count = sum(item.level in {"medium", "high"} for item in complete)
    mean_range = sum(float(item.score_range) for item in complete) / len(complete) if complete else 0.0
    discrimination_decision = "insufficient" if len(complete) < 8 else "usefully_discriminative" if useful_count >= 6 and mean_range >= 0.10 else "low_model_separation"
    decision = "comparison_complete" if len(eligible) == 3 and len(common) >= 8 else "comparison_partial" if len(eligible) >= 2 and len(common) >= 8 else "comparison_incomplete"
    return ProductionModelComparisonResultV1(model_summaries=summaries, common_task_count=len(common), judge_disagreement_count=disagreements, task_discrimination=discrimination, discrimination_decision=discrimination_decision, decision=decision)
