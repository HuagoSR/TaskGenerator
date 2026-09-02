"""Minimal contracts and persisted state for the R10.9 World-First pilot.

The module deliberately records only execution identity and hard hand-offs.  A
work world remains an agent-authored directory (candidate artifacts plus a
teacher-only ledger), not a new business-object ontology.
"""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.planning.scenario_task_compiler import TaskSpecificRubricV1
from task_generator.production.campaign import atomic_json


Domain = Literal["audit_compliance", "procurement_operations"]
WorldVariant = Literal["baseline", "adversarial"]
WorldFirstStage = Literal[
    "not_started",
    "skill_deliberated",
    "world_frozen",
    "task_mined",
    "truth_reconstructed",
    "statically_admitted",
    "judge_calibrated",
    "solver_completed",
    "judged",
    "blocked",
    "incomplete",
]
PilotDecision = Literal[
    "pending",
    "world_first_adversarial_supported",
    "world_first_adversarial_mixed",
    "world_first_adversarial_not_supported",
    "evaluator_revision_required",
    "incomplete",
]
_STAGE_ORDER = {
    "not_started": 0,
    "skill_deliberated": 1,
    "world_frozen": 2,
    "task_mined": 3,
    "truth_reconstructed": 4,
    "statically_admitted": 5,
    "judge_calibrated": 6,
    "solver_completed": 7,
    "judged": 8,
}


class ProfessionDifficultyMutationV1(ScenarioFirstModel):
    mutation_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    professional_cause: str = Field(min_length=20)
    business_event: str = Field(min_length=20)
    candidate_evidence_effect: str = Field(min_length=20)
    targeted_shortcut: str = Field(min_length=10)
    source_ids: list[str] = Field(min_length=1)
    fairness_rationale: str = Field(min_length=20)
    solvability_rationale: str = Field(min_length=20)

    @model_validator(mode="after")
    def require_unique_sources(self) -> "ProfessionDifficultyMutationV1":
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("difficulty_mutation_source_ids_not_unique")
        return self


class ProfessionDifficultyPlanV1(ScenarioFirstModel):
    plan_version: Literal["r10.profession_difficulty_plan.1"] = "r10.profession_difficulty_plan.1"
    domain: Domain
    seed_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    available_source_ids: list[str] = Field(min_length=1)
    mutations: list[ProfessionDifficultyMutationV1] = Field(min_length=1, max_length=6)
    selected_mutation_ids: list[str] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def require_closed_selection_and_sources(self) -> "ProfessionDifficultyPlanV1":
        mutation_ids = [item.mutation_id for item in self.mutations]
        if len(mutation_ids) != len(set(mutation_ids)):
            raise ValueError("difficulty_mutation_ids_not_unique")
        if len(self.available_source_ids) != len(set(self.available_source_ids)):
            raise ValueError("difficulty_available_source_ids_not_unique")
        if not set(self.selected_mutation_ids) <= set(mutation_ids):
            raise ValueError("difficulty_selected_mutation_unknown")
        available = set(self.available_source_ids)
        if any(not set(item.source_ids) <= available for item in self.mutations):
            raise ValueError("difficulty_mutation_source_unknown")
        return self


