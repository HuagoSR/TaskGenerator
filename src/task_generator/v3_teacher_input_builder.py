import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v2_schema import TaskBlueprint
from task_generator.v3_reference_file_generator import GeneratedFileManifest
from task_generator.v3_reference_file_planner import ReferenceFilePlan
from task_generator.v3_pipeline_b_sampler import PipelineBSubgraph
from task_generator.v3_source_schema import load_json_file


TeacherReadiness = Literal["not_ready", "partial_ready", "teacher_ready"]
CheckSeverity = Literal["info", "warning", "blocking"]


class TeacherInputRequest(BaseModel):
    blueprint_path: str
    subgraph_report_path: str
    reference_file_plan_path: str
    generated_file_manifest_path: str
    pipeline_a_feedback_path: Optional[str] = None
    prototype_report_path: Optional[str] = None


class CandidateFileView(BaseModel):
    file_name: str
    file_role: str
    status: str
    relative_path: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)


class CandidateView(BaseModel):
    scenario_title: str
    role: str
    business_context: str
    time_context: str
    tone: str
    visible_requirements: List[str] = Field(default_factory=list)
    style_constraints: List[str] = Field(default_factory=list)
    reference_files: List[CandidateFileView] = Field(default_factory=list)
    deliverables: List[Dict[str, Any]] = Field(default_factory=list)


class SkillIntention(BaseModel):
    skill_id: str
    canonical_name: str
    capability_tags: List[str] = Field(default_factory=list)
    graph_role_hints: List[str] = Field(default_factory=list)
    motif_hints: List[str] = Field(default_factory=list)
    training_intent: str
    selection_rationale: str = ""
    risk_notes: List[str] = Field(default_factory=list)
    common_failure_signals: List[str] = Field(default_factory=list)


class EvidenceContractItem(BaseModel):
    evidence_id: str
    file_name: str
    locator: str
    physical_location: str
    semantic_type: str


class TeacherView(BaseModel):
    selected_motif: str
    subgraph_id: str
    subgraph_confidence: str
    hidden_requirements: List[str] = Field(default_factory=list)
    required_intermediate_states: List[str] = Field(default_factory=list)
    required_final_checks: List[str] = Field(default_factory=list)
    skill_intentions: List[SkillIntention] = Field(default_factory=list)
    hidden_hints: List[str] = Field(default_factory=list)
    deferred_assets: List[str] = Field(default_factory=list)
    pipeline_a_feedback: List[Dict[str, Any]] = Field(default_factory=list)
    missing_or_weak_pipeline_a_signals: List[str] = Field(default_factory=list)
    evidence_contract: List[EvidenceContractItem] = Field(default_factory=list)


class ValidationFinding(BaseModel):
    check_name: str
    severity: CheckSeverity
    passed: bool
    details: str = ""


class TeacherInputDiagnostics(BaseModel):
    readiness: TeacherReadiness
    generated_candidate_file_count: int = 0
    deferred_candidate_file_count: int = 0
    evidence_contract_count: int = 0
    relationship_check_count: int = 0
    blocking_reason_codes: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)


class TeacherInputManifest(BaseModel):
    teacher_input_version: str = "v3.teacher_input.1"
    request: TeacherInputRequest
    blueprint_id: str
    template_family: str
    candidate_view: CandidateView
    teacher_view: TeacherView
    diagnostics: TeacherInputDiagnostics
    notes: List[str] = Field(default_factory=list)


