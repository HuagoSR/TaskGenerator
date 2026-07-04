from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_reference_file_generator import GeneratedFileManifest
from task_generator.v3_rubric_builder import RubricReport
from task_generator.v3_teacher_input_builder import TeacherInputValidationReport
from task_generator.v3_teacher_runner import TeacherRunnerReport
from task_generator.v3_training_annotation_builder import TrainingAnnotationReport
from task_generator.v3_source_schema import load_json_file


QualityDecision = Literal["reject", "revise", "candidate_ready"]
FindingSeverity = Literal["blocking", "revise", "info"]


class PipelineBQualityGateRequest(BaseModel):
    generated_file_manifest_path: str
    teacher_input_validation_report_path: str
    teacher_runner_report_path: str
    training_annotation_report_path: str
    rubric_report_path: str


class QualityGateFinding(BaseModel):
    finding_id: str
    reason_code: str
    severity: FindingSeverity
    message: str
    source_artifact: str
    details: Dict[str, Any] = Field(default_factory=dict)


class PipelineBQualityDecision(BaseModel):
    decision: QualityDecision
    reason_codes: List[str] = Field(default_factory=list)
    blocking_count: int = 0
    revise_count: int = 0


class PipelineBQualityReport(BaseModel):
    quality_gate_version: str = "v3.pipeline_b_quality_gate.1"
    request: PipelineBQualityGateRequest
    blueprint_id: str = "unknown"
    decision: PipelineBQualityDecision
    findings: List[QualityGateFinding] = Field(default_factory=list)
    readiness_by_artifact: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PipelineBQualityGate:
    """Summarize deterministic Pipeline B artifacts into a package-level decision."""

    DOSSIER_REASON_LAYER = {
        "dossier_missing_attachment_metadata": "reference_file_planning",
        "dossier_conflict_source_metadata": "reference_file_planning",
        "dossier_outdated_version_metadata": "reference_file_planning",
        "dossier_manager_notes_metadata": "teacher_operationalization",
    }

    def build(
        self,
        generated_file_manifest_path: str | Path,
        teacher_input_validation_report_path: str | Path,
        teacher_runner_report_path: str | Path,
        training_annotation_report_path: str | Path,
        rubric_report_path: str | Path,
    ) -> PipelineBQualityReport:
        request = PipelineBQualityGateRequest(
            generated_file_manifest_path=str(generated_file_manifest_path),
            teacher_input_validation_report_path=str(teacher_input_validation_report_path),
            teacher_runner_report_path=str(teacher_runner_report_path),
            training_annotation_report_path=str(training_annotation_report_path),
            rubric_report_path=str(rubric_report_path),
        )

        manifest, manifest_error = self._load_model(
            generated_file_manifest_path, GeneratedFileManifest, "generated_file_manifest"
        )
        teacher_input, teacher_input_error = self._load_model(
            teacher_input_validation_report_path,
            TeacherInputValidationReport,
            "teacher_input_validation_report",
        )
        teacher_report, teacher_error = self._load_model(
            teacher_runner_report_path, TeacherRunnerReport, "teacher_runner_report"
        )
        annotation_report, annotation_error = self._load_model(
            training_annotation_report_path,
            TrainingAnnotationReport,
            "training_annotation_report",
        )
        rubric_report, rubric_error = self._load_model(
            rubric_report_path, RubricReport, "rubric_report"
        )

        findings: List[QualityGateFinding] = []
        findings.extend(
            item
            for item in [
                manifest_error,
                teacher_input_error,
                teacher_error,
                annotation_error,
                rubric_error,
            ]
            if item is not None
        )

        if manifest:
            findings.extend(self._manifest_findings(manifest))
        if teacher_input:
            findings.extend(self._teacher_input_findings(teacher_input))
        if teacher_report:
            findings.extend(self._teacher_report_findings(teacher_report))
        if annotation_report:
            findings.extend(self._annotation_report_findings(annotation_report))
        if rubric_report:
            findings.extend(self._rubric_report_findings(rubric_report))

        findings.extend(
            self._cross_artifact_findings(
                teacher_input=teacher_input,
                teacher_report=teacher_report,
                annotation_report=annotation_report,
                rubric_report=rubric_report,
            )
        )

        decision = self._decision(findings)
        blueprint_id = self._blueprint_id(
            manifest=manifest,
            teacher_input=teacher_input,
            teacher_report=teacher_report,
            annotation_report=annotation_report,
            rubric_report=rubric_report,
        )

        return PipelineBQualityReport(
            request=request,
            blueprint_id=blueprint_id,
            decision=decision,
            findings=findings,
            readiness_by_artifact=self._readiness_by_artifact(
                teacher_input, teacher_report, annotation_report, rubric_report
            ),
            notes=[
                "Quality Gate V1 is deterministic and does not call LLM or external APIs.",
                "The gate is intentionally conservative: partial-ready chains are routed to revise.",
                "LLM teacher/prose generation should be scheduled only after this gate makes readiness explicit.",
                "Evidence dossier ecology signals are diagnostic revise findings in this slice and do not change gate thresholds.",
            ],
        )

    def write_outputs(self, report: PipelineBQualityReport, output_dir: str | Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "pipeline_b_quality_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {"quality_report_path": str(report_path)}

    def _load_model(self, path: str | Path, model_type, source_artifact: str):
        try:
            return model_type.model_validate(load_json_file(str(path))), None
        except Exception as exc:
            return None, self._finding(
                reason_code="unreadable_artifact",
                severity="blocking",
                source_artifact=source_artifact,
                message=f"Could not read or validate {source_artifact}.",
                details={"path": str(path), "error_type": type(exc).__name__, "error": str(exc)},
            )

    def _manifest_findings(self, manifest: GeneratedFileManifest) -> List[QualityGateFinding]:
        findings: List[QualityGateFinding] = []
        generated_files = [record for record in manifest.generated_files if record.status == "generated"]
        failed_files = [record for record in manifest.generated_files if record.status == "failed"]
        deferred_files = [
            record for record in manifest.generated_files if record.status in {"skipped", "failed"}
        ]

        if not generated_files or not manifest.evidence_index:
            findings.append(
                self._finding(
                    reason_code="missing_generated_source_evidence",
                    severity="blocking",
                    source_artifact="generated_file_manifest",
                    message="No generated candidate-visible evidence file or evidence index is available.",
                    details={
                        "generated_file_count": len(generated_files),
                        "evidence_index_count": len(manifest.evidence_index),
                    },
                )
            )

        for record in failed_files:
            findings.append(
                self._finding(
                    reason_code="reference_file_generation_failed",
                    severity="blocking",
                    source_artifact="generated_file_manifest",
                    message=f"Reference file generation failed for {record.file_name}.",
                    details={"file_name": record.file_name, "warnings": record.warnings},
                )
            )

        for record in deferred_files:
            reason_code = (
                "deferred_policy_reference"
                if "policy" in record.file_name.lower()
                else "deferred_reference_file"
            )
            findings.append(
                self._finding(
                    reason_code=reason_code,
                    severity="revise",
                    source_artifact="generated_file_manifest",
                    message=f"Reference file is deferred: {record.file_name}.",
                    details={
                        "file_name": record.file_name,
                        "status": record.status,
                        "skipped_reason": record.skipped_reason,
                    },
                )
            )
        return findings

    def _teacher_input_findings(
        self, report: TeacherInputValidationReport
    ) -> List[QualityGateFinding]:
        findings: List[QualityGateFinding] = []
        for finding in report.findings:
            if finding.severity == "blocking" and not finding.passed:
                findings.append(
                    self._finding(
                        reason_code=f"teacher_input_blocking:{finding.check_name}",
                        severity="blocking",
                        source_artifact="teacher_input_validation_report",
                        message=f"Teacher input blocking check failed: {finding.check_name}.",
                        details=finding.model_dump(),
                    )
                )
            elif finding.severity == "warning" and not finding.passed:
                findings.append(
                    self._finding(
                        reason_code=finding.check_name,
                        severity="revise",
                        source_artifact="teacher_input_validation_report",
                        message=self._warning_message(
                            finding.check_name,
                            source_artifact="teacher_input_validation_report",
                        ),
                        details=self._warning_details(finding.check_name, finding.model_dump()),
                    )
                )
        for check in report.relationship_checks:
            if not check.passed:
                severity: FindingSeverity = "blocking" if check.severity == "blocking" else "revise"
                findings.append(
                    self._finding(
                        reason_code=check.check_name,
                        severity=severity,
                        source_artifact="teacher_input_validation_report",
                        message=f"Teacher input relationship check failed: {check.check_name}.",
                        details=check.model_dump(),
                    )
                )
        return findings

    def _teacher_report_findings(self, report: TeacherRunnerReport) -> List[QualityGateFinding]:
        findings: List[QualityGateFinding] = []
        step_count = (
            report.diagnostics.complete_step_count
            + report.diagnostics.partial_step_count
            + report.diagnostics.blocked_step_count
        )
        if step_count == 0:
            findings.append(
                self._finding(
                    reason_code="zero_teacher_steps",
                    severity="blocking",
                    source_artifact="teacher_runner_report",
                    message="Teacher runner produced zero golden steps.",
                    details=report.diagnostics.model_dump(),
                )
            )
        if report.diagnostics.blocked_step_count > 0:
            findings.append(
                self._finding(
                    reason_code="blocked_teacher_steps",
                    severity="blocking",
                    source_artifact="teacher_runner_report",
                    message="Teacher runner has blocked golden steps.",
                    details=report.diagnostics.model_dump(),
                )
            )
        findings.extend(
            self._warning_code_findings(
                report.diagnostics.warning_reason_codes,
                source_artifact="teacher_runner_report",
            )
        )
        for gap in report.unresolved_gaps:
            reason_code = self._reason_from_gap(gap)
            findings.append(
                self._finding(
                    reason_code=reason_code,
                    severity="revise",
                    source_artifact="teacher_runner_report",
                    message=gap,
                    details=self._warning_details(reason_code, {"gap": gap}),
                )
            )
        return findings

    def _annotation_report_findings(
        self, report: TrainingAnnotationReport
    ) -> List[QualityGateFinding]:
        findings: List[QualityGateFinding] = []
        if report.diagnostics.blocked_item_count > 0:
            findings.append(
                self._finding(
                    reason_code="blocked_training_annotation_items",
                    severity="blocking",
                    source_artifact="training_annotation_report",
                    message="Training annotation contains blocked supervision items.",
                    details=report.diagnostics.model_dump(),
                )
            )
        findings.extend(
            self._warning_code_findings(
                report.diagnostics.warning_reason_codes,
                source_artifact="training_annotation_report",
            )
        )
        return findings

    def _rubric_report_findings(self, report: RubricReport) -> List[QualityGateFinding]:
        findings: List[QualityGateFinding] = []
        if report.diagnostics.criterion_count == 0:
            findings.append(
                self._finding(
                    reason_code="zero_rubric_criteria",
                    severity="blocking",
                    source_artifact="rubric_report",
                    message="Rubric contains zero criteria.",
                    details=report.diagnostics.model_dump(),
                )
            )
        if report.diagnostics.blocked_criterion_count > 0:
            findings.append(
                self._finding(
                    reason_code="blocked_rubric_criteria",
                    severity="blocking",
                    source_artifact="rubric_report",
                    message="Rubric contains blocked criteria.",
                    details=report.diagnostics.model_dump(),
                )
            )
        findings.extend(
            self._warning_code_findings(
                report.diagnostics.warning_reason_codes,
                source_artifact="rubric_report",
            )
        )
        return findings

    def _cross_artifact_findings(
        self,
        teacher_input: Optional[TeacherInputValidationReport],
        teacher_report: Optional[TeacherRunnerReport],
        annotation_report: Optional[TrainingAnnotationReport],
        rubric_report: Optional[RubricReport],
    ) -> List[QualityGateFinding]:
        readiness = [
            item.readiness
            for item in [teacher_input, teacher_report, annotation_report, rubric_report]
            if item is not None
        ]
        if any(item == "not_ready" for item in readiness):
            return [
                self._finding(
                    reason_code="not_ready_chain",
                    severity="blocking",
                    source_artifact="cross_artifact_readiness",
                    message="At least one Pipeline B artifact is not_ready.",
                    details={"readiness": readiness},
                )
            ]
        if any(item == "partial_ready" for item in readiness):
            return [
                self._finding(
                    reason_code="partial_ready_chain",
                    severity="revise",
                    source_artifact="cross_artifact_readiness",
                    message="At least one Pipeline B artifact is partial_ready.",
                    details={"readiness": readiness},
                )
            ]
        return []

    def _warning_code_findings(
        self, codes: List[str], source_artifact: str
    ) -> List[QualityGateFinding]:
        findings = []
        for code in codes:
            severity: FindingSeverity = "revise"
            findings.append(
                self._finding(
                    reason_code=code,
                    severity=severity,
                    source_artifact=source_artifact,
                    message=self._warning_message(code, source_artifact),
                    details=self._warning_details(code, {"warning_code": code}),
                )
            )
        return findings

    def _decision(self, findings: List[QualityGateFinding]) -> PipelineBQualityDecision:
        blocking_count = sum(1 for finding in findings if finding.severity == "blocking")
        revise_count = sum(1 for finding in findings if finding.severity == "revise")
        if blocking_count:
            decision: QualityDecision = "reject"
        elif revise_count:
            decision = "revise"
        else:
            decision = "candidate_ready"
        return PipelineBQualityDecision(
            decision=decision,
            reason_codes=sorted({finding.reason_code for finding in findings}),
            blocking_count=blocking_count,
            revise_count=revise_count,
        )

    def _readiness_by_artifact(
        self,
        teacher_input: Optional[TeacherInputValidationReport],
        teacher_report: Optional[TeacherRunnerReport],
        annotation_report: Optional[TrainingAnnotationReport],
        rubric_report: Optional[RubricReport],
    ) -> Dict[str, str]:
        values = {}
        if teacher_input:
            values["teacher_input_validation_report"] = teacher_input.readiness
        if teacher_report:
            values["teacher_runner_report"] = teacher_report.readiness
        if annotation_report:
            values["training_annotation_report"] = annotation_report.readiness
        if rubric_report:
            values["rubric_report"] = rubric_report.readiness
        return values

    def _blueprint_id(
        self,
        manifest: Optional[GeneratedFileManifest],
        teacher_input: Optional[TeacherInputValidationReport],
        teacher_report: Optional[TeacherRunnerReport],
        annotation_report: Optional[TrainingAnnotationReport],
        rubric_report: Optional[RubricReport],
    ) -> str:
        for item in [manifest, teacher_input, teacher_report, annotation_report, rubric_report]:
            if item is not None and getattr(item, "blueprint_id", None):
                return item.blueprint_id
        return "unknown"

    def _reason_from_gap(self, gap: str) -> str:
        if "dossier_missing_support_caveat" in gap or "dossier_missing_attachment_metadata" in gap:
            return "dossier_missing_attachment_metadata"
        if "dossier_conflict_resolution" in gap or "dossier_conflict_source_metadata" in gap:
            return "dossier_conflict_source_metadata"
        if "dossier_version_governance" in gap or "dossier_outdated_version_metadata" in gap:
            return "dossier_outdated_version_metadata"
        if "dossier_manager_escalation" in gap or "dossier_manager_notes_metadata" in gap:
            return "dossier_manager_notes_metadata"
        if "policy_reference.docx" in gap:
            return "deferred_policy_reference"
        if "policy_lookup" in gap:
            return "relationship:policy_lookup"
        if "low_subgraph_confidence" in gap:
            return "low_subgraph_confidence"
        if "single_source_support" in gap:
            return "single_source_support"
        if "Weak Pipeline A signal:" in gap or "pipeline_a_signal_gaps" in gap:
            return "pipeline_a_signal_gaps"
        return "unresolved_gap"

    def _warning_message(self, code: str, source_artifact: str) -> str:
        dossier_messages = {
            "dossier_missing_attachment_metadata": "Evidence dossier indicates missing support or missing attachments that should remain explicit.",
            "dossier_conflict_source_metadata": "Evidence dossier indicates conflicting evidence ecology that should remain explicit.",
            "dossier_outdated_version_metadata": "Evidence dossier indicates stale or prior-version ambiguity that should remain explicit.",
            "dossier_manager_notes_metadata": "Evidence dossier indicates manager-facing escalation or caveat context that should remain explicit.",
        }
        if code in dossier_messages:
            return dossier_messages[code]
        return f"Warning reason code requires revision review: {code}."

    def _warning_details(self, code: str, details: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(details)
        if code in self.DOSSIER_REASON_LAYER:
            enriched.update(
                {
                    "dossier_reason_family": "evidence_dossier",
                    "diagnostic_only": True,
                    "recommended_layer": self.DOSSIER_REASON_LAYER[code],
                }
            )
        return enriched

    def _finding(
        self,
        reason_code: str,
        severity: FindingSeverity,
        source_artifact: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> QualityGateFinding:
        return QualityGateFinding(
            finding_id=self._stable_id("qf", [reason_code, source_artifact, message]),
            reason_code=reason_code,
            severity=severity,
            source_artifact=source_artifact,
            message=message,
            details=details or {},
        )

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        import hashlib

        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
