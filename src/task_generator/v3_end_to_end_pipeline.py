from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file
from task_generator.v3_skill_registry import SkillRegistryBuilder


ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "Test"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "end_to_end_runs"
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_MOTIF_GRAMMAR_PATH = ROOT / "SkillRegistry" / "v3_motif_graph_grammar.experimental.json"
DEFAULT_WORKFLOW_ASSET_PATH = ROOT / "SkillRegistry" / "v3_workflow_archetype_registry.experimental.json"
DEFAULT_ENV_PATH = ROOT.parent / "rw-task" / ".env"
DEFAULT_RW_TASK_ROOT = ROOT.parent / "rw-task"

PipelineStage = Literal[
    "source_to_skills",
    "registry_prepare",
    "task_generation",
    "production_review",
    "rw_task_eval",
]
SourceMode = Literal["web", "local", "existing"]
EvalMode = Literal["dry-run", "execute"]
RegistryMode = Literal["existing", "fresh_scratch"]
StageState = Literal["pending", "skipped", "completed", "failed"]
CollectorBackend = Literal["direct", "stirrup"]

STAGE_ORDER: List[PipelineStage] = [
    "source_to_skills",
    "registry_prepare",
    "task_generation",
    "production_review",
    "rw_task_eval",
]


class StageCommandResult(BaseModel):
    label: str
    command: List[str] = Field(default_factory=list)
    returncode: int = 0
    stdout_path: str = ""
    stderr_path: str = ""
    parsed_stdout: Dict[str, Any] = Field(default_factory=dict)


