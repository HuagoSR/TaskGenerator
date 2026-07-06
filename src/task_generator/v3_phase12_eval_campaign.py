from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_eval_orchestrator import EvalOrchestrator, EvalOrchestrationReport
from task_generator.v3_model_separation_profile import ModelSeparationProfile
from task_generator.v3_source_schema import load_json_file


CampaignStatus = Literal["ready", "partial", "blocked"]


class Phase12EvalCampaignRequest(BaseModel):
    batch_report_path: str
    output_dir: str
    models: List[str] = Field(default_factory=list)
    case_count: int = 3
    workers: int = 1
    rw_task_root: str
    python_exe: str
    run_eval: bool = False
    allow_draft_eval: bool = False
    overwrite: bool = False
    command_timeout_seconds: int = 1800


class Phase12EvalCaseSelection(BaseModel):
    case_id: str
    case_dir: str
    motif: str
    quality_decision: str
    verifier_status: str
    validation_status: str
    global_validity_status: str
    workflow_context_fit: Optional[str] = None
    real_worldness_score: Optional[float] = None


class Phase12EvalCampaignCaseResult(BaseModel):
    case_id: str
    motif: str
    case_dir: str
    orchestration_report_path: str
    model_separation_profile_path: Optional[str] = None
    execution_mode: str = "dry_run_only"
    model_count: int = 0
    run_completed_model_count: int = 0
    summarized_model_count: int = 0
    feedback_model_count: int = 0
    usable_summary_model_count: int = 0
    candidate_quality_model_count: int = 0
    draft_observation_model_count: int = 0
    reason_codes: List[str] = Field(default_factory=list)
    common_failure_modes: List[str] = Field(default_factory=list)
    discriminative_rubric_items: List[str] = Field(default_factory=list)
    format_noise_rubric_items: List[str] = Field(default_factory=list)
    score_range: Dict[str, Optional[float]] = Field(default_factory=dict)


class Phase12EvalCampaignSummary(BaseModel):
    selected_case_count: int = 0
    executed_case_count: int = 0
    model_count: int = 0
    total_model_runs: int = 0
    run_completed_model_count: int = 0
    summarized_model_count: int = 0
    usable_summary_model_count: int = 0
    feedback_model_count: int = 0
    candidate_quality_model_count: int = 0
    draft_observation_model_count: int = 0
    run_completion_rate: float = 0.0
    summary_completion_rate: float = 0.0
    usable_summary_rate: float = 0.0
    average_score_gap: Optional[float] = None
    campaign_status: CampaignStatus = "blocked"


class Phase12EvalCampaignReport(BaseModel):
    phase12_eval_campaign_version: str = "v1"
    request: Phase12EvalCampaignRequest
    selected_cases: List[Phase12EvalCaseSelection] = Field(default_factory=list)
    case_results: List[Phase12EvalCampaignCaseResult] = Field(default_factory=list)
    summary: Phase12EvalCampaignSummary
    notes: List[str] = Field(default_factory=list)


