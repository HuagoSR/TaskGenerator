from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_domain_profile import DomainProfile
from task_generator.v3_formal_brief_admission import SourceProvenanceLedgerV1
from task_generator.v3_pipeline_b_seed_set import PipelineBSeedSetBuilder, TARGET_MOTIFS


class FormalPublicSeedFindingV1(BaseModel):
    check_name: str
    passed: bool
    reason_codes: List[str] = Field(default_factory=list)
    details: Dict[str, object] = Field(default_factory=dict)


class FormalPublicSeedCompileReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.formal_public_seed_compile.1"] = (
        "v3.formal_public_seed_compile.1"
    )
    decision: Literal["pass", "blocked"]
    public_source_skill_count: int
    admitted_skill_count: int
    seed_report_path: str
    findings: List[FormalPublicSeedFindingV1] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class FormalPublicSeedCompiler:
    """Build an experimental source-filtered seed without canonical mutation."""

    def compile(
        self,
        registry_path: str | Path,
        readiness_report_path: str | Path,
        web_audit_report_path: str | Path,
        provenance_ledger_path: str | Path,
        output_dir: str | Path,
        domain_profile: DomainProfile,
    ) -> FormalPublicSeedCompileReportV1:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        audit = json.loads(Path(web_audit_report_path).read_text(encoding="utf-8"))
        ledger = SourceProvenanceLedgerV1.model_validate_json(
            Path(provenance_ledger_path).read_text(encoding="utf-8")
        )
        public_candidates = {
            record.source_candidate_id
            for record in ledger.records
            if record.source_kind == "public_web"
        }
        allowed_skill_ids = {
            record["skill_id"]
            for record in audit.get("records", [])
            if record.get("audit_decision") == "manual_review_needed"
            and set(
                (record.get("evidence_summary") or {}).get(
                    "source_candidate_ids", []
                )
            )
            <= public_candidates
        }
        seed_report = PipelineBSeedSetBuilder().build_report(
            registry_path=registry_path,
            readiness_report_path=readiness_report_path,
            target_count=len(allowed_skill_ids),
            caution_limit=len(allowed_skill_ids),
            domain_profile=domain_profile,
            allowed_skill_ids=allowed_skill_ids,
            selection_policy_id="formal_public_source_only_v1",
        )
        seed_path = output_path / "formal_public_seed_report.json"
        seed_path.write_text(
            json.dumps(seed_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        motif_counts = seed_report.get("selected_motif_counts", {})
        missing_motifs = [
            motif for motif in TARGET_MOTIFS if not motif_counts.get(motif)
        ]
        selected_count = int(seed_report.get("selected_count", 0))
        reasons: List[str] = []
        deferred_count = len(allowed_skill_ids) - selected_count
        if missing_motifs:
            reasons.append("missing_required_motif_coverage")
        findings = [
            FormalPublicSeedFindingV1(
                check_name="public_source_identity",
                passed=bool(allowed_skill_ids),
                reason_codes=[] if allowed_skill_ids else ["no_public_source_skills"],
                details={
                    "public_candidate_count": len(public_candidates),
                    "allowed_skill_ids": sorted(allowed_skill_ids),
                },
            ),
            FormalPublicSeedFindingV1(
                check_name="four_motif_seed_coverage",
                passed=not reasons,
                reason_codes=reasons,
                details={
                    "selected_count": selected_count,
                    "deferred_by_canonical_readiness_count": deferred_count,
                    "motif_counts": motif_counts,
                    "missing_motifs": missing_motifs,
                },
            ),
        ]
        return FormalPublicSeedCompileReportV1(
            decision="pass" if all(item.passed for item in findings) else "blocked",
            public_source_skill_count=len(allowed_skill_ids),
            admitted_skill_count=selected_count,
            seed_report_path=str(seed_path),
            findings=findings,
            notes=[
                "This compiler writes an experimental seed report only.",
                "It does not mutate canonical registry, readiness, weights, or promotion state.",
                "manual_review_needed is admitted only within the source-filtered research slice; revise_recommended remains excluded.",
                "Canonical exclude_until_revised remains authoritative; public provenance does not override readiness.",
            ],
        )
