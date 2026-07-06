from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_global_pipeline_dashboard import GlobalPipelineDashboardBuilder
from task_generator.v3_pipeline_a_substrate_audit import (
    PipelineASubstrateAuditReport,
    PipelineASubstrateAuditor,
)
from task_generator.v3_pipeline_b_batch_feedback_analyzer import PipelineBBatchFeedbackAnalyzer
from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunner
from task_generator.v3_promotion_manager import PromotionManager
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_typed_resource_patch_proposal import (
    TypedResourcePatchProposalBuilder,
    TypedResourcePatchProposalReport,
)


TierLabel = Literal["tier_a", "tier_b", "tier_c", "tier_d"]
PromotionAction = Literal["applied", "blocked", "skipped"]


class Phase12SubstrateHardeningRequest(BaseModel):
    substrate_audit_report_path: str
    typed_resource_patch_proposals_path: str
    typed_resource_patch_proposal_report_path: str
    registry_path: str
    seed_report_path: str
    readiness_report_path: str
    transition_graph_report_path: str
    composition_readiness_report_path: str
    output_dir: str
    max_cases: int = 5
    allow_caution: bool = False
    motif_grammar_path: Optional[str] = None
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str
    python_exe: str
    max_apply_count: int = 3


class TypedResourceTierRecord(BaseModel):
    skill_id: str
    canonical_name: str
    tier: TierLabel
    proposal_status: str
    proposed_resource_count: int = 0
    medium_confidence_resource_count: int = 0
    low_confidence_resource_count: int = 0
    unknown_resource_type_count: int = 0
    risk_reason_codes: List[str] = Field(default_factory=list)
    apply_eligible: bool = False
    eligible_promotion_id: Optional[str] = None
    source_promotion_key: Optional[str] = None
    blocked_reason_codes: List[str] = Field(default_factory=list)
    rationale: str = ""
    notes: List[str] = Field(default_factory=list)


