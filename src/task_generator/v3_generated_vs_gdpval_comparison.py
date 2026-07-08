from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class GeneratedVsGDPValComparisonRequest(BaseModel):
    observational_profiles_path: str
    output_dir: str


class DistributionDelta(BaseModel):
    dimension: str
    gdpval_counts: Dict[str, int] = Field(default_factory=dict)
    generated_counts: Dict[str, int] = Field(default_factory=dict)
    comparison_note: str = ""


class GeneratedVsGDPValComparisonReport(BaseModel):
    report_version: str = "v3.generated_vs_gdpval_comparison.1"
    created_at: str
    request: GeneratedVsGDPValComparisonRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    gdpval_profile_count: int
    generated_profile_count: int
    gdpval_clean_eval_count: int
    generated_clean_eval_count: int
    comparison_readiness: str
    distribution_deltas: List[DistributionDelta] = Field(default_factory=list)
    generated_eval_gaps: List[str] = Field(default_factory=list)
    recommended_next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GeneratedTaskImprovementRecommendations(BaseModel):
    report_version: str = "v3.generated_task_improvement_recommendations.1"
    created_at: str
    diagnostic_only: bool = True
    recommendations: List[str] = Field(default_factory=list)
    blocked_claims: List[str] = Field(default_factory=list)


