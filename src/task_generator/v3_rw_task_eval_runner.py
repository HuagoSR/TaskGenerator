import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_deliverable_contract import (
    DeliveryInspectionReport,
    contract_from_dataset_row,
    inspect_delivery,
)
from task_generator.v3_behavioral_validation import (
    BehavioralExecutionBuilder,
    BehavioralExecutionReportV1,
    SolverToolPreflightReportV1,
    write_behavioral_report,
)
from task_generator.v3_rw_task_eval_prep import RwTaskEvalPrepReport
from task_generator.v3_source_schema import load_json_file


EvalRunStatus = Literal["blocked", "dry_run_ready", "completed", "failed", "timeout", "partial_failed"]
CommandRunStatus = Literal["not_run", "succeeded", "failed", "timeout"]


class RwTaskEvalRunRequest(BaseModel):
    prep_report_path: str
    output_dir: str
    run_eval: bool = False
    allow_draft_eval: bool = False
    command_timeout_seconds: int = 0
    grader_model: Optional[str] = None
    solver_preflight_report_path: Optional[str] = None


class RwTaskEvalCommandRecord(BaseModel):
    command_index: int
    command: List[str]
    command_name: str = "unknown"
    status: CommandRunStatus = "not_run"
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    exit_code: Optional[int] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    timeout_seconds: int = 0
    failure_stage: Optional[str] = None
    cleanup_attempted: bool = False
    cleanup_note: str = ""


class RwTaskEvalOutputInspection(BaseModel):
    output_dir: str
    exists: bool = False
    file_count: int = 0
    sample_files: List[str] = Field(default_factory=list)


