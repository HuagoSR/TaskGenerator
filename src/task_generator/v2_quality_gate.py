import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from task_generator.v2_schema import GoldenRun, TaskBlueprint, TrainingAnnotation, V2DatasetPackage


Severity = Literal["error", "warning", "info"]


@dataclass
class GateIssue:
    severity: Severity
    code: str
    message: str


@dataclass
class GateSectionResult:
    section: str
    passed: bool
    issues: list[GateIssue] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateReport:
    task_id: str
    passed: bool
    blocking_issue_count: int
    warning_count: int
    sections: list[GateSectionResult]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "blocking_issue_count": self.blocking_issue_count,
            "warning_count": self.warning_count,
            "sections": [
                {
                    "section": section.section,
                    "passed": section.passed,
                    "issues": [asdict(issue) for issue in section.issues],
                    "diagnostics": section.diagnostics,
                }
                for section in self.sections
            ],
        }


class V2SampleQualityGate:
    REQUIRED_CASE_FILES = [
        "task_blueprint.json",
        "training_annotation.json",
        "golden_run_package.json",
        "dataset_shell.json",
        "prompt.md",
        "golden_prompt.md",
    ]
    REQUIRED_GOLDEN_FILES = [
        "golden_intermediate_values.json",
        "golden_grading_anchors.json",
        "golden_run_log.json",
    ]

    def assess_case(self, case_dir: str | Path, rw_task_case_dir: str | Path | None = None) -> GateReport:
        case_path = Path(case_dir)
        rw_task_path = Path(rw_task_case_dir) if rw_task_case_dir else None
        sections: list[GateSectionResult] = []

        sections.append(self._check_required_files(case_path, rw_task_path))

        blueprint = self._load_model(case_path / "task_blueprint.json", TaskBlueprint)
        annotation = self._load_model(case_path / "training_annotation.json", TrainingAnnotation)
        golden_run = self._load_model(case_path / "golden_run_package.json", GoldenRun)
        dataset_shell = self._load_model(case_path / "dataset_shell.json", V2DatasetPackage)

        sections.append(self._check_schema_parse(blueprint, annotation, golden_run, dataset_shell))
        sections.append(self._check_id_linkage(blueprint, annotation, golden_run, dataset_shell))
        sections.append(self._check_reference_files(case_path, blueprint, dataset_shell))
        sections.append(self._check_golden_artifacts(case_path, blueprint, golden_run))
        if rw_task_path is not None:
            sections.append(self._check_rw_task_export(rw_task_path, dataset_shell))

        blocking_issue_count = sum(
            1 for section in sections for issue in section.issues if issue.severity == "error"
        )
        warning_count = sum(
            1 for section in sections for issue in section.issues if issue.severity == "warning"
        )
        task_id = dataset_shell.task_id if dataset_shell else case_path.name
        return GateReport(
            task_id=task_id,
            passed=blocking_issue_count == 0,
            blocking_issue_count=blocking_issue_count,
            warning_count=warning_count,
            sections=sections,
        )

    def write_report(self, report: GateReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def assess_batch(
        self,
        batch_dir: str | Path,
        rw_task_batch_dir: str | Path | None = None,
    ) -> list[GateReport]:
        batch_path = Path(batch_dir)
        rw_task_batch_path = Path(rw_task_batch_dir) if rw_task_batch_dir else None
        reports: list[GateReport] = []

        for case_dir in sorted(batch_path.glob("TASK_*")):
            if not case_dir.is_dir():
                continue
            rw_task_case_dir = rw_task_batch_path / case_dir.name if rw_task_batch_path else None
            reports.append(self.assess_case(case_dir, rw_task_case_dir))
        return reports

    def write_batch_report(self, reports: list[GateReport], output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [report.to_json_dict() for report in reports]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _check_required_files(self, case_path: Path, rw_task_path: Path | None) -> GateSectionResult:
        issues: list[GateIssue] = []
        for rel in self.REQUIRED_CASE_FILES:
            if not (case_path / rel).exists():
                issues.append(GateIssue("error", "missing_case_file", f"Missing required case file: {rel}"))
        for rel in self.REQUIRED_GOLDEN_FILES:
            if not (case_path / "golden_run" / rel).exists():
                issues.append(GateIssue("error", "missing_golden_file", f"Missing golden artifact: golden_run/{rel}"))
        if not (case_path / "reference_files").exists():
            issues.append(GateIssue("error", "missing_reference_dir", "Missing reference_files directory."))
        if rw_task_path is not None and not (rw_task_path / "dataset_row.json").exists():
            issues.append(GateIssue("error", "missing_rw_task_export", "Missing rw-task dataset_row.json export."))

        return GateSectionResult(
            section="required_files",
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
        )

    def _check_schema_parse(
        self,
        blueprint: TaskBlueprint | None,
        annotation: TrainingAnnotation | None,
        golden_run: GoldenRun | None,
        dataset_shell: V2DatasetPackage | None,
    ) -> GateSectionResult:
        issues: list[GateIssue] = []
        diagnostics = {
            "blueprint_loaded": blueprint is not None,
            "annotation_loaded": annotation is not None,
            "golden_run_loaded": golden_run is not None,
            "dataset_shell_loaded": dataset_shell is not None,
        }
        for key, ok in diagnostics.items():
            if not ok:
                issues.append(GateIssue("error", "schema_parse_failure", f"Failed to parse required object: {key}"))
        return GateSectionResult(
            section="schema_parse",
            passed=not issues,
            issues=issues,
            diagnostics=diagnostics,
        )

    def _check_id_linkage(
        self,
        blueprint: TaskBlueprint | None,
        annotation: TrainingAnnotation | None,
        golden_run: GoldenRun | None,
        dataset_shell: V2DatasetPackage | None,
    ) -> GateSectionResult:
        issues: list[GateIssue] = []
        diagnostics: dict[str, Any] = {}
        if not all([blueprint, annotation, golden_run, dataset_shell]):
            issues.append(GateIssue("error", "linkage_unchecked", "ID linkage could not be checked because one or more objects failed to load."))
            return GateSectionResult(section="id_linkage", passed=False, issues=issues, diagnostics=diagnostics)

        diagnostics = {
            "blueprint_id": blueprint.blueprint_id,
            "annotation_blueprint_id": annotation.blueprint_id,
            "golden_blueprint_id": golden_run.blueprint_id,
            "dataset_shell_blueprint_id": dataset_shell.extra.get("blueprint_id"),
            "dataset_shell_annotation_id": dataset_shell.extra.get("training_annotation_id"),
            "dataset_shell_golden_run_id": dataset_shell.extra.get("golden_run_id"),
        }
        if annotation.blueprint_id != blueprint.blueprint_id:
            issues.append(GateIssue("error", "annotation_blueprint_mismatch", "TrainingAnnotation.blueprint_id does not match TaskBlueprint.blueprint_id."))
        if golden_run.blueprint_id != blueprint.blueprint_id:
            issues.append(GateIssue("error", "golden_blueprint_mismatch", "GoldenRun.blueprint_id does not match TaskBlueprint.blueprint_id."))
        if dataset_shell.extra.get("blueprint_id") != blueprint.blueprint_id:
            issues.append(GateIssue("error", "dataset_shell_blueprint_mismatch", "dataset_shell.extra.blueprint_id does not match TaskBlueprint.blueprint_id."))
        if dataset_shell.extra.get("training_annotation_id") != annotation.annotation_id:
            issues.append(GateIssue("error", "dataset_shell_annotation_mismatch", "dataset_shell.extra.training_annotation_id does not match TrainingAnnotation.annotation_id."))
        if dataset_shell.extra.get("golden_run_id") != golden_run.golden_run_id:
            issues.append(GateIssue("error", "dataset_shell_golden_mismatch", "dataset_shell.extra.golden_run_id does not match GoldenRun.golden_run_id."))

        return GateSectionResult(
            section="id_linkage",
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            diagnostics=diagnostics,
        )

    def _check_reference_files(
        self,
        case_path: Path,
        blueprint: TaskBlueprint | None,
        dataset_shell: V2DatasetPackage | None,
    ) -> GateSectionResult:
        issues: list[GateIssue] = []
        diagnostics: dict[str, Any] = {}
        if not blueprint or not dataset_shell:
            issues.append(GateIssue("error", "reference_check_unavailable", "Reference-file checks could not run because required objects failed to load."))
            return GateSectionResult(section="reference_files", passed=False, issues=issues)

        expected_names = [spec.file_name for spec in blueprint.data_spec.reference_files]
        existing_names = sorted(path.name for path in (case_path / "reference_files").glob("*") if path.is_file())
        dataset_shell_names = sorted(Path(item).name for item in dataset_shell.reference_files)
        diagnostics = {
            "expected_reference_files": expected_names,
            "existing_reference_files": existing_names,
            "dataset_shell_reference_files": dataset_shell.reference_files,
        }
        for name in expected_names:
            if not (case_path / "reference_files" / name).exists():
                issues.append(GateIssue("error", "missing_reference_file", f"Missing expected reference file: {name}"))
        if sorted(expected_names) != dataset_shell_names:
            issues.append(GateIssue("error", "reference_file_manifest_mismatch", "dataset_shell reference_files do not match TaskBlueprint reference_files."))

        return GateSectionResult(
            section="reference_files",
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            diagnostics=diagnostics,
        )

    def _check_golden_artifacts(
        self,
        case_path: Path,
        blueprint: TaskBlueprint | None,
        golden_run: GoldenRun | None,
    ) -> GateSectionResult:
        issues: list[GateIssue] = []
        diagnostics: dict[str, Any] = {}
        if not blueprint or not golden_run:
            issues.append(GateIssue("error", "golden_artifact_check_unavailable", "Golden artifact checks could not run because required objects failed to load."))
            return GateSectionResult(section="golden_artifacts", passed=False, issues=issues)

        intermediate = self._load_json(case_path / "golden_run" / "golden_intermediate_values.json")
        grading = self._load_json(case_path / "golden_run" / "golden_grading_anchors.json")
        run_log = self._load_json(case_path / "golden_run" / "golden_run_log.json")

        required_states = list(blueprint.golden_plan.required_intermediate_states)
        present_states = sorted(intermediate.keys()) if isinstance(intermediate, dict) else []
        diagnostics = {
            "required_intermediate_states": required_states,
            "present_intermediate_states": present_states,
            "teacher_artifact_names": golden_run.expected_outputs.teacher_artifacts,
        }
        for state in required_states:
            if state not in present_states:
                issues.append(GateIssue("error", "missing_intermediate_state", f"Missing required golden intermediate state: {state}"))
        if not isinstance(grading, dict) or "golden_targets" not in grading:
            issues.append(GateIssue("error", "invalid_grading_anchors", "golden_grading_anchors.json is missing golden_targets."))
        if not isinstance(run_log, dict) or run_log.get("golden_run_id") != golden_run.golden_run_id:
            issues.append(GateIssue("error", "invalid_golden_run_log", "golden_run_log.json is missing the expected golden_run_id linkage."))

        return GateSectionResult(
            section="golden_artifacts",
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            diagnostics=diagnostics,
        )

    def _check_rw_task_export(self, rw_task_path: Path, dataset_shell: V2DatasetPackage | None) -> GateSectionResult:
        issues: list[GateIssue] = []
        diagnostics: dict[str, Any] = {}
        if not dataset_shell:
            issues.append(GateIssue("error", "rw_task_check_unavailable", "rw-task export checks could not run because dataset shell failed to load."))
            return GateSectionResult(section="rw_task_export", passed=False, issues=issues)

        dataset_row = self._load_json(rw_task_path / "dataset_row.json")
        diagnostics = {
            "dataset_row_task_id": dataset_row.get("task_id"),
            "dataset_shell_task_id": dataset_shell.task_id,
            "dataset_row_reference_files": dataset_row.get("reference_files"),
            "dataset_row_deliverable_files": dataset_row.get("deliverable_files"),
        }
        if dataset_row.get("task_id") != dataset_shell.task_id:
            issues.append(GateIssue("error", "rw_task_task_id_mismatch", "rw-task dataset_row task_id does not match dataset shell task_id."))
        if not dataset_row.get("rubric_json"):
            issues.append(GateIssue("error", "rw_task_missing_rubric_json", "rw-task dataset_row.json is missing rubric_json."))
        if not dataset_row.get("deliverable_files"):
            issues.append(GateIssue("warning", "rw_task_missing_deliverable_paths", "rw-task dataset_row.json has no deliverable_files listed."))

        return GateSectionResult(
            section="rw_task_export",
            passed=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            diagnostics=diagnostics,
        )

    def _load_model(self, path: Path, model_type):
        try:
            payload = self._load_json(path)
            return model_type.model_validate(payload)
        except Exception:
            return None

    def _load_json(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