class Phase12EvalCampaignRunner:
    def run(
        self,
        batch_report_path: str | Path,
        output_dir: str | Path,
        models: List[str],
        case_count: int = 3,
        workers: int = 1,
        rw_task_root: str | Path = Path(r"E:\THU\2026Spring\SRT\rw-task"),
        python_exe: str | Path = Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
        run_eval: bool = False,
        allow_draft_eval: bool = False,
        overwrite: bool = False,
        command_timeout_seconds: int = 1800,
    ) -> Phase12EvalCampaignReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = Phase12EvalCampaignRequest(
            batch_report_path=str(batch_report_path),
            output_dir=str(output_path),
            models=models,
            case_count=case_count,
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
            run_eval=run_eval,
            allow_draft_eval=allow_draft_eval,
            overwrite=overwrite,
            command_timeout_seconds=command_timeout_seconds,
        )
        batch_payload = load_json_file(str(batch_report_path))
        selected_cases = self._select_cases(batch_payload, case_count)

        orchestrator = EvalOrchestrator()
        case_results: List[Phase12EvalCampaignCaseResult] = []
        score_gaps: List[float] = []
        for index, selection in enumerate(selected_cases, start=1):
            case_output_dir = output_path / f"case_{index:02d}_{selection.case_id}"
            report = orchestrator.orchestrate(
                case_dir=selection.case_dir,
                models=models,
                output_dir=case_output_dir,
                workers=workers,
                rw_task_root=rw_task_root,
                python_exe=python_exe,
                run_eval=run_eval,
                allow_draft_eval=allow_draft_eval,
                overwrite=overwrite,
                command_timeout_seconds=command_timeout_seconds,
            )
            profile = self._load_profile(report.model_separation_profile_path)
            score_values = [
                model.average_score_ratio
                for model in (profile.models if profile else [])
                if model.average_score_ratio is not None
            ]
            if len(score_values) >= 2:
                score_gaps.append(max(score_values) - min(score_values))
            case_results.append(
                Phase12EvalCampaignCaseResult(
                    case_id=selection.case_id,
                    motif=selection.motif,
                    case_dir=selection.case_dir,
                    orchestration_report_path=str(case_output_dir / "evaluation_orchestration_report.json"),
                    model_separation_profile_path=report.model_separation_profile_path,
                    execution_mode=report.execution_mode,
                    model_count=report.diagnostics.model_count,
                    run_completed_model_count=report.diagnostics.run_completed_model_count,
                    summarized_model_count=report.diagnostics.summarized_model_count,
                    feedback_model_count=report.diagnostics.feedback_model_count,
                    usable_summary_model_count=report.diagnostics.usable_summary_model_count,
                    candidate_quality_model_count=report.diagnostics.candidate_quality_model_count,
                    draft_observation_model_count=report.diagnostics.draft_observation_model_count,
                    reason_codes=list(report.diagnostics.reason_codes),
                    common_failure_modes=list(profile.common_failure_modes) if profile else [],
                    discriminative_rubric_items=list(profile.discriminative_rubric_items) if profile else [],
                    format_noise_rubric_items=list(profile.format_noise_rubric_items) if profile else [],
                    score_range={
                        "min": min(score_values) if score_values else None,
                        "max": max(score_values) if score_values else None,
                    },
                )
            )

        summary = self._summary(case_results, model_count=len(models), average_score_gap=score_gaps)
        report = Phase12EvalCampaignReport(
            request=request,
            selected_cases=selected_cases,
            case_results=case_results,
            summary=summary,
            notes=[
                "Phase 12 eval campaign remains diagnostic comparison evidence, not benchmark-grade model separation evidence.",
                "Selection is restricted to candidate_ready, verifier-pass, export-compatible cases from the supplied batch report.",
                "The orchestrator keeps evaluated_model_name and grader_model identity visible through downstream reports.",
            ],
        )
        (output_path / "phase12_eval_campaign_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _select_cases(
        self,
        batch_payload: Dict[str, object],
        case_count: int,
    ) -> List[Phase12EvalCaseSelection]:
        selected: List[Phase12EvalCaseSelection] = []
        for item in batch_payload.get("cases", []) or []:
            if item.get("quality_decision") != "candidate_ready":
                continue
            if item.get("verifier_status") != "pass":
                continue
            if item.get("validation_status") != "candidate_ready_compatible":
                continue
            if item.get("global_validity_status") not in {"diagnostic_only", "pass", None}:
                continue
            selected.append(
                Phase12EvalCaseSelection(
                    case_id=str(item.get("case_id") or "unknown"),
                    case_dir=str(item.get("case_dir") or ""),
                    motif=str(item.get("motif") or "unknown"),
                    quality_decision=str(item.get("quality_decision") or "unknown"),
                    verifier_status=str(item.get("verifier_status") or "unknown"),
                    validation_status=str(item.get("validation_status") or "unknown"),
                    global_validity_status=str(item.get("global_validity_status") or "unknown"),
                    workflow_context_fit=item.get("workflow_context_fit"),
                    real_worldness_score=item.get("real_worldness_score"),
                )
            )
            if len(selected) >= case_count:
                break
        return selected

    def _load_profile(self, path: Optional[str]) -> Optional[ModelSeparationProfile]:
        if not path:
            return None
        candidate = Path(path)
        if not candidate.exists():
            return None
        return ModelSeparationProfile.model_validate(load_json_file(str(candidate)))

    def _summary(
        self,
        case_results: List[Phase12EvalCampaignCaseResult],
        model_count: int,
        average_score_gap: List[float],
    ) -> Phase12EvalCampaignSummary:
        total_model_runs = len(case_results) * model_count
        run_completed = sum(item.run_completed_model_count for item in case_results)
        summarized = sum(item.summarized_model_count for item in case_results)
        usable = sum(item.usable_summary_model_count for item in case_results)
        feedback = sum(item.feedback_model_count for item in case_results)
        candidate_quality = sum(item.candidate_quality_model_count for item in case_results)
        draft_quality = sum(item.draft_observation_model_count for item in case_results)
        run_rate = (run_completed / total_model_runs) if total_model_runs else 0.0
        summary_rate = (summarized / total_model_runs) if total_model_runs else 0.0
        usable_rate = (usable / total_model_runs) if total_model_runs else 0.0
        status: CampaignStatus = "blocked"
        if case_results and summary_rate >= 0.8:
            status = "ready"
        elif case_results and summary_rate > 0:
            status = "partial"
        return Phase12EvalCampaignSummary(
            selected_case_count=len(case_results),
            executed_case_count=len(case_results),
            model_count=model_count,
            total_model_runs=total_model_runs,
            run_completed_model_count=run_completed,
            summarized_model_count=summarized,
            usable_summary_model_count=usable,
            feedback_model_count=feedback,
            candidate_quality_model_count=candidate_quality,
            draft_observation_model_count=draft_quality,
            run_completion_rate=round(run_rate, 4),
            summary_completion_rate=round(summary_rate, 4),
            usable_summary_rate=round(usable_rate, 4),
            average_score_gap=round(mean(average_score_gap), 4) if average_score_gap else None,
            campaign_status=status,
        )
