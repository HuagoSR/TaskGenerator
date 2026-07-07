from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


EvalMode = Literal["prepare", "dry-run", "execute"]
PrepStatus = Literal["prepared", "blocked"]
RunStatus = Literal["not_run", "completed", "partial_failed", "failed", "timeout"]
GradeStatus = Literal["not_run", "completed", "failed", "missing"]
CompletionStatus = Literal["completed", "failed", "blocked", "not_run"]

DEFAULT_MODELS = ["gpt-5.4-pro", "gpt-4o-mini"]
DEFAULT_GRADER_MODEL = "gpt-5.4-pro"


def ensure_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    out = []
    for char in value.lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "_":
            out.append("_")
    slug = "".join(out).strip("_")
    return slug or "case"


class GDPValRwTaskEvalRequest(BaseModel):
    subset_manifest_path: str
    output_dir: str
    mode: EvalMode = "dry-run"
    models: List[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))
    workers: int = 1
    rw_task_root: str
    python_exe: str = sys.executable
    env_path: Optional[str] = None
    task_limit: int = 0
    task_ids: List[str] = Field(default_factory=list)
    case_indexes: List[int] = Field(default_factory=list)
    overwrite: bool = False
    command_timeout_seconds: int = 7200
    run_eval: bool = False
    agent_max_tokens: int = 16000
    case_timeout_seconds: int = 1800
    sandbox_timeout_seconds: int = 3600
    grader_model: Optional[str] = DEFAULT_GRADER_MODEL


class PreparedGDPValCase(BaseModel):
    task_id: str
    case_slug: str
    case_dir: str
    dataset_row_path: str
    reference_file_count: int
    deliverable_file_count: int
    selection_bucket: str
    selection_reasons: List[str] = Field(default_factory=list)
    prep_status: PrepStatus = "prepared"
    failure_reasons: List[str] = Field(default_factory=list)


class ModelTaskResult(BaseModel):
    task_id: str
    case_slug: str
    prep_status: PrepStatus = "prepared"
    run_status: RunStatus = "not_run"
    grade_status: GradeStatus = "not_run"
    completion_status: CompletionStatus = "not_run"
    score_ratio: Optional[float] = None
    total_score: Optional[float] = None
    max_possible_score: Optional[float] = None
    tool_failure: bool = False
    usable_for_gap_analysis: bool = False
    failure_reasons: List[str] = Field(default_factory=list)
    run_output_dir: Optional[str] = None
    grade_report_path: Optional[str] = None


class GDPValModelRunRecord(BaseModel):
    model: str
    model_slug: str
    input_dir: str
    output_dir: str
    grade_dir: str
    logs_dir: str
    command_preview: List[str]
    grade_command_preview: List[str]
    run_status: RunStatus = "not_run"
    grade_status: GradeStatus = "not_run"
    completion_status: CompletionStatus = "not_run"
    returncode: Optional[int] = None
    grade_returncode: Optional[int] = None
    command_executed: bool = False
    stdout_log_path: Optional[str] = None
    stderr_log_path: Optional[str] = None
    grade_stdout_log_path: Optional[str] = None
    grade_stderr_log_path: Optional[str] = None
    task_results: List[ModelTaskResult] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)


