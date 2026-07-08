from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_rw_task_eval_prep import RwTaskEvalPrep
from task_generator.v3_source_schema import load_json_file


QueueItemStatus = Literal["prepared", "blocked"]


class Phase15CleanEvalQueueRequest(BaseModel):
    ab_experiment_report_path: str
    output_dir: str
    models: List[str] = Field(default_factory=list)
    arms: List[str] = Field(default_factory=list)
    rw_task_root: str
    python_exe: str
    workers: int = 1


class Phase15CleanEvalQueueItem(BaseModel):
    item_id: str
    arm_id: str
    case_id: str
    model: str
    status: QueueItemStatus
    prep_report_path: Optional[str] = None
    eval_input_dir: Optional[str] = None
    would_run_commands: List[List[str]] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15CleanEvalQueueReport(BaseModel):
    report_version: str = "v3.phase15_clean_eval_queue.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15CleanEvalQueueRequest
    queue_items: List[Phase15CleanEvalQueueItem] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    execution_policy: Dict[str, Any] = Field(default_factory=dict)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15CleanEvalQueueBuilder:
    """Prepare one-case, one-model eval queue items for Phase 15 clean paired evaluation."""

    def build(self, request: Phase15CleanEvalQueueRequest) -> Phase15CleanEvalQueueReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ab_report = load_json_file(request.ab_experiment_report_path)
        selected_arms = set(request.arms or ["baseline_deterministic", "generator_reform_only"])
        models = request.models or ["gpt-4o-mini", "gemini-3-pro-preview"]

        queue_items: List[Phase15CleanEvalQueueItem] = []
        for arm in ab_report.get("arms") or []:
            arm_id = str(arm.get("arm_id") or "")
            if arm_id not in selected_arms:
                continue
            if arm.get("arm_status") != "executed" or not arm.get("manifest_path"):
                queue_items.append(self._blocked_arm_item(arm_id, "arm_not_executed_or_manifest_missing"))
                continue
            queue_items.extend(
                self._items_for_arm(
                    arm_id=arm_id,
                    manifest_path=Path(str(arm.get("manifest_path"))),
                    output_dir=output_dir,
                    models=models,
                    request=request,
                )
            )

        report = Phase15CleanEvalQueueReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            queue_items=queue_items,
            summary=self._summary(queue_items),
            execution_policy={
                "run_order": "one_case_one_model_at_a_time",
                "batch_external_calls_allowed": False,
                "llm_candidate_artifact_mutation_allowed": False,
                "recommended_first_pair": self._recommended_first_pair(queue_items),
            },
            next_actions=self._next_actions(queue_items),
            notes=[
                "This queue prepares rw-task eval inputs and command previews only; it does not run model APIs.",
                "Use the queue to execute one item at a time so timeout or provider instability cannot invalidate the full Phase 15 comparison.",
                "The queue is diagnostic until actual result and grade outputs are collected for matched baseline/reform cases.",
            ],
        )
        (output_dir / "phase15_clean_eval_queue_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _items_for_arm(
        self,
        arm_id: str,
        manifest_path: Path,
        output_dir: Path,
        models: List[str],
        request: Phase15CleanEvalQueueRequest,
    ) -> List[Phase15CleanEvalQueueItem]:
        manifest = load_json_file(str(manifest_path))
        items: List[Phase15CleanEvalQueueItem] = []
        for case in manifest.get("cases") or []:
            if case.get("task_state") != "candidate_ready":
                items.append(
                    Phase15CleanEvalQueueItem(
                        item_id=self._item_id(arm_id, str(case.get("case_id") or "unknown"), "all_models"),
                        arm_id=arm_id,
                        case_id=str(case.get("case_id") or "unknown"),
                        model="all_models",
                        status="blocked",
                        blocking_reasons=["case_not_candidate_ready"],
                    )
                )
                continue
            case_dir = Path(str(case.get("case_dir") or ""))
            export_dir = case_dir / "rw_task_export"
            validation_report_path = export_dir / "rw_task_export_validation_report.json"
            for model in models:
                item_id = self._item_id(arm_id, str(case.get("case_id") or "unknown"), model)
                eval_input_dir = output_dir / "eval_inputs" / arm_id / str(case.get("case_id") or "unknown") / model
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
                    Phase15CleanEvalQueueItem(
                        item_id=item_id,
                        arm_id=arm_id,
                        case_id=str(case.get("case_id") or "unknown"),
                        model=model,
                        status="prepared" if prep.prep_status == "prepared" else "blocked",
                        prep_report_path=str(eval_input_dir / "rw_task_eval_prep_report.json"),
                        eval_input_dir=str(eval_input_dir),
                        would_run_commands=prep.would_run_commands,
                        blocking_reasons=prep.blocking_reasons,
                        warnings=prep.warnings,
                        notes=[
                            "Run this item alone, then grade it before moving to the next queue item.",
                        ],
                    )
                )
        return items

    def _blocked_arm_item(self, arm_id: str, reason_code: str) -> Phase15CleanEvalQueueItem:
        return Phase15CleanEvalQueueItem(
            item_id=self._item_id(arm_id, "arm", "all_models"),
            arm_id=arm_id,
            case_id="arm",
            model="all_models",
            status="blocked",
            blocking_reasons=[reason_code],
        )

    def _summary(self, items: List[Phase15CleanEvalQueueItem]) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        arm_counts: Dict[str, int] = {}
        model_counts: Dict[str, int] = {}
        for item in items:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
            arm_counts[item.arm_id] = arm_counts.get(item.arm_id, 0) + 1
            model_counts[item.model] = model_counts.get(item.model, 0) + 1
        return {
            "queue_item_count": len(items),
            "prepared_item_count": sum(1 for item in items if item.status == "prepared"),
            "blocked_item_count": sum(1 for item in items if item.status == "blocked"),
            "status_counts": dict(sorted(status_counts.items())),
            "arm_counts": dict(sorted(arm_counts.items())),
            "model_counts": dict(sorted(model_counts.items())),
            "paired_case_count": self._paired_case_count(items),
        }

    def _paired_case_count(self, items: List[Phase15CleanEvalQueueItem]) -> int:
        by_case: Dict[str, set[str]] = {}
        for item in items:
            if item.status != "prepared":
                continue
            by_case.setdefault(item.case_id, set()).add(item.arm_id)
        return sum(
            1
            for arms in by_case.values()
            if {"baseline_deterministic", "generator_reform_only"}.issubset(arms)
        )

    def _recommended_first_pair(self, items: List[Phase15CleanEvalQueueItem]) -> List[str]:
        prepared = [item for item in items if item.status == "prepared"]
        if not prepared:
            return []
        first_model = prepared[0].model
        first_case = prepared[0].case_id
        return [
            item.item_id
            for item in prepared
            if item.case_id == first_case and item.model == first_model
        ][:2]

    def _next_actions(self, items: List[Phase15CleanEvalQueueItem]) -> List[str]:
        if not items or not any(item.status == "prepared" for item in items):
            return ["Resolve queue blockers before attempting external eval."]
        first_pair = self._recommended_first_pair(items)
        actions = [
            "Execute only the recommended first pair before expanding the run.",
            "After each item, inspect stdout/stderr and grade output before moving to the next model or case.",
        ]
        if first_pair:
            actions.append("Recommended first pair: " + ", ".join(first_pair))
        return actions

    def _item_id(self, arm_id: str, case_id: str, model: str) -> str:
        return "__".join(
            self._slug(part)
            for part in [arm_id, case_id, model]
            if part
        )

    def _slug(self, value: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_") or "item"
