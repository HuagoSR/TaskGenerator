from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_production_qa_gate import (
    ProductionQACaseDecision,
    ProductionQAGateReport,
)
from task_generator.v3_source_schema import load_json_file


ReviewedDecision = Literal["blocked", "review_required", "approved_production_candidate"]


class ProductionReviewRule(BaseModel):
    rule_id: str
    description: str
    approve_for_production: bool = False
    case_ids: List[str] = Field(default_factory=list)
    motifs: List[str] = Field(default_factory=list)
    template_families: List[str] = Field(default_factory=list)
    required_warning_codes: List[str] = Field(default_factory=list)
    max_warning_codes: Optional[int] = None
    min_real_worldness_score: Optional[float] = None
    allowed_workflow_context_fits: List[str] = Field(default_factory=list)
    reviewer_note: str = ""


class ProductionReviewSpec(BaseModel):
    production_review_spec_version: str = "v3.production_review_spec.1"
    review_id: str
    reviewer: str
    batch_id: Optional[str] = None
    default_action: ReviewedDecision = "review_required"
    rules: List[ProductionReviewRule] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ProductionPromotionRequest(BaseModel):
    production_batch_manifest_path: str
    base_production_qa_gate_report_path: str
    production_review_spec_path: str
    output_dir: str


class ProductionPromotionReviewRecord(BaseModel):
    case_id: str
    base_decision: str
    final_decision: ReviewedDecision
    promoted_to_production_candidate: bool = False
    matched_rule_ids: List[str] = Field(default_factory=list)
    reviewer: str
    reviewer_notes: List[str] = Field(default_factory=list)


class ProductionPromotionSummary(BaseModel):
    case_count: int = 0
    approved_production_candidate_count: int = 0
    review_required_count: int = 0
    blocked_count: int = 0
    reviewed_promotion_count: int = 0
    rule_match_counts: Dict[str, int] = Field(default_factory=dict)


class ProductionPromotionArtifact(BaseModel):
    production_promotion_manager_version: str = "v3.production_promotion_manager.1"
    request: ProductionPromotionRequest
    review_spec: ProductionReviewSpec
    reviewed_decisions: List[ProductionPromotionReviewRecord] = Field(default_factory=list)
    summary: ProductionPromotionSummary
    notes: List[str] = Field(default_factory=list)


