from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


DEFAULT_BATCH_REPORTS = [
    "llm_goldenrun_shadow_batch_report.json",
    "llm_rubric_shadow_batch_report.json",
    "llm_realism_critic_batch_report.json",
    "llm_reference_narrative_suggestion_batch_report.json",
]


class LLMImpactEvaluationRequest(BaseModel):
    llm_shadow_dir: str
    output_dir: str


class LLMShadowKindImpact(BaseModel):
    shadow_kind: str
    selected_task_count: int = 0
    prepared_count: int = 0
    awaiting_llm_output_count: int = 0
    completed_metric_count: int = 0
    metric_readiness: str = "not_ready"
    missing_evidence: List[str] = Field(default_factory=list)


class LLMImpactEvaluationReport(BaseModel):
    report_version: str = "v3.llm_impact_evaluation.1"
    created_at: str
    request: LLMImpactEvaluationRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    shadow_kind_count: int
    total_prepared_task_shadows: int
    total_awaiting_llm_output: int
    total_completed_metric_count: int
    impact_readiness: str
    kind_impacts: List[LLMShadowKindImpact] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class LLMShadowFailureTaxonomy(BaseModel):
    report_version: str = "v3.llm_shadow_failure_taxonomy.1"
    created_at: str
    diagnostic_only: bool = True
    failure_counts: Dict[str, int] = Field(default_factory=dict)
    details: List[Dict[str, Any]] = Field(default_factory=list)


class LLMAdoptionRecommendationReport(BaseModel):
    report_version: str = "v3.llm_adoption_recommendation.1"
    created_at: str
    diagnostic_only: bool = True
    recommendation: str
    rationale: List[str] = Field(default_factory=list)
    required_next_evidence: List[str] = Field(default_factory=list)


class LLMImpactEvaluator:
    def build(self, request: LLMImpactEvaluationRequest) -> LLMImpactEvaluationReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        shadow_dir = Path(request.llm_shadow_dir)
        batch_reports = [self._read_json(shadow_dir / name) for name in DEFAULT_BATCH_REPORTS if (shadow_dir / name).exists()]
        kind_impacts = [self._kind_impact(report) for report in batch_reports]
        total_prepared = sum(item.prepared_count for item in kind_impacts)
        total_awaiting = sum(item.awaiting_llm_output_count for item in kind_impacts)
        total_completed = sum(item.completed_metric_count for item in kind_impacts)
        readiness = "ready_for_impact_analysis" if total_completed > 0 and total_awaiting == 0 else "awaiting_llm_shadow_outputs"
        report = LLMImpactEvaluationReport(
            created_at=self._now(),
            request=request,
            shadow_kind_count=len(kind_impacts),
            total_prepared_task_shadows=total_prepared,
            total_awaiting_llm_output=total_awaiting,
            total_completed_metric_count=total_completed,
            impact_readiness=readiness,
            kind_impacts=kind_impacts,
            notes=[
                "This report evaluates whether LLM shadow evidence is ready for adoption decisions.",
                "It does not call external models and does not infer impact from prompt packages alone.",
                "LLM Candidate Mode remains blocked until real shadow outputs produce computable metrics.",
            ],
        )
        taxonomy = self._failure_taxonomy(batch_reports)
        recommendation = self._recommendation(report)
        self._write_json(output_dir / "llm_impact_evaluation_report.json", report.model_dump(mode="json"))
        self._write_json(output_dir / "llm_shadow_failure_taxonomy.json", taxonomy.model_dump(mode="json"))
        self._write_json(output_dir / "llm_adoption_recommendation_report.json", recommendation.model_dump(mode="json"))
        return report

    def _kind_impact(self, report: Dict[str, Any]) -> LLMShadowKindImpact:
        shadow_kind = str(report.get("shadow_kind") or "unknown")
        awaiting = int(report.get("awaiting_llm_output_count") or 0)
        completed = int(report.get("completed_metric_count") or 0)
        missing = []
        if awaiting:
            missing.append("real_llm_shadow_output")
        if completed == 0:
            missing.append("computed_shadow_metrics")
        return LLMShadowKindImpact(
            shadow_kind=shadow_kind,
            selected_task_count=int(report.get("selected_task_count") or 0),
            prepared_count=int(report.get("prepared_count") or 0),
            awaiting_llm_output_count=awaiting,
            completed_metric_count=completed,
            metric_readiness="ready" if completed and not awaiting else "not_ready",
            missing_evidence=missing,
        )

    def _failure_taxonomy(self, batch_reports: List[Dict[str, Any]]) -> LLMShadowFailureTaxonomy:
        counter = Counter()
        details: List[Dict[str, Any]] = []
        for report in batch_reports:
            shadow_kind = str(report.get("shadow_kind") or "unknown")
            for record in report.get("records") or []:
                if record.get("shadow_status") == "awaiting_llm_output":
                    counter["awaiting_llm_output"] += 1
                    details.append(
                        {
                            "shadow_kind": shadow_kind,
                            "task_id": record.get("task_id"),
                            "failure_type": "awaiting_llm_output",
                            "related_path": record.get("shadow_report_path"),
                        }
                    )
                for reason in record.get("blocking_reasons") or []:
                    counter[str(reason)] += 1
        return LLMShadowFailureTaxonomy(
            created_at=self._now(),
            failure_counts=dict(counter),
            details=details,
        )

    def _recommendation(self, report: LLMImpactEvaluationReport) -> LLMAdoptionRecommendationReport:
        if report.impact_readiness == "ready_for_impact_analysis":
            recommendation = "review_shadow_metrics_before_candidate_mode"
            rationale = ["All shadow metrics are present; compare benefit and risk before promotion."]
            next_evidence = ["human review of metric alignment", "candidate-mode risk gate"]
        else:
            recommendation = "do_not_enter_llm_candidate_mode_yet"
            rationale = [
                "LLM shadow prompt packages exist, but real LLM outputs and computed metrics are missing.",
                "Prompt package readiness alone does not prove LLM improves GoldenRun, rubric, realism, or narrative quality.",
            ]
            next_evidence = [
                "Run approved LLM shadow generation for the prepared 5-task slice.",
                "Compute unsupported claim rate and valid evidence citation rate.",
                "Compute rubric hidden-info violations and realism critique alignment.",
                "Compare shadow metrics against GoodTaskProfiler-Observational and human review.",
            ]
        return LLMAdoptionRecommendationReport(
            created_at=self._now(),
            recommendation=recommendation,
            rationale=rationale,
            required_next_evidence=next_evidence,
        )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
