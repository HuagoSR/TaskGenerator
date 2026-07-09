from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class Phase15ExternalEvalResultBuilderRequest(BaseModel):
    runbook_path: str
    queue_report_path: Optional[str] = None
    output_dir: str
    result_output_path: str
    permitted_eval_bundle_report_path: Optional[str] = None
    require_models: List[str] = Field(default_factory=list)
    require_cases: List[str] = Field(default_factory=list)


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
        queue = self._load_optional(request.queue_report_path)
        bundle = self._load_optional(request.permitted_eval_bundle_report_path)
        bundle_items = self._bundle_items_by_id(bundle)
        items = self._items_for_request(runbook, queue, request)
        records = [
            self._record_for_item(item, bundle_items.get(str(item.get("item_id") or "")))
            for item in items
            if isinstance(item, dict)
        ]
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
                "When a permitted-eval bundle report is provided, bundled grades are used as a fallback if run reports are absent.",
            ],
        )
        (output_dir / "phase15_external_eval_result_builder_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _items_for_request(
        self,
        runbook: Dict[str, Any],
        queue: Dict[str, Any],
        request: Phase15ExternalEvalResultBuilderRequest,
    ) -> List[Dict[str, Any]]:
        queue_items = [
            item for item in (queue.get("queue_items") or queue.get("items") or [])
            if isinstance(item, dict)
        ]
        if queue_items:
            return [
                item
                for item in queue_items
                if (not request.require_models or item.get("model") in request.require_models)
                and (not request.require_cases or item.get("case_id") in request.require_cases)
                and item.get("arm_id") in {"baseline_deterministic", "generator_reform_only"}
            ]
        return [item for item in runbook.get("items") or [] if isinstance(item, dict)]

    def _load_optional(self, path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {}
        payload_path = Path(path)
        if not payload_path.exists() or payload_path.is_dir():
            return {}
        try:
            return json.loads(payload_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def _bundle_items_by_id(self, bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        bundle_dir = Path(str(bundle.get("bundle_dir") or ""))
        items_by_id: Dict[str, Dict[str, Any]] = {}
        for item in bundle.get("bundled_items") or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("item_id") or "")
            if not item_id:
                continue
            enriched = dict(item)
            if bundle_dir:
                grade_dir = Path(str(item.get("bundled_grade_dir") or ""))
                result_dir = Path(str(item.get("bundled_result_dir") or ""))
                enriched["resolved_bundled_grade_dir"] = str(bundle_dir / grade_dir)
                enriched["resolved_bundled_result_dir"] = str(bundle_dir / result_dir)
            items_by_id[item_id] = enriched
        return items_by_id

    def _record_for_item(
        self,
        item: Dict[str, Any],
        bundled_item: Optional[Dict[str, Any]] = None,
    ) -> Phase15ExternalEvalResultBuilderRecord:
        run_output_dir = Path(str(item.get("run_output_dir") or ""))
        run_report_path = run_output_dir / "rw_task_eval_run_report.json"
        warnings: List[str] = []
        run_report = load_json_file(str(run_report_path)) if run_report_path.exists() else {}
        if not run_report_path.exists():
            warnings.append("run_report_missing")
        run_status = str(run_report.get("run_status") or "missing")
        grade_dir_value = str(run_report.get("grade_output_dir") or "")
        grade_dir = Path(grade_dir_value) if grade_dir_value else None
        score_source = "run_report_grade_dir"
        score = self._score_from_grade_dir(grade_dir) if grade_dir is not None else None
        bundled_grade_dir = self._bundled_grade_dir(bundled_item)
        if score is None and bundled_grade_dir is not None:
            bundle_score = self._score_from_grade_dir(bundled_grade_dir)
            if bundle_score is not None:
                score = bundle_score
                grade_dir = bundled_grade_dir
                score_source = "permitted_eval_bundle_grade_dir"
                warnings.append("score_loaded_from_permitted_eval_bundle")
        eval_input_grade_dir = self._eval_input_grade_dir(item)
        if score is None and eval_input_grade_dir is not None:
            eval_input_score = self._score_from_grade_dir(eval_input_grade_dir)
            if eval_input_score is not None:
                score = eval_input_score
                grade_dir = eval_input_grade_dir
                score_source = "eval_input_sibling_grade_dir"
                warnings.append("score_loaded_from_eval_input_sibling_grade_dir")
        if score is None and grade_dir is not None:
            warnings.append("score_not_found")
        completed = (run_status == "completed" and score is not None) or (
            run_status == "missing" and score is not None and grade_dir is not None
        )
        status = "completed" if completed else ("failed" if run_report else "missing")
        summary_parts = [
            f"run_status={run_status}",
            f"grade_output_dir={grade_dir}" if grade_dir is not None else "grade_output_dir=missing",
            f"score_source={score_source}",
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
            source_record_id=self._source_record_id(run_report_path, grade_dir, score),
            contains_secret=False,
            raw_prompt_included=False,
            warnings=warnings,
        )

    def _bundled_grade_dir(self, bundled_item: Optional[Dict[str, Any]]) -> Optional[Path]:
        if not bundled_item:
            return None
        grade_dir_value = str(bundled_item.get("resolved_bundled_grade_dir") or "")
        if not grade_dir_value:
            return None
        return Path(grade_dir_value)

    def _source_record_id(
        self,
        run_report_path: Path,
        grade_dir: Optional[Path],
        score: Optional[float],
    ) -> str:
        if run_report_path.exists():
            return str(run_report_path)
        if score is not None and grade_dir is not None:
            return str(grade_dir)
        return ""

    def _eval_input_grade_dir(self, item: Dict[str, Any]) -> Optional[Path]:
        eval_input_dir = str(item.get("eval_input_dir") or "")
        if not eval_input_dir:
            return None
        return Path(f"{eval_input_dir}_grades")

    def _score_from_grade_dir(self, grade_dir: Path) -> Optional[float]:
        if not grade_dir.exists() or not grade_dir.is_dir():
            return None
        for path in sorted(grade_dir.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            score = self._find_score(payload)
            if score is not None:
                return score
        return None

    def _find_score(self, payload: Any) -> Optional[float]:
        if isinstance(payload, dict):
            total_score = self._optional_float(payload.get("total_score"))
            max_possible_score = self._optional_float(payload.get("max_possible_score"))
            if total_score is not None and max_possible_score is not None and max_possible_score > 0:
                return total_score / max_possible_score
            for key in ["score", "final_score", "overall_score", "grade", "mean_score", "total_score"]:
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