class Phase12TypedResourceReviewReport(BaseModel):
    phase12_typed_resource_review_version: str = "v1"
    report_date: str
    source_proposal_report_path: str
    source_proposals_path: str
    tier_counts: Dict[str, int] = Field(default_factory=dict)
    eligible_promotion_count: int = 0
    eligible_unreviewed_promotion_count: int = 0
    no_effective_diff_promotion_count: int = 0
    tier_records: List[TypedResourceTierRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PromotionBatchActionRecord(BaseModel):
    source_promotion_key: str
    promotion_id: str
    skill_id: Optional[str] = None
    action: PromotionAction = "skipped"
    apply_eligible: bool = False
    blocked_reason_codes: List[str] = Field(default_factory=list)
    output_dir: str = ""
    rollback_record_path: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class Phase12PromotionBatchReport(BaseModel):
    phase12_promotion_batch_version: str = "v1"
    report_date: str
    source_proposals_path: str
    scratch_registry_path: str
    promotion_review_report_path: str
    max_apply_count: int = 0
    reviewed_promotion_count: int = 0
    eligible_promotion_count: int = 0
    applied_promotion_count: int = 0
    rollback_record_count: int = 0
    action_records: List[PromotionBatchActionRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class SourceSupportProposal(BaseModel):
    skill_id: str
    canonical_name: str
    source_candidate_count: int = 0
    batch_motifs: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12SourceSupportExpansionReport(BaseModel):
    phase12_source_support_expansion_version: str = "v1"
    report_date: str
    expansion_candidate_count: int = 0
    proposals: List[SourceSupportProposal] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TransitionEvidenceProposal(BaseModel):
    skill_id: str
    canonical_name: str
    local_only_edge_count: int = 0
    transition_edge_ids: List[str] = Field(default_factory=list)
    observational_candidate: bool = False
    recommended_store: str = "SkillRegistry/v3_transition_prior_store.observed.json"
    notes: List[str] = Field(default_factory=list)


class Phase12TransitionEvidenceProposalReport(BaseModel):
    phase12_transition_evidence_proposal_version: str = "v1"
    report_date: str
    proposal_count: int = 0
    proposals: List[TransitionEvidenceProposal] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12SubstrateHardeningSummary(BaseModel):
    pre_candidate_ready_count: int = 0
    post_candidate_ready_count: int = 0
    pre_verifier_pass_count: int = 0
    post_verifier_pass_count: int = 0
    pre_missing_typed_resource_skill_count: int = 0
    post_missing_typed_resource_skill_count: int = 0
    pre_transition_gap_skill_count: int = 0
    post_transition_gap_skill_count: int = 0
    pre_subgraph_confidence_counts: Dict[str, int] = Field(default_factory=dict)
    post_subgraph_confidence_counts: Dict[str, int] = Field(default_factory=dict)
    applied_promotion_count: int = 0
    rollback_record_count: int = 0
    quality_regression_detected: bool = False


class Phase12SubstrateHardeningReport(BaseModel):
    phase12_substrate_hardening_version: str = "v1"
    request: Phase12SubstrateHardeningRequest
    typed_resource_review_report_path: str
    promotion_batch_report_path: str
    source_support_expansion_report_path: str
    transition_evidence_proposal_report_path: str
    post_batch_report_path: str
    post_batch_feedback_report_path: str
    post_substrate_audit_report_path: str
    post_typed_resource_patch_report_path: str
    post_dashboard_report_path: str
    scratch_registry_path: str
    summary: Phase12SubstrateHardeningSummary
    notes: List[str] = Field(default_factory=list)


class Phase12SubstrateHardener:
    def run(
        self,
        substrate_audit_report_path: str | Path,
        typed_resource_patch_proposals_path: str | Path,
        typed_resource_patch_proposal_report_path: str | Path,
        registry_path: str | Path,
        seed_report_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_dir: str | Path,
        max_cases: int = 5,
        allow_caution: bool = False,
        motif_grammar_path: Optional[str | Path] = None,
        model: str = "gpt-5.4-pro",
        workers: int = 1,
        rw_task_root: str | Path = Path(r"E:\THU\2026Spring\SRT\rw-task"),
        python_exe: str | Path = Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
        max_apply_count: int = 3,
    ) -> Phase12SubstrateHardeningReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = Phase12SubstrateHardeningRequest(
            substrate_audit_report_path=str(substrate_audit_report_path),
            typed_resource_patch_proposals_path=str(typed_resource_patch_proposals_path),
            typed_resource_patch_proposal_report_path=str(typed_resource_patch_proposal_report_path),
            registry_path=str(registry_path),
            seed_report_path=str(seed_report_path),
            readiness_report_path=str(readiness_report_path),
            transition_graph_report_path=str(transition_graph_report_path),
            composition_readiness_report_path=str(composition_readiness_report_path),
            output_dir=str(output_path),
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=str(motif_grammar_path) if motif_grammar_path else None,
            model=model,
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
            max_apply_count=max_apply_count,
        )

        audit = PipelineASubstrateAuditReport.model_validate(load_json_file(str(substrate_audit_report_path)))
        proposal_report = TypedResourcePatchProposalReport.model_validate(
            load_json_file(str(typed_resource_patch_proposal_report_path))
        )

        review_dir = output_path / "typed_resource_review"
        review_dir.mkdir(parents=True, exist_ok=True)
        review_report = self._typed_resource_review(
            proposals_path=typed_resource_patch_proposals_path,
            proposal_report=proposal_report,
            registry_path=registry_path,
            output_dir=review_dir,
        )

        source_support_report = self._source_support_expansion(audit, output_path)
        transition_report = self._transition_evidence_proposals(audit, output_path)
        promotion_report = self._promotion_batch(
            typed_resource_patch_proposals_path=typed_resource_patch_proposals_path,
            registry_path=registry_path,
            output_dir=output_path / "promotion_batch",
            review_report=review_report,
            max_apply_count=max_apply_count,
        )

        rerun = self._rerun_with_registry(
            registry_path=promotion_report.scratch_registry_path,
            seed_report_path=seed_report_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_root=output_path / f"post_promotion_regression_{max_cases}case",
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
            promotion_report_path=output_path / "promotion_batch" / "promotion_report.json",
        )
        post_audit = PipelineASubstrateAuditReport.model_validate(
            load_json_file(str(rerun["substrate_audit_report_path"]))
        )
        pre_batch_report_path = audit.request.batch_report_path
        pre_batch_report = load_json_file(str(pre_batch_report_path))
        post_batch_report = load_json_file(str(rerun["batch_report_path"]))

        pre_diag = (pre_batch_report.get("diagnostics") or {})
        post_diag = (post_batch_report.get("diagnostics") or {})
        summary = Phase12SubstrateHardeningSummary(
            pre_candidate_ready_count=(pre_diag.get("quality_decision_counts") or {}).get("candidate_ready", 0),
            post_candidate_ready_count=(post_diag.get("quality_decision_counts") or {}).get("candidate_ready", 0),
            pre_verifier_pass_count=(pre_diag.get("verifier_status_counts") or {}).get("pass", 0),
            post_verifier_pass_count=(post_diag.get("verifier_status_counts") or {}).get("pass", 0),
            pre_missing_typed_resource_skill_count=audit.diagnostics.missing_typed_resource_skill_count,
            post_missing_typed_resource_skill_count=post_audit.diagnostics.missing_typed_resource_skill_count,
            pre_transition_gap_skill_count=audit.diagnostics.transition_gap_skill_count,
            post_transition_gap_skill_count=post_audit.diagnostics.transition_gap_skill_count,
            pre_subgraph_confidence_counts=dict(pre_diag.get("subgraph_confidence_counts") or {}),
            post_subgraph_confidence_counts=dict(post_diag.get("subgraph_confidence_counts") or {}),
            applied_promotion_count=promotion_report.applied_promotion_count,
            rollback_record_count=promotion_report.rollback_record_count,
            quality_regression_detected=(
                (post_diag.get("quality_decision_counts") or {}).get("candidate_ready", 0)
                < (pre_diag.get("quality_decision_counts") or {}).get("candidate_ready", 0)
            ),
        )

        report = Phase12SubstrateHardeningReport(
            request=request,
            typed_resource_review_report_path=str(review_dir / "phase12_typed_resource_review_report.json"),
            promotion_batch_report_path=str(output_path / "promotion_batch" / "phase12_promotion_batch_report.json"),
            source_support_expansion_report_path=str(output_path / "phase12_source_support_expansion_report.json"),
            transition_evidence_proposal_report_path=str(
                output_path / "phase12_transition_evidence_proposal_report.json"
            ),
            post_batch_report_path=rerun["batch_report_path"],
            post_batch_feedback_report_path=rerun["batch_feedback_report_path"],
            post_substrate_audit_report_path=rerun["substrate_audit_report_path"],
            post_typed_resource_patch_report_path=rerun["typed_resource_patch_report_path"],
            post_dashboard_report_path=rerun["dashboard_report_path"],
            scratch_registry_path=promotion_report.scratch_registry_path,
            summary=summary,
            notes=[
                "Phase 12 substrate hardening uses a reviewed registry copy and never mutates the canonical registry silently.",
                "Applied promotions remain append-only typed-resource patches and keep rollback records.",
                "Source support and transition evidence outputs are proposal layers only; they do not raise readiness automatically.",
            ],
        )
        (output_path / "phase12_substrate_audit_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _typed_resource_review(
        self,
        proposals_path: str | Path,
        proposal_report: TypedResourcePatchProposalReport,
        registry_path: str | Path,
        output_dir: Path,
    ) -> Phase12TypedResourceReviewReport:
        full_proposals = TypedResourcePatchProposalReport.model_validate(load_json_file(str(proposals_path)))
        promotion_artifact = PromotionManager().build_proposals(
            typed_resource_patch_proposals_path=proposals_path,
            registry_path=registry_path,
            output_dir=output_dir / "promotion_review",
        )
        promotion_by_skill = {
            (promotion.target_ids[0] if promotion.target_ids else ""): promotion
            for promotion in promotion_artifact.promotions
        }
        tier_records: List[TypedResourceTierRecord] = []
        tier_counts: Counter[str] = Counter()
        for proposal in full_proposals.skill_patch_proposals:
            resources = (
                list(proposal.proposed_required_resources)
                + list(proposal.proposed_optional_resources)
                + list(proposal.proposed_provided_resources)
            )
            medium_count = sum(1 for item in resources if item.confidence == "medium")
            low_count = sum(1 for item in resources if item.confidence == "low")
            unknown_count = sum(
                1 for item in resources if item.proposed_resource.resource_type == "UnknownResource"
            )
            promotion = promotion_by_skill.get(proposal.skill_id)
            tier, rationale = self._tier_for_proposal(
                proposal_status=proposal.proposal_status,
                risk_reason_codes=proposal.risk_reason_codes,
                low_confidence_count=low_count,
                unknown_resource_count=unknown_count,
            )
            record = TypedResourceTierRecord(
                skill_id=proposal.skill_id,
                canonical_name=proposal.canonical_name,
                tier=tier,
                proposal_status=proposal.proposal_status,
                proposed_resource_count=len(resources),
                medium_confidence_resource_count=medium_count,
                low_confidence_resource_count=low_count,
                unknown_resource_type_count=unknown_count,
                risk_reason_codes=list(proposal.risk_reason_codes),
                apply_eligible=promotion.apply_eligible if promotion else False,
                eligible_promotion_id=promotion.promotion_id if promotion and promotion.apply_eligible else None,
                source_promotion_key=promotion.source_promotion_key if promotion else None,
                blocked_reason_codes=list(promotion.blocked_reason_codes) if promotion else [],
                rationale=rationale,
                notes=list(proposal.review_checklist[:2]),
            )
            tier_records.append(record)
            tier_counts[record.tier] += 1
        report = Phase12TypedResourceReviewReport(
            report_date=date.today().isoformat(),
            source_proposal_report_path=str(Path(proposal_report.request.output_dir) / "typed_resource_patch_proposal_report.json"),
            source_proposals_path=str(proposals_path),
            tier_counts=dict(sorted(tier_counts.items())),
            eligible_promotion_count=promotion_artifact.diagnostics.eligible_promotion_count,
            eligible_unreviewed_promotion_count=promotion_artifact.diagnostics.eligible_unreviewed_promotion_count,
            no_effective_diff_promotion_count=promotion_artifact.diagnostics.no_effective_diff_promotion_count,
            tier_records=tier_records,
            notes=[
                "Tier A means medium-confidence reviewed apply is plausible after explicit reviewer approval.",
                "Tier B means proposal content exists but still needs source-span or risk review before apply.",
                "Tier C means low-confidence patch content should stay diagnostic only.",
                "Tier D means new source evidence is needed before patching.",
            ],
        )
        (output_dir / "phase12_typed_resource_review_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _tier_for_proposal(
        self,
        proposal_status: str,
        risk_reason_codes: List[str],
        low_confidence_count: int,
        unknown_resource_count: int,
    ) -> tuple[TierLabel, str]:
        risk_set = set(risk_reason_codes)
        if proposal_status == "needs_source_evidence":
            return "tier_d", "New source evidence is required before a reviewed patch is safe."
        if unknown_resource_count or "unknown_resource_type" in risk_set:
            return "tier_c", "Unknown resource typing keeps this proposal diagnostic-only."
        if low_confidence_count > 0 or "low_confidence_patch" in risk_set:
            return "tier_c", "Low-confidence inferred resources should not be applied in Phase 12."
        if proposal_status == "requires_review":
            if risk_set <= {"transition_evidence_absent_or_local_only"}:
                return "tier_a", "Medium-confidence patch is ready for reviewed apply on a governed registry copy."
            return "tier_b", "Proposal content exists, but still needs source-span or governance review."
        return "tier_b", "Proposal requires additional review before promotion."

    def _source_support_expansion(
        self,
        audit: PipelineASubstrateAuditReport,
        output_dir: Path,
    ) -> Phase12SourceSupportExpansionReport:
        proposals: List[SourceSupportProposal] = []
        for record in audit.skill_records:
            if "candidate_needs_new_source_evidence" not in record.diagnoses:
                continue
            domain = record.domain_tags[0] if record.domain_tags else "business"
            motifs = record.batch_motifs or ["workflow_task"]
            queries = [
                f"{record.canonical_name} {domain} workflow example",
                f"{record.canonical_name} {motifs[0]} evidence example",
            ]
            proposals.append(
                SourceSupportProposal(
                    skill_id=record.skill_id,
                    canonical_name=record.canonical_name,
                    source_candidate_count=record.registry_source_candidate_count,
                    batch_motifs=list(record.batch_motifs),
                    search_queries=queries,
                    notes=[
                        "Do not raise readiness directly from this proposal.",
                        "Prefer collecting one additional independent source before changing support-diversity judgments.",
                    ],
                )
            )
        report = Phase12SourceSupportExpansionReport(
            report_date=date.today().isoformat(),
            expansion_candidate_count=len(proposals),
            proposals=proposals,
            notes=[
                "This is a collection proposal layer only; it does not mutate readiness or the registry.",
            ],
        )
        (output_dir / "phase12_source_support_expansion_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _transition_evidence_proposals(
        self,
        audit: PipelineASubstrateAuditReport,
        output_dir: Path,
    ) -> Phase12TransitionEvidenceProposalReport:
        proposals: List[TransitionEvidenceProposal] = []
        for record in audit.skill_records:
            local_only = record.transition_evidence.local_only_edge_count
            edge_ids = list(record.transition_evidence.transition_edge_ids)
            if not local_only and not edge_ids:
                continue
            proposals.append(
                TransitionEvidenceProposal(
                    skill_id=record.skill_id,
                    canonical_name=record.canonical_name,
                    local_only_edge_count=local_only,
                    transition_edge_ids=edge_ids,
                    observational_candidate=bool(local_only or edge_ids),
                    notes=[
                        "Carry these edges into TransitionPriorStore V0 observations before considering any future prior learning.",
                        "Do not change sampler priors directly from local-only edges.",
                    ],
                )
            )
        report = Phase12TransitionEvidenceProposalReport(
            report_date=date.today().isoformat(),
            proposal_count=len(proposals),
            proposals=proposals,
            notes=[
                "Transition evidence proposals are observational only and remain downstream of current sampler behavior.",
            ],
        )
        (output_dir / "phase12_transition_evidence_proposal_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _promotion_batch(
        self,
        typed_resource_patch_proposals_path: str | Path,
        registry_path: str | Path,
        output_dir: Path,
        review_report: Phase12TypedResourceReviewReport,
        max_apply_count: int,
    ) -> Phase12PromotionBatchReport:
        output_dir.mkdir(parents=True, exist_ok=True)
        scratch_registry_path = output_dir / "phase12_registry_review_copy.json"
        shutil.copy2(registry_path, scratch_registry_path)

        review_artifact = PromotionManager().build_proposals(
            typed_resource_patch_proposals_path=typed_resource_patch_proposals_path,
            registry_path=scratch_registry_path,
            output_dir=output_dir / "promotion_review",
        )
        source_tier_map = {
            record.source_promotion_key: record
            for record in review_report.tier_records
            if record.source_promotion_key
        }
        eligible = [
            promotion
            for promotion in review_artifact.promotions
            if promotion.apply_eligible and source_tier_map.get(promotion.source_promotion_key, None)
            and source_tier_map[promotion.source_promotion_key].tier == "tier_a"
        ]
        eligible.sort(key=lambda item: item.source_promotion_key)

        action_records: List[PromotionBatchActionRecord] = []
        applied_count = 0
        rollback_count = 0
        for promotion in review_artifact.promotions:
            target_skill_id = promotion.target_ids[0] if promotion.target_ids else None
            if applied_count >= max_apply_count or promotion not in eligible:
                action_records.append(
                    PromotionBatchActionRecord(
                        source_promotion_key=promotion.source_promotion_key,
                        promotion_id=promotion.promotion_id,
                        skill_id=target_skill_id,
                        action="skipped",
                        apply_eligible=promotion.apply_eligible,
                        blocked_reason_codes=list(promotion.blocked_reason_codes),
                        output_dir=str(output_dir / "promotion_review"),
                        notes=["Not selected for this limited Phase 12 reviewed apply batch."],
                    )
                )
                continue
            apply_dir = output_dir / f"apply_{applied_count + 1:02d}_{target_skill_id}"
            applied = PromotionManager().apply_promotion(
                typed_resource_patch_proposals_path=typed_resource_patch_proposals_path,
                registry_path=scratch_registry_path,
                output_dir=apply_dir,
                apply_promotion_id=promotion.promotion_id,
                reviewer="phase12_substrate_hardening",
                approval_note="Phase 12 reviewed append-only typed-resource patch on scratch registry copy.",
            )
            rollback_path = apply_dir / "rollback_record.json"
            applied_count += 1
            if rollback_path.exists():
                rollback_count += 1
            action_records.append(
                PromotionBatchActionRecord(
                    source_promotion_key=promotion.source_promotion_key,
                    promotion_id=promotion.promotion_id,
                    skill_id=target_skill_id,
                    action="applied",
                    apply_eligible=True,
                    blocked_reason_codes=[],
                    output_dir=str(apply_dir),
                    rollback_record_path=str(rollback_path) if rollback_path.exists() else None,
                    notes=applied.notes,
                )
            )

        report = Phase12PromotionBatchReport(
            report_date=date.today().isoformat(),
            source_proposals_path=str(typed_resource_patch_proposals_path),
            scratch_registry_path=str(scratch_registry_path),
            promotion_review_report_path=str(output_dir / "promotion_review" / "promotion_report.json"),
            max_apply_count=max_apply_count,
            reviewed_promotion_count=review_artifact.diagnostics.promotion_count,
            eligible_promotion_count=len(eligible),
            applied_promotion_count=applied_count,
            rollback_record_count=rollback_count,
            action_records=action_records,
            notes=[
                "Promotion apply is limited to a scratch registry copy in this Phase 12 hardening batch.",
                "Use source_promotion_key to track the same patch intent across scratch and future canonical review.",
            ],
        )
        (output_dir / "phase12_promotion_batch_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _rerun_with_registry(
        self,
        registry_path: str | Path,
        seed_report_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_root: Path,
        max_cases: int,
        allow_caution: bool,
        motif_grammar_path: Optional[str | Path],
        model: str,
        workers: int,
        rw_task_root: str | Path,
        python_exe: str | Path,
        promotion_report_path: str | Path,
    ) -> Dict[str, str]:
        batch_dir = output_root / "batch"
        feedback_dir = output_root / "feedback"
        substrate_dir = output_root / "substrate"
        typed_patch_dir = output_root / "typed_resource_review"
        dashboard_dir = output_root / "dashboard"

        PipelineBBatchRunner().run(
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            output_dir=batch_dir,
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
        )
        batch_report_path = batch_dir / "pipeline_b_batch_report.json"
        PipelineBBatchFeedbackAnalyzer().analyze(batch_report_path=batch_report_path, output_dir=feedback_dir)
        batch_feedback_path = feedback_dir / "pipeline_b_batch_feedback_report.json"
        PipelineASubstrateAuditor().audit(
            batch_feedback_report_path=batch_feedback_path,
            batch_report_path=batch_report_path,
            registry_path=registry_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_dir=substrate_dir,
        )
        substrate_report_path = substrate_dir / "pipeline_a_substrate_audit_report.json"
        TypedResourcePatchProposalBuilder().build(
            substrate_audit_report_path=substrate_report_path,
            output_dir=typed_patch_dir,
            include_low_confidence=True,
        )
        typed_patch_report_path = typed_patch_dir / "typed_resource_patch_proposal_report.json"
        GlobalPipelineDashboardBuilder().build(
            batch_report_path=batch_report_path,
            batch_feedback_report_path=batch_feedback_path,
            substrate_audit_report_path=substrate_report_path,
            typed_resource_patch_proposal_report_path=typed_patch_report_path,
            promotion_report_path=promotion_report_path,
            output_dir=dashboard_dir,
        )
        dashboard_path = dashboard_dir / "global_pipeline_dashboard_report.json"
        return {
            "batch_report_path": str(batch_report_path),
            "batch_feedback_report_path": str(batch_feedback_path),
            "substrate_audit_report_path": str(substrate_report_path),
            "typed_resource_patch_report_path": str(typed_patch_report_path),
            "dashboard_report_path": str(dashboard_path),
        }
