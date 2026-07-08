from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class GeneratedTaskGapAutopsyRequest(BaseModel):
    generated_task_eval_summary_path: str
    generated_vs_gdpval_gap_path: str
    generated_vs_gdpval_quality_matrix_path: str
    output_dir: str


class GeneratedTaskGapAutopsyCase(BaseModel):
    task_id: str
    motif: str
    strong_model: str
    weak_model: str
    strong_score: float
    weak_score: float
    gap: float
    gap_band: str
    top_gap_sources: List[str] = Field(default_factory=list)
    format_noise_suspected: bool = False
    tool_noise_suspected: bool = False
    productive_complexity_level: str
    frictional_complexity_level: str
    generator_reform_recommendation: List[str] = Field(default_factory=list)
    interpretation: str


class GeneratedTaskGapAutopsyReport(BaseModel):
    report_version: str = "v3.phase15_generated_task_gap_autopsy.1"
    created_at: str
    request: GeneratedTaskGapAutopsyRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    case_count: int
    gap_band_counts: Dict[str, int] = Field(default_factory=dict)
    low_gap_motifs: List[str] = Field(default_factory=list)
    high_gap_motifs: List[str] = Field(default_factory=list)
    recommended_first_reform_target: str
    cases: List[GeneratedTaskGapAutopsyCase] = Field(default_factory=list)
    motif_summaries: Dict[str, Any] = Field(default_factory=dict)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GeneratedTaskGapAutopsyBuilder:
    def build(self, request: GeneratedTaskGapAutopsyRequest) -> GeneratedTaskGapAutopsyReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = self._read_json(Path(request.generated_task_eval_summary_path))
        gap_comparison = self._read_json(Path(request.generated_vs_gdpval_gap_path))
        quality_matrix = self._read_json(Path(request.generated_vs_gdpval_quality_matrix_path))

        cases = [self._case_autopsy(record, summary) for record in summary.get("gap_records") or []]
        band_counts = self._band_counts(cases)
        low_gap_motifs = sorted({case.motif for case in cases if case.gap_band == "low"})
        high_gap_motifs = sorted({case.motif for case in cases if case.gap_band == "high"})
        report = GeneratedTaskGapAutopsyReport(
            created_at=self._now(),
            request=request,
            case_count=len(cases),
            gap_band_counts=band_counts,
            low_gap_motifs=low_gap_motifs,
            high_gap_motifs=high_gap_motifs,
            recommended_first_reform_target="evidence_to_deliverable",
            cases=cases,
            motif_summaries=self._motif_summaries(cases, gap_comparison, quality_matrix),
            next_actions=[
                "Use evidence_to_deliverable as the first Phase 15 generator reform target.",
                "Preserve fan_in_reconciliation as a high-gap reference pattern rather than over-tuning it first.",
                "Map GDPVal productive complexity patterns before changing generator defaults.",
                "Keep reform validation paired: baseline vs reform vs reform+LLM candidate.",
            ],
            notes=[
                "This autopsy reads existing Phase 14 generated-task eval outputs only.",
                "Gap bands remain diagnostic and not benchmark-grade.",
                "Low friction in generated tasks does not imply high training value.",
            ],
        )
        self._write_json(output_dir / "generated_task_gap_autopsy_report.json", report.model_dump(mode="json"))
        return report

    def _case_autopsy(self, record: Dict[str, Any], summary: Dict[str, Any]) -> GeneratedTaskGapAutopsyCase:
        motif = str(record.get("motif") or "unknown")
        gap = float(record.get("score_gap") or 0)
        gap_band = self._gap_band(gap)
        strong_score = float(record.get("strong_score_ratio") or 0)
        weak_score = float(record.get("weak_score_ratio") or 0)
        strong_model = str(record.get("strong_model") or "unknown")
        weak_model = str(record.get("weak_model") or "unknown")
        score_rows = [
            item for item in summary.get("model_scores") or []
            if item.get("task_id") == record.get("task_id")
        ]
        tool_noise = any(item.get("failure_reasons") for item in score_rows)
        format_noise = False
        productive_level = "medium"
        if gap_band == "high":
            productive_level = "high"
        if gap_band == "low":
            productive_level = "low"
        return GeneratedTaskGapAutopsyCase(
            task_id=str(record.get("task_id") or "unknown"),
            motif=motif,
            strong_model=strong_model,
            weak_model=weak_model,
            strong_score=strong_score,
            weak_score=weak_score,
            gap=gap,
            gap_band=gap_band,
            top_gap_sources=self._top_gap_sources(motif, gap_band),
            format_noise_suspected=format_noise,
            tool_noise_suspected=tool_noise,
            productive_complexity_level=productive_level,
            frictional_complexity_level="low" if not tool_noise and not format_noise else "medium",
            generator_reform_recommendation=self._recommendations(motif, gap_band),
            interpretation=self._interpretation(motif, gap_band, strong_score, weak_score, gap),
        )

    def _top_gap_sources(self, motif: str, gap_band: str) -> List[str]:
        if motif == "evidence_to_deliverable":
            return [
                "insufficient_productive_complexity",
                "deliverable_structure_too_template_like",
                "weak_model_can_follow_visible_format",
            ]
        if motif == "cross_check_validation":
            return [
                "cross_file_reasoning",
                "exception_handling",
                "evidence_provenance_tracking",
            ]
        if motif == "fan_in_reconciliation":
            return [
                "numeric_reconciliation",
                "multi_source_synthesis",
                "exception_explanation",
                "manager_facing_conclusion",
            ]
        if motif == "policy_application":
            return [
                "policy_application",
                "evidence_to_policy_citation",
                "professional_judgment",
                "candidate_visible_reasoning",
            ]
        return ["unknown_gap_source"]

    def _recommendations(self, motif: str, gap_band: str) -> List[str]:
        if motif == "evidence_to_deliverable" and gap_band == "low":
            return [
                "increase_business_trigger_and_stakeholder_context",
                "add_second_reference_or_manager_note_without_new_file_type",
                "require_confirmed_vs_unresolved_issue_separation",
                "add_evidence_sufficiency_or_materiality_judgment",
                "make_deliverable_reviewer_facing_instead_of_template_like",
            ]
        if motif == "cross_check_validation":
            return [
                "preserve_cross_evidence_mismatch_checks",
                "increase realism only if verifier and rubric coverage remain stable",
            ]
        if motif == "fan_in_reconciliation":
            return [
                "extract reusable high-gap reconciliation pattern",
                "avoid over-tuning before low-gap motif reform",
            ]
        if motif == "policy_application":
            return [
                "preserve policy-visible citations",
                "add clearer judgment criteria without hidden policy truth",
            ]
        return []

    def _interpretation(self, motif: str, gap_band: str, strong_score: float, weak_score: float, gap: float) -> str:
        if motif == "evidence_to_deliverable" and gap_band == "low":
            return (
                "Both models scored similarly, so the task appears runnable but under-challenging. "
                "This is the strongest evidence that production-ready does not equal high training value."
            )
        if motif == "fan_in_reconciliation" and gap_band == "high":
            return (
                "The strong model substantially outperformed the weak model, suggesting the motif creates productive "
                "complexity through reconciliation and multi-source synthesis rather than obvious tool failure."
            )
        return (
            f"Observed gap={gap:.3f} with strong_score={strong_score:.3f} and weak_score={weak_score:.3f}; "
            f"treat as {gap_band} diagnostic separation evidence."
        )

    def _motif_summaries(
        self,
        cases: List[GeneratedTaskGapAutopsyCase],
        gap_comparison: Dict[str, Any],
        quality_matrix: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "gap_distribution": self._band_counts(cases),
            "generated_vs_gdpval_gap_bands": {
                "gdpval": gap_comparison.get("gdpval_gap_bands"),
                "generated": gap_comparison.get("generated_gap_bands"),
            },
            "quality_matrix_interpretation": quality_matrix.get("interpretation"),
            "reform_hypothesis": {
                "target_motif": "evidence_to_deliverable",
                "hypothesis": (
                    "Adding realistic evidence ecology, reviewer-facing deliverable constraints, and productive "
                    "judgment requirements should raise model gap or workflow realism without increasing tool friction."
                ),
            },
            "reuse_pattern": {
                "source_motif": "fan_in_reconciliation",
                "pattern": "multi-source numeric reconciliation plus exception explanation appears to create high-gap productive complexity.",
            },
        }

    def _gap_band(self, gap: float) -> str:
        if gap >= 0.5:
            return "high"
        if gap >= 0.15:
            return "medium"
        return "low"

    def _band_counts(self, cases: List[GeneratedTaskGapAutopsyCase]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for case in cases:
            counts[case.gap_band] = counts.get(case.gap_band, 0) + 1
        return counts

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
