from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


DEFAULT_MODELS = ["gpt-5.4-pro", "gpt-4o-mini"]


class RunnableSliceRequest(BaseModel):
    clean_baseline_path: str
    anatomy_jsonl_path: str
    gap_autopsy_report_path: str
    hypothesis_ledger_path: str
    subset_manifest_path: str
    release_manifest_path: str
    output_dir: str
    target_gdpval_clean_pairs: int = 8
    target_taskgenerator_pairs: int = 4
    models: List[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))


class GDPValSliceRecord(BaseModel):
    task_id: str
    case_slug: str
    queue_role: str
    selection_bucket: str = ""
    deliverable_type: str = "unknown"
    deliverable_format: str = "unknown"
    reference_file_count: int = 0
    reasoning_requirements: List[str] = Field(default_factory=list)
    likely_skill_motifs: List[str] = Field(default_factory=list)
    clean_status: str = "not_evaluated"
    score_gap: Optional[float] = None
    gap_band: Optional[str] = None
    priority_score: float = 0.0
    selection_reasons: List[str] = Field(default_factory=list)
    command_preview: Optional[str] = None
    diagnostic_only: bool = True
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True


class TaskGeneratorComparisonRecord(BaseModel):
    task_id: str
    source_case_id: str
    release_task_dir: str
    dataset_row_path: str
    motif: str
    blueprint_id: str = ""
    decision: str = ""
    queue_role: str = "taskgenerator_comparison_eval_candidate"
    selection_reasons: List[str] = Field(default_factory=list)
    command_preview: str = ""
    diagnostic_only: bool = True
    use: str = "generated_training_candidate_diagnostic_comparison"
    not_benchmark_grade: bool = True


