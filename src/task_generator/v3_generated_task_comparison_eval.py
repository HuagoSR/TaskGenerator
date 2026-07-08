from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_rw_task_eval_prep import (
    DEFAULT_REAL_WORLD_TASK_PYTHON,
    DEFAULT_RW_TASK_ROOT,
    RwTaskEvalPrep,
    RwTaskEvalPrepReport,
)
from task_generator.v3_rw_task_eval_runner import RwTaskEvalRunReport, RwTaskEvalRunner
from task_generator.v3_rw_task_export_validator import (
    RwTaskExportValidationReport,
    RwTaskExportValidator,
)


GeneratedComparisonMode = Literal["prepare", "dry-run", "execute"]
GeneratedComparisonStatus = Literal["prepared", "dry_run_ready", "completed", "blocked", "failed", "timeout", "partial_failed"]

DEFAULT_MODELS = ["gpt-5.4-pro", "gpt-4o-mini"]


class GeneratedTaskComparisonEvalRequest(BaseModel):
    comparison_plan_path: str
    output_dir: str
    mode: GeneratedComparisonMode = "dry-run"
    models: List[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))
    task_ids: List[str] = Field(default_factory=list)
    workers: int = 1
    rw_task_root: str = str(DEFAULT_RW_TASK_ROOT)
    python_exe: str = str(DEFAULT_REAL_WORLD_TASK_PYTHON)
    env_path: Optional[str] = None
    grader_model: str = "gpt-5.4-pro"
    agent_max_tokens: int = 16000
    case_timeout_seconds: int = 7200
    sandbox_timeout_seconds: int = 3600
    run_eval: bool = False
    overwrite: bool = False
    command_timeout_seconds: int = 0


class GeneratedTaskModelEvalRecord(BaseModel):
    task_id: str
    motif: str = ""
    model: str
    release_task_dir: str
    validation_report_path: str
    prep_report_path: str
    run_report_path: Optional[str] = None
    eval_input_dir: Optional[str] = None
    eval_results_dir: Optional[str] = None
    grade_output_dir: Optional[str] = None
    validation_status: str = "unknown"
    prep_status: str = "unknown"
    run_status: str = "not_run"
    completion_status: GeneratedComparisonStatus = "blocked"
    command_preview: List[List[str]] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True


