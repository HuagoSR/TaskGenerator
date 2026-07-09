from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class Phase15ExternalEvalResultBuilderRequest(BaseModel):
    runbook_path: str
    output_dir: str
    result_output_path: str


class Phase15ExternalEvalResultBuilderRecord(BaseModel):
    item_id: str
    arm_id: str
    case_id: str
    model: str
    status: str
    score: Optional[float] = None
    grade_status: str = ""
    result_summary: str = ""
    source_record_id: str = ""
    contains_secret: bool = False
    raw_prompt_included: bool = False
    warnings: List[str] = Field(default_factory=list)


class Phase15ExternalEvalResultBuilderReport(BaseModel):
    report_version: str = "v3.phase15_external_eval_result_builder.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15ExternalEvalResultBuilderRequest
    records: List[Phase15ExternalEvalResultBuilderRecord] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    result_output_path: str
    notes: List[str] = Field(default_factory=list)


class Phase15ExternalEvalResultBuilder:
    """Build sanitized Phase 15 import records from completed runbook outputs."""

    def build(self, request: Phase15ExternalEvalResultBuilderRequest) -> Phase15ExternalEvalResultBuilderReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        runbook = load_json_file(request.runbook_path)
        records = [self._record_for_item(item) for item in runbook.get("items") or [] if isinstance(item, dict)]
        result_output_path = Path(request.result_output_path)
        result_output_path.parent.mkdir(parents=True, exist_ok=True)
        result_output_path.write_text(
            json.dumps({"records": [record.model_dump(mode="json", exclude={"warnings"}) for record in records]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report = Phase15ExternalEvalResultBuilderReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            records=records,
            summary=self._summary(records),
            result_output_path=str(result_output_path),
            notes=[
                "This builder reads local run reports and grade outputs only; it does not call external APIs.",
                "Generated records intentionally omit raw prompts, API keys, bearer tokens, and provider logs.",
                "If scores cannot be located, records remain failed or missing and the importer will block closeout.",
            ],
        )
        (output_dir / "phase15_external_eval_result_builder_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _record_for_item(self, item: Dict[str, Any]) -> Phase15ExternalEvalResultBuilderRecord:
        run_output_dir = Path(str(item.get("run_output_dir") or ""))
        run_report_path = run_output_dir / "rw_task_eval_run_report.json"
        warnings: List[str] = []
        run_report = load_json_file(str(run_report_path)) if run_report_path.exists() else {}
        if not run_report_path.exists():
            warnings.append("run_report_missing")
        run_status = str(run_report.get("run_status") or "missing")
        grade_dir_value = str(run_report.get("grade_output_dir") or "")
        grade_dir = Path(grade_dir_value) if grade_dir_value else None
        score = self._score_from_grade_dir(grade_dir) if grade_dir is not None else None
        if score is None and grade_dir is not None:
            warnings.append("score_not_found")
        completed = run_status == "completed" and score is not None
        status = "completed" if completed else ("failed" if run_report else "missing")
        summary_parts = [
            f"run_status={run_status}",
            f"grade_output_dir={grade_dir}" if grade_dir is not None else "grade_output_dir=missing",
        ]
        if score is not None:
            summary_parts.append(f"score={score}")
        return Phase15ExternalEvalResultBuilderRecord(
            item_id=str(item.get("item_id") or ""),
            arm_id=str(item.get("arm_id") or ""),
            case_id=str(item.get("case_id") or ""),
            model=str(item.get("model") or ""),
            status=status,
            score=score,
            grade_status="completed" if score is not None else "missing",
            result_summary="; ".join(summary_parts),
            source_record_id=str(run_report_path) if run_report_path.exists() else "",
            contains_secret=False,
            raw_prompt_included=False,
            warnings=warnings,
        )

    def _score_from_grade_dir(self, grade_dir: Path) -> Optional[float]:
        if not grade_dir.exists() or not grade_dir.is_dir():
            return None
        for path in sorted(grade_dir.rglob("*.json")):
            try:
                payload = load_json_file(str(path))
            except Exception:
                continue
            score = self._find_score(payload)
            if score is not None:
                return score
        return None

    def _find_score(self, payload: Any) -> Optional[float]:
        if isinstance(payload, dict):
            for key in ["score", "final_score", "overall_score", "grade", "mean_score"]:
                value = payload.get(key)
                parsed = self._optional_float(value)
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

    def _summary(self, records: List[Phase15ExternalEvalResultBuilderRecord]) -> Dict[str, Any]:
        return {
            "record_count": len(records),
            "completed_count": sum(1 for record in records if record.status == "completed"),
            "failed_count": sum(1 for record in records if record.status == "failed"),
            "missing_count": sum(1 for record in records if record.status == "missing"),
            "score_count": sum(1 for record in records if record.score is not None),
            "warning_count": sum(len(record.warnings) for record in records),
        }
