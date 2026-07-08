from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file

if TYPE_CHECKING:
    from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunReport


ProductionRunMode = Literal["dry_run", "candidate_run", "production_run"]
ProductionTaskState = Literal[
    "generated",
    "structurally_valid",
    "verifier_passed",
    "candidate_ready",
    "production_candidate",
    "training_pool_candidate",
    "diagnostic_eval_sampled",
    "released",
    "deprecated",
]


class ProductionBatchRequest(BaseModel):
    production_batch_id: str
    mode: ProductionRunMode
    registry_path: str
    seed_report_path: str
    workflow_asset_path: Optional[str] = None
    motif_grammar_path: Optional[str] = None
    phase15_reform_spec_path: Optional[str] = None
    output_dir: str
    domain_scope: str = "finance_audit"
    file_type_scope: List[str] = Field(default_factory=lambda: ["xlsx", "docx", "md", "txt"])
    max_cases: int = 30
    skill_count: int = 4
    motifs: List[str] = Field(default_factory=list)
    allow_caution: bool = False
    workflow_archetype: Optional[str] = None
    target_difficulty_profile: Optional[str] = None
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str
    python_exe: str
    selection_policy: str = "deterministic_pipeline_b_batch_v1"


class ProductionCaseRecord(BaseModel):
    case_id: str
    motif: str
    case_dir: str
    batch_status: str
    task_state: ProductionTaskState
    blueprint_id: Optional[str] = None
    subgraph_id: Optional[str] = None
    template_family: Optional[str] = None
    deliverable_file_names: List[str] = Field(default_factory=list)
    selected_skill_ids: List[str] = Field(default_factory=list)
    quality_decision: Optional[str] = None
    verifier_status: Optional[str] = None
    validation_status: Optional[str] = None
    global_validity_status: Optional[str] = None
    real_worldness_score: Optional[float] = None
    difficulty_overall: Optional[float] = None
    workflow_context_fit: Optional[str] = None
    package_readiness: Optional[str] = None
    production_candidate_eligible: bool = False
    training_pool_candidate_eligible: bool = False
    diagnostic_eval_recommended: bool = False
    blocker_reason_codes: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ProductionBatchSummary(BaseModel):
    planned_case_count: int = 0
    executed_case_count: int = 0
    completed_case_count: int = 0
    failed_case_count: int = 0
    candidate_ready_count: int = 0
    production_candidate_eligible_count: int = 0
    training_pool_candidate_eligible_count: int = 0
    diagnostic_eval_recommended_count: int = 0
    task_state_counts: Dict[str, int] = Field(default_factory=dict)
    motif_counts: Dict[str, int] = Field(default_factory=dict)
    batch_warning_counts: Dict[str, int] = Field(default_factory=dict)


class ProductionBatchManifest(BaseModel):
    production_batch_manifest_version: str = "v3.production_batch_manifest.1"
    request: ProductionBatchRequest
    created_at: str
    code_commit: Optional[str] = None
    registry_version: Optional[str] = None
    workflow_asset_version: Optional[str] = None
    motif_grammar_version: Optional[str] = None
    sampler_policy_version: str = "role_filling_v1"
    promotion_state: str = "report_first_phase13_shell"
    execution_status: Literal["planned_only", "executed"] = "planned_only"
    cases: List[ProductionCaseRecord] = Field(default_factory=list)
    summary: ProductionBatchSummary
    output_paths: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class ProductionBatchRunnerArtifact(BaseModel):
    manifest_path: str
    summary_report_path: str
    batch_report_path: Optional[str] = None
    manifest: ProductionBatchManifest