class GDPValEvalCampaignReport(BaseModel):
    report_version: str = "v3.gdpval_rw_task_eval_campaign.1"
    created_at: str
    request: GDPValRwTaskEvalRequest
    use: str = "eval_calibration_only"
    diagnostic_only: bool = True
    not_for_training_generation: bool = True
    subset_manifest_path: str
    mirror_manifest_path: str
    eval_input_dir: str
    prepared_task_count: int
    blocked_task_count: int
    model_count: int
    executed_model_count: int
    prepared_cases: List[PreparedGDPValCase] = Field(default_factory=list)
    model_runs: List[GDPValModelRunRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GapTaskRecord(BaseModel):
    task_id: str
    case_slug: str
    model_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    score_gap: Optional[float] = None
    usable_for_gap_analysis: bool = False
    failure_mode: str = "not_executed"
    failure_reasons: List[str] = Field(default_factory=list)


class GDPValModelGapProfile(BaseModel):
    profile_version: str = "v3.gdpval_model_gap_profile.1"
    created_at: str
    diagnostic_only: bool = True
    task_count: int
    usable_task_count: int
    models: List[str]
    tasks: List[GapTaskRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValEvalFailureRecord(BaseModel):
    model: Optional[str] = None
    task_id: Optional[str] = None
    case_slug: Optional[str] = None
    failure_type: str
    failure_reasons: List[str] = Field(default_factory=list)
    related_path: Optional[str] = None


class GDPValEvalFailureReport(BaseModel):
    report_version: str = "v3.gdpval_eval_failure_report.1"
    created_at: str
    diagnostic_only: bool = True
    failure_count: int
    failures: List[GDPValEvalFailureRecord] = Field(default_factory=list)


class GDPValRwTaskEvalAdapter:
    def run(self, request: GDPValRwTaskEvalRequest) -> GDPValEvalCampaignReport:
        output_dir = Path(request.output_dir).resolve()
        if request.overwrite and output_dir.exists():
            shutil.rmtree(output_dir)
        ensure_dir(output_dir)
        eval_input_dir = ensure_dir(output_dir / "eval_input")
        model_runs_dir = ensure_dir(output_dir / "model_runs")

        subset_manifest = self._read_json(Path(request.subset_manifest_path))
        mirror_manifest_path = Path(subset_manifest["request"]["mirror_manifest_path"]).resolve()
        mirror_manifest = self._read_json(mirror_manifest_path)
        mirror_by_id = {str(record.get("task_id")): record for record in mirror_manifest.get("tasks", [])}

        selected = list(subset_manifest.get("selected_records") or [])
        selected = self._select_records(
            selected,
            task_ids=request.task_ids,
            case_indexes=request.case_indexes,
            task_limit=request.task_limit,
        )

        prepared_cases = [
            self._prepare_case(
                selection=selection,
                mirror_record=mirror_by_id.get(str(selection.get("task_id") or "")),
                eval_input_dir=eval_input_dir,
            )
            for selection in selected
        ]
        model_runs = [
            self._build_model_run(
                request=request,
                model=model,
                eval_input_dir=eval_input_dir,
                model_runs_dir=model_runs_dir,
                prepared_cases=prepared_cases,
            )
            for model in request.models
        ]

        if request.mode == "execute":
            if not request.run_eval:
                for record in model_runs:
                    record.run_status = "failed"
                    record.completion_status = "failed"
                    record.failure_reasons.append("execute mode requires explicit --run-eval")
            else:
                for record in model_runs:
                    self._execute_model_run(request=request, record=record, output_dir=output_dir)

        report = GDPValEvalCampaignReport(
            created_at=self._now(),
            request=request,
            subset_manifest_path=str(Path(request.subset_manifest_path).resolve()),
            mirror_manifest_path=str(mirror_manifest_path),
            eval_input_dir=str(eval_input_dir),
            prepared_task_count=sum(1 for case in prepared_cases if case.prep_status == "prepared"),
            blocked_task_count=sum(1 for case in prepared_cases if case.prep_status == "blocked"),
            model_count=len(model_runs),
            executed_model_count=sum(1 for run in model_runs if run.command_executed),
            prepared_cases=prepared_cases,
            model_runs=model_runs,
            notes=[
                "This report is calibration-only and diagnostic-only.",
                "GDPVal cases prepared here must not be promoted into TaskGenerator training generation or release pools.",
                "Secrets from .env are loaded only into subprocess environments during execute mode and are not written to reports.",
            ],
        )
        self._write_json(output_dir / "gdpval_eval_campaign_report.json", report.model_dump(mode="json"))
        gap_profile = self._build_gap_profile(report)
        self._write_json(output_dir / "gdpval_model_gap_profile.json", gap_profile.model_dump(mode="json"))
        failure_report = self._build_failure_report(report)
        self._write_json(output_dir / "gdpval_eval_failure_report.json", failure_report.model_dump(mode="json"))
        return report

    def _select_records(
        self,
        records: List[Dict[str, Any]],
        *,
        task_ids: List[str],
        case_indexes: List[int],
        task_limit: int,
    ) -> List[Dict[str, Any]]:
        selected = list(records)
        wanted_ids = {str(task_id).strip() for task_id in task_ids if str(task_id).strip()}
        wanted_indexes = [int(index) for index in case_indexes if int(index) > 0]
        if wanted_ids or wanted_indexes:
            by_id = {str(record.get("task_id") or ""): record for record in records}
            picked: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for task_id in task_ids:
                normalized = str(task_id).strip()
                if not normalized:
                    continue
                record = by_id.get(normalized)
                if record is None:
                    continue
                if normalized not in seen:
                    picked.append(record)
                    seen.add(normalized)
            for index in wanted_indexes:
                zero_based = index - 1
                if zero_based < 0 or zero_based >= len(records):
                    continue
                record = records[zero_based]
                task_id = str(record.get("task_id") or "")
                if task_id not in seen:
                    picked.append(record)
                    seen.add(task_id)
            selected = picked
        elif task_limit > 0:
            selected = selected[:task_limit]
        return selected

    def _prepare_case(
        self,
        *,
        selection: Dict[str, Any],
        mirror_record: Any,
        eval_input_dir: Path,
    ) -> PreparedGDPValCase:
        task_id = str(selection.get("task_id") or "")
        case_slug = slugify(task_id)
        case_dir = ensure_dir(eval_input_dir / case_slug)
        failures: List[str] = []
        if mirror_record is None:
            failures.append("task_id not found in GDPVal mirror manifest")
            return PreparedGDPValCase(
                task_id=task_id,
                case_slug=case_slug,
                case_dir=str(case_dir),
                dataset_row_path=str(case_dir / "dataset_row.json"),
                reference_file_count=0,
                deliverable_file_count=int(selection.get("deliverable_file_count") or 0),
                selection_bucket=str(selection.get("selection_bucket") or ""),
                selection_reasons=list(selection.get("selection_reasons") or []),
                prep_status="blocked",
                failure_reasons=failures,
            )

        prompt_path = Path(str(mirror_record.get("prompt_path") or ""))
        metadata_path = Path(str(mirror_record.get("metadata_path") or ""))
        hashes_path = Path(str(mirror_record.get("source_hashes_path") or ""))
        source_case_dir = prompt_path.parent
        source_reference_dir = Path(str(mirror_record.get("reference_files_dir") or ""))
        source_calibration_dir = source_case_dir / "calibration_only"

        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        metadata = self._read_json(metadata_path)
        source_hashes = self._read_json(hashes_path)
        if not prompt.strip():
            failures.append("missing or empty prompt")
        if not source_reference_dir.exists():
            failures.append("missing reference_files directory")

        reference_dir = case_dir / "reference_files"
        if reference_dir.exists():
            shutil.rmtree(reference_dir)
        ensure_dir(reference_dir)
        reference_files: List[str] = []
        if source_reference_dir.exists():
            for source_file in sorted(source_reference_dir.iterdir()):
                if source_file.is_file():
                    dst = reference_dir / source_file.name
                    shutil.copy2(source_file, dst)
                    reference_files.append(f"reference_files/{source_file.name}")
        if not reference_files:
            failures.append("no mirrored reference files available")

        calibration_dir = case_dir / "calibration_only"
        if calibration_dir.exists():
            shutil.rmtree(calibration_dir)
        ensure_dir(calibration_dir)
        rubric_json_path = source_calibration_dir / "rubric_json.json"
        rubric_pretty_path = source_calibration_dir / "rubric_pretty.txt"
        rubric_json = rubric_json_path.read_text(encoding="utf-8") if rubric_json_path.exists() else ""
        rubric_pretty = rubric_pretty_path.read_text(encoding="utf-8") if rubric_pretty_path.exists() else ""
        if rubric_json_path.exists():
            shutil.copy2(rubric_json_path, calibration_dir / "rubric_json.json")
        if rubric_pretty_path.exists():
            shutil.copy2(rubric_pretty_path, calibration_dir / "rubric_pretty.txt")
        if not rubric_json.strip() and not rubric_pretty.strip():
            failures.append("missing GDPVal rubric artifacts")

        copied_metadata_path = case_dir / "metadata.json"
        copied_hashes_path = case_dir / "source_hashes.json"
        self._write_json(copied_metadata_path, metadata)
        self._write_json(copied_hashes_path, source_hashes)

        expected_deliverables = list(metadata.get("deliverable_files") or [])
        dataset_row = {
            "task_id": task_id,
            "prompt": prompt,
            "reference_files": reference_files,
            "deliverable_files": [],
            "rubric_json": rubric_json,
            "rubric": rubric_pretty,
            "rubric_pretty": rubric_pretty,
            "extra": {
                "source": "openai/gdpval",
                "use": "eval_calibration_only",
                "diagnostic_only": True,
                "calibration_only": True,
                "not_for_training_generation": True,
                "gdpval_task_id": task_id,
                "selection_bucket": str(selection.get("selection_bucket") or ""),
                "selection_score": float(selection.get("selection_score") or 0.0),
                "selection_reasons": list(selection.get("selection_reasons") or []),
                "risk_notes": list(selection.get("risk_notes") or []),
                "sector": str(selection.get("sector") or ""),
                "occupation": str(selection.get("occupation") or ""),
                "expected_deliverable_files_metadata_only": expected_deliverables,
            },
        }
        dataset_row_path = case_dir / "dataset_row.json"
        self._write_json(dataset_row_path, dataset_row)

        case_manifest = {
            "manifest_version": "v3.gdpval_rw_task_case_manifest.1",
            "created_at": self._now(),
            "task_id": task_id,
            "case_slug": case_slug,
            "use": "eval_calibration_only",
            "diagnostic_only": True,
            "not_for_training_generation": True,
            "source_mirror_task_dir": str(source_case_dir),
            "dataset_row_path": "dataset_row.json",
            "reference_files": reference_files,
            "calibration_only_files": [
                str(path.relative_to(case_dir)).replace("\\", "/")
                for path in sorted(calibration_dir.iterdir())
                if path.is_file()
            ],
            "metadata_path": "metadata.json",
            "source_hashes_path": "source_hashes.json",
            "dataset_row_sha256": sha256_text(json.dumps(dataset_row, ensure_ascii=False, sort_keys=True)),
        }
        self._write_json(case_dir / "gdpval_case_manifest.json", case_manifest)

        return PreparedGDPValCase(
            task_id=task_id,
            case_slug=case_slug,
            case_dir=str(case_dir),
            dataset_row_path=str(dataset_row_path),
            reference_file_count=len(reference_files),
            deliverable_file_count=len(expected_deliverables),
            selection_bucket=str(selection.get("selection_bucket") or ""),
            selection_reasons=list(selection.get("selection_reasons") or []),
            prep_status="blocked" if failures else "prepared",
            failure_reasons=failures,
        )

    def _build_model_run(
        self,
        *,
        request: GDPValRwTaskEvalRequest,
        model: str,
        eval_input_dir: Path,
        model_runs_dir: Path,
        prepared_cases: List[PreparedGDPValCase],
    ) -> GDPValModelRunRecord:
        model_slug = slugify(model)
        run_root = ensure_dir(model_runs_dir / model_slug)
        output_dir = run_root / "results"
        grade_dir = run_root / "grades"
        logs_dir = run_root / "logs"
        ensure_dir(output_dir)
        ensure_dir(grade_dir)
        ensure_dir(logs_dir)
        command = [
            request.python_exe,
            "-m",
            "task_generator.v3_rw_task_stirrup_entrypoint",
            "--agent-max-tokens",
            str(request.agent_max_tokens),
            "--case-timeout-seconds",
            str(request.case_timeout_seconds),
            "--sandbox-timeout-seconds",
            str(request.sandbox_timeout_seconds),
            str(eval_input_dir),
            "--output",
            str(output_dir),
            "-w",
            str(request.workers),
            "--model",
            model,
        ]
        grade_command = [
            request.python_exe,
            "-m",
            "bench_standalone.grade_deliverables",
            str(output_dir),
            "--out-dir",
            str(grade_dir),
        ]
        task_results = [
            ModelTaskResult(
                task_id=case.task_id,
                case_slug=case.case_slug,
                prep_status=case.prep_status,
                completion_status="blocked" if case.prep_status == "blocked" else "not_run",
                failure_reasons=list(case.failure_reasons),
            )
            for case in prepared_cases
        ]
        return GDPValModelRunRecord(
            model=model,
            model_slug=model_slug,
            input_dir=str(eval_input_dir),
            output_dir=str(output_dir),
            grade_dir=str(grade_dir),
            logs_dir=str(logs_dir),
            command_preview=command,
            grade_command_preview=grade_command,
            task_results=task_results,
        )

    def _execute_model_run(
        self,
        *,
        request: GDPValRwTaskEvalRequest,
        record: GDPValModelRunRecord,
        output_dir: Path,
    ) -> None:
        record.command_executed = True
        env = self._build_subprocess_env(request)
        logs_dir = Path(record.logs_dir)
        stdout_log = logs_dir / "stirrup_batch.stdout.txt"
        stderr_log = logs_dir / "stirrup_batch.stderr.txt"
        record.stdout_log_path = str(stdout_log)
        record.stderr_log_path = str(stderr_log)
        run_result = self._run_command(
            record.command_preview,
            cwd=Path(request.rw_task_root),
            env=env,
            timeout=request.command_timeout_seconds,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
        )
        record.returncode = run_result["returncode"]
        if run_result["timeout"]:
            record.run_status = "timeout"
            record.completion_status = "failed"
            record.failure_reasons.append("stirrup_batch timed out")
        elif record.returncode == 0:
            record.run_status = "completed"
        else:
            record.run_status = "failed"
            record.completion_status = "failed"
            record.failure_reasons.append(f"stirrup_batch exited with code {record.returncode}")

        output_dataset_rows = list(Path(record.output_dir).rglob("dataset_row.json"))
        runnable_case_count = sum(1 for task in record.task_results if task.prep_status == "prepared")
        if record.run_status == "completed" and len(output_dataset_rows) < runnable_case_count:
            record.run_status = "partial_failed" if output_dataset_rows else "failed"
            record.failure_reasons.append(
                f"stirrup_batch produced {len(output_dataset_rows)} dataset_row.json files for "
                f"{runnable_case_count} prepared cases"
            )
        if not output_dataset_rows:
            record.grade_status = "missing"
            if record.completion_status == "not_run":
                record.completion_status = "failed"
            self._update_task_results_from_outputs(record)
            return

        grade_stdout = logs_dir / "grade_deliverables.stdout.txt"
        grade_stderr = logs_dir / "grade_deliverables.stderr.txt"
        record.grade_stdout_log_path = str(grade_stdout)
        record.grade_stderr_log_path = str(grade_stderr)
        grade_result = self._run_command(
            record.grade_command_preview,
            cwd=Path(request.rw_task_root),
            env=env,
            timeout=request.command_timeout_seconds,
            stdout_log=grade_stdout,
            stderr_log=grade_stderr,
        )
        record.grade_returncode = grade_result["returncode"]
        if grade_result["timeout"]:
            record.grade_status = "failed"
            record.completion_status = "failed"
            record.failure_reasons.append("grade_deliverables timed out")
        elif record.grade_returncode == 0:
            record.grade_status = "completed"
        else:
            record.grade_status = "failed"
            record.completion_status = "failed"
            record.failure_reasons.append(f"grade_deliverables exited with code {record.grade_returncode}")

        self._update_task_results_from_outputs(record)
        if record.run_status == "completed" and record.grade_status == "completed":
            failed_tasks = [task for task in record.task_results if task.completion_status != "completed"]
            record.completion_status = "partial_failed" if failed_tasks else "completed"
        if record.completion_status == "not_run":
            record.completion_status = "failed" if record.failure_reasons else "completed"

    def _update_task_results_from_outputs(self, record: GDPValModelRunRecord) -> None:
        grade_report = self._latest_grade_report(Path(record.grade_dir))
        grade_by_task: Dict[str, Dict[str, Any]] = {}
        if grade_report:
            report = self._read_json(grade_report)
            for sample in report.get("samples") or []:
                task_id = str(sample.get("task_id") or "")
                if task_id:
                    grade_by_task[task_id] = sample
        for task in record.task_results:
            if task.prep_status == "blocked":
                task.completion_status = "blocked"
                task.tool_failure = True
                continue
            run_output_dir = Path(record.output_dir) / f"run_{task.case_slug}"
            task.run_output_dir = str(run_output_dir)
            output_row_path = run_output_dir / "dataset_row.json"
            if output_row_path.exists():
                task.run_status = "completed"
            else:
                task.run_status = "failed" if record.run_status != "not_run" else "not_run"
                task.grade_status = "missing"
                task.completion_status = "failed" if record.run_status != "not_run" else "not_run"
                task.tool_failure = True
                task.failure_reasons.append("missing output dataset_row.json")
                continue
            sample = grade_by_task.get(task.task_id)
            if sample is None:
                task.grade_status = "missing" if record.grade_status == "completed" else record.grade_status
                task.completion_status = "failed" if record.run_status != "not_run" else "not_run"
                task.tool_failure = True
                task.failure_reasons.append("missing grading sample")
                continue
            task.grade_report_path = str(grade_report)
            if not sample.get("success"):
                task.grade_status = "failed"
                task.completion_status = "failed"
                task.tool_failure = True
                err = sample.get("error")
                if err:
                    task.failure_reasons.append(str(err))
                continue
            grading = sample.get("grading") or {}
            total = self._as_float(grading.get("total_score"))
            max_score = self._as_float(grading.get("max_possible_score"))
            task.total_score = total
            task.max_possible_score = max_score
            task.score_ratio = (total / max_score) if total is not None and max_score and max_score > 0 else None
            task.grade_status = "completed"
            task.completion_status = "completed" if record.run_status == "completed" else "failed"
            task.usable_for_gap_analysis = bool(task.score_ratio is not None and task.completion_status == "completed")
            task.tool_failure = task.completion_status != "completed"

    def _build_gap_profile(self, report: GDPValEvalCampaignReport) -> GDPValModelGapProfile:
        by_task: Dict[str, GapTaskRecord] = {}
        for case in report.prepared_cases:
            by_task[case.task_id] = GapTaskRecord(task_id=case.task_id, case_slug=case.case_slug)
            if case.prep_status == "blocked":
                by_task[case.task_id].failure_mode = "prep_blocked"
                by_task[case.task_id].failure_reasons.extend(case.failure_reasons)
        for run in report.model_runs:
            for task in run.task_results:
                record = by_task.setdefault(task.task_id, GapTaskRecord(task_id=task.task_id, case_slug=task.case_slug))
                record.model_scores[run.model] = task.score_ratio
                if task.failure_reasons:
                    record.failure_reasons.extend(f"{run.model}: {reason}" for reason in task.failure_reasons)
        for task in by_task.values():
            scores = [score for score in task.model_scores.values() if score is not None]
            if len(scores) >= 2:
                task.score_gap = max(scores) - min(scores)
                task.usable_for_gap_analysis = True
                task.failure_mode = "none"
            elif report.executed_model_count == 0:
                task.failure_mode = "not_executed"
            else:
                task.failure_mode = "insufficient_completed_scores"
        tasks = list(by_task.values())
        return GDPValModelGapProfile(
            created_at=self._now(),
            task_count=len(tasks),
            usable_task_count=sum(1 for task in tasks if task.usable_for_gap_analysis),
            models=[run.model for run in report.model_runs],
            tasks=tasks,
            notes=[
                "Score gaps are diagnostic only and should not be treated as production quality truth.",
                "A task is usable for gap analysis only after at least two model scores are available.",
            ],
        )

    def _build_failure_report(self, report: GDPValEvalCampaignReport) -> GDPValEvalFailureReport:
        failures: List[GDPValEvalFailureRecord] = []
        for case in report.prepared_cases:
            if case.failure_reasons:
                failures.append(
                    GDPValEvalFailureRecord(
                        task_id=case.task_id,
                        case_slug=case.case_slug,
                        failure_type="prep_blocked",
                        failure_reasons=case.failure_reasons,
                        related_path=case.case_dir,
                    )
                )
        for run in report.model_runs:
            if run.failure_reasons:
                failures.append(
                    GDPValEvalFailureRecord(
                        model=run.model,
                        failure_type="model_run_failure",
                        failure_reasons=run.failure_reasons,
                        related_path=run.output_dir,
                    )
                )
            for task in run.task_results:
                if task.failure_reasons:
                    failures.append(
                        GDPValEvalFailureRecord(
                            model=run.model,
                            task_id=task.task_id,
                            case_slug=task.case_slug,
                            failure_type="task_failure",
                            failure_reasons=task.failure_reasons,
                            related_path=task.run_output_dir,
                        )
                    )
        return GDPValEvalFailureReport(
            created_at=self._now(),
            failure_count=len(failures),
            failures=failures,
        )

    def _build_subprocess_env(self, request: GDPValRwTaskEvalRequest) -> Dict[str, str]:
        env = dict(os.environ)
        if request.env_path:
            env.update(self._load_env_file(Path(request.env_path)))
        if request.grader_model:
            env["GRADER_MODEL"] = request.grader_model
        rw_task_root = str(Path(request.rw_task_root).resolve())
        task_generator_src = str(Path(__file__).resolve().parents[1])
        existing = env.get("PYTHONPATH", "")
        pythonpath_parts = [task_generator_src, rw_task_root]
        if existing:
            pythonpath_parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        return env

    def _load_env_file(self, path: Path) -> Dict[str, str]:
        values: Dict[str, str] = {}
        if not path.exists():
            return values
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            if key:
                values[key] = value
        return values

    def _run_command(
        self,
        command: List[str],
        *,
        cwd: Path,
        env: Dict[str, str],
        timeout: int,
        stdout_log: Path,
        stderr_log: Path,
    ) -> Dict[str, Any]:
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        with stdout_log.open("w", encoding="utf-8") as stdout_fh, stderr_log.open("w", encoding="utf-8") as stderr_fh:
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(cwd),
                    env=env,
                    stdout=stdout_fh,
                    stderr=stderr_fh,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                return {"returncode": completed.returncode, "timeout": False}
            except subprocess.TimeoutExpired:
                return {"returncode": None, "timeout": True}

    def _latest_grade_report(self, grade_dir: Path) -> Optional[Path]:
        if not grade_dir.exists():
            return None
        reports = sorted(grade_dir.glob("eval_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return reports[0] if reports else None

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
