from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class LLMShadowReviewRequest(BaseModel):
    llm_shadow_execute_report_path: str
    output_dir: str


class LLMShadowRecordReview(BaseModel):
    shadow_kind: str
    task_id: str
    status: str
    metric_status: str
    labels: Dict[str, bool] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    recommendation: str
    rationale: List[str] = Field(default_factory=list)


class LLMShadowRoleReview(BaseModel):
    shadow_kind: str
    reviewed_count: int
    helpful_rate: float
    harmful_rate: float
    unsupported_claim_rate: float
    evidence_mismatch_rate: float
    candidate_visible_leakage_rate: float
    adoption_recommendation: str
    rationale: List[str] = Field(default_factory=list)


class LLMShadowReviewReport(BaseModel):
    report_version: str = "v3.phase15_llm_shadow_review.1"
    created_at: str
    request: LLMShadowReviewRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    record_reviews: List[LLMShadowRecordReview] = Field(default_factory=list)
    role_reviews: List[LLMShadowRoleReview] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class LLMAdoptionGateReport(BaseModel):
    report_version: str = "v3.phase15_llm_adoption_gate.1"
    created_at: str
    diagnostic_only: bool = True
    gate_policy: Dict[str, Any] = Field(default_factory=dict)
    role_recommendations: Dict[str, str] = Field(default_factory=dict)
    candidate_mode_default_enabled: bool = False
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class LLMShadowReviewBuilder:
    def build(self, request: LLMShadowReviewRequest) -> LLMShadowReviewReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        execute_report = self._read_json(Path(request.llm_shadow_execute_report_path))
        records = execute_report.get("records") or []
        record_reviews = [self._review_record(record) for record in records]
        role_reviews = self._role_reviews(record_reviews)
        report = LLMShadowReviewReport(
            created_at=self._now(),
            request=request,
            record_reviews=record_reviews,
            role_reviews=role_reviews,
            notes=[
                "This is a deterministic Phase 15 review of Phase 14 shadow metrics.",
                "It does not call external models and does not promote any LLM role into the production chain.",
                "Candidate-visible leakage and evidence mismatch are treated conservatively until human review.",
            ],
        )
        gate = self._adoption_gate(role_reviews)
        self._write_json(output_dir / "llm_shadow_review_report.json", report.model_dump(mode="json"))
        self._write_json(output_dir / "llm_adoption_gate_report.json", gate.model_dump(mode="json"))
        return report

    def _review_record(self, record: Dict[str, Any]) -> LLMShadowRecordReview:
        metrics = dict(record.get("metrics") or {})
        labels = self._labels(record, metrics)
        recommendation, rationale = self._record_recommendation(record, labels, metrics)
        return LLMShadowRecordReview(
            shadow_kind=str(record.get("shadow_kind") or "unknown"),
            task_id=str(record.get("task_id") or "unknown"),
            status=str(record.get("status") or "unknown"),
            metric_status=str(record.get("metric_status") or "unknown"),
            labels=labels,
            metrics=metrics,
            recommendation=recommendation,
            rationale=rationale,
        )

    def _labels(self, record: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, bool]:
        hidden_count = int(metrics.get("hidden_info_violation_count") or 0)
        ground_truth_mutation = int(metrics.get("ground_truth_mutation_count") or 0)
        invalid_refs = int(metrics.get("invalid_evidence_ref_count") or 0)
        evidence_id_mutation = int(metrics.get("evidence_id_mutation_count") or 0)
        unsupported_rate = float(metrics.get("unsupported_claim_rate") or 0)
        valid_ref_rate = metrics.get("valid_evidence_ref_rate")
        format_noise_delta = int(metrics.get("format_noise_delta") or 0)
        helpful = bool(metrics.get("output_nonempty")) and (
            int(metrics.get("missing_step_candidates") or 0) > 0
            or int(metrics.get("added_capability_criteria") or 0) > 0
            or int(metrics.get("narrative_improvement_candidates") or 0) > 0
            or bool(metrics.get("workflow_realism_notes"))
        )
        evidence_mismatch = invalid_refs > 0 or evidence_id_mutation > 0 or (valid_ref_rate is not None and float(valid_ref_rate) < 1.0)
        candidate_visible_leakage = hidden_count > 0
        harmful = candidate_visible_leakage or ground_truth_mutation > 0 or evidence_mismatch
        return {
            "helpful": helpful,
            "neutral": bool(metrics.get("output_nonempty")) and not helpful and not harmful,
            "harmful": harmful,
            "ground_truth_mutation": ground_truth_mutation > 0,
            "unsupported_claim": unsupported_rate > 0,
            "evidence_mismatch": evidence_mismatch,
            "policy_mismatch": False,
            "format_noise_added": format_noise_delta > 0,
            "better_realism": bool(metrics.get("workflow_realism_notes")),
            "better_training_signal": int(metrics.get("missing_step_candidates") or 0) > 0
            or int(metrics.get("added_capability_criteria") or 0) > 0,
            "better_rubric_dimension": int(metrics.get("added_capability_criteria") or 0) > 0,
            "hallucinated_business_context": unsupported_rate > 0,
            "candidate_visible_leakage": candidate_visible_leakage,
        }

    def _record_recommendation(
        self,
        record: Dict[str, Any],
        labels: Dict[str, bool],
        metrics: Dict[str, Any],
    ) -> tuple[str, List[str]]:
        rationale: List[str] = []
        if record.get("status") != "completed" or record.get("metric_status") != "computed":
            return "skip_incomplete", ["Shadow output or metrics are incomplete."]
        if labels.get("ground_truth_mutation"):
            rationale.append("Ground-truth mutation detected.")
        if labels.get("candidate_visible_leakage"):
            rationale.append(f"hidden_info_violation_count={metrics.get('hidden_info_violation_count')}")
        if labels.get("evidence_mismatch"):
            rationale.append("Evidence reference mismatch detected.")
        if labels.get("unsupported_claim"):
            rationale.append(f"unsupported_claim_rate={metrics.get('unsupported_claim_rate')}")
        if labels.get("helpful"):
            rationale.append("Useful candidate signal is present.")
        if labels.get("harmful"):
            return "needs_human_review", rationale
        if labels.get("helpful"):
            return "candidate_signal", rationale
        return "shadow_only", rationale or ["No strong helpful or harmful signal detected."]

    def _role_reviews(self, record_reviews: List[LLMShadowRecordReview]) -> List[LLMShadowRoleReview]:
        roles = sorted({review.shadow_kind for review in record_reviews})
        role_reviews: List[LLMShadowRoleReview] = []
        for role in roles:
            items = [review for review in record_reviews if review.shadow_kind == role]
            count = len(items)
            helpful_rate = self._rate(items, "helpful")
            harmful_rate = self._rate(items, "harmful")
            unsupported_claim_rate = self._rate(items, "unsupported_claim")
            evidence_mismatch_rate = self._rate(items, "evidence_mismatch")
            leakage_rate = self._rate(items, "candidate_visible_leakage")
            recommendation, rationale = self._role_recommendation(
                role,
                helpful_rate,
                harmful_rate,
                unsupported_claim_rate,
                evidence_mismatch_rate,
                leakage_rate,
            )
            role_reviews.append(
                LLMShadowRoleReview(
                    shadow_kind=role,
                    reviewed_count=count,
                    helpful_rate=helpful_rate,
                    harmful_rate=harmful_rate,
                    unsupported_claim_rate=unsupported_claim_rate,
                    evidence_mismatch_rate=evidence_mismatch_rate,
                    candidate_visible_leakage_rate=leakage_rate,
                    adoption_recommendation=recommendation,
                    rationale=rationale,
                )
            )
        return role_reviews

    def _role_recommendation(
        self,
        role: str,
        helpful_rate: float,
        harmful_rate: float,
        unsupported_claim_rate: float,
        evidence_mismatch_rate: float,
        leakage_rate: float,
    ) -> tuple[str, List[str]]:
        rationale = [
            f"helpful_rate={helpful_rate:.2f}",
            f"harmful_rate={harmful_rate:.2f}",
            f"unsupported_claim_rate={unsupported_claim_rate:.2f}",
            f"evidence_mismatch_rate={evidence_mismatch_rate:.2f}",
            f"candidate_visible_leakage_rate={leakage_rate:.2f}",
        ]
        passes_adoption_threshold = (
            helpful_rate >= 0.60
            and harmful_rate <= 0.10
            and unsupported_claim_rate <= 0.05
            and evidence_mismatch_rate <= 0.05
            and leakage_rate <= 0.05
        )
        if passes_adoption_threshold:
            return "adopt_candidate_limited_experiment", rationale
        if role == "realism_critic" and helpful_rate >= 0.60 and unsupported_claim_rate <= 0.05 and evidence_mismatch_rate <= 0.05:
            rationale.append("Realism critic can remain diagnostic because it does not directly modify artifacts.")
            return "shadow_only", rationale
        if role in {"goldenrun", "rubric"} and leakage_rate > 0.0:
            rationale.append("Primary truth or scoring-adjacent roles are too risky while leakage is nonzero.")
            return "reject_for_now", rationale
        return "needs_more_review", rationale

    def _adoption_gate(self, role_reviews: List[LLMShadowRoleReview]) -> LLMAdoptionGateReport:
        role_recommendations = {review.shadow_kind: review.adoption_recommendation for review in role_reviews}
        return LLMAdoptionGateReport(
            created_at=self._now(),
            gate_policy={
                "adopt_candidate": {
                    "helpful_rate_min": 0.60,
                    "harmful_rate_max": 0.10,
                    "unsupported_claim_rate_max": 0.05,
                    "evidence_mismatch_rate_max": 0.05,
                    "candidate_visible_leakage_rate_max": 0.05,
                },
                "primary_truth_roles": ["goldenrun"],
                "scoring_adjacent_roles": ["rubric"],
                "diagnostic_roles": ["realism_critic", "reference_narrative"],
            },
            role_recommendations=role_recommendations,
            candidate_mode_default_enabled=False,
            next_actions=[
                "Human-review role-level metric alignment before enabling any guarded LLM candidate experiment.",
                "Prioritize realism_critic as a diagnostic-only signal if Phase 15 needs an LLM-assisted first experiment.",
                "Do not promote GoldenRun or rubric candidate roles while candidate-visible leakage remains nonzero.",
            ],
            notes=[
                "No LLM role is silently promoted by this gate.",
                "The gate is conservative because Phase 15 treats LLM outputs as candidate evidence only.",
            ],
        )

    def _rate(self, items: List[LLMShadowRecordReview], label: str) -> float:
        if not items:
            return 0.0
        return sum(1 for item in items if item.labels.get(label)) / len(items)

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
