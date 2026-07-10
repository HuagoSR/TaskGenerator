from __future__ import annotations

import json
import hashlib
import zipfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_production_batch_runner import ProductionBatchRunner
from task_generator.v3_rw_task_eval_prep import RwTaskEvalPrep
from task_generator.v3_source_schema import load_json_file


Phase16ArmId = Literal[
    "baseline_deterministic",
    "contract_v2_only",
    "contract_v2_plus_productive_complexity",
]
Phase16ArmStatus = Literal["executed", "blocked"]
Phase16QueueStatus = Literal["prepared", "blocked"]


class Phase16ProductionEvalPrepRequest(BaseModel):
    experiment_id: str = "phase16_evidence_to_deliverable_contract_v2"
    registry_path: str = "SkillRegistry/v3_skill_registry.json"
    seed_report_path: str = "SkillRegistry/v3_pipeline_b_seed_set_report.json"
    workflow_asset_path: Optional[str] = "SkillRegistry/v3_workflow_archetype_registry.experimental.json"
    motif_grammar_path: Optional[str] = "SkillRegistry/v3_motif_graph_grammar.experimental.json"
    output_dir: str = "artifacts/phase16/production_eval_prep"
    target_motif: str = "evidence_to_deliverable"
    max_cases_per_arm: int = 3
    selected_case_ids: List[str] = Field(
        default_factory=lambda: [
            "pipeline_b_batch_01_evidence_to_deliverable",
            "pipeline_b_batch_03_evidence_to_deliverable",
        ]
    )
    skill_count: int = 4
    models: List[str] = Field(default_factory=lambda: ["gpt-4o-mini", "gemini-3-pro-preview"])
    workers: int = 1
    rw_task_root: str = r"E:\THU\2026Spring\SRT\rw-task"
    python_exe: str = r"D:\miniconda3\envs\real-world-task\python.exe"
    command_timeout_seconds: int = 900


class Phase16ArmSummary(BaseModel):
    arm_id: Phase16ArmId
    arm_status: Phase16ArmStatus
    production_batch_id: str
    manifest_path: Optional[str] = None
    batch_report_path: Optional[str] = None
    candidate_ready_count: int = 0
    completed_case_count: int = 0
    failed_case_count: int = 0
    comparable_for_clean_eval: bool = False
    experiment_spec_path: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase16ProductionExperimentReport(BaseModel):
    report_version: str = "v3.phase16_production_experiment.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase16ProductionEvalPrepRequest
    arms: List[Phase16ArmSummary] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase16CleanEvalQueueItem(BaseModel):
    item_id: str
    arm_id: Phase16ArmId
    case_id: str
    model: str
    status: Phase16QueueStatus
    prep_report_path: Optional[str] = None
    eval_input_dir: Optional[str] = None
    run_output_dir: Optional[str] = None
    would_run_commands: List[List[str]] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    candidate_visible_bundle_sha256: Optional[str] = None