class WorldFirstCaseStateV1(ScenarioFirstModel):
    case_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    pair_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    domain: Domain
    variant: WorldVariant
    deliverable_format: Literal["xlsx", "docx"]
    stage: WorldFirstStage = "not_started"
    seed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rules_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    skill_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    difficulty_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    world_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    candidate_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    task_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    teacher_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    calibration_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    first_failure: str | None = None

    @model_validator(mode="after")
    def require_stage_evidence(self) -> "WorldFirstCaseStateV1":
        if self.variant == "baseline" and self.difficulty_plan_sha256 is not None:
            raise ValueError("baseline_case_must_not_bind_difficulty_plan")
        if self.variant == "adversarial" and self.stage != "not_started" and self.difficulty_plan_sha256 is None:
            raise ValueError("adversarial_case_requires_difficulty_plan")
        if self.stage in {"blocked", "incomplete"} and not self.first_failure:
            raise ValueError("world_first_terminal_case_requires_failure")
        if self.stage in {
            "world_frozen", "task_mined", "truth_reconstructed", "statically_admitted",
            "judge_calibrated", "solver_completed", "judged",
        } and not (self.world_tree_sha256 and self.candidate_tree_sha256):
            raise ValueError("world_first_world_stage_requires_fingerprints")
        if self.stage in {"truth_reconstructed", "statically_admitted", "judge_calibrated", "solver_completed", "judged"}:
            if not (self.task_tree_sha256 and self.teacher_tree_sha256):
                raise ValueError("world_first_task_stage_requires_fingerprints")
        if self.stage in {"judge_calibrated", "solver_completed", "judged"} and not self.calibration_tree_sha256:
            raise ValueError("world_first_evaluation_requires_calibration")
        return self


class WorldFirstPilotManifestV1(ScenarioFirstModel):
    manifest_version: Literal["r10.world_first_pilot_manifest.1"] = "r10.world_first_pilot_manifest.1"
    campaign_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    image: str = Field(min_length=1)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[WorldFirstCaseStateV1] = Field(min_length=4, max_length=4)
    decision: PilotDecision = "pending"
    professional_validity: Literal["provisional"] = "provisional"
    first_failure: str | None = None

    @model_validator(mode="after")
    def require_two_complete_pairs(self) -> "WorldFirstPilotManifestV1":
        if len({item.case_id for item in self.cases}) != 4:
            raise ValueError("world_first_case_ids_not_unique")
        pairs: dict[str, list[WorldFirstCaseStateV1]] = {}
        for item in self.cases:
            pairs.setdefault(item.pair_id, []).append(item)
        if len(pairs) != 2:
            raise ValueError("world_first_requires_two_pairs")
        domains: set[str] = set()
        for items in pairs.values():
            if len(items) != 2 or {item.variant for item in items} != {"baseline", "adversarial"}:
                raise ValueError("world_first_pair_requires_baseline_and_adversarial")
            if len({item.domain for item in items}) != 1 or len({item.deliverable_format for item in items}) != 1:
                raise ValueError("world_first_pair_identity_mismatch")
            domains.add(items[0].domain)
        if domains != {"audit_compliance", "procurement_operations"}:
            raise ValueError("world_first_domains_incomplete")
        if self.decision == "incomplete" and not self.first_failure:
            raise ValueError("world_first_incomplete_manifest_requires_failure")
        return self


class PairedDecisionAssessmentV1(ScenarioFirstModel):
    decision_id: str = Field(min_length=1)
    bundle_1_rating: Literal["met", "partial", "not_met"]
    bundle_2_rating: Literal["met", "partial", "not_met"]
    bundle_1_major_error: bool
    bundle_2_major_error: bool
    bundle_1_evidence_paths: list[str] = Field(min_length=1)
    bundle_2_evidence_paths: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=20, max_length=2000)


