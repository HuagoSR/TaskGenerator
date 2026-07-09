from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


ExternalEvalReadinessStatus = Literal["ready_for_permitted_environment", "blocked"]


class Phase15ExternalEvalReadinessRequest(BaseModel):
    runbook_path: str
    powershell_script_path: str
    results_template_path: str
    output_dir: str


class Phase15ExternalEvalReadinessReport(BaseModel):
    report_version: str = "v3.phase15_external_eval_readiness.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15ExternalEvalReadinessRequest
    readiness_status: ExternalEvalReadinessStatus
    item_count: int = 0
    run_order: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checked_paths: Dict[str, bool] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase15ExternalEvalReadinessChecker:
    """Validate that the Phase 15 external eval handoff package is structurally ready."""

    EXPECTED_ARMS = ["baseline_deterministic", "generator_reform_only"]

    def build(self, request: Phase15ExternalEvalReadinessRequest) -> Phase15ExternalEvalReadinessReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        runbook_path = Path(request.runbook_path)
        script_path = Path(request.powershell_script_path)
        template_path = Path(request.results_template_path)
        checked_paths = {
            "runbook_path": runbook_path.exists(),
            "powershell_script_path": script_path.exists(),
            "results_template_path": template_path.exists(),
        }
        blocking_reasons: List[str] = []
        warnings: List[str] = []
        runbook: Dict[str, Any] = {}
        template: Dict[str, Any] = {}
        script_text = ""

        for name, exists in checked_paths.items():
            if not exists:
                blocking_reasons.append(f"{name}_missing")
        if runbook_path.exists():
            runbook = load_json_file(str(runbook_path))
        if template_path.exists():
            template = load_json_file(str(template_path))
        if script_path.exists():
            script_text = script_path.read_text(encoding="utf-8", errors="replace")

        items = [item for item in runbook.get("items") or [] if isinstance(item, dict)]
        run_order = [str(item) for item in runbook.get("run_order") or []]
        item_ids = [str(item.get("item_id") or "") for item in items]
        arms = [str(item.get("arm_id") or "") for item in items]

        if len(items) != 2:
            blocking_reasons.append("expected_exactly_two_runbook_items")
        if arms != self.EXPECTED_ARMS:
            blocking_reasons.append("runbook_items_not_baseline_then_reform")
        if run_order != item_ids:
            blocking_reasons.append("run_order_does_not_match_items")
        for item in items:
            self._check_item(item, blocking_reasons, warnings)
        self._check_script(script_text, item_ids, blocking_reasons, warnings)
        self._check_template(template, item_ids, blocking_reasons, warnings)

        report = Phase15ExternalEvalReadinessReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            readiness_status="blocked" if blocking_reasons else "ready_for_permitted_environment",
            item_count=len(items),
            run_order=run_order,
            blocking_reasons=sorted(set(blocking_reasons)),
            warnings=sorted(set(warnings)),
            checked_paths=checked_paths,
            notes=[
                "This readiness check does not call external APIs and does not inspect secret values.",
                "A ready status means the handoff package is structurally consistent, not that this tenant can run it.",
                "Run the generated script only in an environment permitted to export the task package.",
            ],
        )
        (output_dir / "phase15_external_eval_readiness_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _check_item(
        self,
        item: Dict[str, Any],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> None:
        item_id = str(item.get("item_id") or "")
        prep_report = Path(str(item.get("prep_report_path") or ""))
        eval_input = Path(str(item.get("eval_input_dir") or ""))
        commands = item.get("commands") or []
        if not item_id:
            blocking_reasons.append("item_id_missing")
        if not prep_report.exists():
            blocking_reasons.append(f"prep_report_missing:{item_id}")
        if not eval_input.exists():
            blocking_reasons.append(f"eval_input_dir_missing:{item_id}")
        if len(commands) != 2:
            blocking_reasons.append(f"expected_two_commands:{item_id}")
        if commands and "v3_rw_task_eval_stirrup_wrapper" not in " ".join(str(part) for part in commands[0]):
            blocking_reasons.append(f"first_command_not_eval_wrapper:{item_id}")
        if len(commands) > 1 and "grade_deliverables" not in " ".join(str(part) for part in commands[1]):
            blocking_reasons.append(f"second_command_not_grader:{item_id}")
        if item.get("expected_result_record", {}).get("contains_secret") is not False:
            blocking_reasons.append(f"expected_record_secret_flag_not_false:{item_id}")
        if item.get("expected_result_record", {}).get("raw_prompt_included") is not False:
            warnings.append(f"expected_record_raw_prompt_flag_not_false:{item_id}")

    def _check_script(
        self,
        script_text: str,
        item_ids: List[str],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> None:
        if not script_text:
            return
        eval_command_count = script_text.count("Test\\run_v3_rw_task_eval_runner.py")
        if eval_command_count != len(item_ids):
            blocking_reasons.append("script_eval_command_count_mismatch")
        if "$LASTEXITCODE" not in script_text:
            blocking_reasons.append("script_missing_fail_fast_check")
        if "run_v3_phase15_external_eval_importer.py" not in script_text:
            warnings.append("script_missing_importer_followup_comment")
        if "run_v3_phase15_promotion_postmortem.py" not in script_text:
            warnings.append("script_missing_closeout_followup_comment")

    def _check_template(
        self,
        template: Dict[str, Any],
        item_ids: List[str],
        blocking_reasons: List[str],
        warnings: List[str],
    ) -> None:
        records = [record for record in template.get("expected_records") or [] if isinstance(record, dict)]
        record_ids = [str(record.get("item_id") or "") for record in records]
        if record_ids != item_ids:
            blocking_reasons.append("template_records_do_not_match_runbook_items")
        for record in records:
            item_id = str(record.get("item_id") or "")
            if record.get("contains_secret") is not False:
                blocking_reasons.append(f"template_secret_flag_not_false:{item_id}")
            if record.get("raw_prompt_included") is not False:
                warnings.append(f"template_raw_prompt_flag_not_false:{item_id}")
