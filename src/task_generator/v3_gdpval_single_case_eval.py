from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_gdpval_rw_task_eval_adapter import (
    DEFAULT_GRADER_MODEL,
    DEFAULT_MODELS,
    GDPValEvalCampaignReport,
    GDPValRwTaskEvalAdapter,
    GDPValRwTaskEvalRequest,
    slugify,
)


SingleCaseMode = Literal["diagnose-existing", "prepare-regrade", "execute-regrade", "execute"]
ALLOWED_DELIVERABLE_SUFFIXES = {".xlsx", ".pptx", ".docx", ".pdf", ".csv"}
ARCHIVE_SUFFIXES = (".tar.gz", ".tgz")


class SingleCaseEvalRequest(BaseModel):
    run_id: str
    mode: SingleCaseMode
    task_id: Optional[str] = None
    case_index: Optional[int] = None
    source_run: Optional[str] = None
    output_dir: str
    subset_manifest_path: str
    models: List[str] = Field(default_factory=lambda: list(DEFAULT_MODELS))
    workers: int = 1
    rw_task_root: str
    python_exe: str
    env_path: Optional[str] = None
    overwrite: bool = False
    run_eval: bool = False
    command_timeout_seconds: int = 7200
    agent_max_tokens: int = 16000
    case_timeout_seconds: int = 7200
    sandbox_timeout_seconds: int = 3600
    grader_model: Optional[str] = DEFAULT_GRADER_MODEL


class ModelDeliverableDiagnostic(BaseModel):
    model: str
    model_slug: str
    task_id: str
    case_slug: str
    run_output_dir: str
    output_dataset_row_exists: bool
    listed_deliverable_count: int = 0
    physical_deliverable_count: int = 0
    accepted_deliverable_count: int = 0
    archive_deliverable_count: int = 0
    auxiliary_file_count: int = 0
    listed_deliverables: List[str] = Field(default_factory=list)
    accepted_deliverables: List[str] = Field(default_factory=list)
    auxiliary_files: List[str] = Field(default_factory=list)
    failure_modes: List[str] = Field(default_factory=list)
    regradeable: bool = False


class DeliverableDiagnosticReport(BaseModel):
    report_version: str = "v3.gdpval_single_case_deliverable_diagnostics.1"
    created_at: str
    source_run: str
    task_id: str
    case_slug: str
    diagnostics: List[ModelDeliverableDiagnostic]


class RegradeModelRecord(BaseModel):
    model: str
    model_slug: str
    input_dir: str
    grade_dir: str
    command_preview: List[str]
    command_executed: bool = False
    returncode: Optional[int] = None
    status: str = "not_run"
    grade_report_path: Optional[str] = None
    task_id: str
    score_ratio: Optional[float] = None
    total_score: Optional[float] = None
    max_possible_score: Optional[float] = None
    failure_reasons: List[str] = Field(default_factory=list)


class SanitizedRegradeReport(BaseModel):
    report_version: str = "v3.gdpval_sanitized_regrade.1"
    created_at: str
    task_id: str
    case_slug: str
    input_root: str
    model_records: List[RegradeModelRecord]


class SingleCaseGapProfile(BaseModel):
    profile_version: str = "v3.gdpval_single_case_gap_profile.1"
    created_at: str
    task_id: str
    case_slug: str
    model_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    score_gap: Optional[float] = None
    usable_for_gap_analysis: bool = False
    failure_reasons: List[str] = Field(default_factory=list)


class ContinueDecision(BaseModel):
    decision: str
    task_id: str
    case_slug: str
    reasons: List[str] = Field(default_factory=list)


class SingleCaseReport(BaseModel):
    report_version: str = "v3.gdpval_single_case_eval.1"
    created_at: str
    request: SingleCaseEvalRequest
    task_id: str
    case_slug: str
    raw_eval_dir: Optional[str] = None
    deliverable_diagnostic_report_path: str
    sanitized_regrade_report_path: str
    case_gap_profile_path: str
    continue_decision_path: str


