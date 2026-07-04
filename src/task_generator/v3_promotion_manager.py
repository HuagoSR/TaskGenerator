from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_skill_registry import SkillRegistryBuilder
from task_generator.v3_source_schema import SemanticResource, SkillRegistryEntry, load_json_file
from task_generator.v3_typed_resource_patch_proposal import (
    ProposedTypedResource,
    SkillTypedResourcePatchProposal,
    TypedResourcePatchProposalReport,
)


PromotionTargetType = Literal["typed_resource_patch"]
PromotionReviewStatus = Literal["proposed", "approved", "rejected", "applied", "rolled_back"]
PromotionDecision = Literal["pending", "approved_and_applied", "rolled_back", "blocked"]
PromotionChangeType = Literal["append_resource"]
RollbackStatus = Literal["available", "rolled_back"]


class PromotionManagerRequest(BaseModel):
    typed_resource_patch_proposals_path: Optional[str] = None
    registry_path: Optional[str] = None
    output_dir: str
    apply_promotion_id: Optional[str] = None
    reviewer: Optional[str] = None
    approval_note: Optional[str] = None
    rollback_record_path: Optional[str] = None


class PromotionDiffItem(BaseModel):
    skill_id: str
    contract_path: str
    change_type: PromotionChangeType = "append_resource"
    resource_signature: str
    resource_type: str
    proposed_resource: SemanticResource
    before_present: bool = False
    after_present: bool = True
    proposal_id: Optional[str] = None


class PromotionRecord(BaseModel):
    promotion_id: str
    target_type: PromotionTargetType = "typed_resource_patch"
    target_ids: List[str] = Field(default_factory=list)
    source_report_path: str
    target_path: str
    review_status: PromotionReviewStatus = "proposed"
    decision: PromotionDecision = "pending"
    reviewer: Optional[str] = None
    approval_note: Optional[str] = None
    applied_at: Optional[str] = None
    rollback_available: bool = False
    rollback_record_id: Optional[str] = None
    apply_eligible: bool = False
    blocked_reason_codes: List[str] = Field(default_factory=list)
    diff_summary: List[PromotionDiffItem] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RollbackRecord(BaseModel):
    rollback_record_id: str
    promotion_id: str
    target_type: PromotionTargetType = "typed_resource_patch"
    target_path: str
    backup_path: str
    restored_at: Optional[str] = None
    status: RollbackStatus = "available"
    notes: List[str] = Field(default_factory=list)
    promotion_snapshot: Optional[PromotionRecord] = None


class PromotionManagerDiagnostics(BaseModel):
    promotion_count: int = 0
    eligible_promotion_count: int = 0
    blocked_promotion_count: int = 0
    applied_promotion_count: int = 0
    rolled_back_promotion_count: int = 0
    diff_item_count: int = 0
    blocked_reason_counts: Dict[str, int] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PromotionManagerArtifact(BaseModel):
    promotion_manager_version: str = "v3.promotion_manager.1"
    request: PromotionManagerRequest
    promotions: List[PromotionRecord] = Field(default_factory=list)
    rollback_record: Optional[RollbackRecord] = None
    diagnostics: PromotionManagerDiagnostics
    notes: List[str] = Field(default_factory=list)