class Phase16CleanEvalQueueReport(BaseModel):
    report_version: str = "v3.phase16_clean_eval_queue.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase16ProductionEvalPrepRequest
    queue_items: List[Phase16CleanEvalQueueItem] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    execution_policy: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase16ExternalEvalRunbook(BaseModel):
    report_version: str = "v3.phase16_external_eval_runbook.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase16ProductionEvalPrepRequest
    items: List[Phase16CleanEvalQueueItem] = Field(default_factory=list)
    run_order: List[str] = Field(default_factory=list)
    generated_files: Dict[str, str] = Field(default_factory=dict)
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase16ProductionEvalPrepRunner:
    """Prepare Phase 16 clean-eval inputs through the full Pipeline B and rw-task prep path."""

    ARMS: List[Phase16ArmId] = [
        "baseline_deterministic",
        "contract_v2_only",
        "contract_v2_plus_productive_complexity",
    ]

    def run(self, request: Phase16ProductionEvalPrepRequest) -> Dict[str, Any]:
        output_dir = Path(request.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        experiment = self._production_experiment(request, output_dir)
        queue = self._clean_eval_queue(request, output_dir, experiment)
        runbook = self._runbook(request, output_dir, queue)
        return {
            "production_experiment": experiment.model_dump(mode="json"),
            "clean_eval_queue": queue.model_dump(mode="json"),
            "external_eval_runbook": runbook.model_dump(mode="json"),
            "outputs": {
                "production_experiment_report": str(output_dir / "phase16_production_experiment_report.json"),
                "clean_eval_queue_report": str(output_dir / "phase16_clean_eval_queue_report.json"),
                "external_eval_runbook": str(output_dir / "phase16_external_eval_runbook.json"),
                "external_eval_results_template": str(output_dir / "phase16_external_eval_results_template.json"),
                "powershell_script": str(output_dir / "run_phase16_clean_eval.ps1"),
            },
        }

    def _production_experiment(
        self,
        request: Phase16ProductionEvalPrepRequest,
        output_dir: Path,
    ) -> Phase16ProductionExperimentReport:
        specs_dir = output_dir / "experiment_specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        arms: List[Phase16ArmSummary] = []
        for arm_id in self.ARMS:
            try:
                arms.append(self._run_arm(request, output_dir, specs_dir, arm_id))
            except Exception as exc:
                arms.append(
                    Phase16ArmSummary(
                        arm_id=arm_id,
                        arm_status="blocked",
                        production_batch_id=f"{request.experiment_id}_{arm_id}",
                        reason_codes=[f"production_batch_exception:{type(exc).__name__}"],
                        notes=[str(exc)[:500]],
                    )
                )
        report = Phase16ProductionExperimentReport(
            created_at=self._now(),
            request=request,
            arms=arms,
            summary=self._experiment_summary(arms, request),
            notes=[
                "This runner reuses ProductionBatchRunner and rw-task eval prep; it does not call external model APIs.",
                "Phase16 arms are experiment-only and do not promote generator defaults.",
                "Only sanitized result records from the generated runbook should be imported into the clean eval gate.",
            ],
        )
        (output_dir / "phase16_production_experiment_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _run_arm(
        self,
        request: Phase16ProductionEvalPrepRequest,
        output_dir: Path,
        specs_dir: Path,
        arm_id: Phase16ArmId,
    ) -> Phase16ArmSummary:
        spec_path: Optional[Path] = None
        if arm_id != "baseline_deterministic":
            spec_path = self._write_experiment_spec(specs_dir, arm_id)
        batch_id = f"{request.experiment_id}_{arm_id}"
        artifact = ProductionBatchRunner().run(
            production_batch_id=batch_id,
            mode="candidate_run",
            registry_path=request.registry_path,
            seed_report_path=request.seed_report_path,
            workflow_asset_path=request.workflow_asset_path,
            motif_grammar_path=request.motif_grammar_path,
            phase15_reform_spec_path=str(spec_path) if spec_path else None,
            output_dir=output_dir / self._path_alias(arm_id),
            motifs=[request.target_motif],
            skill_count=request.skill_count,
            max_cases=request.max_cases_per_arm,
            model="gpt-5.4-pro",
            workers=request.workers,
            rw_task_root=request.rw_task_root,
            python_exe=request.python_exe,
        )
        selected_required_count = len(request.selected_case_ids)
        ready = artifact.manifest.summary.candidate_ready_count >= selected_required_count
        return Phase16ArmSummary(
            arm_id=arm_id,
            arm_status="executed",
            production_batch_id=batch_id,
            manifest_path=artifact.manifest_path,
            batch_report_path=artifact.batch_report_path,
            candidate_ready_count=artifact.manifest.summary.candidate_ready_count,
            completed_case_count=artifact.manifest.summary.completed_case_count,
            failed_case_count=artifact.manifest.summary.failed_case_count,
            comparable_for_clean_eval=ready,
            experiment_spec_path=str(spec_path) if spec_path else None,
            reason_codes=[] if ready else ["candidate_ready_count_below_selected_case_scope"],
            notes=[
                "Baseline arm uses default deterministic generation." if arm_id == "baseline_deterministic"
                else f"{arm_id} uses an explicit Phase16 experiment spec through the existing reform-spec hook.",
            ],
        )

    def _write_experiment_spec(self, specs_dir: Path, arm_id: Phase16ArmId) -> Path:
        productive = arm_id == "contract_v2_plus_productive_complexity"
        spec = {
            "spec_version": "v3.phase16_evidence_to_deliverable_contract_spec.1",
            "created_at": self._now(),
            "target_motif": "evidence_to_deliverable",
            "reform_status": "proposal_ready_for_controlled_experiment",
            "phase16_contract_mode": arm_id,
            "default_chain_mutation": False,
            "deterministic_changes": [
                {
                    "change_id": "phase16_contract_v2_sections",
                    "change_type": "deliverable_contract_alignment",
                    "deterministic_or_llm_candidate": "deterministic",
                },
                {
                    "change_id": "phase16_traceability_required",
                    "change_type": "rubric_goldenrun_alignment",
                    "deterministic_or_llm_candidate": "deterministic",
                },
            ]
            + (
                [
                    {
                        "change_id": "phase16_productive_uncertainty_handling",
                        "change_type": "productive_complexity",
                        "deterministic_or_llm_candidate": "deterministic",
                    }
                ]
                if productive
                else []
            ),
            "constraints": [
                "no_llm_primary_truth",
                "no_default_generator_promotion",
                "must_route_through_full_task_package_and_rw_task_eval_prep",
            ],
        }
        path = specs_dir / f"{arm_id}_phase16_contract_spec.json"
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _clean_eval_queue(
        self,
        request: Phase16ProductionEvalPrepRequest,
        output_dir: Path,
        experiment: Phase16ProductionExperimentReport,
    ) -> Phase16CleanEvalQueueReport:
        queue_items: List[Phase16CleanEvalQueueItem] = []
        for arm in experiment.arms:
            if arm.arm_status != "executed" or not arm.manifest_path:
                queue_items.append(
                    Phase16CleanEvalQueueItem(
                        item_id=self._item_id(arm.arm_id, "arm", "all_models"),
                        arm_id=arm.arm_id,
                        case_id="arm",
                        model="all_models",
                        status="blocked",
                        blocking_reasons=arm.reason_codes or ["arm_not_executed"],
                    )
                )
                continue
            manifest = load_json_file(arm.manifest_path)
            selected_cases = [
                case for case in (manifest.get("cases") or [])
                if case.get("case_id") in set(request.selected_case_ids)
            ]
            for case in selected_cases:
                queue_items.extend(self._queue_items_for_case(request, output_dir, arm.arm_id, case))
        report = Phase16CleanEvalQueueReport(
            created_at=self._now(),
            request=request,
            queue_items=queue_items,
            summary=self._queue_summary(queue_items, request),
            execution_policy={
                "run_order": "one_item_at_a_time",
                "external_calls_allowed_by_this_runner": False,
                "required_eval_runner": "Test/run_v3_rw_task_eval_runner.py",
                "required_result_import": "Test/run_v3_phase16_clean_eval_gate.py --external-eval-results <sanitized-results>",
            },
            notes=[
                "Queue preparation copies validated rw-task exports into eval input directories.",
                "Prepared status proves structural eval readiness only; it does not prove model-separation evidence.",
            ],
        )
        (output_dir / "phase16_clean_eval_queue_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _queue_items_for_case(
        self,
        request: Phase16ProductionEvalPrepRequest,
        output_dir: Path,
        arm_id: Phase16ArmId,
        case: Dict[str, Any],
    ) -> List[Phase16CleanEvalQueueItem]:
        items: List[Phase16CleanEvalQueueItem] = []
        case_id = str(case.get("case_id") or "unknown")
        case_dir = Path(str(case.get("case_dir") or ""))
        export_dir = case_dir / "rw_task_export"
        validation_report_path = export_dir / "rw_task_export_validation_report.json"
        for model in request.models:
            item_id = self._item_id(arm_id, case_id, model)
            eval_input_dir = (
                output_dir
                / "i"
                / self._path_alias(arm_id)
                / self._path_alias(case_id)
                / self._path_alias(model)
            )
            prep = RwTaskEvalPrep().prepare(
                case_dir=export_dir,
                validation_report_path=validation_report_path,
                eval_input_dir=eval_input_dir,
                model=model,
                workers=request.workers,
                rw_task_root=request.rw_task_root,
                python_exe=request.python_exe,
                overwrite=True,
            )
            items.append(
                Phase16CleanEvalQueueItem(
                    item_id=item_id,
                    arm_id=arm_id,
                    case_id=case_id,
                    model=model,
                    status="prepared" if prep.prep_status == "prepared" else "blocked",
                    prep_report_path=str(eval_input_dir / "rw_task_eval_prep_report.json"),
                    eval_input_dir=str(eval_input_dir),
                    run_output_dir=str(
                        output_dir
                        / "r"
                        / self._path_alias(arm_id)
                        / self._path_alias(case_id)
                        / self._path_alias(model)
                    ),
                    would_run_commands=prep.would_run_commands,
                    blocking_reasons=prep.blocking_reasons,
                    warnings=prep.warnings,
                    candidate_visible_bundle_sha256=self._bundle_fingerprint(export_dir),
                )
            )
        return items

    def _runbook(
        self,
        request: Phase16ProductionEvalPrepRequest,
        output_dir: Path,
        queue: Phase16CleanEvalQueueReport,
    ) -> Phase16ExternalEvalRunbook:
        prepared = [item for item in queue.queue_items if item.status == "prepared"]
        blocking = []
        expected_count = len(request.selected_case_ids) * len(self.ARMS) * len(request.models)
        if len(prepared) != expected_count:
            blocking.append(f"prepared_item_count:{len(prepared)}_expected:{expected_count}")
        script_path = output_dir / "run_phase16_clean_eval.ps1"
        template_path = output_dir / "phase16_external_eval_results_template.json"
        runbook_path = output_dir / "phase16_external_eval_runbook.json"
        self._write_script(script_path, prepared, request)
        self._write_results_template(template_path, prepared)
        runbook = Phase16ExternalEvalRunbook(
            created_at=self._now(),
            request=request,
            items=prepared,
            run_order=[item.item_id for item in prepared],
            generated_files={
                "powershell_script": str(script_path),
                "results_template": str(template_path),
                "runbook": str(runbook_path),
            },
            blocking_reasons=blocking,
            notes=[
                "Run this script only after explicit scoped approval and only in an environment permitted to send task packages to external services.",
                "The script routes through Test/run_v3_rw_task_eval_runner.py and does not call providers directly.",
                "After execution, build sanitized records matching the template and import them through the Phase16 clean eval gate.",
            ],
        )
        runbook_path.write_text(runbook.model_dump_json(indent=2), encoding="utf-8")
        return runbook

    def _write_script(
        self,
        script_path: Path,
        items: List[Phase16CleanEvalQueueItem],
        request: Phase16ProductionEvalPrepRequest,
    ) -> None:
        lines = [
            "# Phase 16 clean-eval runner",
            "# Run only after explicit scoped approval in a permitted external-eval environment.",
            "$ErrorActionPreference = 'Stop'",
            "",
        ]
        for item in items:
            report_path = Path(item.run_output_dir) / "rw_task_eval_run_report.json"
            lines.extend(
                [
                    f"# {item.arm_id} / {item.case_id} / {item.model}",
                    f"$reportPath = '{report_path}'",
                    "$skipCompleted = $false",
                    "if (Test-Path -LiteralPath $reportPath) {",
                    "  $existingReport = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json",
                    "  $skipCompleted = $existingReport.run_status -eq 'completed'",
                    "}",
                    "if ($skipCompleted) { Write-Host \"SKIP completed: $reportPath\" } else {",
                    (
                        f"  & 'D:\\miniconda3\\envs\\taskgenerator\\python.exe' "
                        f"Test\\run_v3_rw_task_eval_runner.py --prep-report '{item.prep_report_path}' "
                        f"--output-dir '{item.run_output_dir}' --run-eval "
                        f"--command-timeout-seconds {request.command_timeout_seconds} --grader-model gpt-5.4-pro"
                    ),
                    "  if ($LASTEXITCODE -ne 0) { throw 'Phase 16 eval item failed; stop before running the next item.' }",
                    "}",
                    "",
                ]
            )
        lines.extend(
            [
                "# After all selected items finish, create sanitized records from run outputs.",
                f"# Fill: {script_path.parent / 'phase16_external_eval_results_template.json'}",
                "# Then run:",
                "# & 'D:\\miniconda3\\envs\\taskgenerator\\python.exe' Test\\run_v3_phase16_clean_eval_gate.py --external-eval-results <sanitized-results>",
                "",
            ]
        )
        script_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_results_template(self, template_path: Path, items: List[Phase16CleanEvalQueueItem]) -> None:
        records = [
            {
                "case_id": item.case_id,
                "arm_id": item.arm_id,
                "evaluated_model": item.model,
                "grader_model": "gpt-5.4-pro",
                "score": None,
                "run_status": "missing",
                "contains_secret": False,
                "raw_prompt_included": False,
                "source_item_id": item.item_id,
                "result_summary": "",
            }
            for item in items
        ]
        template = {
            "template_version": "v3.phase16_external_eval_results_template.1",
            "instructions": [
                "Replace score and run_status only after the corresponding rw-task eval and grade outputs exist.",
                "Do not paste API keys, raw provider logs, bearer tokens, or raw prompts into this file.",
            ],
            "records": records,
        }
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    def _experiment_summary(self, arms: List[Phase16ArmSummary], request: Phase16ProductionEvalPrepRequest) -> Dict[str, Any]:
        return {
            "arm_count": len(arms),
            "executed_arm_count": sum(1 for arm in arms if arm.arm_status == "executed"),
            "all_arms_comparable_for_clean_eval": all(arm.comparable_for_clean_eval for arm in arms),
            "production_cases_per_arm": request.max_cases_per_arm,
            "selected_case_count": len(request.selected_case_ids),
            "selected_case_ids": request.selected_case_ids,
            "candidate_ready_by_arm": {arm.arm_id: arm.candidate_ready_count for arm in arms},
        }

    def _queue_summary(
        self,
        items: List[Phase16CleanEvalQueueItem],
        request: Phase16ProductionEvalPrepRequest,
    ) -> Dict[str, Any]:
        expected_count = len(request.selected_case_ids) * len(self.ARMS) * len(request.models)
        prepared = [item for item in items if item.status == "prepared"]
        return {
            "queue_item_count": len(items),
            "prepared_item_count": len(prepared),
            "blocked_item_count": sum(1 for item in items if item.status == "blocked"),
            "expected_item_count": expected_count,
            "selected_scope_structurally_ready": len(prepared) == expected_count,
            "two_case_clean_eval_structurally_ready": len(prepared) == expected_count
            if len(request.selected_case_ids) == 2
            else False,
            "case_count": len({item.case_id for item in prepared}),
            "selected_case_ids": request.selected_case_ids,
            "arm_count": len({item.arm_id for item in prepared}),
            "model_count": len({item.model for item in prepared}),
        }

    def _item_id(self, arm_id: str, case_id: str, model: str) -> str:
        return "__".join(self._slug(part) for part in [arm_id, case_id, model] if part)

    def _slug(self, value: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_") or "item"

    def _path_alias(self, value: str) -> str:
        aliases = {
            "baseline_deterministic": "b",
            "contract_v2_only": "c2",
            "contract_v2_plus_productive_complexity": "c2p",
            "gpt-4o-mini": "w",
            "gemini-3-pro-preview": "s",
        }
        if value in aliases:
            return aliases[value]
        if value.startswith("pipeline_b_batch_"):
            parts = value.split("_")
            if len(parts) > 3 and parts[3].isdigit():
                return f"c{parts[3]}"
        return self._slug(value)[:32]

    def _bundle_fingerprint(self, export_dir: Path) -> str:
        selected: List[Path] = []
        for relative in [Path("dataset_row.json"), Path("artifacts/rubric.json")]:
            path = export_dir / relative
            if path.exists():
                selected.append(path)
        for directory in [export_dir / "reference_files", export_dir / "deliverable_files"]:
            if directory.exists():
                selected.extend(path for path in directory.rglob("*") if path.is_file())
        digest = hashlib.sha256()
        for path in sorted(selected, key=lambda item: item.relative_to(export_dir).as_posix()):
            digest.update(path.relative_to(export_dir).as_posix().encode("utf-8"))
            digest.update(b"\0")
            suffix = path.suffix.lower()
            if suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            elif suffix in {".xlsx", ".docx"}:
                content_digest = hashlib.sha256()
                with zipfile.ZipFile(path) as archive:
                    for name in sorted(archive.namelist()):
                        if name in {"docProps/core.xml", "docProps/app.xml"}:
                            continue
                        content_digest.update(name.encode("utf-8"))
                        content_digest.update(b"\0")
                        content_digest.update(archive.read(name))
                content = content_digest.digest()
            else:
                content = path.read_bytes()
            digest.update(content)
            digest.update(b"\0")
        return digest.hexdigest()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def build_phase16_production_eval_prep(request: Phase16ProductionEvalPrepRequest) -> Dict[str, Any]:
    return Phase16ProductionEvalPrepRunner().run(request)