class TeacherInputValidationReport(BaseModel):
    teacher_input_validation_version: str = "v3.teacher_input_validation.1"
    blueprint_id: str
    readiness: TeacherReadiness
    findings: List[ValidationFinding] = Field(default_factory=list)
    relationship_checks: List[ValidationFinding] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TeacherInputBuilder:
    """Build a teacher-mode input contract from current Pipeline B artifacts."""

    def build(
        self,
        blueprint_path: str | Path,
        subgraph_report_path: str | Path,
        reference_file_plan_path: str | Path,
        generated_file_manifest_path: str | Path,
        pipeline_a_feedback_path: Optional[str | Path] = None,
        prototype_report_path: Optional[str | Path] = None,
    ) -> tuple[TeacherInputManifest, TeacherInputValidationReport]:
        blueprint = TaskBlueprint.model_validate(load_json_file(str(blueprint_path)))
        subgraph = PipelineBSubgraph.model_validate(load_json_file(str(subgraph_report_path)))
        reference_plan = ReferenceFilePlan.model_validate(load_json_file(str(reference_file_plan_path)))
        generated_manifest = GeneratedFileManifest.model_validate(load_json_file(str(generated_file_manifest_path)))
        pipeline_a_feedback = (
            load_json_file(str(pipeline_a_feedback_path)).get("feedback_items", []) if pipeline_a_feedback_path else []
        )
        prototype_report = load_json_file(str(prototype_report_path)) if prototype_report_path else {}

        candidate_view = self._candidate_view(blueprint, reference_plan, generated_manifest)
        teacher_view = self._teacher_view(
            blueprint=blueprint,
            subgraph=subgraph,
            reference_plan=reference_plan,
            generated_manifest=generated_manifest,
            pipeline_a_feedback=pipeline_a_feedback,
        )
        validation_report = self._validation_report(
            blueprint=blueprint,
            reference_plan=reference_plan,
            generated_manifest=generated_manifest,
            teacher_view=teacher_view,
        )
        diagnostics = self._diagnostics(candidate_view, teacher_view, validation_report)

        manifest = TeacherInputManifest(
            request=TeacherInputRequest(
                blueprint_path=str(blueprint_path),
                subgraph_report_path=str(subgraph_report_path),
                reference_file_plan_path=str(reference_file_plan_path),
                generated_file_manifest_path=str(generated_file_manifest_path),
                pipeline_a_feedback_path=str(pipeline_a_feedback_path) if pipeline_a_feedback_path else None,
                prototype_report_path=str(prototype_report_path) if prototype_report_path else None,
            ),
            blueprint_id=blueprint.blueprint_id,
            template_family=blueprint.template_family,
            candidate_view=candidate_view,
            teacher_view=teacher_view,
            diagnostics=diagnostics,
            notes=[
                "Candidate-visible instructions and teacher-visible supervision are separated intentionally.",
                "Teacher view carries Pipeline A uncertainty forward instead of hiding it from later teacher-mode steps.",
                "This artifact is a pre-TeacherRunner contract and does not contain a solved answer yet.",
            ],
        )

        if prototype_report:
            manifest.notes.append(
                "Prototype report was available and can be used as a supporting diagnostic artifact."
            )

        return manifest, validation_report

    def write_outputs(
        self,
        manifest: TeacherInputManifest,
        validation_report: TeacherInputValidationReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        manifest_path = output_path / "teacher_input_manifest.json"
        validation_path = output_path / "teacher_input_validation_report.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        validation_path.write_text(validation_report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "teacher_input_manifest_path": str(manifest_path),
            "teacher_input_validation_report_path": str(validation_path),
        }

    def _candidate_view(
        self,
        blueprint: TaskBlueprint,
        reference_plan: ReferenceFilePlan,
        generated_manifest: GeneratedFileManifest,
    ) -> CandidateView:
        generated_by_name = {record.file_name: record for record in generated_manifest.generated_files}
        evidence_by_file = self._evidence_ids_by_file(generated_manifest)
        reference_files = []
        for planned_file in reference_plan.planned_files:
            record = generated_by_name.get(planned_file.file_name)
            reference_files.append(
                CandidateFileView(
                    file_name=planned_file.file_name,
                    file_role=planned_file.file_role,
                    status=record.status if record else "missing",
                    relative_path=record.relative_path if record else None,
                    evidence_ids=evidence_by_file.get(planned_file.file_name, []),
                )
            )

        return CandidateView(
            scenario_title=blueprint.task_metadata.scenario_title,
            role=blueprint.scenario_spec.role,
            business_context=blueprint.scenario_spec.business_context,
            time_context=blueprint.scenario_spec.time_context,
            tone=blueprint.scenario_spec.tone,
            visible_requirements=blueprint.prompt_spec.visible_requirements,
            style_constraints=blueprint.prompt_spec.style_constraints,
            reference_files=reference_files,
            deliverables=[
                {
                    "file_name": deliverable.file_name,
                    "file_role": deliverable.file_role,
                    "requirements": deliverable.requirements,
                }
                for deliverable in blueprint.deliverable_spec
            ],
        )

    def _teacher_view(
        self,
        blueprint: TaskBlueprint,
        subgraph: PipelineBSubgraph,
        reference_plan: ReferenceFilePlan,
        generated_manifest: GeneratedFileManifest,
        pipeline_a_feedback: List[Dict[str, Any]],
    ) -> TeacherView:
        generated_by_name = {record.file_name: record for record in generated_manifest.generated_files}
        deferred_assets = [
            record.file_name
            for record in generated_manifest.generated_files
            if record.status in {"skipped", "failed"}
        ]

        hidden_hints = list(blueprint.prompt_spec.hidden_requirements)
        for deliverable in blueprint.deliverable_spec:
            hidden_hints.append(
                "Deliverable contract: "
                + deliverable.file_name
                + " must cover "
                + "; ".join(deliverable.requirements)
                + "."
            )
        hidden_hints.extend(
            f"Pipeline A feedback: {item.get('message', '')}"
            for item in pipeline_a_feedback
            if item.get("message")
        )
        hidden_hints.extend(
            f"Deferred asset: {file_name}" for file_name in deferred_assets
        )
        if any(item.file_name == "policy_reference.docx" for item in generated_manifest.evidence_index):
            hidden_hints.append(
                "Policy clause IDs are candidate-visible and should be cited explicitly whenever policy logic is invoked."
            )
        hidden_hints.extend(self._dossier_hidden_hints(reference_plan))

        skill_intentions = []
        for skill in subgraph.selected_skills:
            skill_intentions.append(
                SkillIntention(
                    skill_id=skill.skill_id,
                    canonical_name=skill.canonical_name,
                    capability_tags=skill.capability_tags,
                    graph_role_hints=skill.graph_role_hints,
                    motif_hints=skill.motif_hints,
                    training_intent=self._training_intent(skill),
                    selection_rationale=skill.selection_reason,
                    risk_notes=self._skill_risk_notes(skill),
                    common_failure_signals=list(skill.reason_codes),
                )
            )

        evidence_contract = [
            EvidenceContractItem(
                evidence_id=item.evidence_id,
                file_name=item.file_name,
                locator=item.locator,
                physical_location=item.physical_location,
                semantic_type=item.semantic_type,
            )
            for item in generated_manifest.evidence_index
        ]

        return TeacherView(
            selected_motif=subgraph.selected_motif,
            subgraph_id=subgraph.subgraph_id,
            subgraph_confidence=subgraph.diagnostics.confidence,
            hidden_requirements=blueprint.prompt_spec.hidden_requirements,
            required_intermediate_states=blueprint.golden_plan.required_intermediate_states,
            required_final_checks=blueprint.golden_plan.required_final_checks,
            skill_intentions=skill_intentions,
            hidden_hints=hidden_hints,
            deferred_assets=deferred_assets,
            pipeline_a_feedback=pipeline_a_feedback,
            missing_or_weak_pipeline_a_signals=subgraph.diagnostics.missing_or_weak_pipeline_a_signals,
            evidence_contract=evidence_contract,
        )

    def _validation_report(
        self,
        blueprint: TaskBlueprint,
        reference_plan: ReferenceFilePlan,
        generated_manifest: GeneratedFileManifest,
        teacher_view: TeacherView,
    ) -> TeacherInputValidationReport:
        findings: List[ValidationFinding] = []
        relationship_checks: List[ValidationFinding] = []
        generated_by_name = {record.file_name: record for record in generated_manifest.generated_files}
        evidence_ids = {item.evidence_id for item in generated_manifest.evidence_index}

        findings.append(
            ValidationFinding(
                check_name="candidate_visible_files_exist_or_are_explicitly_deferred",
                severity="blocking",
                passed=all(
                    record.status in {"generated", "skipped"}
                    for record in generated_manifest.generated_files
                ),
                details="Generated files must exist or be explicitly marked deferred.",
            )
        )
        findings.append(
            ValidationFinding(
                check_name="evidence_index_nonempty",
                severity="blocking",
                passed=bool(generated_manifest.evidence_index),
                details=f"evidence_count={len(generated_manifest.evidence_index)}",
            )
        )
        findings.append(
            ValidationFinding(
                check_name="required_intermediate_states_present",
                severity="blocking",
                passed=bool(teacher_view.required_intermediate_states),
                details="Teacher mode requires explicit intermediate states.",
            )
        )
        findings.append(
            ValidationFinding(
                check_name="selected_skills_have_teacher_intentions",
                severity="blocking",
                passed=len(teacher_view.skill_intentions) == len(blueprint.selected_skills),
                details=f"intentions={len(teacher_view.skill_intentions)} selected_skills={len(blueprint.selected_skills)}",
            )
        )
        findings.append(
            ValidationFinding(
                check_name="deferred_assets_are_visible_to_teacher",
                severity="warning",
                passed=True,
                details=", ".join(teacher_view.deferred_assets) if teacher_view.deferred_assets else "none",
            )
        )
        findings.append(
            ValidationFinding(
                check_name="subgraph_confidence_recorded",
                severity="warning",
                passed=bool(teacher_view.subgraph_confidence),
                details=teacher_view.subgraph_confidence,
            )
        )
        findings.extend(self._dossier_validation_findings(reference_plan))

        for relationship in reference_plan.data_relationships:
            relationship_checks.append(
                self._relationship_check(relationship, generated_by_name, evidence_ids)
            )

        readiness = self._readiness(findings, relationship_checks, teacher_view)
        return TeacherInputValidationReport(
            blueprint_id=blueprint.blueprint_id,
            readiness=readiness,
            findings=findings,
            relationship_checks=relationship_checks,
            notes=[
                "Relationship checks are structural in this slice; they do not yet validate business semantics.",
                "Deferred assets lower readiness but do not block the candidate-visible artifact chain from existing.",
            ],
        )

    def _relationship_check(
        self,
        relationship: Dict[str, Any],
        generated_by_name: Dict[str, Any],
        evidence_ids: set[str],
    ) -> ValidationFinding:
        left_status = self._endpoint_status(relationship.get("left", ""), generated_by_name)
        right_status = self._endpoint_status(relationship.get("right", ""), generated_by_name)
        relation_type = relationship.get("relation_type", "unknown")

        if left_status == "generated" and right_status in {"generated", "deliverable_placeholder"}:
            return ValidationFinding(
                check_name=f"relationship:{relation_type}",
                severity="info",
                passed=True,
                details=f"left={relationship.get('left')} right={relationship.get('right')}",
            )

        severity: CheckSeverity = "warning"
        if "missing" in {left_status, right_status}:
            severity = "blocking"
        if "deferred" in {left_status, right_status}:
            severity = "warning"

        return ValidationFinding(
            check_name=f"relationship:{relation_type}",
            severity=severity,
            passed=False,
            details=(
                f"left_status={left_status} right_status={right_status} "
                f"left={relationship.get('left')} right={relationship.get('right')}"
            ),
        )

    def _endpoint_status(self, endpoint: str, generated_by_name: Dict[str, Any]) -> str:
        if endpoint.startswith("final_deliverable:"):
            return "deliverable_placeholder"
        file_name = endpoint.split(":", 1)[0]
        record = generated_by_name.get(file_name)
        if record is None:
            return "missing"
        if record.status == "generated":
            return "generated"
        if record.status == "skipped":
            return "deferred"
        return "failed"

    def _readiness(
        self,
        findings: List[ValidationFinding],
        relationship_checks: List[ValidationFinding],
        teacher_view: TeacherView,
    ) -> TeacherReadiness:
        all_checks = findings + relationship_checks
        blocking_failures = [check for check in all_checks if check.severity == "blocking" and not check.passed]
        warning_failures = [check for check in all_checks if check.severity == "warning" and not check.passed]
        if blocking_failures:
            return "not_ready"
        if warning_failures or teacher_view.deferred_assets:
            return "partial_ready"
        return "teacher_ready"

    def _diagnostics(
        self,
        candidate_view: CandidateView,
        teacher_view: TeacherView,
        validation_report: TeacherInputValidationReport,
    ) -> TeacherInputDiagnostics:
        blocking_reason_codes = [
            finding.check_name
            for finding in (validation_report.findings + validation_report.relationship_checks)
            if finding.severity == "blocking" and not finding.passed
        ]
        warning_reason_codes = [
            finding.check_name
            for finding in (validation_report.findings + validation_report.relationship_checks)
            if finding.severity == "warning" and not finding.passed
        ]
        return TeacherInputDiagnostics(
            readiness=validation_report.readiness,
            generated_candidate_file_count=sum(
                1 for file_view in candidate_view.reference_files if file_view.status == "generated"
            ),
            deferred_candidate_file_count=sum(
                1 for file_view in candidate_view.reference_files if file_view.status != "generated"
            ),
            evidence_contract_count=len(teacher_view.evidence_contract),
            relationship_check_count=len(validation_report.relationship_checks),
            blocking_reason_codes=blocking_reason_codes,
            warning_reason_codes=warning_reason_codes,
        )

    def _dossier_hidden_hints(self, reference_plan: ReferenceFilePlan) -> List[str]:
        hints: List[str] = []
        dossier = reference_plan.evidence_dossier
        role_by_file_id = {item.file_id: item for item in dossier.file_roles}

        if dossier.synthetic_artifacts:
            hints.append(
                "Evidence dossier metadata includes metadata-only artifacts; unresolved support, conflict, or stale-version ecology should stay visible in teacher reasoning."
            )

        for artifact in dossier.synthetic_artifacts:
            if artifact.role == "missing_attachment":
                hints.append(
                    "Evidence dossier indicates a missing attachment placeholder; teacher outputs should preserve the support gap explicitly instead of treating the record as complete."
                )
            elif artifact.role == "conflict_source":
                hints.append(
                    "Evidence dossier indicates a conflict source placeholder; teacher outputs should distinguish unresolved disagreement from confirmed findings."
                )
            elif artifact.role == "outdated_version":
                hints.append(
                    "Evidence dossier indicates a stale or prior-version placeholder; teacher outputs should avoid silently treating outdated material as governing evidence."
                )
            elif artifact.role == "manager_notes":
                hints.append(
                    "Evidence dossier implies manager-facing notes or review context; teacher outputs should preserve escalation or caveat language where support is incomplete."
                )

        if any(item.contains_missing_fields for item in role_by_file_id.values()):
            hints.append(
                "At least one candidate-visible file is marked as containing missing fields; teacher outputs should preserve incompleteness as a first-class caveat."
            )
        if any(item.contains_conflict for item in role_by_file_id.values()):
            hints.append(
                "At least one candidate-visible file is marked as containing conflict; teacher outputs should preserve reconciliation logic rather than flattening disagreement."
            )
        return hints

    def _dossier_validation_findings(self, reference_plan: ReferenceFilePlan) -> List[ValidationFinding]:
        dossier = reference_plan.evidence_dossier
        findings: List[ValidationFinding] = []
        file_roles = dossier.file_roles
        synthetic_by_role = {artifact.role: artifact for artifact in dossier.synthetic_artifacts}
        conflict_artifact = synthetic_by_role.get("conflict_source")
        conflict_reason_codes = set(conflict_artifact.reason_codes) if conflict_artifact else set()
        motif_native_conflict = bool(
            {"motif:cross_check_validation", "motif:fan_in_reconciliation"} & conflict_reason_codes
        )

        findings.append(
            ValidationFinding(
                check_name="dossier_metadata_present",
                severity="info",
                passed=bool(dossier.dossier_id),
                details=f"dossier_id={dossier.dossier_id}",
            )
        )
        if any(item.contains_missing_fields for item in file_roles) or "missing_attachment" in synthetic_by_role:
            findings.append(
                ValidationFinding(
                    check_name="dossier_missing_attachment_metadata",
                    severity="warning",
                    passed=False,
                    details="Dossier metadata indicates missing support or attachment gaps that should remain explicit.",
                )
            )
        if any(item.contains_conflict for item in file_roles) or "conflict_source" in synthetic_by_role:
            findings.append(
                ValidationFinding(
                    check_name="dossier_conflict_source_metadata",
                    severity="info" if motif_native_conflict else "warning",
                    passed=True if motif_native_conflict else False,
                    details=(
                        "Dossier metadata indicates motif-native conflicting source ecology; "
                        "teacher reasoning should preserve the conflict explicitly without treating it as a readiness downgrade."
                        if motif_native_conflict
                        else "Dossier metadata indicates conflicting source ecology that should remain explicit in teacher reasoning."
                    ),
                )
            )
        if any(
            item.version_relation and item.version_relation != "current"
            for item in file_roles
        ) or "outdated_version" in synthetic_by_role:
            findings.append(
                ValidationFinding(
                    check_name="dossier_outdated_version_metadata",
                    severity="warning",
                    passed=False,
                    details="Dossier metadata indicates a stale or prior-version source that should not be treated as governing by default.",
                )
            )
        if "manager_notes" in synthetic_by_role:
            findings.append(
                ValidationFinding(
                    check_name="dossier_manager_notes_metadata",
                    severity="warning",
                    passed=False,
                    details="Dossier metadata implies manager-facing review context or escalation-oriented notes.",
                )
            )
        return findings

    def _evidence_ids_by_file(self, generated_manifest: GeneratedFileManifest) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for mapping in generated_manifest.evidence_index:
            result.setdefault(mapping.file_name, []).append(mapping.evidence_id)
        return result

    def _training_intent(self, skill: Any) -> str:
        capability_text = ", ".join(skill.capability_tags) if skill.capability_tags else "general reasoning"
        motif_text = ", ".join(skill.motif_hints) if skill.motif_hints else "task assembly"
        sentence = (
            f"Train the model to apply {skill.canonical_name.lower()} with emphasis on "
            f"{capability_text} inside motif(s): {motif_text}."
        )
        lowered = skill.canonical_name.lower()
        if any(token in lowered for token in ["policy", "tax", "withholding", "requirement"]):
            sentence += " Require explicit policy-clause and evidence-ID linkage."
        if any(token in lowered for token in ["reconcile", "consolidate", "report"]):
            sentence += " Require a manager-ready deliverable step instead of loose notes."
        return sentence

    def _skill_risk_notes(self, skill: Any) -> List[str]:
        notes = []
        if "single_source_support" in skill.reason_codes:
            notes.append("Single-source support means the teacher should check provenance carefully.")
        if not skill.graph_role_hints or "unclassified" in skill.graph_role_hints:
            notes.append("Graph role coverage is incomplete for this skill in the current subgraph.")
        lowered = skill.canonical_name.lower()
        if any(token in lowered for token in ["policy", "tax", "withholding", "requirement"]):
            notes.append("Policy-sensitive reasoning should cite clause IDs and evidence IDs together.")
        return notes