class PromotionManager:
    """Build and optionally apply typed-resource promotion records."""

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()

    def build_proposals(
        self,
        typed_resource_patch_proposals_path: str | Path,
        registry_path: str | Path,
        output_dir: str | Path,
    ) -> PromotionManagerArtifact:
        request = PromotionManagerRequest(
            typed_resource_patch_proposals_path=str(typed_resource_patch_proposals_path),
            registry_path=str(registry_path),
            output_dir=str(output_dir),
        )
        proposals_report = TypedResourcePatchProposalReport.model_validate(
            load_json_file(str(typed_resource_patch_proposals_path))
        )
        registry_entries = self.registry_builder.load_registry(registry_path)
        promotions = self._build_promotions(
            proposals_report=proposals_report,
            proposals_path=typed_resource_patch_proposals_path,
            registry_path=registry_path,
            registry_entries=registry_entries,
        )
        artifact = PromotionManagerArtifact(
            request=request,
            promotions=promotions,
            diagnostics=self._diagnostics(promotions=promotions, rollback_record=None),
            notes=[
                "Promotion Manager V1 is typed-resource-first and report-first by default.",
                "Proposal-only mode never mutates SkillRegistry/v3_skill_registry.json.",
                "Apply requires an explicit promotion id plus reviewer metadata.",
            ],
        )
        self.write_outputs(artifact, output_dir)
        return artifact

    def apply_promotion(
        self,
        typed_resource_patch_proposals_path: str | Path,
        registry_path: str | Path,
        output_dir: str | Path,
        apply_promotion_id: str,
        reviewer: str,
        approval_note: str,
    ) -> PromotionManagerArtifact:
        request = PromotionManagerRequest(
            typed_resource_patch_proposals_path=str(typed_resource_patch_proposals_path),
            registry_path=str(registry_path),
            output_dir=str(output_dir),
            apply_promotion_id=apply_promotion_id,
            reviewer=reviewer,
            approval_note=approval_note,
        )
        proposals_report = TypedResourcePatchProposalReport.model_validate(
            load_json_file(str(typed_resource_patch_proposals_path))
        )
        registry_entries = self.registry_builder.load_registry(registry_path)
        promotions = self._build_promotions(
            proposals_report=proposals_report,
            proposals_path=typed_resource_patch_proposals_path,
            registry_path=registry_path,
            registry_entries=registry_entries,
        )
        promotion = self._find_promotion(promotions, apply_promotion_id)
        if promotion is None:
            raise ValueError(f"Unknown promotion id: {apply_promotion_id}")
        if not promotion.apply_eligible:
            raise ValueError(
                f"Promotion {apply_promotion_id} is not apply-eligible: {', '.join(promotion.blocked_reason_codes)}"
            )

        target_path = Path(registry_path)
        output_path = Path(output_dir)
        backup_dir = output_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = self._timestamp()
        backup_path = backup_dir / f"{target_path.stem}.{promotion.promotion_id}.{timestamp}.bak.json"
        shutil.copy2(target_path, backup_path)

        updated_entries = [entry.model_copy(deep=True) for entry in registry_entries]
        target_entry = next((entry for entry in updated_entries if entry.skill_id == promotion.target_ids[0]), None)
        if target_entry is None:
            raise ValueError(f"Promotion target skill missing at apply time: {promotion.target_ids[0]}")

        self._apply_diff_items(target_entry, promotion.diff_summary)
        self.registry_builder.write_registry(target_path, updated_entries)

        rollback_record = RollbackRecord(
            rollback_record_id=self._stable_id("rollback", f"{promotion.promotion_id}:{timestamp}"),
            promotion_id=promotion.promotion_id,
            target_type=promotion.target_type,
            target_path=str(target_path),
            backup_path=str(backup_path),
            status="available",
            notes=["Rollback restores the full registry backup created before apply."],
        )
        promotion.review_status = "applied"
        promotion.decision = "approved_and_applied"
        promotion.reviewer = reviewer
        promotion.approval_note = approval_note
        promotion.applied_at = self._iso_now()
        promotion.rollback_available = True
        promotion.rollback_record_id = rollback_record.rollback_record_id
        promotion.notes = sorted(
            set(
                promotion.notes
                + [
                    "Applied as an append-only typed-resource patch.",
                    "Legacy semantic strings were left unchanged.",
                ]
            )
        )
        rollback_record.promotion_snapshot = promotion.model_copy(deep=True)

        artifact = PromotionManagerArtifact(
            request=request,
            promotions=promotions,
            rollback_record=rollback_record,
            diagnostics=self._diagnostics(promotions=promotions, rollback_record=rollback_record),
            notes=[
                "Apply mode only mutates the explicitly targeted registry file.",
                "Each apply creates a full-file backup to support deterministic rollback.",
            ],
        )
        self.write_outputs(artifact, output_dir)
        return artifact

    def rollback_promotion(
        self,
        rollback_record_path: str | Path,
        output_dir: str | Path,
    ) -> PromotionManagerArtifact:
        rollback_record = RollbackRecord.model_validate(load_json_file(str(rollback_record_path)))
        request = PromotionManagerRequest(
            output_dir=str(output_dir),
            rollback_record_path=str(rollback_record_path),
        )
        target_path = Path(rollback_record.target_path)
        backup_path = Path(rollback_record.backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(f"Rollback backup does not exist: {backup_path}")
        shutil.copy2(backup_path, target_path)
        rollback_record.restored_at = self._iso_now()
        rollback_record.status = "rolled_back"
        rollback_record.notes = sorted(
            set(rollback_record.notes + ["Registry restored from backup via full-file rollback."])
        )
        promotions: List[PromotionRecord] = []
        if rollback_record.promotion_snapshot is not None:
            promotion = rollback_record.promotion_snapshot.model_copy(deep=True)
            promotion.review_status = "rolled_back"
            promotion.decision = "rolled_back"
            promotion.apply_eligible = False
            promotion.rollback_available = False
            promotions.append(promotion)

        artifact = PromotionManagerArtifact(
            request=request,
            promotions=promotions,
            rollback_record=rollback_record,
            diagnostics=self._diagnostics(promotions=promotions, rollback_record=rollback_record),
            notes=[
                "Rollback V1 uses backup-restore instead of field-level inverse patching.",
                "Rollback only touches the target path recorded in rollback_record.json.",
            ],
        )
        self.write_outputs(artifact, output_dir)
        return artifact

    def write_outputs(
        self,
        artifact: PromotionManagerArtifact,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        proposals_path = output_path / "promotion_proposals.json"
        report_path = output_path / "promotion_report.json"
        proposals_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        summary_payload = {
            "promotion_manager_version": artifact.promotion_manager_version,
            "request": artifact.request.model_dump(),
            "promotion_ids": [promotion.promotion_id for promotion in artifact.promotions],
            "diagnostics": artifact.diagnostics.model_dump(),
            "rollback_record_id": artifact.rollback_record.rollback_record_id if artifact.rollback_record else None,
            "notes": artifact.notes,
        }
        report_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        outputs = {
            "promotion_proposals_path": str(proposals_path),
            "promotion_report_path": str(report_path),
        }
        if artifact.rollback_record is not None:
            rollback_path = output_path / "rollback_record.json"
            rollback_path.write_text(artifact.rollback_record.model_dump_json(indent=2), encoding="utf-8")
            outputs["rollback_record_path"] = str(rollback_path)
        return outputs

    def _build_promotions(
        self,
        proposals_report: TypedResourcePatchProposalReport,
        proposals_path: str | Path,
        registry_path: str | Path,
        registry_entries: List[SkillRegistryEntry],
    ) -> List[PromotionRecord]:
        registry_by_skill = {entry.skill_id: entry for entry in registry_entries}
        return [
            self._promotion_from_patch_proposal(
                proposal=proposal,
                proposals_path=str(proposals_path),
                registry_path=str(registry_path),
                registry_entry=registry_by_skill.get(proposal.skill_id),
            )
            for proposal in proposals_report.skill_patch_proposals
        ]

    def _promotion_from_patch_proposal(
        self,
        proposal: SkillTypedResourcePatchProposal,
        proposals_path: str,
        registry_path: str,
        registry_entry: Optional[SkillRegistryEntry],
    ) -> PromotionRecord:
        normalized_source_report = str(Path(proposals_path))
        diff_summary = self._diff_summary(proposal, registry_entry)
        blocked_reason_codes: List[str] = []
        if registry_entry is None:
            blocked_reason_codes.append("missing_registry_skill")
        if proposal.proposal_status == "needs_source_evidence":
            blocked_reason_codes.append("needs_source_evidence")
        resources = self._proposal_resources(proposal)
        if any(resource.confidence != "medium" for resource in resources):
            blocked_reason_codes.append("low_confidence_resource_present")
        if any(resource.proposed_resource.resource_type == "UnknownResource" for resource in resources):
            blocked_reason_codes.append("unknown_resource_type_present")
        if not any(not item.before_present for item in diff_summary):
            blocked_reason_codes.append("no_effective_diff")
        apply_eligible = (
            registry_entry is not None
            and proposal.proposal_status == "requires_review"
            and all(resource.confidence == "medium" for resource in resources)
            and all(resource.proposed_resource.resource_type != "UnknownResource" for resource in resources)
            and any(not item.before_present for item in diff_summary)
        )
        promotion_id = self._stable_id(
            "promotion",
            f"{proposal.skill_id}:{normalized_source_report}:{','.join(item.resource_signature for item in diff_summary)}",
        )
        notes = [
            "This promotion is append-only and does not rewrite legacy semantic strings.",
            f"Patch proposal status: {proposal.proposal_status}.",
        ]
        if proposal.risk_reason_codes:
            notes.append(f"Upstream patch risks: {', '.join(sorted(proposal.risk_reason_codes))}.")
        return PromotionRecord(
            promotion_id=promotion_id,
            target_type="typed_resource_patch",
            target_ids=[proposal.skill_id],
            source_report_path=normalized_source_report,
            target_path=str(registry_path),
            review_status="proposed",
            decision="pending",
            rollback_available=False,
            apply_eligible=apply_eligible,
            blocked_reason_codes=sorted(set(blocked_reason_codes)),
            diff_summary=diff_summary,
            notes=notes,
        )

    def _diff_summary(
        self,
        proposal: SkillTypedResourcePatchProposal,
        registry_entry: Optional[SkillRegistryEntry],
    ) -> List[PromotionDiffItem]:
        contract_items: List[Tuple[str, ProposedTypedResource]] = []
        contract_items.extend(
            ("input_contract.required_resources", item) for item in proposal.proposed_required_resources
        )
        contract_items.extend(
            ("input_contract.optional_resources", item) for item in proposal.proposed_optional_resources
        )
        contract_items.extend(
            ("output_contract.provided_resources", item) for item in proposal.proposed_provided_resources
        )

        existing_signatures: Dict[str, set[str]] = {
            "input_contract.required_resources": set(),
            "input_contract.optional_resources": set(),
            "output_contract.provided_resources": set(),
        }
        if registry_entry is not None:
            existing_signatures["input_contract.required_resources"] = {
                self._resource_signature(resource)
                for resource in registry_entry.input_contract.required_resources
            }
            existing_signatures["input_contract.optional_resources"] = {
                self._resource_signature(resource)
                for resource in registry_entry.input_contract.optional_resources
            }
            existing_signatures["output_contract.provided_resources"] = {
                self._resource_signature(resource)
                for resource in registry_entry.output_contract.provided_resources
            }

        seen_new_signatures: Dict[str, set[str]] = {
            "input_contract.required_resources": set(),
            "input_contract.optional_resources": set(),
            "output_contract.provided_resources": set(),
        }
        diff_summary: List[PromotionDiffItem] = []
        for contract_path, proposed_item in contract_items:
            signature = self._resource_signature(proposed_item.proposed_resource)
            before_present = signature in existing_signatures[contract_path]
            duplicate_in_patch = signature in seen_new_signatures[contract_path]
            if not before_present and not duplicate_in_patch:
                seen_new_signatures[contract_path].add(signature)
            diff_summary.append(
                PromotionDiffItem(
                    skill_id=proposal.skill_id,
                    contract_path=contract_path,
                    change_type="append_resource",
                    resource_signature=signature,
                    resource_type=proposed_item.proposed_resource.resource_type,
                    proposed_resource=proposed_item.proposed_resource,
                    before_present=before_present or duplicate_in_patch,
                    after_present=True,
                    proposal_id=proposed_item.proposal_id,
                )
            )
        return diff_summary

    def _apply_diff_items(
        self,
        entry: SkillRegistryEntry,
        diff_items: List[PromotionDiffItem],
    ) -> None:
        contracts = {
            "input_contract.required_resources": entry.input_contract.required_resources,
            "input_contract.optional_resources": entry.input_contract.optional_resources,
            "output_contract.provided_resources": entry.output_contract.provided_resources,
        }
        signature_sets = {
            key: {self._resource_signature(resource) for resource in value}
            for key, value in contracts.items()
        }
        for item in diff_items:
            if item.before_present:
                continue
            target_resources = contracts[item.contract_path]
            if item.resource_signature in signature_sets[item.contract_path]:
                continue
            target_resources.append(item.proposed_resource.model_copy(deep=True))
            signature_sets[item.contract_path].add(item.resource_signature)

    def _find_promotion(
        self,
        promotions: List[PromotionRecord],
        promotion_id: str,
    ) -> Optional[PromotionRecord]:
        return next((promotion for promotion in promotions if promotion.promotion_id == promotion_id), None)

    def _proposal_resources(
        self,
        proposal: SkillTypedResourcePatchProposal,
    ) -> List[ProposedTypedResource]:
        return [
            *proposal.proposed_required_resources,
            *proposal.proposed_optional_resources,
            *proposal.proposed_provided_resources,
        ]

    def _resource_signature(self, resource: SemanticResource) -> str:
        payload = {
            "resource_type": resource.resource_type,
            "subtype": resource.subtype,
            "attributes": {key: resource.attributes[key] for key in sorted(resource.attributes)},
            "domain": resource.domain,
            "evidence_refs": sorted(resource.evidence_refs),
        }
        return sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _diagnostics(
        self,
        promotions: List[PromotionRecord],
        rollback_record: Optional[RollbackRecord],
    ) -> PromotionManagerDiagnostics:
        blocked_reason_counts: Dict[str, int] = {}
        for promotion in promotions:
            for reason_code in promotion.blocked_reason_codes:
                blocked_reason_counts[reason_code] = blocked_reason_counts.get(reason_code, 0) + 1
        return PromotionManagerDiagnostics(
            promotion_count=len(promotions),
            eligible_promotion_count=sum(1 for promotion in promotions if promotion.apply_eligible),
            blocked_promotion_count=sum(1 for promotion in promotions if not promotion.apply_eligible),
            applied_promotion_count=sum(1 for promotion in promotions if promotion.review_status == "applied"),
            rolled_back_promotion_count=1 if rollback_record and rollback_record.status == "rolled_back" else 0,
            diff_item_count=sum(len(promotion.diff_summary) for promotion in promotions),
            blocked_reason_counts=dict(sorted(blocked_reason_counts.items())),
            notes=[
                "Promotion eligibility is recomputed from current registry state each run.",
                "Backup-restore rollback is intentionally coarse in V1 to keep mutation auditable.",
            ],
        )

    def _stable_id(self, prefix: str, text: str) -> str:
        digest = sha1(text.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
