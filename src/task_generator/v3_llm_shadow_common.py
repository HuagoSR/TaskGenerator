from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


ShadowKind = Literal["goldenrun", "rubric", "realism_critic", "reference_narrative"]


KIND_CONFIG: Dict[ShadowKind, Dict[str, Any]] = {
    "goldenrun": {
        "dir": "llm_goldenrun_shadow",
        "shadow_name": "llm_golden_run_shadow.json",
        "comparison_name": "llm_golden_run_comparison_report.json",
        "inputs": ["candidate prompt", "candidate-visible reference files", "evidence_index", "deterministic GoldenRun", "rubric"],
        "metrics": ["unsupported_claim_rate", "valid_evidence_ref_rate", "missing_step_candidates"],
    },
    "rubric": {
        "dir": "llm_rubric_shadow",
        "shadow_name": "llm_rubric_shadow.json",
        "comparison_name": "llm_rubric_comparison_report.json",
        "inputs": ["task prompt", "reference file summary", "GoldenRun", "TrainingAnnotation", "deterministic rubric"],
        "metrics": ["hidden_info_violation_count", "format_noise_delta", "added_capability_criteria"],
    },
    "realism_critic": {
        "dir": "llm_realism_critic",
        "shadow_name": "llm_realism_critique_report.json",
        "comparison_name": "llm_realism_critique_comparison_report.json",
        "inputs": ["task prompt", "reference file manifest", "evidence dossier", "workflow archetype", "production QA report"],
        "metrics": ["realism_critique_alignment", "friction_signal_count", "workflow_realism_notes"],
    },
    "reference_narrative": {
        "dir": "llm_reference_narrative_suggestion",
        "shadow_name": "llm_reference_narrative_suggestion.json",
        "comparison_name": "llm_reference_narrative_comparison_report.json",
        "inputs": ["manager note", "audit workpaper narrative", "review comments", "policy clause wording", "exception explanation"],
        "metrics": ["ground_truth_mutation_count", "evidence_id_mutation_count", "narrative_improvement_candidates"],
    },
}


class LLMShadowRequest(BaseModel):
    release_manifest_path: str
    output_dir: str
    shadow_kind: ShadowKind
    task_limit: int = 5
    task_ids: List[str] = Field(default_factory=list)
    model: str = "not_run"
    mode: str = "prepare"


class LLMShadowTaskRecord(BaseModel):
    task_id: str
    source_case_id: str = ""
    motif: str = ""
    release_task_dir: str
    prompt_package_path: str
    shadow_report_path: str
    comparison_report_path: str
    shadow_status: str = "awaiting_llm_output"
    metric_status: str = "not_available_until_llm_output"
    unsupported_claim_rate: float | None = None
    valid_evidence_ref_rate: float | None = None
    hidden_info_violation_count: int | None = None
    ground_truth_mutation_count: int | None = None
    blocking_reasons: List[str] = Field(default_factory=list)
    diagnostic_only: bool = True
    not_release_artifact: bool = True


