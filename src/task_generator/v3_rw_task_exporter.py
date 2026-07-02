import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_b_package_assembler import (
    PackageArtifactRecord,
    PipelineBPackageManifest,
)
from task_generator.v3_rubric_builder import RubricArtifact
from task_generator.v3_source_schema import load_json_file


ExportDecision = Literal["blocked", "draft_exported", "exported"]


class PipelineBRwTaskExportRequest(BaseModel):
    package_manifest_path: str
    output_dir: str
    case_id: Optional[str] = None
    allow_revise_only: bool = False


class PipelineBRwTaskExportReport(BaseModel):
    export_version: str = "v3.rw_task_exporter.1"
    request: PipelineBRwTaskExportRequest
    package_id: str
    blueprint_id: str
    package_readiness: str
    quality_decision: str
    export_decision: ExportDecision
    case_id: str
    case_dir: Optional[str] = None
    reference_file_count: int = 0
    deliverable_file_count: int = 0
    rw_task_rubric_item_count: int = 0
    diagnostic_rubric_item_count: int = 0
    reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PipelineBRwTaskExporter:
    """Convert a staged Pipeline B package into an rw-task-style draft case directory."""

    def export(
        self,
        package_manifest_path: str | Path,
        output_dir: str | Path,
        case_id: str | None = None,
        allow_revise_only: bool = False,
    ) -> PipelineBRwTaskExportReport:
        manifest_path = Path(package_manifest_path)
        output_path = Path(output_dir)
        package_root = manifest_path.parent
        package_manifest = PipelineBPackageManifest.model_validate(load_json_file(str(manifest_path)))
        draft_row_path = package_root / "dataset_row_draft.json"
        draft_row = self._load_dataset_row_draft(draft_row_path)
        resolved_case_id = case_id or str(draft_row.get("task_id") or package_manifest.blueprint_id)
        request = PipelineBRwTaskExportRequest(
            package_manifest_path=str(manifest_path),
            output_dir=str(output_path),
            case_id=resolved_case_id,
            allow_revise_only=allow_revise_only,
        )

        if output_path.exists():
            shutil.rmtree(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        export_decision = self._export_decision(
            package_readiness=package_manifest.package_readiness,
            allow_revise_only=allow_revise_only,
        )
        reason_codes = self._reason_codes(
            package_manifest=package_manifest,
            export_decision=export_decision,
            allow_revise_only=allow_revise_only,
        )

        report = PipelineBRwTaskExportReport(
            request=request,
            package_id=package_manifest.package_id,
            blueprint_id=package_manifest.blueprint_id,
            package_readiness=package_manifest.package_readiness,
            quality_decision=package_manifest.diagnostics.quality_decision,
            export_decision=export_decision,
            case_id=resolved_case_id,
            case_dir=str(output_path) if export_decision != "blocked" else None,
            reference_file_count=0,
            deliverable_file_count=0,
            rw_task_rubric_item_count=0,
            diagnostic_rubric_item_count=0,
            reason_codes=reason_codes,
            notes=self._notes(export_decision, package_manifest.package_readiness),
        )

        if export_decision == "blocked":
            self._write_report(output_path / "rw_task_export_report.json", report)
            return report

        reference_records = self._candidate_visible_reference_records(package_manifest.artifacts)
        support_reference_records = self._support_reference_records(package_manifest.artifacts)
        dataset_row = self._normalized_dataset_row(
            draft_row=draft_row,
            case_id=resolved_case_id,
            reference_records=reference_records,
            package_manifest=package_manifest,
            export_decision=export_decision,
        )

        reference_dir = output_path / "reference_files"
        deliverable_dir = output_path / "deliverable_files"
        artifacts_dir = output_path / "artifacts"
        reference_dir.mkdir(parents=True, exist_ok=True)
        deliverable_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._copy_reference_files(package_root, reference_records, reference_dir)
        self._copy_support_reference_files(package_root, support_reference_records, artifacts_dir)
        self._copy_package_artifacts(package_root, package_manifest.artifacts, artifacts_dir)

        deliverable_manifest = {
            "case_id": resolved_case_id,
            "deliverables": dataset_row["deliverable_files"],
            "notes": [
                "Deliverable files are intentionally not pre-generated by the exporter.",
                "This manifest records the expected candidate-created outputs.",
            ],
        }
        (deliverable_dir / "expected_deliverables.json").write_text(
            json.dumps(deliverable_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_path / "dataset_row.json").write_text(
            json.dumps(dataset_row, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        report.reference_file_count = len(reference_records)
        report.deliverable_file_count = len(dataset_row["deliverable_files"])
        report.rw_task_rubric_item_count = dataset_row["extra"]["rw_task_rubric_filter"][
            "exported_item_count"
        ]
        report.diagnostic_rubric_item_count = dataset_row["extra"]["rw_task_rubric_filter"][
            "diagnostic_item_count"
        ]
        self._write_report(output_path / "rw_task_export_report.json", report)
        return report

    def _load_dataset_row_draft(self, draft_row_path: Path) -> Dict[str, Any]:
        return load_json_file(str(draft_row_path))

    def _export_decision(
        self,
        package_readiness: str,
        allow_revise_only: bool,
    ) -> ExportDecision:
        if package_readiness == "candidate_ready":
            return "exported"
        if package_readiness == "revise_only" and allow_revise_only:
            return "draft_exported"
        return "blocked"

    def _reason_codes(
        self,
        package_manifest: PipelineBPackageManifest,
        export_decision: ExportDecision,
        allow_revise_only: bool,
    ) -> List[str]:
        reason_codes = list(package_manifest.diagnostics.warning_reason_codes)
        if export_decision == "blocked":
            reason_codes.append(f"package_readiness:{package_manifest.package_readiness}")
            if package_manifest.package_readiness == "revise_only" and not allow_revise_only:
                reason_codes.append("allow_revise_only_required")
        if export_decision == "draft_exported":
            reason_codes.append("draft_revise_only_export")
        return sorted(set(reason_codes))

    def _notes(self, export_decision: ExportDecision, package_readiness: str) -> List[str]:
        notes = [
            "V3 rw-task exporter is a structural export layer and does not run models or evaluations.",
            "Support reference artifacts stay out of candidate-visible reference_files.",
        ]
        if export_decision == "draft_exported":
            notes.append(
                "This export is inspection-only because the package is revise_only and not final training data."
            )
        if export_decision == "blocked" and package_readiness != "candidate_ready":
            notes.append(
                "Formal export is blocked until package readiness becomes candidate_ready or revise-only export is explicitly allowed."
            )
        return notes

    def _candidate_visible_reference_records(
        self,
        artifacts: List[PackageArtifactRecord],
    ) -> List[PackageArtifactRecord]:
        return [
            record
            for record in artifacts
            if record.role == "reference_file"
            and record.copied
            and not self._is_support_reference_record(record)
        ]

    def _support_reference_records(
        self,
        artifacts: List[PackageArtifactRecord],
    ) -> List[PackageArtifactRecord]:
        return [
            record
            for record in artifacts
            if record.role == "reference_file"
            and record.copied
            and self._is_support_reference_record(record)
        ]

    def _normalized_dataset_row(
        self,
        draft_row: Dict[str, Any],
        case_id: str,
        reference_records: List[PackageArtifactRecord],
        package_manifest: PipelineBPackageManifest,
        export_decision: ExportDecision,
    ) -> Dict[str, Any]:
        draft_extra = dict(draft_row.get("extra") or {})
        draft_extra["rw_task_exporter"] = {
            "export_version": "v3.rw_task_exporter.1",
            "export_decision": export_decision,
            "package_id": package_manifest.package_id,
            "blueprint_id": package_manifest.blueprint_id,
            "manifest_id": self._stable_id("rwexp", [package_manifest.package_id, case_id]),
        }
        draft_extra["not_final_training_data"] = export_decision != "exported"
        if export_decision == "draft_exported":
            draft_extra["export_status"] = "draft_revise_only"
        else:
            draft_extra["export_status"] = "candidate_ready_export"
        draft_extra["rw_task_export_ready"] = export_decision == "exported"
        normalized_rubric_items = self._normalize_rubric_payload(draft_row.get("rubric_json"))
        rubric_filter_summary = self._rubric_filter_summary(draft_row.get("rubric_json"), normalized_rubric_items)
        draft_extra["rw_task_rubric_filter"] = rubric_filter_summary

        return {
            "task_id": case_id,
            "sector": draft_row.get("sector"),
            "occupation": draft_row.get("occupation"),
            "motif": draft_row.get("motif"),
            "prompt": draft_row.get("prompt"),
            "reference_files": [record.package_path for record in reference_records],
            "deliverable_files": list(draft_row.get("deliverable_files") or []),
            "rubric": self._rw_task_rubric_text(normalized_rubric_items),
            "rubric_json": self._rw_task_rubric_json(normalized_rubric_items),
            "extra": draft_extra,
        }

    def _copy_reference_files(
        self,
        package_root: Path,
        reference_records: List[PackageArtifactRecord],
        reference_dir: Path,
    ) -> None:
        for record in reference_records:
            source_path = package_root / Path(record.package_path)
            target_path = reference_dir / Path(record.package_path).name
            shutil.copy2(source_path, target_path)

    def _copy_support_reference_files(
        self,
        package_root: Path,
        support_reference_records: List[PackageArtifactRecord],
        artifacts_dir: Path,
    ) -> None:
        if not support_reference_records:
            return
        support_dir = artifacts_dir / "reference_support"
        support_dir.mkdir(parents=True, exist_ok=True)
        for record in support_reference_records:
            source_path = package_root / Path(record.package_path)
            target_path = support_dir / Path(record.package_path).name
            shutil.copy2(source_path, target_path)

    def _copy_package_artifacts(
        self,
        package_root: Path,
        artifacts: List[PackageArtifactRecord],
        artifacts_dir: Path,
    ) -> None:
        for record in artifacts:
            if record.role == "reference_file":
                continue
            if not record.copied:
                continue
            source_path = package_root / Path(record.package_path)
            target_path = artifacts_dir / Path(record.package_path).name
            shutil.copy2(source_path, target_path)

        package_manifest_path = package_root / "package_manifest.json"
        dataset_row_draft_path = package_root / "dataset_row_draft.json"
        shutil.copy2(package_manifest_path, artifacts_dir / "package_manifest.json")
        shutil.copy2(dataset_row_draft_path, artifacts_dir / "dataset_row_draft.json")

    def _is_support_reference_record(self, record: PackageArtifactRecord) -> bool:
        return any("Support artifact" in note for note in record.notes)

    def _rw_task_rubric_json(self, rubric_payload: Any) -> str:
        normalized_items = (
            rubric_payload
            if isinstance(rubric_payload, list)
            else self._normalize_rubric_payload(rubric_payload)
        )
        return json.dumps(normalized_items, ensure_ascii=False)

    def _rw_task_rubric_text(self, normalized_items: List[Dict[str, Any]]) -> str:
        return "\n".join(
            f"- [{item.get('score', 0)} pts] {item.get('criterion', '')}"
            for item in normalized_items
        )

    def _normalize_rubric_payload(self, rubric_payload: Any) -> List[Dict[str, Any]]:
        if isinstance(rubric_payload, str):
            try:
                parsed = json.loads(rubric_payload)
            except json.JSONDecodeError:
                return []
            if isinstance(parsed, list):
                return parsed
            rubric_payload = parsed

        if isinstance(rubric_payload, list):
            return rubric_payload

        if not isinstance(rubric_payload, dict):
            return []

        rubric = RubricArtifact.model_validate(rubric_payload)
        normalized: List[Dict[str, Any]] = []
        item_index = 1
        for section in rubric.sections:
            for criterion in section.criteria:
                if not getattr(criterion, "export_to_rw_task", True):
                    continue
                normalized.append(
                    {
                        "score": self._criterion_score(criterion),
                        "criterion": criterion.description,
                        "required": criterion.status_hint != "blocked",
                        "rubric_item_id": f"R_{item_index:03d}",
                        "author_type": "model",
                        "tags": self._criterion_tags(section.section_name, criterion),
                        "read_only": None,
                        "form_content": None,
                    }
                )
                item_index += 1
        return normalized

    def _rubric_filter_summary(
        self,
        rubric_payload: Any,
        normalized_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(rubric_payload, dict):
            return {
                "source_type": type(rubric_payload).__name__ if rubric_payload is not None else "none",
                "exported_item_count": len(normalized_items),
                "diagnostic_item_count": 0,
                "filter_applied": False,
            }

        rubric = RubricArtifact.model_validate(rubric_payload)
        all_criteria = [criterion for section in rubric.sections for criterion in section.criteria]
        diagnostic_criteria = [
            criterion for criterion in all_criteria if not getattr(criterion, "export_to_rw_task", True)
        ]
        return {
            "source_type": "RubricArtifact",
            "exported_item_count": len(normalized_items),
            "diagnostic_item_count": len(diagnostic_criteria),
            "filter_applied": True,
            "diagnostic_audiences": sorted(
                set(getattr(criterion, "audience", "candidate") for criterion in diagnostic_criteria)
            ),
            "diagnostic_reason_codes": sorted(
                set(
                    signal
                    for criterion in diagnostic_criteria
                    for signal in list(getattr(criterion, "failure_signals", []) or [])
                )
            ),
        }

    def _criterion_score(self, criterion: Any) -> int:
        severity_base = {
            "low": 1,
            "medium": 2,
            "high": 3,
        }.get(getattr(criterion, "severity", "medium"), 2)
        if getattr(criterion, "status_hint", "pass") == "pass":
            return severity_base + 1 if severity_base < 4 else severity_base
        return severity_base

    def _criterion_tags(self, section_name: str, criterion: Any) -> List[str]:
        tags = [section_name]
        criterion_type = getattr(criterion, "criterion_type", "")
        if criterion_type and criterion_type not in tags:
            tags.append(criterion_type)
        failure_signals = list(getattr(criterion, "failure_signals", []) or [])
        if failure_signals:
            tags.append("warning")
        if getattr(criterion, "status_hint", "") == "pass":
            tags.append("outcome")
        else:
            tags.append("reasoning")
        return tags

    def _write_report(self, report_path: Path, report: PipelineBRwTaskExportReport) -> None:
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
