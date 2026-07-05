from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_b_eval_feedback_analyzer import PipelineBEvalFeedbackReport
from task_generator.v3_rw_task_eval_summarizer import RwTaskEvalSummaryReport
from task_generator.v3_source_schema import load_json_file


EvaluationStatus = Literal[
    "not_enough_data",
    "diagnostic_only",
    "weak_signal",
    "comparable_signal",
]
EligibilityStatus = Literal[
    "not_ready_for_model_separation",
    "ready_for_diagnostic_comparison",
]
Recommendation = Literal[
    "collect_more_evidence",
    "improve_task_readiness_first",
    "safe_to_expand_comparison_later",
]


class ModelSeparationProfileRequest(BaseModel):
    eval_summary_report_paths: List[str] = Field(default_factory=list)
    eval_summary_dir: Optional[str] = None
    eval_feedback_report_path: Optional[str] = None
    task_verifier_report_path: Optional[str] = None
    global_validity_report_path: Optional[str] = None
    output_dir: str


class ModelEvalEvidenceRecord(BaseModel):
    case_id: str = "unknown"
    evidence_use: str = "unknown"
    evaluated_model_name: str = ""
    grader_model: str = ""
    evaluation_mode: Optional[str] = None
    run_status: str = "unknown"
    summary_status: str = "blocked"
    average_score_ratio: Optional[float] = None
    sample_count: int = 0
    successful_sample_count: int = 0
    grade_artifact_present: bool = False
    usable_for_model_separation: bool = False
    warning_reason_codes: List[str] = Field(default_factory=list)
    source_report_path: str


class ModelScoreSummary(BaseModel):
    weak_model_mean: Optional[float] = None
    medium_model_mean: Optional[float] = None
    strong_model_mean: Optional[float] = None
    score_gap: Optional[float] = None
    retry_variance: Optional[float] = None


class ModelSeparationDiagnostics(BaseModel):
    input_summary_count: int = 0
    usable_summary_count: int = 0
    mixed_case_input: bool = False
    mixed_case_count: int = 0
    verifier_blocking_present: bool = False
    global_validity_present: bool = False
    eval_feedback_present: bool = False
    candidate_quality_summary_count: int = 0
    draft_observation_summary_count: int = 0
    reason_notes: List[str] = Field(default_factory=list)
    artifact_read_errors: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ModelSeparationProfile(BaseModel):
    model_separation_version: str = "v3.model_separation_profile.1"
    request: ModelSeparationProfileRequest
    task_id: Optional[str] = None
    case_id: str = "unknown"
    linked_batch_case_id: Optional[str] = None
    linked_blueprint_id: Optional[str] = None
    evaluation_status: EvaluationStatus = "not_enough_data"
    eligibility_status: EligibilityStatus = "not_ready_for_model_separation"
    models: List[ModelEvalEvidenceRecord] = Field(default_factory=list)
    score_summary: ModelScoreSummary = Field(default_factory=ModelScoreSummary)
    discriminative_rubric_items: List[str] = Field(default_factory=list)
    format_noise_rubric_items: List[str] = Field(default_factory=list)
    common_failure_modes: List[str] = Field(default_factory=list)
    recommendation: Recommendation = "collect_more_evidence"
    diagnostics: ModelSeparationDiagnostics
    notes: List[str] = Field(default_factory=list)


