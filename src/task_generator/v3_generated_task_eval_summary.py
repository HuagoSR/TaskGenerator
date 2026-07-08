from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


DEFAULT_MODELS = ["gpt-5.4-pro", "gpt-4o-mini"]


class GeneratedTaskEvalSummaryRequest(BaseModel):
    eval_report_path: str
    eval_report_paths: List[str] = Field(default_factory=list)
    output_dir: str
    strong_model: str = "gpt-5.4-pro"
    weak_model: str = "gpt-4o-mini"


class GeneratedTaskModelScore(BaseModel):
    task_id: str
    motif: str = ""
    model: str
    run_status: str = "unknown"
    completion_status: str = "unknown"
    eval_results_dir: Optional[str] = None
    grade_output_dir: Optional[str] = None
    grade_report_path: Optional[str] = None
    score_ratio: Optional[float] = None
    total_score: Optional[float] = None
    max_possible_score: Optional[float] = None
    deliverable_file_count: int = 0
    failure_reasons: List[str] = Field(default_factory=list)


class GeneratedTaskGapRecord(BaseModel):
    task_id: str
    motif: str = ""
    strong_model: str
    weak_model: str
    strong_score_ratio: Optional[float] = None
    weak_score_ratio: Optional[float] = None
    score_gap: Optional[float] = None
    usable_for_gap_analysis: bool = False
    failure_reasons: List[str] = Field(default_factory=list)
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True


