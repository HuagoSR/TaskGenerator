from __future__ import annotations

import hashlib
import json
from pathlib import Path
from collections import Counter
from typing import Dict, Iterable, List, Literal, Set

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_skill_registry import stable_id
from task_generator.v3_source_schema import ExtractedSkillCandidate, RawSource
from task_generator.v3_task_design_frontend import CapabilityBriefV1


AdmissionDecision = Literal["pass", "blocked"]
SourceKind = Literal["public_web", "internal_governed", "gdpval", "fixture", "synthetic"]


class SourceProvenanceRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_candidate_id: str
    source_id: str
    source_ids: List[str] = Field(default_factory=list)
    normalized_source_id: str | None = None
    source_kind: SourceKind
    source_group_id: str | None = None
    locator: str
    locators: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(min_length=1)
    evidence_spans: List[str] = Field(min_length=1)


class SourceProvenanceLedgerV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_version: Literal["v3.source_provenance_ledger.1"] = (
        "v3.source_provenance_ledger.1"
    )
    records: List[SourceProvenanceRecordV1] = Field(default_factory=list)


class BriefAdmissionFindingV1(BaseModel):
    brief_id: str
    check_name: str
    passed: bool
    reason_codes: List[str] = Field(default_factory=list)
    details: Dict[str, object] = Field(default_factory=dict)