class ModelSeparationProfileBuilder:
    """Build a conservative, evidence-gated model separation profile from existing reports."""

    FORMAT_FAILURE_HINTS = {
        "formatting",
        "format",
        "wording",
        "presentation",
        "surface_form",
        "style",
    }

    def build(
        self,
        eval_summary_report_paths: List[str | Path],
        output_dir: str | Path,
        eval_summary_dir: str | Path | None = None,
        eval_feedback_report_path: str | Path | None = None,
        task_verifier_report_path: str | Path | None = None,
        global_validity_report_path: str | Path | None = None,
    ) -> ModelSeparationProfile:
        collected_summary_paths = self._collect_summary_paths(eval_summary_report_paths, eval_summary_dir)
        request = ModelSeparationProfileRequest(
            eval_summary_report_paths=[str(path) for path in collected_summary_paths],
            eval_summary_dir=str(eval_summary_dir) if eval_summary_dir else None,
            eval_feedback_report_path=str(eval_feedback_report_path) if eval_feedback_report_path else None,
            task_verifier_report_path=str(task_verifier_report_path) if task_verifier_report_path else None,
            global_validity_report_path=str(global_validity_report_path) if global_validity_report_path else None,
            output_dir=str(output_dir),
        )

        diagnostics = ModelSeparationDiagnostics(
            input_summary_count=len(collected_summary_paths),
        )
        summaries = self._load_summaries(collected_summary_paths, diagnostics)
        primary_case_id, primary_summaries, mixed_case_count = self._primary_case_group(summaries)
        diagnostics.mixed_case_count = mixed_case_count
        diagnostics.mixed_case_input = mixed_case_count > 0
        if diagnostics.mixed_case_input:
            diagnostics.reason_notes.append("mixed_case_input")

        eval_feedback = self._load_eval_feedback(eval_feedback_report_path, diagnostics)
        verifier_report = self._load_optional_json(task_verifier_report_path, diagnostics, "task_verifier")
        global_validity_report = self._load_optional_json(
            global_validity_report_path,
            diagnostics,
            "global_validity",
        )
        linked_batch_case_id = self._linked_batch_case_id(global_validity_report)
        linked_blueprint_id = self._linked_blueprint_id(verifier_report, global_validity_report)

        evidence_records = [self._to_evidence_record(summary, source_path) for summary, source_path in primary_summaries]
        diagnostics.candidate_quality_summary_count = sum(
            1 for record in evidence_records if record.evidence_use == "candidate_quality_evidence"
        )
        diagnostics.draft_observation_summary_count = sum(
            1 for record in evidence_records if record.evidence_use == "draft_quality_observation"
        )
        diagnostics.usable_summary_count = sum(
            1 for record in evidence_records if record.usable_for_model_separation
        )

        eligibility_status, eligibility_notes = self._eligibility(
            evidence_records=evidence_records,
            verifier_report=verifier_report,
            global_validity_report=global_validity_report,
        )
        diagnostics.reason_notes.extend(note for note in eligibility_notes if note not in diagnostics.reason_notes)

        evaluation_status = self._evaluation_status(
            evidence_records=evidence_records,
            eligibility_status=eligibility_status,
        )
        score_summary = self._score_summary(primary_summaries)
        task_id = self._task_id([summary for summary, _ in primary_summaries])
        discriminative_items = self._discriminative_items(eval_feedback)
        format_noise_items = self._format_noise_items(eval_feedback)
        common_failure_modes = self._common_failure_modes(evidence_records, eval_feedback)
        recommendation = self._recommendation(
            eligibility_status=eligibility_status,
            evaluation_status=evaluation_status,
            diagnostics=diagnostics,
        )
        diagnostics.notes.extend(
            [
                "ModelSeparationProfile V1 is report-only and evidence-gated.",
                "Draft inspection evidence is preserved but not treated as formal model separation proof.",
            ]
        )

        report = ModelSeparationProfile(
            request=request,
            task_id=task_id,
            case_id=primary_case_id,
            linked_batch_case_id=linked_batch_case_id,
            linked_blueprint_id=linked_blueprint_id,
            evaluation_status=evaluation_status,
            eligibility_status=eligibility_status,
            models=evidence_records,
            score_summary=score_summary,
            discriminative_rubric_items=discriminative_items,
            format_noise_rubric_items=format_noise_items,
            common_failure_modes=common_failure_modes,
            recommendation=recommendation,
            diagnostics=diagnostics,
            notes=[
                "This profile does not run new evaluations and does not change quality truth, registry state, or promotion state.",
                "V1 should default to conservative outputs such as not_enough_data or diagnostic_only unless evidence is unusually complete.",
            ],
        )
        self.write_report(report, Path(output_dir) / "model_separation_profile.json")
        return report

    def write_report(self, report: ModelSeparationProfile, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _collect_summary_paths(
        self,
        explicit_paths: List[str | Path],
        summary_dir: str | Path | None,
    ) -> List[Path]:
        seen: set[Path] = set()
        ordered: List[Path] = []
        for value in explicit_paths:
            path = Path(value)
            if path not in seen:
                seen.add(path)
                ordered.append(path)
        if summary_dir:
            for path in sorted(Path(summary_dir).rglob("pipeline_b_eval_summary_report.json")):
                if path not in seen:
                    seen.add(path)
                    ordered.append(path)
        return ordered

    def _load_summaries(
        self,
        paths: List[Path],
        diagnostics: ModelSeparationDiagnostics,
    ) -> List[Tuple[RwTaskEvalSummaryReport, str]]:
        reports: List[Tuple[RwTaskEvalSummaryReport, str]] = []
        for path in paths:
            try:
                reports.append((RwTaskEvalSummaryReport.model_validate(load_json_file(str(path))), str(path)))
            except Exception:
                diagnostics.artifact_read_errors.append(f"eval_summary_unreadable:{path}")
        return reports

    def _load_eval_feedback(
        self,
        eval_feedback_report_path: str | Path | None,
        diagnostics: ModelSeparationDiagnostics,
    ) -> Optional[PipelineBEvalFeedbackReport]:
        if not eval_feedback_report_path:
            return None
        path = Path(eval_feedback_report_path)
        if not path.exists():
            diagnostics.artifact_read_errors.append(f"eval_feedback_missing:{path}")
            return None
        try:
            report = PipelineBEvalFeedbackReport.model_validate(load_json_file(str(path)))
        except Exception:
            diagnostics.artifact_read_errors.append(f"eval_feedback_unreadable:{path}")
            return None
        diagnostics.eval_feedback_present = True
        return report

    def _load_optional_json(
        self,
        report_path: str | Path | None,
        diagnostics: ModelSeparationDiagnostics,
        label: str,
    ) -> Optional[Dict[str, Any]]:
        if not report_path:
            return None
        path = Path(report_path)
        if not path.exists():
            diagnostics.artifact_read_errors.append(f"{label}_missing:{path}")
            return None
        try:
            payload = load_json_file(str(path))
        except Exception:
            diagnostics.artifact_read_errors.append(f"{label}_unreadable:{path}")
            return None
        if label == "global_validity":
            diagnostics.global_validity_present = True
        return payload

    def _primary_case_group(
        self,
        summaries: List[Tuple[RwTaskEvalSummaryReport, str]],
    ) -> Tuple[str, List[Tuple[RwTaskEvalSummaryReport, str]], int]:
        if not summaries:
            return "unknown", [], 0
        grouped: Dict[str, List[Tuple[RwTaskEvalSummaryReport, str]]] = {}
        for summary, source_path in summaries:
            grouped.setdefault(summary.case_id or "unknown", []).append((summary, source_path))
        ordered = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
        primary_case_id, primary_group = ordered[0]
        mixed_case_count = sum(len(group) for case_id, group in ordered[1:] if case_id != primary_case_id)
        return primary_case_id, primary_group, mixed_case_count

    def _to_evidence_record(
        self,
        summary: RwTaskEvalSummaryReport,
        source_path: str,
    ) -> ModelEvalEvidenceRecord:
        return ModelEvalEvidenceRecord(
            case_id=summary.case_id,
            evidence_use=summary.evidence_use,
            evaluated_model_name=summary.evaluated_model_name,
            grader_model=summary.grader_model,
            evaluation_mode=summary.evaluation_mode,
            run_status=summary.run_status,
            summary_status=summary.summary_status,
            average_score_ratio=summary.average_score_ratio,
            sample_count=summary.sample_count,
            successful_sample_count=summary.successful_sample_count,
            grade_artifact_present=summary.grade_artifact_present,
            usable_for_model_separation=summary.usable_for_model_separation,
            warning_reason_codes=list(summary.warning_reason_codes),
            source_report_path=source_path,
        )

    def _eligibility(
        self,
        evidence_records: List[ModelEvalEvidenceRecord],
        verifier_report: Optional[Dict[str, Any]],
        global_validity_report: Optional[Dict[str, Any]],
    ) -> Tuple[EligibilityStatus, List[str]]:
        notes: List[str] = []
        summarized_records = [record for record in evidence_records if record.summary_status == "summarized"]
        usable_records = [record for record in evidence_records if record.usable_for_model_separation]
        if not summarized_records:
            notes.append("insufficient_eval_summary_count")
        if evidence_records and all(record.evidence_use == "toolchain_smoke_only" for record in evidence_records):
            notes.append("only_toolchain_smoke_evidence")
        if len(usable_records) < 2:
            notes.append("insufficient_eval_summary_count")
        if any("draft_only_case" in record.warning_reason_codes for record in evidence_records):
            notes.append("revise_only_package")

        has_non_failed = any(record.usable_for_model_separation for record in evidence_records)
        if not has_non_failed:
            notes.append("only_toolchain_smoke_evidence")

        verifier_blocking = False
        if verifier_report is not None:
            verifier_blocking = int((verifier_report.get("diagnostics") or {}).get("blocking_count") or 0) > 0
            if verifier_blocking:
                notes.append("verifier_blocking_present")

        real_worldness_score = None
        overall_difficulty = None
        if global_validity_report is not None:
            real_worldness_score = (
                (global_validity_report.get("real_worldness") or {}).get("real_worldness_score")
            )
            overall_difficulty = (
                (global_validity_report.get("difficulty_profile") or {}).get("overall_difficulty")
            )
            if real_worldness_score is None or float(real_worldness_score) < 0.7:
                notes.append("real_worldness_below_threshold")
            if overall_difficulty is None:
                notes.append("difficulty_profile_missing")

        ready = (
            bool(usable_records)
            and any(record.evidence_use != "toolchain_smoke_only" for record in usable_records)
            and has_non_failed
            and not verifier_blocking
            and (
                global_validity_report is None
                or (
                    real_worldness_score is not None
                    and float(real_worldness_score) >= 0.7
                    and overall_difficulty is not None
                )
            )
        )
        return (
            "ready_for_diagnostic_comparison" if ready else "not_ready_for_model_separation",
            sorted(set(notes)),
        )

    def _linked_batch_case_id(self, global_validity_report: Optional[Dict[str, Any]]) -> Optional[str]:
        if global_validity_report is None:
            return None
        value = global_validity_report.get("case_id")
        return str(value) if value else None

    def _linked_blueprint_id(
        self,
        verifier_report: Optional[Dict[str, Any]],
        global_validity_report: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if verifier_report is not None and verifier_report.get("blueprint_id"):
            return str(verifier_report.get("blueprint_id"))
        if global_validity_report is not None and global_validity_report.get("blueprint_id"):
            return str(global_validity_report.get("blueprint_id"))
        return None

    def _evaluation_status(
        self,
        evidence_records: List[ModelEvalEvidenceRecord],
        eligibility_status: EligibilityStatus,
    ) -> EvaluationStatus:
        usable = [
            record
            for record in evidence_records
            if record.usable_for_model_separation
        ]
        if len(usable) < 2:
            return "not_enough_data"
        if all(record.evidence_use != "candidate_quality_evidence" for record in usable):
            return "not_enough_data"
        if eligibility_status == "not_ready_for_model_separation":
            return "diagnostic_only"
        model_scores = [record.average_score_ratio for record in usable if record.average_score_ratio is not None]
        if len(model_scores) >= 2 and (max(model_scores) - min(model_scores)) >= 0.1:
            return "weak_signal"
        return "diagnostic_only"

    def _score_summary(
        self,
        summaries: List[Tuple[RwTaskEvalSummaryReport, str]],
    ) -> ModelScoreSummary:
        grouped: Dict[str, List[float]] = {}
        for summary, _ in summaries:
            if not summary.usable_for_model_separation:
                continue
            model_name = summary.evaluated_model_name or summary.grader_model
            if not model_name or summary.average_score_ratio is None:
                continue
            grouped.setdefault(model_name, []).append(summary.average_score_ratio)
        means = {name: mean(values) for name, values in grouped.items() if values}
        if len(means) < 3:
            return ModelScoreSummary(
                retry_variance=self._retry_variance(grouped),
            )
        ranked = sorted(means.items(), key=lambda item: item[1])
        weak_name, weak_mean = ranked[0]
        medium_name, medium_mean = ranked[len(ranked) // 2]
        strong_name, strong_mean = ranked[-1]
        return ModelScoreSummary(
            weak_model_mean=weak_mean,
            medium_model_mean=medium_mean,
            strong_model_mean=strong_mean,
            score_gap=strong_mean - weak_mean,
            retry_variance=self._retry_variance(grouped),
        )

    def _retry_variance(self, grouped_scores: Dict[str, List[float]]) -> Optional[float]:
        variances: List[float] = []
        for values in grouped_scores.values():
            if len(values) < 2:
                continue
            avg = mean(values)
            variances.append(sum((value - avg) ** 2 for value in values) / len(values))
        if not variances:
            return None
        return mean(variances)

    def _task_id(self, summaries: List[RwTaskEvalSummaryReport]) -> Optional[str]:
        task_ids: List[str] = []
        for summary in summaries:
            for sample in summary.samples:
                if sample.task_id and sample.task_id != "unknown":
                    task_ids.append(sample.task_id)
        if not task_ids:
            return None
        counts = Counter(task_ids)
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def _discriminative_items(
        self,
        eval_feedback: Optional[PipelineBEvalFeedbackReport],
    ) -> List[str]:
        if eval_feedback is None:
            return []
        ranked = sorted(
            eval_feedback.low_scoring_criteria,
            key=lambda item: (item.score_ratio, item.criterion_text),
        )
        return [item.criterion_text for item in ranked[:3]]

    def _format_noise_items(
        self,
        eval_feedback: Optional[PipelineBEvalFeedbackReport],
    ) -> List[str]:
        if eval_feedback is None:
            return []
        items: List[str] = []
        for failure in eval_feedback.likely_failure_sources:
            source = str(failure.get("failure_source") or "")
            if any(token in source for token in self.FORMAT_FAILURE_HINTS):
                example = str(failure.get("example_criterion") or source)
                items.append(example)
        return items[:3]

    def _common_failure_modes(
        self,
        evidence_records: List[ModelEvalEvidenceRecord],
        eval_feedback: Optional[PipelineBEvalFeedbackReport],
    ) -> List[str]:
        counts: Counter[str] = Counter()
        for record in evidence_records:
            counts.update(record.warning_reason_codes)
        if eval_feedback is not None:
            for item in eval_feedback.likely_failure_sources:
                source = str(item.get("failure_source") or "")
                if source:
                    counts[source] += int(item.get("count") or 1)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [name for name, _ in ordered[:6]]

    def _recommendation(
        self,
        eligibility_status: EligibilityStatus,
        evaluation_status: EvaluationStatus,
        diagnostics: ModelSeparationDiagnostics,
    ) -> Recommendation:
        if eligibility_status == "not_ready_for_model_separation":
            if any(
                note in diagnostics.reason_notes
                for note in {"verifier_blocking_present", "real_worldness_below_threshold", "difficulty_profile_missing"}
            ):
                return "improve_task_readiness_first"
            return "collect_more_evidence"
        if evaluation_status in {"not_enough_data", "diagnostic_only"}:
            return "collect_more_evidence"
        return "safe_to_expand_comparison_later"