class LLMShadowBatchReport(BaseModel):
    report_version: str = "v3.llm_shadow_batch.1"
    created_at: str
    request: LLMShadowRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    not_release_artifact: bool = True
    selected_task_count: int
    shadow_kind: ShadowKind
    prepared_count: int
    awaiting_llm_output_count: int
    completed_metric_count: int
    records: List[LLMShadowTaskRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class LLMShadowBuilder:
    def build(self, request: LLMShadowRequest) -> LLMShadowBatchReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        release_manifest_path = Path(request.release_manifest_path)
        release = self._read_json(release_manifest_path)
        tasks = self._select_tasks(release, request)
        records = [self._build_task(request, release_manifest_path.parent, task) for task in tasks]
        report = LLMShadowBatchReport(
            created_at=self._now(),
            request=request,
            selected_task_count=len(tasks),
            shadow_kind=request.shadow_kind,
            prepared_count=sum(1 for record in records if not record.blocking_reasons),
            awaiting_llm_output_count=sum(1 for record in records if record.shadow_status == "awaiting_llm_output"),
            completed_metric_count=sum(1 for record in records if record.metric_status == "computed"),
            records=records,
            notes=[
                "This layer prepares LLM shadow packages and comparison shells only.",
                "It does not call external models in prepare mode and does not fabricate LLM outputs.",
                "LLM shadow artifacts stay under artifacts/phase14 and must not enter release bundles or overwrite deterministic artifacts.",
                "Metrics such as unsupported claim rate and evidence citation validity become computable after real LLM shadow outputs are attached.",
            ],
        )
        config = KIND_CONFIG[request.shadow_kind]
        self._write_json(output_dir / f"{config['dir']}_batch_report.json", report.model_dump(mode="json"))
        return report

    def _build_task(self, request: LLMShadowRequest, release_root: Path, task: Dict[str, Any]) -> LLMShadowTaskRecord:
        config = KIND_CONFIG[request.shadow_kind]
        task_id = str(task.get("task_id") or "")
        task_slug = self._slug(task_id)
        release_task_dir = release_root / str(task.get("release_task_dir") or "")
        task_output_dir = Path(request.output_dir) / config["dir"] / task_slug
        task_output_dir.mkdir(parents=True, exist_ok=True)
        prompt_package_path = task_output_dir / "llm_shadow_prompt_package.json"
        shadow_path = task_output_dir / config["shadow_name"]
        comparison_path = task_output_dir / config["comparison_name"]

        blocking_reasons: List[str] = []
        dataset_row: Dict[str, Any] = {}
        if not release_task_dir.exists():
            blocking_reasons.append("release_task_dir_missing")
        else:
            dataset_row_path = release_task_dir / "dataset_row.json"
            if dataset_row_path.exists():
                dataset_row = self._read_json(dataset_row_path)
            else:
                blocking_reasons.append("dataset_row_missing")

        prompt_package = self._prompt_package(request.shadow_kind, task, release_task_dir, dataset_row)
        self._write_json(prompt_package_path, prompt_package)
        self._write_json(shadow_path, self._empty_shadow(request, task, prompt_package_path))
        self._write_json(comparison_path, self._comparison_shell(request, task, prompt_package_path, shadow_path, blocking_reasons))
        return LLMShadowTaskRecord(
            task_id=task_id,
            source_case_id=str(task.get("source_case_id") or ""),
            motif=str(task.get("motif") or ""),
            release_task_dir=str(release_task_dir),
            prompt_package_path=str(prompt_package_path),
            shadow_report_path=str(shadow_path),
            comparison_report_path=str(comparison_path),
            blocking_reasons=blocking_reasons,
        )

    def _prompt_package(
        self,
        shadow_kind: ShadowKind,
        task: Dict[str, Any],
        release_task_dir: Path,
        dataset_row: Dict[str, Any],
    ) -> Dict[str, Any]:
        artifacts_dir = release_task_dir / "artifacts"
        reference_files = list(dataset_row.get("reference_files") or [])
        artifact_paths = {
            name: str(artifacts_dir / name)
            for name in [
                "evidence_index.json",
                "golden_run.json",
                "rubric.json",
                "training_annotation.json",
                "production_qa_case_report.json",
                "real_worldness_report.json",
                "reference_file_plan.json",
                "task_blueprint.json",
            ]
            if (artifacts_dir / name).exists()
        }
        return {
            "package_version": "v3.llm_shadow_prompt_package.1",
            "created_at": self._now(),
            "shadow_kind": shadow_kind,
            "diagnostic_only": True,
            "not_release_artifact": True,
            "task_id": str(task.get("task_id") or dataset_row.get("task_id") or ""),
            "motif": str(task.get("motif") or dataset_row.get("motif") or ""),
            "prompt": str(dataset_row.get("prompt") or ""),
            "reference_files": reference_files,
            "deliverable_files": list(dataset_row.get("deliverable_files") or []),
            "rubric_excerpt": str(dataset_row.get("rubric") or "")[:6000],
            "required_inputs": KIND_CONFIG[shadow_kind]["inputs"],
            "artifact_paths": artifact_paths,
            "instructions": self._instructions(shadow_kind),
            "forbidden_actions": [
                "Do not edit reference files.",
                "Do not overwrite deterministic GoldenRun, rubric, annotation, or QA artifacts.",
                "Do not introduce hidden ground truth not visible in candidate-facing references.",
                "Do not promote this shadow output into a release bundle.",
            ],
        }

    def _empty_shadow(self, request: LLMShadowRequest, task: Dict[str, Any], prompt_package_path: Path) -> Dict[str, Any]:
        return {
            "shadow_version": f"v3.llm_{request.shadow_kind}_shadow.1",
            "created_at": self._now(),
            "task_id": str(task.get("task_id") or ""),
            "shadow_kind": request.shadow_kind,
            "model": request.model,
            "status": "awaiting_llm_output",
            "diagnostic_only": True,
            "not_release_artifact": True,
            "prompt_package_path": str(prompt_package_path),
            "llm_output": None,
            "notes": [
                "This is a placeholder shell created in prepare mode.",
                "Attach a real LLM shadow output here only after running an approved external model call.",
            ],
        }

    def _comparison_shell(
        self,
        request: LLMShadowRequest,
        task: Dict[str, Any],
        prompt_package_path: Path,
        shadow_path: Path,
        blocking_reasons: List[str],
    ) -> Dict[str, Any]:
        return {
            "comparison_version": f"v3.llm_{request.shadow_kind}_comparison.1",
            "created_at": self._now(),
            "task_id": str(task.get("task_id") or ""),
            "shadow_kind": request.shadow_kind,
            "status": "blocked" if blocking_reasons else "awaiting_llm_output",
            "metric_status": "not_available_until_llm_output",
            "diagnostic_only": True,
            "not_release_artifact": True,
            "prompt_package_path": str(prompt_package_path),
            "shadow_report_path": str(shadow_path),
            "metrics": {metric: None for metric in KIND_CONFIG[request.shadow_kind]["metrics"]},
            "blocking_reasons": blocking_reasons,
        }

    def _instructions(self, shadow_kind: ShadowKind) -> List[str]:
        if shadow_kind == "goldenrun":
            return [
                "Draft a shadow GoldenRun with intermediate reasoning and evidence references.",
                "Separate supported conclusions from unresolved items.",
                "Cite exact candidate-visible evidence IDs where possible.",
            ]
        if shadow_kind == "rubric":
            return [
                "Suggest rubric improvements that score real task competence, not cosmetic formatting alone.",
                "Flag any deterministic rubric criteria that appear duplicative or hidden-info dependent.",
            ]
        if shadow_kind == "realism_critic":
            return [
                "Critique whether the business trigger, files, evidence conflicts, and deliverable feel realistic.",
                "Identify frictional complexity that may measure tool noise instead of domain reasoning.",
            ]
        return [
            "Suggest more natural narrative wording without changing evidence IDs, amounts, policy IDs, statuses, conflicts, answers, or rubric truth.",
        ]

    def _select_tasks(self, release: Dict[str, Any], request: LLMShadowRequest) -> List[Dict[str, Any]]:
        tasks = [task for task in release.get("task_records") or [] if task.get("included_in_release")]
        if request.task_ids:
            wanted = set(request.task_ids)
            tasks = [task for task in tasks if str(task.get("task_id") or "") in wanted]
        return tasks[: max(0, request.task_limit)]

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