class ProductionPromotionManager:
    def apply_review(
        self,
        production_batch_manifest_path: str | Path,
        base_production_qa_gate_report_path: str | Path,
        production_review_spec_path: str | Path,
        output_dir: str | Path,
    ) -> ProductionPromotionArtifact:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = ProductionPromotionRequest(
            production_batch_manifest_path=str(production_batch_manifest_path),
            base_production_qa_gate_report_path=str(base_production_qa_gate_report_path),
            production_review_spec_path=str(production_review_spec_path),
            output_dir=str(output_path),
        )
        manifest = load_json_file(str(production_batch_manifest_path))
        base_report = ProductionQAGateReport.model_validate(load_json_file(str(base_production_qa_gate_report_path)))
        review_spec = ProductionReviewSpec.model_validate(load_json_file(str(production_review_spec_path)))

        cases_by_id = {
            str(case.get("case_id")): case
            for case in (manifest.get("cases") or [])
            if isinstance(case, dict) and case.get("case_id")
        }

        reviewed_decisions: List[ProductionPromotionReviewRecord] = []
        updated_decisions: List[ProductionQACaseDecision] = []
        rule_match_counts: Dict[str, int] = {}
        for decision in base_report.decisions:
            case_payload = cases_by_id.get(decision.case_id, {})
            review_record, updated_decision = self._review_case(
                decision=decision,
                case_payload=case_payload,
                review_spec=review_spec,
            )
            reviewed_decisions.append(review_record)
            updated_decisions.append(updated_decision)
            for rule_id in review_record.matched_rule_ids:
                rule_match_counts[rule_id] = rule_match_counts.get(rule_id, 0) + 1

        reviewed_report = ProductionQAGateReport(
            request=base_report.request,
            production_batch_id=base_report.production_batch_id,
            decisions=updated_decisions,
            summary=base_report._summary(updated_decisions) if hasattr(base_report, "_summary") else self._summary_for_report(updated_decisions),
            notes=[
                *base_report.notes,
                "This reviewed QA report includes explicit reviewer-driven production promotion decisions.",
                f"Reviewer: {review_spec.reviewer}. Review id: {review_spec.review_id}.",
            ],
        )
        artifact = ProductionPromotionArtifact(
            request=request,
            review_spec=review_spec,
            reviewed_decisions=reviewed_decisions,
            summary=ProductionPromotionSummary(
                case_count=len(reviewed_decisions),
                approved_production_candidate_count=sum(
                    1 for item in reviewed_decisions if item.final_decision == "approved_production_candidate"
                ),
                review_required_count=sum(
                    1 for item in reviewed_decisions if item.final_decision == "review_required"
                ),
                blocked_count=sum(1 for item in reviewed_decisions if item.final_decision == "blocked"),
                reviewed_promotion_count=sum(1 for item in reviewed_decisions if item.promoted_to_production_candidate),
                rule_match_counts=dict(sorted(rule_match_counts.items())),
            ),
            notes=[
                "Production promotion manager is explicit-review-only; it does not silently approve cases.",
                "Only review_required cases can be promoted through matched review rules.",
                "Structural blocking findings still remain non-overridable in this slice.",
            ],
        )
        (output_path / "production_promotion_report.json").write_text(
            artifact.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output_path / "reviewed_production_qa_gate_report.json").write_text(
            reviewed_report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return artifact

    def _review_case(
        self,
        decision: ProductionQACaseDecision,
        case_payload: Dict[str, object],
        review_spec: ProductionReviewSpec,
    ) -> tuple[ProductionPromotionReviewRecord, ProductionQACaseDecision]:
        matched_rules: List[ProductionReviewRule] = []
        warning_codes = [finding.code for finding in decision.findings if finding.severity == "warning"]
        for rule in review_spec.rules:
            if self._rule_matches(rule, decision, case_payload, warning_codes):
                matched_rules.append(rule)

        final_decision: ReviewedDecision = review_spec.default_action
        promoted = False
        reviewer_notes: List[str] = []
        updated_decision = decision.model_copy(deep=True)
        if decision.decision == "blocked":
            final_decision = "blocked"
            reviewer_notes.append("Structural blockers remain non-overridable.")
        elif decision.decision == "approved_production_candidate":
            final_decision = "approved_production_candidate"
        else:
            approving_rule = next((rule for rule in matched_rules if rule.approve_for_production), None)
            if approving_rule is not None:
                final_decision = "approved_production_candidate"
                promoted = True
                updated_decision.decision = "approved_production_candidate"
                updated_decision.proposed_task_state = "production_candidate"
                updated_decision.production_candidate_approved = True
                reviewer_notes.append(approving_rule.reviewer_note or approving_rule.description)
            else:
                final_decision = review_spec.default_action
                updated_decision.decision = final_decision
                reviewer_notes.append("No explicit approving rule matched; case remains under governed review.")

        review_record = ProductionPromotionReviewRecord(
            case_id=decision.case_id,
            base_decision=decision.decision,
            final_decision=final_decision,
            promoted_to_production_candidate=promoted,
            matched_rule_ids=[rule.rule_id for rule in matched_rules],
            reviewer=review_spec.reviewer,
            reviewer_notes=reviewer_notes,
        )
        return review_record, updated_decision

    def _rule_matches(
        self,
        rule: ProductionReviewRule,
        decision: ProductionQACaseDecision,
        case_payload: Dict[str, object],
        warning_codes: List[str],
    ) -> bool:
        if decision.decision != "review_required":
            return False
        if rule.case_ids and decision.case_id not in rule.case_ids:
            return False
        motif = str(case_payload.get("motif") or "")
        if rule.motifs and motif not in rule.motifs:
            return False
        template_family = str(case_payload.get("template_family") or "")
        if rule.template_families and template_family not in rule.template_families:
            return False
        if rule.required_warning_codes:
            if not all(code in warning_codes for code in rule.required_warning_codes):
                return False
        if rule.max_warning_codes is not None and len(warning_codes) > rule.max_warning_codes:
            return False
        if rule.min_real_worldness_score is not None:
            score = case_payload.get("real_worldness_score")
            if not isinstance(score, (int, float)) or float(score) < rule.min_real_worldness_score:
                return False
        if rule.allowed_workflow_context_fits:
            workflow_context_fit = str(case_payload.get("workflow_context_fit") or "")
            if workflow_context_fit not in rule.allowed_workflow_context_fits:
                return False
        return True

    def _summary_for_report(
        self,
        decisions: List[ProductionQACaseDecision],
    ):
        from task_generator.v3_production_qa_gate import ProductionQAGateSummary

        decision_counts: Dict[str, int] = {}
        finding_code_counts: Dict[str, int] = {}
        blocking_finding_count = 0
        warning_finding_count = 0
        for decision in decisions:
            decision_counts[decision.decision] = decision_counts.get(decision.decision, 0) + 1
            for finding in decision.findings:
                finding_code_counts[finding.code] = finding_code_counts.get(finding.code, 0) + 1
                if finding.severity == "blocking":
                    blocking_finding_count += 1
                if finding.severity == "warning":
                    warning_finding_count += 1
        return ProductionQAGateSummary(
            case_count=len(decisions),
            approved_production_candidate_count=sum(
                1 for decision in decisions if decision.decision == "approved_production_candidate"
            ),
            review_required_count=sum(1 for decision in decisions if decision.decision == "review_required"),
            blocked_count=sum(1 for decision in decisions if decision.decision == "blocked"),
            blocking_finding_count=blocking_finding_count,
            warning_finding_count=warning_finding_count,
            decision_counts=dict(sorted(decision_counts.items())),
            finding_code_counts=dict(sorted(finding_code_counts.items())),
        )
