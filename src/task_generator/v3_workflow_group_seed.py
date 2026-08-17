from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Literal, Set

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_domain_profile import DomainProfile, load_domain_profile
from task_generator.v3_formal_brief_admission import SourceProvenanceLedgerV1
from task_generator.v3_pipeline_b_seed_set import PipelineBSeedSetBuilder
from task_generator.v3_skill_registry import SkillRegistryBuilder


class WorkflowGroupSeedReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.workflow_group_seed.1"] = "v3.workflow_group_seed.1"
    decision: Literal["pass", "blocked"]
    source_group_id: str
    admitted_skill_ids: list[str] = Field(default_factory=list)
    rejected_skill_reasons: Dict[str, list[str]] = Field(default_factory=dict)
    seed_report_path: str
    notes: list[str] = Field(default_factory=list)


class WorkflowGroupSeedCompiler:
    """Build an isolated Pipeline B seed whose skills share one workflow source group."""

    def compile(
        self,
        registry_path: str | Path,
        readiness_report_path: str | Path,
        provenance_ledger_path: str | Path,
        source_group_id: str,
        output_dir: str | Path,
        domain_profile: DomainProfile | None = None,
    ) -> WorkflowGroupSeedReportV1:
        ledger = SourceProvenanceLedgerV1.model_validate_json(
            Path(provenance_ledger_path).read_text(encoding="utf-8")
        )
        group_by_candidate = {
            record.source_candidate_id: record.source_group_id
            for record in ledger.records
        }
        entries = SkillRegistryBuilder().load_registry(registry_path)
        admitted: Set[str] = set()
        rejected: Dict[str, list[str]] = {}
        for entry in entries:
            reasons: list[str] = []
            candidate_ids = set(entry.source_candidate_ids)
            if not candidate_ids:
                reasons.append("missing_source_candidate")
            unresolved = candidate_ids - set(group_by_candidate)
            if unresolved:
                reasons.append("unresolved_source_candidate")
            resolved_groups = {
                group_by_candidate[candidate_id]
                for candidate_id in candidate_ids
                if candidate_id in group_by_candidate
            }
            if None in resolved_groups:
                reasons.append("missing_source_group")
            if resolved_groups - {source_group_id}:
                reasons.append("different_source_group")
            if not reasons and resolved_groups == {source_group_id}:
                admitted.add(entry.skill_id)
            else:
                rejected[entry.skill_id] = sorted(set(reasons or ["group_not_resolved"]))

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        seed = PipelineBSeedSetBuilder().build_report(
            registry_path=registry_path,
            readiness_report_path=readiness_report_path,
            target_count=len(admitted),
            caution_limit=len(admitted),
            domain_profile=domain_profile or load_domain_profile("finance_audit"),
            allowed_skill_ids=admitted,
            selection_policy_id=f"single_workflow_group:{source_group_id}",
        )
        seed_path = output_path / "workflow_group_seed_report.json"
        seed_path.write_text(
            json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return WorkflowGroupSeedReportV1(
            decision="pass" if admitted and seed.get("selected_count") else "blocked",
            source_group_id=source_group_id,
            admitted_skill_ids=sorted(admitted),
            rejected_skill_reasons=rejected,
            seed_report_path=str(seed_path),
            notes=[
                "This compiler is report-only and never mutates registry readiness.",
                "Every admitted skill resolves exclusively to the requested source/workflow group.",
            ],
        )