class GDPValSingleCaseEvaluator:
    def run(self, request: SingleCaseEvalRequest) -> SingleCaseReport:
        output_dir = Path(request.output_dir).resolve()
        if request.overwrite and output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        task_id = self._resolve_task_id(request)
        case_slug = slugify(task_id)
        source_run = Path(request.source_run).resolve() if request.source_run else None
        raw_eval_dir: Optional[Path] = None

        if request.mode == "execute":
            raw_eval_dir = output_dir / "raw_eval"
            adapter_request = GDPValRwTaskEvalRequest(
                subset_manifest_path=request.subset_manifest_path,
                output_dir=str(raw_eval_dir),
                mode="execute",
                models=request.models,
                workers=request.workers,
                rw_task_root=request.rw_task_root,
                python_exe=request.python_exe,
                env_path=request.env_path,
                task_ids=[task_id],
                overwrite=True,
                command_timeout_seconds=request.command_timeout_seconds,
                run_eval=request.run_eval,
                agent_max_tokens=request.agent_max_tokens,
                case_timeout_seconds=request.case_timeout_seconds,
                sandbox_timeout_seconds=request.sandbox_timeout_seconds,
                grader_model=request.grader_model,
            )
            GDPValRwTaskEvalAdapter().run(adapter_request)
            source_run = raw_eval_dir

        if source_run is None:
            raise ValueError("--source-run is required unless --mode execute is used")

        diagnostics = self._diagnose_deliverables(
            source_run=source_run,
            task_id=task_id,
            case_slug=case_slug,
            models=request.models,
        )
        diagnostic_report = DeliverableDiagnosticReport(
            created_at=self._now(),
            source_run=str(source_run),
            task_id=task_id,
            case_slug=case_slug,
            diagnostics=diagnostics,
        )
        diagnostic_path = output_dir / "deliverable_diagnostic_report.json"
        self._write_json(diagnostic_path, diagnostic_report.model_dump(mode="json"))

        regrade_report = self._prepare_sanitized_regrade(
            source_run=source_run,
            output_dir=output_dir,
            task_id=task_id,
            case_slug=case_slug,
            diagnostics=diagnostics,
            request=request,
        )
        if request.mode in {"execute", "execute-regrade"}:
            self._execute_regrade(request=request, report=regrade_report, output_dir=output_dir)

        regrade_path = output_dir / "sanitized_regrade_report.json"
        self._write_json(regrade_path, regrade_report.model_dump(mode="json"))
        gap_profile = self._build_gap_profile(task_id=task_id, case_slug=case_slug, regrade_report=regrade_report)
        gap_path = output_dir / "case_gap_profile.json"
        self._write_json(gap_path, gap_profile.model_dump(mode="json"))
        decision = self._build_continue_decision(
            task_id=task_id,
            case_slug=case_slug,
            diagnostics=diagnostics,
            regrade_report=regrade_report,
            gap_profile=gap_profile,
        )
        decision_path = output_dir / "continue_decision.json"
        self._write_json(decision_path, decision.model_dump(mode="json"))

        report = SingleCaseReport(
            created_at=self._now(),
            request=request,
            task_id=task_id,
            case_slug=case_slug,
            raw_eval_dir=str(raw_eval_dir) if raw_eval_dir else str(source_run),
            deliverable_diagnostic_report_path=str(diagnostic_path),
            sanitized_regrade_report_path=str(regrade_path),
            case_gap_profile_path=str(gap_path),
            continue_decision_path=str(decision_path),
        )
        self._write_json(output_dir / "single_case_report.json", report.model_dump(mode="json"))
        return report

    def _resolve_task_id(self, request: SingleCaseEvalRequest) -> str:
        if request.task_id:
            return request.task_id
        subset_manifest = self._read_json(Path(request.subset_manifest_path))
        selected = list(subset_manifest.get("selected_records") or [])
        if not request.case_index or request.case_index < 1 or request.case_index > len(selected):
            raise ValueError("Provide --task-id or a valid 1-based --case-index")
        return str(selected[request.case_index - 1].get("task_id") or "")

    def _diagnose_deliverables(
        self,
        *,
        source_run: Path,
        task_id: str,
        case_slug: str,
        models: List[str],
    ) -> List[ModelDeliverableDiagnostic]:
        model_slugs = [slugify(model) for model in models]
        diagnostics: List[ModelDeliverableDiagnostic] = []
        for model, model_slug in zip(models, model_slugs):
            run_output_dir = source_run / "model_runs" / model_slug / "results" / f"run_{case_slug}"
            row_path = run_output_dir / "dataset_row.json"
            row = self._read_json(row_path)
            listed = [str(path) for path in row.get("deliverable_files") or []]
            accepted: List[str] = []
            auxiliary: List[str] = []
            archives: List[str] = []
            physical_count = 0
            for rel in listed:
                target = run_output_dir / rel
                if target.exists() and target.is_file():
                    physical_count += 1
                lower = rel.lower()
                if lower.endswith(ARCHIVE_SUFFIXES):
                    archives.append(rel)
                elif Path(rel).suffix.lower() in ALLOWED_DELIVERABLE_SUFFIXES:
                    accepted.append(rel)
                else:
                    auxiliary.append(rel)
            failure_modes: List[str] = []
            if not row_path.exists():
                failure_modes.append("missing_output_dataset_row")
            if not listed:
                failure_modes.append("no_listed_deliverables")
            if listed and physical_count == 0:
                failure_modes.append("listed_deliverables_missing_on_disk")
            if archives:
                failure_modes.append("archive_deliverable_requires_unpack")
            if auxiliary:
                failure_modes.append("auxiliary_files_listed_as_deliverables")
            diagnostics.append(
                ModelDeliverableDiagnostic(
                    model=model,
                    model_slug=model_slug,
                    task_id=task_id,
                    case_slug=case_slug,
                    run_output_dir=str(run_output_dir),
                    output_dataset_row_exists=row_path.exists(),
                    listed_deliverable_count=len(listed),
                    physical_deliverable_count=physical_count,
                    accepted_deliverable_count=len(accepted),
                    archive_deliverable_count=len(archives),
                    auxiliary_file_count=len(auxiliary),
                    listed_deliverables=listed,
                    accepted_deliverables=accepted,
                    auxiliary_files=auxiliary,
                    failure_modes=failure_modes,
                    regradeable=bool(row_path.exists() and (accepted or archives)),
                )
            )
        return diagnostics

    def _prepare_sanitized_regrade(
        self,
        *,
        source_run: Path,
        output_dir: Path,
        task_id: str,
        case_slug: str,
        diagnostics: List[ModelDeliverableDiagnostic],
        request: SingleCaseEvalRequest,
    ) -> SanitizedRegradeReport:
        input_root = output_dir / "sanitized_regrade" / "input"
        if input_root.exists():
            shutil.rmtree(input_root)
        input_root.mkdir(parents=True, exist_ok=True)
        records: List[RegradeModelRecord] = []
        for diagnostic in diagnostics:
            model_input_dir = input_root / diagnostic.model_slug
            sanitized_case_dir = model_input_dir / case_slug
            sanitized_case_dir.mkdir(parents=True, exist_ok=True)
            source_case_dir = Path(diagnostic.run_output_dir)
            source_row_path = source_case_dir / "dataset_row.json"
            failure_reasons: List[str] = []
            if not source_row_path.exists():
                failure_reasons.append("missing output dataset_row.json")
            else:
                self._copy_reference_files(source_case_dir, sanitized_case_dir)
                row = self._read_json(source_row_path)
                sanitized_deliverables = self._copy_sanitized_deliverables(
                    row=row,
                    source_case_dir=source_case_dir,
                    sanitized_case_dir=sanitized_case_dir,
                    failure_reasons=failure_reasons,
                )
                row["deliverable_files"] = sanitized_deliverables
                self._write_json(sanitized_case_dir / "dataset_row.json", row)
                if not sanitized_deliverables:
                    failure_reasons.append("no sanitized deliverables available")
            grade_dir = output_dir / "sanitized_regrade" / "grades" / diagnostic.model_slug
            command = [
                request.python_exe,
                "-m",
                "bench_standalone.grade_deliverables",
                str(model_input_dir),
                "--out-dir",
                str(grade_dir),
            ]
            records.append(
                RegradeModelRecord(
                    model=diagnostic.model,
                    model_slug=diagnostic.model_slug,
                    input_dir=str(model_input_dir),
                    grade_dir=str(grade_dir),
                    command_preview=command,
                    status="blocked" if failure_reasons else "prepared",
                    task_id=task_id,
                    failure_reasons=failure_reasons,
                )
            )
        return SanitizedRegradeReport(
            created_at=self._now(),
            task_id=task_id,
            case_slug=case_slug,
            input_root=str(input_root),
            model_records=records,
        )

    def _copy_reference_files(self, source_case_dir: Path, sanitized_case_dir: Path) -> None:
        source_ref = source_case_dir / "reference_files"
        if source_ref.exists():
            shutil.copytree(source_ref, sanitized_case_dir / "reference_files", dirs_exist_ok=True)

    def _copy_sanitized_deliverables(
        self,
        *,
        row: Dict[str, Any],
        source_case_dir: Path,
        sanitized_case_dir: Path,
        failure_reasons: List[str],
    ) -> List[str]:
        sanitized: List[str] = []
        for rel in [str(path) for path in row.get("deliverable_files") or []]:
            source = source_case_dir / rel
            if not source.is_file():
                failure_reasons.append(f"listed deliverable missing: {rel}")
                continue
            lower = rel.lower()
            if lower.endswith(ARCHIVE_SUFFIXES):
                sanitized.extend(self._unpack_archive(source=source, sanitized_case_dir=sanitized_case_dir))
                continue
            if source.suffix.lower() not in ALLOWED_DELIVERABLE_SUFFIXES:
                continue
            dst = sanitized_case_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dst)
            sanitized.append(rel.replace("\\", "/"))
        return sanitized

    def _unpack_archive(self, *, source: Path, sanitized_case_dir: Path) -> List[str]:
        unpacked: List[str] = []
        extract_dir = sanitized_case_dir / "deliverable_files" / f"extracted_{slugify(source.stem)}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(source, "r:*") as archive:
                archive.extractall(extract_dir)
        except (tarfile.TarError, OSError):
            return []
        for path in sorted(extract_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in ALLOWED_DELIVERABLE_SUFFIXES:
                unpacked.append(str(path.relative_to(sanitized_case_dir)).replace("\\", "/"))
        return unpacked

    def _execute_regrade(
        self,
        *,
        request: SingleCaseEvalRequest,
        report: SanitizedRegradeReport,
        output_dir: Path,
    ) -> None:
        env = self._build_subprocess_env(request)
        for record in report.model_records:
            if record.status == "blocked":
                continue
            record.command_executed = True
            grade_dir = Path(record.grade_dir)
            grade_dir.mkdir(parents=True, exist_ok=True)
            log_dir = output_dir / "sanitized_regrade" / "logs" / record.model_slug
            log_dir.mkdir(parents=True, exist_ok=True)
            stdout_log = log_dir / "grade_stdout.txt"
            stderr_log = log_dir / "grade_stderr.txt"
            result = self._run_command(
                record.command_preview,
                cwd=Path(request.rw_task_root),
                env=env,
                timeout=request.command_timeout_seconds,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
            record.returncode = result["returncode"]
            if result["timeout"]:
                record.status = "failed"
                record.failure_reasons.append("sanitized regrade timed out")
            elif record.returncode not in (0, None):
                record.status = "failed"
                record.failure_reasons.append(f"sanitized regrade exited with code {record.returncode}")
            else:
                record.status = "completed"
            self._read_regrade_score(record)

    def _read_regrade_score(self, record: RegradeModelRecord) -> None:
        grade_report = self._latest_grade_report(Path(record.grade_dir))
        if not grade_report:
            record.status = "failed"
            record.failure_reasons.append("missing sanitized grade report")
            return
        record.grade_report_path = str(grade_report)
        report = self._read_json(grade_report)
        samples = report.get("samples") or []
        sample = next((item for item in samples if str(item.get("task_id") or "") == record.task_id), None)
        if not sample:
            record.status = "failed"
            record.failure_reasons.append("missing sanitized grading sample")
            return
        if not sample.get("success"):
            record.status = "failed"
            if sample.get("error"):
                record.failure_reasons.append(str(sample.get("error")))
            return
        grading = sample.get("grading") or {}
        record.total_score = self._as_float(grading.get("total_score"))
        record.max_possible_score = self._as_float(grading.get("max_possible_score"))
        if record.total_score is not None and record.max_possible_score and record.max_possible_score > 0:
            record.score_ratio = record.total_score / record.max_possible_score
            record.status = "completed"
        else:
            record.status = "failed"
            record.failure_reasons.append("sanitized grading missing numeric score")

    def _build_gap_profile(
        self,
        *,
        task_id: str,
        case_slug: str,
        regrade_report: SanitizedRegradeReport,
    ) -> SingleCaseGapProfile:
        scores = {record.model: record.score_ratio for record in regrade_report.model_records}
        usable_scores = [score for score in scores.values() if score is not None]
        failures: List[str] = []
        for record in regrade_report.model_records:
            failures.extend(f"{record.model}: {reason}" for reason in record.failure_reasons)
        return SingleCaseGapProfile(
            created_at=self._now(),
            task_id=task_id,
            case_slug=case_slug,
            model_scores=scores,
            score_gap=(max(usable_scores) - min(usable_scores)) if len(usable_scores) >= 2 else None,
            usable_for_gap_analysis=len(usable_scores) >= 2,
            failure_reasons=failures,
        )

    def _build_continue_decision(
        self,
        *,
        task_id: str,
        case_slug: str,
        diagnostics: List[ModelDeliverableDiagnostic],
        regrade_report: SanitizedRegradeReport,
        gap_profile: SingleCaseGapProfile,
    ) -> ContinueDecision:
        reasons: List[str] = []
        if gap_profile.usable_for_gap_analysis:
            return ContinueDecision(
                decision="ready_for_next_case",
                task_id=task_id,
                case_slug=case_slug,
                reasons=["two or more sanitized model scores are available"],
            )
        no_deliverable = [item.model for item in diagnostics if item.listed_deliverable_count == 0]
        if no_deliverable:
            reasons.append("models without deliverables: " + ", ".join(no_deliverable))
            return ContinueDecision(
                decision="needs_model_rerun",
                task_id=task_id,
                case_slug=case_slug,
                reasons=reasons + gap_profile.failure_reasons,
            )
        failed_regrade = [record.model for record in regrade_report.model_records if record.status != "completed"]
        if failed_regrade:
            reasons.append("models with failed sanitized regrade: " + ", ".join(failed_regrade))
            return ContinueDecision(
                decision="needs_regrade",
                task_id=task_id,
                case_slug=case_slug,
                reasons=reasons + gap_profile.failure_reasons,
            )
        return ContinueDecision(
            decision="blocked",
            task_id=task_id,
            case_slug=case_slug,
            reasons=gap_profile.failure_reasons or ["insufficient completed scores"],
        )

    def _build_subprocess_env(self, request: SingleCaseEvalRequest) -> Dict[str, str]:
        env = dict(os.environ)
        if request.env_path:
            env.update(self._load_env_file(Path(request.env_path)))
        if request.grader_model:
            env["GRADER_MODEL"] = request.grader_model
        env.setdefault("GRADER_JSON_MAX_TOKENS", "16384")
        env.setdefault("GRADER_JSON_PARSE_ATTEMPTS", "5")
        env.setdefault("GRADER_MAX_RETRIES", "5")
        env.setdefault("GRADER_HTTP_TIMEOUT_S", "600")
        rw_task_root = str(Path(request.rw_task_root).resolve())
        task_generator_src = str(Path(__file__).resolve().parents[1])
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([task_generator_src, rw_task_root] + ([existing] if existing else []))
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
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            values[key.strip()] = value
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