class PairedJudgeReviewV1(ScenarioFirstModel):
    review_version: Literal["r10.paired_judge_review.1"] = "r10.paired_judge_review.1"
    task_id: str = Field(min_length=1)
    judge_id: Literal["gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"]
    preference: Literal["bundle_1", "bundle_2", "tie"]
    assessments: list[PairedDecisionAssessmentV1] = Field(min_length=3, max_length=5)
    bundle_1_weighted_score: float = Field(ge=0, le=1)
    bundle_2_weighted_score: float = Field(ge=0, le=1)
    bundle_1_major_defect: bool
    bundle_2_major_defect: bool

    @model_validator(mode="after")
    def require_unique_decisions(self) -> "PairedJudgeReviewV1":
        ids = [item.decision_id for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("paired_judge_decision_ids_not_unique")
        return self


def advance_world_first_case(
    manifest: WorldFirstPilotManifestV1,
    *,
    case_id: str,
    stage: WorldFirstStage,
    first_failure: str | None = None,
    **fingerprints: str | None,
) -> WorldFirstPilotManifestV1:
    """Advance one case without reviving started, blocked, or incomplete work."""

    cases: list[WorldFirstCaseStateV1] = []
    found = False
    for item in manifest.cases:
        if item.case_id != case_id:
            cases.append(item)
            continue
        found = True
        if item.stage in {"blocked", "incomplete"}:
            raise ValueError("world_first_terminal_case_cannot_resume")
        if stage not in {"blocked", "incomplete"} and _STAGE_ORDER[stage] <= _STAGE_ORDER[item.stage]:
            raise ValueError("world_first_case_stage_not_forward")
        cases.append(item.model_copy(update={"stage": stage, "first_failure": first_failure or item.first_failure, **fingerprints}))
    if not found:
        raise ValueError("world_first_case_unknown")
    return manifest.model_copy(update={"cases": cases})


def write_manifest(path: Path, manifest: WorldFirstPilotManifestV1) -> None:
    atomic_json(path, manifest.model_dump(mode="json"))


def resumable_case_ids(manifest: WorldFirstPilotManifestV1) -> list[str]:
    """Only pristine cases are automatically resumable."""

    return [item.case_id for item in manifest.cases if item.stage == "not_started"]


def recompute_paired_review(
    review: PairedJudgeReviewV1, *, rubric: TaskSpecificRubricV1,
) -> PairedJudgeReviewV1:
    """Replace model-declared totals with deterministic rubric-weighted totals."""

    criteria = {item.decision_id: item for item in rubric.criteria}
    assessments = {item.decision_id: item for item in review.assessments}
    if set(criteria) != set(assessments):
        raise ValueError("paired_judge_decisions_do_not_match_rubric")
    rating_value = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
    score_1 = sum(criteria[key].weight * rating_value[item.bundle_1_rating] for key, item in assessments.items())
    score_2 = sum(criteria[key].weight * rating_value[item.bundle_2_rating] for key, item in assessments.items())
    major_1 = any(item.bundle_1_major_error for item in review.assessments)
    major_2 = any(item.bundle_2_major_error for item in review.assessments)
    return review.model_copy(update={
        "bundle_1_weighted_score": round(score_1, 6),
        "bundle_2_weighted_score": round(score_2, 6),
        "bundle_1_major_defect": major_1,
        "bundle_2_major_defect": major_2,
    })


def validate_world_candidate_tree(candidate_root: Path) -> list[str]:
    """Check only transport/isolation boundaries, not occupational semantics."""

    errors: list[str] = []
    if not candidate_root.is_dir():
        return ["candidate_tree_missing"]
    files = sorted(path for path in candidate_root.rglob("*") if path.is_file())
    if len(files) < 2:
        errors.append("candidate_requires_two_independent_artifacts")
    forbidden = (
        "teacher", "world_ledger", "difficulty_plan", "professional_skill",
        "correct treatment", "correct_treatment", "questionable",
        "requires follow-up", "requires_follow_up",
    )
    for path in files:
        try:
            relative = path.relative_to(candidate_root)
        except ValueError:
            errors.append("candidate_path_outside_root")
            continue
        if any(part in {"..", "teacher"} for part in relative.parts):
            errors.append(f"candidate_path_unsafe:{relative.as_posix()}")
        if path.stat().st_size == 0:
            errors.append(f"candidate_file_empty:{relative.as_posix()}")
            continue
        suffix = path.suffix.casefold()
        try:
            if suffix == ".xlsx":
                with zipfile.ZipFile(path) as archive:
                    if "xl/workbook.xml" not in archive.namelist():
                        raise ValueError("xlsx_workbook_missing")
            elif suffix == ".docx":
                with zipfile.ZipFile(path) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise ValueError("docx_document_missing")
            elif suffix == ".pdf":
                if not path.read_bytes().startswith(b"%PDF-"):
                    raise ValueError("pdf_header_missing")
            elif suffix == ".csv":
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    next(csv.reader(handle), None)
            elif suffix in {".txt", ".md", ".json"}:
                path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError, zipfile.BadZipFile):
            errors.append(f"candidate_file_invalid:{relative.as_posix()}")
            continue
        if suffix in {".txt", ".md", ".csv", ".json"}:
            searchable = path.read_text(encoding="utf-8-sig", errors="replace").casefold()
            if any(token in searchable for token in forbidden):
                errors.append(f"candidate_answer_leakage:{relative.as_posix()}")
    return sorted(set(errors))


