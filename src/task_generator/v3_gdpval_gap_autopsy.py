from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GDPValGapAutopsyRequest(BaseModel):
    clean_baseline_path: str
    anatomy_jsonl_path: str
    output_dir: str
    task_limit: int = 0
    task_ids: List[str] = Field(default_factory=list)
    strong_model: Optional[str] = None
    weak_model: Optional[str] = None


class RubricGapItem(BaseModel):
    rubric_item_id: str = ""
    criterion: str = ""
    category: str = "other"
    max_score: float = 0.0
    strong_awarded: Optional[float] = None
    weak_awarded: Optional[float] = None
    strong_ratio: Optional[float] = None
    weak_ratio: Optional[float] = None
    ratio_gap: Optional[float] = None


class HypothesisEvidence(BaseModel):
    hypothesis_id: str
    status: str = "insufficient_evidence"
    rationale: str = ""


class GDPValGapAutopsyCase(BaseModel):
    task_id: str
    case_slug: str
    use: str = "eval_calibration_only"
    diagnostic_only: bool = True
    not_for_training_generation: bool = True
    selection_bucket: str = ""
    industry: str = ""
    occupation: str = ""
    deliverable_type: str = "unknown"
    deliverable_format: str = "unknown"
    reference_file_count: int = 0
    deliverable_file_count: int = 0
    reasoning_requirements: List[str] = Field(default_factory=list)
    likely_skill_motifs: List[str] = Field(default_factory=list)
    evidence_density: str = "unknown"
    ambiguity_level: str = "unknown"
    strong_model: Optional[str] = None
    weak_model: Optional[str] = None
    strong_score: Optional[float] = None
    weak_score: Optional[float] = None
    observed_gap: Optional[float] = None
    gap_band: str = "unusable"
    usable_for_gap_analysis: bool = False
    completion_status: str = "not_evaluated"
    top_gap_rubric_items: List[RubricGapItem] = Field(default_factory=list)
    rubric_gap_category_counts: Dict[str, int] = Field(default_factory=dict)
    strong_failure_modes: List[str] = Field(default_factory=list)
    weak_failure_modes: List[str] = Field(default_factory=list)
    productive_complexity_signals: List[str] = Field(default_factory=list)
    frictional_complexity_signals: List[str] = Field(default_factory=list)
    format_noise_suspected: bool = False
    tool_noise_suspected: bool = False
    grader_bias_suspected: bool = False
    human_review_needed: bool = False
    hypothesis_evidence: List[HypothesisEvidence] = Field(default_factory=list)
    autopsy_notes: List[str] = Field(default_factory=list)


class HypothesisLedgerItem(BaseModel):
    hypothesis_id: str
    statement: str
    supporting_cases: List[str] = Field(default_factory=list)
    contradicting_cases: List[str] = Field(default_factory=list)
    insufficient_cases: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValGapHypothesisLedger(BaseModel):
    report_version: str = "v3.gdpval_gap_hypothesis_ledger.1"
    created_at: str
    diagnostic_only: bool = True
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True
    hypothesis_count: int
    hypotheses: List[HypothesisLedgerItem] = Field(default_factory=list)


class GDPValGapAutopsyReport(BaseModel):
    report_version: str = "v3.gdpval_gap_autopsy_report.1"
    created_at: str
    request: GDPValGapAutopsyRequest
    diagnostic_only: bool = True
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True
    task_count: int
    usable_task_count: int
    unusable_task_count: int
    gap_band_counts: Dict[str, int] = Field(default_factory=dict)
    productive_complexity_signal_counts: Dict[str, int] = Field(default_factory=dict)
    frictional_complexity_signal_counts: Dict[str, int] = Field(default_factory=dict)
    rubric_gap_category_counts: Dict[str, int] = Field(default_factory=dict)
    case_autopsy_dir: str
    hypothesis_ledger_path: str
    cases: List[GDPValGapAutopsyCase] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


HYPOTHESES: Dict[str, str] = {
    "H1": "Cross-file evidence localization tends to increase useful model gap.",
    "H2": "Open-ended deliverable construction increases realism and runtime, but may reduce runnability.",
    "H3": "Format-heavy rubric items can inflate or distort apparent model gaps.",
    "H4": "Policy/application tasks separate models differently from pure spreadsheet calculation tasks.",
    "H5": "High-gap GDPVal tasks often contain implicit business constraints.",
    "H6": "Long runtime is valuable only when it reflects productive complexity, not toolchain friction.",
}


