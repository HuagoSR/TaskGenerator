from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class Phase16ExternalEvalResultBuilderRequest(BaseModel):
    runbook_path: str = "artifacts/phase16/production_eval_prep/phase16_external_eval_runbook.json"
    output_dir: str = "artifacts/phase16/production_eval_prep/result_builder"
    result_output_path: str = "artifacts/phase16/production_eval_prep/phase16_external_eval_results.sanitized.json"
    existing_result_paths: List[str] = Field(default_factory=list)


class Phase16ExternalEvalResultRecord(BaseModel):
    case_id: str
    arm_id: str
    evaluated_model: str
    grader_model: str = "gpt-5.4-pro"
    score: Optional[float] = None
    run_status: str
    contains_secret: bool = False
    raw_prompt_included: bool = False
    source_item_id: str = ""
    source_record_id: str = ""
    result_summary: str = ""
    warnings: List[str] = Field(default_factory=list)


class Phase16ExternalEvalResultBuilderReport(BaseModel):
    report_version: str = "v3.phase16_external_eval_result_builder.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase16ExternalEvalResultBuilderRequest
    records: List[Phase16ExternalEvalResultRecord] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    result_output_path: str
    notes: List[str] = Field(default_factory=list)


class Phase16ExternalEvalResultBuilder:
    """Build sanitized Phase16 clean-eval import records from rw-task run outputs."""

    def build(self, request: Phase16ExternalEvalResultBuilderRequest) -> Phase16ExternalEvalResultBuilderReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        runbook = load_json_file(request.runbook_path)
        existing_records = self._existing_records(request.existing_result_paths)
        run_records = [self._record_for_item(item) for item in runbook.get("items") or [] if isinstance(item, dict)]
        records, merge_conflicts = self._merge_records(existing_records + run_records)
        result_output_path = Path(request.result_output_path)
        result_output_path.parent.mkdir(parents=True, exist_ok=True)
        result_output_path.write_text(
            json.dumps(
                {
                    "records": [record.model_dump(mode="json", exclude={"warnings"}) for record in records],
                    "merge_conflicts": merge_conflicts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        report = Phase16ExternalEvalResultBuilderReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            records=records,
            summary={**self._summary(records), "merge_conflicts": merge_conflicts, "merge_conflict_count": len(merge_conflicts)},
            result_output_path=str(result_output_path),
            notes=[
                "This builder does not call external APIs.",
                "It emits sanitized records only: no API keys, bearer tokens, raw prompts, or provider logs.",
                "Import the result_output_path through Test/run_v3_phase16_clean_eval_gate.py.",
            ],
        )
        (output_dir / "phase16_external_eval_result_builder_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _existing_records(self, paths: List[str]) -> List[Phase16ExternalEvalResultRecord]:
        records: List[Phase16ExternalEvalResultRecord] = []
        for raw_path in paths:
            payload = load_json_file(raw_path)
            for item in payload.get("records") or []:
                if isinstance(item, dict):
                    records.append(Phase16ExternalEvalResultRecord.model_validate(item))
        return records

    def _merge_records(
        self,
        records: List[Phase16ExternalEvalResultRecord],
    ) -> tuple[List[Phase16ExternalEvalResultRecord], List[Dict[str, Any]]]:
        merged: Dict[tuple[str, str, str], Phase16ExternalEvalResultRecord] = {}
        conflicts: List[Dict[str, Any]] = []
        for record in records:
            key = (record.case_id, record.arm_id, record.evaluated_model)
            previous = merged.get(key)
            if previous is None:
                merged[key] = record
                continue
            if previous.run_status == "completed" and record.run_status != "completed":
                continue
            if record.run_status == "completed" and previous.run_status != "completed":
                merged[key] = record
                continue
            comparable = (
                previous.grader_model == record.grader_model
                and previous.run_status == record.run_status
                and previous.score == record.score
                and previous.contains_secret == record.contains_secret
                and previous.raw_prompt_included == record.raw_prompt_included
            )
            if not comparable:
                conflicts.append({
                    "key": list(key),
                    "reason": "conflicting_duplicate_record",
                    "existing_score": previous.score,
                    "incoming_score": record.score,
                    "existing_grader": previous.grader_model,
                    "incoming_grader": record.grader_model,
                })
                continue
            if not previous.source_record_id and record.source_record_id:
                merged[key] = record
        return [merged[key] for key in sorted(merged)], conflicts

    def _record_for_item(self, item: Dict[str, Any]) -> Phase16ExternalEvalResultRecord:
        run_output_dir = Path(str(item.get("run_output_dir") or ""))
        run_report_path = run_output_dir / "rw_task_eval_run_report.json"
        warnings: List[str] = []
        run_report = load_json_file(str(run_report_path)) if run_report_path.exists() else {}
        if not run_report_path.exists():
            warnings.append("run_report_missing")
        run_status = str(run_report.get("run_status") or "missing")
        grade_dir = Path(str(run_report.get("grade_output_dir") or "")) if run_report.get("grade_output_dir") else None
        score_source = "run_report_grade_dir"
        score = self._score_from_grade_dir(grade_dir) if grade_dir else None
        if score is None:
            eval_grade_dir = self._eval_input_grade_dir(item)
            eval_score = self._score_from_grade_dir(eval_grade_dir) if eval_grade_dir else None
            if eval_score is not None:
                score = eval_score
                grade_dir = eval_grade_dir
                score_source = "eval_input_sibling_grade_dir"
                warnings.append("score_loaded_from_eval_input_sibling_grade_dir")
        status = "completed" if score is not None and run_status in {"completed", "missing"} else ("failed" if run_report else "missing")
        summary = [
            f"run_status={run_status}",
            f"score_source={score_source}",
            f"grade_output_dir={grade_dir}" if grade_dir else "grade_output_dir=missing",
        ]
        if score is not None:
            summary.append(f"score={score}")
        return Phase16ExternalEvalResultRecord(
            case_id=str(item.get("case_id") or ""),
            arm_id=str(item.get("arm_id") or ""),
            evaluated_model=str(item.get("model") or item.get("evaluated_model") or ""),
            score=score,
            run_status=status,
            source_item_id=str(item.get("item_id") or ""),
            source_record_id=str(run_report_path if run_report_path.exists() else grade_dir or ""),
            result_summary="; ".join(summary),
            warnings=warnings,
        )

    def _eval_input_grade_dir(self, item: Dict[str, Any]) -> Optional[Path]:
        eval_input_dir = str(item.get("eval_input_dir") or "")
        if not eval_input_dir:
            return None
        return Path(f"{eval_input_dir}_grades")

    def _score_from_grade_dir(self, grade_dir: Optional[Path]) -> Optional[float]:
        if not grade_dir or not grade_dir.exists() or not grade_dir.is_dir():
            return None
        for path in sorted(grade_dir.rglob("*.json")):
            try:
                score = self._find_score(json.loads(path.read_text(encoding="utf-8-sig")))
            except Exception:
                continue
            if score is not None:
                return score
        return None

    def _find_score(self, payload: Any) -> Optional[float]:
        if isinstance(payload, dict):
            total_score = self._optional_float(payload.get("total_score"))
            max_score = self._optional_float(payload.get("max_possible_score"))
            if total_score is not None and max_score is not None and max_score > 0:
                return total_score / max_score
            for key in ["score", "final_score", "overall_score", "grade", "mean_score", "total_score"]:
                parsed = self._optional_float(payload.get(key))
                if parsed is not None:
                    return parsed
            for value in payload.values():
                nested = self._find_score(value)
                if nested is not None:
                    return nested
        if isinstance(payload, list):
            scores = [self._find_score(item) for item in payload]
            numeric = [score for score in scores if score is not None]
            if numeric:
                return sum(numeric) / len(numeric)
        return None

    def _optional_float(self, value: Any) -> Optional[float]:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _summary(self, records: List[Phase16ExternalEvalResultRecord]) -> Dict[str, Any]:
        return {
            "record_count": len(records),
            "completed_count": sum(1 for record in records if record.run_status == "completed"),
            "failed_count": sum(1 for record in records if record.run_status == "failed"),
            "missing_count": sum(1 for record in records if record.run_status == "missing"),
            "score_count": sum(1 for record in records if record.score is not None),
            "warning_count": sum(len(record.warnings) for record in records),
        }


def build_phase16_external_eval_results(
    request: Phase16ExternalEvalResultBuilderRequest,
) -> Phase16ExternalEvalResultBuilderReport:
    return Phase16ExternalEvalResultBuilder().build(request)
