from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


ExternalEvalImportStatus = Literal["blocked", "partial", "ready_for_closeout"]
ExternalEvalItemStatus = Literal["completed", "failed", "missing"]


class Phase15ExternalEvalImportRequest(BaseModel):
    queue_report_path: str
    external_results_path: str
    output_dir: str
    require_models: List[str] = Field(default_factory=list)
    require_cases: List[str] = Field(default_factory=list)


class Phase15ImportedEvalItem(BaseModel):
    item_id: str
    arm_id: str
    case_id: str
    model: str
    status: ExternalEvalItemStatus
    score: Optional[float] = None
    grade_status: Optional[str] = None
    result_summary: str = ""
    source_record_id: Optional[str] = None
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class Phase15PairedEvalComparison(BaseModel):
    case_id: str
    model: str
    baseline_item_id: str
    reform_item_id: str
    baseline_score: Optional[float] = None
    reform_score: Optional[float] = None
    score_delta_reform_minus_baseline: Optional[float] = None
    comparison_status: str
    notes: List[str] = Field(default_factory=list)


class Phase15ExternalEvalImportReport(BaseModel):
    report_version: str = "v3.phase15_external_eval_import.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15ExternalEvalImportRequest
    import_status: ExternalEvalImportStatus
    imported_items: List[Phase15ImportedEvalItem] = Field(default_factory=list)
    paired_comparisons: List[Phase15PairedEvalComparison] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    blocking_reasons: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15ExternalEvalTemplate(BaseModel):
    template_version: str = "v3.phase15_external_eval_results_template.1"
    instructions: List[str] = Field(default_factory=list)
    expected_records: List[Dict[str, Any]] = Field(default_factory=list)