class RunnableSliceManifest(BaseModel):
    manifest_version: str = "v3.gdpval_runnable_slice.1"
    created_at: str
    request: RunnableSliceRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    current_gdpval_clean_seed_count: int
    gdpval_holdout_count: int
    next_gdpval_eval_count: int
    taskgenerator_comparison_count: int
    target_total_clean_pairs: int
    gdpval_seed_cases: List[GDPValSliceRecord] = Field(default_factory=list)
    gdpval_holdout_cases: List[GDPValSliceRecord] = Field(default_factory=list)
    next_gdpval_eval_queue: List[GDPValSliceRecord] = Field(default_factory=list)
    taskgenerator_comparison_plan: List[TaskGeneratorComparisonRecord] = Field(default_factory=list)
    strata_counts: Dict[str, int] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class GDPValNextEvalQueueReport(BaseModel):
    report_version: str = "v3.gdpval_next_eval_queue.1"
    created_at: str
    diagnostic_only: bool = True
    queue_count: int
    queue: List[GDPValSliceRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TaskGeneratorComparisonEvalPlan(BaseModel):
    report_version: str = "v3.taskgenerator_comparison_eval_plan.1"
    created_at: str
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    release_id: str
    release_manifest_path: str
    selected_count: int
    selected_tasks: List[TaskGeneratorComparisonRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValRunnableSliceBuilder:
    def build(self, request: RunnableSliceRequest) -> RunnableSliceManifest:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        clean = self._read_json(Path(request.clean_baseline_path))
        anatomy_by_id = self._read_jsonl_by_id(Path(request.anatomy_jsonl_path))
        autopsy = self._read_json(Path(request.gap_autopsy_report_path))
        subset = self._read_json(Path(request.subset_manifest_path))
        release = self._read_json(Path(request.release_manifest_path))

        clean_by_id = {str(item.get("task_id") or ""): item for item in clean.get("tasks") or []}
        gap_band_by_id = {str(item.get("task_id") or ""): str(item.get("gap_band") or "") for item in autopsy.get("cases") or []}
        selected_ids = [str(item) for item in subset.get("selected_task_ids") or []]

        seed_cases = self._build_seed_cases(clean_by_id, anatomy_by_id, gap_band_by_id, request)
        holdouts = self._build_holdouts(clean_by_id, anatomy_by_id, gap_band_by_id, request)
        next_queue = self._select_next_gdpval_queue(
            selected_ids=selected_ids,
            clean_by_id=clean_by_id,
            anatomy_by_id=anatomy_by_id,
            gap_band_by_id=gap_band_by_id,
            request=request,
        )
        comparison_plan = self._select_taskgenerator_comparison_tasks(release, Path(request.release_manifest_path), request)

        manifest = RunnableSliceManifest(
            created_at=self._now(),
            request=request,
            current_gdpval_clean_seed_count=len(seed_cases),
            gdpval_holdout_count=len(holdouts),
            next_gdpval_eval_count=len(next_queue),
            taskgenerator_comparison_count=len(comparison_plan),
            target_total_clean_pairs=len(seed_cases) + len(next_queue) + len(comparison_plan),
            gdpval_seed_cases=seed_cases,
            gdpval_holdout_cases=holdouts,
            next_gdpval_eval_queue=next_queue,
            taskgenerator_comparison_plan=comparison_plan,
            strata_counts=self._strata_counts(seed_cases + holdouts + next_queue, comparison_plan),
            notes=[
                "Runnable slice v2 is a planning layer only; it does not execute rw-task or call external models.",
                "GDPVal tasks remain eval_calibration_only and not_for_training_generation.",
                "TaskGenerator release tasks are selected for diagnostic comparison only, not benchmark-grade claims.",
                "Missing-deliverable GDPVal cases are retained as holdouts and are not counted as clean gap evidence.",
            ],
        )
        self._write_json(output_dir / "gdpval_runnable_slice_v2_manifest.json", manifest.model_dump(mode="json"))
        self._write_json(
            output_dir / "gdpval_next_eval_queue.json",
            GDPValNextEvalQueueReport(
                created_at=self._now(),
                queue_count=len(next_queue),
                queue=next_queue,
                notes=[
                    "Run these GDPVal cases one at a time with the single-case evaluator.",
                    "Do not count a case as clean until both model sides have usable deliverables and completed grading.",
                ],
            ).model_dump(mode="json"),
        )
        self._write_json(
            output_dir / "taskgenerator_comparison_eval_plan.json",
            TaskGeneratorComparisonEvalPlan(
                created_at=self._now(),
                release_id=str(release.get("release_id") or ""),
                release_manifest_path=str(Path(request.release_manifest_path)),
                selected_count=len(comparison_plan),
                selected_tasks=comparison_plan,
                notes=[
                    "Selected generated tasks cover the four current Phase 13 motif families.",
                    "Evaluate these only as diagnostic comparison candidates against the GDPVal clean slice.",
                ],
            ).model_dump(mode="json"),
        )
        return manifest

    def _build_seed_cases(
        self,
        clean_by_id: Dict[str, Dict[str, Any]],
        anatomy_by_id: Dict[str, Dict[str, Any]],
        gap_band_by_id: Dict[str, str],
        request: RunnableSliceRequest,
    ) -> List[GDPValSliceRecord]:
        records: List[GDPValSliceRecord] = []
        for task_id, clean_record in clean_by_id.items():
            if not clean_record.get("usable_for_gap_analysis"):
                continue
            anatomy = anatomy_by_id.get(task_id, {})
            records.append(
                self._gdpval_record(
                    task_id=task_id,
                    anatomy=anatomy,
                    clean_record=clean_record,
                    gap_band=gap_band_by_id.get(task_id),
                    queue_role="current_clean_seed",
                    priority_score=0.0,
                    selection_reasons=[
                        "already_has_clean_paired_scores",
                        f"gap_band:{gap_band_by_id.get(task_id) or 'unknown'}",
                    ],
                    request=request,
                )
            )
        return records

    def _build_holdouts(
        self,
        clean_by_id: Dict[str, Dict[str, Any]],
        anatomy_by_id: Dict[str, Dict[str, Any]],
        gap_band_by_id: Dict[str, str],
        request: RunnableSliceRequest,
    ) -> List[GDPValSliceRecord]:
        records: List[GDPValSliceRecord] = []
        for task_id, clean_record in clean_by_id.items():
            if clean_record.get("usable_for_gap_analysis"):
                continue
            anatomy = anatomy_by_id.get(task_id, {})
            reasons = [str(item) for item in clean_record.get("failure_reasons") or []]
            records.append(
                self._gdpval_record(
                    task_id=task_id,
                    anatomy=anatomy,
                    clean_record=clean_record,
                    gap_band=gap_band_by_id.get(task_id) or "unusable",
                    queue_role="runnability_friction_holdout",
                    priority_score=0.0,
                    selection_reasons=[
                        "not_counted_as_clean_gap_evidence",
                        "requires_targeted_rerun_before_gap_analysis",
                        *reasons,
                    ],
                    request=request,
                )
            )
        return records

    def _select_next_gdpval_queue(
        self,
        *,
        selected_ids: List[str],
        clean_by_id: Dict[str, Dict[str, Any]],
        anatomy_by_id: Dict[str, Dict[str, Any]],
        gap_band_by_id: Dict[str, str],
        request: RunnableSliceRequest,
    ) -> List[GDPValSliceRecord]:
        needed = max(0, request.target_gdpval_clean_pairs - sum(1 for item in clean_by_id.values() if item.get("usable_for_gap_analysis")))
        candidates: List[GDPValSliceRecord] = []
        for task_id in selected_ids:
            clean_record = clean_by_id.get(task_id)
            if clean_record and clean_record.get("completion_status") != "not_evaluated":
                continue
            anatomy = anatomy_by_id.get(task_id, {})
            if not anatomy:
                continue
            score, reasons = self._gdpval_priority(anatomy)
            candidates.append(
                self._gdpval_record(
                    task_id=task_id,
                    anatomy=anatomy,
                    clean_record=clean_record or {},
                    gap_band=gap_band_by_id.get(task_id),
                    queue_role="next_gdpval_eval_candidate",
                    priority_score=score,
                    selection_reasons=reasons,
                    request=request,
                )
            )
        return self._diversified_gdpval_selection(candidates, needed)

    def _gdpval_priority(self, anatomy: Dict[str, Any]) -> tuple[float, List[str]]:
        score = 0.0
        reasons: List[str] = []
        bucket = str(anatomy.get("selection_bucket") or "")
        deliverable_type = str(anatomy.get("deliverable_type") or "")
        reference_count = int(anatomy.get("reference_file_count") or 0)
        requirements = set(str(item) for item in anatomy.get("reasoning_requirements") or [])
        risks = set(str(item) for item in anatomy.get("toolchain_risks") or [])
        if bucket == "policy_compliance_like":
            score += 4
            reasons.append("adds_policy_or_compliance_stratum")
        if bucket == "finance_report_memo" or deliverable_type == "document_report":
            score += 4
            reasons.append("adds_document_or_report_stratum")
        if deliverable_type == "slide_deck":
            score += 3
            reasons.append("adds_presentation_deliverable_stratum")
        if deliverable_type == "spreadsheet_workbook":
            score += 2
            reasons.append("keeps_spreadsheet_finance_core")
        if "policy_application" in requirements:
            score += 2
            reasons.append("requires_policy_application")
        if "cross_file_synthesis" in requirements:
            score += 2
            reasons.append("requires_cross_file_synthesis")
        if reference_count >= 3:
            score += 2
            reasons.append("multi_reference_workflow")
        if reference_count >= 10:
            score -= 2
            reasons.append("large_reference_bundle_risk")
        if "deliverable_metadata_missing" in risks:
            score -= 1
            reasons.append("deliverable_metadata_missing_risk")
        if not reasons:
            reasons.append("fills_remaining_gdpval_slice_capacity")
        return score, reasons

    def _diversified_gdpval_selection(self, candidates: List[GDPValSliceRecord], needed: int) -> List[GDPValSliceRecord]:
        if needed <= 0:
            return []
        selected: List[GDPValSliceRecord] = []
        used_types: Set[str] = set()
        used_buckets: Set[str] = set()
        for candidate in sorted(candidates, key=lambda item: (-item.priority_score, item.reference_file_count, item.task_id)):
            type_key = candidate.deliverable_type
            bucket_key = candidate.selection_bucket
            if len(selected) < needed and (type_key not in used_types or bucket_key not in used_buckets):
                selected.append(candidate)
                used_types.add(type_key)
                used_buckets.add(bucket_key)
        for candidate in sorted(candidates, key=lambda item: (-item.priority_score, item.reference_file_count, item.task_id)):
            if len(selected) >= needed:
                break
            if candidate.task_id not in {item.task_id for item in selected}:
                selected.append(candidate)
        return selected[:needed]

    def _select_taskgenerator_comparison_tasks(
        self,
        release: Dict[str, Any],
        release_manifest_path: Path,
        request: RunnableSliceRequest,
    ) -> List[TaskGeneratorComparisonRecord]:
        release_root = release_manifest_path.parent
        records = [record for record in release.get("task_records") or [] if record.get("included_in_release")]
        selected: List[TaskGeneratorComparisonRecord] = []
        used_motifs: Set[str] = set()
        for record in records:
            motif = str(record.get("motif") or "")
            if motif in used_motifs:
                continue
            selected.append(self._taskgenerator_record(record, release_root, request))
            used_motifs.add(motif)
            if len(selected) >= request.target_taskgenerator_pairs:
                break
        if len(selected) < request.target_taskgenerator_pairs:
            selected_ids = {item.task_id for item in selected}
            for record in records:
                if len(selected) >= request.target_taskgenerator_pairs:
                    break
                if str(record.get("task_id") or "") not in selected_ids:
                    selected.append(self._taskgenerator_record(record, release_root, request))
        return selected

    def _taskgenerator_record(
        self,
        record: Dict[str, Any],
        release_root: Path,
        request: RunnableSliceRequest,
    ) -> TaskGeneratorComparisonRecord:
        release_task_dir = str(record.get("release_task_dir") or "")
        task_dir = release_root / release_task_dir
        dataset_row_name = f"{Path(release_task_dir).name}.dataset_row.json"
        dataset_row_path = release_root / "dataset_rows" / dataset_row_name
        task_id = str(record.get("task_id") or "")
        models = " ".join(f"--model {model}" for model in request.models)
        command_preview = (
            "python Test/run_v3_generated_task_comparison_eval.py "
            f"--mode dry-run --task-id {task_id} {models} --overwrite"
        )
        return TaskGeneratorComparisonRecord(
            task_id=task_id,
            source_case_id=str(record.get("source_case_id") or ""),
            release_task_dir=str(task_dir),
            dataset_row_path=str(dataset_row_path),
            motif=str(record.get("motif") or ""),
            blueprint_id=str(record.get("blueprint_id") or ""),
            decision=str(record.get("decision") or ""),
            selection_reasons=[
                "covers_phase13_reviewed_release_motif",
                f"motif:{record.get('motif') or ''}",
                "diagnostic_generated_vs_gdpval_comparison_candidate",
            ],
            command_preview=command_preview,
        )

    def _gdpval_record(
        self,
        *,
        task_id: str,
        anatomy: Dict[str, Any],
        clean_record: Dict[str, Any],
        gap_band: Optional[str],
        queue_role: str,
        priority_score: float,
        selection_reasons: List[str],
        request: RunnableSliceRequest,
    ) -> GDPValSliceRecord:
        models = " ".join(f"--model {model}" for model in request.models)
        command_preview = None
        if queue_role == "next_gdpval_eval_candidate":
            command_preview = f"python Test/run_v3_gdpval_single_case_eval.py --run-id case_{task_id[:4]} --task-id {task_id} --mode execute {models} --run-eval"
        return GDPValSliceRecord(
            task_id=task_id,
            case_slug=str(anatomy.get("case_slug") or clean_record.get("case_slug") or task_id.replace("-", "_")),
            queue_role=queue_role,
            selection_bucket=str(anatomy.get("selection_bucket") or clean_record.get("selection_bucket") or ""),
            deliverable_type=str(anatomy.get("deliverable_type") or "unknown"),
            deliverable_format=str(anatomy.get("deliverable_format") or "unknown"),
            reference_file_count=int(anatomy.get("reference_file_count") or clean_record.get("reference_file_count") or 0),
            reasoning_requirements=[str(item) for item in anatomy.get("reasoning_requirements") or []],
            likely_skill_motifs=[str(item) for item in anatomy.get("likely_skill_motifs") or []],
            clean_status=str(clean_record.get("completion_status") or anatomy.get("clean_eval", {}).get("completion_status") or "not_evaluated"),
            score_gap=self._as_float(clean_record.get("score_gap")),
            gap_band=gap_band,
            priority_score=priority_score,
            selection_reasons=selection_reasons,
            command_preview=command_preview,
        )

    def _strata_counts(
        self,
        gdpval_records: List[GDPValSliceRecord],
        generated_records: List[TaskGeneratorComparisonRecord],
    ) -> Dict[str, int]:
        counts = Counter()
        for record in gdpval_records:
            counts[f"gdpval_role:{record.queue_role}"] += 1
            counts[f"gdpval_deliverable:{record.deliverable_type}"] += 1
            if record.gap_band:
                counts[f"gdpval_gap_band:{record.gap_band}"] += 1
            if record.selection_bucket:
                counts[f"gdpval_bucket:{record.selection_bucket}"] += 1
        for record in generated_records:
            counts[f"taskgenerator_motif:{record.motif}"] += 1
        return dict(counts)

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_jsonl_by_id(self, path: Path) -> Dict[str, Dict[str, Any]]:
        values: Dict[str, Dict[str, Any]] = {}
        if not path.exists():
            return values
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            values[str(payload.get("task_id") or "")] = payload
        return values

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
