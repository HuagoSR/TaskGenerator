import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v2_schema import TaskBlueprint
from task_generator.v3_pipeline_b_quality_gate import PipelineBQualityReport
from task_generator.v3_reference_file_generator import GeneratedFileManifest
from task_generator.v3_rubric_builder import RubricArtifact, RubricReport
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_teacher_input_builder import TeacherInputManifest, TeacherInputValidationReport
from task_generator.v3_teacher_runner import GoldenRun, TeacherRunnerReport
from task_generator.v3_training_annotation_builder import (
    TrainingAnnotationArtifact,
    TrainingAnnotationReport,
)


PackageReadiness = Literal["reject", "revise_only", "candidate_ready"]
PackageArtifactRole = Literal[
    "blueprint",
    "reference_file",
    "generated_file_manifest",
    "teacher_input",
    "teacher_input_validation",
    "golden_run",
    "teacher_runner_report",
    "training_annotation",
    "training_annotation_report",
    "rubric",
    "rubric_report",
    "quality_report",
    "semantic_contract",
    "semantic_contract_consistency",
    "dataset_row_draft",
]


class PipelineBPackageAssemblerRequest(BaseModel):
    blueprint_path: str
    generated_file_manifest_path: str
    teacher_input_manifest_path: str
    teacher_input_validation_report_path: str
    golden_run_path: str
    teacher_runner_report_path: str
    training_annotation_path: str
    training_annotation_report_path: str
    rubric_path: str
    rubric_report_path: str
    quality_report_path: str
    semantic_contract_path: Optional[str] = None
    semantic_contract_consistency_path: Optional[str] = None


class PackageArtifactRecord(BaseModel):
    artifact_id: str
    role: PackageArtifactRole
    source_path: str
    package_path: str
    copied: bool = False
    notes: List[str] = Field(default_factory=list)


class PipelineBPackageDiagnostics(BaseModel):
    quality_decision: str
    package_readiness: PackageReadiness
    reference_file_count: int = 0
    copied_reference_file_count: int = 0
    deferred_reference_file_count: int = 0
    artifact_count: int = 0
    warning_reason_codes: List[str] = Field(default_factory=list)
    export_blockers: List[str] = Field(default_factory=list)


class PipelineBPackageManifest(BaseModel):
    package_manifest_version: str = "v3.pipeline_b_package_manifest.1"
    request: PipelineBPackageAssemblerRequest
    package_id: str
    blueprint_id: str
    package_readiness: PackageReadiness
    artifacts: List[PackageArtifactRecord] = Field(default_factory=list)
    diagnostics: PipelineBPackageDiagnostics
    notes: List[str] = Field(default_factory=list)