class GeneratedTaskComparisonEvalReport(BaseModel):
    report_version: str = "v3.generated_task_comparison_eval.1"
    created_at: str
    request: GeneratedTaskComparisonEvalRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    selected_task_count: int
    model_count: int
    task_model_attempt_count: int
    prepared_count: int
    dry_run_ready_count: int
    completed_count: int
    blocked_count: int
    failed_count: int
    timeout_count: int
    records: List[GeneratedTaskModelEvalRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GeneratedTaskComparisonFailureReport(BaseModel):
    report_version: str = "v3.generated_task_comparison_failures.1"
    created_at: str
    diagnostic_only: bool = True
    failure_count: int
    failures: List[GeneratedTaskModelEvalRecord] = Field(default_factory=list)


class GeneratedTaskComparisonEval:
    """Prepare or run TaskGenerator release tasks through the diagnostic rw-task path."""

    def run(self, request: GeneratedTaskComparisonEvalRequest) -> GeneratedTaskComparisonEvalReport:
        output_dir = Path(request.output_dir)
        if request.overwrite and output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._load_env_into_process(request.env_path)

        plan = self._read_json(Path(request.comparison_plan_path))
        selected_tasks = self._selected_tasks(plan, request.task_ids)
        records: List[GeneratedTaskModelEvalRecord] = []

        for task in selected_tasks:
            for model in request.models:
                records.append(self._process_task_model(task, model, request, output_dir))

        report = GeneratedTaskComparisonEvalReport(
            created_at=self._now(),
            request=request,
            selected_task_count=len(selected_tasks),
            model_count=len(request.models),
            task_model_attempt_count=len(records),
            prepared_count=sum(1 for item in records if item.prep_status == "prepared"),
            dry_run_ready_count=sum(1 for item in records if item.run_status == "dry_run_ready"),
            completed_count=sum(1 for item in records if item.completion_status == "completed"),
            blocked_count=sum(1 for item in records if item.completion_status == "blocked"),
            failed_count=sum(1 for item in records if item.completion_status in {"failed", "partial_failed"}),
            timeout_count=sum(1 for item in records if item.completion_status == "timeout"),
            records=records,
            notes=[
                "This report prepares generated TaskGenerator release tasks for GDPVal diagnostic comparison.",
                "It is diagnostic-only and not benchmark-grade evidence.",
                "Dry-run mode prepares inputs and command previews but does not call models or external APIs.",
                "Generated-vs-GDPVal model-separation claims remain blocked until completed paired eval records exist.",
            ],
        )
        self._write_json(output_dir / "generated_task_comparison_eval_report.json", report.model_dump(mode="json"))
        failures = [record for record in records if record.completion_status in {"blocked", "failed", "partial_failed", "timeout"}]
        self._write_json(
            output_dir / "generated_task_comparison_failure_report.json",
            GeneratedTaskComparisonFailureReport(
                created_at=self._now(),
                failure_count=len(failures),
                failures=failures,
            ).model_dump(mode="json"),
        )
        self._write_json(output_dir / "generated_task_comparison_command_preview.json", self._command_preview(records))
        return report

    def _process_task_model(
        self,
        task: Dict[str, Any],
        model: str,
        request: GeneratedTaskComparisonEvalRequest,
        output_dir: Path,
    ) -> GeneratedTaskModelEvalRecord:
        task_id = str(task.get("task_id") or "")
        motif = str(task.get("motif") or "")
        task_dir = Path(str(task.get("release_task_dir") or ""))
        model_slug = self._slug(model)
        task_slug = self._slug(task_id)
        validation_path = output_dir / "validation_reports" / f"{task_slug}.rw_task_export_validation_report.json"
        eval_input_dir = output_dir / "eval_inputs" / model_slug / task_slug
        run_output_dir = output_dir / "model_runs" / model_slug / task_slug
        prep_report_path = eval_input_dir / "rw_task_eval_prep_report.json"

        validation_report: Optional[RwTaskExportValidationReport] = None
        prep_report: Optional[RwTaskEvalPrepReport] = None
        run_report: Optional[RwTaskEvalRunReport] = None
        blocking_reasons: List[str] = []
        warnings: List[str] = []

        if not task_dir.exists():
            blocking_reasons.append("release_task_dir_missing")
        else:
            validation_report = RwTaskExportValidator().validate(task_dir, output_path=validation_path)
            warnings.extend(
                finding.finding_id
                for finding in validation_report.findings
                if finding.severity == "warning" and not finding.passed
            )

        if validation_report and validation_report.validation_status == "invalid":
            blocking_reasons.append("validation_status:invalid")

        if not blocking_reasons:
            prep_report = RwTaskEvalPrep().prepare(
                case_dir=task_dir,
                validation_report_path=validation_path,
                eval_input_dir=eval_input_dir,
                model=model,
                workers=request.workers,
                rw_task_root=request.rw_task_root,
                python_exe=request.python_exe,
                overwrite=request.overwrite,
            )
            self._replace_with_stable_entrypoint_commands(prep_report, request)
            self._write_json(prep_report_path, prep_report.model_dump(mode="json"))
            warnings.extend(prep_report.warnings)
            blocking_reasons.extend(prep_report.blocking_reasons)

        if request.mode == "prepare" or blocking_reasons:
            return self._record(
                task=task,
                model=model,
                validation_path=validation_path,
                prep_report_path=prep_report_path,
                validation_report=validation_report,
                prep_report=prep_report,
                run_report=None,
                blocking_reasons=blocking_reasons,
                warnings=warnings,
                mode=request.mode,
            )

        run_report = RwTaskEvalRunner().run(
            prep_report_path=prep_report_path,
            output_dir=run_output_dir,
            run_eval=request.mode == "execute" and request.run_eval,
            allow_draft_eval=False,
            command_timeout_seconds=request.command_timeout_seconds,
            grader_model=request.grader_model,
        )
        blocking_reasons.extend(run_report.blocking_reasons)
        warnings.extend(run_report.warnings)
        return self._record(
            task=task,
            model=model,
            validation_path=validation_path,
            prep_report_path=prep_report_path,
            validation_report=validation_report,
            prep_report=prep_report,
            run_report=run_report,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            mode=request.mode,
        )

    def _replace_with_stable_entrypoint_commands(
        self,
        prep_report: RwTaskEvalPrepReport,
        request: GeneratedTaskComparisonEvalRequest,
    ) -> None:
        eval_input_dir = Path(prep_report.request.eval_input_dir).resolve()
        eval_output_dir = str(eval_input_dir) + "_results"
        grade_output_dir = str(eval_input_dir) + "_grades"
        prep_report.would_run_commands = [
            [
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
                eval_output_dir,
                "-w",
                str(request.workers),
                "--model",
                prep_report.request.model,
            ],
            [
                request.python_exe,
                "-m",
                "bench_standalone.grade_deliverables",
                eval_output_dir,
                "--out-dir",
                grade_output_dir,
            ],
        ]

    def _record(
        self,
        *,
        task: Dict[str, Any],
        model: str,
        validation_path: Path,
        prep_report_path: Path,
        validation_report: Optional[RwTaskExportValidationReport],
        prep_report: Optional[RwTaskEvalPrepReport],
        run_report: Optional[RwTaskEvalRunReport],
        blocking_reasons: List[str],
        warnings: List[str],
        mode: GeneratedComparisonMode,
    ) -> GeneratedTaskModelEvalRecord:
        run_status = run_report.run_status if run_report else ("not_run" if mode == "prepare" else "blocked")
        completion_status = self._completion_status(mode, blocking_reasons, run_report)
        return GeneratedTaskModelEvalRecord(
            task_id=str(task.get("task_id") or ""),
            motif=str(task.get("motif") or ""),
            model=model,
            release_task_dir=str(task.get("release_task_dir") or ""),
            validation_report_path=str(validation_path),
            prep_report_path=str(prep_report_path),
            run_report_path=str(Path(run_report.request.output_dir) / "rw_task_eval_run_report.json") if run_report else None,
            eval_input_dir=prep_report.request.eval_input_dir if prep_report else None,
            eval_results_dir=run_report.eval_results_dir if run_report else None,
            grade_output_dir=run_report.grade_output_dir if run_report else None,
            validation_status=validation_report.validation_status if validation_report else "unknown",
            prep_status=prep_report.prep_status if prep_report else "unknown",
            run_status=run_status,
            completion_status=completion_status,
            command_preview=prep_report.would_run_commands if prep_report else [],
            blocking_reasons=sorted(set(blocking_reasons)),
            warnings=sorted(set(warnings)),
        )

    def _completion_status(
        self,
        mode: GeneratedComparisonMode,
        blocking_reasons: List[str],
        run_report: Optional[RwTaskEvalRunReport],
    ) -> GeneratedComparisonStatus:
        if blocking_reasons:
            return "blocked"
        if mode == "prepare":
            return "prepared"
        if not run_report:
            return "blocked"
        if run_report.run_status == "dry_run_ready":
            return "dry_run_ready"
        if run_report.run_status in {"completed", "failed", "timeout", "partial_failed", "blocked"}:
            return run_report.run_status
        return "blocked"

    def _selected_tasks(self, plan: Dict[str, Any], task_ids: List[str]) -> List[Dict[str, Any]]:
        tasks = list(plan.get("selected_tasks") or [])
        if not task_ids:
            return tasks
        wanted = set(task_ids)
        return [task for task in tasks if str(task.get("task_id") or "") in wanted]

    def _command_preview(self, records: List[GeneratedTaskModelEvalRecord]) -> Dict[str, Any]:
        return {
            "report_version": "v3.generated_task_comparison_command_preview.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "commands": [
                {
                    "task_id": record.task_id,
                    "model": record.model,
                    "commands": record.command_preview,
                }
                for record in records
                if record.command_preview
            ],
        }

    def _load_env_into_process(self, env_path: Optional[str]) -> None:
        if not env_path:
            return
        path = Path(env_path)
        if not path.exists():
            return
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
                os.environ[key] = value

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _slug(self, value: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_") or "unknown"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
