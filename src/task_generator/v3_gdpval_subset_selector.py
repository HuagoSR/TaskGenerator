from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple

from pydantic import BaseModel, Field

from task_generator.v3_gdpval_utils import compact_text, keyword_hits
from task_generator.v3_source_schema import load_json_file


SubsetBucket = Literal[
    "finance_audit_core",
    "finance_spreadsheet",
    "finance_report_memo",
    "policy_compliance_like",
    "hard_reference_tasks",
    "not_selected",
]


class GDPValSubsetSelectionRecord(BaseModel):
    task_id: str
    selected: bool
    selection_bucket: SubsetBucket
    selection_score: float
    sector: str
    occupation: str
    reference_file_count: int
    deliverable_file_count: int
    reference_file_extensions: List[str] = Field(default_factory=list)
    deliverable_file_extensions: List[str] = Field(default_factory=list)
    prompt_excerpt: str = ""
    prompt_keyword_hits: List[str] = Field(default_factory=list)
    selection_reasons: List[str] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)
    use: str = "eval_calibration_only"


class GDPValSubsetSelectionRequest(BaseModel):
    mirror_manifest_path: str
    output_dir: str
    target_count: int = 10


class GDPValSubsetManifest(BaseModel):
    subset_manifest_version: str = "v3.gdpval_subset_selector.1"
    request: GDPValSubsetSelectionRequest
    created_at: str
    dataset_name: str
    split: str
    target_count: int
    selected_count: int
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True
    selected_task_ids: List[str] = Field(default_factory=list)
    selected_records: List[GDPValSubsetSelectionRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValSubsetSelectionReport(BaseModel):
    selection_report_version: str = "v3.gdpval_subset_selection_report.1"
    request: GDPValSubsetSelectionRequest
    created_at: str
    selected_count: int
    considered_count: int
    bucket_counts: Dict[str, int] = Field(default_factory=dict)
    selected_task_ids: List[str] = Field(default_factory=list)
    selected_records: List[GDPValSubsetSelectionRecord] = Field(default_factory=list)
    excluded_examples: List[GDPValSubsetSelectionRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValSubsetSelector:
    PROMPT_KEYWORDS = [
        "audit",
        "account",
        "financial",
        "finance",
        "spreadsheet",
        "workbook",
        "excel",
        "memo",
        "report",
        "policy",
        "compliance",
        "reconcile",
        "reconciliation",
        "cross-check",
        "control",
        "exception",
        "variance",
        "budget",
        "invoice",
        "ledger",
    ]
    DOMAIN_KEYWORDS = [
        "audit",
        "account",
        "financial",
        "finance",
        "policy",
        "compliance",
        "budget",
        "invoice",
        "ledger",
        "reconcile",
        "reconciliation",
        "variance",
        "control",
    ]

    def build(
        self,
        *,
        mirror_manifest_path: str | Path,
        output_dir: str | Path,
        target_count: int = 10,
    ) -> Tuple[GDPValSubsetManifest, GDPValSubsetSelectionReport]:
        manifest_payload = load_json_file(str(mirror_manifest_path))
        mirror_dir = Path(mirror_manifest_path).resolve().parent
        request = GDPValSubsetSelectionRequest(
            mirror_manifest_path=str(mirror_manifest_path),
            output_dir=str(output_dir),
            target_count=target_count,
        )

        records = [
            self._build_selection_record(task_payload, mirror_dir)
            for task_payload in manifest_payload.get("tasks") or []
            if isinstance(task_payload, dict)
        ]
        selected_records = self._select_records(records, target_count)
        selected_ids = {record.task_id for record in selected_records}
        final_records = [
            record.model_copy(update={"selected": record.task_id in selected_ids})
            for record in records
        ]
        selected_final_records = [record for record in final_records if record.selected]
        excluded_examples = sorted(
            [record for record in final_records if not record.selected],
            key=lambda item: item.selection_score,
            reverse=True,
        )[: min(10, max(target_count, 5))]

        bucket_counts = defaultdict(int)
        for record in final_records:
            bucket_counts[record.selection_bucket] += 1

        subset_manifest = GDPValSubsetManifest(
            request=request,
            created_at=datetime.now(timezone.utc).isoformat(),
            dataset_name=str(manifest_payload.get("dataset_name") or ""),
            split=str(manifest_payload.get("split") or ""),
            target_count=target_count,
            selected_count=len(selected_final_records),
            selected_task_ids=[record.task_id for record in selected_final_records],
            selected_records=selected_final_records,
            notes=[
                "This subset is scoped for GDPVal finance/audit calibration only.",
                "Selection is heuristic and reviewable; it should not be treated as benchmark-grade taxonomy.",
                "Deliverable files remain metadata-only and are not imported into TaskGenerator generation paths.",
            ],
        )
        selection_report = GDPValSubsetSelectionReport(
            request=request,
            created_at=subset_manifest.created_at,
            selected_count=len(selected_final_records),
            considered_count=len(final_records),
            bucket_counts=dict(bucket_counts),
            selected_task_ids=subset_manifest.selected_task_ids,
            selected_records=selected_final_records,
            excluded_examples=excluded_examples,
            notes=[
                "Priority favors finance/audit/accounting/compliance tasks with spreadsheet, report, policy, or reconciliation signals.",
                "Bucket balancing is best-effort so the initial calibration slice is not dominated by one narrow motif family.",
            ],
        )

        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "gdpval_finance_audit_subset_manifest.json").write_text(
            subset_manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output_root / "gdpval_subset_selection_report.json").write_text(
            selection_report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return subset_manifest, selection_report

    def _build_selection_record(
        self,
        task_payload: Dict[str, Any],
        mirror_dir: Path,
    ) -> GDPValSubsetSelectionRecord:
        metadata_path = Path(str(task_payload.get("metadata_path") or ""))
        if not metadata_path.is_absolute():
            metadata_path = mirror_dir / metadata_path
        prompt_path = Path(str(task_payload.get("prompt_path") or ""))
        if not prompt_path.is_absolute():
            prompt_path = mirror_dir / prompt_path

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        prompt_text = prompt_path.read_text(encoding="utf-8")
        hits = keyword_hits(prompt_text, self.PROMPT_KEYWORDS)
        bucket, score, reasons, risks = self._score_task(metadata, prompt_text, hits)
        return GDPValSubsetSelectionRecord(
            task_id=str(task_payload.get("task_id") or ""),
            selected=False,
            selection_bucket=bucket,
            selection_score=score,
            sector=str(metadata.get("sector") or ""),
            occupation=str(metadata.get("occupation") or ""),
            reference_file_count=len(metadata.get("reference_files") or []),
            deliverable_file_count=len(metadata.get("deliverable_files") or []),
            reference_file_extensions=list(metadata.get("reference_file_extensions") or []),
            deliverable_file_extensions=list(metadata.get("deliverable_file_extensions") or []),
            prompt_excerpt=compact_text(prompt_text)[:500],
            prompt_keyword_hits=hits,
            selection_reasons=reasons,
            risk_notes=risks,
        )

    def _score_task(
        self,
        metadata: Dict[str, Any],
        prompt_text: str,
        hits: List[str],
    ) -> Tuple[SubsetBucket, float, List[str], List[str]]:
        sector = str(metadata.get("sector") or "").lower()
        occupation = str(metadata.get("occupation") or "").lower()
        reference_files = list(metadata.get("reference_files") or [])
        deliverable_files = list(metadata.get("deliverable_files") or [])
        prompt = compact_text(prompt_text).lower()

        score = 0.0
        reasons: List[str] = []
        risks: List[str] = []
        bucket_scores: Dict[SubsetBucket, float] = defaultdict(float)
        domain_match = False

        if any(term in occupation for term in ["account", "audit", "finance", "financial", "compliance"]):
            score += 3.0
            bucket_scores["finance_audit_core"] += 3.0
            reasons.append("occupation_matches_finance_audit_scope")
            domain_match = True
        if any(term in sector for term in ["finance", "insurance", "bank", "account", "audit"]):
            score += 2.0
            bucket_scores["finance_audit_core"] += 2.0
            reasons.append("sector_matches_finance_scope")
            domain_match = True
        if any(term in prompt for term in self.DOMAIN_KEYWORDS):
            domain_match = True
        if any(term in prompt for term in ["spreadsheet", "excel", "workbook", "table"]):
            score += 2.0
            bucket_scores["finance_spreadsheet"] += 3.0
            reasons.append("spreadsheet_signal_present")
        if any(term in prompt for term in ["memo", "report", "briefing", "summary"]):
            score += 1.5
            bucket_scores["finance_report_memo"] += 2.5
            reasons.append("report_or_memo_deliverable_signal_present")
        if any(term in prompt for term in ["policy", "compliance", "control", "regulation"]):
            score += 1.5
            bucket_scores["policy_compliance_like"] += 3.0
            reasons.append("policy_or_compliance_signal_present")
        if any(term in prompt for term in ["reconcile", "reconciliation", "cross-check", "compare", "variance"]):
            score += 1.5
            bucket_scores["finance_audit_core"] += 1.0
            bucket_scores["hard_reference_tasks"] += 1.5
            reasons.append("cross_file_reasoning_signal_present")
        if len(reference_files) >= 2:
            score += 1.0
            bucket_scores["hard_reference_tasks"] += 1.5
            reasons.append("multiple_reference_files_present")
        if len(reference_files) >= 4:
            score += 1.0
            bucket_scores["hard_reference_tasks"] += 1.0
            reasons.append("dense_reference_bundle_present")
        if len(deliverable_files) == 0:
            risks.append("deliverable_file_metadata_missing")
        if len(reference_files) == 0:
            risks.append("missing_reference_files")
        if len(reference_files) <= 1:
            risks.append("single_reference_file")
        if len(hits) <= 1:
            risks.append("weak_prompt_keyword_signal")
        if ".xlsx" in metadata.get("reference_file_extensions", []):
            bucket_scores["finance_spreadsheet"] += 2.0
            reasons.append("xlsx_reference_present")
        if any(ext in metadata.get("deliverable_file_extensions", []) for ext in [".docx", ".md", ".txt"]):
            bucket_scores["finance_report_memo"] += 1.5
        if any(ext in metadata.get("deliverable_file_extensions", []) for ext in [".xlsx", ".csv"]):
            bucket_scores["finance_spreadsheet"] += 1.0

        if len(reference_files) == 0:
            bucket_scores.clear()
            reasons.append("excluded_due_to_missing_reference_files")
        if not domain_match:
            bucket_scores.clear()
            reasons.append("excluded_due_to_weak_finance_audit_domain_match")
        if not bucket_scores:
            bucket: SubsetBucket = "not_selected"
        else:
            bucket = max(bucket_scores.items(), key=lambda item: item[1])[0]
        if score <= 0.0:
            bucket = "not_selected"
        return bucket, round(score, 2), reasons, risks

    def _select_records(
        self,
        records: List[GDPValSubsetSelectionRecord],
        target_count: int,
    ) -> List[GDPValSubsetSelectionRecord]:
        by_bucket: Dict[str, List[GDPValSubsetSelectionRecord]] = defaultdict(list)
        for record in sorted(records, key=lambda item: item.selection_score, reverse=True):
            if record.selection_bucket != "not_selected":
                by_bucket[record.selection_bucket].append(record)

        selected: List[GDPValSubsetSelectionRecord] = []
        selected_ids = set()
        preferred_bucket_order: List[SubsetBucket] = [
            "finance_audit_core",
            "finance_spreadsheet",
            "finance_report_memo",
            "policy_compliance_like",
            "hard_reference_tasks",
        ]

        for bucket in preferred_bucket_order:
            bucket_records = by_bucket.get(bucket, [])
            if bucket_records:
                candidate = bucket_records[0]
                selected.append(candidate)
                selected_ids.add(candidate.task_id)

        ranked = sorted(records, key=lambda item: item.selection_score, reverse=True)
        for record in ranked:
            if len(selected) >= target_count:
                break
            if record.task_id in selected_ids:
                continue
            if record.selection_bucket == "not_selected":
                continue
            selected.append(record)
            selected_ids.add(record.task_id)
        return selected[:target_count]
