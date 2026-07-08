from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_gdpval_rw_task_eval_adapter import slugify


def compact_text(text: str) -> str:
    return " ".join(text.split())


class GDPValTaskAnatomyRequest(BaseModel):
    subset_manifest_path: str
    mirror_manifest_path: Optional[str] = None
    clean_baseline_path: Optional[str] = None
    output_dir: str
    task_limit: int = 0
    task_ids: List[str] = Field(default_factory=list)


class CleanEvalSummary(BaseModel):
    evaluated: bool = False
    usable_for_gap_analysis: bool = False
    completion_status: str = "not_evaluated"
    model_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    score_gap: Optional[float] = None
    failure_reasons: List[str] = Field(default_factory=list)
    source_run_ids: List[str] = Field(default_factory=list)


class GDPValTaskAnatomyProfile(BaseModel):
    profile_version: str = "v3.gdpval_task_anatomy.1"
    task_id: str
    case_slug: str
    use: str = "eval_calibration_only"
    diagnostic_only: bool = True
    not_for_training_generation: bool = True
    industry: str = ""
    occupation: str = ""
    role: str = ""
    task_trigger: str = ""
    prompt_excerpt: str = ""
    prompt_char_count: int = 0
    selection_bucket: str = ""
    selection_reasons: List[str] = Field(default_factory=list)
    reference_file_count: int = 0
    deliverable_file_count: int = 0
    file_types: List[str] = Field(default_factory=list)
    reference_file_extensions: List[str] = Field(default_factory=list)
    deliverable_file_extensions: List[str] = Field(default_factory=list)
    deliverable_type: str = "unknown"
    deliverable_format: str = "unknown"
    requires_calculation: bool = False
    requires_cross_file_reasoning: bool = False
    requires_policy_application: bool = False
    requires_exception_handling: bool = False
    requires_uncertainty_handling: bool = False
    requires_visual_or_document_formatting: bool = False
    reasoning_requirements: List[str] = Field(default_factory=list)
    evidence_density: str = "low"
    ambiguity_level: str = "low"
    workflow_realism_features: List[str] = Field(default_factory=list)
    likely_skill_motifs: List[str] = Field(default_factory=list)
    rubric_focus_guess: List[str] = Field(default_factory=list)
    toolchain_risks: List[str] = Field(default_factory=list)
    clean_eval: CleanEvalSummary = Field(default_factory=CleanEvalSummary)
    llm_annotation_status: str = "not_requested"
    llm_annotation: Optional[Dict[str, Any]] = None


class GDPValTaskAnatomyDistribution(BaseModel):
    report_version: str = "v3.gdpval_task_anatomy_distribution.1"
    created_at: str
    task_count: int
    deliverable_type_counts: Dict[str, int] = Field(default_factory=dict)
    deliverable_format_counts: Dict[str, int] = Field(default_factory=dict)
    reference_file_extension_counts: Dict[str, int] = Field(default_factory=dict)
    deliverable_file_extension_counts: Dict[str, int] = Field(default_factory=dict)
    motif_counts: Dict[str, int] = Field(default_factory=dict)
    reasoning_requirement_counts: Dict[str, int] = Field(default_factory=dict)
    evidence_density_counts: Dict[str, int] = Field(default_factory=dict)
    ambiguity_level_counts: Dict[str, int] = Field(default_factory=dict)
    clean_eval_status_counts: Dict[str, int] = Field(default_factory=dict)
    selection_bucket_counts: Dict[str, int] = Field(default_factory=dict)