class FormalBriefCohortAdmissionReportV1(BaseModel):
    report_version: Literal["v3.formal_brief_cohort_admission.1"] = (
        "v3.formal_brief_cohort_admission.1"
    )
    cohort_id: str
    decision: AdmissionDecision
    expected_brief_count: int
    observed_brief_count: int
    admitted_brief_ids: List[str] = Field(default_factory=list)
    blocked_brief_ids: List[str] = Field(default_factory=list)
    findings: List[BriefAdmissionFindingV1] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class FormalMatchedBriefCohortAdmissionReportV2(BaseModel):
    """Admission contract for the two-route, replicated screening cohort."""

    report_version: Literal["v3.formal_matched_brief_cohort_admission.2"] = (
        "v3.formal_matched_brief_cohort_admission.2"
    )
    cohort_id: str
    decision: AdmissionDecision
    expected_brief_count: Literal[6] = 6
    expected_motifs: List[str]
    motif_counts: Dict[str, int]
    admitted_brief_ids: List[str] = Field(default_factory=list)
    blocked_brief_ids: List[str] = Field(default_factory=list)
    findings: List[BriefAdmissionFindingV1] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class FormalRepresentativePilotAdmissionReportV3(BaseModel):
    """Admission contract for the fixed two-domain R8.3 pilot."""

    report_version: Literal["v3.formal_representative_pilot_admission.3"] = (
        "v3.formal_representative_pilot_admission.3"
    )
    cohort_id: str
    decision: AdmissionDecision
    expected_brief_count: Literal[12] = 12
    expected_domains: List[str]
    expected_motifs: List[str]
    cell_counts: Dict[str, int]
    admitted_brief_ids: List[str] = Field(default_factory=list)
    blocked_brief_ids: List[str] = Field(default_factory=list)
    findings: List[BriefAdmissionFindingV1] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class FormalBriefCohortAdmission:
    FORBIDDEN_LOCATOR_PREFIXES = (
        "fixture",
        "public-fixture",
        "synthetic",
        "mock",
        "subgraph:",
        "registry-source-candidate:",
    )
    FORBIDDEN_SOURCE_KINDS = {"gdpval", "fixture", "synthetic"}
    MATCHED_SCREENING_MOTIFS = {
        "fan_in_reconciliation",
        "cross_check_validation",
        "policy_application",
    }

    def evaluate(
        self,
        briefs: List[CapabilityBriefV1],
        ledger: SourceProvenanceLedgerV1,
        expected_brief_count: int = 4,
    ) -> FormalBriefCohortAdmissionReportV1:
        ledger_by_candidate = {
            record.source_candidate_id: record for record in ledger.records
        }
        findings: List[BriefAdmissionFindingV1] = []
        blocked: Set[str] = set()

        cohort_reasons: List[str] = []
        if len(briefs) != expected_brief_count:
            cohort_reasons.append("unexpected_brief_count")
        if len({brief.brief_id for brief in briefs}) != len(briefs):
            cohort_reasons.append("duplicate_brief_id")
        if len({brief.workflow_context.subgraph_id for brief in briefs}) != len(briefs):
            cohort_reasons.append("duplicate_subgraph_id")
        if len({brief.motif for brief in briefs}) != len(briefs):
            cohort_reasons.append("duplicate_motif")
        findings.append(
            BriefAdmissionFindingV1(
                brief_id="__cohort__",
                check_name="cohort_shape",
                passed=not cohort_reasons,
                reason_codes=cohort_reasons,
                details={
                    "expected_brief_count": expected_brief_count,
                    "observed_brief_count": len(briefs),
                    "distinct_motif_count": len({brief.motif for brief in briefs}),
                },
            )
        )

        for brief in briefs:
            brief_reasons: List[str] = []
            if brief.workflow_context.workflow_context_fit != "high":
                brief_reasons.append("workflow_context_fit_not_high")
            if brief.workflow_context.missing_roles:
                brief_reasons.append("workflow_roles_missing")

            source_ref_ids = {source.source_ref_id for source in brief.source_refs}
            if any(
                source.locator.lower().startswith(self.FORBIDDEN_LOCATOR_PREFIXES)
                for source in brief.source_refs
            ):
                brief_reasons.append("opaque_or_synthetic_source_locator")

            selected_candidate_ids: Set[str] = set()
            for skill in brief.selected_skills:
                candidate_ids = {
                    ref
                    for ref in skill.provenance_ref_ids
                    if ref.startswith("source_candidate_")
                }
                evidence_refs = {
                    ref
                    for ref in skill.provenance_ref_ids
                    if not ref.startswith("source_candidate_")
                }
                if not candidate_ids:
                    brief_reasons.append(f"skill_missing_source_candidate:{skill.skill_id}")
                if not evidence_refs:
                    brief_reasons.append(f"skill_missing_evidence_ref:{skill.skill_id}")
                if not candidate_ids <= source_ref_ids:
                    brief_reasons.append(f"skill_source_not_in_brief:{skill.skill_id}")
                selected_candidate_ids.update(candidate_ids)

            unresolved = sorted(selected_candidate_ids - set(ledger_by_candidate))
            if unresolved:
                brief_reasons.append("unresolved_source_candidate")

            resolved_records = [
                ledger_by_candidate[candidate_id]
                for candidate_id in sorted(selected_candidate_ids)
                if candidate_id in ledger_by_candidate
            ]
            if any(
                record.source_kind in self.FORBIDDEN_SOURCE_KINDS
                for record in resolved_records
            ):
                brief_reasons.append("forbidden_generation_source_kind")
            if any(
                record.locator.lower().startswith(self.FORBIDDEN_LOCATOR_PREFIXES)
                for record in resolved_records
            ):
                brief_reasons.append("unresolved_ledger_locator")
            source_group_ids = {
                record.source_group_id
                for record in resolved_records
                if record.source_group_id
            }
            if any(not record.source_group_id for record in resolved_records):
                brief_reasons.append("missing_source_group")
            if len(source_group_ids) > 1:
                brief_reasons.append("multiple_source_groups_in_brief")

            findings.append(
                BriefAdmissionFindingV1(
                    brief_id=brief.brief_id,
                    check_name="formal_brief_admission",
                    passed=not brief_reasons,
                    reason_codes=sorted(set(brief_reasons)),
                    details={
                        "motif": brief.motif,
                        "subgraph_id": brief.workflow_context.subgraph_id,
                        "selected_source_candidate_ids": sorted(selected_candidate_ids),
                        "unresolved_source_candidate_ids": unresolved,
                        "source_group_ids": sorted(source_group_ids),
                    },
                )
            )
            if brief_reasons:
                blocked.add(brief.brief_id)

        if cohort_reasons:
            blocked.update(brief.brief_id for brief in briefs)
        admitted = sorted(brief.brief_id for brief in briefs if brief.brief_id not in blocked)
        cohort_seed = {
            "brief_ids": sorted(brief.brief_id for brief in briefs),
            "ledger_candidates": sorted(ledger_by_candidate),
            "expected_brief_count": expected_brief_count,
        }
        cohort_id = "brief_cohort_" + hashlib.sha256(
            json.dumps(cohort_seed, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        return FormalBriefCohortAdmissionReportV1(
            cohort_id=cohort_id,
            decision="pass" if not blocked and not cohort_reasons else "blocked",
            expected_brief_count=expected_brief_count,
            observed_brief_count=len(briefs),
            admitted_brief_ids=admitted,
            blocked_brief_ids=sorted(blocked),
            findings=findings,
            notes=[
                "Formal admission is report-only and does not mutate the registry or campaign.",
                "GDPVal, fixture, synthetic, opaque, and unresolved sources are blocked from generation.",
                "Each formal brief must stay inside one governed source/workflow group.",
            ],
        )

    def evaluate_paths(
        self,
        brief_paths: List[str | Path],
        ledger_path: str | Path,
        expected_brief_count: int = 4,
    ) -> FormalBriefCohortAdmissionReportV1:
        briefs = [
            CapabilityBriefV1.model_validate_json(
                Path(path).read_text(encoding="utf-8")
            )
            for path in brief_paths
        ]
        ledger = SourceProvenanceLedgerV1.model_validate_json(
            Path(ledger_path).read_text(encoding="utf-8")
        )
        return self.evaluate(briefs, ledger, expected_brief_count)

    def evaluate_matched_screening(
        self,
        briefs: List[CapabilityBriefV1],
        ledger: SourceProvenanceLedgerV1,
    ) -> FormalMatchedBriefCohortAdmissionReportV2:
        """Require two independent briefs for each non-experimental motif."""

        findings: List[BriefAdmissionFindingV1] = []
        blocked: Set[str] = set()
        brief_ids = [brief.brief_id for brief in briefs]
        subgraph_ids = [brief.workflow_context.subgraph_id for brief in briefs]
        motif_counts = Counter(brief.motif for brief in briefs)
        cohort_reasons: List[str] = []
        if len(briefs) != 6:
            cohort_reasons.append("unexpected_brief_count")
        if len(brief_ids) != len(set(brief_ids)):
            cohort_reasons.append("duplicate_brief_id")
        if len(subgraph_ids) != len(set(subgraph_ids)):
            cohort_reasons.append("duplicate_subgraph_id")
        if set(motif_counts) != self.MATCHED_SCREENING_MOTIFS:
            cohort_reasons.append("matched_screening_motif_set_mismatch")
        if any(motif_counts.get(motif, 0) != 2 for motif in self.MATCHED_SCREENING_MOTIFS):
            cohort_reasons.append("matched_screening_requires_two_briefs_per_motif")
        if any(brief.motif == "evidence_to_deliverable" for brief in briefs):
            cohort_reasons.append("experimental_motif_forbidden")
        findings.append(
            BriefAdmissionFindingV1(
                brief_id="__cohort__",
                check_name="matched_screening_cohort_shape",
                passed=not cohort_reasons,
                reason_codes=sorted(set(cohort_reasons)),
                details={
                    "expected_brief_count": 6,
                    "observed_brief_count": len(briefs),
                    "motif_counts": dict(sorted(motif_counts.items())),
                },
            )
        )

        # Reuse the per-brief source/trust checks without the V1 distinct-motif
        # cohort rule by evaluating each brief as a single-item diagnostic.
        for brief in briefs:
            single = self.evaluate([brief], ledger, expected_brief_count=1)
            source_finding = next(
                item for item in single.findings if item.brief_id == brief.brief_id
            )
            findings.append(source_finding)
            if not source_finding.passed:
                blocked.add(brief.brief_id)
        if cohort_reasons:
            blocked.update(brief_ids)
        admitted = sorted(set(brief_ids) - blocked)
        seed = {
            "brief_ids": sorted(brief_ids),
            "motif_counts": dict(sorted(motif_counts.items())),
            "ledger_candidates": sorted(record.source_candidate_id for record in ledger.records),
        }
        cohort_id = "matched_brief_cohort_" + hashlib.sha256(
            json.dumps(seed, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        return FormalMatchedBriefCohortAdmissionReportV2(
            cohort_id=cohort_id,
            decision="pass" if not blocked and not cohort_reasons else "blocked",
            expected_motifs=sorted(self.MATCHED_SCREENING_MOTIFS),
            motif_counts=dict(sorted(motif_counts.items())),
            admitted_brief_ids=admitted,
            blocked_brief_ids=sorted(blocked),
            findings=findings,
            notes=[
                "Matched screening admits exactly two briefs per non-experimental motif.",
                "This report grants no provider, solver, grader, release or training authority.",
            ],
        )

    def evaluate_representative_pilot(
        self,
        briefs: List[CapabilityBriefV1],
        ledger: SourceProvenanceLedgerV1,
        *,
        domains_by_brief: Dict[str, str],
    ) -> FormalRepresentativePilotAdmissionReportV3:
        """Require two fresh briefs for every domain × production-motif cell."""

        expected_domains = {"audit_compliance", "procurement_operations"}
        brief_ids = [brief.brief_id for brief in briefs]
        case_ids = [brief.case_id for brief in briefs]
        subgraph_ids = [brief.workflow_context.subgraph_id for brief in briefs]
        cells = Counter(
            (domains_by_brief.get(brief.brief_id, ""), brief.motif)
            for brief in briefs
        )
        cohort_reasons: List[str] = []
        if len(briefs) != 12:
            cohort_reasons.append("unexpected_brief_count")
        if len(brief_ids) != len(set(brief_ids)):
            cohort_reasons.append("duplicate_brief_id")
        if len(case_ids) != len(set(case_ids)):
            cohort_reasons.append("duplicate_case_id")
        if len(subgraph_ids) != len(set(subgraph_ids)):
            cohort_reasons.append("duplicate_subgraph_id")
        if set(domains_by_brief) != set(brief_ids):
            cohort_reasons.append("domain_mapping_incomplete")
        if set(domains_by_brief.values()) != expected_domains:
            cohort_reasons.append("representative_pilot_domain_set_mismatch")
        expected_cells = {
            (domain, motif)
            for domain in expected_domains
            for motif in self.MATCHED_SCREENING_MOTIFS
        }
        if set(cells) != expected_cells:
            cohort_reasons.append("representative_pilot_cell_set_mismatch")
        if any(cells.get(cell, 0) != 2 for cell in expected_cells):
            cohort_reasons.append("representative_pilot_requires_two_briefs_per_cell")
        if any(
            brief.motif in {"evidence_to_deliverable", "strict_template"}
            for brief in briefs
        ):
            cohort_reasons.append("forbidden_pilot_route_or_motif")

        findings: List[BriefAdmissionFindingV1] = [
            BriefAdmissionFindingV1(
                brief_id="__cohort__",
                check_name="representative_pilot_cohort_shape",
                passed=not cohort_reasons,
                reason_codes=sorted(set(cohort_reasons)),
                details={
                    "expected_brief_count": 12,
                    "observed_brief_count": len(briefs),
                    "cell_counts": {
                        f"{domain}::{motif}": count
                        for (domain, motif), count in sorted(cells.items())
                    },
                },
            )
        ]
        blocked: Set[str] = set()
        for brief in briefs:
            single = self.evaluate([brief], ledger, expected_brief_count=1)
            source_finding = next(
                item for item in single.findings if item.brief_id == brief.brief_id
            )
            reasons = list(source_finding.reason_codes)
            bound_capabilities = {
                capability_id
                for skill in brief.selected_skills
                for capability_id in skill.required_capability_ids
            }
            required_capabilities = {
                item.capability_id for item in brief.required_capabilities
            }
            if bound_capabilities != required_capabilities:
                reasons.append("required_capability_not_causally_bound")
            if len(brief.productive_complexity_floor) < 4:
                reasons.append("productive_complexity_floor_too_small")
            complexity_text = " ".join(brief.productive_complexity_floor).lower()
            if not any(
                token in complexity_text
                for token in ("gap", "exception", "conflict", "uncertainty")
            ):
                reasons.append("productive_complexity_lacks_judgment")
            details = dict(source_finding.details)
            details["domain"] = domains_by_brief.get(brief.brief_id)
            details["required_capability_ids"] = sorted(required_capabilities)
            details["bound_capability_ids"] = sorted(bound_capabilities)
            finding = BriefAdmissionFindingV1(
                brief_id=brief.brief_id,
                check_name="representative_pilot_brief_admission",
                passed=not reasons,
                reason_codes=sorted(set(reasons)),
                details=details,
            )
            findings.append(finding)
            if reasons:
                blocked.add(brief.brief_id)

        if cohort_reasons:
            blocked.update(brief_ids)
        admitted = sorted(set(brief_ids) - blocked)
        normalized_cells = {
            f"{domain}::{motif}": cells.get((domain, motif), 0)
            for domain, motif in sorted(expected_cells)
        }
        seed = {
            "brief_ids": sorted(brief_ids),
            "cells": normalized_cells,
            "ledger_candidates": sorted(
                record.source_candidate_id for record in ledger.records
            ),
        }
        cohort_id = "representative_pilot_" + hashlib.sha256(
            json.dumps(seed, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        return FormalRepresentativePilotAdmissionReportV3(
            cohort_id=cohort_id,
            decision="pass" if not blocked and not cohort_reasons else "blocked",
            expected_domains=sorted(expected_domains),
            expected_motifs=sorted(self.MATCHED_SCREENING_MOTIFS),
            cell_counts=normalized_cells,
            admitted_brief_ids=admitted,
            blocked_brief_ids=sorted(blocked),
            findings=findings,
            notes=[
                "R8.3 admits exactly two fresh briefs per domain and production motif.",
                "Admission is report-only and grants no provider, solver, grader, registry, release or training authority.",
            ],
        )

    def hydrate_brief(
        self,
        brief: CapabilityBriefV1,
        ledger: SourceProvenanceLedgerV1,
    ) -> CapabilityBriefV1:
        ledger_by_candidate = {
            record.source_candidate_id: record for record in ledger.records
        }
        hydrated = brief.model_copy(deep=True)
        for source in hydrated.source_refs:
            record = ledger_by_candidate.get(source.source_ref_id)
            if record is None:
                continue
            source.locator = record.locator
            source.evidence_spans = sorted(
                set(source.evidence_spans) | set(record.evidence_spans)
            )
        return hydrated


class SourceProvenanceLedgerCompiler:
    """Compile a report-only resolver from governed Pipeline A artifacts."""

    CANDIDATE_KEYS = (
        "accepted_candidates",
        "candidates",
        "extracted_candidates",
        "skill_candidates",
    )

    def compile(
        self,
        candidate_paths: Iterable[str | Path],
        raw_source_paths: Iterable[str | Path],
    ) -> SourceProvenanceLedgerV1:
        raw_sources = self._load_raw_sources(raw_source_paths)
        records: Dict[str, SourceProvenanceRecordV1] = {}
        for candidate_path in candidate_paths:
            source_group_id = self._source_group_id(Path(candidate_path))
            for candidate in self._load_candidates(candidate_path):
                candidate_ref = self._candidate_ref(candidate)
                source_ids = sorted(set(candidate.source_ids))
                if not source_ids:
                    continue
                resolved_sources = [
                    raw_sources[source_id]
                    for source_id in source_ids
                    if source_id in raw_sources
                ]
                if len(resolved_sources) != len(source_ids):
                    continue
                source_id = source_ids[0]
                raw_source = resolved_sources[0]
                locators = sorted(
                    {source.url_or_path for source in resolved_sources}
                )
                evidence_refs = sorted(
                    {item.evidence_id for item in candidate.evidence if item.evidence_id}
                )
                evidence_spans = sorted(
                    {
                        self._span_label(span)
                        for item in candidate.evidence
                        for span in item.supporting_spans
                        if self._span_label(span)
                    }
                )
                if not evidence_refs or not evidence_spans:
                    continue
                record = SourceProvenanceRecordV1(
                    source_candidate_id=candidate_ref,
                    source_id=source_id,
                    source_ids=source_ids,
                    normalized_source_id=next(
                        (
                            item.normalized_source_id
                            for item in candidate.evidence
                            if item.normalized_source_id
                        ),
                        None,
                    ),
                    source_kind=self._source_set_kind(resolved_sources),
                    source_group_id=source_group_id,
                    locator=" ; ".join(locators),
                    locators=locators,
                    evidence_refs=evidence_refs,
                    evidence_spans=evidence_spans,
                )
                existing = records.get(candidate_ref)
                if existing is None:
                    records[candidate_ref] = record
                elif existing.model_dump(mode="json") != record.model_dump(mode="json"):
                    raise ValueError(f"conflicting_source_candidate:{candidate_ref}")
        return SourceProvenanceLedgerV1(
            records=[records[key] for key in sorted(records)]
        )

    def _load_raw_sources(
        self, raw_source_paths: Iterable[str | Path]
    ) -> Dict[str, RawSource]:
        sources: Dict[str, RawSource] = {}
        for path in raw_source_paths:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            source = RawSource.model_validate(payload)
            existing = sources.get(source.source_id)
            if existing is not None and existing != source:
                raise ValueError(f"conflicting_raw_source:{source.source_id}")
            sources[source.source_id] = source
        return sources

    def _load_candidates(
        self, candidate_path: str | Path
    ) -> List[ExtractedSkillCandidate]:
        payload = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            values = payload
        else:
            values = []
            for key in self.CANDIDATE_KEYS:
                if isinstance(payload.get(key), list):
                    values = payload[key]
                    break
        return [ExtractedSkillCandidate.model_validate(item) for item in values]

    def _candidate_ref(self, candidate: ExtractedSkillCandidate) -> str:
        source_key = ",".join(sorted(candidate.source_ids))
        return stable_id(
            "source_candidate",
            f"{source_key}::{candidate.candidate_id}::{candidate.proposed_name}",
        )

    def _source_group_id(self, candidate_path: Path) -> str:
        parts = candidate_path.resolve().parts
        for index, part in enumerate(parts[:-1]):
            if part == "pipeline_a_batches" and index + 1 < len(parts):
                return parts[index + 1]
        return candidate_path.parent.name

    def _source_kind(self, source: RawSource) -> SourceKind:
        locator = source.url_or_path.lower()
        if source.source_type == "benchmark_task" or source.source_id.startswith(
            "gdpval_"
        ):
            return "gdpval"
        if locator.startswith(("http://", "https://")):
            return "public_web"
        return "internal_governed"

    def _source_set_kind(self, sources: List[RawSource]) -> SourceKind:
        kinds = {self._source_kind(source) for source in sources}
        if "gdpval" in kinds:
            return "gdpval"
        if kinds == {"public_web"}:
            return "public_web"
        return "internal_governed"

    def _span_label(self, span) -> str:
        if not span.block_id:
            return ""
        if span.start_char is None or span.end_char is None:
            return span.block_id
        return f"{span.block_id}:{span.start_char}-{span.end_char}"