class Phase15ExternalEvalImporter:
    """Import sanitized Phase 15 eval results produced in a separately permitted environment."""

    REQUIRED_ARMS = {"baseline_deterministic", "generator_reform_only"}

    def build(
        self,
        request: Phase15ExternalEvalImportRequest,
    ) -> Phase15ExternalEvalImportReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        queue = load_json_file(request.queue_report_path)
        external_results_path = Path(request.external_results_path)
        results = load_json_file(str(external_results_path)) if external_results_path.exists() else {}

        expected_items = self._expected_items(queue, request)
        records_by_item_id = self._records_by_item_id(results)
        imported_items = [
            self._import_item(expected, records_by_item_id.get(expected["item_id"]))
            for expected in expected_items
        ]
        paired = self._paired_comparisons(imported_items)
        blocking_reasons = self._blocking_reasons(imported_items, paired, expected_items, external_results_path)
        report = Phase15ExternalEvalImportReport(
            created_at=self._now(),
            request=request,
            import_status=self._import_status(blocking_reasons, paired),
            imported_items=imported_items,
            paired_comparisons=paired,
            summary=self._summary(imported_items, paired),
            blocking_reasons=blocking_reasons,
            next_actions=self._next_actions(blocking_reasons, paired),
            notes=[
                "This importer expects sanitized result summaries, not raw API keys or private provider logs.",
                "Scores are diagnostic until the grading schema and model pair are reviewed.",
                "The importer does not call external APIs and does not mutate generator or promotion state.",
            ],
        )
        (output_dir / "phase15_external_eval_import_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        self._write_template(queue, request, output_dir / "phase15_external_eval_results_template.json")
        return report

    def _expected_items(
        self,
        queue: Dict[str, Any],
        request: Phase15ExternalEvalImportRequest,
    ) -> List[Dict[str, str]]:
        required_models = set(request.require_models or ["gpt-4o-mini", "gemini-3-pro-preview"])
        required_cases = set(request.require_cases or [])
        expected = []
        for item in queue.get("queue_items") or []:
            if item.get("arm_id") not in self.REQUIRED_ARMS:
                continue
            if item.get("model") not in required_models:
                continue
            if required_cases and item.get("case_id") not in required_cases:
                continue
            expected.append(
                {
                    "item_id": str(item.get("item_id") or ""),
                    "arm_id": str(item.get("arm_id") or ""),
                    "case_id": str(item.get("case_id") or ""),
                    "model": str(item.get("model") or ""),
                }
            )
        expected.sort(key=lambda item: (item["case_id"], item["model"], item["arm_id"]))
        return expected

    def _records_by_item_id(self, results: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        records = {}
        for record in results.get("records") or []:
            if not isinstance(record, dict):
                continue
            item_id = str(record.get("item_id") or "")
            if item_id:
                records[item_id] = record
        return records

    def _import_item(
        self,
        expected: Dict[str, str],
        record: Optional[Dict[str, Any]],
    ) -> Phase15ImportedEvalItem:
        if record is None:
            return Phase15ImportedEvalItem(
                item_id=expected["item_id"],
                arm_id=expected["arm_id"],
                case_id=expected["case_id"],
                model=expected["model"],
                status="missing",
                blocking_reasons=["external_result_record_missing"],
            )
        blocking_reasons = []
        warnings = []
        status = str(record.get("status") or "missing")
        if status not in {"completed", "failed"}:
            blocking_reasons.append(f"invalid_status:{status}")
            status = "missing"
        score = self._optional_score(record.get("score"))
        if status == "completed" and score is None:
            blocking_reasons.append("completed_record_missing_numeric_score")
        for field_name in ["arm_id", "case_id", "model"]:
            if str(record.get(field_name) or "") != expected[field_name]:
                blocking_reasons.append(f"{field_name}_mismatch")
        if record.get("contains_secret") is True:
            blocking_reasons.append("record_contains_secret")
        if record.get("raw_prompt_included") is True:
            warnings.append("raw_prompt_included_in_result_record")
        return Phase15ImportedEvalItem(
            item_id=expected["item_id"],
            arm_id=expected["arm_id"],
            case_id=expected["case_id"],
            model=expected["model"],
            status=status,  # type: ignore[arg-type]
            score=score,
            grade_status=str(record.get("grade_status") or "") or None,
            result_summary=str(record.get("result_summary") or "")[:2000],
            source_record_id=str(record.get("source_record_id") or "") or None,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
        )

    def _paired_comparisons(
        self,
        items: List[Phase15ImportedEvalItem],
    ) -> List[Phase15PairedEvalComparison]:
        by_key: Dict[tuple[str, str], Dict[str, Phase15ImportedEvalItem]] = {}
        for item in items:
            by_key.setdefault((item.case_id, item.model), {})[item.arm_id] = item
        comparisons = []
        for (case_id, model), arms in sorted(by_key.items()):
            baseline = arms.get("baseline_deterministic")
            reform = arms.get("generator_reform_only")
            notes = []
            status = "complete"
            if baseline is None or reform is None:
                status = "missing_pair_member"
            elif baseline.status != "completed" or reform.status != "completed":
                status = "pair_not_completed"
            elif baseline.score is None or reform.score is None:
                status = "pair_missing_score"
            delta = None
            if baseline and reform and baseline.score is not None and reform.score is not None:
                delta = reform.score - baseline.score
                if delta > 0:
                    notes.append("Reform score is higher for this model/case pair.")
                elif delta < 0:
                    notes.append("Reform score is lower for this model/case pair.")
                else:
                    notes.append("No score delta for this model/case pair.")
            comparisons.append(
                Phase15PairedEvalComparison(
                    case_id=case_id,
                    model=model,
                    baseline_item_id=baseline.item_id if baseline else "",
                    reform_item_id=reform.item_id if reform else "",
                    baseline_score=baseline.score if baseline else None,
                    reform_score=reform.score if reform else None,
                    score_delta_reform_minus_baseline=delta,
                    comparison_status=status,
                    notes=notes,
                )
            )
        return comparisons

    def _blocking_reasons(
        self,
        items: List[Phase15ImportedEvalItem],
        paired: List[Phase15PairedEvalComparison],
        expected_items: List[Dict[str, str]],
        external_results_path: Path,
    ) -> List[str]:
        reasons = []
        if not external_results_path.exists():
            reasons.append("external_results_path_missing")
        if not expected_items:
            reasons.append("no_expected_queue_items")
        if any(item.blocking_reasons for item in items):
            reasons.append("imported_item_blockers_present")
        if not paired:
            reasons.append("no_paired_comparisons")
        if any(comparison.comparison_status != "complete" for comparison in paired):
            reasons.append("paired_comparisons_incomplete")
        return sorted(set(reasons))

    def _import_status(
        self,
        blocking_reasons: List[str],
        paired: List[Phase15PairedEvalComparison],
    ) -> ExternalEvalImportStatus:
        if blocking_reasons:
            if any(comparison.comparison_status == "complete" for comparison in paired):
                return "partial"
            return "blocked"
        return "ready_for_closeout"

    def _summary(
        self,
        items: List[Phase15ImportedEvalItem],
        paired: List[Phase15PairedEvalComparison],
    ) -> Dict[str, Any]:
        completed_items = [item for item in items if item.status == "completed"]
        complete_pairs = [item for item in paired if item.comparison_status == "complete"]
        deltas = [
            item.score_delta_reform_minus_baseline
            for item in complete_pairs
            if item.score_delta_reform_minus_baseline is not None
        ]
        return {
            "expected_item_count": len(items),
            "completed_item_count": len(completed_items),
            "missing_item_count": sum(1 for item in items if item.status == "missing"),
            "failed_item_count": sum(1 for item in items if item.status == "failed"),
            "paired_comparison_count": len(paired),
            "complete_pair_count": len(complete_pairs),
            "mean_reform_minus_baseline_delta": mean(deltas) if deltas else None,
            "positive_delta_pair_count": sum(1 for delta in deltas if delta > 0),
            "negative_delta_pair_count": sum(1 for delta in deltas if delta < 0),
            "zero_delta_pair_count": sum(1 for delta in deltas if delta == 0),
        }

    def _next_actions(
        self,
        blocking_reasons: List[str],
        paired: List[Phase15PairedEvalComparison],
    ) -> List[str]:
        if "external_results_path_missing" in blocking_reasons:
            return [
                "Run the authorized eval commands in a separately permitted environment.",
                "Fill phase15_external_eval_results_template.json with sanitized item-level scores.",
                "Re-run this importer before updating Phase 15 closeout.",
            ]
        if blocking_reasons:
            return [
                "Resolve missing or invalid imported records.",
                "Import only sanitized summaries; do not include API keys, provider secrets, or raw private logs.",
            ]
        return [
            "Regenerate Phase 15 closeout with this import report as eval evidence.",
            "Review whether reform deltas justify promotion, rollback, or continued experiment isolation.",
        ]

    def _write_template(
        self,
        queue: Dict[str, Any],
        request: Phase15ExternalEvalImportRequest,
        output_path: Path,
    ) -> None:
        expected = self._expected_items(queue, request)
        template = Phase15ExternalEvalTemplate(
            instructions=[
                "Fill one record per expected item after running eval in a separately permitted environment.",
                "Do not include API keys, bearer tokens, full raw prompts, or private provider logs.",
                "Use a numeric score on a consistent 0-1 or 0-100 scale and document the scale in result_summary if needed.",
            ],
            expected_records=[
                {
                    "item_id": item["item_id"],
                    "arm_id": item["arm_id"],
                    "case_id": item["case_id"],
                    "model": item["model"],
                    "status": "completed",
                    "score": None,
                    "grade_status": "completed",
                    "result_summary": "",
                    "source_record_id": "",
                    "contains_secret": False,
                    "raw_prompt_included": False,
                }
                for item in expected
            ],
        )
        output_path.write_text(template.model_dump_json(indent=2), encoding="utf-8")

    def _optional_score(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