class PipelineBPackageAssembler:
    """Collect gated Pipeline B artifacts into a stable package directory."""

    def build(
        self,
        blueprint_path: str | Path,
        generated_file_manifest_path: str | Path,
        teacher_input_manifest_path: str | Path,
        teacher_input_validation_report_path: str | Path,
        golden_run_path: str | Path,
        teacher_runner_report_path: str | Path,
        training_annotation_path: str | Path,
        training_annotation_report_path: str | Path,
        rubric_path: str | Path,
        rubric_report_path: str | Path,
        quality_report_path: str | Path,
        output_dir: str | Path,
        semantic_contract_path: str | Path | None = None,
        semantic_contract_consistency_path: str | Path | None = None,
    ) -> PipelineBPackageManifest:
        request = PipelineBPackageAssemblerRequest(
            blueprint_path=str(blueprint_path),
            generated_file_manifest_path=str(generated_file_manifest_path),
            teacher_input_manifest_path=str(teacher_input_manifest_path),
            teacher_input_validation_report_path=str(teacher_input_validation_report_path),
            golden_run_path=str(golden_run_path),
            teacher_runner_report_path=str(teacher_runner_report_path),
            training_annotation_path=str(training_annotation_path),
            training_annotation_report_path=str(training_annotation_report_path),
            rubric_path=str(rubric_path),
            rubric_report_path=str(rubric_report_path),
            quality_report_path=str(quality_report_path),
            semantic_contract_path=str(semantic_contract_path) if semantic_contract_path else None,
            semantic_contract_consistency_path=str(semantic_contract_consistency_path) if semantic_contract_consistency_path else None,
        )

        blueprint = TaskBlueprint.model_validate(load_json_file(str(blueprint_path)))
        generated_manifest = GeneratedFileManifest.model_validate(
            load_json_file(str(generated_file_manifest_path))
        )
        teacher_input = TeacherInputManifest.model_validate(load_json_file(str(teacher_input_manifest_path)))
        teacher_validation = TeacherInputValidationReport.model_validate(
            load_json_file(str(teacher_input_validation_report_path))
        )
        golden_run = GoldenRun.model_validate(load_json_file(str(golden_run_path)))
        teacher_report = TeacherRunnerReport.model_validate(load_json_file(str(teacher_runner_report_path)))
        annotation = TrainingAnnotationArtifact.model_validate(load_json_file(str(training_annotation_path)))
        annotation_report = TrainingAnnotationReport.model_validate(
            load_json_file(str(training_annotation_report_path))
        )
        rubric = RubricArtifact.model_validate(load_json_file(str(rubric_path)))
        rubric_report = RubricReport.model_validate(load_json_file(str(rubric_report_path)))
        quality_report = PipelineBQualityReport.model_validate(load_json_file(str(quality_report_path)))

        output_path = Path(output_dir)
        artifacts_dir = output_path / "artifacts"
        reference_dir = output_path / "reference_files"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        reference_dir.mkdir(parents=True, exist_ok=True)

        artifact_records: List[PackageArtifactRecord] = []
        semantic_paths = {}
        if semantic_contract_path:
            semantic_paths["semantic_contract"] = Path(semantic_contract_path)
        if semantic_contract_consistency_path:
            semantic_paths["semantic_contract_consistency"] = Path(semantic_contract_consistency_path)
        artifact_records.extend(
            self._copy_json_artifacts(
                artifacts_dir=artifacts_dir,
                paths_by_role={
                    "blueprint": Path(blueprint_path),
                    "generated_file_manifest": Path(generated_file_manifest_path),
                    "teacher_input": Path(teacher_input_manifest_path),
                    "teacher_input_validation": Path(teacher_input_validation_report_path),
                    "golden_run": Path(golden_run_path),
                    "teacher_runner_report": Path(teacher_runner_report_path),
                    "training_annotation": Path(training_annotation_path),
                    "training_annotation_report": Path(training_annotation_report_path),
                    "rubric": Path(rubric_path),
                    "rubric_report": Path(rubric_report_path),
                    "quality_report": Path(quality_report_path),
                    **semantic_paths,
                },
            )
        )
        reference_records = self._copy_reference_files(generated_manifest, reference_dir)
        artifact_records.extend(reference_records)

        package_readiness = self._package_readiness(quality_report)
        dataset_row = self._dataset_row_draft(
            blueprint=blueprint,
            teacher_input=teacher_input,
            golden_run=golden_run,
            annotation=annotation,
            rubric=rubric,
            quality_report=quality_report,
            reference_records=reference_records,
            package_readiness=package_readiness,
        )
        dataset_row_path = output_path / "dataset_row_draft.json"
        dataset_row_path.write_text(json.dumps(dataset_row, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact_records.append(
            PackageArtifactRecord(
                artifact_id=self._stable_id("pkg_art", ["dataset_row_draft", str(dataset_row_path)]),
                role="dataset_row_draft",
                source_path=str(dataset_row_path),
                package_path="dataset_row_draft.json",
                copied=False,
                notes=["Draft row for downstream export inspection; not a final rw-task case."],
            )
        )

        diagnostics = self._diagnostics(
            generated_manifest=generated_manifest,
            teacher_validation=teacher_validation,
            teacher_report=teacher_report,
            annotation_report=annotation_report,
            rubric_report=rubric_report,
            quality_report=quality_report,
            package_readiness=package_readiness,
            artifact_records=artifact_records,
            reference_records=reference_records,
        )

        manifest = PipelineBPackageManifest(
            request=request,
            package_id=self._stable_id("pkg", [blueprint.blueprint_id, golden_run.golden_run_id]),
            blueprint_id=blueprint.blueprint_id,
            package_readiness=package_readiness,
            artifacts=artifact_records,
            diagnostics=diagnostics,
            notes=[
                "PackageAssembler V1 is a staging layer before final rw-task export.",
                "It preserves quality-gate status rather than upgrading partial packages.",
                "Reference files are copied only when generated by deterministic file generation.",
            ],
        )
        (output_path / "package_manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        return manifest

    def _copy_json_artifacts(
        self,
        artifacts_dir: Path,
        paths_by_role: Dict[PackageArtifactRole, Path],
    ) -> List[PackageArtifactRecord]:
        records: List[PackageArtifactRecord] = []
        for role, source_path in paths_by_role.items():
            package_name = source_path.name
            target_path = artifacts_dir / package_name
            shutil.copy2(source_path, target_path)
            records.append(
                PackageArtifactRecord(
                    artifact_id=self._stable_id("pkg_art", [role, str(source_path)]),
                    role=role,
                    source_path=str(source_path),
                    package_path=str(Path("artifacts") / package_name),
                    copied=True,
                )
            )
        return records

    def _copy_reference_files(
        self,
        manifest: GeneratedFileManifest,
        reference_dir: Path,
    ) -> List[PackageArtifactRecord]:
        records: List[PackageArtifactRecord] = []
        for file_record in manifest.generated_files:
            if file_record.status != "generated" or not file_record.relative_path:
                records.append(
                    PackageArtifactRecord(
                        artifact_id=self._stable_id("pkg_ref", [file_record.file_id, file_record.file_name]),
                        role="reference_file",
                        source_path="",
                        package_path=str(Path("reference_files") / file_record.file_name),
                        copied=False,
                        notes=[
                            f"Reference file status is {file_record.status}.",
                            f"Skipped reason: {file_record.skipped_reason or 'n/a'}",
                        ],
                    )
                )
                continue
            source_path = Path(manifest.output_dir) / file_record.relative_path
            target_path = reference_dir / file_record.file_name
            shutil.copy2(source_path, target_path)
            records.append(
                PackageArtifactRecord(
                    artifact_id=self._stable_id("pkg_ref", [file_record.file_id, str(source_path)]),
                    role="reference_file",
                    source_path=str(source_path),
                    package_path=str(Path("reference_files") / file_record.file_name),
                    copied=True,
                )
            )
            for support_path in file_record.support_artifacts:
                support_source = Path(manifest.output_dir) / support_path
                support_target = reference_dir / Path(support_path).name
                if support_source.exists():
                    shutil.copy2(support_source, support_target)
                    records.append(
                        PackageArtifactRecord(
                            artifact_id=self._stable_id("pkg_ref_support", [file_record.file_id, str(support_source)]),
                            role="reference_file",
                            source_path=str(support_source),
                            package_path=str(Path("reference_files") / Path(support_path).name),
                            copied=True,
                            notes=[f"Support artifact for {file_record.file_name}."],
                        )
                    )
        return records

    def _dataset_row_draft(
        self,
        blueprint: TaskBlueprint,
        teacher_input: TeacherInputManifest,
        golden_run: GoldenRun,
        annotation: TrainingAnnotationArtifact,
        rubric: RubricArtifact,
        quality_report: PipelineBQualityReport,
        reference_records: List[PackageArtifactRecord],
        package_readiness: PackageReadiness,
    ) -> Dict[str, Any]:
        copied_references = [
            record.package_path
            for record in reference_records
            if record.copied and not self._is_support_reference_record(record)
        ]
        deliverable_files = [
            str(Path("deliverable_files") / item.file_name)
            for item in blueprint.deliverable_spec
        ]
        return {
            "task_id": blueprint.blueprint_id,
            "sector": blueprint.task_metadata.sector,
            "occupation": blueprint.task_metadata.occupation,
            "motif": blueprint.template_family,
            "prompt": self._candidate_prompt(teacher_input),
            "reference_files": copied_references,
            "deliverable_files": deliverable_files,
            "rubric": self._rubric_text(rubric),
            "rubric_json": rubric.model_dump(),
            "extra": {
                "export_status": package_readiness,
                "quality_decision": quality_report.decision.decision,
                "quality_reason_codes": quality_report.decision.reason_codes,
                "blueprint_id": blueprint.blueprint_id,
                "golden_run_id": golden_run.golden_run_id,
                "annotation_id": annotation.annotation_id,
                "rubric_readiness": rubric.readiness,
                "rw_task_export_ready": package_readiness == "candidate_ready",
            },
        }

    def _candidate_prompt(self, teacher_input: TeacherInputManifest) -> str:
        candidate = teacher_input.candidate_view
        reference_lines = [
            f"- {item.file_name} ({item.status})"
            for item in candidate.reference_files
        ]
        deliverable_lines = [
            f"- {item.get('file_name')}: {'; '.join(item.get('requirements') or [])}"
            for item in candidate.deliverables
        ]
        sections = [
            candidate.business_context,
            "",
            "Role:",
            candidate.role,
            "",
            "Visible requirements:",
            *[f"- {item}" for item in candidate.visible_requirements],
            "",
            "Reference files:",
            *reference_lines,
            "",
            "Deliverables:",
            *deliverable_lines,
        ]
        if candidate.style_constraints:
            sections.extend(["", "Style constraints:", *[f"- {item}" for item in candidate.style_constraints]])
        return "\n".join(sections).strip()

    def _rubric_text(self, rubric: RubricArtifact) -> str:
        lines = []
        for section in rubric.sections:
            candidate_criteria = [
                criterion for criterion in section.criteria if criterion.export_to_rw_task
            ]
            if not candidate_criteria:
                continue
            lines.append(section.section_name)
            for criterion in candidate_criteria:
                lines.append(f"- [{criterion.severity}/{criterion.status_hint}] {criterion.description}")
        return "\n".join(lines)

    def _diagnostics(
        self,
        generated_manifest: GeneratedFileManifest,
        teacher_validation: TeacherInputValidationReport,
        teacher_report: TeacherRunnerReport,
        annotation_report: TrainingAnnotationReport,
        rubric_report: RubricReport,
        quality_report: PipelineBQualityReport,
        package_readiness: PackageReadiness,
        artifact_records: List[PackageArtifactRecord],
        reference_records: List[PackageArtifactRecord],
    ) -> PipelineBPackageDiagnostics:
        warning_reason_codes = sorted(
            set(
                self._teacher_validation_warning_codes(teacher_validation)
                + teacher_report.diagnostics.warning_reason_codes
                + annotation_report.diagnostics.warning_reason_codes
                + rubric_report.diagnostics.warning_reason_codes
                + quality_report.decision.reason_codes
            )
        )
        export_blockers = []
        if package_readiness != "candidate_ready":
            export_blockers.append(f"quality_gate_decision:{quality_report.decision.decision}")
        if any(
            record.role == "reference_file"
            and not record.copied
            and not self._is_support_reference_record(record)
            for record in reference_records
        ):
            export_blockers.append("deferred_or_missing_reference_files")
        return PipelineBPackageDiagnostics(
            quality_decision=quality_report.decision.decision,
            package_readiness=package_readiness,
            reference_file_count=len(generated_manifest.generated_files),
            copied_reference_file_count=sum(
                1
                for record in reference_records
                if record.copied and not self._is_support_reference_record(record)
            ),
            deferred_reference_file_count=sum(
                1
                for record in reference_records
                if not record.copied and not self._is_support_reference_record(record)
            ),
            artifact_count=len(artifact_records),
            warning_reason_codes=warning_reason_codes,
            export_blockers=export_blockers,
        )

    def _is_support_reference_record(self, record: PackageArtifactRecord) -> bool:
        return any("Support artifact" in note for note in record.notes)

    def _teacher_validation_warning_codes(
        self, report: TeacherInputValidationReport
    ) -> List[str]:
        return [
            finding.check_name
            for finding in report.findings + report.relationship_checks
            if finding.severity == "warning" and not finding.passed
        ]

    def _package_readiness(self, quality_report: PipelineBQualityReport) -> PackageReadiness:
        if quality_report.decision.decision == "candidate_ready":
            return "candidate_ready"
        if quality_report.decision.decision == "reject":
            return "reject"
        return "revise_only"

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        import hashlib

        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