class GDPValTaskAnatomyReport(BaseModel):
    report_version: str = "v3.gdpval_task_anatomy_report.1"
    created_at: str
    request: GDPValTaskAnatomyRequest
    use: str = "eval_calibration_only"
    diagnostic_only: bool = True
    not_for_training_generation: bool = True
    task_count: int
    profile_jsonl_path: str
    distribution_report_path: str
    good_task_profiler_input_path: str
    profiles: List[GDPValTaskAnatomyProfile] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValTaskAnatomyExtractor:
    def build(self, request: GDPValTaskAnatomyRequest) -> GDPValTaskAnatomyReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        profiles_dir = output_dir / "task_profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        subset_manifest = self._read_json(Path(request.subset_manifest_path))
        mirror_manifest_path = self._resolve_mirror_manifest_path(request, subset_manifest)
        mirror_manifest = self._read_json(mirror_manifest_path)
        mirror_by_id = {str(item.get("task_id") or ""): item for item in mirror_manifest.get("tasks") or []}
        clean_by_id = self._load_clean_baseline(request.clean_baseline_path)
        selected = self._select_records(list(subset_manifest.get("selected_records") or []), request)

        profiles = [
            self._build_profile(
                selection=selection,
                mirror_record=mirror_by_id.get(str(selection.get("task_id") or ""), {}),
                clean_record=clean_by_id.get(str(selection.get("task_id") or "")),
            )
            for selection in selected
        ]
        for profile in profiles:
            task_dir = profiles_dir / profile.case_slug
            task_dir.mkdir(parents=True, exist_ok=True)
            self._write_json(task_dir / "task_anatomy_profile.json", profile.model_dump(mode="json"))

        jsonl_path = output_dir / "gdpval_task_anatomy.jsonl"
        jsonl_path.write_text(
            "".join(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False) + "\n" for profile in profiles),
            encoding="utf-8",
        )
        distribution = self._build_distribution(profiles)
        distribution_path = output_dir / "gdpval_task_anatomy_distribution.json"
        self._write_json(distribution_path, distribution.model_dump(mode="json"))
        profiler_input_path = output_dir / "good_task_profiler_input.json"
        self._write_json(profiler_input_path, self._build_profiler_input(profiles))
        report = GDPValTaskAnatomyReport(
            created_at=self._now(),
            request=request,
            task_count=len(profiles),
            profile_jsonl_path=str(jsonl_path),
            distribution_report_path=str(distribution_path),
            good_task_profiler_input_path=str(profiler_input_path),
            profiles=profiles,
            notes=[
                "Task anatomy is deterministic V1 and calibration-only.",
                "LLM annotation fields are reserved but not populated in this run.",
                "Clean eval fields come from the Phase 14.3 clean single-case baseline when available.",
            ],
        )
        self._write_json(output_dir / "gdpval_anatomy_summary_report.json", report.model_dump(mode="json"))
        return report

    def _resolve_mirror_manifest_path(self, request: GDPValTaskAnatomyRequest, subset_manifest: Dict[str, Any]) -> Path:
        if request.mirror_manifest_path:
            return Path(request.mirror_manifest_path).resolve()
        request_payload = subset_manifest.get("request") or {}
        return Path(str(request_payload.get("mirror_manifest_path") or "")).resolve()

    def _select_records(
        self,
        records: List[Dict[str, Any]],
        request: GDPValTaskAnatomyRequest,
    ) -> List[Dict[str, Any]]:
        if request.task_ids:
            ids = set(request.task_ids)
            return [record for record in records if str(record.get("task_id") or "") in ids]
        if request.task_limit > 0:
            return records[: request.task_limit]
        return records

    def _load_clean_baseline(self, path_value: Optional[str]) -> Dict[str, Dict[str, Any]]:
        if not path_value:
            return {}
        path = Path(path_value)
        if not path.exists():
            return {}
        payload = self._read_json(path)
        return {str(item.get("task_id") or ""): item for item in payload.get("tasks") or []}

    def _build_profile(
        self,
        *,
        selection: Dict[str, Any],
        mirror_record: Dict[str, Any],
        clean_record: Optional[Dict[str, Any]],
    ) -> GDPValTaskAnatomyProfile:
        task_id = str(selection.get("task_id") or mirror_record.get("task_id") or "")
        prompt = self._read_prompt(mirror_record)
        metadata = self._read_metadata(mirror_record)
        reference_exts = [str(item) for item in (selection.get("reference_file_extensions") or metadata.get("reference_file_extensions") or [])]
        deliverable_exts = [
            str(item) for item in (selection.get("deliverable_file_extensions") or metadata.get("deliverable_file_extensions") or [])
        ]
        prompt_text = compact_text(prompt)
        role = self._extract_role(prompt_text, selection)
        reasoning = self._reasoning_requirements(prompt_text, reference_exts, deliverable_exts, metadata)
        motifs = self._likely_motifs(prompt_text, reference_exts, deliverable_exts)
        clean_eval = self._clean_eval_summary(clean_record)
        return GDPValTaskAnatomyProfile(
            task_id=task_id,
            case_slug=slugify(task_id),
            industry=str(selection.get("sector") or metadata.get("sector") or ""),
            occupation=str(selection.get("occupation") or metadata.get("occupation") or ""),
            role=role,
            task_trigger=self._task_trigger(prompt_text),
            prompt_excerpt=prompt_text[:600],
            prompt_char_count=int(metadata.get("prompt_char_count") or len(prompt)),
            selection_bucket=str(selection.get("selection_bucket") or ""),
            selection_reasons=[str(item) for item in selection.get("selection_reasons") or []],
            reference_file_count=int(selection.get("reference_file_count") or metadata.get("reference_files") and len(metadata.get("reference_files")) or 0),
            deliverable_file_count=int(selection.get("deliverable_file_count") or metadata.get("deliverable_files") and len(metadata.get("deliverable_files")) or 0),
            file_types=sorted(set(reference_exts + deliverable_exts)),
            reference_file_extensions=reference_exts,
            deliverable_file_extensions=deliverable_exts,
            deliverable_type=self._deliverable_type(prompt_text, deliverable_exts),
            deliverable_format=self._deliverable_format(deliverable_exts),
            requires_calculation="calculation" in reasoning or "spreadsheet_calculation" in reasoning,
            requires_cross_file_reasoning="cross_file_synthesis" in reasoning,
            requires_policy_application="policy_application" in reasoning,
            requires_exception_handling="exception_handling" in reasoning,
            requires_uncertainty_handling="assumption_handling" in reasoning,
            requires_visual_or_document_formatting="visual_or_document_formatting" in reasoning,
            reasoning_requirements=reasoning,
            evidence_density=self._evidence_density(metadata, prompt_text),
            ambiguity_level=self._ambiguity_level(prompt_text),
            workflow_realism_features=self._workflow_features(prompt_text, metadata, role),
            likely_skill_motifs=motifs,
            rubric_focus_guess=self._rubric_focus_guess(prompt_text, deliverable_exts, reasoning),
            toolchain_risks=self._toolchain_risks(metadata, deliverable_exts, clean_eval),
            clean_eval=clean_eval,
        )

    def _read_prompt(self, mirror_record: Dict[str, Any]) -> str:
        path = Path(str(mirror_record.get("prompt_path") or ""))
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _read_metadata(self, mirror_record: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(str(mirror_record.get("metadata_path") or ""))
        if path.exists():
            return self._read_json(path)
        return mirror_record

    def _extract_role(self, prompt_text: str, selection: Dict[str, Any]) -> str:
        match = re.search(r"\bYou are (?:an?|the)?\s*([^\.]+)", prompt_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()[:160]
        occupation = str(selection.get("occupation") or "").strip()
        return occupation

    def _task_trigger(self, prompt_text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", prompt_text)
        for sentence in sentences[:4]:
            lowered = sentence.lower()
            if any(term in lowered for term in ["tasked", "asked", "responsible", "prepare", "create", "review"]):
                return sentence[:260]
        return prompt_text[:260]

    def _reasoning_requirements(
        self,
        prompt_text: str,
        reference_exts: List[str],
        deliverable_exts: List[str],
        metadata: Dict[str, Any],
    ) -> List[str]:
        lowered = prompt_text.lower()
        values: List[str] = []
        reference_count = len(metadata.get("reference_files") or [])
        if reference_count > 1:
            values.append("cross_file_synthesis")
        if any(ext == ".xlsx" for ext in reference_exts + deliverable_exts) or any(
            term in lowered for term in ["excel", "spreadsheet", "workbook", "schedule", "model"]
        ):
            values.append("spreadsheet_calculation")
        if any(term in lowered for term in ["sample", "sampling", "representative", "variance", "risk metric"]):
            values.append("sampling_or_quantitative_testing")
        if any(term in lowered for term in ["policy", "compliance", "contract", "agreement", "documentation"]):
            values.append("policy_application")
        if any(term in lowered for term in ["reconcile", "reconciliation", "cross-check", "tie out", "accuracy"]):
            values.append("reconciliation")
        if any(term in lowered for term in ["exception", "issue", "risk", "flag", "anomaly"]):
            values.append("exception_handling")
        if any(term in lowered for term in ["assume", "if no", "unclear", "estimate", "judgment"]):
            values.append("assumption_handling")
        if any(ext in {".pptx", ".docx", ".pdf"} for ext in deliverable_exts) or any(
            term in lowered for term in ["memo", "presentation", "slides", "deck", "report"]
        ):
            values.append("visual_or_document_formatting")
        return sorted(set(values))

    def _likely_motifs(self, prompt_text: str, reference_exts: List[str], deliverable_exts: List[str]) -> List[str]:
        lowered = prompt_text.lower()
        motifs: List[str] = []
        if any(term in lowered for term in ["audit", "sample", "testing", "risk metric"]):
            motifs.append("audit_sampling_and_testing")
        if any(term in lowered for term in ["reconcile", "reconciliation", "cross-check", "accuracy"]):
            motifs.append("cross_check_validation")
        if any(term in lowered for term in ["prepaid", "amortization", "invoice", "insurance"]):
            motifs.append("amortization_schedule")
        if any(term in lowered for term in ["month-end", "financial package", "financial reporting", "general ledger"]):
            motifs.append("month_end_financial_reporting")
        if any(term in lowered for term in ["policy", "claim", "reimbursement", "compliance"]):
            motifs.append("policy_application")
        if any(ext == ".xlsx" for ext in reference_exts + deliverable_exts):
            motifs.append("evidence_to_spreadsheet_deliverable")
        if any(ext == ".pptx" for ext in deliverable_exts) or any(term in lowered for term in ["presentation", "deck", "slides"]):
            motifs.append("evidence_to_executive_presentation")
        if not motifs:
            motifs.append("general_evidence_to_deliverable")
        return sorted(set(motifs))

    def _deliverable_type(self, prompt_text: str, deliverable_exts: List[str]) -> str:
        lowered = prompt_text.lower()
        if ".xlsx" in deliverable_exts:
            return "spreadsheet_workbook"
        if ".pptx" in deliverable_exts:
            return "slide_deck"
        if ".docx" in deliverable_exts:
            return "document_report"
        if ".pdf" in deliverable_exts:
            return "pdf_report"
        if any(term in lowered for term in ["excel", "workbook", "spreadsheet"]):
            return "spreadsheet_workbook"
        if any(term in lowered for term in ["presentation", "deck", "slides"]):
            return "slide_deck"
        if any(term in lowered for term in ["memo", "report"]):
            return "document_report"
        return "unknown"

    def _deliverable_format(self, deliverable_exts: List[str]) -> str:
        if not deliverable_exts:
            return "metadata_missing"
        return "+".join(sorted(deliverable_exts))

    def _evidence_density(self, metadata: Dict[str, Any], prompt_text: str) -> str:
        reference_count = len(metadata.get("reference_files") or [])
        prompt_len = len(prompt_text)
        if reference_count >= 5 or prompt_len >= 2500:
            return "high"
        if reference_count >= 2 or prompt_len >= 1200:
            return "medium"
        return "low"

    def _ambiguity_level(self, prompt_text: str) -> str:
        lowered = prompt_text.lower()
        hits = sum(1 for term in ["assume", "if no", "unclear", "judgment", "estimate", "review", "appropriate"] if term in lowered)
        if hits >= 3:
            return "high"
        if hits >= 1:
            return "medium"
        return "low"

    def _workflow_features(self, prompt_text: str, metadata: Dict[str, Any], role: str) -> List[str]:
        lowered = prompt_text.lower()
        features: List[str] = []
        if role:
            features.append("explicit_professional_role")
        if re.search(r"\b20\d{2}\b", prompt_text):
            features.append("specific_reporting_period")
        if any(term in lowered for term in ["executive", "leadership", "management", "client", "ceo"]):
            features.append("stakeholder_or_audience_context")
        if len(metadata.get("reference_files") or []) > 1:
            features.append("multi_reference_workflow")
        if any(term in lowered for term in ["account", "ledger", "coa", "balance"]):
            features.append("accounting_system_context")
        if any(term in lowered for term in ["reconcile", "tie out", "accuracy", "validate"]):
            features.append("validation_or_reconciliation_context")
        return sorted(set(features))

    def _rubric_focus_guess(self, prompt_text: str, deliverable_exts: List[str], reasoning: List[str]) -> List[str]:
        lowered = prompt_text.lower()
        values: List[str] = []
        if "spreadsheet_calculation" in reasoning:
            values.append("numeric_accuracy")
            values.append("formula_or_schedule_completeness")
        if "reconciliation" in reasoning:
            values.append("reconciliation_to_evidence")
        if "policy_application" in reasoning:
            values.append("policy_interpretation")
        if "visual_or_document_formatting" in reasoning or any(ext in {".pptx", ".docx", ".pdf"} for ext in deliverable_exts):
            values.append("deliverable_structure_and_clarity")
        if any(term in lowered for term in ["exception", "risk", "issue"]):
            values.append("issue_identification")
        return sorted(set(values)) or ["deliverable_completion"]

    def _toolchain_risks(
        self,
        metadata: Dict[str, Any],
        deliverable_exts: List[str],
        clean_eval: CleanEvalSummary,
    ) -> List[str]:
        risks: List[str] = []
        reference_count = len(metadata.get("reference_files") or [])
        if reference_count >= 10:
            risks.append("dense_reference_bundle")
        if reference_count == 1:
            risks.append("single_reference_file")
        if not deliverable_exts:
            risks.append("deliverable_metadata_missing")
        if ".pptx" in deliverable_exts:
            risks.append("slide_deck_packaging")
        if not clean_eval.evaluated:
            risks.append("no_clean_eval_yet")
        elif not clean_eval.usable_for_gap_analysis:
            risks.append("clean_eval_not_usable")
        if any("no sanitized deliverables" in reason for reason in clean_eval.failure_reasons):
            risks.append("model_missing_deliverable")
        return sorted(set(risks))

    def _clean_eval_summary(self, record: Optional[Dict[str, Any]]) -> CleanEvalSummary:
        if not record:
            return CleanEvalSummary()
        return CleanEvalSummary(
            evaluated=True,
            usable_for_gap_analysis=bool(record.get("usable_for_gap_analysis")),
            completion_status=str(record.get("completion_status") or "not_evaluated"),
            model_scores={str(key): value for key, value in (record.get("model_scores") or {}).items()},
            score_gap=record.get("score_gap"),
            failure_reasons=[str(item) for item in record.get("failure_reasons") or []],
            source_run_ids=[str(item) for item in record.get("source_run_ids") or []],
        )

    def _build_distribution(self, profiles: List[GDPValTaskAnatomyProfile]) -> GDPValTaskAnatomyDistribution:
        deliverable_type_counts = Counter(profile.deliverable_type for profile in profiles)
        deliverable_format_counts = Counter(profile.deliverable_format for profile in profiles)
        reference_ext_counts = Counter(ext for profile in profiles for ext in profile.reference_file_extensions)
        deliverable_ext_counts = Counter(ext for profile in profiles for ext in profile.deliverable_file_extensions)
        motif_counts = Counter(motif for profile in profiles for motif in profile.likely_skill_motifs)
        reasoning_counts = Counter(req for profile in profiles for req in profile.reasoning_requirements)
        return GDPValTaskAnatomyDistribution(
            created_at=self._now(),
            task_count=len(profiles),
            deliverable_type_counts=dict(deliverable_type_counts),
            deliverable_format_counts=dict(deliverable_format_counts),
            reference_file_extension_counts=dict(reference_ext_counts),
            deliverable_file_extension_counts=dict(deliverable_ext_counts),
            motif_counts=dict(motif_counts),
            reasoning_requirement_counts=dict(reasoning_counts),
            evidence_density_counts=dict(Counter(profile.evidence_density for profile in profiles)),
            ambiguity_level_counts=dict(Counter(profile.ambiguity_level for profile in profiles)),
            clean_eval_status_counts=dict(Counter(profile.clean_eval.completion_status for profile in profiles)),
            selection_bucket_counts=dict(Counter(profile.selection_bucket for profile in profiles)),
        )

    def _build_profiler_input(self, profiles: List[GDPValTaskAnatomyProfile]) -> Dict[str, Any]:
        return {
            "input_version": "v3.gdpval_good_task_profiler_input.1",
            "created_at": self._now(),
            "use": "eval_calibration_only",
            "diagnostic_only": True,
            "not_for_training_generation": True,
            "task_count": len(profiles),
            "tasks": [
                {
                    "task_id": profile.task_id,
                    "case_slug": profile.case_slug,
                    "source": "openai/gdpval",
                    "anatomy_profile": profile.model_dump(mode="json"),
                    "dimension_inputs": {
                        "gdpval_similarity": {
                            "industry": profile.industry,
                            "occupation": profile.occupation,
                            "deliverable_type": profile.deliverable_type,
                            "motifs": profile.likely_skill_motifs,
                        },
                        "model_separation_quality": profile.clean_eval.model_dump(mode="json"),
                        "evidence_closure": {
                            "reference_file_count": profile.reference_file_count,
                            "evidence_density": profile.evidence_density,
                            "requires_cross_file_reasoning": profile.requires_cross_file_reasoning,
                        },
                        "workflow_realism": {
                            "role": profile.role,
                            "features": profile.workflow_realism_features,
                        },
                        "evaluation_stability": {
                            "toolchain_risks": profile.toolchain_risks,
                            "ambiguity_level": profile.ambiguity_level,
                        },
                    },
                }
                for profile in profiles
            ],
        }

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
