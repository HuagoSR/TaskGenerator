import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_rw_task_export_validator import (
    RwTaskExportValidationReport,
)
from task_generator.v3_source_schema import load_json_file


PrepStatus = Literal["blocked", "prepared"]
EvaluationMode = Literal["draft_inspection_only", "candidate_ready_eval_candidate"]

DEFAULT_RW_TASK_ROOT = Path(r"E:\THU\2026Spring\SRT\rw-task")
DEFAULT_REAL_WORLD_TASK_PYTHON = Path(r"D:\miniconda3\envs\real-world-task\python.exe")


class RwTaskEvalPrepRequest(BaseModel):
    case_dir: str
    validation_report_path: str
    eval_input_dir: str
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str = str(DEFAULT_RW_TASK_ROOT)
    python_exe: str = str(DEFAULT_REAL_WORLD_TASK_PYTHON)
    overwrite: bool = False


class RwTaskEvalPrepReport(BaseModel):
    prep_version: str = "v3.rw_task_eval_prep.1"
    request: RwTaskEvalPrepRequest
    case_id: str = "unknown"
    batch_case_id: str = "unknown"
    blueprint_id: str = "unknown"
    rw_task_task_id: str = "unknown"
    evaluated_model_name: str = ""
    prep_status: PrepStatus
    evaluation_mode: Optional[EvaluationMode] = None
    eval_input_case_dir: Optional[str] = None
    reference_file_count: int = 0
    deliverable_file_count: int = 0
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    stirrup_max_tokens: Optional[int] = None
    would_run_commands: List[List[str]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RwTaskEvalPrep:
    """Prepare a validated rw-task-style export for later model-backed evaluation."""

    ALLOWED_VALIDATION_STATUSES = {"draft_compatible", "candidate_ready_compatible"}

    def prepare(
        self,
        case_dir: str | Path,
        eval_input_dir: str | Path,
        validation_report_path: str | Path | None = None,
        model: str = "gpt-5.4-pro",
        workers: int = 1,
        rw_task_root: str | Path = DEFAULT_RW_TASK_ROOT,
        python_exe: str | Path = DEFAULT_REAL_WORLD_TASK_PYTHON,
        overwrite: bool = False,
    ) -> RwTaskEvalPrepReport:
        case_path = Path(case_dir)
        validation_path = Path(validation_report_path) if validation_report_path else (
            case_path / "rw_task_export_validation_report.json"
        )
        eval_input_path = Path(eval_input_dir)
        rw_task_root_path = Path(rw_task_root)
        python_path = Path(python_exe)
        request = RwTaskEvalPrepRequest(
            case_dir=str(case_path),
            validation_report_path=str(validation_path),
            eval_input_dir=str(eval_input_path),
            model=model,
            workers=workers,
            rw_task_root=str(rw_task_root_path),
            python_exe=str(python_path),
            overwrite=overwrite,
        )

        blocking_reasons: List[str] = []
        warnings: List[str] = []
        validation_report: Optional[RwTaskExportValidationReport] = None
        dataset_row: Dict[str, Any] | None = None
        dataset_row_draft: Dict[str, Any] | None = None

        if not case_path.exists():
            blocking_reasons.append("case_dir_missing")
        if not validation_path.exists():
            blocking_reasons.append("validation_report_missing")
        else:
            try:
                validation_report = RwTaskExportValidationReport.model_validate(
                    load_json_file(str(validation_path))
                )
            except Exception:
                blocking_reasons.append("validation_report_unreadable")

        dataset_row_path = case_path / "dataset_row.json"
        if dataset_row_path.exists():
            try:
                dataset_row = load_json_file(str(dataset_row_path))
            except Exception:
                blocking_reasons.append("dataset_row_unreadable")
        else:
            blocking_reasons.append("dataset_row_missing")

        draft_path = case_path / "artifacts" / "dataset_row_draft.json"
        if draft_path.exists():
            try:
                dataset_row_draft = load_json_file(str(draft_path))
            except Exception:
                blocking_reasons.append("dataset_row_draft_unreadable")

        if validation_report and validation_report.validation_status not in self.ALLOWED_VALIDATION_STATUSES:
            blocking_reasons.append(f"validation_status:{validation_report.validation_status}")

        if eval_input_path.exists() and not overwrite:
            blocking_reasons.append("eval_input_dir_exists_without_overwrite")

        identity = self._identity(
            case_path=case_path,
            dataset_row=dataset_row,
            dataset_row_draft=dataset_row_draft,
            validation_report=validation_report,
        )
        case_id = identity["batch_case_id"]
        evaluation_mode = self._evaluation_mode(validation_report)
        warnings.extend(self._warnings_from_dataset_row(dataset_row))

        if validation_report and validation_report.validation_status == "draft_compatible":
            warnings.append("draft_only_case")

        would_run_commands = self._would_run_commands(
            eval_input_dir=eval_input_path,
            model=model,
            workers=workers,
            python_exe=python_path,
        )
        stirrup_max_tokens = self._stirrup_max_tokens(model)

        report = RwTaskEvalPrepReport(
            request=request,
            case_id=case_id,
            batch_case_id=identity["batch_case_id"],
            blueprint_id=identity["blueprint_id"],
            rw_task_task_id=identity["rw_task_task_id"],
            evaluated_model_name=model,
            prep_status="blocked" if blocking_reasons else "prepared",
            evaluation_mode=evaluation_mode if not blocking_reasons else evaluation_mode,
            eval_input_case_dir=str(eval_input_path / case_id) if not blocking_reasons else None,
            reference_file_count=len((dataset_row or {}).get("reference_files") or []),
            deliverable_file_count=len((dataset_row or {}).get("deliverable_files") or []),
            blocking_reasons=sorted(set(blocking_reasons)),
            warnings=sorted(set(warnings)),
            stirrup_max_tokens=stirrup_max_tokens,
            would_run_commands=would_run_commands,
            notes=[
                "This prep layer copies a validated case into a batch-style eval input directory.",
                "It previews future rw-task commands but does not run models, APIs, Stirrup, or evaluation.",
                "Draft-compatible cases remain inspection-only and are not promoted to final training data.",
            ],
        )

        if blocking_reasons:
            self._write_report(eval_input_path / "rw_task_eval_prep_report.json", report)
            return report

        if overwrite and eval_input_path.exists():
            shutil.rmtree(eval_input_path)
        eval_input_path.mkdir(parents=True, exist_ok=True)

        target_case_dir = eval_input_path / case_id
        shutil.copytree(case_path, target_case_dir)
        self._write_report(eval_input_path / "rw_task_eval_prep_report.json", report)
        return report

    def _evaluation_mode(
        self,
        validation_report: Optional[RwTaskExportValidationReport],
    ) -> Optional[EvaluationMode]:
        if not validation_report:
            return None
        if validation_report.validation_status == "candidate_ready_compatible":
            return "candidate_ready_eval_candidate"
        if validation_report.validation_status == "draft_compatible":
            return "draft_inspection_only"
        return None

    def _warnings_from_dataset_row(self, dataset_row: Dict[str, Any] | None) -> List[str]:
        if not dataset_row:
            return []
        extra = dataset_row.get("extra") or {}
        warnings = list(extra.get("quality_reason_codes") or [])
        if extra.get("not_final_training_data") is True:
            warnings.append("not_final_training_data")
        if extra.get("export_status"):
            warnings.append(f"export_status:{extra['export_status']}")
        return warnings

    def _would_run_commands(
        self,
        eval_input_dir: Path,
        model: str,
        workers: int,
        python_exe: Path,
    ) -> List[List[str]]:
        wrapper_module = "task_generator.v3_rw_task_eval_stirrup_wrapper"
        eval_output_dir = str(eval_input_dir) + "_results"
        grade_output_dir = str(eval_input_dir) + "_grades"
        return [
            [
                str(python_exe),
                "-m",
                wrapper_module,
                str(eval_input_dir),
                "--output",
                eval_output_dir,
                "-w",
                str(workers),
                "--model",
                model,
                "--max-tokens",
                str(self._stirrup_max_tokens(model)),
            ],
            [
                str(python_exe),
                "-m",
                "bench_standalone.grade_deliverables",
                eval_output_dir,
                "--out-dir",
                grade_output_dir,
            ],
        ]

    def _stirrup_max_tokens(self, model: str) -> int:
        normalized = (model or "").strip()
        if normalized == "gpt-4o-mini":
            return 16384
        return 64000

    def _identity(
        self,
        case_path: Path,
        dataset_row: Optional[Dict[str, Any]],
        dataset_row_draft: Optional[Dict[str, Any]],
        validation_report: Optional[RwTaskExportValidationReport],
    ) -> Dict[str, str]:
        dataset_row = dataset_row or {}
        dataset_row_draft = dataset_row_draft or {}
        extra = dataset_row.get("extra") or {}
        batch_case_id = str(
            dataset_row.get("task_id")
            or (validation_report.case_id if validation_report else "")
            or case_path.name
            or "unknown"
        )
        blueprint_id = str(
            extra.get("blueprint_id")
            or dataset_row_draft.get("task_id")
            or "unknown"
        )
        rw_task_task_id = str(
            dataset_row.get("task_id")
            or dataset_row_draft.get("task_id")
            or batch_case_id
        )
        return {
            "batch_case_id": batch_case_id,
            "blueprint_id": blueprint_id,
            "rw_task_task_id": rw_task_task_id,
        }

    def _write_report(self, output_path: Path, report: RwTaskEvalPrepReport) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
