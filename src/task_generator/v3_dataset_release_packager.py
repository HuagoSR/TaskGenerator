from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


ReleaseMode = Literal["production_ready_only", "internal_review_release"]


class DatasetReleaseRequest(BaseModel):
    release_id: str
    production_batch_manifest_path: str
    production_qa_gate_report_path: str
    output_root: str
    production_batch_diversity_report_path: Optional[str] = None
    include_review_required: bool = False


class ReleaseTaskRecord(BaseModel):
    task_id: str
    source_case_id: str
    blueprint_id: Optional[str] = None
    motif: Optional[str] = None
    decision: str
    included_in_release: bool = False
    release_task_dir: Optional[str] = None
    exclusion_reason: Optional[str] = None


class DatasetReleaseManifest(BaseModel):
    release_manifest_version: str = "v3.dataset_release_manifest.1"
    request: DatasetReleaseRequest
    release_id: str
    release_mode: ReleaseMode
    domain_scope: str
    file_type_scope: List[str] = Field(default_factory=list)
    task_count: int = 0
    production_ready_count: int = 0
    diagnostic_eval_sample_count: int = 0
    excluded_task_count: int = 0
    code_commit: Optional[str] = None
    registry_version: Optional[str] = None
    workflow_asset_version: Optional[str] = None
    motif_grammar_version: Optional[str] = None
    source_production_batch_id: str
    created_at: str
    not_benchmark_grade: bool = True
    intended_use: List[str] = Field(default_factory=list)
    not_intended_use: List[str] = Field(default_factory=list)
    task_records: List[ReleaseTaskRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class DatasetReleaseArtifact(BaseModel):
    release_manifest_path: str
    release_dir: str
    release_manifest: DatasetReleaseManifest


class DatasetReleasePackager:
    WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:\\")

    def build(
        self,
        release_id: str,
        production_batch_manifest_path: str | Path,
        production_qa_gate_report_path: str | Path,
        output_root: str | Path,
        production_batch_diversity_report_path: str | Path | None = None,
        include_review_required: bool = False,
    ) -> DatasetReleaseArtifact:
        output_root_path = Path(output_root)
        release_dir = output_root_path / release_id
        if release_dir.exists():
            shutil.rmtree(release_dir)
        release_dir.mkdir(parents=True, exist_ok=True)
        request = DatasetReleaseRequest(
            release_id=release_id,
            production_batch_manifest_path=str(production_batch_manifest_path),
            production_qa_gate_report_path=str(production_qa_gate_report_path),
            output_root=self._display_path(output_root_path),
            production_batch_diversity_report_path=(
                str(production_batch_diversity_report_path)
                if production_batch_diversity_report_path
                else None
            ),
            include_review_required=include_review_required,
        )
        manifest_payload = load_json_file(str(production_batch_manifest_path))
        qa_payload = load_json_file(str(production_qa_gate_report_path))
        diversity_payload = (
            load_json_file(str(production_batch_diversity_report_path))
            if production_batch_diversity_report_path
            else {}
        )

        production_batch_id = str(
            ((manifest_payload.get("request") or {}).get("production_batch_id")) or "unknown_batch"
        )
        reports_dir = release_dir / "reports"
        docs_dir = release_dir / "docs"
        dataset_rows_dir = release_dir / "dataset_rows"
        tasks_dir = release_dir / "tasks"
        reports_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)
        dataset_rows_dir.mkdir(parents=True, exist_ok=True)
        tasks_dir.mkdir(parents=True, exist_ok=True)
        case_by_id = {
            str(case.get("case_id")): case
            for case in (manifest_payload.get("cases") or [])
            if isinstance(case, dict) and case.get("case_id")
        }
        task_records: List[ReleaseTaskRecord] = []
        included_case_ids: List[str] = []
        for decision_payload in qa_payload.get("decisions") or []:
            if not isinstance(decision_payload, dict):
                continue
            case_id = str(decision_payload.get("case_id") or "unknown_case")
            case_payload = case_by_id.get(case_id, {})
            decision = str(decision_payload.get("decision") or "unknown")
            include_case = decision == "approved_production_candidate" or (
                include_review_required and decision == "review_required"
            )
            release_task_dir = None
            exclusion_reason = None
            if include_case:
                release_task_dir = self._copy_release_task(
                    release_dir=release_dir,
                    index=len(included_case_ids) + 1,
                    case_payload=case_payload,
                    qa_decision_payload=decision_payload,
                )
                included_case_ids.append(case_id)
            else:
                exclusion_reason = decision
            task_records.append(
                ReleaseTaskRecord(
                    task_id=case_id,
                    source_case_id=case_id,
                    blueprint_id=self._optional_str(case_payload.get("blueprint_id")),
                    motif=self._optional_str(case_payload.get("motif")),
                    decision=decision,
                    included_in_release=include_case,
                    release_task_dir=release_task_dir,
                    exclusion_reason=exclusion_reason,
                )
            )

        self._write_release_reports(
            reports_dir=reports_dir,
            manifest_payload=manifest_payload,
            qa_payload=qa_payload,
            diversity_payload=diversity_payload,
            task_records=task_records,
        )
        self._write_release_docs(
            docs_dir=docs_dir,
            release_id=release_id,
            manifest_payload=manifest_payload,
            qa_payload=qa_payload,
            task_records=task_records,
            include_review_required=include_review_required,
        )
        release_manifest = DatasetReleaseManifest(
            request=request,
            release_id=release_id,
            release_mode=(
                "internal_review_release" if include_review_required else "production_ready_only"
            ),
            domain_scope=str(((manifest_payload.get("request") or {}).get("domain_scope")) or "unknown"),
            file_type_scope=[
                str(value)
                for value in (((manifest_payload.get("request") or {}).get("file_type_scope")) or [])
            ],
            task_count=sum(1 for record in task_records if record.included_in_release),
            production_ready_count=sum(
                1 for record in task_records if record.decision == "approved_production_candidate"
            ),
            diagnostic_eval_sample_count=sum(
                1
                for case in (manifest_payload.get("cases") or [])
                if isinstance(case, dict) and bool(case.get("diagnostic_eval_recommended"))
            ),
            excluded_task_count=sum(1 for record in task_records if not record.included_in_release),
            code_commit=self._optional_str(manifest_payload.get("code_commit")),
            registry_version=self._optional_str(manifest_payload.get("registry_version")),
            workflow_asset_version=self._optional_str(manifest_payload.get("workflow_asset_version")),
            motif_grammar_version=self._optional_str(manifest_payload.get("motif_grammar_version")),
            source_production_batch_id=production_batch_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            intended_use=(
                ["training_pool_candidate", "diagnostic_internal_eval"]
                if not include_review_required
                else ["internal_review_release", "diagnostic_internal_eval"]
            ),
            not_intended_use=["formal_public_benchmark_claim", "public_release_without_later_validation"],
            task_records=task_records,
            notes=[
                "Dataset release packaging is a release-side copy and sanitization layer over a production batch.",
                "Release artifacts avoid carrying local absolute workspace paths into the published release bundle.",
                "This release remains not benchmark-grade unless a later phase explicitly validates stronger comparison semantics.",
            ],
        )
        release_manifest_path = release_dir / "release_manifest.json"
        release_manifest_path.write_text(
            release_manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return DatasetReleaseArtifact(
            release_manifest_path=str(release_manifest_path),
            release_dir=str(release_dir),
            release_manifest=release_manifest,
        )

    def _copy_release_task(
        self,
        release_dir: Path,
        index: int,
        case_payload: Dict[str, Any],
        qa_decision_payload: Dict[str, Any],
    ) -> str:
        case_dir = Path(str(case_payload.get("case_dir") or ""))
        rw_task_export_dir = case_dir / "rw_task_export"
        task_dir = release_dir / "tasks" / f"task_{index:04d}"
        task_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rw_task_export_dir / "dataset_row.json", task_dir / "dataset_row.json")
        self._copy_tree(rw_task_export_dir / "reference_files", task_dir / "reference_files")
        self._copy_tree(rw_task_export_dir / "deliverable_files", task_dir / "deliverable_files")

        artifacts_dir = task_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._sanitize_and_write_json(
            rw_task_export_dir / "artifacts" / "draft_task_blueprint.json",
            artifacts_dir / "task_blueprint.json",
        )
        self._sanitize_and_write_json(
            case_dir / "reference_file_plan" / "reference_file_plan.json",
            artifacts_dir / "reference_file_plan.json",
        )
        self._sanitize_and_write_json(
            rw_task_export_dir / "artifacts" / "generated_file_manifest.json",
            artifacts_dir / "generated_file_manifest.json",
        )
        self._sanitize_and_write_json(
            case_dir / "reference_file_generation" / "evidence_index.json",
            artifacts_dir / "evidence_index.json",
        )
        self._sanitize_and_write_json(
            rw_task_export_dir / "artifacts" / "teacher_input_manifest.json",
            artifacts_dir / "teacher_input_manifest.json",
        )
        self._sanitize_and_write_json(
            rw_task_export_dir / "artifacts" / "golden_run.json",
            artifacts_dir / "golden_run.json",
        )
        self._sanitize_and_write_json(
            rw_task_export_dir / "artifacts" / "training_annotation.json",
            artifacts_dir / "training_annotation.json",
        )
        self._sanitize_and_write_json(
            rw_task_export_dir / "artifacts" / "rubric.json",
            artifacts_dir / "rubric.json",
        )
        self._sanitize_and_write_json(
            case_dir / "quality_gate" / "pipeline_b_quality_report.json",
            artifacts_dir / "pipeline_b_quality_report.json",
        )
        self._sanitize_and_write_json(
            case_dir / "task_verifier" / "task_verifier_report.json",
            artifacts_dir / "task_verifier_report.json",
        )
        self._sanitize_and_write_json(
            case_dir / "global_validity" / "global_task_validity_report.json",
            artifacts_dir / "global_task_validity_report.json",
        )
        self._sanitize_and_write_json(
            case_dir / "global_validity" / "real_worldness_report.json",
            artifacts_dir / "real_worldness_report.json",
        )
        self._sanitize_and_write_json(
            case_dir / "global_validity" / "difficulty_profile_report.json",
            artifacts_dir / "difficulty_profile_report.json",
        )
        self._sanitize_and_write_json(
            case_dir / "rw_task_export" / "rw_task_export_validation_report.json",
            artifacts_dir / "rw_task_export_validation_report.json",
        )
        self._sanitize_and_write_payload(
            {
                "case_id": qa_decision_payload.get("case_id"),
                "decision": qa_decision_payload.get("decision"),
                "proposed_task_state": qa_decision_payload.get("proposed_task_state"),
                "production_candidate_approved": qa_decision_payload.get("production_candidate_approved"),
                "findings": qa_decision_payload.get("findings") or [],
                "notes": qa_decision_payload.get("notes") or [],
            },
            artifacts_dir / "production_qa_case_report.json",
        )
        self._sanitize_and_write_payload(
            {
                "task_id": qa_decision_payload.get("case_id"),
                "blueprint_id": case_payload.get("blueprint_id"),
                "motif": case_payload.get("motif"),
                "task_state": case_payload.get("task_state"),
                "release_inclusion_basis": qa_decision_payload.get("decision"),
            },
            task_dir / "release_task_manifest.json",
        )
        shutil.copy2(task_dir / "dataset_row.json", release_dir / "dataset_rows" / f"{task_dir.name}.dataset_row.json")
        return task_dir.relative_to(release_dir).as_posix()

    def _write_release_reports(
        self,
        reports_dir: Path,
        manifest_payload: Dict[str, Any],
        qa_payload: Dict[str, Any],
        diversity_payload: Dict[str, Any],
        task_records: List[ReleaseTaskRecord],
    ) -> None:
        included_count = sum(1 for record in task_records if record.included_in_release)
        quality_report = {
            "release_quality_report_version": "v3.release_quality_report.1",
            "included_task_count": included_count,
            "production_ready_count": sum(
                1 for record in task_records if record.decision == "approved_production_candidate"
            ),
            "review_required_count": sum(1 for record in task_records if record.decision == "review_required"),
            "blocked_count": sum(1 for record in task_records if record.decision == "blocked"),
            "decision_counts": (qa_payload.get("summary") or {}).get("decision_counts") or {},
            "warning_finding_count": (qa_payload.get("summary") or {}).get("warning_finding_count") or 0,
            "blocking_finding_count": (qa_payload.get("summary") or {}).get("blocking_finding_count") or 0,
        }
        verifier_report = {
            "release_verifier_report_version": "v3.release_verifier_report.1",
            "case_count": len(manifest_payload.get("cases") or []),
            "verifier_pass_count": sum(
                1
                for case in (manifest_payload.get("cases") or [])
                if isinstance(case, dict) and case.get("verifier_status") == "pass"
            ),
            "export_compatible_count": sum(
                1
                for case in (manifest_payload.get("cases") or [])
                if isinstance(case, dict) and case.get("validation_status") == "candidate_ready_compatible"
            ),
        }
        eval_report = {
            "release_eval_diagnostic_report_version": "v3.release_eval_diagnostic_report.1",
            "diagnostic_eval_sample_count": sum(
                1
                for case in (manifest_payload.get("cases") or [])
                if isinstance(case, dict) and bool(case.get("diagnostic_eval_recommended"))
            ),
            "notes": [
                "Release packaging does not execute diagnostic evaluation by itself.",
                "This report only records the current production-batch diagnostic-eval recommendation footprint.",
            ],
        }
        diversity_report = {
            "release_diversity_report_version": "v3.release_diversity_report.1",
            "case_count": (diversity_payload.get("summary") or {}).get("case_count") or 0,
            "unique_motif_count": (diversity_payload.get("summary") or {}).get("unique_motif_count") or 0,
            "duplicate_subgraph_count": (diversity_payload.get("summary") or {}).get("duplicate_subgraph_count") or 0,
            "duplicate_blueprint_count": (diversity_payload.get("summary") or {}).get("duplicate_blueprint_count") or 0,
            "duplicate_deliverable_signature_count": (
                (diversity_payload.get("summary") or {}).get("duplicate_deliverable_signature_count") or 0
            ),
            "warnings": ((diversity_payload.get("diagnostics") or {}).get("warnings") or []),
        }
        self._sanitize_and_write_payload(quality_report, reports_dir / "release_quality_report.json")
        self._sanitize_and_write_payload(diversity_report, reports_dir / "release_diversity_report.json")
        self._sanitize_and_write_payload(verifier_report, reports_dir / "release_verifier_report.json")
        self._sanitize_and_write_payload(eval_report, reports_dir / "release_eval_diagnostic_report.json")

    def _write_release_docs(
        self,
        docs_dir: Path,
        release_id: str,
        manifest_payload: Dict[str, Any],
        qa_payload: Dict[str, Any],
        task_records: List[ReleaseTaskRecord],
        include_review_required: bool,
    ) -> None:
        domain_scope = str(((manifest_payload.get("request") or {}).get("domain_scope")) or "unknown")
        file_types = ", ".join(
            str(value)
            for value in (((manifest_payload.get("request") or {}).get("file_type_scope")) or [])
        )
        included_count = sum(1 for record in task_records if record.included_in_release)
        readme = f"""# {release_id}

This release bundle packages selected tasks from the Phase 13 production batch flow.

- domain scope: {domain_scope}
- included task count: {included_count}
- release mode: {"internal_review_release" if include_review_required else "production_ready_only"}
- benchmark-grade: no
"""
        data_card = f"""# DATA CARD

## 1. Generation method
Tasks were generated by the deterministic Pipeline B production batch flow, then filtered through the report-first Phase 13 production QA gate.

## 2. Domain scope
{domain_scope}

## 3. File type scope
{file_types}

## 4. Task structure
Tasks are workflow-conditioned finance or audit cases packaged as rw-task-style directories with reference files, deliverable expectations, and supporting JSON artifacts.

## 5. Quality gates
This release records Pipeline B quality-gate status, task-verifier status, rw-task export validation, real-worldness diagnostics, and a production QA decision.

## 6. Verifier coverage
Verifier pass/fail is preserved from the deterministic task verifier and summarized in reports/release_verifier_report.json.

## 7. Executed eval coverage
Executed eval is not part of release packaging itself; this release only records diagnostic-eval recommendation status from the source production batch.

## 8. Known limitations
This release remains report-first, finance/audit-scoped, and not benchmark-grade. Some source cases may remain review-required rather than approved production candidates.

## 9. Interpretation limits
Do not interpret this release as a public benchmark or a formal model-separation claim.
"""
        known_limitations = """# KNOWN LIMITATIONS

- This release is generated from the current finance/audit production MVP slice only.
- Release packaging sanitizes local workspace paths instead of preserving raw scratch provenance files.
- Diagnostic evaluation evidence is not automatically included as benchmark-grade quality proof.
- Production QA decisions remain conservative and may keep structurally closed cases in review_required.
"""
        (docs_dir / "README.md").write_text(readme, encoding="utf-8")
        (docs_dir / "DATA_CARD.md").write_text(data_card, encoding="utf-8")
        (docs_dir / "KNOWN_LIMITATIONS.md").write_text(known_limitations, encoding="utf-8")

    def _copy_tree(self, source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

    def _sanitize_and_write_json(self, source_path: Path, destination_path: Path) -> None:
        payload = load_json_file(str(source_path))
        self._sanitize_and_write_payload(payload, destination_path)

    def _sanitize_and_write_payload(self, payload: Any, destination_path: Path) -> None:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        sanitized = self._sanitize_value(payload)
        destination_path.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._sanitize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, str):
            return self._sanitize_string(value)
        return value

    def _sanitize_string(self, value: str) -> str:
        if self.WINDOWS_ABSOLUTE_PATH.match(value):
            normalized = value.replace("/", "\\")
            workspace_anchor = "\\TaskGenerator\\"
            if workspace_anchor in normalized:
                return normalized.split(workspace_anchor, 1)[1].replace("\\", "/")
            return "<external_path>"
        return value

    def _optional_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.name
