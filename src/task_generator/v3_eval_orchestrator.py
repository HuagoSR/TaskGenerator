from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_model_separation_profile import ModelSeparationProfileBuilder
from task_generator.v3_pipeline_b_eval_feedback_analyzer import PipelineBEvalFeedbackAnalyzer
from task_generator.v3_rw_task_eval_prep import (
    DEFAULT_REAL_WORLD_TASK_PYTHON,
    DEFAULT_RW_TASK_ROOT,
    RwTaskEvalPrep,
    RwTaskEvalPrepReport,
)
from task_generator.v3_rw_task_eval_runner import RwTaskEvalRunner
from task_generator.v3_rw_task_eval_summarizer import RwTaskEvalSummarizer
from task_generator.v3_source_schema import load_json_file


ExecutionMode = Literal[
    "dry_run_only",
    "executed_with_draft_eval",
    "executed_candidate_ready_eval",
]
PlannedMode = Literal["dry_run", "execute"]


class EvalOrchestratorRequest(BaseModel):
    case_dir: Optional[str] = None
    validation_report_path: Optional[str] = None
    base_prep_report_path: Optional[str] = None
    models: List[str] = Field(default_factory=list)
    output_dir: str
    workers: int = 1
    rw_task_root: str = str(DEFAULT_RW_TASK_ROOT)
    python_exe: str = str(DEFAULT_REAL_WORLD_TASK_PYTHON)
    run_eval: bool = False
    allow_draft_eval: bool = False
    overwrite: bool = False
    command_timeout_seconds: int = 0


class EvalModelRunPlan(BaseModel):
    model_name: str
    model_slug: str
    eval_input_dir: str
    prep_output_path: str
    run_output_path: str
    summary_output_path: str
    feedback_output_path: str
    planned_mode: PlannedMode
    will_execute: bool = False


class EvalModelRunResult(BaseModel):
    model_name: str
    model_slug: str
    batch_case_id: str = "unknown"
    blueprint_id: str = "unknown"
    rw_task_task_id: str = "unknown"
    evaluated_model_name: str = ""
    prep_status: str = "unknown"
    run_status: str = "unknown"
    summary_status: str = "unknown"
    feedback_status: str = "skipped"
    evaluation_mode: Optional[str] = None
    evidence_use: Optional[str] = None
    average_score_ratio: Optional[float] = None
    grade_artifact_present: bool = False
    usable_for_model_separation: bool = False
    artifact_paths: Dict[str, str] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)


class EvalOrchestratorDiagnostics(BaseModel):
    model_count: int = 0
    prepared_model_count: int = 0
    executed_model_count: int = 0
    run_completed_model_count: int = 0
    summarized_model_count: int = 0
    grade_artifact_model_count: int = 0
    usable_summary_model_count: int = 0
    profile_input_model_count: int = 0
    feedback_model_count: int = 0
    candidate_quality_model_count: int = 0
    draft_observation_model_count: int = 0
    mixed_identity_warning: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class EvalOrchestrationReport(BaseModel):
    evaluation_orchestration_version: str = "v3.eval_orchestrator.1"
    request: EvalOrchestratorRequest
    batch_case_id: str = "unknown"
    blueprint_id: str = "unknown"
    rw_task_task_id: str = "unknown"
    execution_mode: ExecutionMode = "dry_run_only"
    model_run_plans: List[EvalModelRunPlan] = Field(default_factory=list)
    model_runs: List[EvalModelRunResult] = Field(default_factory=list)
    model_separation_profile_path: Optional[str] = None
    diagnostics: EvalOrchestratorDiagnostics
    notes: List[str] = Field(default_factory=list)


class _ResolvedEvalCase(BaseModel):
    batch_case_root: Optional[str] = None
    export_case_dir: str
    validation_report_path: str
    rubric_path: Optional[str] = None
    training_annotation_path: Optional[str] = None
    teacher_runner_report_path: Optional[str] = None
    quality_gate_report_path: Optional[str] = None
    task_verifier_report_path: Optional[str] = None
    global_validity_report_path: Optional[str] = None


