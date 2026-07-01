import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from task_generator.v3_reference_file_planner import (
    EvidenceAnchor,
    PlannedReferenceFile,
    PlannedTable,
    ReferenceFilePlan,
)
from task_generator.v3_source_schema import load_json_file


GenerationStatus = Literal["generated", "skipped", "failed"]

SOURCE_LABELS = [
    "ERP Export",
    "Control Workbook",
    "Manager Email",
    "Ledger Snapshot",
    "Policy Attachment",
    "Support Schedule",
]

ENTITY_LABELS = [
    "North Division",
    "South Division",
    "Vendor Atlas",
    "Project Beacon",
    "Client Horizon",
    "Account Delta",
]

DESCRIPTION_TEMPLATES = [
    "Reviewed support for transaction set {index}.",
    "Control exception screening for item {index}.",
    "Follow-up note for evidence bundle {index}.",
    "Reconciliation observation on batch {index}.",
]


class ValidationCheck(BaseModel):
    check_name: str
    passed: bool
    details: str = ""


class GeneratedEvidenceMapping(BaseModel):
    evidence_id: str
    file_id: str
    file_name: str
    locator: str
    physical_location: str
    semantic_type: str


class GeneratedFileRecord(BaseModel):
    file_id: str
    file_name: str
    file_format: str
    status: GenerationStatus
    relative_path: Optional[str] = None
    generation_mode: str
    row_count_by_table: Dict[str, int] = Field(default_factory=dict)
    validation_checks: List[ValidationCheck] = Field(default_factory=list)
    skipped_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class GeneratedFileManifest(BaseModel):
    reference_file_generation_version: str = "v3.reference_file_generation.1"
    blueprint_id: str
    template_family: str
    plan_path: str
    output_dir: str
    generated_files: List[GeneratedFileRecord] = Field(default_factory=list)
    evidence_index: List[GeneratedEvidenceMapping] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class ReferenceFileGenerator:
    """Generate deterministic table-first reference files from a ReferenceFilePlan."""

    def build_from_plan(
        self,
        reference_file_plan_path: str | Path,
        output_dir: str | Path,
    ) -> GeneratedFileManifest:
        plan = ReferenceFilePlan.model_validate(load_json_file(str(reference_file_plan_path)))
        base_output_dir = Path(output_dir)
        reference_dir = base_output_dir / "reference_files"
        reference_dir.mkdir(parents=True, exist_ok=True)

        generated_files: List[GeneratedFileRecord] = []
        evidence_index: List[GeneratedEvidenceMapping] = []
        trace_records: List[Dict[str, Any]] = []

        for planned_file in plan.planned_files:
            record, mappings, trace = self._generate_file(planned_file, reference_dir)
            generated_files.append(record)
            evidence_index.extend(mappings)
            trace_records.append(trace)

        manifest = GeneratedFileManifest(
            blueprint_id=plan.blueprint_id,
            template_family=plan.template_family,
            plan_path=str(reference_file_plan_path),
            output_dir=str(base_output_dir),
            generated_files=generated_files,
            evidence_index=evidence_index,
            diagnostics=self._diagnostics(plan, generated_files, evidence_index),
            notes=[
                "Only deterministic table-first files are generated in this slice.",
                "Unsupported file types are marked explicitly instead of being silently omitted.",
                "Evidence mappings connect planned anchors to physical file locations for later GoldenRun and rubric work.",
            ],
        )

        self._write_outputs(base_output_dir, manifest, trace_records)
        return manifest

    def _generate_file(
        self,
        planned_file: PlannedReferenceFile,
        reference_dir: Path,
    ) -> tuple[GeneratedFileRecord, List[GeneratedEvidenceMapping], Dict[str, Any]]:
        if planned_file.generator_status != "ready_for_deterministic_generation":
            return (
                GeneratedFileRecord(
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    file_format=planned_file.file_format,
                    status="skipped",
                    generation_mode="unsupported_or_deferred",
                    skipped_reason=f"planner_status:{planned_file.generator_status}",
                    warnings=["File type or template is deferred to a later slice."],
                ),
                [],
                {
                    "file_id": planned_file.file_id,
                    "file_name": planned_file.file_name,
                    "status": "skipped",
                    "reason": f"planner_status:{planned_file.generator_status}",
                },
            )

        target_path = reference_dir / planned_file.file_name
        file_format = planned_file.file_format.lower()

        try:
            if file_format == "xlsx":
                table_frames = self._table_frames(planned_file.tables)
                self._write_xlsx(target_path, table_frames)
                mappings = self._xlsx_evidence_mappings(planned_file, table_frames)
                record = self._validate_generated_file(planned_file, target_path, table_frames)
            elif file_format == "csv":
                table_frames = self._table_frames(planned_file.tables)
                self._write_csv(target_path, table_frames, planned_file.file_name)
                mappings = self._csv_evidence_mappings(planned_file, table_frames)
                record = self._validate_generated_file(planned_file, target_path, table_frames)
            elif file_format == "json":
                table_frames = self._table_frames(planned_file.tables)
                self._write_json(target_path, table_frames)
                mappings = self._json_evidence_mappings(planned_file, table_frames)
                record = self._validate_generated_file(planned_file, target_path, table_frames)
            elif file_format in {"md", "txt"}:
                self._write_text_reference(target_path, planned_file)
                mappings = self._text_evidence_mappings(planned_file)
                record = self._validate_text_file(planned_file, target_path)
            else:
                return (
                    GeneratedFileRecord(
                        file_id=planned_file.file_id,
                        file_name=planned_file.file_name,
                        file_format=planned_file.file_format,
                        status="skipped",
                        generation_mode="unsupported_or_deferred",
                        skipped_reason=f"unsupported_format:{planned_file.file_format}",
                        warnings=["No deterministic generator exists yet for this file format."],
                    ),
                    [],
                    {
                        "file_id": planned_file.file_id,
                        "file_name": planned_file.file_name,
                        "status": "skipped",
                        "reason": f"unsupported_format:{planned_file.file_format}",
                    },
                )
        except Exception as exc:
            return (
                GeneratedFileRecord(
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    file_format=planned_file.file_format,
                    status="failed",
                    generation_mode="deterministic_table_first",
                    skipped_reason=type(exc).__name__,
                    warnings=[str(exc)],
                ),
                [],
                {
                    "file_id": planned_file.file_id,
                    "file_name": planned_file.file_name,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

        trace = {
            "file_id": planned_file.file_id,
            "file_name": planned_file.file_name,
            "status": "generated",
            "generation_mode": record.generation_mode,
            "row_count_by_table": record.row_count_by_table,
            "warnings": record.warnings,
        }
        return record, mappings, trace

    def _table_frames(self, tables: List[PlannedTable]) -> Dict[str, pd.DataFrame]:
        return {table.sheet_name: self._build_table_frame(table) for table in tables}

    def _build_table_frame(self, table: PlannedTable) -> pd.DataFrame:
        rows = []
        for row_index in range(table.row_count_target):
            row = {}
            for column_index, column in enumerate(table.columns):
                row[column.name] = self._column_value(
                    column_name=column.name,
                    semantic_type=column.semantic_type,
                    row_index=row_index,
                    column_index=column_index,
                )
            rows.append(row)
        return pd.DataFrame(rows, columns=[column.name for column in table.columns])

    def _column_value(self, column_name: str, semantic_type: str, row_index: int, column_index: int) -> Any:
        lowered_name = column_name.lower()
        lowered_type = semantic_type.lower()

        if "identifier" in lowered_type or "evidence_id" in lowered_name:
            prefix = "EVID" if "evidence" in lowered_name else "ID"
            return f"{prefix}-{row_index + 1:03d}"
        if "source_label" in lowered_type:
            return SOURCE_LABELS[row_index % len(SOURCE_LABELS)]
        if "business_entity" in lowered_type:
            base = ENTITY_LABELS[row_index % len(ENTITY_LABELS)]
            return f"{base} {row_index + 1:03d}"
        if "time_period" in lowered_type:
            quarter = (row_index % 4) + 1
            year = 2025 + (row_index // 8)
            return f"{year}-Q{quarter}"
        if "date" in lowered_type:
            month = (row_index % 12) + 1
            day = (row_index % 28) + 1
            return f"2026-{month:02d}-{day:02d}"
        if "amount" in lowered_type or "value" in lowered_type or "count" in lowered_type:
            return round(1000 + (row_index * 137.5) + (column_index * 11.25), 2)
        if "mixed_fact" in lowered_type:
            return round(2500 + (row_index * 83.4) + (column_index * 7.0), 2)
        if "free_text" in lowered_type or "description" in lowered_type:
            template = DESCRIPTION_TEMPLATES[row_index % len(DESCRIPTION_TEMPLATES)]
            return template.format(index=f"{row_index + 1:03d}")
        if "policy_rule" in lowered_type:
            return f"Apply rule set {row_index + 1:02d} to the referenced item."
        return f"{column_name}_{row_index + 1:03d}"

    def _write_xlsx(self, target_path: Path, table_frames: Dict[str, pd.DataFrame]) -> None:
        with pd.ExcelWriter(target_path) as writer:
            for sheet_name, frame in table_frames.items():
                frame.to_excel(writer, sheet_name=sheet_name, index=False)

    def _write_csv(self, target_path: Path, table_frames: Dict[str, pd.DataFrame], file_name: str) -> None:
        if len(table_frames) != 1:
            raise ValueError(f"{file_name} cannot be written as CSV because it has {len(table_frames)} tables.")
        next(iter(table_frames.values())).to_csv(target_path, index=False)

    def _write_json(self, target_path: Path, table_frames: Dict[str, pd.DataFrame]) -> None:
        if len(table_frames) == 1:
            payload: Any = next(iter(table_frames.values())).to_dict(orient="records")
        else:
            payload = {sheet_name: frame.to_dict(orient="records") for sheet_name, frame in table_frames.items()}
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_text_reference(self, target_path: Path, planned_file: PlannedReferenceFile) -> None:
        lines = [f"# {planned_file.file_name}", ""]
        for section in planned_file.text_sections:
            lines.append(section.heading)
            lines.append(f"This section is planned deterministically for {section.evidence_role}.")
            lines.append("")
        target_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def _validate_generated_file(
        self,
        planned_file: PlannedReferenceFile,
        target_path: Path,
        table_frames: Dict[str, pd.DataFrame],
    ) -> GeneratedFileRecord:
        checks = [ValidationCheck(check_name="file_exists", passed=target_path.exists(), details=str(target_path))]
        row_count_by_table: Dict[str, int] = {}

        if planned_file.file_format == "xlsx":
            workbook = pd.read_excel(target_path, sheet_name=None)
            for table in planned_file.tables:
                frame = workbook.get(table.sheet_name)
                exists = frame is not None
                checks.append(ValidationCheck(check_name=f"sheet_exists:{table.sheet_name}", passed=exists))
                if not exists:
                    continue
                row_count_by_table[table.table_id] = len(frame.index)
                checks.extend(self._table_checks(table, frame))
        elif planned_file.file_format == "csv":
            frame = pd.read_csv(target_path)
            if planned_file.tables:
                table = planned_file.tables[0]
                row_count_by_table[table.table_id] = len(frame.index)
                checks.extend(self._table_checks(table, frame))
        elif planned_file.file_format == "json":
            payload = json.loads(target_path.read_text(encoding="utf-8"))
            if len(planned_file.tables) == 1:
                table = planned_file.tables[0]
                frame = pd.DataFrame(payload)
                row_count_by_table[table.table_id] = len(frame.index)
                checks.extend(self._table_checks(table, frame))
            else:
                for table in planned_file.tables:
                    frame = pd.DataFrame(payload.get(table.sheet_name, []))
                    row_count_by_table[table.table_id] = len(frame.index)
                    checks.extend(self._table_checks(table, frame))

        status: GenerationStatus = "generated" if all(check.passed for check in checks) else "failed"
        return GeneratedFileRecord(
            file_id=planned_file.file_id,
            file_name=planned_file.file_name,
            file_format=planned_file.file_format,
            status=status,
            relative_path=str(Path("reference_files") / planned_file.file_name),
            generation_mode="deterministic_table_first",
            row_count_by_table=row_count_by_table,
            validation_checks=checks,
            warnings=[],
        )

    def _validate_text_file(self, planned_file: PlannedReferenceFile, target_path: Path) -> GeneratedFileRecord:
        checks = [ValidationCheck(check_name="file_exists", passed=target_path.exists(), details=str(target_path))]
        text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        for section in planned_file.text_sections:
            checks.append(
                ValidationCheck(
                    check_name=f"section_present:{section.heading}",
                    passed=section.heading in text,
                )
            )
        status: GenerationStatus = "generated" if all(check.passed for check in checks) else "failed"
        return GeneratedFileRecord(
            file_id=planned_file.file_id,
            file_name=planned_file.file_name,
            file_format=planned_file.file_format,
            status=status,
            relative_path=str(Path("reference_files") / planned_file.file_name),
            generation_mode="deterministic_text_reference",
            validation_checks=checks,
            warnings=[],
        )

    def _table_checks(self, table: PlannedTable, frame: pd.DataFrame) -> List[ValidationCheck]:
        expected_columns = [column.name for column in table.columns]
        actual_columns = list(frame.columns)
        return [
            ValidationCheck(
                check_name=f"row_count:{table.sheet_name}",
                passed=len(frame.index) == table.row_count_target,
                details=f"expected={table.row_count_target} actual={len(frame.index)}",
            ),
            ValidationCheck(
                check_name=f"columns:{table.sheet_name}",
                passed=actual_columns == expected_columns,
                details=f"expected={expected_columns} actual={actual_columns}",
            ),
        ]

    def _xlsx_evidence_mappings(
        self,
        planned_file: PlannedReferenceFile,
        table_frames: Dict[str, pd.DataFrame],
    ) -> List[GeneratedEvidenceMapping]:
        mappings: List[GeneratedEvidenceMapping] = []
        for anchor in planned_file.evidence_anchors:
            physical_location = self._xlsx_location_for_anchor(planned_file, anchor, table_frames)
            mappings.append(
                GeneratedEvidenceMapping(
                    evidence_id=anchor.evidence_id,
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    locator=anchor.locator,
                    physical_location=physical_location,
                    semantic_type=anchor.semantic_type,
                )
            )
        return mappings

    def _csv_evidence_mappings(
        self,
        planned_file: PlannedReferenceFile,
        table_frames: Dict[str, pd.DataFrame],
    ) -> List[GeneratedEvidenceMapping]:
        frame = next(iter(table_frames.values()))
        mappings: List[GeneratedEvidenceMapping] = []
        for anchor in planned_file.evidence_anchors:
            column_name = anchor.locator.split(".")[-1]
            physical_location = f"rows[0:{len(frame.index) - 1}].{column_name}" if len(frame.index) else column_name
            mappings.append(
                GeneratedEvidenceMapping(
                    evidence_id=anchor.evidence_id,
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    locator=anchor.locator,
                    physical_location=physical_location,
                    semantic_type=anchor.semantic_type,
                )
            )
        return mappings

    def _json_evidence_mappings(
        self,
        planned_file: PlannedReferenceFile,
        table_frames: Dict[str, pd.DataFrame],
    ) -> List[GeneratedEvidenceMapping]:
        mappings: List[GeneratedEvidenceMapping] = []
        for anchor in planned_file.evidence_anchors:
            column_name = anchor.locator.split(".")[-1]
            if len(table_frames) == 1:
                physical_location = f"$[*].{column_name}"
            else:
                sheet_name = anchor.locator.split(":")[1].split(".")[0]
                physical_location = f"$.{sheet_name}[*].{column_name}"
            mappings.append(
                GeneratedEvidenceMapping(
                    evidence_id=anchor.evidence_id,
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    locator=anchor.locator,
                    physical_location=physical_location,
                    semantic_type=anchor.semantic_type,
                )
            )
        return mappings

    def _text_evidence_mappings(self, planned_file: PlannedReferenceFile) -> List[GeneratedEvidenceMapping]:
        mappings: List[GeneratedEvidenceMapping] = []
        for anchor in planned_file.evidence_anchors:
            mappings.append(
                GeneratedEvidenceMapping(
                    evidence_id=anchor.evidence_id,
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    locator=anchor.locator,
                    physical_location=anchor.locator.split(":", 1)[-1],
                    semantic_type=anchor.semantic_type,
                )
            )
        return mappings

    def _xlsx_location_for_anchor(
        self,
        planned_file: PlannedReferenceFile,
        anchor: EvidenceAnchor,
        table_frames: Dict[str, pd.DataFrame],
    ) -> str:
        try:
            locator_suffix = anchor.locator.split(":", 1)[1]
            sheet_name, column_name = locator_suffix.split(".", 1)
            frame = table_frames[sheet_name]
            column_index = list(frame.columns).index(column_name) + 1
            excel_column = self._excel_column_name(column_index)
            end_row = len(frame.index) + 1
            return f"{sheet_name}!{excel_column}2:{excel_column}{end_row}"
        except Exception:
            return anchor.locator

    def _excel_column_name(self, index: int) -> str:
        result = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _diagnostics(
        self,
        plan: ReferenceFilePlan,
        generated_files: List[GeneratedFileRecord],
        evidence_index: List[GeneratedEvidenceMapping],
    ) -> Dict[str, Any]:
        generated_count = sum(1 for record in generated_files if record.status == "generated")
        skipped_count = sum(1 for record in generated_files if record.status == "skipped")
        failed_count = sum(1 for record in generated_files if record.status == "failed")
        return {
            "planned_file_count": len(plan.planned_files),
            "generated_file_count": generated_count,
            "skipped_file_count": skipped_count,
            "failed_file_count": failed_count,
            "evidence_mapping_count": len(evidence_index),
            "subgraph_confidence": plan.diagnostics.subgraph_confidence,
            "carried_forward_warnings": plan.diagnostics.planner_warnings,
        }

    def _write_outputs(
        self,
        output_dir: Path,
        manifest: GeneratedFileManifest,
        trace_records: List[Dict[str, Any]],
    ) -> None:
        (output_dir / "generated_file_manifest.json").write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output_dir / "evidence_index.json").write_text(
            json.dumps([mapping.model_dump() for mapping in manifest.evidence_index], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "generation_trace.json").write_text(
            json.dumps(
                {
                    "blueprint_id": manifest.blueprint_id,
                    "template_family": manifest.template_family,
                    "trace_records": trace_records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
