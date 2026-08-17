import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_deliverable_contract import (
    DeliverableContractV1,
    DeliverableContractValidator,
)
from task_generator.v3_source_schema import load_json_file


ValidationSeverity = Literal["blocking", "warning", "info"]
ValidationStatus = Literal["invalid", "draft_compatible", "candidate_ready_compatible"]


class RwTaskExportValidationRequest(BaseModel):
    case_dir: str
    output_path: Optional[str] = None


class RwTaskExportValidationFinding(BaseModel):
    finding_id: str
    check_name: str
    severity: ValidationSeverity
    passed: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class RwTaskExportValidationReport(BaseModel):
    validation_version: str = "v3.rw_task_export_validation.2"
    request: RwTaskExportValidationRequest
    case_dir: str
    case_id: str = "unknown"
    validation_status: ValidationStatus
    blocking_count: int = 0
    warning_count: int = 0
    reference_file_count: int = 0
    deliverable_file_count: int = 0
    findings: List[RwTaskExportValidationFinding] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RwTaskExportValidator:
    """Validate a local rw-task-style export without running model evaluation."""

    REQUIRED_DATASET_FIELDS = [
        "task_id",
        "sector",
        "occupation",
        "motif",
        "prompt",
        "reference_files",
        "deliverable_files",
        "rubric",
        "rubric_json",
        "extra",
    ]

    def validate(
        self,
        case_dir: str | Path,
        output_path: str | Path | None = None,
    ) -> RwTaskExportValidationReport:
        case_path = Path(case_dir)
        request = RwTaskExportValidationRequest(
            case_dir=str(case_path),
            output_path=str(output_path) if output_path else None,
        )
        findings: List[RwTaskExportValidationFinding] = []

        dataset_row_path = case_path / "dataset_row.json"
        export_report_path = case_path / "rw_task_export_report.json"
        reference_dir = case_path / "reference_files"
        deliverable_dir = case_path / "deliverable_files"
        artifacts_dir = case_path / "artifacts"

        dataset_row: Dict[str, Any] | None = None
        export_report: Dict[str, Any] | None = None

        if not case_path.exists():
            findings.append(
                self._finding(
                    "case_dir_exists",
                    "blocking",
                    False,
                    "Case directory does not exist.",
                    {"case_dir": str(case_path)},
                )
            )
        if dataset_row_path.exists():
            try:
                dataset_row = load_json_file(str(dataset_row_path))
                findings.append(
                    self._finding(
                        "dataset_row_readable",
                        "info",
                        True,
                        "dataset_row.json is readable JSON.",
                    )
                )
            except Exception as exc:
                findings.append(
                    self._finding(
                        "dataset_row_readable",
                        "blocking",
                        False,
                        "dataset_row.json is not readable JSON.",
                        {"error_type": type(exc).__name__, "error": str(exc)},
                    )
                )
        else:
            findings.append(
                self._finding(
                    "dataset_row_present",
                    "blocking",
                    False,
                    "dataset_row.json is missing.",
                    {"path": str(dataset_row_path)},
                )
            )

        if export_report_path.exists():
            try:
                export_report = load_json_file(str(export_report_path))
                findings.append(
                    self._finding(
                        "export_report_readable",
                        "info",
                        True,
                        "rw_task_export_report.json is readable JSON.",
                    )
                )
            except Exception as exc:
                findings.append(
                    self._finding(
                        "export_report_readable",
                        "warning",
                        False,
                        "rw_task_export_report.json is not readable JSON.",
                        {"error_type": type(exc).__name__, "error": str(exc)},
                    )
                )
        else:
            findings.append(
                self._finding(
                    "export_report_present",
                    "warning",
                    False,
                    "rw_task_export_report.json is missing.",
                    {"path": str(export_report_path)},
                )
            )

        if dataset_row is not None:
            findings.extend(self._dataset_field_findings(dataset_row))
            findings.extend(
                self._reference_file_findings(
                    case_path=case_path,
                    reference_dir=reference_dir,
                    artifacts_dir=artifacts_dir,
                    dataset_row=dataset_row,
                )
            )
            findings.extend(
                self._deliverable_findings(
                    case_path=case_path,
                    deliverable_dir=deliverable_dir,
                    dataset_row=dataset_row,
                )
            )
            findings.extend(self._deliverable_contract_findings(case_path, dataset_row))
            findings.extend(self._draft_status_findings(dataset_row, export_report))
            findings.extend(self._rubric_findings(dataset_row))

        status = self._status(findings, dataset_row)
        report = RwTaskExportValidationReport(
            request=request,
            case_dir=str(case_path),
            case_id=str((dataset_row or {}).get("task_id") or "unknown"),
            validation_status=status,
            blocking_count=sum(1 for item in findings if item.severity == "blocking" and not item.passed),
            warning_count=sum(1 for item in findings if item.severity == "warning" and not item.passed),
            reference_file_count=len((dataset_row or {}).get("reference_files") or []),
            deliverable_file_count=len((dataset_row or {}).get("deliverable_files") or []),
            findings=findings,
            notes=[
                "This validator checks local export structure only; it does not run rw-task evaluation.",
                "Draft-compatible exports are suitable for inspection, not final training data.",
            ],
        )
        self.write_report(report, output_path or (case_path / "rw_task_export_validation_report.json"))
        return report

    def write_report(
        self,
        report: RwTaskExportValidationReport,
        output_path: str | Path,
    ) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _dataset_field_findings(self, dataset_row: Dict[str, Any]) -> List[RwTaskExportValidationFinding]:
        findings: List[RwTaskExportValidationFinding] = []
        for field_name in self.REQUIRED_DATASET_FIELDS:
            value = dataset_row.get(field_name)
            passed = value is not None and value != "" and value != []
            findings.append(
                self._finding(
                    f"dataset_field:{field_name}",
                    "blocking",
                    passed,
                    f"Required dataset field `{field_name}` is present."
                    if passed
                    else f"Required dataset field `{field_name}` is missing or empty.",
                )
            )

        if not isinstance(dataset_row.get("reference_files"), list):
            findings.append(
                self._finding(
                    "reference_files_type",
                    "blocking",
                    False,
                    "`reference_files` must be a list.",
                )
            )
        if not isinstance(dataset_row.get("deliverable_files"), list):
            findings.append(
                self._finding(
                    "deliverable_files_type",
                    "blocking",
                    False,
                    "`deliverable_files` must be a list.",
                )
            )
        return findings

    def _reference_file_findings(
        self,
        case_path: Path,
        reference_dir: Path,
        artifacts_dir: Path,
        dataset_row: Dict[str, Any],
    ) -> List[RwTaskExportValidationFinding]:
        findings: List[RwTaskExportValidationFinding] = []
        references = dataset_row.get("reference_files") or []

        findings.append(
            self._finding(
                "reference_dir_present",
                "blocking",
                reference_dir.exists(),
                "reference_files directory exists."
                if reference_dir.exists()
                else "reference_files directory is missing.",
                {"path": str(reference_dir)},
            )
        )

        support_names = {
            path.name
            for path in (artifacts_dir / "reference_support").glob("*")
            if path.is_file()
        }
        for relative_path in references:
            ref_path = case_path / Path(str(relative_path))
            findings.append(
                self._finding(
                    f"reference_file_exists:{Path(str(relative_path)).name}",
                    "blocking",
                    ref_path.exists() and ref_path.is_file(),
                    f"Reference file exists: {relative_path}."
                    if ref_path.exists() and ref_path.is_file()
                    else f"Reference file is missing: {relative_path}.",
                    {"relative_path": str(relative_path), "resolved_path": str(ref_path)},
                )
            )
            if Path(str(relative_path)).name in support_names:
                findings.append(
                    self._finding(
                        f"support_not_candidate_visible:{Path(str(relative_path)).name}",
                        "blocking",
                        False,
                        "Support reference artifact is incorrectly exposed as candidate-visible.",
                        {"relative_path": str(relative_path)},
                    )
                )

        return findings

    def _deliverable_findings(
        self,
        case_path: Path,
        deliverable_dir: Path,
        dataset_row: Dict[str, Any],
    ) -> List[RwTaskExportValidationFinding]:
        findings: List[RwTaskExportValidationFinding] = []
        deliverables = dataset_row.get("deliverable_files") or []
        manifest_path = deliverable_dir / "expected_deliverables.json"
        findings.append(
            self._finding(
                "deliverable_dir_present",
                "blocking",
                deliverable_dir.exists(),
                "deliverable_files directory exists."
                if deliverable_dir.exists()
                else "deliverable_files directory is missing.",
                {"path": str(deliverable_dir)},
            )
        )
        findings.append(
            self._finding(
                "expected_deliverables_manifest_present",
                "warning",
                manifest_path.exists(),
                "expected_deliverables.json is present."
                if manifest_path.exists()
                else "expected_deliverables.json is missing.",
                {"path": str(manifest_path)},
            )
        )
        for relative_path in deliverables:
            resolved = case_path / Path(str(relative_path))
            findings.append(
                self._finding(
                    f"deliverable_not_pregenerated:{Path(str(relative_path)).name}",
                    "warning",
                    not resolved.exists(),
                    f"Expected deliverable is not pre-generated: {relative_path}."
                    if not resolved.exists()
                    else f"Expected deliverable already exists: {relative_path}.",
                    {"relative_path": str(relative_path), "resolved_path": str(resolved)},
                )
            )
        return findings

    def _draft_status_findings(
        self,
        dataset_row: Dict[str, Any],
        export_report: Dict[str, Any] | None,
    ) -> List[RwTaskExportValidationFinding]:
        findings: List[RwTaskExportValidationFinding] = []
        extra = dataset_row.get("extra") or {}
        export_status = extra.get("export_status")
        not_final = extra.get("not_final_training_data")
        export_ready = extra.get("rw_task_export_ready")

        if export_status == "draft_revise_only":
            findings.append(
                self._finding(
                    "draft_not_final_training_data",
                    "blocking",
                    not_final is True,
                    "Draft export is marked as not final training data."
                    if not_final is True
                    else "Draft export is not marked as not final training data.",
                )
            )
            findings.append(
                self._finding(
                    "draft_not_export_ready",
                    "blocking",
                    export_ready is False,
                    "Draft export is not marked rw_task_export_ready."
                    if export_ready is False
                    else "Draft export incorrectly appears rw_task_export_ready.",
                )
            )
        elif export_status == "candidate_ready_export":
            findings.append(
                self._finding(
                    "candidate_ready_export_flag",
                    "blocking",
                    export_ready is True and not_final is False,
                    "Candidate-ready export flags are consistent."
                    if export_ready is True and not_final is False
                    else "Candidate-ready export flags are inconsistent.",
                )
            )
        else:
            findings.append(
                self._finding(
                    "export_status_known",
                    "blocking",
                    False,
                    "Export status is missing or unknown.",
                    {"export_status": export_status},
                )
            )

        if export_report:
            report_decision = export_report.get("export_decision")
            row_decision = ((extra.get("rw_task_exporter") or {}).get("export_decision"))
            findings.append(
                self._finding(
                    "export_report_matches_dataset_row",
                    "warning",
                    report_decision == row_decision,
                    "Export report decision matches dataset row metadata."
                    if report_decision == row_decision
                    else "Export report decision differs from dataset row metadata.",
                    {"export_report_decision": report_decision, "dataset_row_decision": row_decision},
                )
            )
        return findings

    def _deliverable_contract_findings(
        self,
        case_path: Path,
        dataset_row: Dict[str, Any],
    ) -> List[RwTaskExportValidationFinding]:
        findings: List[RwTaskExportValidationFinding] = []
        extra = dataset_row.get("extra") or {}
        mode = str(extra.get("deliverable_contract_mode") or "diagnostic")
        blocking = mode == "blocking"
        severity: ValidationSeverity = "blocking" if blocking else "warning"
        contract_path = case_path / "deliverable_contract.json"
        contract_payload = extra.get("deliverable_contract")
        if contract_path.exists():
            try:
                contract_payload = load_json_file(str(contract_path))
            except Exception as exc:
                findings.append(
                    self._finding(
                        "deliverable_contract_readable",
                        severity,
                        False,
                        "deliverable_contract.json is unreadable.",
                        {"error_type": type(exc).__name__, "error": str(exc)},
                    )
                )
                return findings
        if not isinstance(contract_payload, dict):
            findings.append(
                self._finding(
                    "deliverable_contract_present",
                    severity,
                    False,
                    "A versioned deliverable contract is required."
                    if blocking
                    else "No versioned deliverable contract is present; legacy export remains diagnostic.",
                    {"mode": mode},
                )
            )
            return findings
        try:
            contract = DeliverableContractV1.model_validate(contract_payload)
        except Exception as exc:
            findings.append(
                self._finding(
                    "deliverable_contract_schema_valid",
                    severity,
                    False,
                    "Deliverable contract does not satisfy the V1 schema.",
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
            )
            return findings

        findings.append(
            self._finding(
                "deliverable_contract_schema_valid",
                severity,
                True,
                "Deliverable contract satisfies the V1 schema.",
                {"contract_version": contract.contract_version, "mode": mode},
            )
        )
        contract_paths = [item.relative_path for item in contract.deliverables]
        row_paths = [str(item).replace("\\", "/") for item in dataset_row.get("deliverable_files") or []]
        findings.append(
            self._finding(
                "dataset_row_matches_deliverable_contract",
                severity,
                row_paths == contract_paths,
                "dataset_row deliverables exactly match the authoritative contract."
                if row_paths == contract_paths
                else "dataset_row deliverables differ from the authoritative contract.",
                {"dataset_row": row_paths, "contract": contract_paths},
            )
        )
        manifest_path = case_path / "deliverable_files" / "expected_deliverables.json"
        manifest_paths: List[str] = []
        if manifest_path.exists():
            try:
                manifest = load_json_file(str(manifest_path))
                manifest_paths = [
                    str(item).replace("\\", "/")
                    for item in manifest.get("deliverables") or []
                ]
            except Exception:
                manifest_paths = []
        findings.append(
            self._finding(
                "expected_manifest_matches_deliverable_contract",
                severity,
                manifest_paths == contract_paths,
                "Expected-deliverables manifest exactly matches the authoritative contract."
                if manifest_paths == contract_paths
                else "Expected-deliverables manifest differs from the authoritative contract.",
                {"manifest": manifest_paths, "contract": contract_paths},
            )
        )
        contract_report = DeliverableContractValidator().validate(
            contract=contract,
            prompt=str(dataset_row.get("prompt") or ""),
            reference_files=list(dataset_row.get("reference_files") or []),
        )
        for item in contract_report.findings:
            findings.append(
                self._finding(
                    f"deliverable_contract:{item.check_name}",
                    severity if item.severity == "blocking" else item.severity,
                    item.passed,
                    item.message,
                    item.details,
                )
            )
        return findings

    def _rubric_findings(self, dataset_row: Dict[str, Any]) -> List[RwTaskExportValidationFinding]:
        rubric_json = dataset_row.get("rubric_json")
        rubric_string_valid = False
        parsed_type = None
        if isinstance(rubric_json, str):
            try:
                parsed = json.loads(rubric_json)
                rubric_string_valid = isinstance(parsed, list)
                parsed_type = type(parsed).__name__
            except json.JSONDecodeError:
                rubric_string_valid = False
        return [
            self._finding(
                "rubric_json_compatible",
                "blocking",
                isinstance(rubric_json, (dict, list)) or rubric_string_valid,
                "rubric_json is compatible structured JSON or a stringified rw-task rubric-item list."
                if isinstance(rubric_json, (dict, list)) or rubric_string_valid
                else "rubric_json should be structured JSON or a stringified rubric-item list.",
                {
                    "stored_type": type(rubric_json).__name__ if rubric_json is not None else "none",
                    "parsed_type": parsed_type,
                },
            )
        ]

    def _status(
        self,
        findings: List[RwTaskExportValidationFinding],
        dataset_row: Dict[str, Any] | None,
    ) -> ValidationStatus:
        if any(item.severity == "blocking" and not item.passed for item in findings):
            return "invalid"
        extra = (dataset_row or {}).get("extra") or {}
        if extra.get("export_status") == "candidate_ready_export":
            return "candidate_ready_compatible"
        return "draft_compatible"

    def _finding(
        self,
        check_name: str,
        severity: ValidationSeverity,
        passed: bool,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> RwTaskExportValidationFinding:
        return RwTaskExportValidationFinding(
            finding_id=self._stable_id("rwval", [check_name, message]),
            check_name=check_name,
            severity=severity,
            passed=passed,
            message=message,
            details=details or {},
        )

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        import hashlib

        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