def judge_calibration_errors(reviews: list[dict], *, decision_ids: set[str]) -> list[str]:
    """Validate one task's two blind three-tier Judge calibration records."""

    errors: list[str] = []
    if len(reviews) != 2:
        return ["calibration_requires_two_judges"]
    for review in reviews:
        judge = str(review.get("judge_id", "unknown"))
        tiers = review.get("tiers", {})
        if set(tiers) != {"reference_quality", "plausible_incomplete", "shortcut_critical_error"}:
            errors.append(f"calibration_tiers_incomplete:{judge}")
            continue
        scores = {name: float(value.get("weighted_score", -1)) for name, value in tiers.items()}
        if not (scores["reference_quality"] > scores["plausible_incomplete"] > scores["shortcut_critical_error"]):
            errors.append(f"calibration_not_monotonic:{judge}")
        if scores["reference_quality"] - scores["shortcut_critical_error"] < 0.20:
            errors.append(f"calibration_gap_too_small:{judge}")
        if bool(tiers["reference_quality"].get("major_defect")):
            errors.append(f"calibration_reference_major_defect:{judge}")
        if not bool(tiers["shortcut_critical_error"].get("major_defect")):
            errors.append(f"calibration_shortcut_major_not_detected:{judge}")
        for tier, value in tiers.items():
            assessments = value.get("assessments", [])
            if {item.get("decision_id") for item in assessments} != decision_ids:
                errors.append(f"calibration_decisions_incomplete:{judge}:{tier}")
    return sorted(set(errors))


def paired_task_discrimination(
    reviews: list[PairedJudgeReviewV1], *, bundle_1_solver: str, bundle_2_solver: str,
) -> dict[str, object]:
    """Aggregate two paired reviews without turning Judge disagreement into signal."""

    if len(reviews) != 2 or len({item.judge_id for item in reviews}) != 2:
        return {"classification": "incomplete", "reason": "paired_reviews_incomplete"}
    preferences = {item.preference for item in reviews}
    major_pairs = {(item.bundle_1_major_defect, item.bundle_2_major_defect) for item in reviews}
    if len(preferences) != 1 or len(major_pairs) != 1:
        return {"classification": "judge_ambiguous", "reason": "judge_direction_or_major_defect_disagreement"}
    score_1 = sum(item.bundle_1_weighted_score for item in reviews) / 2
    score_2 = sum(item.bundle_2_weighted_score for item in reviews) / 2
    gap = abs(score_1 - score_2)
    major_1, major_2 = next(iter(major_pairs))
    clean = gap >= 0.05 or major_1 != major_2
    winner = "tie"
    if clean:
        winner = bundle_1_solver if score_1 > score_2 else bundle_2_solver
    return {
        "classification": "cleanly_discriminative" if clean else "near_tie",
        "bundle_1_solver": bundle_1_solver,
        "bundle_2_solver": bundle_2_solver,
        "bundle_1_composite": round(score_1, 6),
        "bundle_2_composite": round(score_2, 6),
        "absolute_gap": round(gap, 6),
        "winner": winner,
        "major_defect_pair": [major_1, major_2],
    }