class GeneratedTaskEvalSummaryReport(BaseModel):
    report_version: str = "v3.generated_task_eval_summary.1"
    created_at: str
    request: GeneratedTaskEvalSummaryRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    task_count: int
    model_score_count: int
    completed_model_score_count: int
    clean_pair_count: int
    blocked_pair_count: int
    model_scores: List[GeneratedTaskModelScore] = Field(default_factory=list)
    gap_records: List[GeneratedTaskGapRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GeneratedTaskEvalSummaryBuilder:
    def build(self, request: GeneratedTaskEvalSummaryRequest) -> GeneratedTaskEvalSummaryReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        eval_report_paths = request.eval_report_paths or [request.eval_report_path]
        records: List[Dict[str, Any]] = []
        for report_path in eval_report_paths:
            eval_report = self._read_json(Path(report_path))
            records.extend(eval_report.get("records") or [])
        model_scores = [self._model_score(record) for record in records]
        gap_records = self._gap_records(model_scores, request)
        report = GeneratedTaskEvalSummaryReport(
            created_at=self._now(),
            request=request,
            task_count=len({item.task_id for item in model_scores}),
            model_score_count=len(model_scores),
            completed_model_score_count=sum(1 for item in model_scores if item.score_ratio is not None),
            clean_pair_count=sum(1 for item in gap_records if item.usable_for_gap_analysis),
            blocked_pair_count=sum(1 for item in gap_records if not item.usable_for_gap_analysis),
            model_scores=model_scores,
            gap_records=gap_records,
            notes=[
                "This summary reads existing generated-task rw-task outputs only; it does not call models.",
                "A clean pair requires non-empty scores for both the configured strong and weak models.",
                "Generated-vs-GDPVal model-separation claims remain diagnostic-only and not benchmark-grade.",
            ],
        )
        self._write_json(output_dir / "generated_task_eval_summary_report.json", report.model_dump(mode="json"))
        self._write_json(output_dir / "generated_task_gap_profile.json", self._gap_profile(report))
        return report

    def _model_score(self, record: Dict[str, Any]) -> GeneratedTaskModelScore:
        grade_dir = Path(str(record.get("grade_output_dir") or ""))
        eval_results_dir = Path(str(record.get("eval_results_dir") or ""))
        task_id = str(record.get("task_id") or "")
        grade_report_path, sample = self._find_grade_sample(grade_dir, task_id)
        total_score = self._as_float((sample.get("grading") or {}).get("total_score")) if sample else None
        max_score = self._as_float((sample.get("grading") or {}).get("max_possible_score")) if sample else None
        score_ratio = total_score / max_score if total_score is not None and max_score else None
        failure_reasons = list(record.get("blocking_reasons") or [])
        if record.get("run_status") in {"failed", "timeout", "partial_failed", "blocked"}:
            failure_reasons.append(f"run_status:{record.get('run_status')}")
        if grade_dir and not grade_dir.exists():
            failure_reasons.append("grade_output_dir_missing")
        elif sample is None:
            failure_reasons.append("grade_sample_missing")
        return GeneratedTaskModelScore(
            task_id=task_id,
            motif=str(record.get("motif") or ""),
            model=str(record.get("model") or ""),
            run_status=str(record.get("run_status") or "unknown"),
            completion_status=str(record.get("completion_status") or "unknown"),
            eval_results_dir=str(eval_results_dir) if str(eval_results_dir) else None,
            grade_output_dir=str(grade_dir) if str(grade_dir) else None,
            grade_report_path=str(grade_report_path) if grade_report_path else None,
            score_ratio=score_ratio,
            total_score=total_score,
            max_possible_score=max_score,
            deliverable_file_count=self._deliverable_file_count(eval_results_dir),
            failure_reasons=sorted(set(failure_reasons)),
        )

    def _find_grade_sample(self, grade_dir: Path, task_id: str) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
        if not grade_dir.exists():
            return None, None
        candidates = sorted(grade_dir.glob("eval_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            try:
                payload = self._read_json(path)
            except Exception:
                continue
            for sample in payload.get("samples") or []:
                if str(sample.get("task_id") or "") == task_id:
                    return path, sample
        return None, None

    def _deliverable_file_count(self, eval_results_dir: Path) -> int:
        if not eval_results_dir.exists():
            return 0
        count = 0
        for path in eval_results_dir.rglob("*"):
            if path.is_file() and path.name not in {"dataset_row.json"}:
                if "logs" not in path.parts:
                    count += 1
        return count

    def _gap_records(
        self,
        model_scores: List[GeneratedTaskModelScore],
        request: GeneratedTaskEvalSummaryRequest,
    ) -> List[GeneratedTaskGapRecord]:
        by_task: Dict[str, Dict[str, GeneratedTaskModelScore]] = defaultdict(dict)
        motifs: Dict[str, str] = {}
        for score in model_scores:
            by_task[score.task_id][score.model] = score
            motifs[score.task_id] = score.motif
        records: List[GeneratedTaskGapRecord] = []
        for task_id, by_model in sorted(by_task.items()):
            strong = by_model.get(request.strong_model)
            weak = by_model.get(request.weak_model)
            failures: List[str] = []
            if strong is None:
                failures.append(f"missing_strong_model:{request.strong_model}")
            if weak is None:
                failures.append(f"missing_weak_model:{request.weak_model}")
            strong_score = strong.score_ratio if strong else None
            weak_score = weak.score_ratio if weak else None
            if strong and strong_score is None:
                failures.extend(strong.failure_reasons or ["strong_score_missing"])
            if weak and weak_score is None:
                failures.extend(weak.failure_reasons or ["weak_score_missing"])
            usable = strong_score is not None and weak_score is not None
            records.append(
                GeneratedTaskGapRecord(
                    task_id=task_id,
                    motif=motifs.get(task_id, ""),
                    strong_model=request.strong_model,
                    weak_model=request.weak_model,
                    strong_score_ratio=strong_score,
                    weak_score_ratio=weak_score,
                    score_gap=abs(strong_score - weak_score) if usable else None,
                    usable_for_gap_analysis=usable,
                    failure_reasons=sorted(set(failures)),
                )
            )
        return records

    def _gap_profile(self, report: GeneratedTaskEvalSummaryReport) -> Dict[str, Any]:
        return {
            "report_version": "v3.generated_task_gap_profile.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "not_benchmark_grade": True,
            "clean_pair_count": report.clean_pair_count,
            "blocked_pair_count": report.blocked_pair_count,
            "gap_records": [item.model_dump(mode="json") for item in report.gap_records],
        }

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _as_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