class ProductionBatchRunner:
    def run(
        self,
        production_batch_id: str,
        mode: ProductionRunMode,
        registry_path: str | Path,
        seed_report_path: str | Path,
        output_dir: str | Path,
        workflow_asset_path: str | Path | None = None,
        motif_grammar_path: str | Path | None = None,
        phase15_reform_spec_path: str | Path | None = None,
        domain_scope: str = "finance_audit",
        file_type_scope: Optional[List[str]] = None,
        motifs: Optional[List[str]] = None,
        skill_count: int = 4,
        max_cases: int = 30,
        allow_caution: bool = False,
        workflow_archetype: Optional[str] = None,
        target_difficulty_profile: Optional[str] = None,
        model: str = "gpt-5.4-pro",
        workers: int = 1,
        rw_task_root: str | Path = Path(r"E:\THU\2026Spring\SRT\rw-task"),
        python_exe: str | Path = Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
    ) -> ProductionBatchRunnerArtifact:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        batch_output_dir = output_path / "batch"
        manifest_path = output_path / "production_batch_manifest.json"
        summary_path = output_path / "production_batch_summary_report.json"
        request = ProductionBatchRequest(
            production_batch_id=production_batch_id,
            mode=mode,
            registry_path=str(registry_path),
            seed_report_path=str(seed_report_path),
            workflow_asset_path=str(workflow_asset_path) if workflow_asset_path else None,
            motif_grammar_path=str(motif_grammar_path) if motif_grammar_path else None,
            phase15_reform_spec_path=str(phase15_reform_spec_path) if phase15_reform_spec_path else None,
            output_dir=str(output_path),
            domain_scope=domain_scope,
            file_type_scope=file_type_scope or ["xlsx", "docx", "md", "txt"],
            max_cases=max_cases,
            skill_count=skill_count,
            motifs=list(motifs or []),
            allow_caution=allow_caution,
            workflow_archetype=workflow_archetype,
            target_difficulty_profile=target_difficulty_profile,
            model=model,
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
        )

        registry_payload = self._safe_load_json(registry_path)
        workflow_payload = self._safe_load_json(workflow_asset_path) if workflow_asset_path else {}
        grammar_payload = self._safe_load_json(motif_grammar_path) if motif_grammar_path else {}
        created_at = datetime.now(timezone.utc).isoformat()
        code_commit = self._git_commit(output_path)

        execution_status: Literal["planned_only", "executed"] = "planned_only"
        batch_report_path: Optional[str] = None
        batch_report: Optional["PipelineBBatchRunReport"] = None

        if mode != "dry_run":
            from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunner

            execution_status = "executed"
            batch_report = PipelineBBatchRunner().run(
                registry_path=registry_path,
                seed_report_path=seed_report_path,
                output_dir=batch_output_dir,
                motifs=motifs,
                skill_count=skill_count,
                max_cases=max_cases,
                allow_caution=allow_caution,
                workflow_archetype=workflow_archetype,
                motif_grammar_path=motif_grammar_path,
                phase15_reform_spec_path=phase15_reform_spec_path,
                target_difficulty_profile=target_difficulty_profile,
                model=model,
                workers=workers,
                rw_task_root=rw_task_root,
                python_exe=python_exe,
            )
            batch_report_path = str(batch_output_dir / "pipeline_b_batch_report.json")

        cases = self._case_records(batch_report, mode)
        summary = self._summary(cases, request, batch_report)
        manifest = ProductionBatchManifest(
            request=request,
            created_at=created_at,
            code_commit=code_commit,
            registry_version=self._registry_version(registry_payload),
            workflow_asset_version=self._workflow_asset_version(workflow_payload),
            motif_grammar_version=self._motif_grammar_version(grammar_payload),
            execution_status=execution_status,
            cases=cases,
            summary=summary,
            output_paths={
                "manifest_path": str(manifest_path),
                "summary_report_path": str(summary_path),
                "batch_output_dir": str(batch_output_dir),
                "batch_report_path": batch_report_path or "",
            },
            notes=[
                "Phase 13 shell keeps the existing deterministic Pipeline B batch runner intact and adds production-facing manifest metadata.",
                "The current shell auto-assigns states through candidate_ready only.",
                "production_candidate and downstream states remain governed until a dedicated production QA gate exists.",
            ],
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        return ProductionBatchRunnerArtifact(
            manifest_path=str(manifest_path),
            summary_report_path=str(summary_path),
            batch_report_path=batch_report_path,
            manifest=manifest,
        )

    def _case_records(
        self,
        batch_report: Optional["PipelineBBatchRunReport"],
        mode: ProductionRunMode,
    ) -> List[ProductionCaseRecord]:
        if batch_report is None:
            return []
        records: List[ProductionCaseRecord] = []
        for case in batch_report.cases:
            task_state = self._task_state(case)
            candidate_ready = task_state == "candidate_ready"
            production_candidate_eligible = candidate_ready
            training_pool_candidate_eligible = candidate_ready and case.verifier_status == "pass"
            diagnostic_eval_recommended = candidate_ready and mode == "production_run"
            blueprint_payload = self._safe_load_json(
                Path(case.case_dir) / "prototype" / "draft_task_blueprint.json"
            )
            notes: List[str] = []
            if production_candidate_eligible:
                notes.append("Eligible for later production QA review once the production gate exists.")
            if candidate_ready and case.workflow_context_fit in {"low", None}:
                notes.append("Candidate-ready path exists, but workflow context should remain under review.")
            records.append(
                ProductionCaseRecord(
                    case_id=case.case_id,
                    motif=case.motif,
                    case_dir=case.case_dir,
                    batch_status=case.status,
                    task_state=task_state,
                    blueprint_id=getattr(case, "blueprint_id", None),
                    subgraph_id=getattr(case, "subgraph_id", None),
                    template_family=self._template_family(blueprint_payload),
                    deliverable_file_names=self._deliverable_file_names(blueprint_payload),
                    selected_skill_ids=self._selected_skill_ids(blueprint_payload),
                    quality_decision=case.quality_decision,
                    verifier_status=case.verifier_status,
                    validation_status=case.validation_status,
                    global_validity_status=case.global_validity_status,
                    real_worldness_score=case.real_worldness_score,
                    difficulty_overall=getattr(case, "difficulty_overall", None),
                    workflow_context_fit=case.workflow_context_fit,
                    package_readiness=case.package_readiness,
                    production_candidate_eligible=production_candidate_eligible,
                    training_pool_candidate_eligible=training_pool_candidate_eligible,
                    diagnostic_eval_recommended=diagnostic_eval_recommended,
                    blocker_reason_codes=list(case.reason_codes),
                    warning_reason_codes=list(case.warning_reason_codes),
                    notes=notes,
                )
            )
        return records

    def _summary(
        self,
        cases: List[ProductionCaseRecord],
        request: ProductionBatchRequest,
        batch_report: Optional["PipelineBBatchRunReport"],
    ) -> ProductionBatchSummary:
        state_counts: Dict[str, int] = {}
        motif_counts: Dict[str, int] = {}
        warning_counts: Dict[str, int] = {}
        for case in cases:
            state_counts[case.task_state] = state_counts.get(case.task_state, 0) + 1
            motif_counts[case.motif] = motif_counts.get(case.motif, 0) + 1
        if batch_report is not None:
            for warning in batch_report.diagnostics.batch_warnings:
                warning_counts[warning] = warning_counts.get(warning, 0) + 1
        return ProductionBatchSummary(
            planned_case_count=request.max_cases,
            executed_case_count=len(cases),
            completed_case_count=sum(1 for case in cases if case.batch_status == "completed"),
            failed_case_count=sum(1 for case in cases if case.batch_status == "failed"),
            candidate_ready_count=sum(1 for case in cases if case.task_state == "candidate_ready"),
            production_candidate_eligible_count=sum(1 for case in cases if case.production_candidate_eligible),
            training_pool_candidate_eligible_count=sum(1 for case in cases if case.training_pool_candidate_eligible),
            diagnostic_eval_recommended_count=sum(1 for case in cases if case.diagnostic_eval_recommended),
            task_state_counts=dict(sorted(state_counts.items())),
            motif_counts=dict(sorted(motif_counts.items())),
            batch_warning_counts=dict(sorted(warning_counts.items())),
        )

    def _task_state(self, case: BaseModel) -> ProductionTaskState:
        if getattr(case, "status", None) != "completed":
            return "generated"
        state: ProductionTaskState = "structurally_valid"
        if getattr(case, "verifier_status", None) == "pass":
            state = "verifier_passed"
        if self._is_candidate_ready(case):
            state = "candidate_ready"
        return state

    def _is_candidate_ready(self, case: BaseModel) -> bool:
        return (
            getattr(case, "quality_decision", None) == "candidate_ready"
            and getattr(case, "verifier_status", None) == "pass"
            and getattr(case, "validation_status", None) == "candidate_ready_compatible"
            and getattr(case, "global_validity_status", None) in {"diagnostic_only", "pass", None}
        )

    def _registry_version(self, payload: Dict[str, object]) -> Optional[str]:
        value = payload.get("registry_version")
        return str(value) if value is not None else "v3.0"

    def _workflow_asset_version(self, payload: Dict[str, object]) -> Optional[str]:
        if not payload:
            return None
        value = payload.get("workflow_archetype_registry_version")
        return str(value) if value is not None else None

    def _motif_grammar_version(self, payload: Dict[str, object]) -> Optional[str]:
        if not payload:
            return None
        value = payload.get("motif_graph_grammar_version")
        return str(value) if value is not None else None

    def _safe_load_json(self, path: str | Path | None) -> Dict[str, object]:
        if not path:
            return {}
        resolved = Path(path)
        if not resolved.exists():
            return {}
        return load_json_file(str(resolved))

    def _template_family(self, payload: Dict[str, object]) -> Optional[str]:
        value = payload.get("template_family")
        return str(value) if value is not None else None

    def _deliverable_file_names(self, payload: Dict[str, object]) -> List[str]:
        values = payload.get("deliverable_spec") or []
        if not isinstance(values, list):
            return []
        file_names: List[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            file_name = item.get("file_name")
            if file_name is not None:
                file_names.append(str(file_name))
        return file_names

    def _selected_skill_ids(self, payload: Dict[str, object]) -> List[str]:
        values = payload.get("selected_skills") or []
        if not isinstance(values, list):
            return []
        return [str(value) for value in values]

    def _git_commit(self, cwd: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                capture_output=True,
                check=True,
                text=True,
            )
        except Exception:
            return None
        return result.stdout.strip() or None
