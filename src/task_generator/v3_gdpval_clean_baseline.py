from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_gdpval_rw_task_eval_adapter import DEFAULT_MODELS, slugify


class GDPValCleanBaselineRequest(BaseModel):
    subset_manifest_path: str
    single_case_runs_dir: str
    output_dir: str
    models: List[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))
    task_limit: int = 5
    task_ids: List[str] = Field(default_factory=list)


class CleanModelScoreRecord(BaseModel):
    model: str
    score_ratio: Optional[float] = None
    total_score: Optional[float] = None
    max_possible_score: Optional[float] = None
    status: str = "missing"
    source_run_id: Optional[str] = None
    source_report_path: Optional[str] = None
    grade_report_path: Optional[str] = None
    accepted_deliverable_count: int = 0
    listed_deliverable_count: int = 0
    failure_reasons: List[str] = Field(default_factory=list)


class CleanBaselineTaskRecord(BaseModel):
    task_id: str
    case_slug: str
    selected_subset_index: int
    selection_bucket: str = ""
    selection_reasons: List[str] = Field(default_factory=list)
    sector: str = ""
    occupation: str = ""
    reference_file_count: int = 0
    deliverable_file_count: int = 0
    reference_file_extensions: List[str] = Field(default_factory=list)
    deliverable_file_extensions: List[str] = Field(default_factory=list)
    model_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    model_records: List[CleanModelScoreRecord] = Field(default_factory=list)
    score_gap: Optional[float] = None
    usable_for_gap_analysis: bool = False
    completion_status: str = "not_evaluated"
    failure_reasons: List[str] = Field(default_factory=list)
    source_run_ids: List[str] = Field(default_factory=list)
    diagnostic_only: bool = True
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True


