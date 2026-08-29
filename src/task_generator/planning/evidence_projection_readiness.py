"""Report whether a Scenario Bible can be deterministically projected into files.

R10 deliberately treats the Bible as the sole authority for business facts.  A
plain narrative fact is enough to explain a case to a human, but it is not
enough for code to derive candidate-visible columns, values, artifact placement
and visibility without inventing new business facts.  This is a report-only
gate; it neither materializes files nor changes a Bible.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from task_generator.core.scenario_first import ScenarioBibleV1, ScenarioFirstModel


ProjectionReadinessDecision = Literal["pass", "blocked"]


class ProjectionReadinessFindingV1(ScenarioFirstModel):
    code: str = Field(min_length=1)
    passed: bool
    details: dict[str, int | list[str]] = Field(default_factory=dict)


class ScenarioProjectionReadinessReportV1(ScenarioFirstModel):
    report_version: Literal["r10.projection_readiness_report.1"] = "r10.projection_readiness_report.1"
    scenario_id: str = Field(min_length=1)
    bible_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: ProjectionReadinessDecision
    findings: list[ProjectionReadinessFindingV1]


class EvidenceProjectionReadinessValidator:
    """Detect missing structured facts before an R10 projection compiler exists."""

    _REQUIRED_FACT_PAYLOAD_KEYS = {
        "business_object_id", "candidate_visibility", "artifact_hints", "field_values",
    }

    def evaluate(self, bible: ScenarioBibleV1) -> ScenarioProjectionReadinessReportV1:
        # ScenarioFactV1 intentionally has no projection payload in the initial
        # R10.2 contract.  Read it from the model dump so this check will become
        # meaningful when a future version introduces those fields.
        facts = [fact.model_dump(mode="json") for fact in bible.facts]
        missing_by_key = {
            key: [fact["fact_id"] for fact in facts if key not in fact]
            for key in self._REQUIRED_FACT_PAYLOAD_KEYS
        }
        findings = [
            ProjectionReadinessFindingV1(
                code=f"missing_{key}", passed=not fact_ids,
                details={"fact_count": len(fact_ids), "fact_ids": fact_ids},
            )
            for key, fact_ids in sorted(missing_by_key.items())
        ]
        decision: ProjectionReadinessDecision = "pass" if all(item.passed for item in findings) else "blocked"
        return ScenarioProjectionReadinessReportV1(
            scenario_id=bible.scenario_id,
            bible_sha256=bible.canonical_sha256(),
            decision=decision,
            findings=findings,
        )
