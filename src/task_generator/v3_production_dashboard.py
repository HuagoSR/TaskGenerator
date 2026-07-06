from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class ProductionDashboardRequest(BaseModel):
    production_batch_manifest_path: str
    production_batch_diversity_report_path: str
    production_qa_gate_report_path: str
    release_manifest_path: Optional[str] = None
    comparison_batch_manifest_paths: List[str] = Field(default_factory=list)
    output_dir: str


class ProductionDashboardSummary(BaseModel):
    case_count: int = 0
    candidate_ready_count: int = 0
    candidate_ready_rate: float = 0.0
    production_ready_count: int = 0
    production_ready_rate: float = 0.0
    review_required_count: int = 0
    blocked_count: int = 0
    verifier_pass_count: int = 0
    verifier_pass_rate: float = 0.0
    export_compatible_count: int = 0
    export_compatible_rate: float = 0.0
    unique_motif_count: int = 0
    unique_deliverable_signature_count: int = 0
    duplicate_subgraph_count: int = 0
    release_task_count: int = 0
    release_mode: Optional[str] = None


class ScoreDistribution(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    low_count: int = 0
    medium_count: int = 0
    high_count: int = 0


class ProductionDashboardReport(BaseModel):
    production_dashboard_version: str = "v3.production_dashboard.1"
    request: ProductionDashboardRequest
    production_batch_id: str
    summary: ProductionDashboardSummary
    motif_distribution: Dict[str, int] = Field(default_factory=dict)
    workflow_context_fit_distribution: Dict[str, int] = Field(default_factory=dict)
    qa_decision_distribution: Dict[str, int] = Field(default_factory=dict)
    real_worldness_distribution: ScoreDistribution = Field(default_factory=ScoreDistribution)
    difficulty_distribution: ScoreDistribution = Field(default_factory=ScoreDistribution)
    known_limitations: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ProductionBatchComparisonReport(BaseModel):
    production_batch_comparison_version: str = "v3.production_batch_comparison.1"
    current_batch_id: str
    baseline_batch_id: Optional[str] = None
    deltas: Dict[str, Optional[float]] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class ReleaseReadinessReport(BaseModel):
    release_readiness_version: str = "v3.release_readiness.1"
    production_batch_id: str
    release_id: Optional[str] = None
    readiness_status: str
    blocking_reasons: List[str] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ProductionDashboardBuilder:
    def build(
        self,
        production_batch_manifest_path: str | Path,
        production_batch_diversity_report_path: str | Path,
        production_qa_gate_report_path: str | Path,
        output_dir: str | Path,
        release_manifest_path: str | Path | None = None,
        comparison_batch_manifest_paths: Optional[List[str | Path]] = None,
    ) -> Dict[str, Any]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = ProductionDashboardRequest(
            production_batch_manifest_path=str(production_batch_manifest_path),
            production_batch_diversity_report_path=str(production_batch_diversity_report_path),
            production_qa_gate_report_path=str(production_qa_gate_report_path),
            release_manifest_path=str(release_manifest_path) if release_manifest_path else None,
            comparison_batch_manifest_paths=[
                str(path) for path in (comparison_batch_manifest_paths or [])
            ],
            output_dir=str(output_path),
        )
        manifest = load_json_file(str(production_batch_manifest_path))
        diversity = load_json_file(str(production_batch_diversity_report_path))
        qa = load_json_file(str(production_qa_gate_report_path))
        release_manifest = self._load_optional(release_manifest_path)
        batch_id = str(((manifest.get("request") or {}).get("production_batch_id")) or "unknown_batch")
        cases = [case for case in (manifest.get("cases") or []) if isinstance(case, dict)]
        decisions = [item for item in (qa.get("decisions") or []) if isinstance(item, dict)]

        case_count = len(cases)
        candidate_ready_count = sum(1 for case in cases if case.get("task_state") == "candidate_ready")
        production_ready_count = sum(
            1 for item in decisions if item.get("decision") == "approved_production_candidate"
        )
        review_required_count = sum(1 for item in decisions if item.get("decision") == "review_required")
        blocked_count = sum(1 for item in decisions if item.get("decision") == "blocked")
        verifier_pass_count = sum(1 for case in cases if case.get("verifier_status") == "pass")
        export_compatible_count = sum(
            1 for case in cases if case.get("validation_status") == "candidate_ready_compatible"
        )
        real_worldness_values = [
            float(case.get("real_worldness_score"))
            for case in cases
            if isinstance(case.get("real_worldness_score"), (int, float))
        ]
        difficulty_values = [
            float(case.get("difficulty_overall"))
            for case in cases
            if isinstance(case.get("difficulty_overall"), (int, float))
        ]
        summary = ProductionDashboardSummary(
            case_count=case_count,
            candidate_ready_count=candidate_ready_count,
            candidate_ready_rate=self._rate(candidate_ready_count, case_count),
            production_ready_count=production_ready_count,
            production_ready_rate=self._rate(production_ready_count, case_count),
            review_required_count=review_required_count,
            blocked_count=blocked_count,
            verifier_pass_count=verifier_pass_count,
            verifier_pass_rate=self._rate(verifier_pass_count, case_count),
            export_compatible_count=export_compatible_count,
            export_compatible_rate=self._rate(export_compatible_count, case_count),
            unique_motif_count=int((diversity.get("summary") or {}).get("unique_motif_count") or 0),
            unique_deliverable_signature_count=int(
                (diversity.get("summary") or {}).get("unique_deliverable_signature_count") or 0
            ),
            duplicate_subgraph_count=int((diversity.get("summary") or {}).get("duplicate_subgraph_count") or 0),
            release_task_count=int((release_manifest or {}).get("task_count") or 0),
            release_mode=(release_manifest or {}).get("release_mode"),
        )
        dashboard = ProductionDashboardReport(
            request=request,
            production_batch_id=batch_id,
            summary=summary,
            motif_distribution=dict(sorted(Counter(str(case.get("motif") or "unknown") for case in cases).items())),
            workflow_context_fit_distribution=dict(
                sorted(
                    Counter(
                        str(case.get("workflow_context_fit") or "unknown")
                        for case in cases
                    ).items()
                )
            ),
            qa_decision_distribution=dict(
                sorted(Counter(str(item.get("decision") or "unknown") for item in decisions).items())
            ),
            real_worldness_distribution=self._distribution(real_worldness_values),
            difficulty_distribution=self._distribution(difficulty_values),
            known_limitations=self._known_limitations(summary, diversity, release_manifest),
            next_actions=self._next_actions(summary, diversity),
            notes=[
                "Production dashboard V1 aggregates batch manifest, diversity, QA, and optional release state.",
                "This dashboard remains deterministic and report-first.",
            ],
        )
        comparison = self._comparison(
            current_manifest=manifest,
            current_qa=qa,
            baseline_paths=comparison_batch_manifest_paths or [],
        )
        readiness = self._release_readiness(
            batch_id=batch_id,
            summary=summary,
            diversity=diversity,
            release_manifest=release_manifest,
        )
        (output_path / "production_dashboard_report.json").write_text(
            dashboard.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output_path / "production_batch_comparison_report.json").write_text(
            comparison.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output_path / "release_readiness_report.json").write_text(
            readiness.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return {
            "production_dashboard_report": dashboard,
            "production_batch_comparison_report": comparison,
            "release_readiness_report": readiness,
        }

    def _comparison(
        self,
        current_manifest: Dict[str, Any],
        current_qa: Dict[str, Any],
        baseline_paths: List[str | Path],
    ) -> ProductionBatchComparisonReport:
        current_batch_id = str(((current_manifest.get("request") or {}).get("production_batch_id")) or "unknown_batch")
        if not baseline_paths:
            return ProductionBatchComparisonReport(
                current_batch_id=current_batch_id,
                baseline_batch_id=None,
                deltas={},
                notes=["No baseline production batch was provided for comparison."],
            )
        baseline_manifest = self._load_required(baseline_paths[0])
        baseline_batch_id = str(((baseline_manifest.get("request") or {}).get("production_batch_id")) or "baseline")
        current_cases = [case for case in (current_manifest.get("cases") or []) if isinstance(case, dict)]
        baseline_cases = [case for case in (baseline_manifest.get("cases") or []) if isinstance(case, dict)]
        current_case_count = len(current_cases)
        baseline_case_count = len(baseline_cases)
        current_candidate_ready = sum(1 for case in current_cases if case.get("task_state") == "candidate_ready")
        baseline_candidate_ready = sum(1 for case in baseline_cases if case.get("task_state") == "candidate_ready")
        current_verifier = sum(1 for case in current_cases if case.get("verifier_status") == "pass")
        baseline_verifier = sum(1 for case in baseline_cases if case.get("verifier_status") == "pass")
        current_export = sum(
            1 for case in current_cases if case.get("validation_status") == "candidate_ready_compatible"
        )
        baseline_export = sum(
            1 for case in baseline_cases if case.get("validation_status") == "candidate_ready_compatible"
        )
        return ProductionBatchComparisonReport(
            current_batch_id=current_batch_id,
            baseline_batch_id=baseline_batch_id,
            deltas={
                "candidate_ready_rate_delta": round(
                    self._rate(current_candidate_ready, current_case_count)
                    - self._rate(baseline_candidate_ready, baseline_case_count),
                    4,
                ),
                "verifier_pass_rate_delta": round(
                    self._rate(current_verifier, current_case_count)
                    - self._rate(baseline_verifier, baseline_case_count),
                    4,
                ),
                "export_compatible_rate_delta": round(
                    self._rate(current_export, current_case_count)
                    - self._rate(baseline_export, baseline_case_count),
                    4,
                ),
            },
            notes=["Comparison V1 currently uses the first provided baseline batch manifest."],
        )

    def _release_readiness(
        self,
        batch_id: str,
        summary: ProductionDashboardSummary,
        diversity: Dict[str, Any],
        release_manifest: Optional[Dict[str, Any]],
    ) -> ReleaseReadinessReport:
        blocking_reasons: List[str] = []
        review_reasons: List[str] = []
        if summary.production_ready_count == 0:
            blocking_reasons.append("no_production_ready_cases")
        if summary.verifier_pass_rate < 0.95:
            blocking_reasons.append("verifier_pass_rate_below_threshold")
        if summary.export_compatible_rate < 0.95:
            blocking_reasons.append("export_compatible_rate_below_threshold")
        if ((diversity.get("diagnostics") or {}).get("warnings") or []):
            review_reasons.extend(list((diversity.get("diagnostics") or {}).get("warnings") or []))
        if summary.review_required_count > 0:
            review_reasons.append("review_required_cases_present")
        if release_manifest is None:
            review_reasons.append("no_release_manifest")
        readiness_status = "release_ready"
        if blocking_reasons:
            readiness_status = "not_ready_for_release"
        elif review_reasons:
            readiness_status = "internal_review_only"
        return ReleaseReadinessReport(
            production_batch_id=batch_id,
            release_id=(release_manifest or {}).get("release_id"),
            readiness_status=readiness_status,
            blocking_reasons=blocking_reasons,
            review_reasons=review_reasons,
            notes=[
                "Release readiness is a deterministic Phase 13 report and does not mutate task state.",
            ],
        )

    def _known_limitations(
        self,
        summary: ProductionDashboardSummary,
        diversity: Dict[str, Any],
        release_manifest: Optional[Dict[str, Any]],
    ) -> List[str]:
        limitations = [
            "Production dashboard does not turn diagnostic-only validity into formal benchmark-grade evidence.",
        ]
        if summary.production_ready_count == 0:
            limitations.append("No governed production-ready case exists in the current batch.")
        if release_manifest and release_manifest.get("release_mode") == "internal_review_release":
            limitations.append("Current release packaging is internal-review-only rather than production-ready-only.")
        if ((diversity.get("diagnostics") or {}).get("warnings") or []):
            limitations.append("Diversity warnings remain present and should be reviewed before scale-up.")
        return limitations

    def _next_actions(
        self,
        summary: ProductionDashboardSummary,
        diversity: Dict[str, Any],
    ) -> List[str]:
        actions: List[str] = []
        if summary.production_ready_count == 0:
            actions.append("Promote at least one case from review_required to approved production candidate by tightening workflow-context fit and production-validity interpretation.")
        if summary.review_required_count > 0:
            actions.append("Reduce review_required cases by reviewing borderline real-worldness thresholds and workflow-context heuristics.")
        if ((diversity.get("diagnostics") or {}).get("warnings") or []):
            actions.append("Address diversity concentration warnings before expanding the next pilot batch.")
        actions.append("Run a larger production pilot batch once at least one governed production-ready case exists.")
        return actions

    def _distribution(self, values: List[float]) -> ScoreDistribution:
        if not values:
            return ScoreDistribution()
        return ScoreDistribution(
            min=min(values),
            max=max(values),
            mean=round(mean(values), 4),
            low_count=sum(1 for value in values if value < 0.4),
            medium_count=sum(1 for value in values if 0.4 <= value < 0.7),
            high_count=sum(1 for value in values if value >= 0.7),
        )

    def _rate(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _load_optional(self, path_value: str | Path | None) -> Optional[Dict[str, Any]]:
        if not path_value:
            return None
        path = Path(path_value)
        try:
            return load_json_file(str(path))
        except Exception:
            return None

    def _load_required(self, path_value: str | Path) -> Dict[str, Any]:
        return load_json_file(str(Path(path_value)))