class GeneratedVsGDPValComparisonBuilder:
    def build(self, request: GeneratedVsGDPValComparisonRequest) -> GeneratedVsGDPValComparisonReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        profiles = self._read_profiles(Path(request.observational_profiles_path))
        gdpval = [profile for profile in profiles if profile.get("source") == "openai/gdpval"]
        generated = [profile for profile in profiles if profile.get("source") == "taskgenerator/phase13_reviewed_release"]
        gdpval_clean = [profile for profile in gdpval if profile.get("evaluation_status") == "clean_paired_eval"]
        generated_clean = [profile for profile in generated if profile.get("evaluation_status") == "clean_paired_eval"]

        deltas = [
            self._delta("deliverable_type", gdpval, generated),
            self._delta("gap_band", gdpval, generated),
            self._nested_delta("productive_complexity", gdpval, generated),
            self._nested_delta("frictional_complexity", gdpval, generated),
            self._nested_delta("model_separation_quality", gdpval, generated),
            self._nested_delta("format_noise_risk", gdpval, generated),
            self._nested_delta("tool_failure_risk", gdpval, generated),
        ]
        generated_eval_gaps = self._generated_eval_gaps(generated)
        report = GeneratedVsGDPValComparisonReport(
            created_at=self._now(),
            request=request,
            gdpval_profile_count=len(gdpval),
            generated_profile_count=len(generated),
            gdpval_clean_eval_count=len(gdpval_clean),
            generated_clean_eval_count=len(generated_clean),
            comparison_readiness="structure_only_pending_generated_eval" if not generated_clean else "clean_pair_comparison_available",
            distribution_deltas=deltas,
            generated_eval_gaps=generated_eval_gaps,
            recommended_next_actions=self._next_actions(generated_clean_count=len(generated_clean), generated_eval_gaps=generated_eval_gaps),
            notes=[
                "This comparison is report-only and diagnostic.",
                "Generated TaskGenerator tasks currently lack clean paired eval evidence, so model-gap claims are blocked.",
                "Use this report to prioritize generated-task rw-task comparison runs, not to claim benchmark-grade separation.",
            ],
        )
        self._write_json(output_dir / "generated_vs_gdpval_similarity_report.json", report.model_dump(mode="json"))
        self._write_json(output_dir / "generated_vs_gdpval_gap_report.json", self._gap_report(report, gdpval_clean, generated_clean))
        self._write_json(output_dir / "generated_vs_gdpval_quality_matrix.json", self._quality_matrix(gdpval, generated, deltas))
        self._write_json(
            output_dir / "generated_task_improvement_recommendations.json",
            GeneratedTaskImprovementRecommendations(
                created_at=self._now(),
                recommendations=report.recommended_next_actions,
                blocked_claims=[
                    "Do not compare generated model separation against GDPVal until generated_clean_eval_count > 0.",
                    "Do not emit GoodTaskScore or weighted quality rankings from this first-pass comparison.",
                ],
            ).model_dump(mode="json"),
        )
        return report

    def _read_profiles(self, path: Path) -> List[Dict[str, Any]]:
        values: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                values.append(json.loads(line))
        return values

    def _delta(self, dimension: str, gdpval: List[Dict[str, Any]], generated: List[Dict[str, Any]]) -> DistributionDelta:
        gdpval_counts = Counter(str(profile.get(dimension) or "unknown") for profile in gdpval)
        generated_counts = Counter(str(profile.get(dimension) or "unknown") for profile in generated)
        return DistributionDelta(
            dimension=dimension,
            gdpval_counts=dict(gdpval_counts),
            generated_counts=dict(generated_counts),
            comparison_note=self._comparison_note(dimension, gdpval_counts, generated_counts),
        )

    def _nested_delta(self, dimension: str, gdpval: List[Dict[str, Any]], generated: List[Dict[str, Any]]) -> DistributionDelta:
        gdpval_counts = Counter(str((profile.get(dimension) or {}).get("value") or "unknown") for profile in gdpval)
        generated_counts = Counter(str((profile.get(dimension) or {}).get("value") or "unknown") for profile in generated)
        return DistributionDelta(
            dimension=dimension,
            gdpval_counts=dict(gdpval_counts),
            generated_counts=dict(generated_counts),
            comparison_note=self._comparison_note(dimension, gdpval_counts, generated_counts),
        )

    def _comparison_note(self, dimension: str, gdpval_counts: Counter, generated_counts: Counter) -> str:
        if not generated_counts:
            return "No generated profiles available."
        if "not_observed" in generated_counts or "unknown_until_eval" in generated_counts:
            return f"Generated {dimension} is not fully comparable until executed eval evidence exists."
        return f"Compare {dimension} distribution after generated-task clean eval."

    def _generated_eval_gaps(self, generated: List[Dict[str, Any]]) -> List[str]:
        gaps: List[str] = []
        for profile in generated:
            if profile.get("evaluation_status") != "clean_paired_eval":
                gaps.append(f"{profile.get('task_id')}: {profile.get('evaluation_status')}")
        return gaps

    def _next_actions(self, *, generated_clean_count: int, generated_eval_gaps: List[str]) -> List[str]:
        actions = []
        if generated_clean_count == 0:
            actions.append("Run the 4 TaskGenerator comparison candidates through the rw-task diagnostic path one at a time.")
            actions.append("After each generated-task run, rebuild GoodTaskProfiler-Observational and this comparison report.")
        if generated_eval_gaps:
            actions.append("Keep generated-vs-GDPVal claims structure-only until generated tasks have clean paired scores.")
        actions.append("Use GDPVal next eval queue to raise GDPVal clean paired comparisons from 4 toward 8.")
        return actions

    def _gap_report(
        self,
        report: GeneratedVsGDPValComparisonReport,
        gdpval_clean: List[Dict[str, Any]],
        generated_clean: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "report_version": "v3.generated_vs_gdpval_gap_report.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "not_benchmark_grade": True,
            "gdpval_clean_eval_count": len(gdpval_clean),
            "generated_clean_eval_count": len(generated_clean),
            "gdpval_gap_bands": dict(Counter(str(profile.get("gap_band") or "unknown") for profile in gdpval_clean)),
            "generated_gap_bands": dict(Counter(str(profile.get("gap_band") or "unknown") for profile in generated_clean)),
            "comparison_readiness": report.comparison_readiness,
            "blocked_reason": None if generated_clean else "generated_tasks_have_no_clean_paired_eval_yet",
        }

    def _quality_matrix(
        self,
        gdpval: List[Dict[str, Any]],
        generated: List[Dict[str, Any]],
        deltas: List[DistributionDelta],
    ) -> Dict[str, Any]:
        return {
            "report_version": "v3.generated_vs_gdpval_quality_matrix.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "not_benchmark_grade": True,
            "gdpval_profile_count": len(gdpval),
            "generated_profile_count": len(generated),
            "dimensions": [delta.model_dump(mode="json") for delta in deltas],
            "interpretation": "Generated profiles are structurally comparable but model-separation and stability dimensions remain pending executed eval.",
        }

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
