from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class Phase15ExternalEvalRunbookRequest(BaseModel):
    queue_report_path: str
    external_eval_template_path: str
    output_dir: str
    require_model: str = "gpt-4o-mini"
    require_case: str = "pipeline_b_batch_01_evidence_to_deliverable"
    command_timeout_seconds: int = 600


class Phase15ExternalEvalRunbookItem(BaseModel):
    item_id: str
    arm_id: str
    case_id: str
    model: str
    prep_report_path: str
    eval_input_dir: str
    run_output_dir: str
    commands: List[List[str]] = Field(default_factory=list)
    expected_result_record: Dict[str, Any] = Field(default_factory=dict)


class Phase15ExternalEvalRunbook(BaseModel):
    runbook_version: str = "v3.phase15_external_eval_runbook.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15ExternalEvalRunbookRequest
    items: List[Phase15ExternalEvalRunbookItem] = Field(default_factory=list)
    run_order: List[str] = Field(default_factory=list)
    generated_files: Dict[str, str] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15ExternalEvalRunbookBuilder:
    """Build a portable runbook for executing Phase 15 eval in a permitted environment."""

    REQUIRED_ARMS = ["baseline_deterministic", "generator_reform_only"]

    def build(self, request: Phase15ExternalEvalRunbookRequest) -> Phase15ExternalEvalRunbook:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        queue = load_json_file(request.queue_report_path)
        template = load_json_file(request.external_eval_template_path)
        expected_records = {
            str(record.get("item_id") or ""): record
            for record in template.get("expected_records") or []
            if isinstance(record, dict)
        }
        items = self._items(queue, expected_records, request)
        warnings = []
        if len(items) != 2:
            warnings.append("expected_two_paired_items_not_found")
        if [item.arm_id for item in items] != self.REQUIRED_ARMS:
            warnings.append("run_order_not_baseline_then_reform")

        script_path = output_dir / "run_phase15_first_pair_external_eval.ps1"
        runbook_path = output_dir / "phase15_external_eval_runbook.json"
        self._write_script(script_path, items, request)
        runbook = Phase15ExternalEvalRunbook(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            items=items,
            run_order=[item.item_id for item in items],
            generated_files={
                "powershell_script": str(script_path),
                "runbook": str(runbook_path),
                "external_eval_results_template": request.external_eval_template_path,
            },
            warnings=warnings,
            notes=[
                "Run this only in an environment permitted to send the task package to external model/API services.",
                "The script is intentionally sequential: baseline first, then reform, both for the same case/model.",
                "After execution, fill the sanitized results template and re-run the external eval importer.",
            ],
        )
        runbook_path.write_text(runbook.model_dump_json(indent=2), encoding="utf-8")
        return runbook

    def _items(
        self,
        queue: Dict[str, Any],
        expected_records: Dict[str, Dict[str, Any]],
        request: Phase15ExternalEvalRunbookRequest,
    ) -> List[Phase15ExternalEvalRunbookItem]:
        selected = []
        for item in queue.get("queue_items") or []:
            if item.get("arm_id") not in self.REQUIRED_ARMS:
                continue
            if item.get("case_id") != request.require_case:
                continue
            if item.get("model") != request.require_model:
                continue
            item_id = str(item.get("item_id") or "")
            selected.append(
                Phase15ExternalEvalRunbookItem(
                    item_id=item_id,
                    arm_id=str(item.get("arm_id") or ""),
                    case_id=str(item.get("case_id") or ""),
                    model=str(item.get("model") or ""),
                    prep_report_path=str(item.get("prep_report_path") or ""),
                    eval_input_dir=str(item.get("eval_input_dir") or ""),
                    run_output_dir=self._run_output_dir(str(item.get("arm_id") or ""), request),
                    commands=item.get("would_run_commands") or [],
                    expected_result_record=expected_records.get(item_id, {}),
                )
            )
        selected.sort(key=lambda item: self.REQUIRED_ARMS.index(item.arm_id) if item.arm_id in self.REQUIRED_ARMS else 99)
        return selected

    def _run_output_dir(self, arm_id: str, request: Phase15ExternalEvalRunbookRequest) -> str:
        suffix = "baseline_case01_gpt4omini_authorized" if arm_id == "baseline_deterministic" else "reform_case01_gpt4omini_authorized"
        return str(Path("artifacts") / "phase15" / "clean_eval_runs" / suffix)

    def _write_script(
        self,
        script_path: Path,
        items: List[Phase15ExternalEvalRunbookItem],
        request: Phase15ExternalEvalRunbookRequest,
    ) -> None:
        lines = [
            "# Phase 15 external clean-eval first-pair runner",
            "# Run only in an environment permitted to send this task package to external model/API services.",
            "$ErrorActionPreference = 'Stop'",
            "",
        ]
        for item in items:
            lines.extend(
                [
                    f"# {item.arm_id} / {item.case_id} / {item.model}",
                    f"& 'D:\\miniconda3\\envs\\taskgenerator\\python.exe' Test\\run_v3_rw_task_eval_runner.py --prep-report '{item.prep_report_path}' --output-dir '{item.run_output_dir}' --run-eval --command-timeout-seconds {request.command_timeout_seconds}",
                    "if ($LASTEXITCODE -ne 0) { throw 'Phase 15 eval item failed; stop before running the next item.' }",
                    "",
                ]
            )
        lines.extend(
            [
                "# After both commands finish, fill:",
                f"# {request.external_eval_template_path}",
                "# Then run:",
                "# & 'D:\\miniconda3\\envs\\taskgenerator\\python.exe' Test\\run_v3_phase15_external_eval_importer.py",
                "# & 'D:\\miniconda3\\envs\\taskgenerator\\python.exe' Test\\run_v3_phase15_promotion_postmortem.py --external-eval-authorization-status approved",
                "",
            ]
        )
        script_path.write_text("\n".join(lines), encoding="utf-8")
