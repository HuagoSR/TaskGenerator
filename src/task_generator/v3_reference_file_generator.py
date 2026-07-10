import json
import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from xml.sax.saxutils import escape

import pandas as pd
from pydantic import BaseModel, Field

from task_generator.v3_reference_file_planner import (
    EvidenceAnchor,
    PlannedReferenceFile,
    PlannedTable,
    PlannedTextSection,
    ReferenceFilePlan,
)
from task_generator.v3_source_schema import load_json_file


GenerationStatus = Literal["generated", "skipped", "failed"]
GenerationStrategy = Literal[
    "deterministic_structured",
    "llm_structured_prose",
    "stirrup_agentic_file",
    "external_or_imported",
]
TrustLevel = Literal["deterministic_verified", "deterministic_partial", "llm_proposal", "external_unverified"]
ValidatorStatus = Literal["passed", "partial", "failed", "not_run"]
EvidenceMappingStatus = Literal["finalized", "proposal_only", "missing"]

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
    mapping_source: str = "generator_finalized"


class GeneratedFileRecord(BaseModel):
    file_id: str
    file_name: str
    file_format: str
    status: GenerationStatus
    relative_path: Optional[str] = None
    generation_mode: str
    generation_strategy: GenerationStrategy = "deterministic_structured"
    trust_level: TrustLevel = "deterministic_verified"
    validator_status: ValidatorStatus = "not_run"
    evidence_mapping_status: EvidenceMappingStatus = "missing"
    row_count_by_table: Dict[str, int] = Field(default_factory=dict)
    validation_checks: List[ValidationCheck] = Field(default_factory=list)
    skipped_reason: Optional[str] = None
    support_artifacts: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class GeneratedFileManifest(BaseModel):
    reference_file_generation_version: str = "v3.reference_file_generation.1"
    blueprint_id: str
    template_family: str
    plan_path: str
    output_dir: str
    generated_files: List[GeneratedFileRecord] = Field(default_factory=list)
    evidence_index: List[GeneratedEvidenceMapping] = Field(default_factory=list)
    evidence_index_proposal: List[GeneratedEvidenceMapping] = Field(default_factory=list)
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
        dossier_role_by_file_id = {
            item.file_id: item
            for item in plan.evidence_dossier.file_roles
        }

        for planned_file in plan.planned_files:
            record, mappings, trace = self._generate_file(
                planned_file, reference_dir, plan.blueprint_id, plan.template_family.startswith("finance_")
            )
            dossier_role = dossier_role_by_file_id.get(planned_file.file_id)
            if dossier_role is not None:
                trace["dossier_role"] = dossier_role.role
                trace["dossier_noise_level"] = dossier_role.noise_level
                trace["dossier_contains_conflict"] = dossier_role.contains_conflict
                trace["dossier_contains_missing_fields"] = dossier_role.contains_missing_fields
                trace["dossier_version_relation"] = dossier_role.version_relation
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
        blueprint_id: str,
        production_mode: bool,
    ) -> tuple[GeneratedFileRecord, List[GeneratedEvidenceMapping], Dict[str, Any]]:
        if planned_file.generator_status != "ready_for_deterministic_generation":
            return (
                GeneratedFileRecord(
                    file_id=planned_file.file_id,
                    file_name=planned_file.file_name,
                    file_format=planned_file.file_format,
                    status="skipped",
                    generation_mode="unsupported_or_deferred",
                    generation_strategy=planned_file.preferred_generation_strategy,
                    trust_level="deterministic_partial",
                    validator_status="not_run",
                    evidence_mapping_status="missing",
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
                table_frames = self._table_frames(planned_file.tables, blueprint_id)
                self._write_xlsx(target_path, table_frames, production_mode)
                mappings = self._xlsx_evidence_mappings(planned_file, table_frames)
                record = self._validate_generated_file(planned_file, target_path, table_frames)
            elif file_format == "csv":
                table_frames = self._table_frames(planned_file.tables, blueprint_id)
                self._write_csv(target_path, table_frames, planned_file.file_name)
                mappings = self._csv_evidence_mappings(planned_file, table_frames)
                record = self._validate_generated_file(planned_file, target_path, table_frames)
            elif file_format == "json":
                table_frames = self._table_frames(planned_file.tables, blueprint_id)
                self._write_json(target_path, table_frames)
                mappings = self._json_evidence_mappings(planned_file, table_frames)
                record = self._validate_generated_file(planned_file, target_path, table_frames)
            elif file_format in {"md", "txt"}:
                self._write_text_reference(target_path, planned_file)
                mappings = self._text_evidence_mappings(planned_file)
                record = self._validate_text_file(planned_file, target_path)
            elif file_format == "docx":
                support_artifacts = self._write_docx_reference(target_path, planned_file, production_mode)
                mappings = self._text_evidence_mappings(planned_file)
                record = self._validate_docx_file(planned_file, target_path, support_artifacts)
            else:
                return (
                    GeneratedFileRecord(
                        file_id=planned_file.file_id,
                        file_name=planned_file.file_name,
                        file_format=planned_file.file_format,
                        status="skipped",
                        generation_mode="unsupported_or_deferred",
                        generation_strategy=planned_file.preferred_generation_strategy,
                        trust_level="deterministic_partial",
                        validator_status="not_run",
                        evidence_mapping_status="missing",
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
                    generation_strategy=planned_file.preferred_generation_strategy,
                    trust_level="deterministic_partial",
                    validator_status="failed",
                    evidence_mapping_status="missing",
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
            "generation_strategy": record.generation_strategy,
            "row_count_by_table": record.row_count_by_table,
            "support_artifacts": record.support_artifacts,
            "warnings": record.warnings,
        }
        return record, mappings, trace

    def _table_frames(self, tables: List[PlannedTable], blueprint_id: str) -> Dict[str, pd.DataFrame]:
        return {table.sheet_name: self._build_table_frame(table, blueprint_id) for table in tables}

    def _build_table_frame(self, table: PlannedTable, blueprint_id: str) -> pd.DataFrame:
        production = self._finance_production_frame(table, blueprint_id)
        if production is not None:
            return production
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

    def _finance_production_frame(self, table: PlannedTable, blueprint_id: str) -> Optional[pd.DataFrame]:
        columns = [column.name for column in table.columns]
        names = set(columns)
        variant = int(hashlib.sha256(blueprint_id.encode("utf-8")).hexdigest()[:6], 16) % 700
        if names == {"Bank_ID", "Transaction_Date", "Reference", "Description", "Amount"}:
            rows = []
            for i in range(12):
                ref = f"PAY-{variant + i + 101:04d}" if i < 10 else f"BANK-{variant + i:04d}"
                amount = round((185 + variant / 10 + i * 73.25) * (-1 if i % 3 else 1), 2)
                rows.append({"Bank_ID": f"B-{i+1:03d}", "Transaction_Date": f"2026-06-{i+2:02d}", "Reference": ref,
                             "Description": "Customer receipt" if amount > 0 else "Electronic payment", "Amount": amount})
            return pd.DataFrame(rows, columns=columns)
        if names == {"Ledger_ID", "Posting_Date", "Reference", "Description", "Amount"}:
            rows = []
            for i in range(12):
                ref = f"PAY-{variant + i + 101:04d}" if i < 10 else f"BOOK-{variant + i:04d}"
                amount = round((185 + variant / 10 + i * 73.25) * (-1 if i % 3 else 1), 2)
                rows.append({"Ledger_ID": f"L-{i+1:03d}", "Posting_Date": f"2026-06-{i+2:02d}", "Reference": ref,
                             "Description": "Cash receipt entry" if amount > 0 else "Cash disbursement entry", "Amount": amount})
            return pd.DataFrame(rows, columns=columns)
        if names == {"PO_ID", "Item_ID", "Ordered_Qty", "Unit_Price"}:
            return pd.DataFrame([{"PO_ID": f"PO-{variant+i+1:04d}", "Item_ID": f"ITEM-{i+1:03d}",
                                  "Ordered_Qty": 5 + i, "Unit_Price": round(18.5 + i * 4.25 + variant / 100, 2)} for i in range(10)], columns=columns)
        if names == {"Receipt_ID", "PO_ID", "Item_ID", "Received_Qty"}:
            return pd.DataFrame([{"Receipt_ID": f"GR-{variant+i+1:04d}", "PO_ID": f"PO-{variant+i+1:04d}",
                                  "Item_ID": f"ITEM-{i+1:03d}", "Received_Qty": 5 + i - (1 if i == 7 else 0)} for i in range(10)], columns=columns)
        if names == {"Invoice_ID", "PO_ID", "Item_ID", "Invoiced_Qty", "Unit_Price"}:
            rows = [{"Invoice_ID": f"INV-{variant+i+1:04d}", "PO_ID": f"PO-{variant+i+1:04d}", "Item_ID": f"ITEM-{i+1:03d}",
                     "Invoiced_Qty": 5 + i + (2 if i == 7 else 0),
                     "Unit_Price": round(18.5 + i * 4.25 + variant / 100 + (3 if i == 4 else 0), 2)} for i in range(10)]
            rows.append(dict(rows[2], Invoice_ID=f"INV-{variant+99:04d}"))
            return pd.DataFrame(rows, columns=columns)
        if {"Transaction_ID", "Employee_ID", "Category", "Amount", "Receipt_Available"}.issubset(names):
            categories = ["Meals", "Hotel", "Airfare", "Office Supplies", "Entertainment"]
            rows = []
            for i in range(14):
                amount = round(35 + variant / 20 + i * 61.4, 2)
                rows.append({"Transaction_ID": f"TX-{variant+i+1:04d}", "Employee_ID": f"EMP-{(i%5)+1:03d}",
                             "Expense_Date": f"2026-06-{i+1:02d}", "Category": categories[i % len(categories)], "Amount": amount,
                             "Receipt_Available": "No" if i in {3, 9} else "Yes", "Approval_Level": "Director" if i in {6, 12} else "Manager",
                             "Business_Purpose": f"Client or operating activity {variant+i+1}"})
            return pd.DataFrame(rows, columns=columns)
        return None

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

    def _write_xlsx(self, target_path: Path, table_frames: Dict[str, pd.DataFrame], production_mode: bool = False) -> None:
        with pd.ExcelWriter(target_path, engine="openpyxl" if production_mode else None) as writer:
            for sheet_name, frame in table_frames.items():
                frame.to_excel(writer, sheet_name=sheet_name, index=False)
                if not production_mode:
                    continue
                sheet = writer.book[sheet_name]
                sheet.freeze_panes = "A2"
                sheet.auto_filter.ref = sheet.dimensions
                for cell in sheet[1]:
                    cell.font = cell.font.copy(bold=True, color="FFFFFF")
                    cell.fill = cell.fill.copy(fill_type="solid", fgColor="1F4E78")
                for index, column in enumerate(frame.columns, 1):
                    width = min(42, max(12, len(str(column)) + 2, *(len(str(value)) + 2 for value in frame[column].head(30))))
                    sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
                    if "Amount" in str(column) or "Price" in str(column):
                        for cell in sheet.iter_cols(min_col=index, max_col=index, min_row=2):
                            for item in cell:
                                item.number_format = '#,##0.00;[Red]-#,##0.00'

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
            if section.clause_id:
                lines.append(f"## {section.clause_id} {section.heading}")
                lines.append(self._policy_clause_body(section))
            else:
                lines.append(section.heading)
                lines.append(f"This section is planned deterministically for {section.evidence_role}.")
            lines.append("")
        target_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def _write_docx_reference(
        self,
        target_path: Path,
        planned_file: PlannedReferenceFile,
        production_mode: bool = False,
    ) -> List[str]:
        if planned_file.file_name == "expense_policy.docx":
            paragraphs = [
                "Expense and Corporate Card Policy",
                "Purpose", "Define the evidence and approval rules for employee expenses.",
                "Applicable Guidance", "Apply POL-001 through POL-004 to every supplied transaction.",
                "Evidence Interpretation", "Use the receipt, approval, category, amount, and business-purpose fields as supplied.",
                "Decision Rules", "Classify a transaction as an exception when any applicable clause is not satisfied.",
                "POL-001 Receipt requirement", "A receipt is required for every transaction of 75.00 or more.",
                "POL-002 Meal threshold", "Meals above 100.00 per person require Director approval.",
                "POL-003 Entertainment", "Entertainment transactions require Director approval and a stated business purpose.",
                "POL-004 Missing evidence", "A missing receipt or business purpose must be classified as an exception pending follow-up.",
            ]
        else:
            paragraphs = [planned_file.file_name]
        if production_mode:
            paragraphs.append(f"Control package ID: {planned_file.file_id}")
        for section in ([] if planned_file.file_name == "expense_policy.docx" else planned_file.text_sections):
            title = f"{section.clause_id} {section.heading}" if section.clause_id else section.heading
            paragraphs.append(title)
            if section.clause_id:
                paragraphs.append(self._policy_clause_body(section))
            else:
                paragraphs.append(f"This section is planned deterministically for {section.evidence_role}.")

        self._write_minimal_docx(target_path, paragraphs, production_mode)
        clause_map_name = f"{Path(planned_file.file_name).stem}_clause_map.json"
        clause_map_path = target_path.parent / clause_map_name
        clause_map_payload = {
            "file_name": planned_file.file_name,
            **({"control_package_id": planned_file.file_id} if production_mode else {}),
            "clauses": [
                {
                    "clause_id": section.clause_id,
                    "heading": section.heading,
                    "evidence_role": section.evidence_role,
                    "locator": f"{planned_file.file_name}:{section.clause_id or section.heading}",
                }
                for section in planned_file.text_sections
            ],
        }
        clause_map_path.write_text(
            json.dumps(clause_map_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return [str(Path("reference_files") / clause_map_name)]

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
            generation_strategy=planned_file.preferred_generation_strategy,
            trust_level="deterministic_verified" if status == "generated" else "deterministic_partial",
            validator_status="passed" if status == "generated" else "failed",
            evidence_mapping_status="finalized",
            row_count_by_table=row_count_by_table,
            validation_checks=checks,
            support_artifacts=[],
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
            generation_strategy=planned_file.preferred_generation_strategy,
            trust_level="deterministic_verified" if status == "generated" else "deterministic_partial",
            validator_status="passed" if status == "generated" else "failed",
            evidence_mapping_status="finalized",
            validation_checks=checks,
            support_artifacts=[],
            warnings=[],
        )

    def _validate_docx_file(
        self,
        planned_file: PlannedReferenceFile,
        target_path: Path,
        support_artifacts: List[str],
    ) -> GeneratedFileRecord:
        checks = [ValidationCheck(check_name="file_exists", passed=target_path.exists(), details=str(target_path))]
        xml_text = self._read_docx_document_xml(target_path) if target_path.exists() else ""
        for section in planned_file.text_sections:
            title = f"{section.clause_id} {section.heading}" if section.clause_id else section.heading
            checks.append(
                ValidationCheck(
                    check_name=f"section_present:{title}",
                    passed=title in xml_text,
                )
            )
            if section.clause_id:
                checks.append(
                    ValidationCheck(
                        check_name=f"clause_present:{section.clause_id}",
                        passed=section.clause_id in xml_text,
                    )
                )
        status: GenerationStatus = "generated" if all(check.passed for check in checks) else "failed"
        return GeneratedFileRecord(
            file_id=planned_file.file_id,
            file_name=planned_file.file_name,
            file_format=planned_file.file_format,
            status=status,
            relative_path=str(Path("reference_files") / planned_file.file_name),
            generation_mode="deterministic_policy_reference",
            generation_strategy=planned_file.preferred_generation_strategy,
            trust_level="deterministic_verified" if status == "generated" else "deterministic_partial",
            validator_status="passed" if status == "generated" else "failed",
            evidence_mapping_status="finalized",
            validation_checks=checks,
            support_artifacts=support_artifacts,
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
            physical_location = anchor.locator.split(":", 1)[-1]
            if planned_file.file_format.lower() == "docx" and ":" in anchor.locator:
                physical_location = f"clause:{anchor.locator.split(':', 1)[1]}"
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

    def _policy_clause_body(self, section: PlannedTextSection) -> str:
        clause_id = section.clause_id or "POL-000"
        if clause_id == "POL-001":
            return (
                "Use the source evidence workbook as the primary record for identifying relevant items, "
                "and match each material conclusion to one or more cited evidence identifiers."
            )
        if clause_id == "POL-002":
            return (
                "When the evidence package contains unresolved discrepancies or missing support, "
                "describe them separately from confirmed exceptions and avoid unsupported resolution."
            )
        if clause_id == "POL-003":
            return (
                "A conclusion may be treated as review-ready only when the cited evidence and the stated rationale "
                "are both visible in the candidate reference package."
            )
        if clause_id == "POL-004":
            return (
                "If policy alignment or evidence sufficiency cannot be confirmed from the provided files, "
                "escalate the issue as unresolved rather than inferring a final answer."
            )
        return f"This clause provides deterministic guidance for {section.heading.lower()}."

    def _write_minimal_docx(self, target_path: Path, paragraphs: List[str], production_mode: bool = False) -> None:
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""
        relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""
        document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""
        created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(target_path.stem)}</dc:title>
  <dc:creator>TaskGenerator</dc:creator>
  <cp:lastModifiedBy>TaskGenerator</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""
        app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>TaskGenerator</Application>
</Properties>
"""
        document_xml = self._document_xml(paragraphs, production_mode)
        with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", relationships)
            archive.writestr("word/document.xml", document_xml)
            archive.writestr("word/_rels/document.xml.rels", document_rels)
            archive.writestr("docProps/core.xml", core_xml)
            archive.writestr("docProps/app.xml", app_xml)

    def _document_xml(self, paragraphs: List[str], production_mode: bool = False) -> str:
        body = []
        for paragraph in paragraphs:
            body.append(
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                + escape(paragraph)
                + "</w:t></w:r></w:p>"
            )
        body.append(
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
            if production_mode else "<w:sectPr/>"
        )
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
            "<w:body>"
            + "".join(body)
            + "</w:body></w:document>"
        )

    def _read_docx_document_xml(self, target_path: Path) -> str:
        with zipfile.ZipFile(target_path, "r") as archive:
            return archive.read("word/document.xml").decode("utf-8", errors="ignore")

    def _diagnostics(
        self,
        plan: ReferenceFilePlan,
        generated_files: List[GeneratedFileRecord],
        evidence_index: List[GeneratedEvidenceMapping],
    ) -> Dict[str, Any]:
        generated_count = sum(1 for record in generated_files if record.status == "generated")
        skipped_count = sum(1 for record in generated_files if record.status == "skipped")
        failed_count = sum(1 for record in generated_files if record.status == "failed")
        strategy_counts: Dict[str, int] = {}
        validator_counts: Dict[str, int] = {}
        for record in generated_files:
            strategy_counts[record.generation_strategy] = strategy_counts.get(record.generation_strategy, 0) + 1
            validator_counts[record.validator_status] = validator_counts.get(record.validator_status, 0) + 1
        return {
            "planned_file_count": len(plan.planned_files),
            "generated_file_count": generated_count,
            "skipped_file_count": skipped_count,
            "failed_file_count": failed_count,
            "evidence_mapping_count": len(evidence_index),
            "generation_strategy_counts": dict(sorted(strategy_counts.items())),
            "validator_status_counts": dict(sorted(validator_counts.items())),
            "subgraph_confidence": plan.diagnostics.subgraph_confidence,
            "dossier_id": plan.evidence_dossier.dossier_id,
            "candidate_visible_file_count": len(plan.evidence_dossier.candidate_visible_files),
            "teacher_only_file_count": len(plan.evidence_dossier.teacher_only_files),
            "cross_file_constraint_count": len(plan.evidence_dossier.cross_file_constraints),
            "distractor_item_count": len(plan.evidence_dossier.distractor_items),
            "synthetic_artifact_count": len(plan.evidence_dossier.synthetic_artifacts),
            "synthetic_artifact_role_counts": self._synthetic_artifact_role_counts(plan),
            "carried_forward_warnings": plan.diagnostics.planner_warnings,
        }

    def _synthetic_artifact_role_counts(self, plan: ReferenceFilePlan) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for artifact in plan.evidence_dossier.synthetic_artifacts:
            counts[artifact.role] = counts.get(artifact.role, 0) + 1
        return dict(sorted(counts.items()))

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
        (output_dir / "evidence_index_proposal.json").write_text(
            json.dumps(
                [mapping.model_dump() for mapping in manifest.evidence_index_proposal],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (output_dir / "generation_trace.json").write_text(
            json.dumps(
                {
                    "blueprint_id": manifest.blueprint_id,
                    "template_family": manifest.template_family,
                    "dossier_summary": {
                        "dossier_id": manifest.diagnostics.get("dossier_id"),
                        "candidate_visible_file_count": manifest.diagnostics.get("candidate_visible_file_count", 0),
                        "cross_file_constraint_count": manifest.diagnostics.get("cross_file_constraint_count", 0),
                        "distractor_item_count": manifest.diagnostics.get("distractor_item_count", 0),
                        "synthetic_artifact_count": manifest.diagnostics.get("synthetic_artifact_count", 0),
                        "synthetic_artifact_role_counts": manifest.diagnostics.get("synthetic_artifact_role_counts", {}),
                    },
                    "trace_records": trace_records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