class RwTaskEvalRunReport(BaseModel):
    run_version: str = "v3.rw_task_eval_runner.2"
    request: RwTaskEvalRunRequest
    case_id: str = "unknown"
    batch_case_id: str = "unknown"
    blueprint_id: str = "unknown"
    rw_task_task_id: str = "unknown"
    evaluated_model_name: str = ""
    prep_status: str = "unknown"
    evaluation_mode: Optional[str] = None
    model: str = ""
    python_exe: str = ""
    rw_task_root: str = ""
    eval_input_case_dir: Optional[str] = None
    eval_results_dir: Optional[str] = None
    grade_output_dir: Optional[str] = None
    run_status: EvalRunStatus
    commands_executed: bool = False
    command_count: int = 0
    command_records: List[RwTaskEvalCommandRecord] = Field(default_factory=list)
    output_dirs: List[str] = Field(default_factory=list)
    output_inspections: List[RwTaskEvalOutputInspection] = Field(default_factory=list)
    delivery_inspection_path: Optional[str] = None
    delivery_status: Optional[str] = None
    expected_deliverable_count: int = 0
    valid_deliverable_count: int = 0
    behavioral_execution_report_path: Optional[str] = None
    behavioral_failure_category: Optional[str] = None
    grader_eligible: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RwTaskEvalRunner:
    """Guarded runner for rw-task smoke evaluation commands prepared by V3 Pipeline B."""

    def run(
        self,
        prep_report_path: str | Path,
        output_dir: str | Path,
        run_eval: bool = False,
        allow_draft_eval: bool = False,
        command_timeout_seconds: int = 0,
        grader_model: Optional[str] = None,
        solver_preflight_report_path: str | Path | None = None,
    ) -> RwTaskEvalRunReport:
        prep_path = Path(prep_report_path)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        request = RwTaskEvalRunRequest(
            prep_report_path=str(prep_path),
            output_dir=str(output_path),
            run_eval=run_eval,
            allow_draft_eval=allow_draft_eval,
            command_timeout_seconds=command_timeout_seconds,
            grader_model=grader_model,
            solver_preflight_report_path=(
                str(solver_preflight_report_path)
                if solver_preflight_report_path
                else None
            ),
        )
        blocking_reasons: List[str] = []
        warnings: List[str] = []
        prep_report: Optional[RwTaskEvalPrepReport] = None
        preflight_report: Optional[SolverToolPreflightReportV1] = None

        if not prep_path.exists():
            blocking_reasons.append("prep_report_missing")
        else:
            try:
                prep_report = RwTaskEvalPrepReport.model_validate(load_json_file(str(prep_path)))
            except Exception:
                blocking_reasons.append("prep_report_unreadable")

        if prep_report:
            warnings.extend(prep_report.warnings)
            if prep_report.prep_status != "prepared":
                blocking_reasons.append(f"prep_status:{prep_report.prep_status}")
            if not prep_report.would_run_commands:
                blocking_reasons.append("no_commands_to_run")
            if run_eval and prep_report.evaluation_mode == "draft_inspection_only" and not allow_draft_eval:
                blocking_reasons.append("allow_draft_eval_required")
            if run_eval:
                python_path = Path(prep_report.request.python_exe)
                if not python_path.exists():
                    blocking_reasons.append("python_exe_missing")
                eval_case_dir = Path(prep_report.eval_input_case_dir or "")
                if not eval_case_dir.exists():
                    blocking_reasons.append("eval_input_case_dir_missing")
            preflight_required = self._requires_solver_preflight(prep_report)
            if solver_preflight_report_path:
                try:
                    preflight_report = SolverToolPreflightReportV1.model_validate(
                        load_json_file(str(solver_preflight_report_path))
                    )
                except Exception:
                    blocking_reasons.append("solver_preflight_report_unreadable")
            if run_eval and preflight_required:
                if preflight_report is None:
                    blocking_reasons.append("solver_preflight_required")
                elif preflight_report.status != "pass":
                    blocking_reasons.append(
                        f"solver_preflight_status:{preflight_report.status}"
                    )
                elif not preflight_report.eligible_for_business_eval:
                    blocking_reasons.append("solver_preflight_not_business_eligible")
                elif preflight_report.solver_model != prep_report.request.model:
                    blocking_reasons.append("solver_preflight_model_mismatch")
        else:
            preflight_required = False

        command_records = self._initial_command_records(prep_report)
        output_dirs = self._output_dirs(prep_report)
        eval_results_dir = self._dir_for_flag(prep_report, "--output")
        grade_output_dir = self._dir_for_flag(prep_report, "--out-dir")
        output_inspections = self._inspect_output_dirs(output_dirs)
        notes = [
            "This runner consumes a prepared rw-task eval input report and records execution metadata.",
            "Dry-run mode does not call models, APIs, Stirrup, or rw-task evaluation.",
            "Draft inspection runs are toolchain smoke checks, not task-quality or model-separation evidence.",
            "Timeouts and command failures should still produce this report when they occur inside the runner timeout boundary.",
        ]

        if blocking_reasons:
            behavioral_report, behavioral_path = self._build_behavioral_report(
                output_path=output_path,
                prep_report=prep_report,
                command_records=command_records,
                delivery_inspection=None,
                delivery_inspection_path=None,
                preflight_report=preflight_report,
                preflight_report_path=solver_preflight_report_path,
                preflight_required=preflight_required,
            )
            report = self._report(
                request=request,
                prep_report=prep_report,
                run_status="blocked",
                commands_executed=False,
                command_records=command_records,
                output_dirs=output_dirs,
                eval_results_dir=eval_results_dir,
                grade_output_dir=grade_output_dir,
                output_inspections=output_inspections,
                blocking_reasons=blocking_reasons,
                warnings=warnings,
                notes=notes,
                behavioral_report=behavioral_report,
                behavioral_report_path=behavioral_path,
            )
            self.write_report(report, output_path / "rw_task_eval_run_report.json")
            return report

        if not run_eval:
            report = self._report(
                request=request,
                prep_report=prep_report,
                run_status="dry_run_ready",
                commands_executed=False,
                command_records=command_records,
                output_dirs=output_dirs,
                eval_results_dir=eval_results_dir,
                grade_output_dir=grade_output_dir,
                output_inspections=output_inspections,
                blocking_reasons=[],
                warnings=warnings,
                notes=notes,
            )
            self.write_report(report, output_path / "rw_task_eval_run_report.json")
            return report

        executed_records, delivery_inspection, delivery_inspection_path = self._execute_commands(
            commands=prep_report.would_run_commands if prep_report else [],
            output_dir=output_path,
            timeout_seconds=command_timeout_seconds,
            grading_model=grader_model or (prep_report.request.model if prep_report else ""),
            rw_task_root=prep_report.request.rw_task_root if prep_report else "",
            prep_report=prep_report,
        )
        output_inspections = self._inspect_output_dirs(output_dirs)
        run_status = self._run_status(executed_records)
        behavioral_report, behavioral_report_path = self._build_behavioral_report(
            output_path=output_path,
            prep_report=prep_report,
            command_records=executed_records,
            delivery_inspection=delivery_inspection,
            delivery_inspection_path=delivery_inspection_path,
            preflight_report=preflight_report,
            preflight_report_path=solver_preflight_report_path,
            preflight_required=preflight_required,
        )
        report = self._report(
            request=request,
            prep_report=prep_report,
            run_status=run_status,
            commands_executed=True,
            command_records=executed_records,
            output_dirs=output_dirs,
            eval_results_dir=eval_results_dir,
            grade_output_dir=grade_output_dir,
            output_inspections=output_inspections,
            blocking_reasons=[],
            warnings=warnings,
            notes=notes,
            delivery_inspection=delivery_inspection,
            delivery_inspection_path=delivery_inspection_path,
            behavioral_report=behavioral_report,
            behavioral_report_path=behavioral_report_path,
        )
        self.write_report(report, output_path / "rw_task_eval_run_report.json")
        return report

    def write_report(self, report: RwTaskEvalRunReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _report(
        self,
        request: RwTaskEvalRunRequest,
        prep_report: Optional[RwTaskEvalPrepReport],
        run_status: EvalRunStatus,
        commands_executed: bool,
        command_records: List[RwTaskEvalCommandRecord],
        output_dirs: List[str],
        eval_results_dir: Optional[str],
        grade_output_dir: Optional[str],
        output_inspections: List[RwTaskEvalOutputInspection],
        blocking_reasons: List[str],
        warnings: List[str],
        notes: List[str],
        delivery_inspection: Optional[DeliveryInspectionReport] = None,
        delivery_inspection_path: Optional[str] = None,
        behavioral_report: Optional[BehavioralExecutionReportV1] = None,
        behavioral_report_path: Optional[str] = None,
    ) -> RwTaskEvalRunReport:
        return RwTaskEvalRunReport(
            request=request,
            case_id=prep_report.case_id if prep_report else "unknown",
            batch_case_id=prep_report.batch_case_id if prep_report else "unknown",
            blueprint_id=prep_report.blueprint_id if prep_report else "unknown",
            rw_task_task_id=prep_report.rw_task_task_id if prep_report else "unknown",
            evaluated_model_name=prep_report.evaluated_model_name if prep_report else "",
            prep_status=prep_report.prep_status if prep_report else "unknown",
            evaluation_mode=prep_report.evaluation_mode if prep_report else None,
            model=prep_report.request.model if prep_report else "",
            python_exe=prep_report.request.python_exe if prep_report else "",
            rw_task_root=prep_report.request.rw_task_root if prep_report else "",
            eval_input_case_dir=prep_report.eval_input_case_dir if prep_report else None,
            eval_results_dir=eval_results_dir,
            grade_output_dir=grade_output_dir,
            run_status=run_status,
            commands_executed=commands_executed,
            command_count=len(command_records),
            command_records=command_records,
            output_dirs=output_dirs,
            output_inspections=output_inspections,
            delivery_inspection_path=delivery_inspection_path,
            delivery_status=delivery_inspection.delivery_status if delivery_inspection else None,
            expected_deliverable_count=delivery_inspection.expected_count if delivery_inspection else 0,
            valid_deliverable_count=delivery_inspection.valid_count if delivery_inspection else 0,
            behavioral_execution_report_path=behavioral_report_path,
            behavioral_failure_category=(
                behavioral_report.failure_category if behavioral_report else None
            ),
            grader_eligible=(
                behavioral_report.grader_eligible if behavioral_report else False
            ),
            blocking_reasons=sorted(set(blocking_reasons)),
            warnings=sorted(set(warnings)),
            notes=notes,
        )

    def _build_behavioral_report(
        self,
        *,
        output_path: Path,
        prep_report: Optional[RwTaskEvalPrepReport],
        command_records: List[RwTaskEvalCommandRecord],
        delivery_inspection: Optional[DeliveryInspectionReport],
        delivery_inspection_path: Optional[str],
        preflight_report: Optional[SolverToolPreflightReportV1],
        preflight_report_path: str | Path | None,
        preflight_required: bool,
    ) -> tuple[BehavioralExecutionReportV1, str]:
        solver_output = self._dir_for_flag(prep_report, "--output")
        report = BehavioralExecutionBuilder().build(
            case_id=prep_report.case_id if prep_report else "unknown",
            solver_model=prep_report.request.model if prep_report else "",
            environment_id=(
                preflight_report.environment_id
                if preflight_report
                else "not_evaluated"
            ),
            command_records=command_records,
            delivery_inspection=delivery_inspection,
            output_root=solver_output or output_path,
            input_package_root=(
                prep_report.eval_input_case_dir if prep_report else None
            ),
            preflight_report=preflight_report,
            preflight_report_path=(
                preflight_report_path
                if preflight_report_path
                else None
            ),
            preflight_required=preflight_required,
            delivery_inspection_path=delivery_inspection_path,
        )
        path = output_path / "behavioral_execution_report.json"
        write_behavioral_report(report, path)
        return report, str(path)

    def _requires_solver_preflight(
        self,
        prep_report: Optional[RwTaskEvalPrepReport],
    ) -> bool:
        if not prep_report or not prep_report.eval_input_case_dir:
            return False
        dataset_path = Path(prep_report.eval_input_case_dir) / "dataset_row.json"
        if not dataset_path.exists():
            return False
        try:
            dataset_row = load_json_file(str(dataset_path))
        except Exception:
            return False
        extra = dataset_row.get("extra") or {}
        route = str(extra.get("materialization_route") or "")
        return route.startswith("hybrid_") or bool(extra.get("behavioral_preflight_required"))

    def _initial_command_records(
        self,
        prep_report: Optional[RwTaskEvalPrepReport],
    ) -> List[RwTaskEvalCommandRecord]:
        if not prep_report:
            return []
        return [
            RwTaskEvalCommandRecord(
                command_index=index,
                command=command,
                command_name=self._command_name(command),
            )
            for index, command in enumerate(prep_report.would_run_commands, start=1)
        ]

    def _execute_commands(
        self,
        commands: List[List[str]],
        output_dir: Path,
        timeout_seconds: int,
        grading_model: str,
        rw_task_root: str,
        prep_report: Optional[RwTaskEvalPrepReport],
    ) -> tuple[List[RwTaskEvalCommandRecord], Optional[DeliveryInspectionReport], Optional[str]]:
        records: List[RwTaskEvalCommandRecord] = []
        log_dir = output_dir / "command_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timeout = timeout_seconds if timeout_seconds > 0 else None
        delivery_inspection: Optional[DeliveryInspectionReport] = None
        delivery_inspection_path: Optional[str] = None

        for index, command in enumerate(commands, start=1):
            started_at = self._now()
            status: CommandRunStatus = "failed"
            exit_code: Optional[int] = None
            stdout = ""
            stderr = ""
            failure_stage: Optional[str] = None
            cleanup_attempted = False
            cleanup_note = ""
            command_name = self._command_name(command)
            if command_name == "bench_standalone.grade_deliverables":
                delivery_inspection = self._inspect_expected_delivery(prep_report)
                delivery_path = output_dir / "delivery_inspection_report.json"
                delivery_path.write_text(
                    delivery_inspection.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                delivery_inspection_path = str(delivery_path)
                if delivery_inspection.delivery_status != "valid":
                    records.append(
                        RwTaskEvalCommandRecord(
                            command_index=index,
                            command=command,
                            command_name=command_name,
                            status="not_run",
                            started_at=started_at,
                            ended_at=self._now(),
                            timeout_seconds=timeout_seconds,
                            failure_stage="delivery_inspection",
                            stderr_excerpt=(
                                "Grading skipped because exact expected deliverables "
                                "were missing, invalid, wrongly named, or on the wrong path."
                            ),
                        )
                    )
                    break
            try:
                env = self._command_env(command, grading_model, rw_task_root)
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    env=env,
                    cwd=rw_task_root or None,
                )
                exit_code = completed.returncode
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
                status = "succeeded" if completed.returncode == 0 else "failed"
                if status == "failed":
                    failure_stage = command_name
            except subprocess.TimeoutExpired as exc:
                status = "timeout"
                stdout = self._decode_output(exc.stdout)
                stderr = self._decode_output(exc.stderr)
                failure_stage = command_name
                cleanup_attempted = True
                cleanup_note = "subprocess.run killed and waited for the timed-out command process"
            except Exception as exc:
                status = "failed"
                stderr = f"{type(exc).__name__}: {exc}"
                failure_stage = command_name
            ended_at = self._now()

            stdout_path = log_dir / f"command_{index:02d}_stdout.txt"
            stderr_path = log_dir / f"command_{index:02d}_stderr.txt"
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            records.append(
                RwTaskEvalCommandRecord(
                    command_index=index,
                    command=command,
                    command_name=command_name,
                    status=status,
                    started_at=started_at,
                    ended_at=ended_at,
                    exit_code=exit_code,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    stdout_excerpt=self._excerpt(stdout),
                    stderr_excerpt=self._excerpt(stderr),
                    timeout_seconds=timeout_seconds,
                    failure_stage=failure_stage,
                    cleanup_attempted=cleanup_attempted,
                    cleanup_note=cleanup_note,
                )
            )
            if status != "succeeded":
                break
        return records, delivery_inspection, delivery_inspection_path

    def _run_status(self, records: List[RwTaskEvalCommandRecord]) -> EvalRunStatus:
        if any(record.status == "timeout" for record in records):
            return "timeout"
        failed_records = [record for record in records if record.status == "failed"]
        if failed_records:
            succeeded_count = sum(1 for record in records if record.status == "succeeded")
            return "partial_failed" if succeeded_count else "failed"
        if any(record.status == "not_run" for record in records):
            return "partial_failed"
        return "completed"

    def _inspect_expected_delivery(
        self,
        prep_report: Optional[RwTaskEvalPrepReport],
    ) -> DeliveryInspectionReport:
        if not prep_report or not prep_report.eval_input_case_dir:
            raise ValueError("delivery_inspection_requires_prepared_case")
        case_dir = Path(prep_report.eval_input_case_dir)
        dataset_row = load_json_file(str(case_dir / "dataset_row.json"))
        contract = contract_from_dataset_row(
            dataset_row,
            case_dir / "deliverable_contract.json",
        )
        output_dir = self._dir_for_flag(prep_report, "--output")
        if not output_dir:
            raise ValueError("delivery_inspection_requires_solver_output")
        return inspect_delivery(output_dir, contract)

    def _command_env(self, command: List[str], grading_model: str, rw_task_root: str) -> dict[str, str]:
        env = dict(os.environ)
        command_name = self._command_name(command)
        repo_src = Path(__file__).resolve().parents[1]
        pythonpath_parts: List[str] = []
        if rw_task_root:
            env["RW_TASK_ROOT"] = rw_task_root
            pythonpath_parts.append(rw_task_root)
        if command_name in {
            "task_generator.v3_rw_task_eval_stirrup_wrapper",
            "task_generator.v3_rw_task_stirrup_entrypoint",
            "bench_standalone.grade_deliverables",
        }:
            pythonpath_parts.insert(0, str(repo_src))
        if command_name == "bench_standalone.grade_deliverables" and grading_model:
            env["GRADER_MODEL"] = grading_model
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        if pythonpath_parts:
            if existing_pythonpath:
                pythonpath_parts.append(existing_pythonpath)
            env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        return env

    def _output_dirs(self, prep_report: Optional[RwTaskEvalPrepReport]) -> List[str]:
        if not prep_report:
            return []
        output_dirs: List[str] = []
        for command in prep_report.would_run_commands:
            for index, part in enumerate(command):
                if part in {"--output", "--out-dir"} and index + 1 < len(command):
                    output_dirs.append(command[index + 1])
        return output_dirs

    def _dir_for_flag(
        self,
        prep_report: Optional[RwTaskEvalPrepReport],
        flag: str,
    ) -> Optional[str]:
        if not prep_report:
            return None
        for command in prep_report.would_run_commands:
            for index, part in enumerate(command):
                if part == flag and index + 1 < len(command):
                    return command[index + 1]
        return None

    def _inspect_output_dirs(self, output_dirs: List[str]) -> List[RwTaskEvalOutputInspection]:
        inspections: List[RwTaskEvalOutputInspection] = []
        for output_dir in output_dirs:
            path = Path(output_dir)
            sample_files: List[str] = []
            file_count = 0
            if path.exists():
                for child in path.rglob("*"):
                    if child.is_file():
                        file_count += 1
                        if len(sample_files) < 10:
                            sample_files.append(str(child))
            inspections.append(
                RwTaskEvalOutputInspection(
                    output_dir=str(path),
                    exists=path.exists(),
                    file_count=file_count,
                    sample_files=sample_files,
                )
            )
        return inspections

    def _command_name(self, command: List[str]) -> str:
        if "-m" in command:
            index = command.index("-m")
            if index + 1 < len(command):
                return command[index + 1]
        return Path(command[0]).name if command else "unknown"

    def _decode_output(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def _excerpt(self, text: str, limit: int = 1200) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[truncated]"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
