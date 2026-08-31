"""Small persisted state contract for an R10 Scenario-First cohort.

The contract records hand-offs between existing R10 stages.  It intentionally
does not describe provider protocols or try to replace the specialist runners.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel


R10CohortStage = Literal[
    "not_started", "seed_admitted", "bible_admitted", "skill_admitted",
    "evidence_admitted", "task_admitted", "solver_completed", "judge_completed",
    "blocked", "incomplete",
]


class R10CohortTaskStateV1(ScenarioFirstModel):
    task_id: str = Field(min_length=1)
    domain: Literal["audit_compliance", "procurement_operations"]
    deliverable_format: Literal["xlsx", "docx"]
    stage: R10CohortStage = "not_started"
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    seed_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bible_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    skill_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    candidate_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    teacher_tree_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    first_failure: str | None = None

    @model_validator(mode="after")
    def require_terminal_reason_and_task_fingerprint(self) -> "R10CohortTaskStateV1":
        if self.stage in {"blocked", "incomplete"} and not self.first_failure:
            raise ValueError("r10_cohort_terminal_state_requires_first_failure")
        if self.stage in {"task_admitted", "solver_completed", "judge_completed"}:
            if not self.candidate_tree_sha256 or not self.teacher_tree_sha256:
                raise ValueError("r10_cohort_task_stage_requires_package_fingerprints")
        return self


class R10CohortManifestV1(ScenarioFirstModel):
    manifest_version: Literal["r10.cohort_manifest.1"] = "r10.cohort_manifest.1"
    campaign_id: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    tasks: list[R10CohortTaskStateV1] = Field(min_length=1, max_length=10)
    professional_validity: Literal["provisional"] = "provisional"
    first_failure: str | None = None

    @model_validator(mode="after")
    def require_unique_tasks_and_balanced_final_cohort(self) -> "R10CohortManifestV1":
        ids = [item.task_id for item in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("r10_cohort_task_ids_not_unique")
        if len(self.tasks) == 10:
            domains = [item.domain for item in self.tasks]
            formats = [item.deliverable_format for item in self.tasks]
            if domains.count("audit_compliance") != 5 or domains.count("procurement_operations") != 5:
                raise ValueError("r10_cohort_requires_five_tasks_per_domain")
            if formats.count("xlsx") != 5 or formats.count("docx") != 5:
                raise ValueError("r10_cohort_requires_five_tasks_per_format")
        return self


def advance_task_state(
    manifest: R10CohortManifestV1, *, task_id: str, stage: R10CohortStage,
    first_failure: str | None = None, **fingerprints: str | None,
) -> R10CohortManifestV1:
    """Return a new manifest while preventing silent revival of terminal work."""
    states = []
    found = False
    for item in manifest.tasks:
        if item.task_id != task_id:
            states.append(item)
            continue
        found = True
        if item.stage in {"blocked", "incomplete"}:
            raise ValueError("r10_cohort_terminal_task_cannot_resume")
        update = {"stage": stage, "first_failure": first_failure or item.first_failure, **fingerprints}
        states.append(item.model_copy(update=update))
    if not found:
        raise ValueError("r10_cohort_task_unknown")
    return manifest.model_copy(update={"tasks": states})