class GDPValGapAutopsyBuilder:
    def build(self, request: GDPValGapAutopsyRequest) -> GDPValGapAutopsyReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        case_dir = output_dir / "gdpval_gap_autopsy_cases"
        case_dir.mkdir(parents=True, exist_ok=True)

        clean_report = self._read_json(Path(request.clean_baseline_path))
        anatomy_by_id = self._read_anatomy_jsonl(Path(request.anatomy_jsonl_path))
        tasks = self._select_tasks(list(clean_report.get("tasks") or []), request)
        models = [str(item) for item in clean_report.get("models") or []]
        strong_model = request.strong_model or (models[0] if models else None)
        weak_model = request.weak_model or (models[1] if len(models) > 1 else None)

        cases = [
            self._build_case(
                clean_task=task,
                anatomy=anatomy_by_id.get(str(task.get("task_id") or ""), {}),
                strong_model=strong_model,
                weak_model=weak_model,
            )
            for task in tasks
        ]
        for case in cases:
            task_dir = case_dir / case.case_slug
            task_dir.mkdir(parents=True, exist_ok=True)
            self._write_json(task_dir / "gap_autopsy.json", case.model_dump(mode="json"))

        ledger = self._build_hypothesis_ledger(cases)
        ledger_path = output_dir / "gdpval_gap_hypothesis_ledger.json"
        self._write_json(ledger_path, ledger.model_dump(mode="json"))

        report = GDPValGapAutopsyReport(
            created_at=self._now(),
            request=request,
            task_count=len(cases),
            usable_task_count=sum(1 for case in cases if case.usable_for_gap_analysis),
            unusable_task_count=sum(1 for case in cases if not case.usable_for_gap_analysis),
            gap_band_counts=dict(Counter(case.gap_band for case in cases)),
            productive_complexity_signal_counts=dict(Counter(signal for case in cases for signal in case.productive_complexity_signals)),
            frictional_complexity_signal_counts=dict(Counter(signal for case in cases for signal in case.frictional_complexity_signals)),
            rubric_gap_category_counts=dict(Counter(category for case in cases for category, count in case.rubric_gap_category_counts.items() for _ in range(count))),
            case_autopsy_dir=str(case_dir),
            hypothesis_ledger_path=str(ledger_path),
            cases=cases,
            notes=[
                "This report is observational and calibration-only.",
                "It explains clean paired comparisons; it does not introduce a weighted GoodTaskScore.",
                "Unusable cases such as missing strong-model deliverables are retained as runnability/friction evidence, not model-quality evidence.",
            ],
        )
        self._write_json(output_dir / "gdpval_gap_autopsy_report.json", report.model_dump(mode="json"))
        return report

    def _select_tasks(self, tasks: List[Dict[str, Any]], request: GDPValGapAutopsyRequest) -> List[Dict[str, Any]]:
        if request.task_ids:
            ids = set(request.task_ids)
            return [task for task in tasks if str(task.get("task_id") or "") in ids]
        if request.task_limit > 0:
            return tasks[: request.task_limit]
        return tasks

    def _build_case(
        self,
        *,
        clean_task: Dict[str, Any],
        anatomy: Dict[str, Any],
        strong_model: Optional[str],
        weak_model: Optional[str],
    ) -> GDPValGapAutopsyCase:
        model_records = {str(item.get("model") or ""): item for item in clean_task.get("model_records") or []}
        strong_record = model_records.get(strong_model or "", {})
        weak_record = model_records.get(weak_model or "", {})
        strong_score = self._as_float((clean_task.get("model_scores") or {}).get(strong_model or ""))
        weak_score = self._as_float((clean_task.get("model_scores") or {}).get(weak_model or ""))
        observed_gap = self._as_float(clean_task.get("score_gap"))
        usable = bool(clean_task.get("usable_for_gap_analysis"))

        top_gap_items = self._top_gap_items(strong_record, weak_record) if usable else []
        category_counts = dict(Counter(item.category for item in top_gap_items))
        productive_signals = self._productive_signals(anatomy)
        frictional_signals = self._frictional_signals(clean_task, anatomy, strong_record, weak_record, usable)
        format_noise = self._format_noise_suspected(top_gap_items, anatomy)
        tool_noise = bool(frictional_signals) and not usable
        grader_bias = self._grader_bias_suspected(strong_record, weak_record)
        gap_band = self._gap_band(observed_gap, usable)
        hypothesis_evidence = self._hypothesis_evidence(
            anatomy=anatomy,
            clean_task=clean_task,
            gap_band=gap_band,
            usable=usable,
            productive_signals=productive_signals,
            frictional_signals=frictional_signals,
            format_noise=format_noise,
        )
        return GDPValGapAutopsyCase(
            task_id=str(clean_task.get("task_id") or anatomy.get("task_id") or ""),
            case_slug=str(clean_task.get("case_slug") or anatomy.get("case_slug") or ""),
            selection_bucket=str(clean_task.get("selection_bucket") or anatomy.get("selection_bucket") or ""),
            industry=str(clean_task.get("sector") or anatomy.get("industry") or ""),
            occupation=str(clean_task.get("occupation") or anatomy.get("occupation") or ""),
            deliverable_type=str(anatomy.get("deliverable_type") or "unknown"),
            deliverable_format=str(anatomy.get("deliverable_format") or "unknown"),
            reference_file_count=int(clean_task.get("reference_file_count") or anatomy.get("reference_file_count") or 0),
            deliverable_file_count=int(clean_task.get("deliverable_file_count") or anatomy.get("deliverable_file_count") or 0),
            reasoning_requirements=[str(item) for item in anatomy.get("reasoning_requirements") or []],
            likely_skill_motifs=[str(item) for item in anatomy.get("likely_skill_motifs") or []],
            evidence_density=str(anatomy.get("evidence_density") or "unknown"),
            ambiguity_level=str(anatomy.get("ambiguity_level") or "unknown"),
            strong_model=strong_model,
            weak_model=weak_model,
            strong_score=strong_score,
            weak_score=weak_score,
            observed_gap=observed_gap,
            gap_band=gap_band,
            usable_for_gap_analysis=usable,
            completion_status=str(clean_task.get("completion_status") or "not_evaluated"),
            top_gap_rubric_items=top_gap_items,
            rubric_gap_category_counts=category_counts,
            strong_failure_modes=[str(item) for item in strong_record.get("failure_reasons") or []],
            weak_failure_modes=[str(item) for item in weak_record.get("failure_reasons") or []],
            productive_complexity_signals=productive_signals,
            frictional_complexity_signals=frictional_signals,
            format_noise_suspected=format_noise,
            tool_noise_suspected=tool_noise,
            grader_bias_suspected=grader_bias,
            human_review_needed=(format_noise or tool_noise or grader_bias or gap_band in {"low", "unusable"}),
            hypothesis_evidence=hypothesis_evidence,
            autopsy_notes=self._autopsy_notes(gap_band, usable, productive_signals, frictional_signals, format_noise),
        )

    def _top_gap_items(self, strong_record: Dict[str, Any], weak_record: Dict[str, Any]) -> List[RubricGapItem]:
        strong_items = self._criteria_by_id(strong_record.get("grade_report_path"))
        weak_items = self._criteria_by_id(weak_record.get("grade_report_path"))
        items: List[RubricGapItem] = []
        for item_id, strong in strong_items.items():
            weak = weak_items.get(item_id)
            if not weak:
                continue
            max_score = self._as_float(strong.get("max")) or self._as_float(weak.get("max")) or 0.0
            if max_score <= 0:
                continue
            strong_awarded = self._as_float(strong.get("awarded"))
            weak_awarded = self._as_float(weak.get("awarded"))
            if strong_awarded is None or weak_awarded is None:
                continue
            strong_ratio = strong_awarded / max_score
            weak_ratio = weak_awarded / max_score
            ratio_gap = strong_ratio - weak_ratio
            if ratio_gap <= 0:
                continue
            criterion = str(strong.get("criterion") or weak.get("criterion") or "")
            items.append(
                RubricGapItem(
                    rubric_item_id=item_id,
                    criterion=criterion,
                    category=self._criterion_category(criterion),
                    max_score=max_score,
                    strong_awarded=strong_awarded,
                    weak_awarded=weak_awarded,
                    strong_ratio=strong_ratio,
                    weak_ratio=weak_ratio,
                    ratio_gap=ratio_gap,
                )
            )
        items.sort(key=lambda item: ((item.ratio_gap or 0.0), item.max_score), reverse=True)
        return items[:10]

    def _criteria_by_id(self, grade_report_path: Any) -> Dict[str, Dict[str, Any]]:
        if not grade_report_path:
            return {}
        path = Path(str(grade_report_path))
        if not path.exists():
            return {}
        payload = self._read_json(path)
        values: Dict[str, Dict[str, Any]] = {}
        for sample in payload.get("samples") or []:
            grading = sample.get("grading") or {}
            for item in grading.get("per_criterion") or []:
                item_id = str(item.get("rubric_item_id") or item.get("criterion") or "")
                if item_id:
                    values[item_id] = item
        return values

    def _criterion_category(self, criterion: str) -> str:
        text = criterion.lower()
        if any(token in text for token in ["policy", "eligible", "reimbursement", "coverage", "withholding rate"]):
            return "policy_application"
        if any(token in text for token in ["reconcile", "tie", "support", "evidence", "source", "invoice", "claim"]):
            return "evidence_reconciliation"
        if any(
            token in text
            for token in ["total", "amount", "calculate", "calculation", "formula", "equals", "gross", "net", "balance", "amortization", "variance", "rate"]
        ):
            return "numeric_accuracy"
        if any(token in text for token in ["format", "workbook", "sheet", "tab", "column", "table", "slide", "chart", "presentation"]):
            return "deliverable_structure"
        return "other"

    def _productive_signals(self, anatomy: Dict[str, Any]) -> List[str]:
        signals: List[str] = []
        if anatomy.get("requires_cross_file_reasoning"):
            signals.append("cross_file_reasoning")
        if anatomy.get("requires_policy_application"):
            signals.append("policy_application")
        if anatomy.get("requires_exception_handling"):
            signals.append("exception_handling")
        if anatomy.get("requires_uncertainty_handling"):
            signals.append("assumption_handling")
        if anatomy.get("evidence_density") == "high":
            signals.append("high_evidence_density")
        if anatomy.get("ambiguity_level") == "high":
            signals.append("high_ambiguity")
        if int(anatomy.get("reference_file_count") or 0) >= 4:
            signals.append("multi_reference_workflow")
        for motif in anatomy.get("likely_skill_motifs") or []:
            signals.append(f"motif:{motif}")
        return sorted(set(signals))

    def _frictional_signals(
        self,
        clean_task: Dict[str, Any],
        anatomy: Dict[str, Any],
        strong_record: Dict[str, Any],
        weak_record: Dict[str, Any],
        usable: bool,
    ) -> List[str]:
        signals: List[str] = []
        for risk in anatomy.get("toolchain_risks") or []:
            risk_value = str(risk)
            if risk_value == "single_reference_file":
                continue
            signals.append(risk_value)
        if int(anatomy.get("reference_file_count") or clean_task.get("reference_file_count") or 0) >= 10:
            signals.append("large_reference_bundle")
        if anatomy.get("deliverable_type") == "slide_deck":
            signals.append("slide_deck_packaging")
        for label, record in [("strong", strong_record), ("weak", weak_record)]:
            accepted = int(record.get("accepted_deliverable_count") or 0)
            listed = int(record.get("listed_deliverable_count") or 0)
            if listed > accepted:
                signals.append(f"{label}_auxiliary_or_extra_deliverables")
            if accepted == 0:
                signals.append(f"{label}_missing_sanitized_deliverable")
        if not usable:
            signals.append("not_usable_for_gap_analysis")
        return sorted(set(signals))

    def _format_noise_suspected(self, top_items: List[RubricGapItem], anatomy: Dict[str, Any]) -> bool:
        if not top_items:
            return False
        structure_count = sum(1 for item in top_items[:5] if item.category == "deliverable_structure")
        return structure_count >= 3 or anatomy.get("deliverable_type") in {"slide_deck", "document_or_report"}

    def _grader_bias_suspected(self, strong_record: Dict[str, Any], weak_record: Dict[str, Any]) -> bool:
        strong_path = str(strong_record.get("grade_report_path") or "")
        weak_path = str(weak_record.get("grade_report_path") or "")
        return bool(strong_path and weak_path and Path(strong_path).exists() != Path(weak_path).exists())

    def _hypothesis_evidence(
        self,
        *,
        anatomy: Dict[str, Any],
        clean_task: Dict[str, Any],
        gap_band: str,
        usable: bool,
        productive_signals: List[str],
        frictional_signals: List[str],
        format_noise: bool,
    ) -> List[HypothesisEvidence]:
        high_or_medium = gap_band in {"high", "medium"}
        low = gap_band == "low"
        values = [
            self._evidence(
                "H1",
                "supporting" if anatomy.get("requires_cross_file_reasoning") and high_or_medium else "contradicting" if anatomy.get("requires_cross_file_reasoning") and low else "insufficient_evidence",
                "Cross-file reasoning is present." if anatomy.get("requires_cross_file_reasoning") else "Cross-file reasoning is not a central requirement.",
            ),
            self._evidence(
                "H2",
                "supporting" if frictional_signals and (anatomy.get("deliverable_type") in {"slide_deck", "document_or_report"} or not usable) else "insufficient_evidence",
                "Deliverable or packaging friction is visible." if frictional_signals else "No strong deliverable-friction signal.",
            ),
            self._evidence(
                "H3",
                "supporting" if format_noise else "insufficient_evidence",
                "Top gap items or deliverable type suggest format noise." if format_noise else "Top gap items are not dominated by format structure.",
            ),
            self._evidence(
                "H4",
                "supporting" if anatomy.get("requires_policy_application") and high_or_medium else "contradicting" if anatomy.get("requires_policy_application") and low else "insufficient_evidence",
                "Policy/application is present." if anatomy.get("requires_policy_application") else "Policy/application is not central.",
            ),
            self._evidence(
                "H5",
                "supporting" if ("high_ambiguity" in productive_signals or "high_evidence_density" in productive_signals) and high_or_medium else "contradicting" if ("high_ambiguity" in productive_signals or "high_evidence_density" in productive_signals) and low else "insufficient_evidence",
                "High ambiguity or evidence density is present." if ("high_ambiguity" in productive_signals or "high_evidence_density" in productive_signals) else "No high implicit-constraint signal.",
            ),
            self._evidence(
                "H6",
                "supporting" if (not usable and frictional_signals) or (usable and productive_signals and not frictional_signals) else "insufficient_evidence",
                "Case distinguishes productive complexity from tool friction.",
            ),
        ]
        if clean_task.get("completion_status") == "needs_model_rerun":
            values[-1].status = "supporting"
            values[-1].rationale = "Needs rerun because at least one model side lacks a usable deliverable."
        return values

    def _evidence(self, hypothesis_id: str, status: str, rationale: str) -> HypothesisEvidence:
        return HypothesisEvidence(hypothesis_id=hypothesis_id, status=status, rationale=rationale)

    def _build_hypothesis_ledger(self, cases: List[GDPValGapAutopsyCase]) -> GDPValGapHypothesisLedger:
        buckets: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        notes: Dict[str, List[str]] = defaultdict(list)
        for case in cases:
            for evidence in case.hypothesis_evidence:
                case_ref = f"{case.case_slug}:{case.gap_band}"
                if evidence.status == "supporting":
                    buckets[evidence.hypothesis_id]["supporting"].append(case_ref)
                elif evidence.status == "contradicting":
                    buckets[evidence.hypothesis_id]["contradicting"].append(case_ref)
                else:
                    buckets[evidence.hypothesis_id]["insufficient"].append(case_ref)
                if evidence.rationale:
                    notes[evidence.hypothesis_id].append(f"{case.case_slug}: {evidence.rationale}")
        items = [
            HypothesisLedgerItem(
                hypothesis_id=hypothesis_id,
                statement=statement,
                supporting_cases=buckets[hypothesis_id]["supporting"],
                contradicting_cases=buckets[hypothesis_id]["contradicting"],
                insufficient_cases=buckets[hypothesis_id]["insufficient"],
                notes=notes[hypothesis_id][:12],
            )
            for hypothesis_id, statement in HYPOTHESES.items()
        ]
        return GDPValGapHypothesisLedger(created_at=self._now(), hypothesis_count=len(items), hypotheses=items)

    def _autopsy_notes(
        self,
        gap_band: str,
        usable: bool,
        productive_signals: List[str],
        frictional_signals: List[str],
        format_noise: bool,
    ) -> List[str]:
        notes: List[str] = []
        if usable:
            notes.append(f"Clean paired comparison is usable with {gap_band} observed gap.")
        else:
            notes.append("Case is not usable for model-gap analysis; retain as runnability or friction evidence.")
        if productive_signals:
            notes.append("Productive complexity signals are present and should be compared against generated-task profiles.")
        if frictional_signals:
            notes.append("Frictional complexity signals are present; avoid treating all failures as model capability.")
        if format_noise:
            notes.append("Format or deliverable-structure noise may contribute to the observed gap.")
        return notes

    def _gap_band(self, gap: Optional[float], usable: bool) -> str:
        if not usable or gap is None:
            return "unusable"
        if gap >= 0.5:
            return "high"
        if gap >= 0.15:
            return "medium"
        return "low"

    def _read_anatomy_jsonl(self, path: Path) -> Dict[str, Dict[str, Any]]:
        values: Dict[str, Dict[str, Any]] = {}
        if not path.exists():
            return values
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            values[str(item.get("task_id") or "")] = item
        return values

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _as_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
