from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_rw_task_eval_runner import RwTaskEvalRunReport
from task_generator.v3_source_schema import load_json_file


EvalSummaryStatus = Literal["blocked", "summarized"]
EvalEvidenceUse = Literal[
    "toolchain_smoke_only",
    "draft_quality_observation",
    "candidate_quality_evidence",
]


class RwTaskEvalSummaryRequest(BaseModel):
    run_report_path: str
    grade_report_path: Optional[str] = None
    grade_dir: Optional[str] = None
    output_dir: str


class RwTaskEvalSampleSummary(BaseModel):
    task_id: str
    success: bool = False
    total_score: Optional[float] = None
    max_possible_score: Optional[float] = None
    score_ratio: Optional[float] = None
    criterion_count: int = 0
    grading_notes: str = ""
    audit_applied: Optional[bool] = None
    audit_skipped_reason: str = ""
    error: Optional[str] = None


class RwTaskEvalSummaryReport(BaseModel):
    summary_version: str = "v3.rw_task_eval_summarizer.1"
    request: RwTaskEvalSummaryRequest
    summary_status: EvalSummaryStatus
    evidence_use: EvalEvidenceUse
    case_id: str = "unknown"
    evaluation_mode: Optional[str] = None
    run_status: str = "unknown"
    toolchain_completed: bool = False
    commands_executed: bool = False
    command_count: int = 0
    command_success_count: int = 0
    grade_report_path: Optional[str] = None
    grader_model: str = ""
    grading_strictness: str = ""
    sample_count: int = 0
    successful_sample_count: int = 0
    average_score_ratio: Optional[float] = None
    samples: List[RwTaskEvalSampleSummary] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RwTaskEvalSummarizer:
    """Summarize rw-task runner and grader outputs without updating quality truth."""

    def summarize(
        self,
        run_report_path: str | Path,
        output_dir: str | Path,
        grade_report_path: str | Path | None = None,
        grade_dir: str | Path | None = None,
    ) -> RwTaskEvalSummaryReport:
        run_path = Path(run_report_path)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        resolved_grade_path = self._resolve_grade_path(grade_report_path, grade_dir)
        request = RwTaskEvalSummaryRequest(
            run_report_path=str(run_path),
            grade_report_path=str(resolved_grade_path) if resolved_grade_path else None,
            grade_dir=str(grade_dir) if grade_dir else None,
            output_dir=str(output_path),
        )

        blocking_reasons: List[str] = []
        run_report: Optional[RwTaskEvalRunReport] = None
        grade_report: Optional[Dict[str, Any]] = None

        if not run_path.exists():
            blocking_reasons.append("run_report_missing")
        else:
            try:
                run_report = RwTaskEvalRunReport.model_validate(load_json_file(str(run_path)))
            except Exception:
                blocking_reasons.append("run_report_unreadable")

        if resolved_grade_path is None:
            blocking_reasons.append("grade_report_missing")
        else:
            try:
                grade_report = load_json_file(str(resolved_grade_path))
            except Exception:
                blocking_reasons.append("grade_report_unreadable")

        samples = self._sample_summaries(grade_report)
        report = RwTaskEvalSummaryReport(
            request=request,
            summary_status="blocked" if blocking_reasons else "summarized",
            evidence_use=self._evidence_use(run_report),
            case_id=run_report.case_id if run_report else "unknown",
            evaluation_mode=run_report.evaluation_mode if run_report else None,
            run_status=run_report.run_status if run_report else "unknown",
            toolchain_completed=bool(run_report and run_report.run_status == "completed"),
            commands_executed=bool(run_report and run_report.commands_executed),
            command_count=run_report.command_count if run_report else 0,
            command_success_count=self._command_success_count(run_report),
            grade_report_path=str(resolved_grade_path) if resolved_grade_path else None,
            grader_model=str((grade_report or {}).get("model") or ""),
            grading_strictness=str((grade_report or {}).get("grading_strictness") or ""),
            sample_count=len(samples),
            successful_sample_count=sum(1 for sample in samples if sample.success),
            average_score_ratio=self._average_score_ratio(samples),
            samples=samples,
            blocking_reasons=sorted(set(blocking_reasons)),
            warning_reason_codes=sorted(set(run_report.warnings if run_report else [])),
            notes=self._notes(run_report),
        )
        self.write_report(report, output_path / "pipeline_b_eval_summary_report.json")
        return report

    def write_report(self, report: RwTaskEvalSummaryReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _resolve_grade_path(
        self,
        grade_report_path: str | Path | None,
        grade_dir: str | Path | None,
    ) -> Optional[Path]:
        if grade_report_path:
            return Path(grade_report_path)
        if not grade_dir:
            return None
        grade_path = Path(grade_dir)
        if not grade_path.exists():
            return None
        candidates = sorted(
            grade_path.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _sample_summaries(self, grade_report: Optional[Dict[str, Any]]) -> List[RwTaskEvalSampleSummary]:
        if not grade_report:
            return []
        samples: List[RwTaskEvalSampleSummary] = []
        for sample in grade_report.get("samples") or []:
            grading = sample.get("grading") or {}
            total_score = self._float_or_none(grading.get("total_score"))
            max_score = self._float_or_none(grading.get("max_possible_score"))
            samples.append(
                RwTaskEvalSampleSummary(
                    task_id=str(sample.get("task_id") or "unknown"),
                    success=bool(sample.get("success")),
                    total_score=total_score,
                    max_possible_score=max_score,
                    score_ratio=self._ratio(total_score, max_score),
                    criterion_count=len(grading.get("per_criterion") or []),
                    grading_notes=str(grading.get("grading_notes") or ""),
                    audit_applied=grading.get("audit_applied"),
                    audit_skipped_reason=str(grading.get("audit_skipped_reason") or ""),
                    error=sample.get("error"),
                )
            )
        return samples

    def _evidence_use(self, run_report: Optional[RwTaskEvalRunReport]) -> EvalEvidenceUse:
        if not run_report or run_report.run_status != "completed":
            return "toolchain_smoke_only"
        if run_report.evaluation_mode == "candidate_ready_eval_candidate":
            return "candidate_quality_evidence"
        return "draft_quality_observation"

    def _command_success_count(self, run_report: Optional[RwTaskEvalRunReport]) -> int:
        if not run_report:
            return 0
        return sum(1 for record in run_report.command_records if record.status == "succeeded")

    def _average_score_ratio(self, samples: List[RwTaskEvalSampleSummary]) -> Optional[float]:
        ratios = [sample.score_ratio for sample in samples if sample.score_ratio is not None]
        if not ratios:
            return None
        return sum(ratios) / len(ratios)

    def _ratio(self, total_score: Optional[float], max_score: Optional[float]) -> Optional[float]:
        if total_score is None or max_score in {None, 0}:
            return None
        return total_score / max_score

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _notes(self, run_report: Optional[RwTaskEvalRunReport]) -> List[str]:
        notes = [
            "This summary is report-only and does not update registries, transition priors, or quality gates.",
            "Draft inspection results can prove toolchain compatibility and expose weaknesses, but they do not promote a package to candidate_ready.",
        ]
        if run_report and run_report.evaluation_mode == "draft_inspection_only":
            notes.append(
                "The source package was explicitly marked draft_inspection_only and not_final_training_data."
            )
        return notes
