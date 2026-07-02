import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_rw_task_eval_prep import RwTaskEvalPrepReport
from task_generator.v3_source_schema import load_json_file


EvalRunStatus = Literal["blocked", "dry_run_ready", "completed", "failed"]
CommandRunStatus = Literal["not_run", "succeeded", "failed", "timeout"]


class RwTaskEvalRunRequest(BaseModel):
    prep_report_path: str
    output_dir: str
    run_eval: bool = False
    allow_draft_eval: bool = False
    command_timeout_seconds: int = 0


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


class RwTaskEvalRunReport(BaseModel):
    run_version: str = "v3.rw_task_eval_runner.1"
    request: RwTaskEvalRunRequest
    case_id: str = "unknown"
    prep_status: str = "unknown"
    evaluation_mode: Optional[str] = None
    model: str = ""
    python_exe: str = ""
    rw_task_root: str = ""
    eval_input_case_dir: Optional[str] = None
    run_status: EvalRunStatus
    commands_executed: bool = False
    command_count: int = 0
    command_records: List[RwTaskEvalCommandRecord] = Field(default_factory=list)
    output_dirs: List[str] = Field(default_factory=list)
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
        )
        blocking_reasons: List[str] = []
        warnings: List[str] = []
        prep_report: Optional[RwTaskEvalPrepReport] = None

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

        command_records = self._initial_command_records(prep_report)
        output_dirs = self._output_dirs(prep_report)
        notes = [
            "This runner consumes a prepared rw-task eval input report and records execution metadata.",
            "Dry-run mode does not call models, APIs, Stirrup, or rw-task evaluation.",
            "Draft inspection runs are toolchain smoke checks, not task-quality or model-separation evidence.",
        ]

        if blocking_reasons:
            report = self._report(
                request=request,
                prep_report=prep_report,
                run_status="blocked",
                commands_executed=False,
                command_records=command_records,
                output_dirs=output_dirs,
                blocking_reasons=blocking_reasons,
                warnings=warnings,
                notes=notes,
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
                blocking_reasons=[],
                warnings=warnings,
                notes=notes,
            )
            self.write_report(report, output_path / "rw_task_eval_run_report.json")
            return report

        executed_records = self._execute_commands(
            commands=prep_report.would_run_commands if prep_report else [],
            output_dir=output_path,
            timeout_seconds=command_timeout_seconds,
        )
        failed = any(record.status in {"failed", "timeout"} for record in executed_records)
        report = self._report(
            request=request,
            prep_report=prep_report,
            run_status="failed" if failed else "completed",
            commands_executed=True,
            command_records=executed_records,
            output_dirs=output_dirs,
            blocking_reasons=[],
            warnings=warnings,
            notes=notes,
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
        blocking_reasons: List[str],
        warnings: List[str],
        notes: List[str],
    ) -> RwTaskEvalRunReport:
        return RwTaskEvalRunReport(
            request=request,
            case_id=prep_report.case_id if prep_report else "unknown",
            prep_status=prep_report.prep_status if prep_report else "unknown",
            evaluation_mode=prep_report.evaluation_mode if prep_report else None,
            model=prep_report.request.model if prep_report else "",
            python_exe=prep_report.request.python_exe if prep_report else "",
            rw_task_root=prep_report.request.rw_task_root if prep_report else "",
            eval_input_case_dir=prep_report.eval_input_case_dir if prep_report else None,
            run_status=run_status,
            commands_executed=commands_executed,
            command_count=len(command_records),
            command_records=command_records,
            output_dirs=output_dirs,
            blocking_reasons=sorted(set(blocking_reasons)),
            warnings=sorted(set(warnings)),
            notes=notes,
        )

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
    ) -> List[RwTaskEvalCommandRecord]:
        records: List[RwTaskEvalCommandRecord] = []
        log_dir = output_dir / "command_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timeout = timeout_seconds if timeout_seconds > 0 else None

        for index, command in enumerate(commands, start=1):
            started_at = self._now()
            status: CommandRunStatus = "failed"
            exit_code: Optional[int] = None
            stdout = ""
            stderr = ""
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                exit_code = completed.returncode
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
                status = "succeeded" if completed.returncode == 0 else "failed"
            except subprocess.TimeoutExpired as exc:
                status = "timeout"
                stdout = self._decode_output(exc.stdout)
                stderr = self._decode_output(exc.stderr)
            except Exception as exc:
                status = "failed"
                stderr = f"{type(exc).__name__}: {exc}"
            ended_at = self._now()

            stdout_path = log_dir / f"command_{index:02d}_stdout.txt"
            stderr_path = log_dir / f"command_{index:02d}_stderr.txt"
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            records.append(
                RwTaskEvalCommandRecord(
                    command_index=index,
                    command=command,
                    command_name=self._command_name(command),
                    status=status,
                    started_at=started_at,
                    ended_at=ended_at,
                    exit_code=exit_code,
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    stdout_excerpt=self._excerpt(stdout),
                    stderr_excerpt=self._excerpt(stderr),
                )
            )
            if status != "succeeded":
                break
        return records

    def _output_dirs(self, prep_report: Optional[RwTaskEvalPrepReport]) -> List[str]:
        if not prep_report:
            return []
        output_dirs: List[str] = []
        for command in prep_report.would_run_commands:
            for index, part in enumerate(command):
                if part in {"--output", "--out-dir"} and index + 1 < len(command):
                    output_dirs.append(command[index + 1])
        return output_dirs

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