class GDPValCleanBaselineReport(BaseModel):
    report_version: str = "v3.gdpval_clean_baseline.1"
    created_at: str
    request: GDPValCleanBaselineRequest
    diagnostic_only: bool = True
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True
    task_count: int
    usable_task_count: int
    blocked_task_count: int
    needs_model_rerun_count: int
    models: List[str]
    tasks: List[CleanBaselineTaskRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class CleanGapTaskRecord(BaseModel):
    task_id: str
    case_slug: str
    model_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    score_gap: Optional[float] = None
    usable_for_gap_analysis: bool = False
    completion_status: str = "not_evaluated"
    failure_reasons: List[str] = Field(default_factory=list)


class GDPValCleanGapProfile(BaseModel):
    profile_version: str = "v3.gdpval_clean_gap_profile.1"
    created_at: str
    diagnostic_only: bool = True
    task_count: int
    usable_task_count: int
    models: List[str]
    tasks: List[CleanGapTaskRecord] = Field(default_factory=list)
    score_gap_distribution: Dict[str, int] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class CleanFailureRecord(BaseModel):
    task_id: str
    case_slug: str
    model: Optional[str] = None
    failure_type: str
    failure_reasons: List[str] = Field(default_factory=list)
    related_run_id: Optional[str] = None
    related_path: Optional[str] = None


class GDPValCleanFailureReport(BaseModel):
    report_version: str = "v3.gdpval_clean_failure_report.1"
    created_at: str
    diagnostic_only: bool = True
    failure_count: int
    failures: List[CleanFailureRecord] = Field(default_factory=list)


class _ScoreCandidate(BaseModel):
    model: str
    score_ratio: Optional[float] = None
    total_score: Optional[float] = None
    max_possible_score: Optional[float] = None
    status: str = "missing"
    source_run_id: str
    source_report_path: str
    grade_report_path: Optional[str] = None
    created_at: str = ""
    accepted_deliverable_count: int = 0
    listed_deliverable_count: int = 0
    failure_reasons: List[str] = Field(default_factory=list)


class GDPValCleanBaselineBuilder:
    def build(self, request: GDPValCleanBaselineRequest) -> GDPValCleanBaselineReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        subset_manifest = self._read_json(Path(request.subset_manifest_path))
        selected = self._select_records(list(subset_manifest.get("selected_records") or []), request)
        candidates = self._collect_score_candidates(Path(request.single_case_runs_dir))
        task_records = [
            self._build_task_record(
                selection=selection,
                subset_index=index,
                models=request.models,
                candidates=candidates.get(str(selection.get("task_id") or ""), {}),
            )
            for index, selection in enumerate(selected, start=1)
        ]
        report = GDPValCleanBaselineReport(
            created_at=self._now(),
            request=request,
            task_count=len(task_records),
            usable_task_count=sum(1 for record in task_records if record.usable_for_gap_analysis),
            blocked_task_count=sum(1 for record in task_records if record.completion_status == "blocked"),
            needs_model_rerun_count=sum(1 for record in task_records if record.completion_status == "needs_model_rerun"),
            models=request.models,
            tasks=task_records,
            notes=[
                "This is the clean Phase 14.3 diagnostic baseline assembled from single-case repair runs.",
                "Missing-deliverable zero scores are not counted as usable model-separation evidence.",
                "GDPVal records remain calibration-only and must not enter TaskGenerator training or release pools.",
            ],
        )
        self._write_json(output_dir / "gdpval_clean_baseline_report.json", report.model_dump(mode="json"))
        gap_profile = self._build_gap_profile(report)
        self._write_json(output_dir / "gdpval_clean_gap_profile.json", gap_profile.model_dump(mode="json"))
        failure_report = self._build_failure_report(report)
        self._write_json(output_dir / "gdpval_clean_failure_report.json", failure_report.model_dump(mode="json"))
        return report

    def _select_records(
        self,
        records: List[Dict[str, Any]],
        request: GDPValCleanBaselineRequest,
    ) -> List[Dict[str, Any]]:
        if request.task_ids:
            ids = set(request.task_ids)
            return [record for record in records if str(record.get("task_id") or "") in ids]
        if request.task_limit > 0:
            return records[: request.task_limit]
        return records

    def _collect_score_candidates(self, runs_dir: Path) -> Dict[str, Dict[str, List[_ScoreCandidate]]]:
        by_task: Dict[str, Dict[str, List[_ScoreCandidate]]] = defaultdict(lambda: defaultdict(list))
        if not runs_dir.exists():
            return by_task
        for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
            single_report_path = run_dir / "single_case_report.json"
            regrade_path = run_dir / "sanitized_regrade_report.json"
            diagnostic_path = run_dir / "deliverable_diagnostic_report.json"
            if not single_report_path.exists() or not regrade_path.exists():
                continue
            single_report = self._read_json(single_report_path)
            regrade = self._read_json(regrade_path)
            diagnostics = self._diagnostics_by_model(self._read_json(diagnostic_path))
            task_id = str(single_report.get("task_id") or regrade.get("task_id") or "")
            if not task_id:
                continue
            created_at = str(regrade.get("created_at") or single_report.get("created_at") or "")
            for record in regrade.get("model_records") or []:
                model = str(record.get("model") or "")
                if not model:
                    continue
                diagnostic = diagnostics.get(model, {})
                candidate = _ScoreCandidate(
                    model=model,
                    score_ratio=self._as_float(record.get("score_ratio")),
                    total_score=self._as_float(record.get("total_score")),
                    max_possible_score=self._as_float(record.get("max_possible_score")),
                    status=str(record.get("status") or "missing"),
                    source_run_id=run_dir.name,
                    source_report_path=str(regrade_path),
                    grade_report_path=record.get("grade_report_path"),
                    created_at=created_at,
                    accepted_deliverable_count=int(diagnostic.get("accepted_deliverable_count") or 0),
                    listed_deliverable_count=int(diagnostic.get("listed_deliverable_count") or 0),
                    failure_reasons=[str(item) for item in record.get("failure_reasons") or []],
                )
                by_task[task_id][model].append(candidate)
        return by_task

    def _diagnostics_by_model(self, report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        values: Dict[str, Dict[str, Any]] = {}
        for item in report.get("diagnostics") or []:
            model = str(item.get("model") or "")
            if model:
                values[model] = item
        return values

    def _build_task_record(
        self,
        *,
        selection: Dict[str, Any],
        subset_index: int,
        models: List[str],
        candidates: Dict[str, List[_ScoreCandidate]],
    ) -> CleanBaselineTaskRecord:
        task_id = str(selection.get("task_id") or "")
        model_records: List[CleanModelScoreRecord] = []
        model_scores: Dict[str, Optional[float]] = {}
        source_run_ids = set()
        failures: List[str] = []
        for model in models:
            chosen = self._choose_candidate(candidates.get(model, []))
            if chosen:
                source_run_ids.add(chosen.source_run_id)
                model_scores[model] = chosen.score_ratio if chosen.status == "completed" else None
                model_records.append(
                    CleanModelScoreRecord(
                        model=model,
                        score_ratio=chosen.score_ratio if chosen.status == "completed" else None,
                        total_score=chosen.total_score if chosen.status == "completed" else None,
                        max_possible_score=chosen.max_possible_score if chosen.status == "completed" else None,
                        status=chosen.status,
                        source_run_id=chosen.source_run_id,
                        source_report_path=chosen.source_report_path,
                        grade_report_path=chosen.grade_report_path,
                        accepted_deliverable_count=chosen.accepted_deliverable_count,
                        listed_deliverable_count=chosen.listed_deliverable_count,
                        failure_reasons=chosen.failure_reasons,
                    )
                )
                if chosen.status != "completed":
                    failures.extend(f"{model}: {reason}" for reason in chosen.failure_reasons)
            else:
                model_scores[model] = None
                model_records.append(CleanModelScoreRecord(model=model, failure_reasons=["missing single-case evidence"]))
                failures.append(f"{model}: missing single-case evidence")
        numeric_scores = [score for score in model_scores.values() if score is not None]
        score_gap = (max(numeric_scores) - min(numeric_scores)) if len(numeric_scores) >= 2 else None
        usable = len(numeric_scores) >= 2
        completion_status = self._completion_status(model_records, usable)
        return CleanBaselineTaskRecord(
            task_id=task_id,
            case_slug=slugify(task_id),
            selected_subset_index=subset_index,
            selection_bucket=str(selection.get("selection_bucket") or ""),
            selection_reasons=[str(item) for item in selection.get("selection_reasons") or []],
            sector=str(selection.get("sector") or ""),
            occupation=str(selection.get("occupation") or ""),
            reference_file_count=int(selection.get("reference_file_count") or 0),
            deliverable_file_count=int(selection.get("deliverable_file_count") or 0),
            reference_file_extensions=[str(item) for item in selection.get("reference_file_extensions") or []],
            deliverable_file_extensions=[str(item) for item in selection.get("deliverable_file_extensions") or []],
            model_scores=model_scores,
            model_records=model_records,
            score_gap=score_gap,
            usable_for_gap_analysis=usable,
            completion_status=completion_status,
            failure_reasons=[] if usable else failures,
            source_run_ids=sorted(source_run_ids),
        )

    def _choose_candidate(self, candidates: List[_ScoreCandidate]) -> Optional[_ScoreCandidate]:
        if not candidates:
            return None
        completed = [item for item in candidates if item.status == "completed" and item.score_ratio is not None]
        if completed:
            return sorted(completed, key=lambda item: (item.created_at, item.source_run_id))[-1]
        return sorted(candidates, key=lambda item: (item.created_at, item.source_run_id))[-1]

    def _completion_status(self, records: List[CleanModelScoreRecord], usable: bool) -> str:
        if usable:
            return "usable_for_gap_analysis"
        if any(record.listed_deliverable_count == 0 for record in records if record.status != "completed"):
            return "needs_model_rerun"
        if any(record.status not in {"completed", "missing"} for record in records):
            return "needs_regrade"
        return "blocked"

    def _build_gap_profile(self, report: GDPValCleanBaselineReport) -> GDPValCleanGapProfile:
        buckets = Counter()
        tasks: List[CleanGapTaskRecord] = []
        for record in report.tasks:
            if not record.usable_for_gap_analysis or record.score_gap is None:
                buckets["unusable"] += 1
            elif record.score_gap >= 0.5:
                buckets["high_gap"] += 1
            elif record.score_gap >= 0.15:
                buckets["medium_gap"] += 1
            else:
                buckets["low_gap"] += 1
            tasks.append(
                CleanGapTaskRecord(
                    task_id=record.task_id,
                    case_slug=record.case_slug,
                    model_scores=record.model_scores,
                    score_gap=record.score_gap,
                    usable_for_gap_analysis=record.usable_for_gap_analysis,
                    completion_status=record.completion_status,
                    failure_reasons=record.failure_reasons,
                )
            )
        return GDPValCleanGapProfile(
            created_at=self._now(),
            task_count=report.task_count,
            usable_task_count=report.usable_task_count,
            models=report.models,
            tasks=tasks,
            score_gap_distribution=dict(buckets),
            notes=[
                "Gap buckets are diagnostic: high >= 0.5, medium >= 0.15, low < 0.15.",
                "Only tasks with at least two completed sanitized scores are usable for gap analysis.",
            ],
        )

    def _build_failure_report(self, report: GDPValCleanBaselineReport) -> GDPValCleanFailureReport:
        failures: List[CleanFailureRecord] = []
        for task in report.tasks:
            for record in task.model_records:
                if record.status == "completed":
                    continue
                failure_type = "missing_deliverable" if record.listed_deliverable_count == 0 else "missing_or_failed_score"
                failures.append(
                    CleanFailureRecord(
                        task_id=task.task_id,
                        case_slug=task.case_slug,
                        model=record.model,
                        failure_type=failure_type,
                        failure_reasons=record.failure_reasons,
                        related_run_id=record.source_run_id,
                        related_path=record.source_report_path,
                    )
                )
        return GDPValCleanFailureReport(
            created_at=self._now(),
            failure_count=len(failures),
            failures=failures,
        )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _as_float(self, value: Any) -> Optional[float]:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