class EvalOrchestrator:
    """Single-entry orchestration layer for multi-model evaluation evidence."""

    def __init__(self) -> None:
        self.prep = RwTaskEvalPrep()
        self.runner = RwTaskEvalRunner()
        self.summarizer = RwTaskEvalSummarizer()
        self.feedback_analyzer = PipelineBEvalFeedbackAnalyzer()
        self.model_separation_builder = ModelSeparationProfileBuilder()

    def orchestrate(
        self,
        output_dir: str | Path,
        models: List[str],
        case_dir: str | Path | None = None,
        validation_report_path: str | Path | None = None,
        base_prep_report_path: str | Path | None = None,
        workers: int = 1,
        rw_task_root: str | Path = DEFAULT_RW_TASK_ROOT,
        python_exe: str | Path = DEFAULT_REAL_WORLD_TASK_PYTHON,
        run_eval: bool = False,
        allow_draft_eval: bool = False,
        overwrite: bool = False,
        command_timeout_seconds: int = 0,
    ) -> EvalOrchestrationReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = EvalOrchestratorRequest(
            case_dir=str(case_dir) if case_dir else None,
            validation_report_path=str(validation_report_path) if validation_report_path else None,
            base_prep_report_path=str(base_prep_report_path) if base_prep_report_path else None,
            models=models,
            output_dir=str(output_path),
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
            run_eval=run_eval,
            allow_draft_eval=allow_draft_eval,
            overwrite=overwrite,
            command_timeout_seconds=command_timeout_seconds,
        )

        if not models:
            raise ValueError("At least one --model is required.")
        if not case_dir and not base_prep_report_path:
            raise ValueError("Provide either case_dir or base_prep_report_path.")

        resolved = self._resolve_case(case_dir=case_dir, validation_report_path=validation_report_path, base_prep_report_path=base_prep_report_path)
        plans = self._plans(models=models, output_dir=output_path, will_execute=run_eval)
        results: List[EvalModelRunResult] = []
        profile_input_summary_paths: List[Path] = []
        feedback_path: Optional[Path] = None

        for model_name, plan in zip(models, plans):
            result = self._run_one(
                resolved=resolved,
                model_name=model_name,
                plan=plan,
                workers=workers,
                rw_task_root=rw_task_root,
                python_exe=python_exe,
                run_eval=run_eval,
                allow_draft_eval=allow_draft_eval,
                overwrite=overwrite,
                command_timeout_seconds=command_timeout_seconds,
            )
            results.append(result)
            summary_path = Path(result.artifact_paths.get("summary_report_path") or "")
            if summary_path.exists() and result.summary_status == "summarized":
                profile_input_summary_paths.append(summary_path)
            if result.artifact_paths.get("feedback_report_path"):
                feedback_path = Path(result.artifact_paths["feedback_report_path"])

        diagnostics = self._diagnostics(results)
        profile_output_dir = output_path / "model_separation"
        profile_path: Optional[Path] = None
        if profile_input_summary_paths:
            self.model_separation_builder.build(
                eval_summary_report_paths=profile_input_summary_paths,
                eval_feedback_report_path=feedback_path if feedback_path and feedback_path.exists() else None,
                task_verifier_report_path=resolved.task_verifier_report_path,
                global_validity_report_path=resolved.global_validity_report_path,
                output_dir=profile_output_dir,
            )
            profile_path = profile_output_dir / "model_separation_profile.json"
        else:
            diagnostics.reason_codes = sorted(set(diagnostics.reason_codes + ["no_summarized_eval_evidence"]))
            diagnostics.notes.append(
                "No summarized evaluation evidence was available, so model separation profile generation was skipped."
            )
        report = EvalOrchestrationReport(
            request=request,
            batch_case_id=self._shared_identity(results, "batch_case_id"),
            blueprint_id=self._shared_identity(results, "blueprint_id"),
            rw_task_task_id=self._shared_identity(results, "rw_task_task_id"),
            execution_mode=self._execution_mode(results, run_eval),
            model_run_plans=plans,
            model_runs=results,
            model_separation_profile_path=str(profile_path) if profile_path and profile_path.exists() else None,
            diagnostics=diagnostics,
            notes=[
                "Evaluation Orchestrator V1 is executable but defaults to dry-run behavior unless run_eval is explicitly enabled.",
                "This orchestration layer does not mutate quality truth, registry state, dashboard state, or promotion state.",
                "Draft inspection evidence remains diagnostic and does not automatically become formal model-separation proof.",
            ],
        )
        self.write_report(report, output_path / "evaluation_orchestration_report.json")
        return report

    def write_report(self, report: EvalOrchestrationReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _resolve_case(
        self,
        case_dir: str | Path | None,
        validation_report_path: str | Path | None,
        base_prep_report_path: str | Path | None,
    ) -> _ResolvedEvalCase:
        if base_prep_report_path:
            prep_payload = RwTaskEvalPrepReport.model_validate(load_json_file(str(base_prep_report_path)))
            export_case_dir = Path(prep_payload.request.case_dir)
            validation_path = Path(prep_payload.request.validation_report_path)
        else:
            export_case_dir = self._resolve_export_case_dir(Path(case_dir))
            validation_path = Path(validation_report_path) if validation_report_path else (export_case_dir / "rw_task_export_validation_report.json")

        batch_case_root = self._resolve_batch_case_root(export_case_dir)
        return _ResolvedEvalCase(
            batch_case_root=str(batch_case_root) if batch_case_root else None,
            export_case_dir=str(export_case_dir),
            validation_report_path=str(validation_path),
            rubric_path=self._first_existing(
                export_case_dir / "artifacts" / "rubric.json",
                (batch_case_root / "rubric" / "rubric.json") if batch_case_root else None,
            ),
            training_annotation_path=self._first_existing(
                export_case_dir / "artifacts" / "training_annotation.json",
                (batch_case_root / "training_annotation" / "training_annotation.json") if batch_case_root else None,
            ),
            teacher_runner_report_path=self._first_existing(
                export_case_dir / "artifacts" / "teacher_runner_report.json",
                (batch_case_root / "teacher_runner" / "teacher_runner_report.json") if batch_case_root else None,
            ),
            quality_gate_report_path=self._first_existing(
                export_case_dir / "artifacts" / "pipeline_b_quality_report.json",
                (batch_case_root / "quality_gate" / "pipeline_b_quality_report.json") if batch_case_root else None,
            ),
            task_verifier_report_path=self._first_existing(
                (batch_case_root / "task_verifier" / "task_verifier_report.json") if batch_case_root else None,
            ),
            global_validity_report_path=self._first_existing(
                (batch_case_root / "global_validity" / "global_task_validity_report.json") if batch_case_root else None,
            ),
        )

    def _resolve_export_case_dir(self, case_dir: Path) -> Path:
        if (case_dir / "dataset_row.json").exists():
            return case_dir
        candidate = case_dir / "rw_task_export"
        if (candidate / "dataset_row.json").exists():
            return candidate
        raise ValueError(f"Could not resolve rw_task export case directory from: {case_dir}")

    def _resolve_batch_case_root(self, export_case_dir: Path) -> Optional[Path]:
        if export_case_dir.name == "rw_task_export":
            return export_case_dir.parent
        return None

    def _first_existing(self, *paths: Optional[Path]) -> Optional[str]:
        for path in paths:
            if path and path.exists():
                return str(path)
        return None

    def _plans(
        self,
        models: List[str],
        output_dir: Path,
        will_execute: bool,
    ) -> List[EvalModelRunPlan]:
        plans: List[EvalModelRunPlan] = []
        for model_name in models:
            model_slug = self._slug(model_name)
            model_dir = output_dir / "models" / model_slug
            plans.append(
                EvalModelRunPlan(
                    model_name=model_name,
                    model_slug=model_slug,
                    eval_input_dir=str(model_dir / "eval_input"),
                    prep_output_path=str(model_dir / "prep" / "rw_task_eval_prep_report.json"),
                    run_output_path=str(model_dir / "run" / "rw_task_eval_run_report.json"),
                    summary_output_path=str(model_dir / "summary" / "pipeline_b_eval_summary_report.json"),
                    feedback_output_path=str(model_dir / "feedback" / "pipeline_b_eval_feedback_report.json"),
                    planned_mode="execute" if will_execute else "dry_run",
                    will_execute=will_execute,
                )
            )
        return plans

    def _run_one(
        self,
        resolved: _ResolvedEvalCase,
        model_name: str,
        plan: EvalModelRunPlan,
        workers: int,
        rw_task_root: str | Path,
        python_exe: str | Path,
        run_eval: bool,
        allow_draft_eval: bool,
        overwrite: bool,
        command_timeout_seconds: int,
    ) -> EvalModelRunResult:
        model_dir = Path(plan.prep_output_path).parents[1]
        prep_dir = model_dir / "prep"
        run_dir = model_dir / "run"
        summary_dir = model_dir / "summary"
        feedback_dir = model_dir / "feedback"
        prep_report = self.prep.prepare(
            case_dir=resolved.export_case_dir,
            validation_report_path=resolved.validation_report_path,
            eval_input_dir=plan.eval_input_dir,
            model=model_name,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
            overwrite=overwrite,
        )
        self._copy_report(prep_dir / "rw_task_eval_prep_report.json", prep_report.model_dump_json(indent=2))

        run_report = self.runner.run(
            prep_report_path=prep_dir / "rw_task_eval_prep_report.json",
            output_dir=run_dir,
            run_eval=run_eval,
            allow_draft_eval=allow_draft_eval,
            command_timeout_seconds=command_timeout_seconds,
        )
        grade_dir = self._grade_dir(run_report)
        summary_report = self.summarizer.summarize(
            run_report_path=run_dir / "rw_task_eval_run_report.json",
            grade_dir=grade_dir,
            output_dir=summary_dir,
        )

        feedback_status = "skipped"
        feedback_report_path: Optional[str] = None
        feedback_warnings: List[str] = []
        feedback_blockers: List[str] = []
        if summary_report.summary_status == "summarized" and self._feedback_inputs_ready(resolved):
            feedback_report = self.feedback_analyzer.analyze(
                eval_summary_report_path=summary_dir / "pipeline_b_eval_summary_report.json",
                rubric_path=resolved.rubric_path,
                training_annotation_path=resolved.training_annotation_path,
                teacher_runner_report_path=resolved.teacher_runner_report_path,
                quality_gate_report_path=resolved.quality_gate_report_path,
                output_dir=feedback_dir,
            )
            feedback_status = feedback_report.feedback_status
            feedback_report_path = str(feedback_dir / "pipeline_b_eval_feedback_report.json")
            feedback_warnings = list(feedback_report.warning_reason_codes)
            feedback_blockers = list(feedback_report.blocking_reasons)
        elif summary_report.summary_status != "summarized":
            feedback_blockers.append("feedback_skipped_due_to_missing_summary")

        warnings = sorted(
            set(
                list(prep_report.warnings)
                + list(run_report.warnings)
                + list(summary_report.warning_reason_codes)
                + feedback_warnings
            )
        )
        blocking_reasons = sorted(
            set(
                list(prep_report.blocking_reasons)
                + list(run_report.blocking_reasons)
                + list(summary_report.blocking_reasons)
                + feedback_blockers
            )
        )
        return EvalModelRunResult(
            model_name=model_name,
            model_slug=plan.model_slug,
            batch_case_id=summary_report.batch_case_id,
            blueprint_id=summary_report.blueprint_id,
            rw_task_task_id=summary_report.rw_task_task_id,
            evaluated_model_name=summary_report.evaluated_model_name,
            prep_status=prep_report.prep_status,
            run_status=run_report.run_status,
            summary_status=summary_report.summary_status,
            feedback_status=feedback_status,
            evaluation_mode=summary_report.evaluation_mode,
            evidence_use=summary_report.evidence_use,
            average_score_ratio=summary_report.average_score_ratio,
            grade_artifact_present=summary_report.grade_artifact_present,
            usable_for_model_separation=summary_report.usable_for_model_separation,
            artifact_paths={
                "prep_report_path": str(prep_dir / "rw_task_eval_prep_report.json"),
                "run_report_path": str(run_dir / "rw_task_eval_run_report.json"),
                "summary_report_path": str(summary_dir / "pipeline_b_eval_summary_report.json"),
                "feedback_report_path": feedback_report_path or "",
            },
            warnings=warnings,
            blocking_reasons=blocking_reasons,
        )

    def _copy_report(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _grade_dir(self, run_report: Any) -> Optional[str]:
        return getattr(run_report, "grade_output_dir", None)

    def _feedback_inputs_ready(self, resolved: _ResolvedEvalCase) -> bool:
        return all(
            [
                resolved.rubric_path,
                resolved.training_annotation_path,
                resolved.teacher_runner_report_path,
                resolved.quality_gate_report_path,
            ]
        )

    def _execution_mode(self, results: List[EvalModelRunResult], run_eval: bool) -> ExecutionMode:
        if not run_eval:
            return "dry_run_only"
        if any(result.evaluation_mode == "candidate_ready_eval_candidate" for result in results):
            return "executed_candidate_ready_eval"
        return "executed_with_draft_eval"

    def _shared_identity(self, results: List[EvalModelRunResult], field_name: str) -> str:
        values = sorted({str(getattr(result, field_name) or "unknown") for result in results if getattr(result, field_name, None)})
        if not values:
            return "unknown"
        return values[0]

    def _diagnostics(self, results: List[EvalModelRunResult]) -> EvalOrchestratorDiagnostics:
        reason_codes = sorted(
            {
                item
                for result in results
                for item in result.blocking_reasons + result.warnings
            }
        )
        identities = {
            (
                result.batch_case_id,
                result.blueprint_id,
                result.rw_task_task_id,
            )
            for result in results
        }
        return EvalOrchestratorDiagnostics(
            model_count=len(results),
            prepared_model_count=sum(1 for result in results if result.prep_status == "prepared"),
            executed_model_count=sum(1 for result in results if result.run_status not in {"dry_run_ready", "blocked", "unknown"}),
            run_completed_model_count=sum(1 for result in results if result.run_status == "completed"),
            summarized_model_count=sum(1 for result in results if result.summary_status == "summarized"),
            grade_artifact_model_count=sum(1 for result in results if result.grade_artifact_present),
            usable_summary_model_count=sum(1 for result in results if result.usable_for_model_separation),
            profile_input_model_count=sum(1 for result in results if result.summary_status == "summarized"),
            feedback_model_count=sum(1 for result in results if result.feedback_status == "analyzed"),
            candidate_quality_model_count=sum(
                1 for result in results if result.evidence_use == "candidate_quality_evidence"
            ),
            draft_observation_model_count=sum(
                1 for result in results if result.evidence_use == "draft_quality_observation"
            ),
            mixed_identity_warning=len(identities) > 1,
            reason_codes=self._diagnostic_reason_codes(results, reason_codes),
            notes=[
                "Eval orchestrator keeps one model -> one workspace and never shares eval result directories across models.",
                "Mixed identity warnings indicate that compared model runs do not agree on batch case, blueprint, or rw-task task ids.",
                "Blocked summaries stay visible in orchestration diagnostics but are excluded from model separation profile intake.",
            ],
        )

    def _diagnostic_reason_codes(
        self,
        results: List[EvalModelRunResult],
        base_reason_codes: List[str],
    ) -> List[str]:
        codes = set(base_reason_codes)
        if any(result.run_status == "completed" and not result.grade_artifact_present for result in results):
            codes.add("grade_artifact_missing_after_run")
        if any(result.run_status == "completed" and result.summary_status == "blocked" for result in results):
            codes.add("summary_blocked_after_run")
        if any(
            result.feedback_status == "skipped" and result.summary_status != "summarized"
            for result in results
        ):
            codes.add("feedback_skipped_due_to_missing_summary")
        return sorted(codes)

    def _slug(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
        return cleaned or "model"