class StageStatus(BaseModel):
    stage: PipelineStage
    state: StageState = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    artifact_paths: Dict[str, str] = Field(default_factory=dict)
    command_results: List[StageCommandResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class StageFailure(RuntimeError):
    def __init__(self, message: str, status: StageStatus) -> None:
        super().__init__(message)
        self.status = status


class EndToEndRequest(BaseModel):
    run_id: str
    selected_stages: List[PipelineStage]
    source_mode: SourceMode = "existing"
    registry_mode: Optional[RegistryMode] = None
    registry_path: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    collection_dirs: List[str] = Field(default_factory=list)
    local_source_dir: Optional[str] = None
    source_limit: int = 3
    collector_backend: CollectorBackend = "direct"
    collector_max_turns: int = 32
    max_cases: int = 4
    apply_registry_update: bool = False
    allow_web_collection: bool = False
    allow_external_upload: bool = False
    reuse_existing: bool = False
    force_stage: bool = False
    review_spec_path: Optional[str] = None
    eval_mode: EvalMode = "dry-run"
    run_eval: bool = False
    allow_draft_eval: bool = False
    models: List[str] = Field(default_factory=list)
    rw_task_root: str = str(DEFAULT_RW_TASK_ROOT)
    env_path: str = str(DEFAULT_ENV_PATH)
    python_exe: str = sys.executable
    timeout_seconds: int = 0


class EndToEndManifest(BaseModel):
    end_to_end_manifest_version: str = "v3.end_to_end_pipeline.1"
    run_id: str
    created_at: str
    updated_at: str
    request: EndToEndRequest
    run_dir: str
    stage_status_path: str
    summary_report_path: str
    registry_mode: RegistryMode = "existing"
    active_registry_path: str = str(DEFAULT_REGISTRY_PATH)
    canonical_registry_path: str = str(DEFAULT_REGISTRY_PATH)
    scratch_registry_initialized: bool = False
    registry_entry_count_initial: int = 0
    stages: Dict[str, StageStatus] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class EndToEndPipeline:
    """Report-first central runner for the V3 source-to-eval workflow."""

    def __init__(self, repo_root: str | Path = ROOT) -> None:
        self.root = Path(repo_root)
        self.test_dir = self.root / "Test"

    def run(self, request: EndToEndRequest, output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> EndToEndManifest:
        run_dir = Path(output_root) / request.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._load_or_create_manifest(request, run_dir)
        manifest = self._prepare_registry_state(request, run_dir, manifest)
        selected_stages = self._expanded_stages(request.selected_stages)

        for stage in selected_stages:
            existing = manifest.stages.get(stage)
            if existing and existing.state == "completed" and request.reuse_existing and not request.force_stage:
                existing.warnings = sorted(set(existing.warnings + ["Stage reused from a previous completed run."]))
                self._write_manifest(manifest)
                self._write_summary(manifest)
                continue
            try:
                manifest.stages[stage] = self._run_stage(stage, request, run_dir, manifest)
            except StageFailure as exc:
                failed = exc.status
                failed.state = "failed"
                failed.finished_at = self._now()
                failed.blocking_reasons = sorted(set(failed.blocking_reasons + [str(exc)]))
                manifest.stages[stage] = failed
                self._write_manifest(manifest)
                self._write_summary(manifest)
                raise RuntimeError(str(exc))
            except Exception as exc:
                failed = manifest.stages.get(stage) or StageStatus(stage=stage)
                failed.state = "failed"
                failed.finished_at = self._now()
                failed.blocking_reasons = sorted(set(failed.blocking_reasons + [str(exc)]))
                manifest.stages[stage] = failed
                self._write_manifest(manifest)
                self._write_summary(manifest)
                raise
            self._write_manifest(manifest)
            self._write_summary(manifest)

        self._write_manifest(manifest)
        self._write_summary(manifest)
        return manifest

    def _run_stage(
        self,
        stage: PipelineStage,
        request: EndToEndRequest,
        run_dir: Path,
        manifest: EndToEndManifest,
    ) -> StageStatus:
        status = StageStatus(stage=stage, state="pending", started_at=self._now())
        stage_dir = run_dir / self._stage_dir_name(stage)
        stage_dir.mkdir(parents=True, exist_ok=True)

        if stage == "source_to_skills":
            status = self._stage_source_to_skills(status, request, stage_dir, manifest)
        elif stage == "registry_prepare":
            status = self._stage_registry_prepare(status, request, stage_dir, manifest)
        elif stage == "task_generation":
            status = self._stage_task_generation(status, request, stage_dir, manifest)
        elif stage == "production_review":
            status = self._stage_production_review(status, request, stage_dir, manifest)
        elif stage == "rw_task_eval":
            status = self._stage_rw_task_eval(status, request, stage_dir, manifest)
        else:
            raise ValueError(f"Unsupported stage: {stage}")

        self._validate_stage_outcome(status, request, manifest)
        status.state = "completed"
        status.finished_at = self._now()
        return status

    def _stage_source_to_skills(
        self,
        status: StageStatus,
        request: EndToEndRequest,
        stage_dir: Path,
        manifest: EndToEndManifest,
    ) -> StageStatus:
        manifest_registry_path = manifest.active_registry_path
        status.summary["active_registry_path"] = manifest_registry_path
        status.summary["registry_mode"] = manifest.registry_mode
        if request.source_mode == "existing":
            status.summary.update(
                {
                    "source_mode": "existing",
                    "note": "Existing SkillRegistry and source artifacts are reused.",
                }
            )
            return status

        if request.source_mode == "local":
            if not request.local_source_dir:
                raise ValueError("--local-source-dir is required when --source-mode local.")
            output_dir = stage_dir / "local_source_package"
            cmd = [
                request.python_exe,
                str(self.test_dir / "run_v3_local_source_to_skill.py"),
                "--input-dir",
                request.local_source_dir,
                "--output-dir",
                str(output_dir),
            ]
            result = self._run_command("local_source_to_skill", cmd, stage_dir, request.timeout_seconds)
            status.command_results.append(result)
            status.artifact_paths["local_prompt_package"] = str(output_dir / "skill_extraction_prompt_package.json")
            status.summary.update(
                {
                    "source_mode": "local",
                    "local_prompt_package_only": True,
                    "registry_entry_count_before": self._registry_entry_count(Path(manifest_registry_path)),
                    "registry_entry_count_after": self._registry_entry_count(Path(manifest_registry_path)),
                    "registry_entry_delta_this_run": 0,
                    "note": "Local mode builds a prompt package; it does not perform external LLM extraction by itself.",
                }
            )
            return status

        output_root = stage_dir / "web_source_collections"
        batch_report = stage_dir / "web_source_pipeline_a_batch_report.json"
        registry_path = manifest_registry_path
        cmd = [
            request.python_exe,
            str(self.test_dir / "run_v3_web_source_pipeline_a_batch.py"),
            "--output-root",
            str(output_root),
            "--batch-report-path",
            str(batch_report),
            "--registry-path",
            str(registry_path),
            "--env-path",
            request.env_path,
            "--limit",
            str(request.source_limit),
            "--collector-backend",
            request.collector_backend,
            "--collector-max-turns",
            str(request.collector_max_turns),
            "--build-transition-graph",
        ]
        for topic in request.topics:
            cmd.extend(["--topic", topic])
        for collection_dir in request.collection_dirs:
            cmd.extend(["--collection-dir", collection_dir])
        if request.allow_web_collection:
            cmd.append("--allow-web-collection")
        if request.allow_external_upload:
            cmd.append("--allow-external-upload")
        if request.reuse_existing:
            cmd.append("--reuse-existing")
        if not self._should_write_registry(request, manifest):
            cmd.append("--skip-registry-update")
        result = self._run_command("web_source_pipeline_a_batch", cmd, stage_dir, request.timeout_seconds)
        status.command_results.append(result)
        status.artifact_paths["web_source_batch_report"] = str(batch_report)
        status.artifact_paths["web_source_output_root"] = str(output_root)
        payload = self._safe_load(batch_report)
        totals = payload.get("totals") or {}
        status.summary.update(
            {
                "source_mode": "web",
                "collector_backend": request.collector_backend,
                "collection_dir_count": len(request.collection_dirs),
                "status": payload.get("status"),
                "batch_count": payload.get("batch_count"),
                "successful_batch_count": payload.get("successful_batch_count"),
                "failed_batch_count": payload.get("failed_batch_count"),
                "collection_failed_batch_count": payload.get("collection_failed_batch_count"),
                "candidate_count": totals.get("candidate_count"),
                "accepted_count": totals.get("accepted_count"),
                "revise_count": totals.get("revise_count"),
                "rejected_count": totals.get("rejected_count"),
                "registry_update_mode": payload.get("registry_update_mode"),
                "registry_entry_count_before": payload.get("registry_entry_count_before"),
                "registry_entry_count_after": payload.get("registry_entry_count_after"),
                "registry_entry_delta_this_run": payload.get("registry_entry_delta_this_run"),
            }
        )
        return status

    def _stage_registry_prepare(
        self,
        status: StageStatus,
        request: EndToEndRequest,
        stage_dir: Path,
        manifest: EndToEndManifest,
    ) -> StageStatus:
        registry_path = manifest.active_registry_path
        audit_report = stage_dir / "v3_skill_registry_audit_report.json"
        readiness_report = stage_dir / "v3_registry_sampling_readiness_report.json"
        seed_report = stage_dir / "v3_pipeline_b_seed_set_report.json"
        transition_report = stage_dir / "v3_skill_transition_graph_report.json"
        composition_report = stage_dir / "v3_composition_readiness_report.json"

        commands = [
            (
                "skill_registry_audit",
                [
                    request.python_exe,
                    str(self.test_dir / "run_v3_skill_registry_audit.py"),
                    "--registry-path",
                    str(registry_path),
                    "--audit-report-path",
                    str(audit_report),
                ],
            ),
            (
                "registry_sampling_readiness",
                [
                    request.python_exe,
                    str(self.test_dir / "run_v3_registry_sampling_readiness.py"),
                    "--registry-path",
                    str(registry_path),
                    "--audit-report",
                    str(audit_report),
                    "--no-default-reports",
                    "--output-path",
                    str(readiness_report),
                ],
            ),
            (
                "pipeline_b_seed_set",
                [
                    request.python_exe,
                    str(self.test_dir / "run_v3_pipeline_b_seed_set.py"),
                    "--registry-path",
                    str(registry_path),
                    "--readiness-report",
                    str(readiness_report),
                    "--output-path",
                    str(seed_report),
                ],
            ),
        ]
        for label, cmd in commands:
            status.command_results.append(self._run_command(label, cmd, stage_dir, request.timeout_seconds))

        candidates = self._find_latest_source_artifact(manifest, "extracted_skill_candidates.json")
        accepted = self._find_latest_source_artifact(manifest, "accepted_skill_candidates.json")
        if candidates:
            cmd = [
                request.python_exe,
                str(self.test_dir / "run_v3_skill_transition_graph.py"),
                "--candidates",
                str(candidates),
                "--registry-path",
                str(registry_path),
                "--readiness-report",
                str(readiness_report),
                "--transition-report-path",
                str(transition_report),
                "--composition-report-path",
                str(composition_report),
            ]
            if accepted:
                cmd.extend(["--accepted-candidates", str(accepted)])
            status.command_results.append(self._run_command("skill_transition_graph", cmd, stage_dir, request.timeout_seconds))
            status.artifact_paths["transition_report"] = str(transition_report)
            status.artifact_paths["composition_report"] = str(composition_report)
        else:
            status.warnings.append("No extracted_skill_candidates.json found from source_to_skills; transition graph was skipped.")

        status.artifact_paths.update(
            {
                "audit_report": str(audit_report),
                "readiness_report": str(readiness_report),
                "seed_report": str(seed_report),
            }
        )
        seed_payload = self._safe_load(seed_report)
        status.summary = {
            "active_registry_path": registry_path,
            "registry_mode": manifest.registry_mode,
            "selected_count": seed_payload.get("selected_count"),
            "selected_readiness_counts": seed_payload.get("selected_readiness_counts"),
            "selected_motif_counts": seed_payload.get("selected_motif_counts"),
        }
        return status

    def _stage_task_generation(
        self,
        status: StageStatus,
        request: EndToEndRequest,
        stage_dir: Path,
        manifest: EndToEndManifest,
    ) -> StageStatus:
        registry_path = manifest.active_registry_path
        seed_report = self._artifact(manifest, "registry_prepare", "seed_report") or str(Path(registry_path).parent / "v3_pipeline_b_seed_set_report.json")
        cmd = [
            request.python_exe,
            str(self.test_dir / "run_v3_production_batch_runner.py"),
            "--production-batch-id",
            request.run_id,
            "--mode",
            "candidate_run",
            "--max-cases",
            str(request.max_cases),
            "--registry-path",
            registry_path,
            "--seed-report",
            seed_report,
            "--output-root",
            str(stage_dir),
            "--rw-task-root",
            request.rw_task_root,
            "--python-exe",
            request.python_exe,
        ]
        if DEFAULT_MOTIF_GRAMMAR_PATH.exists():
            cmd.extend(["--motif-grammar-path", str(DEFAULT_MOTIF_GRAMMAR_PATH)])
        if DEFAULT_WORKFLOW_ASSET_PATH.exists():
            cmd.extend(["--workflow-asset-path", str(DEFAULT_WORKFLOW_ASSET_PATH)])
        result = self._run_command("production_batch_runner", cmd, stage_dir, request.timeout_seconds)
        status.command_results.append(result)
        batch_dir = stage_dir / request.run_id
        manifest_path = batch_dir / "production_batch_manifest.json"
        batch_report = batch_dir / "batch" / "pipeline_b_batch_report.json"
        status.artifact_paths.update(
            {
                "production_batch_manifest": str(manifest_path),
                "pipeline_b_batch_report": str(batch_report),
                "production_batch_dir": str(batch_dir),
            }
        )
        payload = self._safe_load(manifest_path)
        status.summary = payload.get("summary") or {}
        status.summary["active_registry_path"] = registry_path
        status.summary["registry_mode"] = manifest.registry_mode
        return status

    def _stage_production_review(
        self,
        status: StageStatus,
        request: EndToEndRequest,
        stage_dir: Path,
        manifest: EndToEndManifest,
    ) -> StageStatus:
        manifest_path = self._artifact(manifest, "task_generation", "production_batch_manifest")
        if not manifest_path:
            raise ValueError("task_generation must run before production_review.")
        diversity_dir = stage_dir / "production_diversity"
        qa_dir = stage_dir / "production_qa_gate"
        diversity_report = diversity_dir / "production_batch_diversity_report.json"
        qa_report = qa_dir / "production_qa_gate_report.json"

        status.command_results.append(
            self._run_command(
                "production_batch_diversity",
                [
                    request.python_exe,
                    str(self.test_dir / "run_v3_production_batch_diversity.py"),
                    "--manifest-path",
                    manifest_path,
                    "--output-dir",
                    str(diversity_dir),
                ],
                stage_dir,
                request.timeout_seconds,
            )
        )
        status.command_results.append(
            self._run_command(
                "production_qa_gate",
                [
                    request.python_exe,
                    str(self.test_dir / "run_v3_production_qa_gate.py"),
                    "--manifest-path",
                    manifest_path,
                    "--diversity-report-path",
                    str(diversity_report),
                    "--output-dir",
                    str(qa_dir),
                ],
                stage_dir,
                request.timeout_seconds,
            )
        )

        effective_qa_report = qa_report
        release_manifest: Optional[Path] = None
        if request.review_spec_path:
            review_dir = stage_dir / "production_review" / "applied"
            status.command_results.append(
                self._run_command(
                    "production_promotion_manager",
                    [
                        request.python_exe,
                        str(self.test_dir / "run_v3_production_promotion_manager.py"),
                        "--manifest-path",
                        manifest_path,
                        "--qa-gate-report-path",
                        str(qa_report),
                        "--review-spec-path",
                        request.review_spec_path,
                        "--output-dir",
                        str(review_dir),
                    ],
                    stage_dir,
                    request.timeout_seconds,
                )
            )
            effective_qa_report = review_dir / "reviewed_production_qa_gate_report.json"
            status.artifact_paths["reviewed_qa_report"] = str(effective_qa_report)

            release_id = f"{request.run_id}_release"
            status.command_results.append(
                self._run_command(
                    "dataset_release_packager",
                    [
                        request.python_exe,
                        str(self.test_dir / "run_v3_dataset_release_packager.py"),
                        "--release-id",
                        release_id,
                        "--manifest-path",
                        manifest_path,
                        "--qa-gate-report-path",
                        str(effective_qa_report),
                        "--diversity-report-path",
                        str(diversity_report),
                        "--output-root",
                        str(stage_dir / "releases"),
                    ],
                    stage_dir,
                    request.timeout_seconds,
                )
            )
            release_manifest = stage_dir / "releases" / release_id / "release_manifest.json"
            status.artifact_paths["release_manifest"] = str(release_manifest)
        else:
            status.warnings.append("No review spec was provided; reviewed promotion and strict release packaging were skipped.")

        dashboard_dir = stage_dir / "production_dashboard"
        dashboard_cmd = [
            request.python_exe,
            str(self.test_dir / "run_v3_production_dashboard.py"),
            "--manifest-path",
            manifest_path,
            "--diversity-report-path",
            str(diversity_report),
            "--qa-gate-report-path",
            str(effective_qa_report),
            "--output-dir",
            str(dashboard_dir),
        ]
        if release_manifest and release_manifest.exists():
            dashboard_cmd.extend(["--release-manifest-path", str(release_manifest)])
        status.command_results.append(self._run_command("production_dashboard", dashboard_cmd, stage_dir, request.timeout_seconds))

        status.artifact_paths.update(
            {
                "diversity_report": str(diversity_report),
                "qa_gate_report": str(qa_report),
                "dashboard_report": str(dashboard_dir / "production_dashboard_report.json"),
                "release_readiness_report": str(dashboard_dir / "release_readiness_report.json"),
            }
        )
        readiness = self._safe_load(dashboard_dir / "release_readiness_report.json")
        qa_payload = self._safe_load(effective_qa_report)
        diversity = self._safe_load(diversity_report)
        status.summary = {
            "release_readiness_status": readiness.get("readiness_status"),
            "approved_production_candidate_count": (qa_payload.get("summary") or {}).get("approved_production_candidate_count"),
            "review_required_count": (qa_payload.get("summary") or {}).get("review_required_count"),
            "blocked_count": (qa_payload.get("summary") or {}).get("blocked_count"),
            "diversity_warnings": ((diversity.get("diagnostics") or {}).get("warnings") or []),
        }
        return status

    def _stage_rw_task_eval(
        self,
        status: StageStatus,
        request: EndToEndRequest,
        stage_dir: Path,
        manifest: EndToEndManifest,
    ) -> StageStatus:
        if request.eval_mode == "execute" and not request.run_eval:
            raise ValueError("--eval-mode execute requires explicit --run-eval.")
        manifest_path = self._artifact(manifest, "task_generation", "production_batch_manifest")
        if not manifest_path:
            raise ValueError("task_generation must run before rw_task_eval.")
        case_dir = self._first_eval_case_dir(Path(manifest_path))
        models = request.models or ["gpt-5.4-pro", "gpt-4o-mini"]
        cmd = [
            request.python_exe,
            str(self.test_dir / "run_v3_eval_orchestrator.py"),
            "--case-dir",
            str(case_dir),
            "--output-dir",
            str(stage_dir / "eval_orchestrator"),
            "--rw-task-root",
            request.rw_task_root,
            "--python-exe",
            request.python_exe,
            "--overwrite",
        ]
        for model in models:
            cmd.extend(["--model", model])
        if request.eval_mode == "execute":
            cmd.append("--run-eval")
            if request.allow_draft_eval:
                cmd.append("--allow-draft-eval")
        status.command_results.append(self._run_command("eval_orchestrator", cmd, stage_dir, request.timeout_seconds))
        report_path = stage_dir / "eval_orchestrator" / "evaluation_orchestration_report.json"
        status.artifact_paths["evaluation_orchestration_report"] = str(report_path)
        payload = self._safe_load(report_path)
        diagnostics = payload.get("diagnostics") or {}
        status.summary = {
            "execution_mode": payload.get("execution_mode"),
            "model_count": diagnostics.get("model_count"),
            "prepared_model_count": diagnostics.get("prepared_model_count"),
            "executed_model_count": diagnostics.get("executed_model_count"),
            "usable_summary_model_count": diagnostics.get("usable_summary_model_count"),
            "model_separation_profile_path": payload.get("model_separation_profile_path"),
        }
        return status

    def _run_command(
        self,
        label: str,
        cmd: List[str],
        stage_dir: Path,
        timeout_seconds: int,
    ) -> StageCommandResult:
        command_dir = stage_dir / "commands"
        command_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = command_dir / f"{label}.stdout.txt"
        stderr_path = command_dir / f"{label}.stderr.txt"
        result = subprocess.run(
            cmd,
            cwd=str(self.root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds or None,
        )
        stdout_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_path.write_text(result.stderr or "", encoding="utf-8")
        parsed = self._parse_json_stdout(result.stdout or "")
        command_result = StageCommandResult(
            label=label,
            command=cmd,
            returncode=result.returncode,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            parsed_stdout=parsed,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-1200:]
            raise RuntimeError(f"{label} failed with return code {result.returncode}: {tail}")
        return command_result

    def _write_manifest(self, manifest: EndToEndManifest) -> None:
        manifest.updated_at = self._now()
        Path(manifest.stage_status_path).write_text(
            json.dumps(
                {stage: status.model_dump(mode="json") for stage, status in manifest.stages.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        manifest_path = Path(manifest.run_dir) / "end_to_end_run_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    def _write_summary(self, manifest: EndToEndManifest) -> None:
        task_summary = self._task_summary(manifest)
        review_summary = self._summary_for(manifest, "production_review")
        eval_summary = self._summary_for(manifest, "rw_task_eval")
        source_summary = self._summary_for(manifest, "source_to_skills")
        payload = {
            "end_to_end_summary_version": "v3.end_to_end_summary.1",
            "run_id": manifest.run_id,
            "updated_at": self._now(),
            "stage_states": {stage: status.state for stage, status in manifest.stages.items()},
            "registry_summary": self._registry_summary(manifest),
            "questions": {
                "reusable_skills_extracted": self._skill_answer(source_summary),
                "tasks_generated": self._task_answer(task_summary),
                "task_diversity": self._diversity_answer(review_summary),
                "model_separation": self._model_separation_answer(eval_summary),
            },
            "source_summary": source_summary,
            "task_generation_summary": task_summary,
            "production_review_summary": review_summary,
            "rw_task_eval_summary": eval_summary,
            "artifact_paths": {
                stage: status.artifact_paths for stage, status in manifest.stages.items()
            },
            "warnings": {
                stage: status.warnings for stage, status in manifest.stages.items() if status.warnings
            },
            "blocking_reasons": {
                stage: status.blocking_reasons for stage, status in manifest.stages.items() if status.blocking_reasons
            },
            "notes": [
                "This is a report-first end-to-end summary; it does not mutate registry state unless apply_registry_update was explicitly enabled.",
                "External model evaluation remains dry-run unless eval_mode=execute and run_eval are both set.",
            ],
        }
        Path(manifest.summary_report_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_or_create_manifest(self, request: EndToEndRequest, run_dir: Path) -> EndToEndManifest:
        now = self._now()
        manifest_path = run_dir / "end_to_end_run_manifest.json"
        if manifest_path.exists():
            payload = load_json_file(str(manifest_path))
            if isinstance(payload, dict):
                payload["request"] = request.model_dump(mode="json")
                payload["updated_at"] = now
                payload["run_dir"] = str(run_dir)
                payload["stage_status_path"] = str(run_dir / "stage_status.json")
                payload["summary_report_path"] = str(run_dir / "end_to_end_summary_report.json")
                return EndToEndManifest.model_validate(payload)
        return EndToEndManifest(
            run_id=request.run_id,
            created_at=now,
            updated_at=now,
            request=request,
            run_dir=str(run_dir),
            stage_status_path=str(run_dir / "stage_status.json"),
            summary_report_path=str(run_dir / "end_to_end_summary_report.json"),
            registry_mode="existing",
            active_registry_path=str(DEFAULT_REGISTRY_PATH),
            canonical_registry_path=str(DEFAULT_REGISTRY_PATH),
            scratch_registry_initialized=False,
            registry_entry_count_initial=0,
            notes=[
                "The central pipeline reuses existing report-first runners and records their original artifacts.",
                "Use --force-stage to rerun a completed stage, and --reuse-existing to avoid rerunning completed stages.",
            ],
        )

    def _expanded_stages(self, stages: List[PipelineStage]) -> List[PipelineStage]:
        if not stages:
            return STAGE_ORDER
        return stages

    def _artifact(self, manifest: EndToEndManifest, stage: str, key: str) -> Optional[str]:
        status = manifest.stages.get(stage)
        if not status:
            return None
        value = status.artifact_paths.get(key)
        return value if value else None

    def _summary_for(self, manifest: EndToEndManifest, stage: str) -> Dict[str, Any]:
        status = manifest.stages.get(stage)
        return dict(status.summary) if status else {}

    def _task_summary(self, manifest: EndToEndManifest) -> Dict[str, Any]:
        summary = self._summary_for(manifest, "task_generation")
        return summary if summary else {}

    def _skill_answer(self, source_summary: Dict[str, Any]) -> Dict[str, Any]:
        mode = source_summary.get("source_mode")
        registry_mode = source_summary.get("registry_mode")
        if registry_mode == "fresh_scratch" and mode == "existing":
            return {"status": "fresh_registry_not_populated", "evidence": source_summary}
        if mode == "existing":
            return {"status": "reused_existing_registry", "evidence": source_summary}
        if mode == "local":
            return {"status": "prompt_package_built_only", "evidence": source_summary}
        delta = source_summary.get("registry_entry_delta_this_run")
        update_mode = source_summary.get("registry_update_mode")
        if update_mode == "updated" and delta not in {None, 0}:
            return {"status": "registry_populated_for_this_run", "evidence": source_summary}
        return {
            "status": "observed" if delta not in {None, 0} else "no_registry_growth_or_update_skipped",
            "evidence": source_summary,
        }

    def _task_answer(self, task_summary: Dict[str, Any]) -> Dict[str, Any]:
        ready = int(task_summary.get("candidate_ready_count") or 0)
        states = task_summary.get("task_state_counts") or {}
        return {
            "status": "candidate_ready_tasks_present" if ready else "no_candidate_ready_tasks_observed",
            "candidate_ready_count": ready,
            "task_state_counts": states,
        }

    def _diversity_answer(self, review_summary: Dict[str, Any]) -> Dict[str, Any]:
        warnings = review_summary.get("diversity_warnings") or []
        return {
            "status": "no_diversity_warnings" if not warnings else "diversity_review_needed",
            "warnings": warnings,
        }

    def _model_separation_answer(self, eval_summary: Dict[str, Any]) -> Dict[str, Any]:
        usable = int(eval_summary.get("usable_summary_model_count") or 0)
        executed = int(eval_summary.get("executed_model_count") or 0)
        return {
            "status": "diagnostic_evidence_available" if usable >= 2 else "not_enough_executed_evidence",
            "executed_model_count": executed,
            "usable_summary_model_count": usable,
            "model_separation_profile_path": eval_summary.get("model_separation_profile_path"),
        }

    def _first_eval_case_dir(self, manifest_path: Path) -> Path:
        payload = self._safe_load(manifest_path)
        for case in payload.get("cases") or []:
            if not isinstance(case, dict):
                continue
            case_dir = Path(str(case.get("case_dir") or ""))
            if case_dir.exists() and (case_dir / "rw_task_export").exists():
                return case_dir
        raise ValueError(f"No eval-ready case_dir found in {manifest_path}")

    def _find_latest_source_artifact(self, manifest: EndToEndManifest, filename: str) -> Optional[Path]:
        source_status = manifest.stages.get("source_to_skills")
        if not source_status:
            return None
        roots = [
            Path(path)
            for key, path in source_status.artifact_paths.items()
            if key.endswith("root") or key.endswith("dir")
        ]
        for root in roots:
            if not root.exists():
                continue
            matches = sorted(root.rglob(filename), key=lambda path: path.stat().st_mtime, reverse=True)
            if matches:
                return matches[0]
        return None

    def _parse_json_stdout(self, stdout: str) -> Dict[str, Any]:
        text = stdout.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _safe_load(self, path: str | Path) -> Dict[str, Any]:
        path = Path(path)
        if not path.exists():
            return {}
        payload = load_json_file(str(path))
        return payload if isinstance(payload, dict) else {}

    def _prepare_registry_state(
        self,
        request: EndToEndRequest,
        run_dir: Path,
        manifest: EndToEndManifest,
    ) -> EndToEndManifest:
        resumed_active_path = Path(manifest.active_registry_path) if manifest.active_registry_path else None
        resumed_mode = manifest.registry_mode if resumed_active_path else None
        registry_mode = request.registry_mode or resumed_mode or "existing"
        if registry_mode == "fresh_scratch" and request.registry_path:
            raise ValueError("--registry-path cannot be combined with --registry-mode fresh_scratch.")

        if registry_mode == "fresh_scratch":
            active_path = run_dir / "00_run_state" / "v3_skill_registry.scratch.json"
            scratch_initialized = self._initialize_scratch_registry(active_path)
            if resumed_mode != "fresh_scratch":
                manifest.registry_entry_count_initial = 0
            manifest.registry_mode = "fresh_scratch"
            manifest.active_registry_path = str(active_path)
            manifest.canonical_registry_path = str(DEFAULT_REGISTRY_PATH)
            manifest.scratch_registry_initialized = manifest.scratch_registry_initialized or scratch_initialized or active_path.exists()
            return manifest

        if resumed_mode == "fresh_scratch" and request.registry_mode is None and request.registry_path is None:
            active_path = Path(manifest.active_registry_path)
            registry_mode = "fresh_scratch"
            manifest.registry_mode = registry_mode
            manifest.active_registry_path = str(active_path)
            manifest.canonical_registry_path = str(DEFAULT_REGISTRY_PATH)
            manifest.scratch_registry_initialized = active_path.exists()
            if manifest.registry_entry_count_initial == 0 and not active_path.exists():
                manifest.registry_entry_count_initial = 0
            return manifest

        active_path = Path(request.registry_path) if request.registry_path else Path(DEFAULT_REGISTRY_PATH)
        initial_count = manifest.registry_entry_count_initial
        if active_path != resumed_active_path:
            initial_count = self._registry_entry_count(active_path)
        elif registry_mode == "existing" and initial_count == 0 and active_path.exists():
            initial_count = self._registry_entry_count(active_path)
        elif initial_count == 0 and not manifest.stages:
            initial_count = self._registry_entry_count(active_path)
        manifest.registry_mode = registry_mode
        manifest.active_registry_path = str(active_path)
        manifest.canonical_registry_path = str(DEFAULT_REGISTRY_PATH)
        manifest.scratch_registry_initialized = False
        manifest.registry_entry_count_initial = initial_count
        return manifest

    def _initialize_scratch_registry(self, path: Path) -> bool:
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "registry_version": "v3.0",
                    "entry_count": 0,
                    "entries": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return True

    def _registry_entry_count(self, path: Path) -> int:
        return len(SkillRegistryBuilder().load_registry(path))

    def _registry_summary(self, manifest: EndToEndManifest) -> Dict[str, Any]:
        active_path = Path(manifest.active_registry_path)
        final_count = self._registry_entry_count(active_path) if active_path.exists() else 0
        return {
            "registry_mode": manifest.registry_mode,
            "active_registry_path": manifest.active_registry_path,
            "canonical_registry_path": manifest.canonical_registry_path,
            "scratch_registry_initialized": manifest.scratch_registry_initialized,
            "initial_entry_count": manifest.registry_entry_count_initial,
            "final_entry_count": final_count,
            "entry_delta": final_count - manifest.registry_entry_count_initial,
        }

    def _validate_stage_outcome(
        self,
        status: StageStatus,
        request: EndToEndRequest,
        manifest: EndToEndManifest,
    ) -> None:
        if status.stage == "source_to_skills":
            if manifest.registry_mode == "fresh_scratch" and request.source_mode == "existing":
                status.summary.setdefault("source_mode", "existing")
                status.summary["note"] = "Fresh scratch registry requires web or future local extraction that can populate skills."
                raise StageFailure(
                    "fresh_scratch requires source_to_skills to extract new skills; source-mode existing cannot populate an empty registry.",
                    status,
                )
            if manifest.registry_mode == "fresh_scratch" and request.source_mode == "local":
                raise StageFailure(
                    "fresh_scratch cannot continue from source-mode local yet because local mode only builds a prompt package and does not populate a registry.",
                    status,
                )
            if request.source_mode == "web":
                successful_batch_count = int(status.summary.get("successful_batch_count") or 0)
                batch_count = int(status.summary.get("batch_count") or 0)
                if batch_count > 0 and successful_batch_count == 0:
                    status.warnings.append(
                        "No topic collection finished successfully. Inspect the batch report before retrying."
                    )
                    raise StageFailure(
                        "source_to_skills did not produce any successful web collection or extraction batch, so downstream task generation was stopped.",
                        status,
                    )
                if batch_count > 0 and successful_batch_count < batch_count:
                    status.warnings.append(
                        "Only part of the requested web collection batch succeeded. Downstream stages will continue from the successful collections only."
                    )
            if manifest.registry_mode == "fresh_scratch":
                accepted_count = int(status.summary.get("accepted_count") or 0)
                final_count = self._registry_entry_count(Path(manifest.active_registry_path))
                status.summary["registry_entry_count_after"] = final_count
                if accepted_count == 0 or final_count == 0:
                    raise StageFailure(
                        "No accepted skills were written into the scratch registry, so Pipeline B cannot start from this fresh run.",
                        status,
                    )
        if status.stage == "registry_prepare":
            selected_count = int(status.summary.get("selected_count") or 0)
            if selected_count == 0:
                status.warnings.append(
                    "Seed set is empty. Increase topic/source coverage or inspect extraction and review reports before retrying."
                )
                raise StageFailure(
                    "registry_prepare produced an empty seed set; no skills are available for Pipeline B sampling.",
                    status,
                )

    def _should_write_registry(
        self,
        request: EndToEndRequest,
        manifest: EndToEndManifest,
    ) -> bool:
        if manifest.registry_mode == "fresh_scratch":
            return True
        return request.apply_registry_update

    def _stage_dir_name(self, stage: PipelineStage) -> str:
        index = STAGE_ORDER.index(stage) + 1
        return f"{index:02d}_{stage}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
