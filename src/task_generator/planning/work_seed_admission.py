"""Public-source admission for R10 Scenario-First work seeds.

The module records why a real worker receives work.  It intentionally does
not create a fictional organization, scenario facts, candidate files, or
provider prompt.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from task_generator.core.scenario_first import (
    ProfessionalRuleSetV1,
    ScenarioFirstModel,
    WorkSeedV1,
)


Domain = Literal["audit_compliance", "procurement_operations"]
CandidateStatus = Literal["admitted", "rejected"]
AdmissionDecision = Literal["pass", "blocked"]


class PublicWorkSourceBlockV1(ScenarioFirstModel):
    block_id: str = Field(min_length=1)
    section_reference: str = Field(min_length=1)
    source_summary: str = Field(min_length=1)


class PublicWorkSourceV1(ScenarioFirstModel):
    source_id: str = Field(min_length=1)
    normalized_source_id: str = Field(min_length=1)
    domains: list[Domain] = Field(min_length=1)
    locator: str = Field(min_length=9)
    retrieved_at: str = Field(min_length=20)
    retrieval_mode: Literal["content_hashed", "browser_verified"]
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verification_note: str | None = None
    blocks: list[PublicWorkSourceBlockV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_public_source(self) -> "PublicWorkSourceV1":
        if not self.locator.startswith("https://"):
            raise ValueError("public_work_source_requires_https")
        if self.retrieval_mode == "content_hashed" and not self.content_sha256:
            raise ValueError("content_hashed_source_requires_sha256")
        if self.retrieval_mode == "browser_verified" and not self.verification_note:
            raise ValueError("browser_verified_source_requires_note")
        block_ids = [item.block_id for item in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("duplicate_public_work_source_block")
        return self


class PublicWorkSourceCatalogV1(ScenarioFirstModel):
    catalog_version: Literal["r10.public_work_source_catalog.1"] = "r10.public_work_source_catalog.1"
    catalog_id: str = Field(min_length=1)
    sources: list[PublicWorkSourceV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_sources(self) -> "PublicWorkSourceCatalogV1":
        ids = [item.source_id for item in self.sources]
        normalized_ids = [item.normalized_source_id for item in self.sources]
        if len(ids) != len(set(ids)) or len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("duplicate_public_work_source")
        return self


class WorkSeedCandidateV1(ScenarioFirstModel):
    candidate_id: str = Field(min_length=1)
    work_pattern_id: str = Field(min_length=1)
    seed: WorkSeedV1
    status: CandidateStatus
    selection_rationale: str = Field(min_length=1)
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def validate_candidate_status(self) -> "WorkSeedCandidateV1":
        if self.status == "rejected" and not self.rejection_reason:
            raise ValueError("rejected_work_seed_requires_reason")
        if self.status == "admitted" and self.rejection_reason:
            raise ValueError("admitted_work_seed_cannot_have_rejection_reason")
        return self


class WorkSeedAdmissionFindingV1(ScenarioFirstModel):
    candidate_id: str
    passed: bool
    reason_codes: list[str] = Field(default_factory=list)


class WorkSeedAdmissionReportV1(ScenarioFirstModel):
    report_version: Literal["r10.work_seed_admission_report.1"] = "r10.work_seed_admission_report.1"
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: AdmissionDecision
    admitted_seed_ids: list[str] = Field(default_factory=list)
    findings: list[WorkSeedAdmissionFindingV1] = Field(default_factory=list)


class WorkSeedAdmissionValidator:
    """Validate a fixed four-candidate-per-domain R10.1 source cohort."""

    REQUIRED_CANDIDATES_PER_DOMAIN = 4
    REQUIRED_ADMITTED_PER_DOMAIN = 2

    def evaluate(
        self,
        *,
        catalog: PublicWorkSourceCatalogV1,
        candidates: list[WorkSeedCandidateV1],
        rule_sets: list[ProfessionalRuleSetV1],
    ) -> WorkSeedAdmissionReportV1:
        source_by_id = {source.source_id: source for source in catalog.sources}
        rules_by_domain = {rules.domain: rules for rules in rule_sets}
        findings: list[WorkSeedAdmissionFindingV1] = []

        candidate_ids = [item.candidate_id for item in candidates]
        pattern_ids = [item.work_pattern_id for item in candidates]
        seed_ids = [item.seed.seed_id for item in candidates]
        cohort_reasons: list[str] = []
        if len(candidate_ids) != len(set(candidate_ids)):
            cohort_reasons.append("duplicate_work_seed_candidate_id")
        if len(pattern_ids) != len(set(pattern_ids)):
            cohort_reasons.append("duplicate_work_pattern_id")
        if len(seed_ids) != len(set(seed_ids)):
            cohort_reasons.append("duplicate_work_seed_id")

        by_domain: dict[Domain, list[WorkSeedCandidateV1]] = {
            "audit_compliance": [], "procurement_operations": [],
        }
        for candidate in candidates:
            by_domain[candidate.seed.domain].append(candidate)
        for domain, values in by_domain.items():
            if len(values) != self.REQUIRED_CANDIDATES_PER_DOMAIN:
                cohort_reasons.append(f"candidate_count_invalid:{domain}")
            if sum(item.status == "admitted" for item in values) != self.REQUIRED_ADMITTED_PER_DOMAIN:
                cohort_reasons.append(f"admitted_count_invalid:{domain}")
            if domain not in rules_by_domain:
                cohort_reasons.append(f"missing_rule_set:{domain}")

        for candidate in candidates:
            reasons = self._candidate_reasons(candidate, source_by_id, rules_by_domain.get(candidate.seed.domain))
            findings.append(WorkSeedAdmissionFindingV1(
                candidate_id=candidate.candidate_id,
                passed=not reasons,
                reason_codes=sorted(set(reasons)),
            ))

        decision = "pass" if not cohort_reasons and all(item.passed for item in findings) else "blocked"
        admitted = sorted(
            candidate.seed.seed_id
            for candidate in candidates
            if candidate.status == "admitted" and not next(
                item.reason_codes for item in findings if item.candidate_id == candidate.candidate_id
            )
        )
        if decision == "blocked":
            admitted = []
        if cohort_reasons:
            findings.append(WorkSeedAdmissionFindingV1(
                candidate_id="__cohort__", passed=False, reason_codes=sorted(set(cohort_reasons)),
            ))
        return WorkSeedAdmissionReportV1(
            catalog_sha256=catalog.canonical_sha256(),
            candidate_set_sha256=self._sha256(candidates, rule_sets),
            decision=decision,
            admitted_seed_ids=admitted,
            findings=findings,
        )

    @staticmethod
    def _candidate_reasons(
        candidate: WorkSeedCandidateV1,
        sources: dict[str, PublicWorkSourceV1],
        rule_set: ProfessionalRuleSetV1 | None,
    ) -> list[str]:
        reasons: list[str] = []
        seed = candidate.seed
        if len(seed.typical_inputs) < 2:
            reasons.append("insufficient_typical_inputs")
        source_refs = {(item.source_id, item.normalized_source_id, item.locator) for item in seed.public_sources}
        for source_id, normalized_id, locator in source_refs:
            source = sources.get(source_id)
            if source is None:
                reasons.append("unknown_public_source")
                continue
            if source.normalized_source_id != normalized_id or source.locator != locator:
                reasons.append("source_trace_identity_mismatch")
        for trace in seed.public_sources:
            source = sources.get(trace.source_id)
            if source and not set(trace.block_ids) <= {block.block_id for block in source.blocks}:
                reasons.append("unknown_public_source_block")
            if source and seed.domain not in source.domains:
                reasons.append("source_domain_mismatch")
        if rule_set is None or rule_set.domain != seed.domain:
            reasons.append("missing_matching_professional_rule_set")
        return reasons

    @staticmethod
    def _sha256(candidates: list[WorkSeedCandidateV1], rule_sets: list[ProfessionalRuleSetV1]) -> str:
        payload = {
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "rule_sets": [item.model_dump(mode="json") for item in rule_sets],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
